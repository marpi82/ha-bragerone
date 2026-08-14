"""Tests for BragerRuntime symbol resolution helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import HomeAssistantError

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone import runtime as runtime_module  # noqa: E402
from tests.helpers.fakes import FakeParamUpdate, make_runtime  # noqa: E402


class _FakeResolver:
    def __init__(self, resolved: object | None) -> None:
        self._resolved = resolved

    @classmethod
    def from_api(cls, api: object, store: object, lang: object) -> _FakeResolver:
        _ = api, store, lang
        return cls(SimpleNamespace(value=10, value_label="Ten", unit="°C"))

    async def resolve_value(self, symbol: str) -> object | None:
        if symbol == "MISSING":
            return None
        return self._resolved


@pytest.mark.asyncio
async def test_async_resolve_status_label_uses_value_label(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()
    monkeypatch.setattr(runtime_module, "ParamResolver", _FakeResolver)

    assert await runtime.async_resolve_status_label("PARAM_1") is None
    assert await runtime.async_resolve_status_label("STATUS_P5_0") == "Ten"


@pytest.mark.asyncio
async def test_async_resolve_symbol_value_and_with_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()
    monkeypatch.setattr(runtime_module, "ParamResolver", _FakeResolver)

    assert await runtime.async_resolve_symbol_value("MISSING") is None
    assert await runtime.async_resolve_symbol_value("PARAM_1") == "Ten"

    value, unit = await runtime.async_resolve_symbol_with_unit("PARAM_1")
    assert value == "Ten"
    assert unit == "°C"


@pytest.mark.asyncio
async def test_async_resolve_symbol_swallows_resolver_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()

    class _FailingResolver(_FakeResolver):
        async def resolve_value(self, symbol: str) -> object | None:
            _ = symbol
            raise RuntimeError("boom")

    monkeypatch.setattr(runtime_module, "ParamResolver", _FailingResolver)

    assert await runtime.async_resolve_symbol_value("PARAM_1") is None


@pytest.mark.asyncio
async def test_async_get_resolver_returns_none_when_from_api_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()
    runtime._status_resolver = None

    class _BrokenFactory:
        @classmethod
        def from_api(cls, api: object, store: object, lang: object) -> _BrokenFactory:
            _ = api, store, lang
            raise RuntimeError("factory failed")

    monkeypatch.setattr(runtime_module, "ParamResolver", _BrokenFactory)

    assert await runtime._async_get_resolver() is None
    assert await runtime.async_resolve_symbol_value("PARAM_1") is None


@pytest.mark.asyncio
async def test_async_write_raw_command_route_requires_command_mapping() -> None:
    runtime, _api, _gateway, _store = make_runtime()
    descriptor = {
        "symbol": "SYNC_ACTION",
        "devid": "DEV1",
        "pool": None,
        "chan": None,
        "idx": None,
        "mapping": {"command_rules": [{"value": "ON"}]},
    }

    with pytest.raises(HomeAssistantError, match="No raw command mapping"):
        await runtime.async_write(descriptor=descriptor, input_display_value=True)


@pytest.mark.asyncio
async def test_runtime_delivers_updates_when_meta_is_not_dict() -> None:
    """Cover the non-dict update.meta branch in BragerRuntime._dispatch_updates."""
    runtime, _api, gateway, _store = make_runtime()
    received: list[FakeParamUpdate] = []
    delivered_event = asyncio.Event()

    def _listener(update: FakeParamUpdate) -> None:
        received.append(update)
        delivered_event.set()

    runtime.add_listener(_listener)
    await runtime.start()
    try:
        update = FakeParamUpdate(pool="P1", chan="v", idx=1)
        update.meta = "ws"  # type: ignore[assignment]
        gateway.bus.push(update)
        await asyncio.wait_for(delivered_event.wait(), timeout=1.0)
        assert received == [update]
    finally:
        await runtime.stop()
