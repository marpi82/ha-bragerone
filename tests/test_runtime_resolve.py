"""Tests for BragerRuntime symbol resolution helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone import runtime as runtime_module  # noqa: E402
from custom_components.habragerone.runtime import BragerRuntime  # noqa: E402
from tests.helpers.fakes import FakeParamUpdate, make_runtime  # noqa: E402


class _FakeResolver:
    def __init__(self, resolved: object | None) -> None:
        self._resolved = resolved
        self.prefetched: list[str] = []

    @classmethod
    def from_api(cls, api: object, store: object, lang: object) -> _FakeResolver:
        _ = api, store, lang
        return cls(SimpleNamespace(value=10, value_label="Ten", unit="°C"))

    async def prefetch_param_mappings(self, symbols: Iterable[str]) -> None:
        self.prefetched.extend(list(symbols))

    async def resolve_value(self, symbol: str) -> object | None:
        if symbol == "MISSING":
            return None
        return self._resolved


@pytest.mark.asyncio
async def test_async_warm_status_resolver_builds_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()
    runtime._status_resolver = None
    monkeypatch.setattr(runtime_module, "ParamResolver", _FakeResolver)

    await runtime.async_warm_status_resolver(["STATUS_P5_0"])

    assert runtime._status_resolver is not None
    assert runtime.peek_status_label("STATUS_P5_0") == "Ten"
    assert runtime._status_resolver.prefetched == ["STATUS_P5_0"]


@pytest.mark.asyncio
async def test_async_warm_status_resolver_noop_without_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()
    runtime._status_resolver = None
    monkeypatch.setattr(runtime_module, "ParamResolver", _FakeResolver)

    await runtime.async_warm_status_resolver([])

    assert runtime._status_resolver is None


@pytest.mark.asyncio
async def test_async_resolve_status_label_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()
    monkeypatch.setattr(runtime_module, "ParamResolver", _FakeResolver)
    runtime._status_label_cache["STATUS_P5_0"] = "Cached"

    assert await runtime.async_resolve_status_label("STATUS_P5_0") == "Cached"


@pytest.mark.asyncio
async def test_async_resolve_status_label_uses_value_label(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()
    monkeypatch.setattr(runtime_module, "ParamResolver", _FakeResolver)

    assert await runtime.async_resolve_status_label("PARAM_1") is None
    assert await runtime.async_resolve_status_label("STATUS_P5_0") == "Ten"


@pytest.mark.asyncio
async def test_peek_status_label_rejects_non_status_symbols() -> None:
    runtime, _api, _gateway, _store = make_runtime()
    runtime._status_label_cache["STATUS_P5_0"] = "On"

    assert runtime.peek_status_label("PARAM_1") is None
    assert runtime.peek_status_label("STATUS_P5_0") == "On"


@pytest.mark.asyncio
async def test_async_warm_status_resolver_returns_when_resolver_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()

    class _BrokenFactory:
        @classmethod
        def from_api(cls, api: object, store: object, lang: object) -> None:
            _ = api, store, lang
            raise RuntimeError("factory failed")

    monkeypatch.setattr(runtime_module, "ParamResolver", _BrokenFactory)

    await runtime.async_warm_status_resolver(["STATUS_P5_0"])

    assert runtime._status_resolver is None
    assert runtime._status_label_cache == {}


@pytest.mark.asyncio
async def test_async_warm_status_resolver_prefetches_non_status_symbols_only(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()
    monkeypatch.setattr(runtime_module, "ParamResolver", _FakeResolver)

    await runtime.async_warm_status_resolver(["PARAM_14"])

    assert runtime._status_resolver is not None
    assert runtime._status_resolver.prefetched == ["PARAM_14"]
    assert runtime._status_label_cache == {}


@pytest.mark.asyncio
async def test_async_warm_status_resolver_skips_unresolved_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()

    class _EmptyLabelResolver(_FakeResolver):
        async def resolve_value(self, symbol: str) -> object | None:
            _ = symbol
            return SimpleNamespace(value=None, value_label="", unit=None)

    monkeypatch.setattr(runtime_module, "ParamResolver", _EmptyLabelResolver)

    await runtime.async_warm_status_resolver(["STATUS_P5_0", "STATUS_P5_1"])

    assert runtime._status_label_cache == {}


@pytest.mark.asyncio
async def test_async_resolve_status_label_populates_cache_on_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()
    monkeypatch.setattr(runtime_module, "ParamResolver", _FakeResolver)

    assert await runtime.async_resolve_status_label("STATUS_P5_0") == "Ten"
    assert runtime._status_label_cache["STATUS_P5_0"] == "Ten"


@pytest.mark.asyncio
async def test_resolve_status_label_uncached_returns_raw_value(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()

    class _RawValueResolver(_FakeResolver):
        async def resolve_value(self, symbol: str) -> object | None:
            _ = symbol
            return SimpleNamespace(value=42, value_label="", unit=None)

    monkeypatch.setattr(runtime_module, "ParamResolver", _RawValueResolver)

    assert await runtime._resolve_status_label_uncached("STATUS_P5_0") == 42


@pytest.mark.asyncio
async def test_dispatch_updates_clears_status_label_cache() -> None:
    runtime, _api, gateway, _store = make_runtime()
    runtime._status_label_cache["STATUS_P5_0"] = "On"
    cleared = asyncio.Event()

    def _listener(_update: FakeParamUpdate) -> None:
        cleared.set()

    runtime.add_listener(_listener)
    await runtime.start()
    try:
        gateway.bus.push(FakeParamUpdate(pool="P1", chan="v", idx=1))
        await asyncio.wait_for(cleared.wait(), timeout=1.0)
        assert runtime._status_label_cache == {}
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_dispatch_updates_logs_first_update_once() -> None:
    runtime, _api, gateway, _store = make_runtime()
    received = 0

    def _listener(_update: FakeParamUpdate) -> None:
        nonlocal received
        received += 1

    runtime.add_listener(_listener)
    await runtime.start()
    try:
        gateway.bus.push(FakeParamUpdate(pool="P1", chan="v", idx=1))
        gateway.bus.push(FakeParamUpdate(pool="P1", chan="v", idx=2))
        await asyncio.sleep(0.05)
        assert received == 2
        assert runtime._first_update_logged is True
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_async_resolve_status_label_returns_none_for_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()

    class _MissingStatusResolver(_FakeResolver):
        async def resolve_value(self, symbol: str) -> object | None:
            _ = symbol
            return None

    monkeypatch.setattr(runtime_module, "ParamResolver", _MissingStatusResolver)

    assert await runtime.async_resolve_status_label("STATUS_MISSING") is None
    assert "STATUS_MISSING" not in runtime._status_label_cache


@pytest.mark.asyncio
async def test_resolve_status_label_uncached_returns_none_when_resolver_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()

    class _MissingStatusResolver(_FakeResolver):
        async def resolve_value(self, symbol: str) -> object | None:
            _ = symbol
            return None

    monkeypatch.setattr(runtime_module, "ParamResolver", _MissingStatusResolver)

    assert await runtime._resolve_status_label_uncached("STATUS_MISSING") is None


@pytest.mark.asyncio
async def test_async_resolve_symbol_with_unit_handles_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()
    monkeypatch.setattr(runtime_module, "ParamResolver", _FakeResolver)

    assert await runtime.async_resolve_symbol_with_unit("MISSING") == (None, None)


@pytest.mark.asyncio
async def test_async_warm_status_resolver_continues_when_prefetch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()

    class _FailingPrefetchResolver(_FakeResolver):
        async def prefetch_param_mappings(self, symbols: Iterable[str]) -> None:
            _ = symbols
            raise RuntimeError("prefetch failed")

    monkeypatch.setattr(runtime_module, "ParamResolver", _FailingPrefetchResolver)

    await runtime.async_warm_status_resolver(["STATUS_P5_0"])

    assert runtime._status_resolver is not None
    assert runtime._status_label_cache == {}


@pytest.mark.asyncio
async def test_async_get_resolver_is_idempotent_under_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()
    runtime._status_resolver = None
    monkeypatch.setattr(runtime_module, "ParamResolver", _FakeResolver)

    first, second = await asyncio.gather(
        runtime._async_get_resolver(),
        runtime._async_get_resolver(),
    )

    assert first is second


@pytest.mark.asyncio
async def test_async_get_resolver_reuses_instance_for_lock_waiter(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, _api, _gateway, _store = make_runtime()
    runtime._status_resolver = None
    monkeypatch.setattr(runtime_module, "ParamResolver", _FakeResolver)

    await runtime._resolver_lock.acquire()
    pending = asyncio.create_task(runtime._async_get_resolver())
    await asyncio.sleep(0)
    runtime._status_resolver = _FakeResolver.from_api(runtime.api, runtime.store, runtime.language)
    runtime._resolver_lock.release()

    assert await pending is runtime._status_resolver


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


@pytest.mark.asyncio
async def test_dispatch_upserts_store_before_route_visibility() -> None:
    """Route visibility must see this delta, not a stale ParamStore snapshot."""
    runtime, _api, gateway, store = make_runtime()
    seen: list[object] = []
    refreshed = asyncio.Event()

    async def _refresh(_self: BragerRuntime, symbols: set[str] | None = None) -> None:
        _ = symbols
        seen.append(_self.store.flatten().get("P6.v219"))
        refreshed.set()

    await runtime.start()
    try:
        runtime._route_visibility_dep_to_symbols["P6.v219"] = {"PARAM_177"}
        with patch.object(BragerRuntime, "refresh_route_visibility", _refresh):
            gateway.bus.push(FakeParamUpdate(pool="P6", chan="v", idx=219, value=7))
            await asyncio.wait_for(refreshed.wait(), timeout=1.0)
            assert seen == [7]
            assert store.flatten()["P6.v219"] == 7
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_dispatch_skips_store_upsert_when_value_is_none() -> None:
    """None deltas are ignored, matching ParamStore.run_with_bus."""
    runtime, _api, gateway, store = make_runtime(flat_values={"P6.v219": 1})
    delivered = asyncio.Event()
    runtime.add_listener(lambda _update: delivered.set())
    await runtime.start()
    try:
        gateway.bus.push(FakeParamUpdate(pool="P6", chan="v", idx=219, value=None))
        await asyncio.wait_for(delivered.wait(), timeout=1.0)
        assert store.flatten()["P6.v219"] == 1
    finally:
        await runtime.stop()
