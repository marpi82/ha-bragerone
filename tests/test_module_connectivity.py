"""Tests for module connectivity runtime cache and diagnostic binary sensor."""

from __future__ import annotations

import types

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.binary_sensor import (  # noqa: E402
    BragerModuleConnectivityBinarySensor,
    async_setup_entry,
)
from custom_components.habragerone.const import (  # noqa: E402
    CONF_CONNECTION_DESCRIPTORS,
    CONF_MODULES_META,
    DATA_ENTITY_STATS,
    DOMAIN,
)
from custom_components.habragerone.entity_common import entity_is_available, module_is_reachable  # noqa: E402
from tests.helpers.descriptors import binary_sensor_descriptor  # noqa: E402
from tests.helpers.fakes import make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402

CONNECTION_DESCRIPTOR = {
    "kind": "module_connection",
    "source": "module_i18n",
    "menu_key": "module.connection",
    "devid": "DEV1",
    "module_name": "Boiler",
    "label": "Connection with module status",
    "device_name": "Boiler — Connection with module",
    "labels": {
        "connection.status": "Connection with module status",
        "connection.index": "Connection with module",
        "connection.connected": "Connected",
        "connection.notConnected": "Disconnected",
        "serverConnection": "Server connection status",
    },
    "platform": "binary_sensor",
}


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
    seen: list[tuple[str, bool, bool]] = []
    runtime.add_connectivity_listener(lambda devid, online, flipped: seen.append((devid, online, flipped)))

    await runtime.start()
    assert runtime.supports_module_connectivity is True
    assert runtime.module_online("DEV1") is True
    assert runtime.modules_meta["DEV1"]["connectedAt"] == 1_700_000_000
    assert ("DEV1", True, True) in seen

    seen.clear()
    gateway.emit_connectivity("DEV1", False, connected_at=0)
    assert runtime.module_online("DEV1") is False
    assert runtime.modules_meta["DEV1"]["connectedAt"] == 0
    assert seen == [("DEV1", False, True)]
    await runtime.stop()


@pytest.mark.asyncio
async def test_async_write_refuses_when_offline() -> None:
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime._module_online["DEV1"] = False
    with pytest.raises(HomeAssistantError, match="offline"):
        await runtime.async_write(
            descriptor={"symbol": "PARAM_X", "devid": "DEV1", "pool": "P1", "chan": "v", "idx": 1},
            input_display_value=1,
        )


@pytest.mark.asyncio
async def test_async_setup_adds_connectivity_sensor(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(
        flat_values={"P5.s0": 1},
        modules_meta={"DEV1": {"name": "Boiler", "title": "DasPell", "version": "V2"}},
    )
    descriptors = [binary_sensor_descriptor(symbol="BIN1")]
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_MODULES_META: {"DEV1": {"name": "Boiler", "title": "DasPell", "version": "V2"}},
            CONF_CONNECTION_DESCRIPTORS: [CONNECTION_DESCRIPTOR],
        },
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry

    added: list[object] = []
    await async_setup_entry(hass, entry, added.extend)

    connectivity = [entity for entity in added if isinstance(entity, BragerModuleConnectivityBinarySensor)]
    assert len(connectivity) == 1
    entity = connectivity[0]
    assert entity._attr_device_class == BinarySensorDeviceClass.CONNECTIVITY
    assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC
    assert entity._attr_name == "Connection with module status"
    assert entity._attr_unique_id.endswith("_dev1_connectivity_binary")
    info = entity.device_info
    assert info is not None
    assert (DOMAIN, "DEV1:module.connection") in info["identifiers"]
    assert info.get("via_device") == (DOMAIN, "DEV1")
    assert info.get("name") == "Boiler — Connection with module"
    stats = hass.data[DOMAIN][entry.entry_id][DATA_ENTITY_STATS]["binary_sensor"]
    assert stats["created_count"] == 2
    assert stats["descriptor_count"] == 2


@pytest.mark.asyncio
async def test_async_setup_skips_connectivity_without_descriptor(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_MODULES_META: {"DEV1": {"name": "Boiler"}}, CONF_CONNECTION_DESCRIPTORS: []},
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry
    added: list[object] = []
    await async_setup_entry(hass, entry, added.extend)
    assert not any(isinstance(entity, BragerModuleConnectivityBinarySensor) for entity in added)


@pytest.mark.asyncio
async def test_connectivity_sensor_tracks_runtime(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    entity = BragerModuleConnectivityBinarySensor(
        entry=entry,
        runtime=runtime,
        devid="DEV1",
        module_meta={"name": "Boiler"},
        connection_descriptor={
            "label": "Status połączenia z modułem",
            "device_name": "Boiler — Połączenie z modułem",
            "menu_key": "module.connection",
            "labels": {
                "connection.index": "Połączenie z modułem",
                "connection.connected": "Połączono",
                "connection.notConnected": "Rozłączono",
            },
        },
    )
    entity.hass = hass
    entity.async_write_ha_state = lambda: None  # type: ignore[method-assign]
    entity.schedule_update_ha_state = lambda *a, **k: None  # type: ignore[method-assign]
    entity.async_schedule_update_ha_state = lambda *a, **k: None  # type: ignore[method-assign]

    await entity.async_added_to_hass()
    await entity.async_update()
    assert entity._attr_is_on is None
    assert entity._attr_available is False

    runtime._apply_module_online(
        "DEV1",
        True,
        connected_at=99,
        gateway={"address": "10.0.0.1", "interface": "wifi", "version": "V2"},
    )
    await entity.async_update()
    assert entity._attr_is_on is True
    assert entity._attr_available is True
    assert entity._attr_name == "Status połączenia z modułem"
    attrs = entity.extra_state_attributes
    assert attrs["connected_at"] == 99
    assert attrs["gateway_interface"] == "wifi"
    assert attrs["state_label_on"] == "Połączono"

    runtime._apply_module_online("DEV1", False, connected_at=0)
    await entity.async_update()
    assert entity._attr_is_on is False

    entity._on_connectivity("OTHER", True)
    entity._on_connectivity("DEV1", False)
    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_connectivity is None


@pytest.mark.asyncio
async def test_async_setup_skips_non_dict_connection_rows(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}, "": {"name": "bad"}})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_MODULES_META: {"DEV1": "not-a-dict", "": {"name": "bad"}},
            CONF_CONNECTION_DESCRIPTORS: ["bad", {"devid": ""}, CONNECTION_DESCRIPTOR],
        },
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry
    added: list[object] = []
    await async_setup_entry(hass, entry, added.extend)
    connectivity = [entity for entity in added if isinstance(entity, BragerModuleConnectivityBinarySensor)]
    assert len(connectivity) == 1


@pytest.mark.asyncio
async def test_async_setup_skips_non_list_connection_descriptors(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_MODULES_META: {"DEV1": {"name": "Boiler"}},
            CONF_CONNECTION_DESCRIPTORS: "not-a-list",
        },
    )
    entry = hass.config_entries.async_get_entry(entry.entry_id) or entry
    added: list[object] = []
    await async_setup_entry(hass, entry, added.extend)
    assert not any(isinstance(entity, BragerModuleConnectivityBinarySensor) for entity in added)


@pytest.mark.asyncio
async def test_connectivity_sensor_attrs_without_optional_fields(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    runtime.modules_meta["DEV1"] = {
        "name": "Boiler",
        "connectedAt": "bad",
        "gateway": {"address": None, "interface": "", "version": None},
    }
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    entity = BragerModuleConnectivityBinarySensor(
        entry=entry,
        runtime=runtime,
        devid="DEV1",
        module_meta=runtime.modules_meta["DEV1"],
        connection_descriptor={
            "label": "Status",
            "labels": {"connection.connected": 1, "connection.notConnected": None},
            "menu_key": "module.connection",
        },
    )
    attrs = entity.extra_state_attributes
    assert "connected_at" not in attrs
    assert "gateway_address" not in attrs
    assert "gateway_interface" not in attrs
    assert "gateway_version" not in attrs
    assert "state_label_on" not in attrs

    runtime.modules_meta["DEV1"] = {"name": "Boiler", "gateway": "not-a-dict"}
    assert "gateway_address" not in entity.extra_state_attributes

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_connectivity is None


@pytest.mark.asyncio
async def test_connectivity_sensor_requires_spa_label(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    with pytest.raises(ValueError, match="missing SPA i18n label"):
        BragerModuleConnectivityBinarySensor(
            entry=entry,
            runtime=runtime,
            devid="DEV1",
            module_meta={"name": "Boiler"},
            connection_descriptor={"labels": {}},
        )


@pytest.mark.asyncio
async def test_runtime_connectivity_listener_compat_and_seed_edges() -> None:
    from typing import ClassVar

    from custom_components.habragerone.runtime import BragerRuntime

    runtime, _api, _gateway, _store = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    two_arg: list[tuple[str, bool]] = []
    runtime.add_connectivity_listener(lambda devid, online: two_arg.append((devid, online)))
    boom_calls = 0

    def _boom(_devid: str, _online: bool, _flipped: bool = True) -> None:
        nonlocal boom_calls
        boom_calls += 1
        raise RuntimeError("listener boom")

    runtime.add_connectivity_listener(_boom)
    runtime._apply_module_online("DEV1", True, connected_at=1)
    assert two_arg == [("DEV1", True)]
    assert boom_calls == 1

    # Bad gateway events are ignored.
    runtime._on_gateway_connectivity(object())
    runtime._on_gateway_connectivity(types.SimpleNamespace(devid="", online=True))
    runtime._on_gateway_connectivity(
        types.SimpleNamespace(devid="DEV1", online=False, online_changed="yes", connected_at=0, gateway=None)
    )
    assert runtime.module_online("DEV1") is False

    # Seed skips when gateway has no modules list / no online getter.
    class _NoModules:
        def on_module_connectivity(self, _cb: object) -> None:
            return None

        def module_online(self, _devid: str) -> bool | None:
            return True

    runtime.gateway = _NoModules()  # type: ignore[assignment]
    runtime._seed_module_online_from_gateway()

    class _BadModules:
        modules: ClassVar[object] = "nope"

        def on_module_connectivity(self, _cb: object) -> None:
            return None

        def module_online(self, _devid: str) -> bool | None:
            return True

    runtime.gateway = _BadModules()  # type: ignore[assignment]
    runtime._seed_module_online_from_gateway()

    class _NoOnlineGetter:
        modules: ClassVar[list[str]] = ["DEV1"]

        def on_module_connectivity(self, _cb: object) -> None:
            return None

    runtime.gateway = _NoOnlineGetter()  # type: ignore[assignment]
    assert runtime.supports_module_connectivity is False
    runtime._seed_module_online_from_gateway()

    class _SupportsButNoGetter:
        modules: ClassVar[list[str]] = ["DEV1"]
        module_online = None

        def on_module_connectivity(self, _cb: object) -> None:
            return None

    class _NonBoolOnline:
        modules: ClassVar[list[str]] = ["DEV1"]

        def on_module_connectivity(self, _cb: object) -> None:
            return None

        def module_online(self, _devid: str) -> object:
            return "yes"

        def module_connected_at(self, _devid: str) -> None:
            return None

        def module_gateway(self, _devid: str) -> None:
            return None

    original_supports = BragerRuntime.supports_module_connectivity
    try:
        BragerRuntime.supports_module_connectivity = property(lambda self: True)  # type: ignore[assignment,method-assign]
        runtime.gateway = _SupportsButNoGetter()  # type: ignore[assignment]
        runtime._seed_module_online_from_gateway()
    finally:
        BragerRuntime.supports_module_connectivity = original_supports  # type: ignore[assignment]

    runtime.gateway = _NonBoolOnline()  # type: ignore[assignment]
    runtime._seed_module_online_from_gateway()
    assert runtime.module_online("DEV1") is False

    # Metadata-only apply (no connected_at) and start without connectivity API.
    runtime._apply_module_online("DEV1", True, connected_at=None, gateway={"address": ""})
    assert runtime.modules_meta["DEV1"].get("gateway") == {"address": ""}

    class _NoConnectivityApi:
        modules: ClassVar[list[str]] = ["DEV1"]

        def __init__(self) -> None:
            from tests.helpers.fakes import FakeBus

            self.bus = FakeBus()

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    runtime.gateway = _NoConnectivityApi()  # type: ignore[assignment]
    await runtime.start()
    await runtime.stop()
