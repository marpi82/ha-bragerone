"""Tests for the binary_sensor platform and BragerStatusBinarySensor entity."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.binary_sensor import (  # noqa: E402
    BragerStatusBinarySensor,
    _to_bool,
    async_setup_entry,
)
from custom_components.habragerone.const import DATA_ENTITY_STATS, DATA_RUNTIME, DOMAIN  # noqa: E402
from tests.helpers.descriptors import binary_sensor_descriptor, select_descriptor  # noqa: E402
from tests.helpers.fakes import FakeParamUpdate, make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        ("on", True),
        ("OFF", False),
        ("yes", True),
        ("disabled", False),
        ("maybe", False),
        (None, False),
    ],
)
def test_to_bool(raw: Any, expected: bool) -> None:
    assert _to_bool(raw) is expected


@pytest.mark.asyncio
async def test_async_setup_entry_registers_entities_and_stats(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P5.s0": 1})
    descriptors = [
        binary_sensor_descriptor(symbol="BIN1"),
        binary_sensor_descriptor(symbol="BIN2", idx=1),
        select_descriptor(),
    ]
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors)
    added: list[BragerStatusBinarySensor] = []
    await async_setup_entry(hass, entry, added.extend)

    assert len(added) == 2
    assert {entity._symbol for entity in added} == {"BIN1", "BIN2"}
    stats = hass.data[DOMAIN][entry.entry_id][DATA_ENTITY_STATS]["binary_sensor"]
    assert stats == {"descriptor_count": 2, "created_count": 2}


@pytest.mark.asyncio
async def test_async_setup_entry_noop_when_runtime_missing(hass: HomeAssistant) -> None:
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[binary_sensor_descriptor()])
    hass.data[DOMAIN][entry.entry_id].pop(DATA_RUNTIME)
    added: list[BragerStatusBinarySensor] = []
    await async_setup_entry(hass, entry, added.extend)

    assert added == []


@pytest.mark.asyncio
async def test_binary_sensor_entity_identity_and_device_info(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = binary_sensor_descriptor(symbol="PUMP_ON")
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerStatusBinarySensor(entry=entry, runtime=runtime, descriptor=descriptor)

    assert entity._attr_name == "Pump active"
    assert entity._attr_unique_id == f"{entry.entry_id}_dev1_pump_on_binary"
    assert entity.device_info["identifiers"] == {(DOMAIN, "DEV1")}


@pytest.mark.asyncio
async def test_binary_sensor_listener_lifecycle_and_raw_bool_state(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P5.s0": 1})
    descriptor = binary_sensor_descriptor()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerStatusBinarySensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "binary_sensor.test_flag"

    await entity.async_added_to_hass()
    assert callable(entity._unsubscribe_listener)

    await entity.async_update()
    assert entity.is_on is True
    assert entity.available is True

    entity._runtime.store._flat.clear()
    await entity.async_update()
    assert entity.available is False

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_listener is None


@pytest.mark.asyncio
async def test_binary_sensor_status_symbol_uses_resolver_label(hass: HomeAssistant) -> None:
    from unittest.mock import AsyncMock, patch

    from custom_components.habragerone.runtime import BragerRuntime

    runtime, *_rest = make_runtime(flat_values={"P5.s11": 64.0})
    descriptor = binary_sensor_descriptor(
        symbol="STATUS_P5_11",
        pool="P5",
        chan="s",
        idx=11,
        command_rules=[],  # empty cached rules — resolver is the source of truth
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerStatusBinarySensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "binary_sensor.pump_status"

    with patch.object(BragerRuntime, "async_resolve_status_label", new=AsyncMock(return_value="On")):
        await entity.async_update()
    assert entity.is_on is True

    with patch.object(BragerRuntime, "async_resolve_status_label", new=AsyncMock(return_value="Off")):
        await entity.async_update()
    assert entity.is_on is False

    with patch.object(
        BragerRuntime,
        "async_resolve_status_label",
        new=AsyncMock(return_value="Włączone (ręcznie)"),
    ):
        await entity.async_update()
    assert entity.is_on is True

    with patch.object(BragerRuntime, "async_resolve_status_label", new=AsyncMock(return_value="e.OFF_MANUAL")):
        await entity.async_update()
    assert entity.is_on is False


@pytest.mark.asyncio
async def test_binary_sensor_uses_rule_mapping_when_configured(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P5.s5": 768})
    descriptor = binary_sensor_descriptor(
        pool="P5",
        chan="s",
        idx=5,
        command_rules=[
            {
                "value": "On",
                "conditions": [{"operation": "equalTo", "expected": 768, "targets": [{"address": "P5.s5"}]}],
            }
        ],
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerStatusBinarySensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "binary_sensor.test_flag"

    await entity.async_update()

    assert entity.is_on is True


@pytest.mark.asyncio
async def test_binary_sensor_runtime_update_schedules_refresh_for_matching_key(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = binary_sensor_descriptor(pool="P5", chan="s", idx=0)
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerStatusBinarySensor(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "binary_sensor.test_flag"
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]
    await entity.async_added_to_hass()
    entity.async_schedule_update_ha_state.reset_mock()

    entity._on_runtime_update(FakeParamUpdate(pool="P5", chan="s", idx=0))
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

    bare = BragerStatusBinarySensor(entry=entry, runtime=runtime, descriptor=descriptor)
    await bare.async_will_remove_from_hass()
    assert bare._unsubscribe_connectivity is None
