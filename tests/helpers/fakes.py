"""Fake py-bragerone / runtime collaborators for offline unit tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, ClassVar


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

    modules: ClassVar[list[object]] = []

    def __init__(self, *, start_error: Exception | None = None, start_delay: bool = False) -> None:
        self.bus = FakeBus()
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

    async def stop(self) -> None:
        self.stopped = True


class FakeStore:
    """ParamStore stand-in with flatten() and cancellable run_with_bus()."""

    def __init__(self, *, flat_values: dict[str, object] | None = None) -> None:
        self._flat = dict(flat_values or {})
        self.run_started = False
        self.run_cancelled = False

    def flatten(self) -> dict[str, object]:
        return dict(self._flat)

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
