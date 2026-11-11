"""Datetime platform for BragerOne DATE_TIME symbols (SPA yyMMddHHmm)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from pybragerone.models.events import ParamUpdate

from .const import DOMAIN
from .date_time_codec import format_server_date_time, parse_server_date_time
from .entity_common import (
    attach_route_visibility_listener,
    attach_transport_availability_listener,
    descriptor_current_raw_value,
    descriptor_display_name,
    descriptor_enabled_by_default,
    descriptor_refresh_keys,
    descriptor_suggested_object_id,
    device_grouping_mode,
    device_info_from_descriptor,
    entity_is_available,
    get_runtime_and_descriptors,
    record_platform_entity_stats,
)
from .runtime import BragerRuntime


def _wire_to_hass_datetime(raw: Any) -> datetime | None:
    """Parse Brager wire value and attach HA local timezone (required by DateTimeEntity)."""
    parsed = parse_server_date_time(raw)
    if parsed is None:
        return None
    # Codec always returns naive wall time; HA DateTimeEntity requires tzinfo.
    return parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)


def _hass_datetime_to_wire(value: datetime) -> str | None:
    """Encode an aware HA datetime as Brager local wall-time ``yyMMddHHmm``."""
    local = dt_util.as_local(value)
    return format_server_date_time(local.replace(tzinfo=None))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up BragerOne datetime entities."""
    runtime_and_descriptors = get_runtime_and_descriptors(hass, entry, platform="datetime")
    if runtime_and_descriptors is None:
        return
    runtime, descriptors = runtime_and_descriptors

    entities = [BragerSymbolDateTime(entry=entry, runtime=runtime, descriptor=descriptor) for descriptor in descriptors]
    record_platform_entity_stats(
        hass,
        entry,
        platform="datetime",
        descriptor_count=len(descriptors),
        created_count=len(entities),
    )
    async_add_entities(entities)


class BragerSymbolDateTime(DateTimeEntity):
    """Datetime entity bound to one BragerOne DATE_TIME writable symbol."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, *, entry: ConfigEntry, runtime: BragerRuntime, descriptor: dict[str, Any]) -> None:
        """Initialize datetime entity from one cached descriptor."""
        self._entry = entry
        self._runtime = runtime
        self._descriptor = descriptor
        self._symbol = str(descriptor.get("symbol") or "")
        self._devid = str(descriptor.get("devid") or "")

        label = descriptor_display_name(descriptor, grouping=device_grouping_mode(entry))
        self._attr_name = label
        self._attr_suggested_object_id = descriptor_suggested_object_id(descriptor)
        self._attr_unique_id = f"{entry.entry_id}_{self._devid}_{self._symbol}_datetime".lower().replace(" ", "_")
        self._attr_entity_registry_enabled_default = descriptor_enabled_by_default(descriptor)
        self._attr_native_value = None
        self._attr_available = True
        self._refresh_keys = descriptor_refresh_keys(descriptor)
        self._unsubscribe_listener: Any = None
        self._unsubscribe_connectivity: Any = None
        self._unsubscribe_route_visibility: Any = None
        self._unsubscribe_transport: Any = None

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
        """Attach runtime listeners when entity is added."""
        self._unsubscribe_listener = self._runtime.add_listener(self._on_runtime_update)
        self._unsubscribe_connectivity = self._runtime.add_connectivity_listener(self._on_connectivity)
        self._unsubscribe_route_visibility = attach_route_visibility_listener(
            self._runtime,
            devid=self._devid,
            descriptor=self._descriptor,
            schedule_update=lambda: self.async_schedule_update_ha_state(True),
        )
        self._unsubscribe_transport = attach_transport_availability_listener(
            self._runtime,
            schedule_update=lambda: self.async_schedule_update_ha_state(True),
        )
        self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        """Detach runtime listeners before entity removal."""
        if callable(self._unsubscribe_listener):
            self._unsubscribe_listener()
            self._unsubscribe_listener = None
        if callable(self._unsubscribe_connectivity):
            self._unsubscribe_connectivity()
            self._unsubscribe_connectivity = None
        if callable(self._unsubscribe_route_visibility):
            self._unsubscribe_route_visibility()
            self._unsubscribe_route_visibility = None
        if callable(self._unsubscribe_transport):
            self._unsubscribe_transport()
            self._unsubscribe_transport = None

    async def async_update(self) -> None:
        """Refresh datetime value from ParamStore wire reading."""
        raw_value = descriptor_current_raw_value(self._runtime.store, self._descriptor)
        self._attr_available = entity_is_available(
            self._runtime,
            devid=self._devid,
            has_value=raw_value is not None,
            descriptor=self._descriptor,
        )
        self._attr_native_value = _wire_to_hass_datetime(raw_value)

    async def async_set_value(self, value: datetime) -> None:
        """Write a HA datetime as Brager ``yyMMddHHmm`` wire string."""
        wire = _hass_datetime_to_wire(value)
        if wire is None:
            raise HomeAssistantError(f"Invalid DATE_TIME value for '{self._symbol}': {value!r}")
        await self._runtime.async_write(descriptor=self._descriptor, input_display_value=wire)
        self._attr_native_value = _wire_to_hass_datetime(wire)

    def _on_runtime_update(self, _update: ParamUpdate) -> None:
        update_key = f"{_update.pool}.{_update.chan}{_update.idx}"
        if self._refresh_keys and update_key not in self._refresh_keys:
            return
        self.async_schedule_update_ha_state(True)

    def _on_connectivity(self, devid: str, _online: bool, online_changed: bool = True) -> None:
        if devid != self._devid or not online_changed:
            return
        self.async_schedule_update_ha_state(True)
