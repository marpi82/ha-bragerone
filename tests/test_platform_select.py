"""Tests for the select platform and BragerSymbolSelect entity."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.const import DATA_ENTITY_STATS, DATA_RUNTIME, DOMAIN  # noqa: E402
from custom_components.habragerone.select import BragerSymbolSelect, async_setup_entry  # noqa: E402
from tests.helpers.descriptors import select_descriptor, switch_descriptor  # noqa: E402
from tests.helpers.fakes import FakeParamUpdate, make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


@pytest.mark.asyncio
async def test_async_setup_entry_registers_entities_and_stats(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P6.v0": 2})
    descriptors = [select_descriptor(symbol="SEL1"), select_descriptor(symbol="SEL2", idx=1), switch_descriptor()]
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors)
    added: list[BragerSymbolSelect] = []
    await async_setup_entry(hass, entry, added.extend)

    assert len(added) == 2
    assert {entity._symbol for entity in added} == {"SEL1", "SEL2"}
    stats = hass.data[DOMAIN][entry.entry_id][DATA_ENTITY_STATS]["select"]
    assert stats == {"descriptor_count": 2, "created_count": 2}


@pytest.mark.asyncio
async def test_async_setup_entry_noop_when_runtime_missing(hass: HomeAssistant) -> None:
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[select_descriptor()])
    hass.data[DOMAIN][entry.entry_id].pop(DATA_RUNTIME)
    added: list[BragerSymbolSelect] = []
    await async_setup_entry(hass, entry, added.extend)

    assert added == []


@pytest.mark.asyncio
async def test_select_entity_identity_and_device_info(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = select_descriptor(symbol="MODE")
    descriptor["panel_path"] = "Settings/Mode"
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSelect(entry=entry, runtime=runtime, descriptor=descriptor)

    assert entity._attr_name == "Settings/Mode - Operating mode"
    assert entity._attr_unique_id == f"{entry.entry_id}_dev1_mode_select"
    assert entity._attr_options == ["Eco", "Comfort"]
    assert entity.device_info["identifiers"] == {(DOMAIN, "DEV1")}


@pytest.mark.asyncio
async def test_select_listener_lifecycle_and_state_refresh(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(flat_values={"P6.v0": 3})
    descriptor = select_descriptor()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSelect(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "select.test_mode"

    await entity.async_added_to_hass()
    assert callable(entity._unsubscribe_listener)

    await entity.async_update()
    assert entity.current_option == "Comfort"
    assert entity.available is True

    entity._runtime.store._flat.clear()
    await entity.async_update()
    assert entity.available is False

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_listener is None


@pytest.mark.asyncio
async def test_select_option_dispatches_enum_mapped_write(hass: HomeAssistant) -> None:
    runtime, api, _gateway, _store = make_runtime()
    descriptor = select_descriptor()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSelect(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "select.test_mode"
    await entity.async_added_to_hass()

    await entity.async_select_option("Eco")

    assert entity.current_option == "Eco"
    assert len(api.calls) == 1
    assert api.calls[0]["value"] == 2


@pytest.mark.asyncio
async def test_select_runtime_update_schedules_refresh_for_matching_key(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = select_descriptor(pool="P6", chan="v", idx=0)
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerSymbolSelect(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "select.test_mode"
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]
    await entity.async_added_to_hass()
    entity.async_schedule_update_ha_state.reset_mock()

    entity._on_runtime_update(FakeParamUpdate(pool="P6", chan="v", idx=0))
    entity.async_schedule_update_ha_state.assert_called_once_with(True)

    entity.async_schedule_update_ha_state.reset_mock()
    entity._on_runtime_update(FakeParamUpdate(pool="P1", chan="s", idx=9))
    entity.async_schedule_update_ha_state.assert_not_called()

    entity.async_schedule_update_ha_state.reset_mock()
    entity._on_connectivity("OTHER", False)
    entity.async_schedule_update_ha_state.assert_not_called()
    entity._on_connectivity("DEV1", False)
    entity.async_schedule_update_ha_state.assert_called_once_with(True)

    bare = BragerSymbolSelect(entry=entry, runtime=runtime, descriptor=descriptor)
    await bare.async_will_remove_from_hass()
    assert bare._unsubscribe_connectivity is None
