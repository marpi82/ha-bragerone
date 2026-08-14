"""Tests for the number platform and BragerSymbolNumber entity."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.const import DATA_ENTITY_STATS, DATA_RUNTIME, DOMAIN  # noqa: E402
from custom_components.habragerone.number import BragerSymbolNumber, async_setup_entry  # noqa: E402
from tests.helpers.descriptors import switch_descriptor, writable_parameter_descriptor  # noqa: E402
from tests.helpers.fakes import FakeParamUpdate, make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


@pytest.mark.asyncio
async def test_async_setup_entry_registers_entities_and_stats(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P6.v0": 12.5})
    descriptors = [
        writable_parameter_descriptor(symbol="NUM1", raw_min=0, raw_max=100),
        writable_parameter_descriptor(symbol="NUM2", idx=1),
        switch_descriptor(),
    ]
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors)
    added: list[BragerSymbolNumber] = []
    await async_setup_entry(hass, entry, added.extend)

    assert len(added) == 2
    assert {entity._symbol for entity in added} == {"NUM1", "NUM2"}
    stats = hass.data[DOMAIN][entry.entry_id][DATA_ENTITY_STATS]["number"]
    assert stats == {"descriptor_count": 2, "created_count": 2}


@pytest.mark.asyncio
async def test_async_setup_entry_noop_when_runtime_missing(hass: HomeAssistant) -> None:
    entry = register_config_entry(
        hass,
        runtime=make_runtime()[0],
        descriptors=[writable_parameter_descriptor()],
    )
    hass.data[DOMAIN][entry.entry_id].pop(DATA_RUNTIME)
    added: list[BragerSymbolNumber] = []
    await async_setup_entry(hass, entry, added.extend)

    assert added == []


@pytest.mark.asyncio
async def test_number_entity_identity_min_max_and_device_info(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = writable_parameter_descriptor(symbol="SETPOINT", raw_min=5, raw_max=30)
    descriptor.update(
        {
            "label": "Target temperature",
            "panel_path": "Heating/Zone 1",
            "module_name": "zone_module",
        },
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolNumber(entry=entry, runtime=runtime, descriptor=descriptor)

    assert entity._attr_name == "Heating/Zone 1 - Target temperature"
    assert entity._attr_suggested_object_id == "zone_module_setpoint"
    assert entity._attr_unique_id == f"{entry.entry_id}_dev1_setpoint_number"
    assert entity._attr_native_min_value == 5.0
    assert entity._attr_native_max_value == 30.0
    assert entity.device_info["identifiers"] == {(DOMAIN, "DEV1")}


@pytest.mark.asyncio
async def test_number_listener_lifecycle_and_state_refresh(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P6.v0": 21})
    descriptor = writable_parameter_descriptor()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolNumber(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "number.test_number"

    await entity.async_added_to_hass()
    assert callable(entity._unsubscribe_listener)

    await entity.async_update()
    assert entity.native_value == 21.0
    assert entity.available is True

    entity._runtime.store._flat.clear()
    await entity.async_update()
    assert entity.available is False

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_listener is None


@pytest.mark.asyncio
async def test_number_set_native_value_dispatches_write(hass: HomeAssistant) -> None:
    runtime, api, _gateway, _store = make_runtime()
    descriptor = writable_parameter_descriptor(raw_min=0, raw_max=100)
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolNumber(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "number.test_number"
    await entity.async_added_to_hass()

    await entity.async_set_native_value(18.5)

    assert len(api.calls) == 1
    assert entity.native_value == 18.5


@pytest.mark.asyncio
async def test_number_runtime_update_schedules_refresh_for_matching_key(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = writable_parameter_descriptor(pool="P6", chan="v", idx=0)
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolNumber(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "number.test_number"
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]
    await entity.async_added_to_hass()
    entity.async_schedule_update_ha_state.reset_mock()

    entity._on_runtime_update(FakeParamUpdate(pool="P6", chan="v", idx=0))
    entity.async_schedule_update_ha_state.assert_called_once_with(True)

    entity.async_schedule_update_ha_state.reset_mock()
    entity._on_runtime_update(FakeParamUpdate(pool="P1", chan="s", idx=9))
    entity.async_schedule_update_ha_state.assert_not_called()
