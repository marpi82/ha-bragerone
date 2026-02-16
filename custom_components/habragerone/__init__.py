from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from pybragerone import BragerOneApiClient, BragerOneGateway
from pybragerone.models.param import ParamStore
from pybragerone.models.param_resolver import ParamResolver

from .bootstrap import async_build_bootstrap_payload
from .const import (
    CONF_ENTITY_DESCRIPTORS,
    CONF_MODULES,
    CONF_MODULES_META,
    CONF_OBJECT_ID,
    DATA_API,
    DATA_GATEWAY,
    DATA_RESOLVER,
    DATA_RUNTIME,
    DATA_STORE,
    DOMAIN,
    PLATFORMS,
)
from .runtime import BragerRuntime

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BragerOne from a config entry."""
    email = str(entry.data[CONF_EMAIL])
    password = str(entry.data[CONF_PASSWORD])
    object_id = int(entry.data[CONF_OBJECT_ID])
    modules = [str(module) for module in entry.data.get(CONF_MODULES, [])]

    api = BragerOneApiClient()
    try:
        await api.ensure_auth(email, password)
    except Exception as err:
        raise ConfigEntryNotReady(f"Authentication failed for BragerOne entry {entry.entry_id}") from err

    modules_meta = entry.data.get(CONF_MODULES_META)
    descriptors = entry.data.get(CONF_ENTITY_DESCRIPTORS)
    if not isinstance(modules_meta, dict) or not isinstance(descriptors, list):
        bootstrap_payload = await async_build_bootstrap_payload(api=api, object_id=object_id, modules=modules)
        updated_data = dict(entry.data)
        updated_data.update(bootstrap_payload)
        hass.config_entries.async_update_entry(entry, data=updated_data)
        modules_meta = bootstrap_payload[CONF_MODULES_META]
        descriptors = bootstrap_payload[CONF_ENTITY_DESCRIPTORS]

    store = ParamStore()
    resolver = ParamResolver.from_api(api=api, store=store)
    gateway = BragerOneGateway(api=api, object_id=object_id, modules=modules)
    runtime = BragerRuntime(
        api=api,
        gateway=gateway,
        store=store,
        resolver=resolver,
        modules_meta={str(k): dict(v) for k, v in modules_meta.items()} if isinstance(modules_meta, dict) else {},
    )
    await runtime.start()

    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = {
        DATA_API: api,
        DATA_GATEWAY: gateway,
        DATA_STORE: store,
        DATA_RESOLVER: resolver,
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
