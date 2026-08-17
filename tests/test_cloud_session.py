"""Tests for library↔cloud Socket.IO session runtime cache and diagnostic sensor."""

from __future__ import annotations

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.binary_sensor import (  # noqa: E402
    BragerCloudSessionBinarySensor,
    async_setup_entry,
)
from custom_components.habragerone.const import DOMAIN  # noqa: E402
from tests.helpers.descriptors import binary_sensor_descriptor  # noqa: E402
from tests.helpers.fakes import FakeGateway, make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


@pytest.mark.asyncio
async def test_runtime_seeds_and_fans_out_cloud_session() -> None:
    runtime, _api, gateway, _store = make_runtime()
    seen: list[tuple[bool, bool]] = []
    runtime.add_cloud_session_listener(lambda up, changed: seen.append((up, changed)))

    await runtime.start()
    assert runtime.supports_cloud_session is True
    assert runtime.cloud_session_up() is True
    assert (True, True) in seen

    seen.clear()
    gateway.emit_cloud_session(False, source="disconnect")
    assert runtime.cloud_session_up() is False
    assert seen == [(False, True)]

    seen.clear()
    gateway.emit_cloud_session(True, source="connect")
    assert runtime.cloud_session_up() is True
    assert seen == [(True, True)]
    await runtime.stop()


@pytest.mark.asyncio
async def test_async_setup_adds_cloud_session_sensor(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[binary_sensor_descriptor()])
    added: list[object] = []
    await async_setup_entry(hass, entry, added.extend)

    sessions = [entity for entity in added if isinstance(entity, BragerCloudSessionBinarySensor)]
    assert len(sessions) == 1
    entity = sessions[0]
    assert entity._attr_unique_id == f"{entry.entry_id}_cloud_session_binary"
    assert entity._attr_device_class == BinarySensorDeviceClass.CONNECTIVITY
    assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC
    assert entity._attr_translation_key == "cloud_session"
    info = entity.device_info
    assert (DOMAIN, f"entry:{entry.entry_id}") in info["identifiers"]
    assert info["entry_type"] == DeviceEntryType.SERVICE


@pytest.mark.asyncio
async def test_cloud_session_sensor_tracks_runtime(hass: HomeAssistant) -> None:
    runtime, _api, gateway, _store = make_runtime()
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    entity = BragerCloudSessionBinarySensor(entry=entry, runtime=runtime)
    entity.hass = hass
    entity.entity_id = "binary_sensor.test_cloud_session"

    await runtime.start()
    await entity.async_update()
    assert entity.is_on is True
    assert entity.available is True

    runtime._apply_cloud_session(False, changed=True)
    await entity.async_update()
    assert entity.is_on is False

    # Listener wiring without scheduling HA state (no platform_data in unit tests).
    seen: list[tuple[bool, bool]] = []
    entity._unsubscribe_session = runtime.add_cloud_session_listener(lambda up, changed: seen.append((up, changed)))
    gateway.emit_cloud_session(True, source="connect")
    assert seen == [(True, True)]

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_session is None
    await runtime.stop()


@pytest.mark.asyncio
async def test_async_setup_skips_cloud_session_without_gateway_api(hass: HomeAssistant) -> None:
    class BareGateway:
        """Gateway stub without ``on_cloud_session``."""

        def __init__(self) -> None:
            self.bus = FakeGateway().bus
            self.modules = ["DEV1"]

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_module_connectivity(self, _cb: object) -> None:
            return None

        def module_online(self, _devid: str) -> bool | None:
            return None

        def ws_session_up(self) -> bool:
            return False

    runtime, *_rest = make_runtime()
    runtime.gateway = BareGateway()  # type: ignore[assignment]
    assert runtime.supports_cloud_session is False
    entry = register_config_entry(hass, runtime=runtime, descriptors=[binary_sensor_descriptor()])
    added: list[object] = []
    await async_setup_entry(hass, entry, added.extend)
    assert not any(isinstance(entity, BragerCloudSessionBinarySensor) for entity in added)
