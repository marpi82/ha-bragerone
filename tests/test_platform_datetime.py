"""Tests for the datetime platform and BragerSymbolDateTime entity."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.const import DATA_ENTITY_STATS, DATA_RUNTIME, DOMAIN  # noqa: E402
from custom_components.habragerone.datetime import (  # noqa: E402
    BragerSymbolDateTime,
    async_setup_entry,
)
from tests.helpers.descriptors import datetime_descriptor, switch_descriptor  # noqa: E402
from tests.helpers.fakes import FakeParamUpdate, make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


@pytest.mark.asyncio
async def test_async_setup_entry_registers_entities_and_stats(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P9.v1": "2512251200"})
    descriptors = [
        datetime_descriptor(),
        datetime_descriptor(symbol="OTHER_DT", idx=2),
        switch_descriptor(),
    ]
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors)
    added: list[BragerSymbolDateTime] = []
    await async_setup_entry(hass, entry, added.extend)

    assert len(added) == 2
    assert {entity._symbol for entity in added} == {"CZAS_ZAKONCZENIA_TRYBU_URLOP_WRITE", "OTHER_DT"}
    stats = hass.data[DOMAIN][entry.entry_id][DATA_ENTITY_STATS]["datetime"]
    assert stats == {"descriptor_count": 2, "created_count": 2, "supplemental_count": 0}


@pytest.mark.asyncio
async def test_async_setup_entry_noop_when_runtime_missing(hass: HomeAssistant) -> None:
    entry = register_config_entry(
        hass,
        runtime=make_runtime()[0],
        descriptors=[datetime_descriptor()],
    )
    hass.data[DOMAIN][entry.entry_id].pop(DATA_RUNTIME)
    added: list[BragerSymbolDateTime] = []
    await async_setup_entry(hass, entry, added.extend)

    assert added == []


@pytest.mark.asyncio
async def test_datetime_entity_identity_and_device_info(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = datetime_descriptor()
    descriptor.update(
        {
            "label": "Vacation end",
            "panel_path": "Service/Vacation",
            "module_name": "zone_module",
        },
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolDateTime(entry=entry, runtime=runtime, descriptor=descriptor)

    assert entity._attr_name == "Vacation - Vacation end"
    assert entity._attr_suggested_object_id == "dev1_czas_zakonczenia_trybu_urlop_write"
    assert entity._attr_unique_id == f"{entry.entry_id}_dev1_czas_zakonczenia_trybu_urlop_write_datetime"
    assert entity._attr_entity_registry_enabled_default is True
    assert entity.device_info["identifiers"] == {(DOMAIN, "DEV1")}


@pytest.mark.asyncio
async def test_datetime_listener_lifecycle_and_state_refresh(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P9.v1": "2512251200"})
    descriptor = datetime_descriptor()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolDateTime(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "datetime.test_vacation"

    await entity.async_added_to_hass()
    assert callable(entity._unsubscribe_listener)

    await entity.async_update()
    assert entity.native_value == datetime(2025, 12, 25, 12, 0, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    assert entity.available is True
    assert entity.state == entity.native_value.astimezone(ZoneInfo("UTC")).isoformat(timespec="seconds")

    entity._runtime.store._flat.clear()
    await entity.async_update()
    assert entity.available is False
    assert entity.native_value is None

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_listener is None


@pytest.mark.asyncio
async def test_datetime_will_remove_is_noop_without_listeners(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = datetime_descriptor()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolDateTime(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "datetime.test_vacation"

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_listener is None
    assert entity._unsubscribe_connectivity is None


@pytest.mark.asyncio
async def test_datetime_factory_default_is_wall_clock(hass: HomeAssistant) -> None:
    """Wire ``0001011200`` surfaces as ``2000-01-01 12:00`` local (date-as-date)."""
    runtime, *_rest = make_runtime(flat_values={"P9.v1": "0001011200"})
    descriptor = datetime_descriptor()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolDateTime(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "datetime.test_vacation"

    await entity.async_update()
    assert entity.native_value == datetime(2000, 1, 1, 12, 0, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    assert entity.available is True


@pytest.mark.asyncio
async def test_datetime_set_value_dispatches_wire_string(hass: HomeAssistant) -> None:
    runtime, api, _gateway, _store = make_runtime(flat_values={"P9.v1": "2512251200"})
    descriptor = datetime_descriptor()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolDateTime(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "datetime.test_vacation"
    await entity.async_added_to_hass()

    value = datetime(2026, 1, 15, 8, 30, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    await entity.async_set_value(value)

    assert len(api.calls) == 1
    assert api.calls[0]["value"] == "2601150830"
    assert entity.native_value == value


@pytest.mark.asyncio
async def test_datetime_set_value_rejects_invalid_input(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, api, _gateway, _store = make_runtime()
    descriptor = datetime_descriptor()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolDateTime(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "datetime.test_vacation"

    from custom_components.habragerone import datetime as datetime_platform

    monkeypatch.setattr(datetime_platform, "_hass_datetime_to_wire", lambda _value: None)
    with pytest.raises(HomeAssistantError, match="Invalid DATE_TIME"):
        await entity.async_set_value(datetime(2026, 1, 15, 8, 30, tzinfo=dt_util.DEFAULT_TIME_ZONE))
    assert api.calls == []


@pytest.mark.asyncio
async def test_datetime_runtime_update_schedules_refresh_for_matching_key(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = datetime_descriptor(pool="P9", chan="v", idx=1)
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolDateTime(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "datetime.test_vacation"
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]
    await entity.async_added_to_hass()
    entity.async_schedule_update_ha_state.reset_mock()

    entity._on_runtime_update(FakeParamUpdate(pool="P9", chan="v", idx=1))
    entity.async_schedule_update_ha_state.assert_called_once_with(True)

    entity.async_schedule_update_ha_state.reset_mock()
    entity._on_runtime_update(FakeParamUpdate(pool="P1", chan="s", idx=9))
    entity.async_schedule_update_ha_state.assert_not_called()

    entity.async_schedule_update_ha_state.reset_mock()
    entity._on_connectivity("OTHER", False)
    entity.async_schedule_update_ha_state.assert_not_called()
    entity._on_connectivity("DEV1", False)
    entity.async_schedule_update_ha_state.assert_called_once_with(True)
