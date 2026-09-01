"""Tests for BragerRuntime.async_write and command-rule helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.runtime import (  # noqa: E402
    BragerRuntime,
    _compare_condition,
    _read_target_actual,
    _rule_command_name,
    _select_command_rule,
    _select_intent_command_rule,
)
from tests.helpers.descriptors import command_rule_descriptor, writable_parameter_descriptor  # noqa: E402
from tests.helpers.fakes import FakeApi, make_runtime  # noqa: E402


@pytest.mark.asyncio
async def test_async_write_missing_devid_raises() -> None:
    runtime, _api, _gateway, _store = make_runtime()
    descriptor = writable_parameter_descriptor(devid="")
    with pytest.raises(HomeAssistantError, match="Missing device id"):
        await runtime.async_write(descriptor=descriptor, input_display_value=1)


@pytest.mark.asyncio
async def test_async_write_maps_write_validation_error_to_home_assistant_error() -> None:
    runtime, _api, _gateway, _store = make_runtime()
    descriptor = writable_parameter_descriptor(raw_min=0, raw_max=5)
    with pytest.raises(HomeAssistantError, match="exceeds maximum"):
        await runtime.async_write(descriptor=descriptor, input_display_value=99)


@pytest.mark.asyncio
async def test_async_write_parameter_route_failure_raises() -> None:
    runtime, _api, _gateway, _store = make_runtime(api=FakeApi(succeed=False))
    descriptor = writable_parameter_descriptor()
    with pytest.raises(HomeAssistantError, match="parameter route"):
        await runtime.async_write(descriptor=descriptor, input_display_value=42)


@pytest.mark.asyncio
async def test_async_write_raw_command_failure_raises() -> None:
    runtime, _api, _gateway, _store = make_runtime(api=FakeApi(succeed=False))
    descriptor = command_rule_descriptor(
        command_rules=[{"command": "BOILER_START", "value": "ON"}],
    )
    with pytest.raises(HomeAssistantError, match="raw command route"):
        await runtime.async_write(descriptor=descriptor, input_display_value=True)


@pytest.mark.asyncio
async def test_async_write_ignores_boolean_min_max_bounds() -> None:
    runtime, api, _gateway, _store = make_runtime()
    descriptor = writable_parameter_descriptor()
    descriptor["min"] = False
    descriptor["max"] = True
    await runtime.async_write(descriptor=descriptor, input_display_value=42)
    assert api.calls[0]["value"] == 42


@pytest.mark.asyncio
async def test_async_write_applies_inverse_numeric_transform() -> None:
    runtime, api, _gateway, _store = make_runtime()
    descriptor = writable_parameter_descriptor(raw_min=0, raw_max=400)
    descriptor.update({"transform_scale": 0.1, "transform_offset": 0.0})
    await runtime.async_write(descriptor=descriptor, input_display_value=33.3)
    assert api.calls[0]["value"] == 333


@pytest.mark.asyncio
async def test_async_write_schedules_activity_refresh() -> None:
    """Successful writes refresh the activity feed (SPA logs parameter changes)."""
    api = FakeApi()
    api.modules_activity = AsyncMock(return_value=(200, {"activities": []}))  # type: ignore[attr-defined]
    runtime, *_rest = make_runtime(api=api)
    refresh = AsyncMock()
    with patch.object(BragerRuntime, "async_refresh_activity", refresh):
        descriptor = writable_parameter_descriptor()
        await runtime.async_write(descriptor=descriptor, input_display_value=42)
        await asyncio.sleep(0)
        refresh.assert_awaited_once_with("DEV1")


@pytest.mark.asyncio
async def test_async_write_fallback_raw_command_route_schedules_activity_refresh() -> None:
    """Cover the final raw-command branch (after parameter/intent routes are skipped)."""
    api = FakeApi()
    api.modules_activity = AsyncMock(return_value=(200, {"activities": []}))  # type: ignore[attr-defined]
    runtime, *_rest = make_runtime(api=api)
    refresh = AsyncMock()
    descriptor = {
        "symbol": "SYNC",
        "devid": "DEV1",
        "mapping": {
            "command_rules": [
                {"command": "void 0", "value": "MISS"},
                {"command": "DO_SYNC", "value": "GO"},
            ]
        },
    }
    with patch.object(BragerRuntime, "async_refresh_activity", refresh):
        await runtime.async_write(descriptor=descriptor, input_display_value="GO")
        await asyncio.sleep(0)
        refresh.assert_awaited_once_with("DEV1")


def test_schedule_activity_refresh_without_running_loop() -> None:
    """No running loop must not raise when scheduling post-write activity refresh."""
    api = FakeApi()
    api.modules_activity = AsyncMock(return_value=(200, {"activities": []}))  # type: ignore[attr-defined]
    runtime, *_rest = make_runtime(api=api)
    runtime._schedule_activity_refresh_after_write("DEV1")


def test_read_target_actual_accepts_integer_floats() -> None:
    assert (
        _read_target_actual(
            {"address": "P5.s0", "bit": 0},
            flat_values={"P5.s0": 64.0},
            devid="DEV1",
            modules_meta={},
        )
        == 0
    )
    assert (
        _read_target_actual(
            {"address": "P5.s0", "bit": 0},
            flat_values={"P5.s0": 65.0},
            devid="DEV1",
            modules_meta={},
        )
        == 1
    )
    assert (
        _read_target_actual(
            {"address": "P5.s0", "bit": 0},
            flat_values={"P5.s0": True},
            devid="DEV1",
            modules_meta={},
        )
        is True
    )
    assert (
        _read_target_actual(
            {"address": "P5.s0", "bit": 0},
            flat_values={"P5.s0": 1.5},
            devid="DEV1",
            modules_meta={},
        )
        == 1.5
    )


@pytest.mark.asyncio
async def test_async_write_applies_enum_mapping() -> None:
    runtime, api, _gateway, _store = make_runtime()
    descriptor = writable_parameter_descriptor()
    await runtime.async_write(
        descriptor=descriptor,
        input_display_value="Eco",
        enum_mapping={"Eco": 2, "Comfort": 3},
    )
    assert api.calls[0]["value"] == 2


@pytest.mark.asyncio
async def test_async_write_uses_group_target_address() -> None:
    runtime, api, _gateway, _store = make_runtime(flat_values={"P7.s3": 0})
    descriptor = command_rule_descriptor(
        command_rules=[
            {
                "conditions": [
                    {
                        "operation": "equalTo",
                        "expected": 0,
                        "targets": [{"group": "P7", "use": "s", "number": 3}],
                    }
                ],
                "command": "RELAY_ON",
                "value": "ON",
            }
        ],
    )
    await runtime.async_write(descriptor=descriptor, input_display_value=True)
    assert api.calls[0]["command"] == "RELAY_ON"


@pytest.mark.asyncio
async def test_async_write_uses_connected_at_store_getter() -> None:
    runtime, api, _gateway, _store = make_runtime(
        flat_values={},
        modules_meta={"DEV1": {"connectedAt": "2026-04-06T10:00:00Z"}},
    )
    descriptor = command_rule_descriptor(
        command_rules=[
            {
                "conditions": [
                    {
                        "operation": "equalTo",
                        "expected": "2026-04-06T10:00:00Z",
                        "targets": [{"storeGetter": "modules.connectedAt"}],
                    }
                ],
                "command": "SYNC_OK",
                "value": "OK",
            }
        ],
    )
    await runtime.async_write(descriptor=descriptor, input_display_value=True)
    assert api.calls[0]["command"] == "SYNC_OK"


def test_rule_command_name_rejects_void() -> None:
    assert _rule_command_name({"command": "void 0"}) is None
    assert _rule_command_name({"command": " BOILER_START "}) == "BOILER_START"


def test_select_command_rule_matches_bool_logic() -> None:
    rules = [
        {"logic": "on", "command": "START", "value": "ON"},
        {"logic": "off", "command": "STOP", "value": "OFF"},
    ]
    assert _rule_command_name(_select_command_rule(command_rules=rules, desired_value=True)) == "START"
    assert _rule_command_name(_select_command_rule(command_rules=rules, desired_value=False)) == "STOP"


def test_select_intent_command_rule_prefers_logic_tags() -> None:
    rules = [
        {"logic": "on", "command": "BOILER_START", "value": "ON"},
        {"logic": "off", "command": "BOILER_STOP", "value": "OFF"},
    ]
    picked = _select_intent_command_rule(command_rules=rules, desired_value=False)
    assert _rule_command_name(picked) == "BOILER_STOP"


def test_compare_condition_supports_not_equal() -> None:
    assert _compare_condition(operation="notEqualTo", actual=1, expected=0) is True
    assert _compare_condition(operation="equalTo", actual=1, expected=1) is True
    assert _compare_condition(operation="unknown.op", actual=1, expected=1) is False


def test_read_target_actual_extracts_bit_from_address() -> None:
    actual = _read_target_actual(
        {"address": "P5.s0", "bit": 1},
        flat_values={"P5.s0": 0b10},
        devid="DEV1",
        modules_meta={},
    )
    assert actual == 1
