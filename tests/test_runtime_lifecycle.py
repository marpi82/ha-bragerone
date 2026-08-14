"""Tests for BragerRuntime lifecycle, listeners, and update dispatch."""

from __future__ import annotations

import asyncio

import pytest

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from tests.helpers.fakes import FakeParamUpdate, make_runtime  # noqa: E402


@pytest.mark.asyncio
async def test_runtime_start_and_stop_cancels_background_tasks() -> None:
    runtime, _api, gateway, store = make_runtime()
    await runtime.start()
    await asyncio.sleep(0)
    assert gateway.started
    assert store.run_started
    assert len(runtime._tasks) == 2

    await runtime.stop()
    assert store.run_cancelled
    assert gateway.stopped


@pytest.mark.asyncio
async def test_runtime_start_failure_cancels_tasks_and_reraises() -> None:
    runtime, _api, _gateway, store = make_runtime(start_error=RuntimeError("gateway failed"), start_delay=True)
    with pytest.raises(RuntimeError, match="gateway failed"):
        await runtime.start()
    assert runtime._tasks == []
    assert store.run_cancelled


@pytest.mark.asyncio
async def test_runtime_dispatches_updates_to_listeners() -> None:
    runtime, _api, gateway, _store = make_runtime()
    received: list[FakeParamUpdate] = []
    received_event = asyncio.Event()

    def _on_update(update: FakeParamUpdate) -> None:
        received.append(update)
        received_event.set()

    runtime.add_listener(_on_update)
    await runtime.start()

    update = FakeParamUpdate(pool="P1", chan="v", idx=2, value=21.5)
    gateway.bus.push(update)
    await asyncio.wait_for(received_event.wait(), timeout=1.0)

    assert received == [update]
    await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_listener_unsubscribe_stops_delivery() -> None:
    runtime, _api, gateway, _store = make_runtime()
    received: list[FakeParamUpdate] = []

    remove = runtime.add_listener(received.append)
    remove()

    await runtime.start()
    gateway.bus.push(FakeParamUpdate(pool="P1", chan="v", idx=1))
    await asyncio.sleep(0.05)

    assert received == []
    await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_listener_exception_does_not_stop_dispatcher() -> None:
    runtime, _api, gateway, _store = make_runtime()
    delivered: list[FakeParamUpdate] = []
    delivered_event = asyncio.Event()

    def _failing_listener(_update: FakeParamUpdate) -> None:
        raise RuntimeError("listener boom")

    def _healthy_listener(update: FakeParamUpdate) -> None:
        delivered.append(update)
        delivered_event.set()

    runtime.add_listener(_failing_listener)
    runtime.add_listener(_healthy_listener)
    await runtime.start()

    gateway.bus.push(FakeParamUpdate(pool="P2", chan="s", idx=0))
    await asyncio.wait_for(delivered_event.wait(), timeout=1.0)
    assert delivered

    await runtime.stop()
