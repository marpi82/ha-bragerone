"""Shared mocks for integration setup/unload tests."""

from __future__ import annotations

import ssl
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.habragerone.const import (
    BOOTSTRAP_VERSION,
    CONF_BACKEND_PLATFORM,
    CONF_BOOTSTRAP_VERSION,
    CONF_ENTITY_DESCRIPTORS,
    CONF_MODULES,
    CONF_MODULES_META,
    CONF_OBJECT_ID,
    DOMAIN,
)
from tests.helpers.config_flow import make_bootstrap_payload


def _fake_ssl_context() -> ssl.SSLContext:
    return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def make_config_entry(
    *,
    entry_id: str = "test-entry-id",
    data: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> MockConfigEntry:
    """Build a config entry with a complete cached bootstrap payload."""
    bootstrap = make_bootstrap_payload()
    entry_data: dict[str, Any] = {
        CONF_EMAIL: "user@example.com",
        CONF_PASSWORD: "secret",
        CONF_BACKEND_PLATFORM: "bragerone",
        CONF_OBJECT_ID: 1,
        CONF_MODULES: ["DEV1"],
        CONF_BOOTSTRAP_VERSION: BOOTSTRAP_VERSION,
        CONF_MODULES_META: bootstrap[CONF_MODULES_META],
        CONF_ENTITY_DESCRIPTORS: bootstrap[CONF_ENTITY_DESCRIPTORS],
    }
    if data:
        entry_data.update(data)
    return MockConfigEntry(entry_id=entry_id, domain=DOMAIN, data=entry_data, options=options or {})


@contextmanager
def patch_setup_dependencies(
    *,
    api: AsyncMock | None = None,
    bootstrap_payload: dict[str, Any] | None = None,
    runtime: Any | None = None,
):
    """Patch collaborators used by async_setup_entry."""
    if api is None:
        fake_api = MagicMock()
        fake_api.ensure_auth = AsyncMock(return_value=None)
    else:
        fake_api = api
    fake_api.close = AsyncMock()

    fake_gateway = MagicMock()
    fake_store = MagicMock()
    fake_runtime = runtime or MagicMock()
    fake_runtime.start = AsyncMock()
    fake_runtime.stop = AsyncMock()

    bootstrap_result = bootstrap_payload if bootstrap_payload is not None else make_bootstrap_payload()
    bootstrap_mock = AsyncMock(return_value=bootstrap_result)

    def _api_factory(**_kwargs: object) -> MagicMock:
        return fake_api

    with (
        patch("custom_components.habragerone.BragerOneApiClient", side_effect=_api_factory),
        patch("custom_components.habragerone.BragerOneGateway", return_value=fake_gateway),
        patch("custom_components.habragerone.ParamStore", return_value=fake_store),
        patch("custom_components.habragerone.BragerRuntime", return_value=fake_runtime),
        patch("custom_components.habragerone.async_build_bootstrap_payload", bootstrap_mock),
        patch("custom_components.habragerone._build_ssl_context", _fake_ssl_context),
    ):
        yield {
            "api": fake_api,
            "gateway": fake_gateway,
            "store": fake_store,
            "runtime": fake_runtime,
            "bootstrap": bootstrap_mock,
        }
