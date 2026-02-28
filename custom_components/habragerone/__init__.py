from __future__ import annotations

import logging
import ssl
from collections import Counter
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from pybragerone import BragerOneApiClient, BragerOneGateway
from pybragerone.api.server import Platform, server_for
from pybragerone.models.param import ParamStore

from .bootstrap import async_build_bootstrap_payload, normalize_cached_descriptors
from .const import (
    CONF_BACKEND_PLATFORM,
    CONF_ENTITY_DESCRIPTORS,
    CONF_ENTITY_FILTER_MODE,
    CONF_LANGUAGE,
    CONF_MODULE_FILTER_MODES,
    CONF_MODULES,
    CONF_MODULES_META,
    CONF_OBJECT_ID,
    DATA_API,
    DATA_GATEWAY,
    DATA_RUNTIME,
    DATA_STORE,
    DEFAULT_ENTITY_FILTER_MODE,
    DOMAIN,
    PLATFORMS,
)
from .runtime import BragerRuntime

LOGGER = logging.getLogger(__name__)


def _build_ssl_context() -> ssl.SSLContext:
    """Create SSL context outside the HA event loop."""
    return ssl.create_default_context()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BragerOne from a config entry."""
    email = str(entry.data[CONF_EMAIL])
    password = str(entry.data[CONF_PASSWORD])
    object_id = int(entry.options.get(CONF_OBJECT_ID, entry.data[CONF_OBJECT_ID]))
    modules_raw = entry.options.get(CONF_MODULES, entry.data.get(CONF_MODULES, []))
    modules = [str(module) for module in modules_raw] if isinstance(modules_raw, list) else []
    platform_raw = str(entry.data.get(CONF_BACKEND_PLATFORM, Platform.BRAGERONE.value)).strip().lower()
    language = str(entry.data.get(CONF_LANGUAGE, "")).strip().lower() or None
    entity_filter_mode = (
        str(
            entry.options.get(
                CONF_ENTITY_FILTER_MODE,
                entry.data.get(CONF_ENTITY_FILTER_MODE, DEFAULT_ENTITY_FILTER_MODE),
            )
        )
        .strip()
        .lower()
        or DEFAULT_ENTITY_FILTER_MODE
    )
    module_filter_modes_raw = entry.options.get(
        CONF_MODULE_FILTER_MODES,
        entry.data.get(CONF_MODULE_FILTER_MODES, {}),
    )
    module_filter_modes_source = module_filter_modes_raw if isinstance(module_filter_modes_raw, dict) else {}
    module_filter_modes = {
        str(devid): str(mode).strip().lower() for devid, mode in module_filter_modes_source.items() if str(devid).strip()
    }

    try:
        server = server_for(platform_raw)
    except Exception as err:
        raise ConfigEntryNotReady(f"Unsupported backend platform '{platform_raw}'") from err

    verify_context = await hass.async_add_executor_job(_build_ssl_context)
    api = BragerOneApiClient(server=server, verify=verify_context)
    try:
        await api.ensure_auth(email, password)
    except Exception as err:
        raise ConfigEntryNotReady(f"Authentication failed for BragerOne entry {entry.entry_id}") from err

    data_object_id = int(entry.data[CONF_OBJECT_ID])
    data_modules_raw = entry.data.get(CONF_MODULES, [])
    data_modules = [str(module) for module in data_modules_raw] if isinstance(data_modules_raw, list) else []
    data_filter_mode = str(entry.data.get(CONF_ENTITY_FILTER_MODE, DEFAULT_ENTITY_FILTER_MODE)).strip().lower()
    data_module_filter_modes_raw = entry.data.get(CONF_MODULE_FILTER_MODES, {})
    data_module_filter_modes_source = data_module_filter_modes_raw if isinstance(data_module_filter_modes_raw, dict) else {}
    data_module_filter_modes = {
        str(devid): str(mode).strip().lower() for devid, mode in data_module_filter_modes_source.items() if str(devid).strip()
    }
    options_changed = (
        object_id != data_object_id
        or modules != data_modules
        or entity_filter_mode != data_filter_mode
        or module_filter_modes != data_module_filter_modes
    )
    missing_cached_payload = not isinstance(entry.data.get(CONF_MODULES_META), dict) or not isinstance(
        entry.data.get(CONF_ENTITY_DESCRIPTORS), list
    )

    modules_meta = entry.data.get(CONF_MODULES_META)
    descriptors = entry.data.get(CONF_ENTITY_DESCRIPTORS)
    if options_changed or missing_cached_payload:
        LOGGER.debug(
            "Refreshing bootstrap for entry %s (options_changed=%s, missing_cached_payload=%s, object_id=%s, modules=%s)",
            entry.entry_id,
            options_changed,
            missing_cached_payload,
            object_id,
            len(modules),
        )
        bootstrap_payload = await async_build_bootstrap_payload(
            api=api,
            object_id=object_id,
            modules=modules,
            language=language,
            entity_filter_mode=entity_filter_mode,
            module_filter_modes=module_filter_modes,
        )
        platform_counter: Counter[str] = Counter()
        for descriptor in bootstrap_payload[CONF_ENTITY_DESCRIPTORS]:
            if isinstance(descriptor, dict):
                platform_counter[str(descriptor.get("platform", "sensor"))] += 1
        LOGGER.debug(
            "Bootstrap refresh completed for entry %s (descriptors_total=%s, platform_breakdown=%s)",
            entry.entry_id,
            len(bootstrap_payload[CONF_ENTITY_DESCRIPTORS]),
            dict(sorted(platform_counter.items())),
        )
        updated_data = dict(entry.data)
        updated_data[CONF_OBJECT_ID] = object_id
        updated_data[CONF_MODULES] = modules
        updated_data.update(bootstrap_payload)
        hass.config_entries.async_update_entry(entry, data=updated_data)
        modules_meta = bootstrap_payload[CONF_MODULES_META]
        descriptors = bootstrap_payload[CONF_ENTITY_DESCRIPTORS]
    else:
        descriptors_list = descriptors if isinstance(descriptors, list) else []
        normalized_descriptors = normalize_cached_descriptors(descriptors_list)
        if normalized_descriptors != descriptors:
            updated_data = dict(entry.data)
            updated_data[CONF_ENTITY_DESCRIPTORS] = normalized_descriptors
            hass.config_entries.async_update_entry(entry, data=updated_data)
            descriptors = normalized_descriptors

    store = ParamStore()
    gateway = BragerOneGateway(api=api, object_id=object_id, modules=modules)
    runtime = BragerRuntime(
        api=api,
        gateway=gateway,
        store=store,
        modules_meta={str(k): dict(v) for k, v in modules_meta.items()} if isinstance(modules_meta, dict) else {},
    )
    await runtime.start()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = {
        DATA_API: api,
        DATA_GATEWAY: gateway,
        DATA_STORE: store,
        DATA_RUNTIME: runtime,
        CONF_ENTITY_DESCRIPTORS: descriptors,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload BragerOne config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False

    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data is None:
        return True

    runtime = data.get(DATA_RUNTIME)
    if isinstance(runtime, BragerRuntime):
        await runtime.stop()

    if not hass.data.get(DOMAIN):
        hass.data.pop(DOMAIN, None)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry after options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(_hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy entries to the current schema."""
    data: dict[str, Any] = dict(entry.data)
    changed = False

    if "email" in data and CONF_EMAIL not in data:
        data[CONF_EMAIL] = data.pop("email")
        changed = True
    if "password" in data and CONF_PASSWORD not in data:
        data[CONF_PASSWORD] = data.pop("password")
        changed = True
    if "object_id" in data and CONF_OBJECT_ID not in data:
        data[CONF_OBJECT_ID] = data.pop("object_id")
        changed = True
    if "modules" in data and CONF_MODULES not in data:
        data[CONF_MODULES] = data.pop("modules")
        changed = True

    if changed:
        _hass.config_entries.async_update_entry(entry, data=data, version=2)
        LOGGER.info("Migrated BragerOne config entry %s to version 2", entry.entry_id)

    return True
