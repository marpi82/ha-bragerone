"""Binary sensor platform for BragerOne status, module connectivity, and cloud session."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pybragerone.models.events import ParamUpdate

from .const import (
    CONF_CONNECTION_DESCRIPTORS,
    CONF_MODULES_META,
    CONNECTION_MENU_KEY,
    DATA_RUNTIME,
    DOMAIN,
)
from .entity_common import (
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
from .status_rules import coerce_status_bool, resolve_entity_bool, status_binary_has_sync_path, status_label_to_bool


def _descriptor_labels(descriptor: dict[str, Any]) -> dict[str, Any]:
    """Return the SPA label map from a connection descriptor, or an empty dict."""
    raw = descriptor.get("labels")
    return raw if isinstance(raw, dict) else {}


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
    connection_descriptors = entry.data.get(CONF_CONNECTION_DESCRIPTORS)
    connection_count = 0
    if isinstance(runtime_obj, BragerRuntime) and isinstance(modules_meta, dict) and runtime_obj.supports_module_connectivity:
        by_devid: dict[str, dict[str, Any]] = {}
        if isinstance(connection_descriptors, list):
            for raw in connection_descriptors:
                if not isinstance(raw, dict):
                    continue
                devid_key = str(raw.get("devid") or "").strip()
                if devid_key:
                    by_devid[devid_key] = raw
        for devid, meta in modules_meta.items():
            if not isinstance(devid, str) or not devid.strip():
                continue
            descriptor = by_devid.get(devid)
            if not isinstance(descriptor, dict):
                # Fail closed: never create a sensor with hardcoded/untranslated labels.
                continue
            if not isinstance(meta, dict):
                meta = {}
            entities.append(
                BragerModuleConnectivityBinarySensor(
                    entry=entry,
                    runtime=runtime_obj,
                    devid=devid,
                    module_meta=meta,
                    connection_descriptor=descriptor,
                )
            )
            connection_count += 1

    cloud_session_count = 0
    if isinstance(runtime_obj, BragerRuntime) and runtime_obj.supports_cloud_session:
        entities.append(BragerCloudSessionBinarySensor(entry=entry, runtime=runtime_obj))
        cloud_session_count = 1

    record_platform_entity_stats(
        hass,
        entry,
        platform="binary_sensor",
        descriptor_count=len(descriptors) + connection_count + cloud_session_count,
        created_count=len(entities),
    )
    async_add_entities(entities)


class BragerStatusBinarySensor(BinarySensorEntity):
    """Binary sensor for status-like symbols."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, *, entry: ConfigEntry, runtime: BragerRuntime, descriptor: dict[str, Any]) -> None:
        """Initialize binary sensor entity from one cached descriptor."""
        self._entry = entry
        self._runtime = runtime
        self._descriptor = descriptor
        self._symbol = str(descriptor.get("symbol") or "")
        self._devid = str(descriptor.get("devid") or "")

        label = descriptor_display_name(descriptor, grouping=device_grouping_mode(entry))
        self._attr_name = label
        self._attr_suggested_object_id = descriptor_suggested_object_id(descriptor)
        self._attr_unique_id = f"{entry.entry_id}_{self._devid}_{self._symbol}_binary".lower().replace(" ", "_")
        self._attr_entity_registry_enabled_default = descriptor_enabled_by_default(descriptor)
        self._attr_is_on = False
        self._attr_available = True
        self._refresh_keys = descriptor_refresh_keys(descriptor)
        self._unsubscribe_listener: Any = None
        self._unsubscribe_connectivity: Any = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata for HA device registry."""
        return device_info_from_descriptor(
            self._descriptor,
            domain=DOMAIN,
            grouping=device_grouping_mode(self._entry),
        )

    async def async_added_to_hass(self) -> None:
        """Attach runtime listeners when entity is added."""
        self._unsubscribe_listener = self._runtime.add_listener(self._on_runtime_update)
        self._unsubscribe_connectivity = self._runtime.add_connectivity_listener(self._on_connectivity)
        raw_value = descriptor_current_raw_value(self._runtime.store, self._descriptor)
        if raw_value is not None and self._try_apply_binary_state_sync(raw_value):
            self._attr_available = entity_is_available(
                self._runtime,
                devid=self._devid,
                has_value=True,
            )
            self.async_write_ha_state()
            return
        if self._try_apply_status_label_cache(raw_value):
            self._attr_available = entity_is_available(
                self._runtime,
                devid=self._devid,
                has_value=raw_value is not None or self._runtime.peek_status_label(self._symbol) is not None,
            )
            self.async_write_ha_state()
            return
        self.async_schedule_update_ha_state(True)

    def _try_apply_status_label_cache(self, raw_value: Any | None) -> bool:
        """Apply on/off from pre-warmed STATUS labels without scheduling ``async_update``."""
        if not self._symbol.startswith("STATUS_"):
            return False
        cached = self._runtime.peek_status_label(self._symbol)
        if cached is None:
            return False
        resolved_bool = status_label_to_bool(cached)
        if resolved_bool is None:
            resolved_bool = resolve_entity_bool(
                descriptor=self._descriptor,
                flat_values=self._runtime.store.flatten(),
                default_actual=raw_value if raw_value is not None else cached,
            )
        self._attr_is_on = resolved_bool
        return True

    def _try_apply_binary_state_sync(self, raw_value: Any) -> bool:
        """Apply on/off from ParamStore without ``ParamResolver`` when possible."""
        flat_values = self._runtime.store.flatten()
        if self._symbol.startswith("STATUS_") and not status_binary_has_sync_path(
            descriptor=self._descriptor,
            flat_values=flat_values,
            default_actual=raw_value,
        ):
            return False
        self._attr_is_on = resolve_entity_bool(
            descriptor=self._descriptor,
            flat_values=flat_values,
            default_actual=raw_value,
        )
        return True

    async def async_will_remove_from_hass(self) -> None:
        """Detach runtime listeners before entity removal."""
        if callable(self._unsubscribe_listener):
            self._unsubscribe_listener()
            self._unsubscribe_listener = None
        if callable(self._unsubscribe_connectivity):
            self._unsubscribe_connectivity()
            self._unsubscribe_connectivity = None

    async def async_update(self) -> None:
        """Refresh state from ParamStore / SPA status resolver."""
        raw_value = descriptor_current_raw_value(self._runtime.store, self._descriptor)
        self._attr_available = entity_is_available(
            self._runtime,
            devid=self._devid,
            has_value=raw_value is not None,
        )
        if raw_value is None:
            return

        if self._try_apply_binary_state_sync(raw_value):
            return

        # STATUS_* diodes (e.g. PumpState) with value maps / dual-bit inputs need the SPA
        # ComputedValueEvaluator — cached command_rules alone are not always enough.
        if self._symbol.startswith("STATUS_"):
            resolved = await self._runtime.async_resolve_status_label(self._symbol)
            resolved_bool = status_label_to_bool(resolved)
            if resolved_bool is not None:
                self._attr_is_on = resolved_bool
                return

        self._attr_is_on = resolve_entity_bool(
            descriptor=self._descriptor,
            flat_values=self._runtime.store.flatten(),
            default_actual=raw_value,
        )

    def _on_runtime_update(self, _update: ParamUpdate) -> None:
        update_key = f"{_update.pool}.{_update.chan}{_update.idx}"
        if self._refresh_keys and update_key not in self._refresh_keys:
            return
        self.async_schedule_update_ha_state(True)

    def _on_connectivity(self, devid: str, _online: bool, online_changed: bool = True) -> None:
        if devid != self._devid or not online_changed:
            return
        self.async_schedule_update_ha_state(True)


class BragerModuleConnectivityBinarySensor(BinarySensorEntity):
    """Diagnostic binary sensor for SPA module connection status."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        *,
        entry: ConfigEntry,
        runtime: BragerRuntime,
        devid: str,
        module_meta: dict[str, Any],
        connection_descriptor: dict[str, Any],
    ) -> None:
        """Initialize connectivity sensor for one module connection device."""
        self._runtime = runtime
        self._devid = devid
        self._module_meta = module_meta
        self._descriptor = connection_descriptor
        labels = _descriptor_labels(self._descriptor)
        label = (
            str(self._descriptor.get("label") or "").strip()
            or str(labels.get("connection.status") or "").strip()
            or str(labels.get("serverConnection") or "").strip()
        )
        if not label:
            raise ValueError("connection descriptor missing SPA i18n label")
        self._attr_name = label
        self._attr_unique_id = f"{entry.entry_id}_{devid}_connectivity_binary".lower().replace(" ", "_")
        self._attr_suggested_object_id = f"{devid}_connection_status".lower().replace(" ", "_")
        online = runtime.module_online(devid)
        # Unknown stays unknown — never coerce None to offline.
        self._attr_is_on = online
        self._attr_available = online is not None
        self._unsubscribe_connectivity: Any = None

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to a connection child device via the internet module.

        Stable id uses SPA i18n path ``module.connection`` (not a menu-router route)
        so HA #165 can keep these entities separable from panel-grouped devices.
        """
        labels = _descriptor_labels(self._descriptor)
        module_name = str(self._module_meta.get("name") or self._descriptor.get("module_name") or self._devid)
        index_label = str(labels.get("connection.index") or "").strip()
        device_name = str(self._descriptor.get("device_name") or "").strip() or (
            f"{module_name} — {index_label}" if index_label else module_name
        )
        menu_key = str(self._descriptor.get("menu_key") or CONNECTION_MENU_KEY)
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._devid}:{menu_key}")},
            manufacturer="BragerOne",
            name=device_name,
            model=str(self._module_meta.get("title") or self._descriptor.get("module_title") or module_name),
            sw_version=str(self._module_meta.get("version") or "") or None,
            via_device=(DOMAIN, self._devid),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose SPA connection fields (connectedAt + gateway) as attributes."""
        meta = self._runtime.modules_meta.get(self._devid, self._module_meta)
        attrs: dict[str, Any] = {}
        connected_at = meta.get("connectedAt") if isinstance(meta, dict) else None
        if isinstance(connected_at, int):
            attrs["connected_at"] = connected_at
        gateway = meta.get("gateway") if isinstance(meta, dict) else None
        if isinstance(gateway, dict):
            for key in ("address", "interface", "version"):
                value = gateway.get(key)
                if value is not None and value != "":
                    attrs[f"gateway_{key}"] = value
        labels = _descriptor_labels(self._descriptor)
        connected_label = labels.get("connection.connected")
        if isinstance(connected_label, str):
            attrs["state_label_on"] = connected_label
        not_connected_label = labels.get("connection.notConnected")
        if isinstance(not_connected_label, str):
            attrs["state_label_off"] = not_connected_label
        return attrs

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
        self._attr_is_on = online
        self._attr_available = online is not None

    def _on_connectivity(self, devid: str, _online: bool, online_changed: bool = True) -> None:
        if devid != self._devid:
            return
        # Refresh on online flips and on metadata-only connectedAt/gateway updates.
        self.async_schedule_update_ha_state(True)


class BragerCloudSessionBinarySensor(BinarySensorEntity):
    """Diagnostic binary sensor for library↔cloud Socket.IO session health.

    Distinct from :class:`BragerModuleConnectivityBinarySensor` (module↔cloud
    ``connectedAt``). When this is off the library self-heals; module offline is
    observe-only and must not be inferred from this bit.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "cloud_session"

    def __init__(self, *, entry: ConfigEntry, runtime: BragerRuntime) -> None:
        """Initialize the cloud API session diagnostic for one config entry."""
        self._runtime = runtime
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_cloud_session_binary"
        self._attr_suggested_object_id = "cloud_api_session"
        up = runtime.cloud_session_up()
        self._attr_is_on = up
        self._attr_available = up is not None
        self._unsubscribe_session: Any = None

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to a config-entry service device (not a per-module child)."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"entry:{self._entry.entry_id}")},
            manufacturer="BragerOne",
            name="BragerOne",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Attach cloud-session listener when entity is added."""
        self._unsubscribe_session = self._runtime.add_cloud_session_listener(self._on_cloud_session)
        self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        """Detach cloud-session listener before entity removal."""
        if callable(self._unsubscribe_session):
            self._unsubscribe_session()
            self._unsubscribe_session = None

    async def async_update(self) -> None:
        """Refresh on/off from runtime cloud-session cache."""
        up = self._runtime.cloud_session_up()
        self._attr_is_on = up
        self._attr_available = up is not None

    def _on_cloud_session(self, _up: bool, _changed: bool = True) -> None:
        self.async_schedule_update_ha_state(True)


def _to_bool(value: Any) -> bool:
    """Backward-compatible alias for status bool coercion."""
    return coerce_status_bool(value)
