"""Tests for dynamic unit-based sensor value resolution."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)

from custom_components.habragerone.sensor import BragerSymbolSensor


def test_sensor_marks_dynamic_unit_channel_for_resolver_path() -> None:
    runtime = SimpleNamespace(
        store=SimpleNamespace(),
        add_listener=lambda _cb: None,
        async_resolve_symbol_value=AsyncMock(return_value=33.3),
    )
    entry = SimpleNamespace(entry_id="entry-1")
    descriptor = {
        "symbol": "PARAM16_2",
        "devid": "MOD1",
        "label": "Maksymalna moc palnika",
        "pool": "P10",
        "chan": "v",
        "idx": 2,
        "unit": None,
        "mapping": {
            "channels": {
                "value": [{"address": "P10.v2"}],
                "unit": [{"address": "P10.u2"}],
            }
        },
    }

    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)

    assert entity._requires_resolver_value is True


def test_sensor_normalizes_common_units_to_ha_constants() -> None:
    assert BragerSymbolSensor._normalize_unit("kWh") == UnitOfEnergy.KILO_WATT_HOUR
    assert BragerSymbolSensor._normalize_unit("Wh") == UnitOfEnergy.WATT_HOUR
    assert BragerSymbolSensor._normalize_unit("kW") == UnitOfPower.KILO_WATT
    assert BragerSymbolSensor._normalize_unit("°C") == UnitOfTemperature.CELSIUS
    assert BragerSymbolSensor._normalize_unit("%") == PERCENTAGE
    assert BragerSymbolSensor._normalize_unit("l/min") == UnitOfVolumeFlowRate.LITERS_PER_MINUTE
    assert BragerSymbolSensor._normalize_unit({"pl": "°C", "en": "C"}) == UnitOfTemperature.CELSIUS
    assert BragerSymbolSensor._normalize_unit("wn.9998") is None


def test_sensor_infers_energy_and_power_classes_from_unit() -> None:
    energy_class, energy_state = BragerSymbolSensor._infer_sensor_classes(UnitOfEnergy.KILO_WATT_HOUR)
    assert energy_class == SensorDeviceClass.ENERGY
    assert energy_state == SensorStateClass.TOTAL_INCREASING

    power_class, power_state = BragerSymbolSensor._infer_sensor_classes(UnitOfPower.KILO_WATT)
    assert power_class == SensorDeviceClass.POWER
    assert power_state == SensorStateClass.MEASUREMENT

    temp_class, temp_state = BragerSymbolSensor._infer_sensor_classes(UnitOfTemperature.CELSIUS)
    assert temp_class == SensorDeviceClass.TEMPERATURE
    assert temp_state == SensorStateClass.MEASUREMENT

    flow_class, flow_state = BragerSymbolSensor._infer_sensor_classes(UnitOfVolumeFlowRate.LITERS_PER_MINUTE)
    assert flow_class == SensorDeviceClass.VOLUME_FLOW_RATE
    assert flow_state == SensorStateClass.MEASUREMENT

    pct_class, pct_state = BragerSymbolSensor._infer_sensor_classes(PERCENTAGE)
    assert pct_class is None
    assert pct_state == SensorStateClass.MEASUREMENT


def test_sensor_entity_applies_classes_from_descriptor_unit() -> None:
    runtime = SimpleNamespace(
        store=SimpleNamespace(),
        add_listener=lambda _cb: None,
        add_connectivity_listener=lambda _cb: None,
    )
    entry = SimpleNamespace(entry_id="entry-1")
    descriptor = {
        "symbol": "TEMP1",
        "devid": "MOD1",
        "label": "Boiler temp",
        "pool": "P1",
        "chan": "v",
        "idx": 0,
        "unit": "°C",
        "mapping": {},
    }

    entity = BragerSymbolSensor(entry=entry, runtime=runtime, descriptor=descriptor)

    assert entity._attr_native_unit_of_measurement == UnitOfTemperature.CELSIUS
    assert entity._attr_device_class == SensorDeviceClass.TEMPERATURE
    assert entity._attr_state_class == SensorStateClass.MEASUREMENT
