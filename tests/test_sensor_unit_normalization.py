"""Tests for sensor unit normalization."""

from __future__ import annotations

from custom_components.habragerone.sensor import BragerSymbolSensor


def test_normalize_unit_rejects_symbolic_tokens() -> None:
    assert BragerSymbolSensor._normalize_unit("wn.9998") is None
    assert BragerSymbolSensor._normalize_unit("units.101") is None
    assert BragerSymbolSensor._normalize_unit("app.one.boilerStatus.1") is None


def test_normalize_unit_rejects_named_custom_unit_tokens() -> None:
    """Named SPA units must not become HA unit_of_measurement (breaks text STATUS)."""
    assert BragerSymbolSensor._normalize_unit("BOILER_STATE") is None
    assert BragerSymbolSensor._normalize_unit("DEVICE_STATE") is None
    assert BragerSymbolSensor._normalize_unit("PUMP_STATE") is None
    assert BragerSymbolSensor._normalize_unit("THREE_WAY_VALVE_STATE") is None


def test_normalize_unit_keeps_real_units() -> None:
    assert BragerSymbolSensor._normalize_unit("°C") == "°C"
    assert BragerSymbolSensor._normalize_unit("%") == "%"
