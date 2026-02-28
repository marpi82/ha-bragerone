import asyncio
import sys
from types import SimpleNamespace

import pytest

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.bootstrap import (  # noqa: E402
    _collect_symbols_from_menu,
    _normalize_filter_mode,
    async_build_bootstrap_payload,
)
from custom_components.habragerone.const import DEFAULT_ENTITY_FILTER_MODE  # noqa: E402


def _param(token: str) -> SimpleNamespace:
    return SimpleNamespace(token=token)


def _container(*tokens: str) -> SimpleNamespace:
    return SimpleNamespace(read=[_param(token) for token in tokens], write=[], status=[], special=[])


def test_collect_symbols_from_menu_walks_nested_routes() -> None:
    leaf = SimpleNamespace(
        meta=SimpleNamespace(parameters=_container("LEAF_A")),
        parameters=_container("LEAF_B"),
        children=[],
    )
    root = SimpleNamespace(
        meta=SimpleNamespace(parameters=_container("ROOT_A")),
        parameters=_container("ROOT_B"),
        children=[leaf],
    )
    menu = SimpleNamespace(routes=[root])

    symbols = _collect_symbols_from_menu(menu)

    assert symbols == {"ROOT_A", "ROOT_B", "LEAF_A", "LEAF_B"}


def test_normalize_filter_mode_defaults_for_unknown_values() -> None:
    assert _normalize_filter_mode("ui") == "ui"
    assert _normalize_filter_mode("permissions") == "permissions"
    assert _normalize_filter_mode("unexpected") == DEFAULT_ENTITY_FILTER_MODE


def test_async_build_bootstrap_payload_applies_filter_mode_per_module(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {}

    class _FakeResolver:
        def __init__(self) -> None:
            self._current_devid = ""

        @classmethod
        def from_api(cls, api: object, store: object, lang: object) -> "_FakeResolver":
            return cls()

        async def build_panel_groups(
            self,
            *,
            device_menu: str,
            permissions: list[str] | None,
            all_panels: bool,
        ) -> dict[str, list[str]]:
            _ = permissions, all_panels
            return {"panel": [f"SYM_{device_menu}"]}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            return {
                symbol: {
                    "label": symbol,
                    "pool": "P4",
                    "chan": "v",
                    "idx": 1,
                    "mapping": {},
                    "min": None,
                    "max": None,
                    "unit": None,
                }
                for symbol in symbols
            }

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            if not isinstance(context, dict):
                self._current_devid = ""
                return
            self._current_devid = str(context.get("devid", ""))

        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            _ = symbol
            return SimpleNamespace(value=1, value_label="1")

        def parameter_visibility_diagnostics(
            self,
            *,
            desc: dict[str, object],
            resolved: object,
            flat_values: dict[str, object],
        ) -> tuple[bool, dict[str, object]]:
            _ = desc, resolved, flat_values
            return self._current_devid != "M1", {}

    class _FakeGateway:
        def model_dump(self, mode: str = "json") -> dict[str, object]:
            _ = mode
            return {}

    class _FakeApi:
        async def get_modules(self, object_id: int) -> list[SimpleNamespace]:
            _ = object_id
            return [
                SimpleNamespace(
                    devid="M1",
                    name="Module 1",
                    moduleTitle="Module 1",
                    moduleVersion="1.0",
                    gateway=_FakeGateway(),
                    moduleInterface="if1",
                    moduleAddress="addr1",
                    permissions=[],
                    deviceMenu="M1",
                    connectedAt="now",
                ),
                SimpleNamespace(
                    devid="M2",
                    name="Module 2",
                    moduleTitle="Module 2",
                    moduleVersion="1.0",
                    gateway=_FakeGateway(),
                    moduleInterface="if2",
                    moduleAddress="addr2",
                    permissions=[],
                    deviceMenu="M2",
                    connectedAt="now",
                ),
            ]

        async def modules_parameters_prime(
            self, module_ids: list[str], return_data: bool = False
        ) -> tuple[int, dict[str, object]]:
            _ = module_ids, return_data
            return 200, {}

    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _FakeResolver)

    payload = asyncio.run(
        async_build_bootstrap_payload(
            api=_FakeApi(),
            object_id=1,
            modules=["M1", "M2"],
            language="en",
            entity_filter_mode="ui",
            module_filter_modes={"M1": "ui", "M2": "permissions"},
        )
    )

    symbols = {(item["devid"], item["symbol"]) for item in payload["entity_descriptors"]}
    assert symbols == {("M2", "SYM_M2")}
