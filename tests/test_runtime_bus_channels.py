"""Runtime multi-event bus channel bridge (#285)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.runtime import BragerRuntime  # noqa: E402
from tests.helpers.fakes import FakeGateway, make_runtime  # noqa: E402


@pytest.mark.asyncio
async def test_runtime_prefers_bus_channels_over_callbacks() -> None:
    """With subscribe_channel, runtime does not register gateway on_* callbacks."""
    runtime, _api, gateway, _store = make_runtime(bus_channels=True)
    await runtime.start()
    assert runtime.supports_bus_channels is True
    assert gateway._connectivity_callbacks == []
    assert gateway._cloud_session_callbacks == []
    assert gateway._live_push_callbacks == []
    assert gateway._alarm_quantity_callbacks == []
    assert gateway._alarm_feed_invalidate_callbacks == []
    assert gateway._activity_feed_invalidate_callbacks == []
    await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_falls_back_to_callbacks_without_channels() -> None:
    """Older bus without subscribe_channel still uses on_* registration."""
    runtime, _api, gateway, _store = make_runtime(bus_channels=False)
    await runtime.start()
    assert runtime.supports_bus_channels is False
    assert runtime._on_gateway_connectivity in gateway._connectivity_callbacks
    assert runtime._on_gateway_cloud_session in gateway._cloud_session_callbacks
    await runtime.stop()


@pytest.mark.asyncio
async def test_bus_channel_events_drive_runtime_listeners() -> None:
    """Channel events update connectivity / session and schedule feed refresh."""
    runtime, _api, gateway, _store = make_runtime(bus_channels=True)
    seen_conn: list[tuple[str, bool, bool]] = []
    seen_session: list[tuple[bool, bool]] = []
    runtime.add_connectivity_listener(lambda devid, online, flipped: seen_conn.append((devid, online, flipped)))
    runtime.add_cloud_session_listener(lambda up, changed: seen_session.append((up, changed)))
    refresh_alarms = AsyncMock()
    refresh_activity = AsyncMock()

    with (
        patch.object(BragerRuntime, "async_refresh_alarms", refresh_alarms),
        patch.object(BragerRuntime, "async_refresh_activity", refresh_activity),
    ):
        await runtime.start()
        await asyncio.sleep(0)

        gateway.emit_connectivity("DEV1", False, source="ws")
        gateway.emit_cloud_session(False, source="disconnect")
        gateway.emit_alarm_feed_invalidate("DEV1", reason="change")
        gateway.emit_activity_feed_invalidate("DEV1", reason="task")
        gateway.emit_alarm_quantity("DEV1", 2)
        for _ in range(20):
            await asyncio.sleep(0)

        assert any(item[0] == "DEV1" and item[1] is False for item in seen_conn)
        assert any(item[0] is False for item in seen_session)
        assert refresh_alarms.await_count >= 2
        assert refresh_activity.await_count >= 1
        await runtime.stop()


@pytest.mark.asyncio
async def test_callback_fallback_still_receives_emits() -> None:
    """Callback path remains functional when channels are disabled."""
    runtime, _api, gateway, _store = make_runtime(bus_channels=False)
    seen: list[bool] = []
    runtime.add_cloud_session_listener(lambda up, _changed: seen.append(up))
    await runtime.start()
    gateway.emit_cloud_session(False, source="disconnect")
    await asyncio.sleep(0)
    assert False in seen
    await runtime.stop()


@pytest.mark.asyncio
async def test_make_runtime_with_explicit_gateway_bus_channels_flag() -> None:
    """Explicit FakeGateway(bus_channels=...) is honoured by make_runtime."""
    gateway = FakeGateway(bus_channels=True)
    runtime, _api, gw, _store = make_runtime(gateway=gateway)
    assert gw is gateway
    await runtime.start()
    assert runtime.supports_bus_channels is True
    assert gateway._connectivity_callbacks == []
    await runtime.stop()
