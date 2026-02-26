"""Shared helpers for BragerOne entity platforms."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import slugify

from .const import (
    CONF_ENTITY_DESCRIPTORS,
    CONF_ENUM_MAP,
    CONF_OPTIONS,
    CONF_PLATFORM,
    CONF_RAW_TO_LABEL,
    DATA_ENTITY_STATS,
    DATA_RUNTIME,
    DOMAIN,
)
from .runtime import BragerRuntime


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


def device_info_from_descriptor(descriptor: dict[str, Any], *, domain: str) -> DeviceInfo:
    """Build DeviceInfo object from cached descriptor fields."""
    devid = str(descriptor.get("devid") or "")
    module_name = str(descriptor.get("module_name") or devid)
    module_version = str(descriptor.get("module_version") or "")
    return DeviceInfo(
        identifiers={(domain, devid)},
        manufacturer="BragerOne",
        name=module_name,
        model=str(descriptor.get("module_title") or "Brager module"),
        sw_version=module_version or None,
    )


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
    """Build entity display label as ``Menu/Submenu - Label`` when available."""
    label = str(descriptor.get("label") or descriptor.get("symbol") or "")
    panel_path = str(descriptor.get("panel_path") or "").strip()
    if panel_path:
        return f"{panel_path} - {label}"
    return label


def descriptor_suggested_object_id(descriptor: dict[str, Any]) -> str:
    """Build stable object id to avoid duplicate suffixes for repeated labels."""
    module_name = str(descriptor.get("module_name") or descriptor.get("devid") or "device")
    symbol = str(descriptor.get("symbol") or "entity")
    return slugify(f"{module_name}_{symbol}")


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
