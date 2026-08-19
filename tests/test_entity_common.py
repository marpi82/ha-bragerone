"""Tests for shared entity_common helpers."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.const import (  # noqa: E402
    CONF_ENTITY_DESCRIPTORS,
    CONF_MODULES,
    DATA_ENTITY_STATS,
    DATA_RUNTIME,
    DEVICE_GROUPING_BY_MENU,
    DEVICE_GROUPING_FLAT,
    DOMAIN,
)
from custom_components.habragerone.entity_common import (  # noqa: E402
    _menu_device_display_name,
    async_register_module_parent_devices,
    descriptor_current_raw_value,
    descriptor_enum_map,
    descriptor_options,
    descriptor_raw_to_label,
    descriptor_refresh_keys,
    device_grouping_mode,
    device_info_from_descriptor,
    get_runtime_and_descriptors,
    module_parent_device_info,
    record_platform_entity_stats,
    store_value_for_address,
)
from tests.helpers.descriptors import switch_descriptor, writable_parameter_descriptor  # noqa: E402
from tests.helpers.fakes import FakeStore, make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


def test_descriptor_refresh_keys_direct_address() -> None:
    descriptor = switch_descriptor(pool="P5", chan="s", idx=3)
    assert descriptor_refresh_keys(descriptor) == {"P5.s3"}


def test_descriptor_refresh_keys_mapping_inputs() -> None:
    descriptor = {
        "mapping": {
            "inputs": [{"address": "P1.v2"}, {"address": " P6.s0 "}, {"address": ""}, "bad"],
        },
    }
    assert descriptor_refresh_keys(descriptor) == {"P1.v2", "P6.s0"}


def test_store_value_for_address_reads_family_channel() -> None:
    store = FakeStore(flat_values={"P6.v0": 42, "P6.s0": 1})
    assert store_value_for_address(store, "P6.v0") == 42
    assert store_value_for_address(store, "P6.s9") is None


def test_store_value_for_address_rejects_invalid_syntax() -> None:
    store = FakeStore()
    assert store_value_for_address(store, "invalid") is None
    assert store_value_for_address(store, "P6.bad") is None


def test_descriptor_current_raw_value_prefers_direct_mapping() -> None:
    store = FakeStore(flat_values={"P5.s0": 0, "P1.v2": 99})
    descriptor = switch_descriptor(
        pool="P5",
        chan="s",
        idx=0,
        mapping_inputs=[{"address": "P1.v2"}],
    )
    assert descriptor_current_raw_value(store, descriptor) == 0


def test_descriptor_current_raw_value_falls_back_to_mapping_input() -> None:
    store = FakeStore(flat_values={"P1.v2": 7})
    descriptor = {
        "pool": "P5",
        "chan": "s",
        "idx": 0,
        "mapping": {"inputs": [{"address": "P1.v2"}]},
    }
    assert descriptor_current_raw_value(store, descriptor) == 7


def test_descriptor_current_raw_value_returns_none_when_missing() -> None:
    store = FakeStore()
    assert descriptor_current_raw_value(store, switch_descriptor()) is None


def test_descriptor_options_filters_invalid_entries() -> None:
    descriptor: dict[str, Any] = {"options": [" Auto ", "", 3, None]}
    assert descriptor_options(descriptor) == [" Auto ", "3", "None"]
    assert descriptor_options({"options": "bad"}) == []


def test_descriptor_enum_map_keeps_scalar_values_only() -> None:
    descriptor: dict[str, Any] = {
        "enum_map": {"On": 1, "Off": 0, "Bad": {"nested": True}, "Text": "x"},
    }
    assert descriptor_enum_map(descriptor) == {"On": 1, "Off": 0, "Text": "x"}
    assert descriptor_enum_map({"enum_map": []}) == {}


def test_descriptor_raw_to_label_normalizes_keys() -> None:
    descriptor: dict[str, Any] = {"raw_to_label": {1: "On", 0: "Off"}}
    assert descriptor_raw_to_label(descriptor) == {"1": "On", "0": "Off"}
    assert descriptor_raw_to_label({"raw_to_label": "bad"}) == {}


def test_menu_device_display_name_falls_back_to_menu_literal() -> None:
    assert _menu_device_display_name({}) == "menu"
    assert _menu_device_display_name({"menu_key": ""}) == "menu"


def test_device_info_from_descriptor_builds_registry_payload() -> None:
    descriptor = writable_parameter_descriptor(
        devid="DEV9",
        symbol="TEMP",
    )
    descriptor.update(
        {
            "module_name": "boiler",
            "module_title": "Boiler module",
            "module_version": "1.2.3",
        },
    )
    info = device_info_from_descriptor(descriptor, domain=DOMAIN)
    assert info["identifiers"] == {(DOMAIN, "DEV9")}
    assert info["manufacturer"] == "BragerOne"
    assert info["name"] == "boiler"
    assert info["model"] == "Boiler module"
    assert info["sw_version"] == "1.2.3"
    assert "via_device" not in info


def test_device_info_from_descriptor_groups_by_menu_when_enabled() -> None:
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update(
        {
            "module_name": "boiler",
            "module_title": "Boiler module",
            "module_version": "1.2.3",
            "menu_key": "modules.menu.thermostats",
            "menu_title": "Zawór 1",
            "menu_group_title": "Menu termostatów",
            "panel_path": "Menu termostatów/Zawór 1",
        },
    )
    info = device_info_from_descriptor(descriptor, domain=DOMAIN, grouping=DEVICE_GROUPING_BY_MENU)
    assert info["identifiers"] == {(DOMAIN, "DEV9:modules.menu.thermostats")}
    assert info["name"] == "Menu termostatów"
    assert info["via_device"] == (DOMAIN, "DEV9")
    assert info["model"] == "Boiler module"


def test_device_info_from_descriptor_group_mode_keeps_parent_without_menu_key() -> None:
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update({"module_name": "boiler", "module_title": "Boiler module"})
    info = device_info_from_descriptor(descriptor, domain=DOMAIN, grouping=DEVICE_GROUPING_BY_MENU)
    assert info["identifiers"] == {(DOMAIN, "DEV9")}
    assert "via_device" not in info


def test_device_info_flat_ignores_menu_key() -> None:
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update(
        {
            "module_name": "boiler",
            "menu_key": "modules.menu.boiler",
            "menu_title": "Kocioł",
        },
    )
    info = device_info_from_descriptor(descriptor, domain=DOMAIN, grouping=DEVICE_GROUPING_FLAT)
    assert info["identifiers"] == {(DOMAIN, "DEV9")}
    assert info["name"] == "boiler"


def test_device_info_group_mode_uses_panel_path_leaf_without_menu_title() -> None:
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update(
        {
            "module_name": "boiler",
            "module_title": "Boiler module",
            "menu_key": "modules.menu.valve1",
            "panel_path": "Termostaty/Zawór 1",
        },
    )
    info = device_info_from_descriptor(descriptor, domain=DOMAIN, grouping=DEVICE_GROUPING_BY_MENU)
    assert info["identifiers"] == {(DOMAIN, "DEV9:modules.menu.valve1")}
    # Without menu_group_title, first panel_path segment is the device name.
    assert info["name"] == "Termostaty"


def test_device_info_group_mode_falls_back_to_menu_key_then_menu() -> None:
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update({"module_name": "boiler", "menu_key": "modules.menu.dhw"})
    info = device_info_from_descriptor(descriptor, domain=DOMAIN, grouping=DEVICE_GROUPING_BY_MENU)
    assert info["name"] == "modules.menu.dhw"

    descriptor_empty = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor_empty.update({"module_name": "boiler", "menu_key": "  "})
    # Empty menu_key keeps the entity on the parent device.
    info_parent = device_info_from_descriptor(descriptor_empty, domain=DOMAIN, grouping=DEVICE_GROUPING_BY_MENU)
    assert info_parent["identifiers"] == {(DOMAIN, "DEV9")}


def test_device_info_group_mode_slash_only_panel_path_keeps_path() -> None:
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update(
        {
            "module_name": "boiler",
            "menu_key": "modules.menu.x",
            "panel_path": "/",
        },
    )
    info = device_info_from_descriptor(descriptor, domain=DOMAIN, grouping=DEVICE_GROUPING_BY_MENU)
    assert info["name"] == "/"


def test_menu_device_display_name_falls_back_through_path_segments() -> None:
    assert _menu_device_display_name({"menu_group_title": "Menu termostatów"}) == "Menu termostatów"
    assert _menu_device_display_name({"menu_title": "Zawór 1"}) == "Zawór 1"
    assert _menu_device_display_name({"panel_path": "Root/Leaf"}) == "Root"
    assert _menu_device_display_name({"panel_path": "/Leaf"}) == "Leaf"
    assert _menu_device_display_name({"menu_key": "modules.menu.boiler"}) == "modules.menu.boiler"
    assert _menu_device_display_name({}) == "menu"


def test_module_parent_device_info_rejects_non_dict_meta() -> None:
    info = module_parent_device_info(
        devid="DEV9",
        domain=DOMAIN,
        modules_meta={"DEV9": "not-a-dict"},  # type: ignore[dict-item]
        sample_descriptor={"module_name": "from-desc"},
    )
    assert info["name"] == "from-desc"


def test_module_parent_device_info_prefers_modules_meta() -> None:
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update({"module_name": "ignored", "module_title": "Ignored", "module_version": "0"})
    info = module_parent_device_info(
        devid="DEV9",
        domain=DOMAIN,
        modules_meta={"DEV9": {"name": "DasPell", "title": "HT DasPell GL 37kW", "version": "V2.08"}},
        sample_descriptor=descriptor,
    )
    assert info["identifiers"] == {(DOMAIN, "DEV9")}
    assert info["name"] == "DasPell"
    assert info["model"] == "HT DasPell GL 37kW"
    assert info["sw_version"] == "V2.08"


@pytest.mark.asyncio
async def test_async_register_module_parent_devices_for_group_by_menu(hass: HomeAssistant) -> None:
    from homeassistant.helpers import device_registry as dr

    runtime, *_rest = make_runtime()
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update(
        {
            "menu_key": "modules.menu.boiler",
            "module_name": "boiler",
            "module_title": "Boiler module",
            "module_version": "1.2.3",
        },
    )
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, "device_grouping": DEVICE_GROUPING_BY_MENU, CONF_MODULES: ["DEV9"]},
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    await async_register_module_parent_devices(
        hass,
        entry,
        descriptors=[descriptor],
        modules_meta={"DEV9": {"name": "boiler", "title": "Boiler module", "version": "1.2.3"}},
    )

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "DEV9")})
    assert device is not None
    assert device.name == "boiler"


@pytest.mark.asyncio
async def test_async_register_module_parent_devices_skips_flat_mode(hass: HomeAssistant) -> None:
    from homeassistant.helpers import device_registry as dr

    runtime, *_rest = make_runtime()
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update({"menu_key": "modules.menu.boiler"})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])

    await async_register_module_parent_devices(hass, entry, descriptors=[descriptor], modules_meta={})

    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "DEV9")}) is None


@pytest.mark.asyncio
async def test_async_register_module_parent_devices_from_modules_list_only(hass: HomeAssistant) -> None:
    from homeassistant.helpers import device_registry as dr

    runtime, *_rest = make_runtime()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, "device_grouping": DEVICE_GROUPING_BY_MENU, CONF_MODULES: ["DEV9"]},
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    await async_register_module_parent_devices(
        hass,
        entry,
        descriptors=[],
        modules_meta={"DEV9": {"name": "Boiler only modules list"}},
    )

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "DEV9")})
    assert device is not None
    assert device.name == "Boiler only modules list"


@pytest.mark.asyncio
async def test_async_register_module_parent_devices_skips_invalid_rows(hass: HomeAssistant) -> None:
    from homeassistant.helpers import device_registry as dr

    runtime, *_rest = make_runtime()
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update({"menu_key": "modules.menu.boiler", "module_name": "boiler"})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    hass.config_entries.async_update_entry(entry, data={**entry.data, "device_grouping": DEVICE_GROUPING_BY_MENU})
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    await async_register_module_parent_devices(
        hass,
        entry,
        descriptors=["bad-row", {"devid": ""}, descriptor],
        modules_meta={},
    )

    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "DEV9")}) is not None


@pytest.mark.asyncio
async def test_async_register_module_parent_devices_no_devids_is_noop(hass: HomeAssistant) -> None:
    from homeassistant.helpers import device_registry as dr

    runtime, *_rest = make_runtime()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, "device_grouping": DEVICE_GROUPING_BY_MENU, CONF_MODULES: []},
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    await async_register_module_parent_devices(hass, entry, descriptors=["bad"], modules_meta={})

    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "DEV9")}) is None


@pytest.mark.asyncio
async def test_async_register_module_parent_devices_ignores_non_list_modules(hass: HomeAssistant) -> None:
    from homeassistant.helpers import device_registry as dr

    runtime, *_rest = make_runtime()
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update({"menu_key": "modules.menu.boiler"})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, "device_grouping": DEVICE_GROUPING_BY_MENU, CONF_MODULES: "not-a-list"},
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    await async_register_module_parent_devices(hass, entry, descriptors=[descriptor], modules_meta={})

    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "DEV9")}) is not None


@pytest.mark.asyncio
async def test_async_register_module_parent_devices_skips_blank_module_ids(hass: HomeAssistant) -> None:
    from homeassistant.helpers import device_registry as dr

    runtime, *_rest = make_runtime()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, "device_grouping": DEVICE_GROUPING_BY_MENU, CONF_MODULES: ["", "   "]},
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    await async_register_module_parent_devices(hass, entry, descriptors=[], modules_meta={"": {}, "  ": {}})

    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "DEV9")}) is None


@pytest.mark.asyncio
async def test_async_register_module_parent_devices_skips_non_mapping_meta(hass: HomeAssistant) -> None:
    from homeassistant.helpers import device_registry as dr

    runtime, *_rest = make_runtime()
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update({"menu_key": "modules.menu.boiler"})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    hass.config_entries.async_update_entry(entry, data={**entry.data, "device_grouping": DEVICE_GROUPING_BY_MENU})
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    await async_register_module_parent_devices(hass, entry, descriptors=[descriptor], modules_meta="bad-meta")  # type: ignore[arg-type]

    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "DEV9")}) is not None


@pytest.mark.asyncio
async def test_async_register_module_parent_devices_skips_invalid_identifiers(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from homeassistant.helpers import device_registry as dr

    import custom_components.habragerone.entity_common as entity_common_module

    runtime, *_rest = make_runtime()
    descriptor = writable_parameter_descriptor(devid="DEV9", symbol="TEMP")
    descriptor.update({"menu_key": "modules.menu.boiler"})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    hass.config_entries.async_update_entry(entry, data={**entry.data, "device_grouping": DEVICE_GROUPING_BY_MENU})
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    def _bad_parent_info(**_kwargs: object) -> dict[str, object]:
        return {
            "identifiers": [(DOMAIN, "DEV9")],
            "manufacturer": "BragerOne",
            "name": "bad",
            "model": "bad",
            "sw_version": None,
        }

    monkeypatch.setattr(entity_common_module, "module_parent_device_info", _bad_parent_info)

    await async_register_module_parent_devices(hass, entry, descriptors=[descriptor], modules_meta={})

    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "DEV9")}) is None


@pytest.mark.asyncio
async def test_device_grouping_mode_reads_options_then_data(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    assert device_grouping_mode(entry) == DEVICE_GROUPING_FLAT

    hass.config_entries.async_update_entry(entry, data={**entry.data, "device_grouping": DEVICE_GROUPING_BY_MENU})
    assert device_grouping_mode(entry) == DEVICE_GROUPING_BY_MENU

    hass.config_entries.async_update_entry(entry, options={"device_grouping": DEVICE_GROUPING_FLAT})
    assert device_grouping_mode(entry) == DEVICE_GROUPING_FLAT

    hass.config_entries.async_update_entry(entry, options={"device_grouping": "weird"})
    assert device_grouping_mode(entry) == DEVICE_GROUPING_FLAT


@pytest.mark.asyncio
async def test_get_runtime_and_descriptors_filters_platform(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    switch = switch_descriptor()
    number = writable_parameter_descriptor(symbol="NUM")
    entry = register_config_entry(hass, runtime=runtime, descriptors=[switch, number])

    result = get_runtime_and_descriptors(hass, entry, platform="switch")
    assert result is not None
    resolved_runtime, descriptors = result
    assert resolved_runtime is runtime
    assert descriptors == [switch]


@pytest.mark.asyncio
async def test_get_runtime_and_descriptors_returns_none_for_invalid_payload(hass: HomeAssistant) -> None:
    entry = register_config_entry(hass, runtime=make_runtime()[0], descriptors=[])
    hass.data[DOMAIN][entry.entry_id][DATA_RUNTIME] = "not-a-runtime"

    assert get_runtime_and_descriptors(hass, entry, platform="switch") is None

    hass.data[DOMAIN][entry.entry_id][DATA_RUNTIME] = make_runtime()[0]
    hass.data[DOMAIN][entry.entry_id][CONF_ENTITY_DESCRIPTORS] = "bad"
    assert get_runtime_and_descriptors(hass, entry, platform="switch") is None


@pytest.mark.asyncio
async def test_record_platform_entity_stats_persists_counts(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])

    record_platform_entity_stats(
        hass,
        entry,
        platform="switch",
        descriptor_count=3,
        created_count=2,
    )

    stats = hass.data[DOMAIN][entry.entry_id][DATA_ENTITY_STATS]
    assert stats == {"switch": {"descriptor_count": 3, "created_count": 2}}
