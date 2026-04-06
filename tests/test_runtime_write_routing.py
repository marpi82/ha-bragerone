import asyncio
from typing import ClassVar

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.runtime import BragerRuntime  # noqa: E402


class _FakeApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def module_command_auto(self, **kwargs: object) -> bool:
        self.calls.append(kwargs)
        return True

    async def close(self) -> None:
        return None


class _FakeGateway:
    modules: ClassVar[list[object]] = []

    class _FakeBus:
        async def subscribe(self):  # pragma: no cover - not used in these tests
            if False:
                yield None

    bus = _FakeBus()

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class _FakeStore:
    def __init__(self, *, flat_values: dict[str, object]) -> None:
        self._flat = dict(flat_values)

    def flatten(self) -> dict[str, object]:
        return dict(self._flat)

    async def run_with_bus(self, _bus: object) -> None:  # pragma: no cover - not used in these tests
        return None


def test_async_write_prefers_raw_command_rule_over_parameter_address() -> None:
    api = _FakeApi()
    runtime = BragerRuntime(
        api=api,
        gateway=_FakeGateway(),
        store=_FakeStore(flat_values={"P5.s0": 0}),
        modules_meta={"DEV1": {"connectedAt": "2026-04-06T10:00:00Z"}},
    )
    descriptor = {
        "symbol": "URUCHOMIENIE_KOTLA",
        "devid": "DEV1",
        "pool": "P5",
        "chan": "s",
        "idx": 0,
        "mapping": {
            "command_rules": [
                {
                    "operation": "ignored",
                    "conditions": [{"operation": "equalTo", "expected": 0, "targets": [{"address": "P5.s0", "bit": 0}]}],
                    "command": "BOILER_START",
                    "value": "OFF",
                },
                {
                    "conditions": [{"operation": "equalTo", "expected": 1, "targets": [{"address": "P5.s0", "bit": 0}]}],
                    "command": "BOILER_STOP",
                    "value": "ON",
                },
            ]
        },
    }

    asyncio.run(runtime.async_write(descriptor=descriptor, input_display_value=True))

    assert len(api.calls) == 1
    assert api.calls[0]["command"] == "BOILER_START"
    assert api.calls[0]["value"] == "OFF"
    assert "pool" not in api.calls[0]
    assert "parameter" not in api.calls[0]


def test_async_write_uses_descriptor_address_when_rule_conditions_have_no_targets() -> None:
    api = _FakeApi()
    runtime = BragerRuntime(
        api=api,
        gateway=_FakeGateway(),
        store=_FakeStore(flat_values={"P5.s0": 1}),
        modules_meta={"DEV1": {}},
    )
    descriptor = {
        "symbol": "URUCHOMIENIE_KOTLA",
        "devid": "DEV1",
        "pool": "P5",
        "chan": "s",
        "idx": 0,
        "mapping": {
            "command_rules": [
                {"conditions": [{"operation": "equalTo", "expected": 0}], "command": "BOILER_START", "value": "OFF"},
                {"conditions": [{"operation": "equalTo", "expected": 1}], "command": "BOILER_STOP", "value": "ON"},
                {"conditions": [], "command": "void 0"},
            ]
        },
    }

    asyncio.run(runtime.async_write(descriptor=descriptor, input_display_value=False))

    assert len(api.calls) == 1
    assert api.calls[0]["command"] == "BOILER_STOP"
    assert api.calls[0]["value"] == "ON"


def test_async_write_prefers_intent_rule_for_start_stop_commands() -> None:
    api = _FakeApi()
    runtime = BragerRuntime(
        api=api,
        gateway=_FakeGateway(),
        store=_FakeStore(flat_values={"P5.s0": 0}),
        modules_meta={"DEV1": {}},
    )
    descriptor = {
        "symbol": "URUCHOMIENIE_KOTLA",
        "devid": "DEV1",
        "pool": "P5",
        "chan": "s",
        "idx": 0,
        "mapping": {
            "command_rules": [
                {"conditions": [{"operation": "equalTo", "expected": 0}], "command": "BOILER_START", "value": "OFF"},
                {"conditions": [{"operation": "equalTo", "expected": 1}], "command": "BOILER_STOP", "value": "ON"},
            ]
        },
    }

    asyncio.run(runtime.async_write(descriptor=descriptor, input_display_value=False))

    assert len(api.calls) == 1
    assert api.calls[0]["command"] == "BOILER_STOP"
