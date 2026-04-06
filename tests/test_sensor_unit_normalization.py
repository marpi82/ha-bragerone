"""Tests for sensor unit normalization."""

from __future__ import annotations

from custom_components.habragerone.sensor import BragerSymbolSensor


def test_normalize_unit_rejects_symbolic_tokens() -> None:
    assert BragerSymbolSensor._normalize_unit("wn.9998") is None
    assert BragerSymbolSensor._normalize_unit("units.101") is None
    assert BragerSymbolSensor._normalize_unit("app.one.boilerStatus.1") is None


def test_normalize_unit_keeps_real_units() -> None:
    assert BragerSymbolSensor._normalize_unit("°C") == "°C"
    assert BragerSymbolSensor._normalize_unit("%") == "%"
