"""Shared helpers for BragerOne entity platforms."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import slugify
from pybragerone.models.param import ParamStore

from .const import (
    CONF_DEVICE_GROUPING,
    CONF_ENABLED_BY_DEFAULT,
    CONF_ENTITY_DESCRIPTORS,
    CONF_ENUM_MAP,
    CONF_MODULES,
    CONF_OPTIONS,
    CONF_PLATFORM,
    CONF_RAW_TO_LABEL,
    CONF_ROUTE_VISIBILITY_DEPS,
    CONF_UI_ROUTE_SYMBOL,
    CONNECTION_MENU_KEY,
    DATA_ENTITY_STATS,
    DATA_RUNTIME,
    DEFAULT_DEVICE_GROUPING,
    DEVICE_GROUPING_BY_MENU,
    DEVICE_GROUPING_MODES,
    DOMAIN,
)
from .runtime import BragerRuntime


def collect_resolver_warm_symbols(items: Iterable[Any]) -> list[str]:
    """Return symbol names that benefit from bulk ParamResolver prefetch at startup."""
    symbols: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip()
        if not symbol or symbol in seen:
            continue
        if symbol.startswith("STATUS_"):
            seen.add(symbol)
            symbols.append(symbol)
            continue
        mapping = item.get("mapping")
        if not isinstance(mapping, dict):
            continue
        channels = mapping.get("channels")
        if isinstance(channels, dict) and isinstance(channels.get("unit"), list) and channels.get("unit"):
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def device_grouping_mode(entry: ConfigEntry) -> str:
    """Return the configured device grouping mode for *entry* (flat default)."""
    options = getattr(entry, "options", None)
    data = getattr(entry, "data", None)
    options_map = options if isinstance(options, Mapping) else {}
    data_map = data if isinstance(data, Mapping) else {}
    raw = options_map.get(CONF_DEVICE_GROUPING, data_map.get(CONF_DEVICE_GROUPING, DEFAULT_DEVICE_GROUPING))
    mode = str(raw or "").strip().lower()
    if mode in DEVICE_GROUPING_MODES:
        return mode
    return DEFAULT_DEVICE_GROUPING


def _menu_device_display_name(descriptor: dict[str, Any]) -> str:
    """Localized child-device name from parent menu group title / leaf fallback."""
    group_title = str(descriptor.get("menu_group_title") or "").strip()
    if group_title:
        return group_title
    title = str(descriptor.get("menu_title") or "").strip()
    if title:
        return title
    panel_path = str(descriptor.get("panel_path") or "").strip()
    if panel_path:
        # Prefer parent (first) segment for device naming when group title is absent.
        root = panel_path.split("/", 1)[0].strip()
        if root:
            return root
        leaf = panel_path.rsplit("/", 1)[-1].strip()
        if leaf:
            return leaf
        return panel_path
    menu_key = str(descriptor.get("menu_key") or "").strip()
    return menu_key or "menu"


def _display_name_panel_prefix(descriptor: dict[str, Any]) -> str:
    """Return a meaningful panel prefix for entity display names.

    Prefers bootstrap ``menu_title`` (leaf segment). Falls back to the leaf of
    ``panel_path``. Treats empty or slash-only paths as absent so names never
    become a leading dash plus label.
    """
    title = str(descriptor.get("menu_title") or "").strip().strip("/")
    if title and title not in {".", ".."}:
        return title
    panel_path = str(descriptor.get("panel_path") or "").strip().strip("/")
    if not panel_path or panel_path in {".", ".."}:
        return ""
    leaf = panel_path.rsplit("/", 1)[-1].strip()
    if leaf and leaf not in {".", ".."}:
        return leaf
    return ""


def _address_from_value_selector(entry: Mapping[str, Any]) -> str | None:
    """Build ``P<n>.<chan><idx>`` from an SPA value-path address selector."""
    group = entry.get("group")
    number = entry.get("number")
    use = entry.get("use")
    if not isinstance(group, str) or not group.strip():
        return None
    if not isinstance(number, int):
        return None
    if not isinstance(use, str) or not use.strip():
        return None
    return f"{group.strip()}.{use.strip()[0]}{number}"


def _is_address_selector_entry(entry: Any) -> bool:
    """Return whether *entry* is a ``{group, number, use[, convert, times]}`` selector."""
    if not isinstance(entry, Mapping):
        return False
    group = entry.get("group")
    number = entry.get("number")
    use = entry.get("use")
    return isinstance(group, str) and bool(group) and isinstance(number, int) and isinstance(use, str) and bool(use)


def _address_selectors_need_compose(entries: list[Any]) -> bool:
    """Return whether address selectors need multi-register composition.

    Plain single ``{group, number, use}`` paths must not call compose: older
    ``py-bragerone`` builds coerce words with ``int()`` and truncate half-degree
    floats (``40.5`` → ``40``). Compose only for multi-selector lists or
    selectors that carry ``convert`` / a non-default ``times``.
    """
    selectors = [entry for entry in entries if _is_address_selector_entry(entry)]
    if len(selectors) >= 2:
        return True
    if len(selectors) != 1:
        return False
    entry = selectors[0]
    if entry.get("convert"):
        return True
    times = entry.get("times")
    return isinstance(times, (int, float)) and not isinstance(times, bool) and float(times) != 1.0


def _mapping_value_selector_entries(mapping: Mapping[str, Any]) -> list[Any] | None:
    """Return SPA address-selector value paths from a cached descriptor mapping."""
    for key in ("paths", "raw"):
        container = mapping.get(key)
        if not isinstance(container, Mapping):
            continue
        candidate = container.get("value")
        if not isinstance(candidate, list) or not candidate:
            continue
        if any(
            isinstance(entry, Mapping) and any(rule in entry for rule in ("if", "elseif", "then", "else")) for entry in candidate
        ):
            continue
        if any(_is_address_selector_entry(entry) for entry in candidate):
            return candidate
    return None


def descriptor_refresh_keys(descriptor: dict[str, Any]) -> set[str]:
    """Return address keys that should trigger entity refresh for a descriptor."""
    keys: set[str] = set()

    pool = descriptor.get("pool")
    chan = descriptor.get("chan")
    idx = descriptor.get("idx")
    if isinstance(pool, str) and isinstance(chan, str) and isinstance(idx, int):
        keys.add(f"{pool}.{chan}{idx}")

    mapping = descriptor.get("mapping")
    if isinstance(mapping, dict):
        inputs = mapping.get("inputs")
        if isinstance(inputs, list):
            for candidate in inputs:
                if not isinstance(candidate, dict):
                    continue
                address = candidate.get("address")
                if isinstance(address, str) and address.strip():
                    keys.add(address.strip())

        channels = mapping.get("channels")
        if isinstance(channels, dict):
            value_channels = channels.get("value")
            if isinstance(value_channels, list):
                for candidate in value_channels:
                    if not isinstance(candidate, dict):
                        continue
                    address = candidate.get("address") or candidate.get("channel")
                    if isinstance(address, str) and address.strip():
                        keys.add(address.strip())

        paths = mapping.get("paths")
        if isinstance(paths, dict):
            value_paths = paths.get("value")
            if isinstance(value_paths, list):
                for candidate in value_paths:
                    if not isinstance(candidate, dict):
                        continue
                    address = _address_from_value_selector(candidate)
                    if address is not None:
                        keys.add(address)

    route_deps = descriptor.get(CONF_ROUTE_VISIBILITY_DEPS)
    if isinstance(route_deps, list):
        for dep in route_deps:
            if isinstance(dep, str) and dep.strip():
                keys.add(dep.strip())

    return keys


def attach_route_visibility_listener(
    runtime: BragerRuntime,
    *,
    devid: str,
    descriptor: Mapping[str, Any],
    schedule_update: Callable[[], None],
) -> Callable[[], None] | None:
    """Subscribe to SPA route visibility flips for one UI-route entity (#192)."""
    if not bool(descriptor.get(CONF_UI_ROUTE_SYMBOL)):
        return None
    symbol = str(descriptor.get("symbol") or "").strip()
    if not symbol:
        return None

    def _on_route_visibility(changed_devid: str, changed_symbol: str, _visible: bool) -> None:
        if changed_devid != devid or changed_symbol != symbol:
            return
        schedule_update()

    return runtime.add_route_visibility_listener(_on_route_visibility)


def store_value_for_address(store: ParamStore, address: str) -> Any | None:
    """Read one value from ParamStore using ``P<n>.<chan><idx>`` address syntax."""
    try:
        pool, rest = address.split(".", 1)
        chan = rest[0]
        idx = int(rest[1:])
    except Exception:
        return None

    family = store.get_family(pool, idx)
    if family is None:
        return None
    return family.get(chan)


def descriptor_current_raw_value(store: ParamStore, descriptor: dict[str, Any]) -> Any | None:
    """Return current raw/display value for descriptor from ParamStore.

    Prefer SPA multi-register composition (``convert`` + ``times``) via
    :meth:`ParamResolver.compose_mapping_register_value` when the mapping carries
    multi-register / converted address-selector value paths (#327 /
    ha-bragerone#214). Plain single ``{group, number, use}`` selectors fall through
    to a direct store read so half-degree floats are preserved. Fall back to
    direct ``pool/chan/idx``, then the first mapping input address.
    """
    from pybragerone.models.param_resolver import ParamResolver

    mapping = descriptor.get("mapping")
    compose = getattr(ParamResolver, "compose_mapping_register_value", None)
    if callable(compose) and isinstance(mapping, dict):
        entries = _mapping_value_selector_entries(mapping)
        if entries is not None and _address_selectors_need_compose(entries):
            composed = compose(store, mapping)
            if composed is not None:
                return composed

    pool = descriptor.get("pool")
    chan = descriptor.get("chan")
    idx = descriptor.get("idx")
    if isinstance(pool, str) and isinstance(chan, str) and isinstance(idx, int):
        direct = store_value_for_address(store, f"{pool}.{chan}{idx}")
        if direct is not None:
            return direct

    if not isinstance(mapping, dict):
        return None
    inputs = mapping.get("inputs")
    if not isinstance(inputs, list):
        return None

    for candidate in inputs:
        if not isinstance(candidate, dict):
            continue
        address = candidate.get("address")
        if not isinstance(address, str) or not address.strip():
            continue
        value = store_value_for_address(store, address.strip())
        if value is not None:
            return value
    return None


def get_runtime_and_descriptors(
    hass: Any,
    entry: ConfigEntry,
    *,
    platform: str,
) -> tuple[BragerRuntime, list[dict[str, Any]]] | None:
    """Return runtime and descriptors filtered for a specific platform."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    runtime = entry_data.get(DATA_RUNTIME)
    descriptors = entry_data.get(CONF_ENTITY_DESCRIPTORS, [])
    if not isinstance(runtime, BragerRuntime) or not isinstance(descriptors, list):
        return None

    filtered = [
        descriptor
        for descriptor in descriptors
        if isinstance(descriptor, dict) and str(descriptor.get(CONF_PLATFORM, "sensor")) == platform
    ]
    return runtime, filtered


def module_parent_device_info(
    *,
    devid: str,
    domain: str,
    modules_meta: Mapping[str, Any] | None = None,
    sample_descriptor: Mapping[str, Any] | None = None,
) -> DeviceInfo:
    """Build flat module ``DeviceInfo`` for ``via_device`` parents."""
    meta = modules_meta.get(devid, {}) if isinstance(modules_meta, Mapping) else {}
    if not isinstance(meta, dict):
        meta = {}
    desc = sample_descriptor if isinstance(sample_descriptor, Mapping) else {}
    module_name = str(meta.get("name") or desc.get("module_name") or devid)
    module_model = str(meta.get("title") or desc.get("module_title") or "Brager module")
    module_version = str(meta.get("version") or desc.get("module_version") or "")
    return DeviceInfo(
        identifiers={(domain, devid)},
        manufacturer="BragerOne",
        name=module_name,
        model=module_model,
        sw_version=module_version or None,
    )


async def async_register_module_parent_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    descriptors: Iterable[Any],
    modules_meta: Mapping[str, Any] | None = None,
) -> None:
    """Pre-register internet-module devices before menu child ``via_device`` links (#203)."""
    if device_grouping_mode(entry) != DEVICE_GROUPING_BY_MENU:
        return

    sample_by_devid: dict[str, dict[str, Any]] = {}
    for raw in descriptors:
        if not isinstance(raw, dict):
            continue
        devid = str(raw.get("devid") or "").strip()
        if devid:
            sample_by_devid.setdefault(devid, raw)

    modules_raw = entry.options.get(CONF_MODULES, entry.data.get(CONF_MODULES, []))
    if isinstance(modules_raw, list):
        for raw_devid in modules_raw:
            devid = str(raw_devid).strip()
            if devid:
                sample_by_devid.setdefault(devid, {})

    if isinstance(modules_meta, Mapping):
        for raw_devid in modules_meta:
            devid = str(raw_devid).strip()
            if devid:
                sample_by_devid.setdefault(devid, sample_by_devid.get(devid, {}))

    if not sample_by_devid:
        return

    registry = dr.async_get(hass)
    for devid, sample in sorted(sample_by_devid.items()):
        info = module_parent_device_info(
            devid=devid,
            domain=DOMAIN,
            modules_meta=modules_meta,
            sample_descriptor=sample,
        )
        identifiers = info.get("identifiers")
        if not isinstance(identifiers, set):
            continue
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers=identifiers,
            manufacturer=str(info.get("manufacturer") or "BragerOne"),
            name=str(info.get("name") or devid),
            model=str(info.get("model") or "Brager module"),
            sw_version=info.get("sw_version"),
        )


async def async_remove_legacy_connection_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    devids: Iterable[str],
) -> None:
    """Remove empty legacy per-connection child devices after connectivity moved to parent."""
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    for raw_devid in devids:
        devid = str(raw_devid or "").strip()
        if not devid:
            continue
        legacy_identifiers = {(DOMAIN, f"{devid}:{CONNECTION_MENU_KEY}")}
        device = device_registry.async_get_device(identifiers=legacy_identifiers)
        if device is None:
            continue
        entities = er.async_entries_for_device(
            entity_registry,
            device.id,
            include_disabled_entities=True,
        )
        if entities:
            continue
        device_registry.async_remove_device(device.id)


def device_info_from_descriptor(
    descriptor: dict[str, Any],
    *,
    domain: str,
    grouping: str = DEFAULT_DEVICE_GROUPING,
) -> DeviceInfo:
    """Build DeviceInfo object from cached descriptor fields.

    Flat mode (default) keeps one device per internet module ``devid``.
    Group-by-menu mode attaches entities with a stable ``menu_key`` to a child
    device ``{devid}:{menu_key}`` linked via ``via_device`` to the module.
    Entities without a resolvable ``menu_key`` stay on the parent module device.
    """
    devid = str(descriptor.get("devid") or "")
    module_name = str(descriptor.get("module_name") or devid)
    module_version = str(descriptor.get("module_version") or "")
    module_model = str(descriptor.get("module_title") or "Brager module")
    mode = str(grouping or "").strip().lower()
    menu_key = str(descriptor.get("menu_key") or "").strip()
    if mode == DEVICE_GROUPING_BY_MENU and menu_key:
        return DeviceInfo(
            identifiers={(domain, f"{devid}:{menu_key}")},
            manufacturer="BragerOne",
            name=_menu_device_display_name(descriptor),
            model=module_model,
            sw_version=module_version or None,
            via_device=(domain, devid),
        )
    return DeviceInfo(
        identifiers={(domain, devid)},
        manufacturer="BragerOne",
        name=module_name,
        model=module_model,
        sw_version=module_version or None,
    )


def module_is_reachable(runtime: BragerRuntime, devid: str) -> bool:
    """Return whether entities for *devid* should be treated as reachable.

    Unknown connectivity (``None``) keeps previous value-based availability so
    startups before the first REST poll do not blank the UI.
    """
    online = runtime.module_online(devid)
    if online is None:
        return True
    return online


def entity_is_available(
    runtime: BragerRuntime,
    *,
    devid: str,
    has_value: bool,
    descriptor: Mapping[str, Any] | None = None,
    symbol: str | None = None,
) -> bool:
    """Combine value presence, module connectivity, and SPA route visibility (#192)."""
    symbol_name = symbol
    if descriptor is not None:
        if bool(descriptor.get(CONF_UI_ROUTE_SYMBOL)):
            symbol_name = str(descriptor.get("symbol") or symbol_name or "")
            if symbol_name and not runtime.route_visible_for_symbol(devid, symbol_name):
                return False
    elif symbol_name and not runtime.route_visible_for_symbol(devid, symbol_name):
        return False
    return bool(has_value) and module_is_reachable(runtime, devid)


def descriptor_options(descriptor: dict[str, Any]) -> list[str]:
    """Return select options from descriptor."""
    options = descriptor.get(CONF_OPTIONS, [])
    if not isinstance(options, list):
        return []
    return [str(option) for option in options if str(option).strip()]


def descriptor_enum_map(descriptor: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Return label-to-raw enum mapping from descriptor."""
    enum_map = descriptor.get(CONF_ENUM_MAP, {})
    if not isinstance(enum_map, dict):
        return {}
    out: dict[str, str | int | float | bool] = {}
    for key, value in enum_map.items():
        if isinstance(value, bool | int | float | str):
            out[str(key)] = value
    return out


def descriptor_raw_to_label(descriptor: dict[str, Any]) -> dict[str, str]:
    """Return raw-to-label enum mapping from descriptor."""
    raw_to_label = descriptor.get(CONF_RAW_TO_LABEL, {})
    if not isinstance(raw_to_label, dict):
        return {}
    return {str(key): str(value) for key, value in raw_to_label.items()}


def descriptor_enabled_by_default(descriptor: Mapping[str, Any]) -> bool:
    """Return whether an entity should be enabled by default (#212).

    Every permission-gated symbol still becomes an entity; only entities outside
    the everyday web UI (or not SPA-visible) start disabled in the entity registry.
    """
    raw = descriptor.get(CONF_ENABLED_BY_DEFAULT, True)
    return bool(raw)


def descriptor_display_name(
    descriptor: dict[str, Any],
    *,
    grouping: str = DEFAULT_DEVICE_GROUPING,
) -> str:
    """Build entity display label as ``LeafPanel - Label`` when useful.

    Uses the menu leaf (``menu_title`` / last ``panel_path`` segment), not the
    full parent-to-child chain — the parent segment belongs on the HA device once
    group-by-menu uses parent menus (#176). Empty or slash-only paths yield the
    bare label (no leading dash).

    In group-by-menu mode, when the leaf prefix equals ``menu_group_title`` (the
    child device name), return the bare label so HA does not show a redundant
    ``Device - …`` name that renders as a leading dash under that device.
    """
    label = str(descriptor.get("label") or descriptor.get("symbol") or "").strip()
    prefix = _display_name_panel_prefix(descriptor)
    if not prefix:
        return label
    mode = str(grouping or "").strip().lower()
    if mode == DEVICE_GROUPING_BY_MENU:
        group = str(descriptor.get("menu_group_title") or "").strip()
        if group and prefix == group:
            return label
    return f"{prefix} - {label}"


def descriptor_suggested_object_id(descriptor: dict[str, Any]) -> str:
    """Build a stable suggested object id from ``devid`` + ``symbol``.

    Uses the internet-module id (not the localizable module display name) so
    new entity_ids survive language/bundle/bootstrap refreshes. Existing
    registry entity_ids are not rewritten by Home Assistant on upgrade.
    """
    devid = str(descriptor.get("devid") or "device")
    symbol = str(descriptor.get("symbol") or "entity")
    return slugify(f"{devid}_{symbol}")


def record_platform_entity_stats(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    platform: str,
    descriptor_count: int,
    created_count: int,
    supplemental_count: int = 0,
) -> None:
    """Record per-platform entity setup statistics for diagnostics."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    stats_raw = entry_data.get(DATA_ENTITY_STATS)
    stats = stats_raw if isinstance(stats_raw, dict) else {}
    stats[platform] = {
        "descriptor_count": int(descriptor_count),
        "created_count": int(created_count),
        "supplemental_count": int(supplemental_count),
    }
    entry_data[DATA_ENTITY_STATS] = stats
