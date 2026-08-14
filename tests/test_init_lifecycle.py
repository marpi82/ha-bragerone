"""Tests for integration setup, unload, and migration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone import (  # noqa: E402
    _async_update_listener,
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.habragerone.const import (  # noqa: E402
    BOOTSTRAP_VERSION,
    CONF_BACKEND_PLATFORM,
    CONF_BOOTSTRAP_VERSION,
    CONF_ENTITY_DESCRIPTORS,
    CONF_MODULES,
    CONF_MODULES_META,
    CONF_OBJECT_ID,
    DATA_RUNTIME,
    DOMAIN,
)
from tests.helpers.config_flow import make_bootstrap_payload  # noqa: E402
from tests.helpers.fakes import make_runtime  # noqa: E402
from tests.helpers.init_setup import make_config_entry, patch_setup_dependencies  # noqa: E402


@pytest.mark.asyncio
async def test_async_setup_entry_uses_cached_bootstrap(hass: HomeAssistant) -> None:
    entry = make_config_entry()
    entry.add_to_hass(hass)

    with patch_setup_dependencies() as deps, patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()):
        assert await async_setup_entry(hass, entry) is True

    deps["api"].ensure_auth.assert_awaited_once()
    deps["runtime"].start.assert_awaited_once()
    deps["bootstrap"].assert_not_awaited()
    assert DATA_RUNTIME in hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
async def test_async_setup_entry_refreshes_when_options_changed(hass: HomeAssistant) -> None:
    entry = make_config_entry(options={CONF_OBJECT_ID: 2, CONF_MODULES: ["DEV2"]})
    entry.add_to_hass(hass)
    bootstrap_payload = make_bootstrap_payload()

    with (
        patch_setup_dependencies(bootstrap_payload=bootstrap_payload) as deps,
        patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()),
    ):
        assert await async_setup_entry(hass, entry) is True

    deps["bootstrap"].assert_awaited_once()
    assert entry.data[CONF_OBJECT_ID] == 2
    assert entry.data[CONF_MODULES] == ["DEV2"]
    assert entry.data[CONF_BOOTSTRAP_VERSION] == BOOTSTRAP_VERSION


@pytest.mark.asyncio
async def test_async_setup_entry_refreshes_when_cached_bootstrap_missing(hass: HomeAssistant) -> None:
    entry = make_config_entry(data={CONF_MODULES_META: None, CONF_BOOTSTRAP_VERSION: None})
    entry.add_to_hass(hass)

    with patch_setup_dependencies() as deps, patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()):
        assert await async_setup_entry(hass, entry) is True

    deps["bootstrap"].assert_awaited_once()


@pytest.mark.asyncio
async def test_async_setup_entry_normalizes_cached_descriptors(hass: HomeAssistant) -> None:
    entry = make_config_entry(
        data={
            CONF_ENTITY_DESCRIPTORS: [
                {
                    "symbol": "PARAM_P5_40",
                    "devid": "MOD1",
                    "pool": "P5",
                    "chan": "s",
                    "idx": 40,
                    "platform": "sensor",
                    "mapping": {},
                    "writable": False,
                }
            ]
        }
    )
    entry.add_to_hass(hass)

    with patch_setup_dependencies(), patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()):
        assert await async_setup_entry(hass, entry) is True

    stored = entry.data[CONF_ENTITY_DESCRIPTORS]
    assert isinstance(stored, list)
    assert stored[0]["platform"] == "binary_sensor"


@pytest.mark.asyncio
async def test_async_setup_entry_raises_when_auth_fails(hass: HomeAssistant) -> None:
    entry = make_config_entry()
    entry.add_to_hass(hass)
    api = AsyncMock()
    api.ensure_auth = AsyncMock(side_effect=RuntimeError("auth failed"))

    with patch_setup_dependencies(api=api), pytest.raises(ConfigEntryNotReady, match="Authentication failed"):
        await async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_setup_entry_raises_for_unsupported_platform(hass: HomeAssistant) -> None:
    entry = make_config_entry(data={CONF_BACKEND_PLATFORM: "unknown"})
    entry.add_to_hass(hass)

    with (
        patch("custom_components.habragerone.server_for", side_effect=ValueError("bad platform")),
        pytest.raises(ConfigEntryNotReady, match="Unsupported backend platform"),
    ):
        await async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_unload_entry_stops_runtime_and_clears_domain_data(hass: HomeAssistant) -> None:
    runtime, *_rest = make_runtime()
    entry = make_config_entry()
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {entry.entry_id: {DATA_RUNTIME: runtime}}

    with patch.object(hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=True)):
        assert await async_unload_entry(hass, entry) is True

    assert entry.entry_id not in hass.data.get(DOMAIN, {})
    assert DOMAIN not in hass.data


@pytest.mark.asyncio
async def test_async_unload_entry_returns_false_when_platform_unload_fails(hass: HomeAssistant) -> None:
    entry = make_config_entry()
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {entry.entry_id: {DATA_RUNTIME: make_runtime()[0]}}

    with patch.object(hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=False)):
        assert await async_unload_entry(hass, entry) is False


@pytest.mark.asyncio
async def test_async_unload_entry_without_domain_data(hass: HomeAssistant) -> None:
    entry = make_config_entry()
    entry.add_to_hass(hass)

    with patch.object(hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=True)):
        assert await async_unload_entry(hass, entry) is True


@pytest.mark.asyncio
async def test_async_update_listener_reloads_entry(hass: HomeAssistant) -> None:
    entry = make_config_entry()
    entry.add_to_hass(hass)
    reload_mock = AsyncMock()

    with patch.object(hass.config_entries, "async_reload", reload_mock):
        await _async_update_listener(hass, entry)

    reload_mock.assert_awaited_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_async_migrate_entry_returns_true_for_legacy_style_entry(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_OBJECT_ID: 1,
            CONF_MODULES: ["DEV1"],
        },
        version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True


@pytest.mark.asyncio
async def test_async_migrate_entry_noop_when_already_current(hass: HomeAssistant) -> None:
    entry = make_config_entry()
    entry.add_to_hass(hass)
    before = dict(entry.data)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.data == before
