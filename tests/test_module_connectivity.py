"""Tests for module connectivity runtime cache and diagnostic binary sensor."""

from __future__ import annotations

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.binary_sensor import (  # noqa: E402
    BragerModuleConnectivityBinarySensor,
    async_setup_entry,
)
from custom_components.habragerone.const import (  # noqa: E402
    CONF_MODULES_META,
    DATA_ENTITY_STATS,
    DOMAIN,
)
from custom_components.habragerone.entity_common import entity_is_available, module_is_reachable  # noqa: E402
from tests.helpers.descriptors import binary_sensor_descriptor  # noqa: E402
from tests.helpers.fakes import make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


def test_module_is_reachable_unknown_defaults_true() -> None:
    runtime, *_rest = make_runtime()
    assert module_is_reachable(runtime, "DEV1") is True
    runtime._module_online["DEV1"] = False
    assert module_is_reachable(runtime, "DEV1") is False
    assert entity_is_available(runtime, devid="DEV1", has_value=True) is False
    assert entity_is_available(runtime, devid="DEV1", has_value=False) is False


@pytest.mark.asyncio
async def test_runtime_seeds_and_fans_out_connectivity() -> None:
    runtime, _api, gateway, _store = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    gateway._online["DEV1"] = True
    gateway._connected_at["DEV1"] = 1_700_000_000
    seen: list[tuple[str, bool]] = []
    runtime.add_connectivity_listener(lambda devid, online: seen.append((devid, online)))

    await runtime.start()
    assert runtime.module_online("DEV1") is True
    assert runtime.modules_meta["DEV1"]["connectedAt"] == 1_700_000_000
    assert ("DEV1", True) in seen

    seen.clear()
    gateway.emit_connectivity("DEV1", False, connected_at=0)
    assert runtime.module_online("DEV1") is False
    assert runtime.modules_meta["DEV1"]["connectedAt"] == 0
    assert seen == [("DEV1", False)]
    await runtime.stop()


@pytest.mark.asyncio
async def test_async_setup_adds_connectivity_sensor(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(
        flat_values={"P5.s0": 1},
        modules_meta={"DEV1": {"name": "Boiler", "title": "DasPell", "version": "V2"}},
    )
    descriptors = [binary_sensor_descriptor(symbol="BIN1")]
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors)
    # register_config_entry may not persist modules_meta on entry.data — set explicitly.
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_MODULES_META: {"DEV1": {"name": "Boiler"}}})
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    added: list[object] = []
    await async_setup_entry(hass, entry, added.extend)

    connectivity = [entity for entity in added if isinstance(entity, BragerModuleConnectivityBinarySensor)]
    assert len(connectivity) == 1
    entity = connectivity[0]
    assert entity._attr_device_class == BinarySensorDeviceClass.CONNECTIVITY
    assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC
    assert entity._attr_unique_id.endswith("_dev1_connectivity_binary")
    stats = hass.data[DOMAIN][entry.entry_id][DATA_ENTITY_STATS]["binary_sensor"]
    assert stats["created_count"] == 2


@pytest.mark.asyncio
async def test_connectivity_sensor_tracks_runtime(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    entity = BragerModuleConnectivityBinarySensor(
        entry=entry,
        runtime=runtime,
        devid="DEV1",
        module_meta={"name": "Boiler"},
    )
    entity.hass = hass
    entity.async_write_ha_state = lambda: None  # type: ignore[method-assign]
    entity.schedule_update_ha_state = lambda *a, **k: None  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = lambda *a, **k: None  # type: ignore[method-assign]

    await entity.async_added_to_hass()
    runtime._apply_module_online("DEV1", True, connected_at=99)
    await entity.async_update()
    assert entity._attr_is_on is True

    runtime._apply_module_online("DEV1", False, connected_at=0)
    await entity.async_update()
    assert entity._attr_is_on is False
