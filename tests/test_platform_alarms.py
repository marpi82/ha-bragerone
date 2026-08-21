"""Tests for module alarms feed sensors (#222)."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.const import (  # noqa: E402
    CONF_MODULES_META,
    DATA_ENTITY_STATS,
    DOMAIN,
)
from custom_components.habragerone.event_feeds import (  # noqa: E402
    BragerAlarmsCurrentSensor,
    BragerAlarmsHistorySensor,
    iter_alarm_feed_entities,
)
from custom_components.habragerone.sensor import async_setup_entry  # noqa: E402
from tests.helpers.descriptors import sensor_descriptor  # noqa: E402
from tests.helpers.fakes import FakeApi, make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


class _AlarmsApi(FakeApi):
    """Fake API with modules_alarms list helpers."""

    def __init__(self) -> None:
        super().__init__()
        self.current_calls = 0
        self.history_calls = 0
        self.current_payload: dict[str, Any] = {
            "status": True,
            "alarms": [
                {
                    "id": 38,
                    "devid": "DEV1",
                    "created_at": "2026-04-28T08:00:46.000000Z",
                }
            ],
        }
        self.history_payload: dict[str, Any] = {
            "status": True,
            "alarms": {
                "data": [
                    {
                        "id": 0,
                        "devid": "DEV1",
                        "created_at": "2026-04-28T07:00:00.000000Z",
                        "finished_at": "2026-04-28T08:09:57.000000Z",
                    }
                ]
            },
        }

    async def modules_alarms(
        self,
        modules: list[str],
        *,
        page: int = 1,
        limit: int = 20,
        return_data: bool = False,
    ) -> tuple[int, Any] | bool:
        self.current_calls += 1
        assert modules == ["DEV1"]
        assert page == 1
        assert limit == 20
        return (200, self.current_payload) if return_data else True

    async def modules_alarms_history(
        self,
        modules: list[str],
        *,
        page: int = 1,
        limit: int = 20,
        return_data: bool = False,
    ) -> tuple[int, Any] | bool:
        self.history_calls += 1
        assert modules == ["DEV1"]
        return (200, self.history_payload) if return_data else True


def _runtime_with_alarms(*, language: str = "en") -> tuple[Any, _AlarmsApi]:
    api = _AlarmsApi()
    runtime, *_rest = make_runtime(api=api, modules_meta={"DEV1": {"name": "Boiler", "title": "DasPell", "version": "V2"}})
    runtime.language = language
    runtime._alarm_chrome_labels = {
        "currentAlarms": "Current alarms",
        "historyAlarms": "Alarm history",
    }
    runtime._alarm_names = {38: "ERROR_BRAK_PALIWA", 0: "ERROR_TEMPERATURA_KOTLA"}
    runtime._errors_i18n = {
        "ERROR_BRAK_PALIWA": "No fuel",
        "ERROR_TEMPERATURA_KOTLA": "Boiler temperature",
    }
    runtime._alarm_names_loaded = True
    return runtime, api


@pytest.mark.asyncio
async def test_async_refresh_alarms_normalizes_and_resolves_names() -> None:
    runtime, api = _runtime_with_alarms()
    seen: list[str] = []
    runtime.add_event_feed_listener(seen.append)

    await runtime.async_refresh_alarms("DEV1")

    assert api.current_calls == 1
    assert api.history_calls == 1
    assert seen == ["DEV1"]
    current = runtime.alarms_current("DEV1")
    assert len(current) == 1
    assert current[0]["id"] == 38
    assert current[0]["name"] == "No fuel"
    assert current[0]["finished_at"] is None
    history = runtime.alarms_history("DEV1")
    assert len(history) == 1
    assert history[0]["id"] == 0
    assert history[0]["name"] == "Boiler temperature"
    assert history[0]["finished_at"] == "2026-04-28T08:09:57.000000Z"


@pytest.mark.asyncio
async def test_async_refresh_alarms_noops_without_api() -> None:
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    await runtime.async_refresh_alarms("DEV1")
    assert runtime.alarms_current("DEV1") == []
    assert runtime.supports_module_alarms is False


@pytest.mark.asyncio
async def test_iter_alarm_feed_entities_fail_closed_without_chrome(hass: HomeAssistant) -> None:
    runtime, api = _runtime_with_alarms()
    runtime._alarm_chrome_labels = {}
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_MODULES_META: {"DEV1": {"name": "Boiler"}}},
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    entities = await iter_alarm_feed_entities(hass, entry, runtime)
    assert entities == []
    assert api.current_calls == 0


@pytest.mark.asyncio
async def test_iter_and_setup_create_alarm_sensors(hass: HomeAssistant) -> None:
    runtime, api = _runtime_with_alarms()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[sensor_descriptor()])
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_MODULES_META: {"DEV1": {"name": "Boiler", "title": "DasPell", "version": "V2"}},
        },
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    added: list[object] = []
    await async_setup_entry(hass, entry, added.extend)

    current = [entity for entity in added if isinstance(entity, BragerAlarmsCurrentSensor)]
    history = [entity for entity in added if isinstance(entity, BragerAlarmsHistorySensor)]
    assert len(current) == 1
    assert len(history) == 1
    assert api.current_calls == 1
    assert api.history_calls == 1

    entity = current[0]
    assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC
    assert entity._attr_should_poll is False
    assert entity._attr_has_entity_name is True
    assert entity._attr_name == "Current alarms"
    assert entity._attr_unique_id == f"{entry.entry_id}_dev1_alarms_current"
    assert entity._attr_native_value == 1
    attrs = entity.extra_state_attributes
    assert attrs["alarms"][0]["id"] == 38
    assert attrs["alarms"][0]["name"] == "No fuel"
    assert attrs["alarms"][0]["devid"] == "DEV1"
    assert attrs["alarms"][0]["created_at"] == "2026-04-28T08:00:46.000000Z"
    assert attrs["alarms"][0]["finished_at"] is None

    hist = history[0]
    assert hist._attr_unique_id == f"{entry.entry_id}_dev1_alarms_history"
    assert hist._attr_name == "Alarm history"
    assert hist._attr_native_value == 1
    assert hist.extra_state_attributes["alarms"][0]["finished_at"] == "2026-04-28T08:09:57.000000Z"

    info = entity.device_info
    assert info is not None
    assert (DOMAIN, "DEV1") in info["identifiers"]
    assert info.get("manufacturer") == "BragerOne"

    stats = hass.data[DOMAIN][entry.entry_id][DATA_ENTITY_STATS]["sensor"]
    assert stats["created_count"] == 3
    assert stats["descriptor_count"] == 3


@pytest.mark.asyncio
async def test_alarm_sensor_refreshes_when_module_comes_online(hass: HomeAssistant) -> None:
    runtime, api = _runtime_with_alarms()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    entity = BragerAlarmsCurrentSensor(
        entry=entry,
        runtime=runtime,
        devid="DEV1",
        module_meta={"name": "Boiler"},
        name="Current alarms",
    )
    entity.hass = hass
    entity.async_write_ha_state = lambda: None  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = lambda *a, **k: None  # type: ignore[method-assign]

    await entity.async_added_to_hass()
    assert api.current_calls == 0

    api.current_payload = {
        "status": True,
        "alarms": [
            {"id": 38, "devid": "DEV1", "created_at": "t0"},
            {"id": 54, "devid": "DEV1", "created_at": "t1"},
        ],
    }
    runtime._module_online["DEV1"] = False
    entity._on_connectivity("DEV1", True, True)
    # Connectivity schedules a task; flush it.
    await hass.async_block_till_done()
    await entity.async_update()
    assert api.current_calls >= 1
    assert entity._attr_native_value == 2

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_feed is None
    assert entity._unsubscribe_connectivity is None


@pytest.mark.asyncio
async def test_alarm_sensor_event_feed_updates_state(hass: HomeAssistant) -> None:
    runtime, _api = _runtime_with_alarms()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    entity = BragerAlarmsHistorySensor(
        entry=entry,
        runtime=runtime,
        devid="DEV1",
        module_meta={"name": "Boiler"},
        name="Alarm history",
    )
    entity.hass = hass
    entity.async_write_ha_state = lambda: None  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = lambda *a, **k: None  # type: ignore[method-assign]

    await entity.async_added_to_hass()
    runtime._alarms_history["DEV1"] = [
        {"id": 1, "name": None, "devid": "DEV1", "created_at": "a", "finished_at": "b"},
        {"id": 2, "name": None, "devid": "DEV1", "created_at": "c", "finished_at": "d"},
    ]
    entity._on_event_feed("DEV1")
    assert entity._attr_native_value == 2
    entity._on_event_feed("OTHER")
    assert entity._attr_native_value == 2
