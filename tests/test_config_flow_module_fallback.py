"""Tests for config-flow module fallback behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from pybragerone.api.client import ApiError

from custom_components.habragerone.config_flow import _extract_modules_payload, _safe_module_payloads


def test_extract_modules_payload_handles_known_shapes() -> None:
    assert _extract_modules_payload({"data": [{"devid": "M1"}, {"devid": "M2"}]}) == [
        {"devid": "M1"},
        {"devid": "M2"},
    ]
    assert _extract_modules_payload([{"devid": "M1"}, "bad"]) == [{"devid": "M1"}]
    assert _extract_modules_payload({"unexpected": "shape"}) == []


def test_safe_module_payloads_reraises_api_error() -> None:
    class _Api:
        async def get_modules(self, object_id: int) -> list[object]:
            _ = object_id
            raise ApiError(401, {"message": "unauthorized"})

    with pytest.raises(ApiError):
        asyncio.run(_safe_module_payloads(_Api(), 1))


def test_safe_module_payloads_falls_back_to_raw_request_on_parse_error() -> None:
    class _Api:
        _api_base = "https://api.example.test"

        async def get_modules(self, object_id: int) -> list[object]:
            _ = object_id
            raise ValueError("validation failed")

        async def _req(self, method: str, url: str) -> tuple[int, Any, dict[str, Any]]:
            _ = method
            assert "group_id=42" in url
            return 200, {"data": [{"devid": "M1", "name": "Module 1"}]}, {}

    result = asyncio.run(_safe_module_payloads(_Api(), 42))

    assert result == [{"devid": "M1", "name": "Module 1"}]


def test_safe_module_payloads_returns_empty_for_non_200_raw_response() -> None:
    class _Api:
        _api_base = "https://api.example.test"

        async def get_modules(self, object_id: int) -> list[object]:
            _ = object_id
            raise ValueError("validation failed")

        async def _req(self, method: str, url: str) -> tuple[int, Any, dict[str, Any]]:
            _ = method, url
            return 500, {"error": "boom"}, {}

    result = asyncio.run(_safe_module_payloads(_Api(), 7))

    assert result == []


def test_safe_module_payloads_uses_model_dump_when_available() -> None:
    class _Api:
        async def get_modules(self, object_id: int) -> list[object]:
            _ = object_id
            return [SimpleNamespace(model_dump=lambda mode="json": {"devid": "M1", "mode": mode})]

    result = asyncio.run(_safe_module_payloads(_Api(), 1))

    assert result == [{"devid": "M1", "mode": "json"}]
