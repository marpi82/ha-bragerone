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
    descriptor_display_name,
    descriptor_suggested_object_id,
    device_info_from_descriptor,
    get_runtime_and_descriptors,
    record_platform_entity_stats,
)
from .runtime import BragerRuntime


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
    _attr_should_poll = True

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
        self._attr_name = label
        self._attr_suggested_object_id = descriptor_suggested_object_id(descriptor)
        self._attr_unique_id = f"{entry.entry_id}_{devid}_{symbol}".lower().replace(" ", "_")
        self._attr_native_unit_of_measurement = self._normalize_unit(descriptor.get("unit"))
        self._attr_available = True

        self._unsubscribe_listener: Any = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to push updates when entity is added to HA."""
        self._unsubscribe_listener = self._runtime.add_listener(self._on_runtime_update)

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
        """Fetch latest resolved value from ParamResolver."""
        try:
            resolved = await self._runtime.resolver.resolve_value(self._symbol)
        except Exception:
            self._attr_available = False
            return

        self._attr_available = True
        self._attr_native_value = resolved.value_label or resolved.value
        unit = self._normalize_unit(resolved.unit)
        if isinstance(unit, str):
            self._attr_native_unit_of_measurement = unit

    def _on_runtime_update(self, _update: ParamUpdate) -> None:
        self.async_schedule_update_ha_state(True)

    @staticmethod
    def _normalize_unit(value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in ("en", "pl"):
                val = value.get(key)
                if isinstance(val, str) and val.strip():
                    return val
        return None
