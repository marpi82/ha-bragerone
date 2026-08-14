"""Shared mocks for config flow integration tests."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from pybragerone.api.client import ApiError


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
    api = AsyncMock()
    api.ensure_auth = AsyncMock(side_effect=ApiError(401, {"message": "auth"}) if auth_error else None)
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
    return {
        "entity_descriptors": [{"symbol": "PARAM_0", "devid": "DEV1", "platform": "sensor"}],
        "modules_meta": {"DEV1": {"name": "Boiler module"}},
        "module_filter_modes": {"DEV1": "ui"},
    }


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

    with (
        patch("custom_components.habragerone.config_flow.BragerOneApiClient", return_value=fake_api),
        patch("custom_components.habragerone.config_flow.LiveAssetsCatalog", return_value=catalog),
        patch("custom_components.habragerone.config_flow.async_build_bootstrap_payload", bootstrap_mock),
        patch("custom_components.habragerone.config_flow.server_for", return_value=object()),
    ):
        yield fake_api, bootstrap_mock
