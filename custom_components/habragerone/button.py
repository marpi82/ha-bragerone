"""Button platform for BragerOne action-like symbols."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity_common import (
    attach_route_visibility_listener,
    descriptor_display_name,
    descriptor_enabled_by_default,
    descriptor_suggested_object_id,
    device_grouping_mode,
    device_info_from_descriptor,
    entity_is_available,
    get_runtime_and_descriptors,
    record_platform_entity_stats,
)
from .runtime import BragerRuntime


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up BragerOne button entities."""
    runtime_and_descriptors = get_runtime_and_descriptors(hass, entry, platform="button")
    if runtime_and_descriptors is None:
        return
    runtime, descriptors = runtime_and_descriptors

    entities = [BragerActionButton(entry=entry, runtime=runtime, descriptor=descriptor) for descriptor in descriptors]
    record_platform_entity_stats(
        hass,
        entry,
        platform="button",
        descriptor_count=len(descriptors),
        created_count=len(entities),
    )
    async_add_entities(entities)


class BragerActionButton(ButtonEntity):
    """Button entity for command-only BragerOne symbols."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, *, entry: ConfigEntry, runtime: BragerRuntime, descriptor: dict[str, Any]) -> None:
        """Initialize action button from one cached descriptor."""
        self._entry = entry
        self._runtime = runtime
        self._descriptor = descriptor
        self._symbol = str(descriptor.get("symbol") or "")
        self._devid = str(descriptor.get("devid") or "")

        label = descriptor_display_name(descriptor, grouping=device_grouping_mode(entry))
        self._attr_name = label
        self._attr_suggested_object_id = descriptor_suggested_object_id(descriptor)
        self._attr_unique_id = f"{entry.entry_id}_{self._devid}_{self._symbol}_button".lower().replace(" ", "_")
        self._attr_entity_registry_enabled_default = descriptor_enabled_by_default(descriptor)
        self._attr_available = entity_is_available(
            runtime,
            devid=self._devid,
            has_value=True,
            descriptor=descriptor,
        )
        self._unsubscribe_connectivity: Any = None
        self._unsubscribe_route_visibility: Any = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata for HA device registry."""
        return device_info_from_descriptor(
            self._descriptor,
            domain=DOMAIN,
            grouping=device_grouping_mode(self._entry),
            hass=self.hass,
            config_entry_id=self._entry.entry_id,
        )

    async def async_added_to_hass(self) -> None:
        """Attach connectivity and route-visibility listeners when entity is added."""
        self._unsubscribe_connectivity = self._runtime.add_connectivity_listener(self._on_connectivity)
        self._unsubscribe_route_visibility = attach_route_visibility_listener(
            self._runtime,
            devid=self._devid,
            descriptor=self._descriptor,
            schedule_update=lambda: self.async_schedule_update_ha_state(True),
        )
        self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        """Detach listeners before entity removal."""
        if callable(self._unsubscribe_connectivity):
            self._unsubscribe_connectivity()
            self._unsubscribe_connectivity = None
        if callable(self._unsubscribe_route_visibility):
            self._unsubscribe_route_visibility()
            self._unsubscribe_route_visibility = None

    async def async_update(self) -> None:
        """Refresh availability from connectivity and SPA route visibility."""
        self._attr_available = entity_is_available(
            self._runtime,
            devid=self._devid,
            has_value=True,
            descriptor=self._descriptor,
        )

    def _on_connectivity(self, devid: str, _online: bool, online_changed: bool = True) -> None:
        if devid != self._devid or not online_changed:
            return
        self.async_schedule_update_ha_state(True)

    async def async_press(self) -> None:
        """Dispatch action command to backend."""
        mapping_raw = self._descriptor.get("mapping")
        mapping = mapping_raw if isinstance(mapping_raw, dict) else {}
        rules_raw = mapping.get("command_rules")
        command_rules = rules_raw if isinstance(rules_raw, list) else []
        rule = next((rule for rule in command_rules if isinstance(rule, dict)), {})
        value = rule.get("value", True)
        if not isinstance(value, bool | int | float | str):
            value = True
        await self._runtime.async_write(descriptor=self._descriptor, input_display_value=value)
