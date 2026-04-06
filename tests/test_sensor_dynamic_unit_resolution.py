"""Tests for dynamic unit-based sensor value resolution."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

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
