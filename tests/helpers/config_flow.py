"""Shared mocks for config flow integration tests."""

from __future__ import annotations

import ssl
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch


def _module_model(*, devid: str = "DEV1", name: str = "Boiler module", version: str = "1.0") -> SimpleNamespace:
    return SimpleNamespace(
        model_dump=lambda mode="json": {
            "devid": devid,
            "name": name,
            "moduleTitle": name,
            "moduleVersion": version,
        },
    )


def make_fake_api(
    *,
    auth_error: bool = False,
    objects: list[SimpleNamespace] | None = None,
    modules: list[SimpleNamespace] | None = None,
) -> AsyncMock:
    """Build a fake API client for config/options flow tests."""
    from pybragerone.api.client import ApiError

    api = AsyncMock()
    if auth_error:
        api.ensure_auth = AsyncMock(side_effect=ApiError(401, {"message": "auth"}))
    else:
        api.ensure_auth = AsyncMock(return_value=None)
    api.get_objects = AsyncMock(
        return_value=[
            SimpleNamespace(id=1, name="Site A"),
            SimpleNamespace(id=2, name="Site B"),
        ]
        if objects is None
        else objects,
    )
    api.get_modules = AsyncMock(return_value=modules if modules is not None else [_module_model()])
    api.close = AsyncMock()
    return api


def make_language_config() -> SimpleNamespace:
    """Build a minimal language config payload for LiveAssetsCatalog."""
    return SimpleNamespace(
        default_translation="en",
        translations=[
            {"id": "en", "name": "English", "flag": "🇬🇧"},
            {"id": "pl", "name": "Polski", "flag": "🇵🇱"},
        ],
    )


def make_bootstrap_payload() -> dict[str, Any]:
    """Build a minimal bootstrap payload returned during module selection."""
    from custom_components.habragerone.const import BOOTSTRAP_VERSION

    return {
        "entity_descriptors": [{"symbol": "PARAM_0", "devid": "DEV1", "platform": "sensor", "enabled_by_default": True}],
        "modules_meta": {"DEV1": {"name": "Boiler module"}},
        "connection_descriptors": [],
        "bootstrap_debug": {"modules": {}},
        "bootstrap_version": BOOTSTRAP_VERSION,
        "upstream_assets_fingerprint": "1.04.01|index-test.js",
    }


def _fake_ssl_context() -> ssl.SSLContext:
    return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


@contextmanager
def patch_config_flow_dependencies(
    *,
    api: AsyncMock | None = None,
    bootstrap_payload: dict[str, Any] | None = None,
    bootstrap_error: Exception | None = None,
):
    """Patch config-flow external collaborators for offline tests."""
    fake_api = api or make_fake_api()
    bootstrap_result = bootstrap_payload if bootstrap_payload is not None else make_bootstrap_payload()
    bootstrap_mock = AsyncMock(side_effect=bootstrap_error) if bootstrap_error else AsyncMock(return_value=bootstrap_result)

    catalog = AsyncMock()
    catalog.list_language_config = AsyncMock(return_value=make_language_config())
    catalog.get_i18n = AsyncMock(return_value={"lang": {"en": "English", "pl": "Polski"}})

    client_calls: list[dict[str, Any]] = []
    verify_context = _fake_ssl_context()

    def _api_factory(**kwargs: Any) -> AsyncMock:
        client_calls.append(kwargs)
        return fake_api

    with (
        patch("custom_components.habragerone.config_flow.BragerOneApiClient", side_effect=_api_factory),
        patch(
            "custom_components.habragerone.config_flow.async_ssl_verify_context",
            AsyncMock(return_value=verify_context),
        ),
        patch("custom_components.habragerone.config_flow.LiveAssetsCatalog", return_value=catalog),
        patch("custom_components.habragerone.config_flow.async_build_bootstrap_payload", bootstrap_mock),
        patch("custom_components.habragerone.config_flow.server_for", return_value=object()),
    ):
        fake_api.client_calls = client_calls  # type: ignore[attr-defined]
        fake_api.verify_context = verify_context  # type: ignore[attr-defined]
        yield fake_api, bootstrap_mock
