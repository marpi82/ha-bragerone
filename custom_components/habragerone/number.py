"""Number platform for writable numeric BragerOne symbols."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
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
    """Set up BragerOne number entities."""
    runtime_and_descriptors = get_runtime_and_descriptors(hass, entry, platform="number")
    if runtime_and_descriptors is None:
        return
    runtime, descriptors = runtime_and_descriptors

    entities = [BragerSymbolNumber(entry=entry, runtime=runtime, descriptor=descriptor) for descriptor in descriptors]
    record_platform_entity_stats(
        hass,
        entry,
        platform="number",
        descriptor_count=len(descriptors),
        created_count=len(entities),
    )
    async_add_entities(entities)


class BragerSymbolNumber(NumberEntity):
    """Number entity bound to one BragerOne writable numeric symbol."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(self, *, entry: ConfigEntry, runtime: BragerRuntime, descriptor: dict[str, Any]) -> None:
        """Initialize number entity from one cached descriptor."""
        self._entry = entry
        self._runtime = runtime
        self._descriptor = descriptor
        self._symbol = str(descriptor.get("symbol") or "")
        self._devid = str(descriptor.get("devid") or "")

        label = descriptor_display_name(descriptor)
        self._attr_name = label
        self._attr_suggested_object_id = descriptor_suggested_object_id(descriptor)
        self._attr_unique_id = f"{entry.entry_id}_{self._devid}_{self._symbol}_number".lower().replace(" ", "_")
        self._attr_native_value = None
        self._attr_available = True
        self._unsubscribe_listener: Any = None

        min_value = descriptor.get("min")
        max_value = descriptor.get("max")
        if isinstance(min_value, int | float):
            self._attr_native_min_value = float(min_value)
        if isinstance(max_value, int | float):
            self._attr_native_max_value = float(max_value)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata for HA device registry."""
        return device_info_from_descriptor(self._descriptor, domain=DOMAIN)

    async def async_added_to_hass(self) -> None:
        """Attach runtime listener when entity is added."""
        self._unsubscribe_listener = self._runtime.add_listener(self._on_runtime_update)

    async def async_will_remove_from_hass(self) -> None:
        """Detach runtime listener before entity removal."""
        if callable(self._unsubscribe_listener):
            self._unsubscribe_listener()
            self._unsubscribe_listener = None

    async def async_update(self) -> None:
        """Refresh numeric value from resolved symbol value."""
        try:
            resolved = await self._runtime.resolver.resolve_value(self._symbol)
        except Exception:
            self._attr_available = False
            return

        self._attr_available = True
        value = resolved.value
        if isinstance(value, int | float) and not isinstance(value, bool):
            self._attr_native_value = float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Write a new numeric value to backend."""
        await self._runtime.async_write(descriptor=self._descriptor, input_display_value=value)
        self._attr_native_value = value

    def _on_runtime_update(self, _update: ParamUpdate) -> None:
        self.async_schedule_update_ha_state(True)
