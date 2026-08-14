"""Sensor platform for BragerOne entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pybragerone.models.events import ParamUpdate

from .const import DOMAIN
from .entity_common import (
    descriptor_current_raw_value,
    descriptor_display_name,
    descriptor_raw_to_label,
    descriptor_refresh_keys,
    descriptor_suggested_object_id,
    device_info_from_descriptor,
    get_runtime_and_descriptors,
    record_platform_entity_stats,
)
from .runtime import BragerRuntime
from .status_rules import resolve_rule_display_value


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up BragerOne sensor entities from cached descriptors."""
    runtime_and_descriptors = get_runtime_and_descriptors(hass, entry, platform="sensor")
    if runtime_and_descriptors is None:
        return
    runtime, descriptors = runtime_and_descriptors

    entities = [BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor) for descriptor in descriptors]
    record_platform_entity_stats(
        hass,
        entry,
        platform="sensor",
        descriptor_count=len(descriptors),
        created_count=len(entities),
    )
    async_add_entities(entities)


class BragerSymbolSensor(SensorEntity):
    """Generic sensor representing one BragerOne symbol."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, *, entry: ConfigEntry, runtime: BragerRuntime, descriptor: dict[str, Any]) -> None:
        """Initialize one sensor entity from a serialized descriptor."""
        self._entry = entry
        self._runtime = runtime
        self._descriptor = descriptor

        symbol = str(descriptor.get("symbol", ""))
        devid = str(descriptor.get("devid", ""))
        label = descriptor_display_name(descriptor)

        self._symbol = symbol
        self._devid = devid
        self._is_status_symbol = symbol.startswith("STATUS_")
        self._attr_name = label
        self._attr_suggested_object_id = descriptor_suggested_object_id(descriptor)
        self._attr_unique_id = f"{entry.entry_id}_{devid}_{symbol}".lower().replace(" ", "_")
        self._attr_native_unit_of_measurement = self._normalize_unit(descriptor.get("unit"))
        self._attr_available = True
        self._raw_to_label = descriptor_raw_to_label(descriptor)
        mapping = descriptor.get("mapping")
        mapping_dict = mapping if isinstance(mapping, dict) else {}
        channels = mapping_dict.get("channels")
        self._requires_resolver_value = (
            self._attr_native_unit_of_measurement is None
            and isinstance(channels, dict)
            and isinstance(channels.get("unit"), list)
            and len(channels.get("unit") or []) > 0
        )
        self._refresh_keys = descriptor_refresh_keys(descriptor)

        self._unsubscribe_listener: Any = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to push updates when entity is added to HA."""
        self._unsubscribe_listener = self._runtime.add_listener(self._on_runtime_update)
        self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        """Detach runtime listener when entity is removed from HA."""
        if callable(self._unsubscribe_listener):
            self._unsubscribe_listener()
            self._unsubscribe_listener = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        return device_info_from_descriptor(self._descriptor, domain=DOMAIN)

    async def async_update(self) -> None:
        """Fetch latest value from ParamStore (no heavy resolver call)."""
        raw_value = descriptor_current_raw_value(self._runtime.store, self._descriptor)
        if raw_value is None:
            self._attr_available = False
            return

        self._attr_available = True
        if self._requires_resolver_value:
            resolved_value, resolved_unit = await self._runtime.async_resolve_symbol_with_unit(self._symbol)
            normalized_dynamic_unit = self._normalize_unit(resolved_unit)
            if normalized_dynamic_unit:
                self._attr_native_unit_of_measurement = normalized_dynamic_unit
            if resolved_value is not None:
                self._attr_native_value = _normalize_text_state(resolved_value)
                return
        mapped_by_unit = self._raw_to_label.get(str(raw_value))
        if mapped_by_unit is not None:
            self._attr_native_value = _normalize_text_state(mapped_by_unit)
            return
        resolved_status = await self._runtime.async_resolve_status_label(self._symbol) if self._is_status_symbol else None
        if resolved_status is not None:
            self._attr_native_value = _normalize_text_state(resolved_status)
            return
        mapped_value = resolve_rule_display_value(
            descriptor=self._descriptor,
            flat_values=self._runtime.store.flatten(),
            default_actual=raw_value,
        )
        if mapped_value is not None:
            self._attr_native_value = _normalize_text_state(mapped_value)
            return
        self._attr_native_value = _normalize_text_state(self._raw_to_label.get(str(raw_value), raw_value))

    def _on_runtime_update(self, _update: ParamUpdate) -> None:
        update_key = f"{_update.pool}.{_update.chan}{_update.idx}"
        if self._refresh_keys and update_key not in self._refresh_keys:
            return
        self.async_schedule_update_ha_state(True)

    @staticmethod
    def _normalize_unit(value: Any) -> str | None:
        if isinstance(value, str):
            unit = value.strip()
            if not unit:
                return None
            # Reject unresolved symbolic unit tokens (e.g. "wn.9998"),
            # they are not real units of measurement and break text states.
            if "." in unit and " " not in unit:
                lowered = unit.casefold()
                if lowered.startswith(("wn.", "units.", "app.")):
                    return None
            return unit
        if isinstance(value, dict):
            for key in ("en", "pl"):
                val = value.get(key)
                if isinstance(val, str) and val.strip():
                    return val
        return None


def _normalize_text_state(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return text
    head = text[0]
    if not head.isalpha():
        return text
    # Keep unresolved ALL_CAPS enum tags (``STOP``) intact. Lowercasing only the
    # first letter produced nonsense like ``sTOP`` when unit option labels missed.
    letters = [ch for ch in text if ch.isalpha()]
    if letters and all(ch.isupper() for ch in letters):
        return text
    return f"{head.lower()}{text[1:]}"
