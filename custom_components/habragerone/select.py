"""Select platform for writable enum-like BragerOne symbols."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pybragerone.models.events import ParamUpdate

from .const import DOMAIN
from .entity_common import (
    descriptor_display_name,
    descriptor_enum_map,
    descriptor_options,
    descriptor_raw_to_label,
    descriptor_refresh_keys,
    descriptor_suggested_object_id,
    device_info_from_descriptor,
    get_runtime_and_descriptors,
    record_platform_entity_stats,
)
from .runtime import BragerRuntime


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up BragerOne select entities."""
    runtime_and_descriptors = get_runtime_and_descriptors(hass, entry, platform="select")
    if runtime_and_descriptors is None:
        return
    runtime, descriptors = runtime_and_descriptors

    entities = [BragerSymbolSelect(entry=entry, runtime=runtime, descriptor=descriptor) for descriptor in descriptors]
    record_platform_entity_stats(
        hass,
        entry,
        platform="select",
        descriptor_count=len(descriptors),
        created_count=len(entities),
    )
    async_add_entities(entities)


class BragerSymbolSelect(SelectEntity):
    """Select entity for enum-like writable BragerOne symbols."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, *, entry: ConfigEntry, runtime: BragerRuntime, descriptor: dict[str, Any]) -> None:
        """Initialize select entity from one cached descriptor."""
        self._entry = entry
        self._runtime = runtime
        self._descriptor = descriptor
        self._symbol = str(descriptor.get("symbol") or "")
        self._devid = str(descriptor.get("devid") or "")

        label = descriptor_display_name(descriptor)
        self._attr_name = label
        self._attr_suggested_object_id = descriptor_suggested_object_id(descriptor)
        self._attr_unique_id = f"{entry.entry_id}_{self._devid}_{self._symbol}_select".lower().replace(" ", "_")
        self._enum_map = descriptor_enum_map(descriptor)
        self._raw_to_label = descriptor_raw_to_label(descriptor)
        self._attr_options = descriptor_options(descriptor)
        self._attr_current_option = self._attr_options[0] if self._attr_options else None
        self._attr_available = True
        self._refresh_keys = descriptor_refresh_keys(descriptor)
        self._unsubscribe_listener: Any = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata for HA device registry."""
        return device_info_from_descriptor(self._descriptor, domain=DOMAIN)

    async def async_added_to_hass(self) -> None:
        """Attach runtime listener when entity is added."""
        self._unsubscribe_listener = self._runtime.add_listener(self._on_runtime_update)
        await self.async_update()

    async def async_will_remove_from_hass(self) -> None:
        """Detach runtime listener before entity removal."""
        if callable(self._unsubscribe_listener):
            self._unsubscribe_listener()
            self._unsubscribe_listener = None

    async def async_update(self) -> None:
        """Refresh current option from resolved symbol value."""
        try:
            resolved = await self._runtime.resolver.resolve_value(self._symbol)
        except Exception:
            self._attr_available = False
            return

        self._attr_available = True
        candidate = resolved.value_label if isinstance(resolved.value_label, str) else self._raw_to_label.get(str(resolved.value))
        if candidate is None:
            candidate = str(resolved.value)
        if candidate in self._attr_options:
            self._attr_current_option = candidate

    async def async_select_option(self, option: str) -> None:
        """Write selected enum option to backend."""
        await self._runtime.async_write(
            descriptor=self._descriptor,
            input_display_value=option,
            enum_mapping=self._enum_map,
        )
        self._attr_current_option = option

    def _on_runtime_update(self, _update: ParamUpdate) -> None:
        update_key = f"{_update.pool}.{_update.chan}{_update.idx}"
        if self._refresh_keys and update_key not in self._refresh_keys:
            return
        self.async_schedule_update_ha_state(True)
