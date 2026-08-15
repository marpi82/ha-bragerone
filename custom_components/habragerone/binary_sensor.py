"""Binary sensor platform for BragerOne status symbols and module connectivity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pybragerone.models.events import ParamUpdate

from .const import CONF_MODULES_META, DATA_RUNTIME, DOMAIN
from .entity_common import (
    descriptor_current_raw_value,
    descriptor_display_name,
    descriptor_refresh_keys,
    descriptor_suggested_object_id,
    device_info_from_descriptor,
    entity_is_available,
    get_runtime_and_descriptors,
    record_platform_entity_stats,
)
from .runtime import BragerRuntime
from .status_rules import resolve_rule_bool


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up BragerOne binary sensor entities."""
    runtime_and_descriptors = get_runtime_and_descriptors(hass, entry, platform="binary_sensor")
    if runtime_and_descriptors is None:
        return
    runtime, descriptors = runtime_and_descriptors

    entities: list[BinarySensorEntity] = [
        BragerStatusBinarySensor(entry=entry, runtime=runtime, descriptor=descriptor) for descriptor in descriptors
    ]

    entry_data = hass.data[DOMAIN][entry.entry_id]
    runtime_obj = entry_data.get(DATA_RUNTIME)
    modules_meta = entry.data.get(CONF_MODULES_META)
    if isinstance(runtime_obj, BragerRuntime) and isinstance(modules_meta, dict):
        for devid, meta in modules_meta.items():
            if not isinstance(devid, str) or not devid.strip():
                continue
            if not isinstance(meta, dict):
                meta = {}
            entities.append(
                BragerModuleConnectivityBinarySensor(
                    entry=entry,
                    runtime=runtime_obj,
                    devid=devid,
                    module_meta=meta,
                )
            )

    record_platform_entity_stats(
        hass,
        entry,
        platform="binary_sensor",
        descriptor_count=len(descriptors),
        created_count=len(entities),
    )
    async_add_entities(entities)


class BragerStatusBinarySensor(BinarySensorEntity):
    """Binary sensor for status-like symbols."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, *, entry: ConfigEntry, runtime: BragerRuntime, descriptor: dict[str, Any]) -> None:
        """Initialize binary sensor entity from one cached descriptor."""
        self._runtime = runtime
        self._descriptor = descriptor
        self._symbol = str(descriptor.get("symbol") or "")
        self._devid = str(descriptor.get("devid") or "")

        label = descriptor_display_name(descriptor)
        self._attr_name = label
        self._attr_suggested_object_id = descriptor_suggested_object_id(descriptor)
        self._attr_unique_id = f"{entry.entry_id}_{self._devid}_{self._symbol}_binary".lower().replace(" ", "_")
        self._attr_is_on = False
        self._attr_available = True
        self._refresh_keys = descriptor_refresh_keys(descriptor)
        self._unsubscribe_listener: Any = None
        self._unsubscribe_connectivity: Any = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata for HA device registry."""
        return device_info_from_descriptor(self._descriptor, domain=DOMAIN)

    async def async_added_to_hass(self) -> None:
        """Attach runtime listeners when entity is added."""
        self._unsubscribe_listener = self._runtime.add_listener(self._on_runtime_update)
        self._unsubscribe_connectivity = self._runtime.add_connectivity_listener(self._on_connectivity)
        self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        """Detach runtime listeners before entity removal."""
        if callable(self._unsubscribe_listener):
            self._unsubscribe_listener()
            self._unsubscribe_listener = None
        if callable(self._unsubscribe_connectivity):
            self._unsubscribe_connectivity()
            self._unsubscribe_connectivity = None

    async def async_update(self) -> None:
        """Refresh state from ParamStore value."""
        raw_value = descriptor_current_raw_value(self._runtime.store, self._descriptor)
        self._attr_available = entity_is_available(
            self._runtime,
            devid=self._devid,
            has_value=raw_value is not None,
        )
        if raw_value is None:
            return

        rule_value = resolve_rule_bool(
            descriptor=self._descriptor,
            flat_values=self._runtime.store.flatten(),
            default_actual=raw_value,
        )
        self._attr_is_on = rule_value if rule_value is not None else _to_bool(raw_value)

    def _on_runtime_update(self, _update: ParamUpdate) -> None:
        update_key = f"{_update.pool}.{_update.chan}{_update.idx}"
        if self._refresh_keys and update_key not in self._refresh_keys:
            return
        self.async_schedule_update_ha_state(True)

    def _on_connectivity(self, devid: str, _online: bool) -> None:
        if devid != self._devid:
            return
        self.async_schedule_update_ha_state(True)


class BragerModuleConnectivityBinarySensor(BinarySensorEntity):
    """Diagnostic binary sensor for module cloud connectivity."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Cloud connectivity"

    def __init__(
        self,
        *,
        entry: ConfigEntry,
        runtime: BragerRuntime,
        devid: str,
        module_meta: dict[str, Any],
    ) -> None:
        """Initialize connectivity sensor for one module device."""
        self._runtime = runtime
        self._devid = devid
        self._module_meta = module_meta
        self._attr_unique_id = f"{entry.entry_id}_{devid}_connectivity_binary".lower().replace(" ", "_")
        self._attr_suggested_object_id = f"{devid}_cloud_connectivity".lower().replace(" ", "_")
        online = runtime.module_online(devid)
        self._attr_is_on = bool(online) if online is not None else False
        self._attr_available = True
        self._unsubscribe_connectivity: Any = None

    @property
    def device_info(self) -> DeviceInfo:
        """Attach connectivity entity to the module device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._devid)},
            manufacturer="BragerOne",
            name=str(self._module_meta.get("name") or self._devid),
            model=str(self._module_meta.get("title") or "Brager module"),
            sw_version=str(self._module_meta.get("version") or "") or None,
        )

    async def async_added_to_hass(self) -> None:
        """Attach connectivity listener when entity is added."""
        self._unsubscribe_connectivity = self._runtime.add_connectivity_listener(self._on_connectivity)
        self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        """Detach connectivity listener before entity removal."""
        if callable(self._unsubscribe_connectivity):
            self._unsubscribe_connectivity()
            self._unsubscribe_connectivity = None

    async def async_update(self) -> None:
        """Refresh on/off from runtime module online cache."""
        online = self._runtime.module_online(self._devid)
        self._attr_available = True
        self._attr_is_on = bool(online) if online is not None else False

    def _on_connectivity(self, devid: str, _online: bool) -> None:
        if devid != self._devid:
            return
        self.async_schedule_update_ha_state(True)


def _to_bool(value: Any) -> bool:
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
