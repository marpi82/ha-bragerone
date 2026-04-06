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
        async def subscribe(self):  # pragma: no cover - not used in this test
            if False:
                yield None

    bus = _FakeBus()

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class _FakeStore:
    def flatten(self) -> dict[str, object]:
        return {}

    async def run_with_bus(self, _bus: object) -> None:  # pragma: no cover - not used in this test
        return None


def test_async_write_parameter_route_includes_parameter_name_from_mapping_raw() -> None:
    api = _FakeApi()
    runtime = BragerRuntime(
        api=api,
        gateway=_FakeGateway(),
        store=_FakeStore(),
        modules_meta={},
    )
    descriptor = {
        "symbol": "PARAM_0",
        "devid": "DEV1",
        "pool": "P6",
        "chan": "v",
        "idx": 0,
        "mapping": {"raw": {"name": "parameters.PARAM_0"}, "command_rules": []},
    }

    asyncio.run(runtime.async_write(descriptor=descriptor, input_display_value=77.0))

    assert len(api.calls) == 1
    assert api.calls[0]["pool"] == "P6"
    assert api.calls[0]["parameter"] == "v0"
    assert api.calls[0]["parameter_name"] == "parameters.PARAM_0"
