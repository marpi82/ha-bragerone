"""Fake py-bragerone / runtime collaborators for offline unit tests."""

from __future__ import annotations

import asyncio
import time
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
        self._live_push_callbacks: list[Any] = []
        self._alarm_quantity_callbacks: list[Any] = []
        self._ws_session_up = False
        self._last_param_update_age_s: float | None = None
        self._last_live_param_update_age_s: float | None = None
        self._cloud_outage: dict[str, float | str | None] = {}
        self._live_push: dict[str, float | bool | None] = {}
        self._module_outage: dict[str, dict[str, float | str | None]] = {}
        self._connectivity_episodes: list[dict[str, float | str | None]] = []
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

    def on_live_push(self, callback: Any) -> None:
        """Register a LivePushHealth callback (mirrors BragerOneGateway)."""
        self._live_push_callbacks.append(callback)

    def on_alarm_quantity(self, callback: Any) -> None:
        """Register an AlarmQuantityChanged callback (mirrors BragerOneGateway)."""
        self._alarm_quantity_callbacks.append(callback)

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

    def cloud_session_outage(self) -> dict[str, float | str | None]:
        """Return fake cloud-session outage snapshot."""
        return dict(self._cloud_outage)

    def live_push_health(self) -> dict[str, float | bool | None]:
        """Return fake live-push health snapshot."""
        return dict(self._live_push)

    def module_outage(self, devid: str) -> dict[str, float | str | None]:
        """Return fake module outage snapshot for *devid*."""
        snapshot = self._module_outage.get(devid)
        return dict(snapshot) if isinstance(snapshot, dict) else {}

    def connectivity_episodes(self) -> list[dict[str, float | str | None]]:
        """Return fake completed connectivity episodes (oldest → newest)."""
        return [dict(item) for item in self._connectivity_episodes]

    def last_param_update_age_s(self) -> float | None:
        """Return seconds since the last fake ParamUpdate, or ``None``."""
        age = self._last_param_update_age_s
        if isinstance(age, bool) or not isinstance(age, int | float):
            return None
        return float(age)

    def last_live_param_update_age_s(self) -> float | None:
        """Return seconds since the last fake live WS ParamUpdate, or ``None``."""
        age = self._last_live_param_update_age_s
        if isinstance(age, bool) or not isinstance(age, int | float):
            return None
        return float(age)

    def emit_connectivity(
        self,
        devid: str,
        online: bool,
        *,
        connected_at: int | None = None,
        source: str = "derived",
        gateway: dict[str, object] | None = None,
        down_since: float | None = None,
        down_for_s: float | None = None,
        reason: str | None = None,
        last_down_for_s: float | None = None,
        last_reason: str | None = None,
    ) -> None:
        """Update online cache and notify registered connectivity callbacks."""
        if connected_at is not None:
            self._connected_at[devid] = connected_at
        if gateway is not None:
            self._gateway[devid] = dict(gateway)
        previous = self._online.get(devid)
        self._online[devid] = online
        if not online and (previous is None or previous is True):
            self._module_outage[devid] = {
                "down_since": down_since if down_since is not None else time.time(),
                "down_for_s": down_for_s if down_for_s is not None else 0.0,
                "reason": reason if reason is not None else source,
                "last_down_for_s": self._module_outage.get(devid, {}).get("last_down_for_s"),
                "last_reason": self._module_outage.get(devid, {}).get("last_reason"),
            }
        elif online and previous is False:
            prior = self._module_outage.get(devid, {})
            duration = last_down_for_s if last_down_for_s is not None else prior.get("down_for_s")
            ended_reason = last_reason if last_reason is not None else prior.get("reason")
            last_down: float | None = None
            if not isinstance(duration, bool) and isinstance(duration, (int, float)):
                last_down = float(duration)
            self._module_outage[devid] = {
                "down_since": None,
                "down_for_s": None,
                "reason": None,
                "last_down_for_s": last_down,
                "last_reason": str(ended_reason) if isinstance(ended_reason, str) else source,
            }
        outage = self._module_outage.get(devid, {})
        event = types.SimpleNamespace(
            devid=devid,
            online=online,
            source=source,
            connected_at=connected_at if connected_at is not None else self._connected_at.get(devid),
            gateway=self._gateway.get(devid),
            online_changed=True,
            metadata_changed=False,
            down_since=outage.get("down_since"),
            down_for_s=outage.get("down_for_s"),
            reason=outage.get("reason"),
            last_down_for_s=outage.get("last_down_for_s"),
            last_reason=outage.get("last_reason"),
        )
        for callback in list(self._connectivity_callbacks):
            callback(event)

    def emit_cloud_session(
        self,
        up: bool,
        *,
        source: str = "disconnect",
        changed: bool = True,
        down_since: float | None = None,
        down_for_s: float | None = None,
        reason: str | None = None,
        last_down_for_s: float | None = None,
        last_reason: str | None = None,
    ) -> None:
        """Update session cache and notify registered cloud-session callbacks."""
        previous = self._ws_session_up
        self._ws_session_up = up
        if not up and previous:
            self._cloud_outage = {
                "down_since": down_since if down_since is not None else time.time(),
                "down_for_s": down_for_s if down_for_s is not None else 0.0,
                "reason": reason if reason is not None else source,
                "last_down_for_s": self._cloud_outage.get("last_down_for_s"),
                "last_reason": self._cloud_outage.get("last_reason"),
            }
        elif up and previous is False and self._cloud_outage.get("down_since") is not None:
            prior = self._cloud_outage
            duration = last_down_for_s if last_down_for_s is not None else prior.get("down_for_s")
            ended_reason = last_reason if last_reason is not None else prior.get("reason")
            last_down: float | None = None
            if not isinstance(duration, bool) and isinstance(duration, (int, float)):
                last_down = float(duration)
            self._cloud_outage = {
                "down_since": None,
                "down_for_s": None,
                "reason": None,
                "last_down_for_s": last_down,
                "last_reason": str(ended_reason) if isinstance(ended_reason, str) else source,
            }
        event = types.SimpleNamespace(
            up=up,
            source=source,
            changed=changed or previous is not up,
            down_since=self._cloud_outage.get("down_since"),
            down_for_s=self._cloud_outage.get("down_for_s"),
            reason=self._cloud_outage.get("reason"),
            last_down_for_s=self._cloud_outage.get("last_down_for_s"),
            last_reason=self._cloud_outage.get("last_reason"),
        )
        for callback in list(self._cloud_session_callbacks):
            callback(event)

    def emit_live_push(
        self,
        *,
        healthy: bool | None,
        live_stale_for_s: float | None = None,
        last_resumed_after_s: float | None = None,
        changed: bool = True,
    ) -> None:
        """Update live-push cache and notify registered callbacks."""
        self._live_push = {
            "push_healthy": healthy,
            "live_stale_for_s": live_stale_for_s,
            "last_resumed_after_s": last_resumed_after_s
            if last_resumed_after_s is not None
            else self._live_push.get("last_resumed_after_s"),
        }
        event = types.SimpleNamespace(
            healthy=healthy,
            live_stale_for_s=self._live_push.get("live_stale_for_s"),
            last_resumed_after_s=self._live_push.get("last_resumed_after_s"),
            changed=changed,
        )
        for callback in list(self._live_push_callbacks):
            callback(event)


class FakeStore:
    """ParamStore stand-in with flatten() and cancellable run_with_bus()."""

    def __init__(self, *, flat_values: dict[str, object] | None = None) -> None:
        self._flat = dict(flat_values or {})
        self._by_devid: dict[str, dict[str, object]] = {}
        self.run_started = False
        self.run_cancelled = False

    def flatten(self) -> dict[str, object]:
        return dict(self._flat)

    def flatten_for_devid(self, devid: str) -> dict[str, object]:
        bucket = self._by_devid.get(devid)
        if bucket is None:
            return {}
        return dict(bucket)

    def upsert(self, key: str, value: object, *, devid: str | None = None) -> None:
        """Mirror ``ParamStore.upsert`` so dispatch can apply deltas before flatten()."""
        if devid is not None:
            bucket = self._by_devid.setdefault(devid, {})
            bucket[str(key)] = value
        self._flat[str(key)] = value

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
