"""Tests for the sensor platform entity lifecycle and update paths."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.const import DATA_ENTITY_STATS, DATA_RUNTIME, DOMAIN  # noqa: E402
from custom_components.habragerone.sensor import BragerSymbolSensor, async_setup_entry  # noqa: E402
from tests.helpers.descriptors import button_descriptor, sensor_descriptor  # noqa: E402
from tests.helpers.fakes import FakeParamUpdate, FakeStore, make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


@pytest.mark.asyncio
async def test_async_setup_entry_registers_entities_and_stats(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P6.v0": 21.5})
    descriptors = [
        sensor_descriptor(symbol="TEMP1"),
        sensor_descriptor(symbol="TEMP2", idx=1),
        button_descriptor(),
    ]
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors)
    added: list[BragerSymbolSensor] = []
    await async_setup_entry(hass, entry, added.extend)

    assert len(added) == 2
    assert {entity._symbol for entity in added} == {"TEMP1", "TEMP2"}
    stats = hass.data[DOMAIN][entry.entry_id][DATA_ENTITY_STATS]["sensor"]
    assert stats == {"descriptor_count": 2, "created_count": 2}


@pytest.mark.asyncio
async def test_async_setup_entry_noop_when_runtime_missing(hass: HomeAssistant) -> None:
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[sensor_descriptor()])
    hass.data[DOMAIN][entry.entry_id].pop(DATA_RUNTIME)
    added: list[BragerSymbolSensor] = []
    await async_setup_entry(hass, entry, added.extend)

    assert added == []


@pytest.mark.asyncio
async def test_sensor_entity_identity_and_device_info(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = sensor_descriptor(symbol="TEMP_BOILER", unit="°C")
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)

    assert entity._attr_name == "Boiler temperature"
    assert entity._attr_unique_id == f"{entry.entry_id}_dev1_temp_boiler"
    assert entity._attr_native_unit_of_measurement == UnitOfTemperature.CELSIUS
    assert entity._attr_device_class == SensorDeviceClass.TEMPERATURE
    assert entity._attr_state_class == SensorStateClass.MEASUREMENT
    assert entity.device_info["identifiers"] == {(DOMAIN, "DEV1")}


@pytest.mark.asyncio
async def test_sensor_listener_lifecycle_and_numeric_state(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P6.v0": 55.2})
    descriptor = sensor_descriptor(unit=None)
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "sensor.test_temp"

    await entity.async_added_to_hass()
    assert callable(entity._unsubscribe_listener)

    await entity.async_update()
    assert entity.native_value == 55.2
    assert entity.available is True

    entity._runtime.store._flat.clear()
    await entity.async_update()
    assert entity.available is False

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_listener is None


@pytest.mark.asyncio
async def test_sensor_update_uses_raw_to_label_mapping(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P6.v0": 1})
    descriptor = sensor_descriptor(raw_to_label={"1": "Open", "0": "Closed"})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "sensor.test_valve"

    await entity.async_update()

    assert entity.native_value == "open"


@pytest.mark.asyncio
async def test_sensor_update_uses_status_resolver_for_status_symbols(hass: HomeAssistant) -> None:
    store = FakeStore(flat_values={"P5.s5": 768})
    resolve_status = AsyncMock(return_value="Work")
    runtime = SimpleNamespace(
        store=store,
        add_listener=lambda _cb: lambda: None,
        module_online=lambda _devid: None,
        async_resolve_status_label=resolve_status,
    )
    descriptor = sensor_descriptor(symbol="STATUS_BOILER", pool="P5", chan="s", idx=5, unit=None)
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)  # type: ignore[arg-type]
    entity.hass = hass
    entity.entity_id = "sensor.test_status"

    await entity.async_update()

    assert entity.native_value == "work"
    resolve_status.assert_awaited_once_with("STATUS_BOILER")


@pytest.mark.asyncio
async def test_sensor_update_uses_dynamic_unit_resolver(hass: HomeAssistant) -> None:
    store = FakeStore(flat_values={"P10.v2": 33})
    resolve_with_unit = AsyncMock(return_value=(42.0, "%"))
    runtime = SimpleNamespace(
        store=store,
        add_listener=lambda _cb: lambda: None,
        module_online=lambda _devid: None,
        async_resolve_symbol_with_unit=resolve_with_unit,
    )
    descriptor = sensor_descriptor(
        symbol="PARAM16_2",
        pool="P10",
        chan="v",
        idx=2,
        unit=None,
        mapping_channels={
            "value": [{"address": "P10.v2"}],
            "unit": [{"address": "P10.u2"}],
        },
    )
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)  # type: ignore[arg-type]
    entity.hass = hass
    entity.entity_id = "sensor.test_power"

    await entity.async_update()

    assert entity.native_value == 42.0
    assert entity.native_unit_of_measurement == "%"
    assert entity._attr_device_class is None
    assert entity._attr_state_class == SensorStateClass.MEASUREMENT
    resolve_with_unit.assert_awaited_once_with("PARAM16_2")


@pytest.mark.asyncio
async def test_sensor_dynamic_unit_resolver_skips_unresolved_unit_token(hass: HomeAssistant) -> None:
    store = FakeStore(flat_values={"P10.v2": 33})
    resolve_with_unit = AsyncMock(return_value=(None, "wn.9998"))
    runtime = SimpleNamespace(
        store=store,
        add_listener=lambda _cb: lambda: None,
        module_online=lambda _devid: None,
        async_resolve_symbol_with_unit=resolve_with_unit,
        async_resolve_status_label=AsyncMock(return_value=None),
    )
    descriptor = sensor_descriptor(
        symbol="PARAM16_2",
        pool="P10",
        chan="v",
        idx=2,
        unit=None,
        mapping_channels={
            "value": [{"address": "P10.v2"}],
            "unit": [{"address": "P10.u2"}],
        },
    )
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)  # type: ignore[arg-type]
    entity.hass = hass
    entity.entity_id = "sensor.test_power"

    await entity.async_update()

    assert entity.native_unit_of_measurement is None
    assert entity.native_value == 33


@pytest.mark.asyncio
async def test_sensor_update_uses_command_rule_display_value(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P5.s5": 768})
    descriptor = sensor_descriptor(
        pool="P5",
        chan="s",
        idx=5,
        unit=None,
        command_rules=[
            {
                "value": "WORK",
                "conditions": [{"operation": "equalTo", "expected": 768, "targets": [{"address": "P5.s5"}]}],
            }
        ],
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "sensor.test_rule"

    await entity.async_update()

    assert entity.native_value == "work"


@pytest.mark.asyncio
async def test_sensor_runtime_update_schedules_refresh_for_matching_key(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = sensor_descriptor(pool="P6", chan="v", idx=0)
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "sensor.test_temp"
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]
    await entity.async_added_to_hass()
    entity.async_schedule_update_ha_state.reset_mock()

    entity._on_runtime_update(FakeParamUpdate(pool="P6", chan="v", idx=0))
    entity.async_schedule_update_ha_state.assert_called_once_with(True)

    entity.async_schedule_update_ha_state.reset_mock()
    entity._on_runtime_update(FakeParamUpdate(pool="P9", chan="v", idx=1))
    entity.async_schedule_update_ha_state.assert_not_called()

    entity.async_schedule_update_ha_state.reset_mock()
    entity._on_connectivity("OTHER", False)
    entity.async_schedule_update_ha_state.assert_not_called()
    entity._on_connectivity("DEV1", False, online_changed=False)
    entity.async_schedule_update_ha_state.assert_not_called()
    entity._on_connectivity("DEV1", False)
    entity.async_schedule_update_ha_state.assert_called_once_with(True)

    bare = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    await bare.async_will_remove_from_hass()
    assert bare._unsubscribe_connectivity is None
