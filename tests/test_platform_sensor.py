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
    assert stats == {"descriptor_count": 2, "created_count": 2, "supplemental_count": 0}


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
    assert entity._attr_entity_registry_enabled_default is True
    assert entity.device_info["identifiers"] == {(DOMAIN, "DEV1")}


@pytest.mark.asyncio
async def test_sensor_respects_enabled_by_default_false(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = sensor_descriptor(symbol="TEMP_HIDDEN")
    descriptor["enabled_by_default"] = False
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)

    assert entity._attr_entity_registry_enabled_default is False


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
        peek_status_label=lambda _symbol: None,
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
async def test_status_sensor_ignores_boiler_state_map_on_pool_register(hass: HomeAssistant) -> None:
    """STATUS_P5_0 must not map P5.s0 through BOILER_STATE (1=Czyszczenie, 2=Rozpalanie)."""
    store = FakeStore(flat_values={"P5.s0": 1})
    resolve_status = AsyncMock(return_value="Praca")
    runtime = SimpleNamespace(
        store=store,
        add_listener=lambda _cb: lambda: None,
        module_online=lambda _devid: True,
        cloud_session_up=True,
        live_push_healthy=True,
        async_resolve_status_label=resolve_status,
        peek_status_label=lambda _symbol: None,
        route_visible_for_symbol=lambda *_a, **_k: True,
    )
    descriptor = sensor_descriptor(
        symbol="STATUS_P5_0",
        pool="P5",
        chan="s",
        idx=0,
        unit=None,
        raw_to_label={
            "0": "Stop",
            "1": "Czyszczenie",
            "2": "Rozpalanie",
            "11": "Praca",
        },
        command_rules=[
            {
                "kind": "elseif",
                "logic": "any",
                "value": "WORK",
                "conditions": [{"operation": "equalTo", "expected": 1, "targets": [{"address": "P5.s0"}]}],
            }
        ],
    )
    descriptor["unit_code"] = "BOILER_STATE"
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)  # type: ignore[arg-type]
    entity.hass = hass
    entity.entity_id = "sensor.status_kotla"

    await entity.async_update()

    assert entity.native_value == "praca"
    resolve_status.assert_awaited_once_with("STATUS_P5_0")


@pytest.mark.asyncio
async def test_status_sensor_maps_resolved_raw_code_via_unit_table(hass: HomeAssistant) -> None:
    """Resolver may return BOILER_STATE code 11; map it via raw_to_label, not P5.s0."""
    store = FakeStore(flat_values={"P5.s0": 1})
    resolve_status = AsyncMock(return_value=11)
    runtime = SimpleNamespace(
        store=store,
        add_listener=lambda _cb: lambda: None,
        module_online=lambda _devid: True,
        cloud_session_up=True,
        live_push_healthy=True,
        async_resolve_status_label=resolve_status,
        peek_status_label=lambda _symbol: None,
        route_visible_for_symbol=lambda *_a, **_k: True,
    )
    descriptor = sensor_descriptor(
        symbol="STATUS_P5_0",
        pool="P5",
        chan="s",
        idx=0,
        unit=None,
        raw_to_label={"1": "Czyszczenie", "2": "Rozpalanie", "11": "Praca"},
    )
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)  # type: ignore[arg-type]
    entity.hass = hass
    entity.entity_id = "sensor.status_kotla_code"

    await entity.async_update()

    assert entity.native_value == "praca"
    resolve_status.assert_awaited_once_with("STATUS_P5_0")


@pytest.mark.asyncio
async def test_status_sensor_falls_back_to_rules_when_resolver_misses(hass: HomeAssistant) -> None:
    store = FakeStore(flat_values={"P5.s0": 1})
    resolve_status = AsyncMock(return_value=None)
    runtime = SimpleNamespace(
        store=store,
        add_listener=lambda _cb: lambda: None,
        module_online=lambda _devid: True,
        cloud_session_up=True,
        live_push_healthy=True,
        async_resolve_status_label=resolve_status,
        peek_status_label=lambda _symbol: None,
        route_visible_for_symbol=lambda *_a, **_k: True,
    )
    descriptor = sensor_descriptor(
        symbol="STATUS_P5_0",
        pool="P5",
        chan="s",
        idx=0,
        unit=None,
        raw_to_label={"1": "Czyszczenie", "11": "Praca"},
        command_rules=[{"logic": "on", "value": "Podtrzymanie", "conditions": []}],
    )
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)  # type: ignore[arg-type]
    entity.hass = hass
    entity.entity_id = "sensor.status_kotla_rules"

    await entity.async_update()

    assert entity.native_value == "podtrzymanie"
    resolve_status.assert_awaited_once_with("STATUS_P5_0")


@pytest.mark.asyncio
async def test_status_sensor_keeps_raw_pool_when_resolver_and_rules_miss(hass: HomeAssistant) -> None:
    store = FakeStore(flat_values={"P5.s0": 1})
    resolve_status = AsyncMock(return_value=None)
    runtime = SimpleNamespace(
        store=store,
        add_listener=lambda _cb: lambda: None,
        module_online=lambda _devid: True,
        cloud_session_up=True,
        live_push_healthy=True,
        async_resolve_status_label=resolve_status,
        peek_status_label=lambda _symbol: None,
        route_visible_for_symbol=lambda *_a, **_k: True,
    )
    descriptor = sensor_descriptor(
        symbol="STATUS_P5_0",
        pool="P5",
        chan="s",
        idx=0,
        unit=None,
        raw_to_label={"1": "Czyszczenie", "2": "Rozpalanie"},
        command_rules=[],
    )
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)  # type: ignore[arg-type]
    entity.hass = hass
    entity.entity_id = "sensor.status_kotla_raw"

    await entity.async_update()

    # Must not become "czyszczenie" via BOILER_STATE map of the pool register.
    assert entity.native_value == 1
    resolve_status.assert_awaited_once_with("STATUS_P5_0")


@pytest.mark.asyncio
async def test_status_sensor_update_returns_when_resolver_misses_without_raw(hass: HomeAssistant) -> None:
    store = FakeStore(flat_values={})
    resolve_status = AsyncMock(return_value=None)
    runtime = SimpleNamespace(
        store=store,
        add_listener=lambda _cb: lambda: None,
        module_online=lambda _devid: True,
        cloud_session_up=True,
        live_push_healthy=True,
        async_resolve_status_label=resolve_status,
        peek_status_label=lambda _symbol: None,
        route_visible_for_symbol=lambda *_a, **_k: True,
    )
    descriptor = sensor_descriptor(symbol="STATUS_P5_0", pool="P5", chan="s", idx=0, unit=None)
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)  # type: ignore[arg-type]
    entity.hass = hass
    entity.entity_id = "sensor.status_kotla_empty"
    entity._attr_native_value = "stale"

    await entity.async_update()

    assert entity.native_value == "stale"
    resolve_status.assert_awaited_once_with("STATUS_P5_0")


@pytest.mark.asyncio
async def test_status_sensor_update_uses_peek_for_availability_without_raw(hass: HomeAssistant) -> None:
    store = FakeStore(flat_values={})
    resolve_status = AsyncMock(return_value="Praca")
    runtime = SimpleNamespace(
        store=store,
        add_listener=lambda _cb: lambda: None,
        module_online=lambda _devid: True,
        cloud_session_up=True,
        live_push_healthy=True,
        async_resolve_status_label=resolve_status,
        peek_status_label=lambda _symbol: "Praca",
        route_visible_for_symbol=lambda *_a, **_k: True,
    )
    descriptor = sensor_descriptor(symbol="STATUS_P5_0", pool="P5", chan="s", idx=0, unit=None)
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)  # type: ignore[arg-type]
    entity.hass = hass
    entity.entity_id = "sensor.status_kotla_peek"

    await entity.async_update()

    assert entity.native_value == "praca"
    assert entity.available is True


@pytest.mark.asyncio
async def test_status_sensor_initial_sync_uses_rules_without_cache(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P5.s0": 1})
    descriptor = sensor_descriptor(
        symbol="STATUS_P5_0",
        pool="P5",
        chan="s",
        idx=0,
        unit=None,
        raw_to_label={"1": "Czyszczenie", "11": "Praca"},
        command_rules=[{"logic": "on", "value": 11, "conditions": []}],
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "sensor.status_kotla_rule_sync"
    entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]

    await entity.async_added_to_hass()

    assert entity.native_value == "praca"
    entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_status_sensor_initial_sync_skips_misleading_unit_map(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P5.s0": 2})
    runtime._status_label_cache["STATUS_P5_0"] = "Podtrzymanie"
    descriptor = sensor_descriptor(
        symbol="STATUS_P5_0",
        pool="P5",
        chan="s",
        idx=0,
        unit=None,
        raw_to_label={"1": "Czyszczenie", "2": "Rozpalanie", "5": "Podtrzymanie"},
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "sensor.status_kotla_sync"
    entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]

    await entity.async_added_to_hass()

    assert entity.native_value == "podtrzymanie"
    entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_sensor_added_to_hass_uses_prewarmed_status_label(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P5.s5": 768})
    runtime._status_label_cache["STATUS_BOILER"] = "Work"
    descriptor = sensor_descriptor(symbol="STATUS_BOILER", pool="P5", chan="s", idx=5, unit=None)
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "sensor.test_status"
    entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]

    await entity.async_added_to_hass()

    entity.async_write_ha_state.assert_called_once()
    entity.async_schedule_update_ha_state.assert_not_called()
    assert entity.native_value == "work"


@pytest.mark.asyncio
async def test_sensor_initial_sync_uses_raw_to_label_map(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P6.v0": 2})
    descriptor = sensor_descriptor(raw_to_label={"2": "Eco"})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "sensor.test_mode"
    entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]

    await entity.async_added_to_hass()

    entity.async_write_ha_state.assert_called_once()
    entity.async_schedule_update_ha_state.assert_not_called()
    assert entity.native_value == "eco"


@pytest.mark.asyncio
async def test_sensor_initial_sync_uses_rule_display_value(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P5.s11": 1})
    descriptor = sensor_descriptor(
        symbol="STATUS_P5_11",
        pool="P5",
        chan="s",
        idx=11,
        unit=None,
        command_rules=[{"logic": "on", "value": "On", "conditions": []}],
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "sensor.test_rule"
    entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]

    await entity.async_added_to_hass()

    entity.async_write_ha_state.assert_called_once()
    entity.async_schedule_update_ha_state.assert_not_called()
    assert entity.native_value == "on"


@pytest.mark.asyncio
async def test_sensor_initial_sync_uses_cache_without_raw_value(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={})
    runtime._status_label_cache["STATUS_BOILER"] = "Work"
    descriptor = sensor_descriptor(symbol="STATUS_BOILER", pool="P5", chan="s", idx=5, unit=None)
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "sensor.test_status_cached"
    entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]

    await entity.async_added_to_hass()

    entity.async_write_ha_state.assert_called_once()
    entity.async_schedule_update_ha_state.assert_not_called()
    assert entity.native_value == "work"


@pytest.mark.asyncio
async def test_sensor_initial_sync_status_without_cache_schedules_update(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P5.s5": 1})
    descriptor = sensor_descriptor(symbol="STATUS_BOILER", pool="P5", chan="s", idx=5, unit=None)
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "sensor.test_status_pending"
    entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]

    await entity.async_added_to_hass()

    entity.async_write_ha_state.assert_not_called()
    entity.async_schedule_update_ha_state.assert_called_once()


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
async def test_sensor_dynamic_unit_resolver_returns_when_raw_missing(hass: HomeAssistant) -> None:
    store = FakeStore(flat_values={})
    resolve_with_unit = AsyncMock(return_value=(42.0, "%"))
    runtime = SimpleNamespace(
        store=store,
        add_listener=lambda _cb: lambda: None,
        module_online=lambda _devid: True,
        cloud_session_up=True,
        live_push_healthy=True,
        async_resolve_symbol_with_unit=resolve_with_unit,
        peek_status_label=lambda _symbol: None,
        route_visible_for_symbol=lambda *_a, **_k: True,
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
    entity.entity_id = "sensor.test_power_missing"
    entity._attr_native_value = "stale"

    await entity.async_update()

    assert entity.native_value == "stale"
    resolve_with_unit.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_sensor_initial_sync_returns_false_without_matching_rules(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P5.s0": 1})
    descriptor = sensor_descriptor(
        symbol="STATUS_P5_0",
        pool="P5",
        chan="s",
        idx=0,
        unit=None,
        raw_to_label={"1": "Czyszczenie"},
        command_rules=[
            {
                "kind": "elseif",
                "logic": "all",
                "value": "WORK",
                "conditions": [{"operation": "equalTo", "expected": 99, "targets": [{"address": "P5.s0"}]}],
            }
        ],
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "sensor.status_kotla_no_rule"
    entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]

    await entity.async_added_to_hass()

    # Sync path cannot resolve; falls through to async_update scheduling.
    entity.async_write_ha_state.assert_not_called()
    entity.async_schedule_update_ha_state.assert_called_once_with(True)


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
