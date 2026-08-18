"""Fake py-bragerone / runtime collaborators for offline unit tests."""

from __future__ import annotations

import asyncio
import types
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeParamUpdate:
    """Minimal ParamUpdate stand-in for runtime dispatch tests."""

    pool: str
    chan: str
    idx: int
    devid: str = "DEV1"
    value: Any = None
    meta: dict[str, Any] = field(default_factory=dict)


class FakeBus:
    """Async bus that yields pushed updates until closed."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[FakeParamUpdate | None] = asyncio.Queue()

    async def subscribe(self) -> AsyncIterator[FakeParamUpdate]:
        while True:
            update = await self._queue.get()
            if update is None:
                break
            yield update

    def push(self, update: FakeParamUpdate) -> None:
        self._queue.put_nowait(update)

    def close(self) -> None:
        self._queue.put_nowait(None)


class FakeApi:
    """Records module_command_auto calls; configurable success flag."""

    def __init__(self, *, succeed: bool = True) -> None:
        self.calls: list[dict[str, object]] = []
        self._succeed = succeed

    async def module_command_auto(self, **kwargs: object) -> bool:
        self.calls.append(kwargs)
        return self._succeed

    async def close(self) -> None:
        return None


class FakeGateway:
    """Gateway with controllable start/stop and a fake event bus."""

    def __init__(
        self,
        *,
        start_error: Exception | None = None,
        start_delay: bool = False,
        modules: list[str] | None = None,
    ) -> None:
        self.bus = FakeBus()
        self.modules: list[str] = list(modules) if modules is not None else ["DEV1"]
        self._online: dict[str, bool] = {}
        self._connected_at: dict[str, int] = {}
        self._gateway: dict[str, dict[str, object]] = {}
        self._connectivity_callbacks: list[Any] = []
        self._cloud_session_callbacks: list[Any] = []
        self._ws_session_up = False
        self._start_error = start_error
        self._start_delay = start_delay
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        if self._start_delay:
            await asyncio.sleep(0)
        if self._start_error is not None:
            raise self._start_error
        self.started = True
        self.emit_cloud_session(True, source="connect")

    async def stop(self) -> None:
        self.stopped = True
        self.emit_cloud_session(False, source="stop")

    def on_module_connectivity(self, callback: Any) -> None:
        """Register a ModuleConnectivity callback (mirrors BragerOneGateway)."""
        self._connectivity_callbacks.append(callback)

    def on_cloud_session(self, callback: Any) -> None:
        """Register a CloudSessionConnectivity callback (mirrors BragerOneGateway)."""
        self._cloud_session_callbacks.append(callback)

    def module_online(self, devid: str) -> bool | None:
        """Return cached online flag, or ``None`` when unknown."""
        return self._online.get(devid)

    def module_connected_at(self, devid: str) -> int | None:
        """Return cached REST ``connectedAt`` epoch seconds when known."""
        return self._connected_at.get(devid)

    def module_gateway(self, devid: str) -> dict[str, object] | None:
        """Return cached gateway blob when known."""
        gateway = self._gateway.get(devid)
        return dict(gateway) if isinstance(gateway, dict) else None

    def ws_session_up(self) -> bool:
        """Return whether the fake Socket.IO session is up."""
        return self._ws_session_up

    def last_param_update_age_s(self) -> float | None:
        """Return seconds since the last fake ParamUpdate, or ``None``."""
        return getattr(self, "_last_param_update_age_s", None)

    def emit_connectivity(
        self,
        devid: str,
        online: bool,
        *,
        connected_at: int | None = None,
        source: str = "derived",
        gateway: dict[str, object] | None = None,
    ) -> None:
        """Update online cache and notify registered connectivity callbacks."""
        if connected_at is not None:
            self._connected_at[devid] = connected_at
        if gateway is not None:
            self._gateway[devid] = dict(gateway)
        self._online[devid] = online
        event = types.SimpleNamespace(
            devid=devid,
            online=online,
            source=source,
            connected_at=connected_at if connected_at is not None else self._connected_at.get(devid),
            gateway=self._gateway.get(devid),
            online_changed=True,
            metadata_changed=False,
        )
        for callback in list(self._connectivity_callbacks):
            callback(event)

    def emit_cloud_session(self, up: bool, *, source: str = "disconnect", changed: bool = True) -> None:
        """Update session cache and notify registered cloud-session callbacks."""
        previous = self._ws_session_up
        self._ws_session_up = up
        event = types.SimpleNamespace(up=up, source=source, changed=changed or previous is not up)
        for callback in list(self._cloud_session_callbacks):
            callback(event)


class FakeStore:
    """ParamStore stand-in with flatten() and cancellable run_with_bus()."""

    def __init__(self, *, flat_values: dict[str, object] | None = None) -> None:
        self._flat = dict(flat_values or {})
        self.run_started = False
        self.run_cancelled = False

    def flatten(self) -> dict[str, object]:
        return dict(self._flat)

    def get_family(self, pool: str, idx: int) -> dict[str, object] | None:
        """Return channel map for one ParamStore family (``P<n>.<chan><idx>`` keys)."""
        family: dict[str, object] = {}
        for key, value in self._flat.items():
            if not isinstance(key, str) or "." not in key:
                continue
            key_pool, rest = key.split(".", 1)
            if key_pool != pool or len(rest) < 2:
                continue
            chan = rest[0]
            try:
                key_idx = int(rest[1:])
            except ValueError:
                continue
            if key_idx == idx:
                family[chan] = value
        return family or None

    async def run_with_bus(self, _bus: object) -> None:
        self.run_started = True
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.run_cancelled = True
            raise


def make_runtime(
    *,
    api: FakeApi | None = None,
    gateway: FakeGateway | None = None,
    store: FakeStore | None = None,
    flat_values: dict[str, object] | None = None,
    modules_meta: dict[str, dict[str, Any]] | None = None,
    start_error: Exception | None = None,
    start_delay: bool = False,
) -> tuple[Any, FakeApi, FakeGateway, FakeStore]:
    """Build a BragerRuntime wired to fake collaborators."""
    from custom_components.habragerone.runtime import BragerRuntime

    fake_api = api or FakeApi()
    fake_gateway = gateway or FakeGateway(start_error=start_error, start_delay=start_delay)
    fake_store = store or FakeStore(flat_values=flat_values)
    runtime = BragerRuntime(
        api=fake_api,  # type: ignore[arg-type]
        gateway=fake_gateway,  # type: ignore[arg-type]
        store=fake_store,  # type: ignore[arg-type]
        modules_meta=modules_meta or {},
    )
    return runtime, fake_api, fake_gateway, fake_store


def param_update(**kwargs: Any) -> FakeParamUpdate:
    """Shorthand for FakeParamUpdate with SimpleNamespace-compatible fields."""
    return FakeParamUpdate(**kwargs)
