"""Tests for HA token persistence helper."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from pybragerone.models.token import Token  # noqa: E402

from custom_components.habragerone.token_store import HATokenStore  # noqa: E402


@pytest.mark.asyncio
async def test_token_store_load_returns_none_when_empty(hass: HomeAssistant) -> None:
    store = HATokenStore(hass, "entry-1")
    assert await store.load() is None


@pytest.mark.asyncio
async def test_token_store_roundtrip_and_clear(hass: HomeAssistant) -> None:
    store = HATokenStore(hass, "entry-2")
    token = Token(
        access_token="access-123",
        refresh_token="refresh-456",
        token_type="bearer",
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        objects=[{"id": 1, "name": "Site"}],
    )

    await store.save(token)
    loaded = await store.load()

    assert loaded is not None
    assert loaded.access_token == "access-123"
    assert loaded.refresh_token == "refresh-456"
    assert loaded.token_type == "bearer"
    assert loaded.objects == [{"id": 1, "name": "Site"}]

    await store.clear()
    assert await store.load() is None


@pytest.mark.asyncio
async def test_token_store_load_accepts_legacy_camel_case_keys(hass: HomeAssistant) -> None:
    store = HATokenStore(hass, "entry-3")
    await store._store().async_save(
        {
            "accessToken": "legacy-access",
            "refreshToken": "legacy-refresh",
            "type": "Bearer",
            "expiresAt": "2030-01-01T00:00:00+00:00",
            "objects": [],
        }
    )

    loaded = await store.load()
    assert loaded is not None
    assert loaded.access_token == "legacy-access"
    assert loaded.refresh_token == "legacy-refresh"
    assert loaded.token_type == "Bearer"


@pytest.mark.asyncio
async def test_token_store_load_returns_none_for_invalid_payload(hass: HomeAssistant) -> None:
    store = HATokenStore(hass, "entry-4")
    await store._store().async_save("not-a-dict")

    assert await store.load() is None
