"""Switch platform for writable BragerOne symbols."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pybragerone.models.events import ParamUpdate

from .const import DOMAIN
from .entity_common import device_info_from_descriptor, get_runtime_and_descriptors, record_platform_entity_stats
from .runtime import BragerRuntime


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up BragerOne switch entities."""
    runtime_and_descriptors = get_runtime_and_descriptors(hass, entry, platform="switch")
    if runtime_and_descriptors is None:
        return
    runtime, descriptors = runtime_and_descriptors

    entities = [BragerSymbolSwitch(entry=entry, runtime=runtime, descriptor=descriptor) for descriptor in descriptors]
    record_platform_entity_stats(
        hass,
        entry,
        platform="switch",
        descriptor_count=len(descriptors),
        created_count=len(entities),
    )
    async_add_entities(entities)


class BragerSymbolSwitch(SwitchEntity):
    """Switch entity bound to one BragerOne writable symbol."""

    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(self, *, entry: ConfigEntry, runtime: BragerRuntime, descriptor: dict[str, Any]) -> None:
        """Initialize switch entity from one cached descriptor."""
        self._entry = entry
        self._runtime = runtime
        self._descriptor = descriptor
        self._symbol = str(descriptor.get("symbol") or "")
        self._devid = str(descriptor.get("devid") or "")

        label = str(descriptor.get("label") or self._symbol)
        self._attr_name = label
        self._attr_unique_id = f"{entry.entry_id}_{self._devid}_{self._symbol}_switch".lower().replace(" ", "_")
        self._attr_is_on = False
        self._attr_available = True
        self._unsubscribe_listener: Any = None

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
        """Refresh switch state from resolved symbol value."""
        try:
            resolved = await self._runtime.resolver.resolve_value(self._symbol)
        except Exception:
            self._attr_available = False
            return

        self._attr_available = True
        self._attr_is_on = _coerce_bool(resolved.value_label if resolved.value_label is not None else resolved.value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn switch on by dispatching a write command."""
        await self._runtime.async_write(descriptor=self._descriptor, input_display_value=True)
        self._attr_is_on = True

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn switch off by dispatching a write command."""
        await self._runtime.async_write(descriptor=self._descriptor, input_display_value=False)
        self._attr_is_on = False

    def _on_runtime_update(self, _update: ParamUpdate) -> None:
        self.async_schedule_update_ha_state(True)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    if isinstance(value, str):
        norm = value.strip().casefold()
        if norm in {"1", "true", "on", "enabled", "yes"}:
            return True
        if norm in {"0", "false", "off", "disabled", "no"}:
            return False
    return False
