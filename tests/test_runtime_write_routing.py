"""Runtime write routing tests (raw command vs parameter path)."""

from __future__ import annotations

import pytest

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from tests.helpers.descriptors import command_rule_descriptor  # noqa: E402
from tests.helpers.fakes import make_runtime  # noqa: E402


@pytest.mark.asyncio
async def test_async_write_prefers_raw_command_rule_over_parameter_address() -> None:
    runtime, api, _gateway, _store = make_runtime(flat_values={"P5.s0": 0})
    descriptor = command_rule_descriptor(
        command_rules=[
            {
                "operation": "ignored",
                "conditions": [{"operation": "equalTo", "expected": 0, "targets": [{"address": "P5.s0", "bit": 0}]}],
                "command": "BOILER_START",
                "value": "OFF",
            },
            {
                "conditions": [{"operation": "equalTo", "expected": 1, "targets": [{"address": "P5.s0", "bit": 0}]}],
                "command": "BOILER_STOP",
                "value": "ON",
            },
        ],
    )

    await runtime.async_write(descriptor=descriptor, input_display_value=True)

    assert len(api.calls) == 1
    assert api.calls[0]["command"] == "BOILER_START"
    assert api.calls[0]["value"] == "OFF"
    assert "pool" not in api.calls[0]
    assert "parameter" not in api.calls[0]


@pytest.mark.asyncio
async def test_async_write_uses_descriptor_address_when_rule_conditions_have_no_targets() -> None:
    runtime, api, _gateway, _store = make_runtime(flat_values={"P5.s0": 1})
    descriptor = command_rule_descriptor(
        command_rules=[
            {"conditions": [{"operation": "equalTo", "expected": 0}], "command": "BOILER_START", "value": "OFF"},
            {"conditions": [{"operation": "equalTo", "expected": 1}], "command": "BOILER_STOP", "value": "ON"},
            {"conditions": [], "command": "void 0"},
        ],
    )

    await runtime.async_write(descriptor=descriptor, input_display_value=False)

    assert len(api.calls) == 1
    assert api.calls[0]["command"] == "BOILER_STOP"
    assert api.calls[0]["value"] == "ON"


@pytest.mark.asyncio
async def test_async_write_prefers_intent_rule_for_start_stop_commands() -> None:
    runtime, api, _gateway, _store = make_runtime(flat_values={"P5.s0": 0})
    descriptor = command_rule_descriptor(
        command_rules=[
            {"conditions": [{"operation": "equalTo", "expected": 0}], "command": "BOILER_START", "value": "OFF"},
            {"conditions": [{"operation": "equalTo", "expected": 1}], "command": "BOILER_STOP", "value": "ON"},
        ],
    )

    await runtime.async_write(descriptor=descriptor, input_display_value=False)

    assert len(api.calls) == 1
    assert api.calls[0]["command"] == "BOILER_STOP"
