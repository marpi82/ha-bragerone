"""Shared helpers for BragerOne entity platforms."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import slugify
from pybragerone.models.param import ParamStore

from .const import (
    CONF_DEVICE_GROUPING,
    CONF_ENTITY_DESCRIPTORS,
    CONF_ENUM_MAP,
    CONF_OPTIONS,
    CONF_PLATFORM,
    CONF_RAW_TO_LABEL,
    DATA_ENTITY_STATS,
    DATA_RUNTIME,
    DEFAULT_DEVICE_GROUPING,
    DEVICE_GROUPING_BY_MENU,
    DEVICE_GROUPING_MODES,
    DOMAIN,
)
from .runtime import BragerRuntime


def device_grouping_mode(entry: ConfigEntry) -> str:
    """Return the configured device grouping mode for *entry* (flat default)."""
    raw = entry.options.get(CONF_DEVICE_GROUPING, entry.data.get(CONF_DEVICE_GROUPING, DEFAULT_DEVICE_GROUPING))
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

    return keys


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
    """Return current raw value for descriptor from ParamStore.

    Prefers direct ``pool/chan/idx`` mapping, then falls back to first mapping input
    address when available.
    """
    pool = descriptor.get("pool")
    chan = descriptor.get("chan")
    idx = descriptor.get("idx")
    if isinstance(pool, str) and isinstance(chan, str) and isinstance(idx, int):
        direct = store_value_for_address(store, f"{pool}.{chan}{idx}")
        if direct is not None:
            return direct

    mapping = descriptor.get("mapping")
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


def entity_is_available(runtime: BragerRuntime, *, devid: str, has_value: bool) -> bool:
    """Combine ParamStore value presence with module cloud connectivity."""
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


def descriptor_display_name(descriptor: dict[str, Any]) -> str:
    """Build entity display label as ``LeafPanel - Label`` when available.

    Uses the menu leaf (``menu_title`` / last ``panel_path`` segment), not the
    full parent-to-child chain — the parent segment belongs on the HA device once
    group-by-menu uses parent menus (#176). Empty or slash-only paths yield the
    bare label (no leading dash).
    """
    label = str(descriptor.get("label") or descriptor.get("symbol") or "").strip()
    prefix = _display_name_panel_prefix(descriptor)
    if prefix:
        return f"{prefix} - {label}"
    return label


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
) -> None:
    """Record per-platform entity setup statistics for diagnostics."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    stats_raw = entry_data.get(DATA_ENTITY_STATS)
    stats = stats_raw if isinstance(stats_raw, dict) else {}
    stats[platform] = {
        "descriptor_count": int(descriptor_count),
        "created_count": int(created_count),
    }
    entry_data[DATA_ENTITY_STATS] = stats
