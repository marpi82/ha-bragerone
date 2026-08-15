"""Tests for upstream web-app asset fingerprint helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.upstream_assets import (  # noqa: E402
    async_discover_index_asset,
    async_probe_upstream_assets_fingerprint,
    build_upstream_assets_fingerprint,
    index_asset_from_url,
)


def test_build_and_parse_fingerprint_helpers() -> None:
    assert build_upstream_assets_fingerprint(api_version="2.08", index_asset="index-Ab12.js") == "2.08|index-Ab12.js"
    assert index_asset_from_url("https://one.brager.pl/assets/index-Ab12.js") == "index-Ab12.js"
    assert index_asset_from_url("https://one.brager.pl/") is None
    assert index_asset_from_url(None) is None


@pytest.mark.asyncio
async def test_discover_index_asset_reads_homepage_script() -> None:
    client = SimpleNamespace(
        one_base="https://one.brager.pl",
        get_bytes=AsyncMock(return_value=b'<script src="/assets/index-NewHash.js"></script>'),
    )
    assert await async_discover_index_asset(client) == "index-NewHash.js"


@pytest.mark.asyncio
async def test_probe_fingerprint_happy_path() -> None:
    client = SimpleNamespace(
        one_base="https://one.brager.pl",
        get_system_version=AsyncMock(return_value=SimpleNamespace(version="2.08")),
        get_bytes=AsyncMock(return_value=b'href="/assets/index-Ab12.js"'),
    )
    assert await async_probe_upstream_assets_fingerprint(client) == "2.08|index-Ab12.js"


@pytest.mark.asyncio
async def test_probe_fingerprint_returns_none_on_failure() -> None:
    client = SimpleNamespace(
        one_base="https://one.brager.pl",
        get_system_version=AsyncMock(side_effect=RuntimeError("offline")),
        get_bytes=AsyncMock(),
    )
    assert await async_probe_upstream_assets_fingerprint(client) is None
