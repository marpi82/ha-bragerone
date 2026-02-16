"""Button platform for BragerOne action-like symbols."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity_common import device_info_from_descriptor, get_runtime_and_descriptors, record_platform_entity_stats
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

    def __init__(self, *, entry: ConfigEntry, runtime: BragerRuntime, descriptor: dict[str, Any]) -> None:
        """Initialize action button from one cached descriptor."""
        self._runtime = runtime
        self._descriptor = descriptor
        self._symbol = str(descriptor.get("symbol") or "")
        self._devid = str(descriptor.get("devid") or "")

        label = str(descriptor.get("label") or self._symbol)
        self._attr_name = label
        self._attr_unique_id = f"{entry.entry_id}_{self._devid}_{self._symbol}_button".lower().replace(" ", "_")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata for HA device registry."""
        return device_info_from_descriptor(self._descriptor, domain=DOMAIN)

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
