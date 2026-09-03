"""Module alarms/activity event-feed sensors (SPA Alarms + Activity — #222/#223)."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import slugify

from .const import CONF_MODULES_META, DOMAIN
from .entity_common import module_is_reachable
from .runtime import BragerRuntime


async def iter_alarm_feed_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    runtime: BragerRuntime,
) -> list[SensorEntity]:
    """Build per-module current/history alarm sensors when API + i18n allow it.

    Fail closed when SPA ``alarm.currentAlarms`` / ``alarm.historyAlarms`` chrome
    labels cannot be resolved (never hardcode PL/EN entity names).
    """
    _ = hass
    if not runtime.supports_module_alarms:
        return []

    modules_meta = entry.data.get(CONF_MODULES_META)
    if not isinstance(modules_meta, dict) or not modules_meta:
        modules_meta = runtime.modules_meta
    if not isinstance(modules_meta, dict) or not modules_meta:
        return []

    chrome = await runtime.async_get_alarm_chrome_labels()
    if chrome is None:
        return []
    current_label = chrome.get("currentAlarms")
    history_label = chrome.get("historyAlarms")
    if not isinstance(current_label, str) or not current_label.strip():
        return []
    if not isinstance(history_label, str) or not history_label.strip():
        return []

    devids: list[str] = []
    module_metas: dict[str, dict[str, Any]] = {}
    for raw_devid, meta in modules_meta.items():
        devid = str(raw_devid or "").strip()
        if not devid:
            continue
        devids.append(devid)
        module_metas[devid] = meta if isinstance(meta, dict) else {}

    await asyncio.gather(*(runtime.async_refresh_alarms(devid) for devid in devids))

    entities: list[SensorEntity] = []
    for devid in devids:
        module_meta = module_metas[devid]
        entities.append(
            BragerAlarmsCurrentSensor(
                entry=entry,
                runtime=runtime,
                devid=devid,
                module_meta=module_meta,
                name=current_label.strip(),
            )
        )
        entities.append(
            BragerAlarmsHistorySensor(
                entry=entry,
                runtime=runtime,
                devid=devid,
                module_meta=module_meta,
                name=history_label.strip(),
            )
        )
    return entities


class _BragerAlarmsFeedSensor(SensorEntity):
    """Shared base for current/history module alarm count sensors.

    State is the number of rows returned on the SPA first page (``page=1``,
    ``limit=20``), not the total alarm count across all pages.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _feed_kind: str

    def __init__(
        self,
        *,
        entry: ConfigEntry,
        runtime: BragerRuntime,
        devid: str,
        module_meta: dict[str, Any],
        name: str,
    ) -> None:
        """Initialize one diagnostic alarms feed sensor for *devid*."""
        self._entry = entry
        self._runtime = runtime
        self._devid = devid
        self._module_meta = module_meta
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{devid}_alarms_{self._feed_kind}".lower().replace(" ", "_")
        self._attr_suggested_object_id = slugify(f"{devid}_alarms_{self._feed_kind}")
        self._attr_native_value = len(self._alarms())
        self._attr_available = True
        self._unsubscribe_feed: Any = None
        self._unsubscribe_connectivity: Any = None

    def _alarms(self) -> list[dict[str, Any]]:
        if self._feed_kind == "current":
            return self._runtime.alarms_current(self._devid)
        return self._runtime.alarms_history(self._devid)

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to the internet module device (same parent as connectivity parent device)."""
        meta = self._runtime.modules_meta.get(self._devid, self._module_meta)
        module_name = str(meta.get("name") or self._module_meta.get("name") or self._devid)
        return DeviceInfo(
            identifiers={(DOMAIN, self._devid)},
            manufacturer="BragerOne",
            name=module_name,
            model=str(meta.get("title") or self._module_meta.get("title") or module_name),
            sw_version=str(meta.get("version") or self._module_meta.get("version") or "") or None,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the structured alarms list for automations and dashboards."""
        return {"alarms": self._alarms()}

    async def async_added_to_hass(self) -> None:
        """Subscribe to feed + connectivity; initial list was refreshed at setup."""
        self._unsubscribe_feed = self._runtime.add_event_feed_listener(self._on_event_feed)
        self._unsubscribe_connectivity = self._runtime.add_connectivity_listener(self._on_connectivity)
        self._apply_from_cache()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Detach runtime listeners before entity removal."""
        if callable(self._unsubscribe_feed):
            self._unsubscribe_feed()
            self._unsubscribe_feed = None
        if callable(self._unsubscribe_connectivity):
            self._unsubscribe_connectivity()
            self._unsubscribe_connectivity = None

    async def async_update(self) -> None:
        """Refresh state from the runtime alarms cache (no REST from here)."""
        self._apply_from_cache()

    def _apply_from_cache(self) -> None:
        alarms = self._alarms()
        self._attr_native_value = len(alarms)
        self._attr_available = module_is_reachable(self._runtime, self._devid) and self._runtime.alarms_feed_ready(self._devid)

    def _on_event_feed(self, devid: str) -> None:
        if devid != self._devid:
            return
        self._apply_from_cache()
        self.async_write_ha_state()

    def _on_connectivity(self, devid: str, online: bool, online_changed: bool = True) -> None:
        if devid != self._devid:
            return
        if online and online_changed:
            self.hass.async_create_task(self._runtime.async_refresh_alarms(self._devid))
        self._apply_from_cache()
        self.async_schedule_update_ha_state(False)


class BragerAlarmsCurrentSensor(_BragerAlarmsFeedSensor):
    """Diagnostic sensor: count + list of active module alarms."""

    _feed_kind = "current"


class BragerAlarmsHistorySensor(_BragerAlarmsFeedSensor):
    """Diagnostic sensor: count + list of finished/historical module alarms."""

    _feed_kind = "history"


async def iter_activity_feed_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    runtime: BragerRuntime,
) -> list[SensorEntity]:
    """Build per-module activity sensors when API + i18n allow it.

    Fail closed when SPA ``routes.activity.index`` cannot be resolved (never
    hardcode PL/EN entity names). State is the loaded row count (SPA first page,
    ``limit=20``); ``extra_state_attributes.activities`` holds the structured list.
    """
    _ = hass
    if not runtime.supports_module_activity:
        return []

    modules_meta = entry.data.get(CONF_MODULES_META)
    if not isinstance(modules_meta, dict) or not modules_meta:
        modules_meta = runtime.modules_meta
    if not isinstance(modules_meta, dict) or not modules_meta:
        return []

    index_label = await runtime.async_get_activity_index_label()
    if not isinstance(index_label, str) or not index_label.strip():
        return []

    devids: list[str] = []
    module_metas: dict[str, dict[str, Any]] = {}
    for raw_devid, meta in modules_meta.items():
        devid = str(raw_devid or "").strip()
        if not devid:
            continue
        devids.append(devid)
        module_metas[devid] = meta if isinstance(meta, dict) else {}

    await asyncio.gather(*(runtime.async_refresh_activity(devid) for devid in devids))

    return [
        BragerActivitySensor(
            entry=entry,
            runtime=runtime,
            devid=devid,
            module_meta=module_metas[devid],
            name=index_label.strip(),
        )
        for devid in devids
    ]


class BragerActivitySensor(SensorEntity):
    """Diagnostic sensor: count + list of module activity rows."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        *,
        entry: ConfigEntry,
        runtime: BragerRuntime,
        devid: str,
        module_meta: dict[str, Any],
        name: str,
    ) -> None:
        """Initialize one diagnostic activity feed sensor for *devid*."""
        self._entry = entry
        self._runtime = runtime
        self._devid = devid
        self._module_meta = module_meta
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{devid}_activity".lower().replace(" ", "_")
        self._attr_suggested_object_id = slugify(f"{devid}_activity")
        self._attr_native_value = len(self._activities())
        self._attr_available = True
        self._unsubscribe_feed: Any = None
        self._unsubscribe_connectivity: Any = None

    def _activities(self) -> list[dict[str, Any]]:
        return self._runtime.activity(self._devid)

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to the internet module device (same parent as connectivity parent device)."""
        meta = self._runtime.modules_meta.get(self._devid, self._module_meta)
        module_name = str(meta.get("name") or self._module_meta.get("name") or self._devid)
        return DeviceInfo(
            identifiers={(DOMAIN, self._devid)},
            manufacturer="BragerOne",
            name=module_name,
            model=str(meta.get("title") or self._module_meta.get("title") or module_name),
            sw_version=str(meta.get("version") or self._module_meta.get("version") or "") or None,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the structured activities list for automations and dashboards."""
        return {"activities": self._activities()}

    async def async_added_to_hass(self) -> None:
        """Subscribe to feed + connectivity; initial list was refreshed at setup."""
        self._unsubscribe_feed = self._runtime.add_event_feed_listener(self._on_event_feed)
        self._unsubscribe_connectivity = self._runtime.add_connectivity_listener(self._on_connectivity)
        self._apply_from_cache()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Detach runtime listeners before entity removal."""
        if callable(self._unsubscribe_feed):
            self._unsubscribe_feed()
            self._unsubscribe_feed = None
        if callable(self._unsubscribe_connectivity):
            self._unsubscribe_connectivity()
            self._unsubscribe_connectivity = None

    async def async_update(self) -> None:
        """Refresh state from the runtime activity cache (no REST from here)."""
        self._apply_from_cache()

    def _apply_from_cache(self) -> None:
        activities = self._activities()
        self._attr_native_value = len(activities)
        self._attr_available = module_is_reachable(self._runtime, self._devid) and self._runtime.activity_feed_ready(self._devid)

    def _on_event_feed(self, devid: str) -> None:
        if devid != self._devid:
            return
        self._apply_from_cache()
        self.async_write_ha_state()

    def _on_connectivity(self, devid: str, online: bool, online_changed: bool = True) -> None:
        if devid != self._devid:
            return
        if online and online_changed:
            self.hass.async_create_task(self._runtime.async_refresh_activity(self._devid))
        self._apply_from_cache()
        self.async_schedule_update_ha_state(False)
