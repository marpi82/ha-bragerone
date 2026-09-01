"""Tests for the switch platform and BragerSymbolSwitch entity."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.const import DATA_ENTITY_STATS, DATA_RUNTIME, DOMAIN  # noqa: E402
from custom_components.habragerone.switch import (  # noqa: E402
    BragerSymbolSwitch,
    async_setup_entry,
)
from tests.helpers.descriptors import (  # noqa: E402
    command_rule_descriptor,
    switch_descriptor,
    writable_parameter_descriptor,
)
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
        (64, False),
    ],
)
def test_coerce_status_bool_via_resolve_entity(raw: Any, expected: bool) -> None:
    from custom_components.habragerone.status_rules import coerce_status_bool

    assert coerce_status_bool(raw) is expected


@pytest.mark.asyncio
async def test_async_setup_entry_registers_entities_and_stats(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P5.s0": 1})
    descriptors = [
        switch_descriptor(symbol="SW1"),
        switch_descriptor(symbol="SW2", idx=1),
        writable_parameter_descriptor(symbol="NUM_ONLY"),
    ]
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors)
    added: list[BragerSymbolSwitch] = []
    await async_setup_entry(hass, entry, added.extend)

    assert len(added) == 2
    assert {entity._symbol for entity in added} == {"SW1", "SW2"}
    stats = hass.data[DOMAIN][entry.entry_id][DATA_ENTITY_STATS]["switch"]
    assert stats == {"descriptor_count": 2, "created_count": 2, "supplemental_count": 0}


@pytest.mark.asyncio
async def test_async_setup_entry_noop_when_runtime_missing(hass: HomeAssistant) -> None:
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[switch_descriptor()])
    hass.data[DOMAIN][entry.entry_id].pop(DATA_RUNTIME)
    added: list[BragerSymbolSwitch] = []
    await async_setup_entry(hass, entry, added.extend)

    assert added == []


@pytest.mark.asyncio
async def test_switch_entity_identity_and_device_info(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = command_rule_descriptor(
        platform="switch",
        label="Boiler run",
        panel_path="Menu/Boiler",
        module_name="boiler_module",
        command_rules=[{"command": "BOILER_START", "value": "ON"}],
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSwitch(entry=entry, runtime=runtime, descriptor=descriptor)

    assert entity._attr_name == "Boiler - Boiler run"
    assert entity._attr_suggested_object_id == "dev1_uruchomienie_kotla"
    assert entity._attr_unique_id == f"{entry.entry_id}_dev1_uruchomienie_kotla_switch"
    assert entity._attr_entity_registry_enabled_default is True
    assert entity.device_info["identifiers"] == {(DOMAIN, "DEV1")}


@pytest.mark.asyncio
async def test_switch_listener_lifecycle_and_state_refresh(hass: HomeAssistant) -> None:
    runtime, _api, _gateway, _store = make_runtime(flat_values={"P5.s0": 1})
    descriptor = switch_descriptor()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSwitch(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "switch.test_switch"

    await entity.async_added_to_hass()
    assert callable(entity._unsubscribe_listener)

    await entity.async_update()
    assert entity.is_on is True
    assert entity.available is True

    entity._attr_available = True
    entity._attr_is_on = True
    entity._runtime.store._flat.clear()
    await entity.async_update()
    assert entity.available is False

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_listener is None


@pytest.mark.asyncio
async def test_switch_bit_rule_reads_off_for_nonzero_status_word(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P5.s0": 64})
    descriptor = command_rule_descriptor(
        platform="switch",
        command_rules=[
            {
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
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSwitch(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "switch.test_boiler"

    await entity.async_update()
    assert entity.is_on is False

    entity._runtime.store._flat["P5.s0"] = 65
    await entity.async_update()
    assert entity.is_on is True


@pytest.mark.asyncio
async def test_switch_turn_on_off_dispatch_writes(hass: HomeAssistant) -> None:
    runtime, api, _gateway, _store = make_runtime()
    descriptor = command_rule_descriptor(
        platform="switch",
        command_rules=[
            {"logic": "on", "command": "BOILER_START", "value": "ON"},
            {"logic": "off", "command": "BOILER_STOP", "value": "OFF"},
        ],
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSwitch(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "switch.test_switch"
    await entity.async_added_to_hass()

    await entity.async_turn_on()
    await entity.async_turn_off()

    assert len(api.calls) == 2
    assert entity.is_on is False


@pytest.mark.asyncio
async def test_switch_runtime_update_schedules_refresh_for_matching_key(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = switch_descriptor(pool="P5", chan="s", idx=0)
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSwitch(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "switch.test_switch"
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
    entity._on_connectivity("DEV1", False)
    entity.async_schedule_update_ha_state.assert_called_once_with(True)

    bare = BragerSymbolSwitch(entry=entry, runtime=runtime, descriptor=descriptor)
    await bare.async_will_remove_from_hass()
    assert bare._unsubscribe_connectivity is None
