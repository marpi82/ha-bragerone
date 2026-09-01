"""Tests for the button platform and BragerActionButton entity."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.button import BragerActionButton, async_setup_entry  # noqa: E402
from custom_components.habragerone.const import (  # noqa: E402
    CONF_ROUTE_VISIBILITY_NAME,
    CONF_ROUTE_VISIBILITY_PATH,
    CONF_UI_ROUTE_SYMBOL,
    DATA_ENTITY_STATS,
    DATA_RUNTIME,
    DOMAIN,
)
from tests.helpers.descriptors import button_descriptor, sensor_descriptor  # noqa: E402
from tests.helpers.fakes import make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


@pytest.mark.asyncio
async def test_async_setup_entry_registers_entities_and_stats(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptors = [
        button_descriptor(symbol="BTN1"),
        button_descriptor(symbol="BTN2"),
        sensor_descriptor(),
    ]
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors)
    added: list[BragerActionButton] = []
    await async_setup_entry(hass, entry, added.extend)

    assert len(added) == 2
    assert {entity._symbol for entity in added} == {"BTN1", "BTN2"}
    stats = hass.data[DOMAIN][entry.entry_id][DATA_ENTITY_STATS]["button"]
    assert stats == {"descriptor_count": 2, "created_count": 2}


@pytest.mark.asyncio
async def test_async_setup_entry_noop_when_runtime_missing(hass: HomeAssistant) -> None:
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[button_descriptor()])
    hass.data[DOMAIN][entry.entry_id].pop(DATA_RUNTIME)
    added: list[BragerActionButton] = []
    await async_setup_entry(hass, entry, added.extend)

    assert added == []


@pytest.mark.asyncio
async def test_button_entity_identity_and_device_info(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    descriptor = button_descriptor(symbol="RESET_ALARM")
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerActionButton(entry=entry, runtime=runtime, descriptor=descriptor)

    assert entity._attr_name == "Reset alarm"
    assert entity._attr_unique_id == f"{entry.entry_id}_dev1_reset_alarm_button"
    assert entity._attr_entity_registry_enabled_default is True
    assert entity.device_info["identifiers"] == {(DOMAIN, "DEV1")}


@pytest.mark.asyncio
async def test_button_press_dispatches_first_rule_value(hass: HomeAssistant) -> None:
    runtime, api, _gateway, _store = make_runtime()
    descriptor = button_descriptor(
        command_rules=[{"command": "RESET_ALARM", "value": True}],
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerActionButton(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "button.test_reset"

    await entity.async_press()

    assert len(api.calls) == 1
    assert api.calls[0]["command"] == "RESET_ALARM"


@pytest.mark.asyncio
async def test_button_connectivity_listener_lifecycle(hass: HomeAssistant) -> None:
    from unittest.mock import MagicMock

    runtime, *_rest = make_runtime()
    descriptor = button_descriptor(symbol="RESET_ALARM")
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerActionButton(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "button.test_reset"
    entity.async_schedule_update_ha_state = MagicMock()  # type: ignore[method-assign]

    await entity.async_added_to_hass()
    assert callable(entity._unsubscribe_connectivity)
    assert entity._unsubscribe_route_visibility is None
    await entity.async_update()
    assert entity.available is True

    entity.async_schedule_update_ha_state.reset_mock()
    entity._on_connectivity("OTHER", False)
    entity.async_schedule_update_ha_state.assert_not_called()
    entity._on_connectivity("DEV1", False)
    entity.async_schedule_update_ha_state.assert_called_once_with(True)

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_connectivity is None

    bare = BragerActionButton(entry=entry, runtime=runtime, descriptor=descriptor)
    await bare.async_will_remove_from_hass()
    assert bare._unsubscribe_connectivity is None


@pytest.mark.asyncio
async def test_button_press_defaults_value_when_rule_missing(hass: HomeAssistant) -> None:
    runtime, api, _gateway, _store = make_runtime()
    descriptor = button_descriptor(command_rules=[{"command": "PING"}])
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerActionButton(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = "button.test_ping"

    await entity.async_press()

    assert len(api.calls) == 1
    assert api.calls[0]["command"] == "PING"


@pytest.mark.asyncio
async def test_button_hides_ui_route_when_spa_route_not_visible(hass: HomeAssistant) -> None:
    """UI-route buttons must respect SPA route visibility like other platforms (#192)."""
    runtime, *_rest = make_runtime()
    runtime._symbol_route_lookup["DEV1:RESET_ALARM"] = ("DEV1", "RESET_ALARM", "MAINMENU_X", "/x")
    runtime._symbol_route_visible["DEV1:RESET_ALARM"] = False
    descriptor = button_descriptor(symbol="RESET_ALARM")
    descriptor[CONF_UI_ROUTE_SYMBOL] = True
    descriptor[CONF_ROUTE_VISIBILITY_NAME] = "MAINMENU_X"
    descriptor[CONF_ROUTE_VISIBILITY_PATH] = "/x"
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = BragerActionButton(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass

    await entity.async_update()
    assert entity._attr_available is False
