from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from typing import Any, cast

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
        meta=SimpleNamespace(parameters=_container("PARAM_LEAF_A")),
        parameters=_container("PARAM_LEAF_B"),
        children=[],
    )
    root = SimpleNamespace(
        meta=SimpleNamespace(parameters=_container("PARAM_ROOT_A")),
        parameters=_container("PARAM_ROOT_B"),
        children=[leaf],
    )
    menu = SimpleNamespace(routes=[root])

    symbols = _collect_symbols_from_menu(menu)

    assert symbols == {"PARAM_ROOT_A", "PARAM_ROOT_B", "PARAM_LEAF_A", "PARAM_LEAF_B"}


def test_normalize_filter_mode_defaults_for_unknown_values() -> None:
    """``_normalize_filter_mode`` is deprecated (#212) but kept for old-cache reads."""
    assert _normalize_filter_mode("ui") == "ui"
    assert _normalize_filter_mode("permissions") == "permissions"
    assert _normalize_filter_mode("unexpected") == DEFAULT_ENTITY_FILTER_MODE


def test_async_build_bootstrap_payload_creates_every_permitted_entity_and_gates_enabled_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All permission-gated symbols become entities (#212); UI-invisible ones start disabled."""

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P4.v1": 42}

    class _FakeResolver:
        def __init__(self) -> None:
            self._current_devid = ""

        @classmethod
        def from_api(cls, api: object, store: object, lang: object) -> _FakeResolver:
            return cls()

        async def build_panel_groups(
            self,
            *,
            device_menu: str,
            permissions: list[str] | None,
            all_panels: bool,
            web_ui_only: bool = False,
        ) -> dict[str, list[str]]:
            _ = permissions, all_panels, web_ui_only
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
            api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
            object_id=1,
            modules=["M1", "M2"],
            language="en",
        )
    )

    descriptors = {(item["devid"], item["symbol"]): item for item in payload["entity_descriptors"]}
    # Both modules' permission-gated symbols are created, unlike the old UI-filter behavior
    # that dropped M1 entirely.
    assert set(descriptors) == {("M1", "SYM_M1"), ("M2", "SYM_M2")}
    # M1's symbol fails the SPA visibility check (fake resolver ties visibility to devid),
    # so it is created but disabled by default; M2's passes and stays enabled.
    assert descriptors[("M1", "SYM_M1")]["enabled_by_default"] is False
    assert descriptors[("M2", "SYM_M2")]["enabled_by_default"] is True


def test_async_build_bootstrap_payload_includes_non_panel_actions_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-panel command actions (permissions-only extras) are created but disabled by default."""

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P4.v1": 42}

    class _FakeAssets:
        async def get_module_menu(
            self,
            *,
            device_menu: str,
            permissions: list[str] | None,
        ) -> dict[str, object]:
            _ = device_menu, permissions
            return {
                "routes": [
                    {
                        "name": "Actions",
                        "parameters": {
                            "read": [],
                            "write": [{"parameter": {"token": "COMMAND_MODULE_RESTART"}}],
                            "status": [],
                            "special": [],
                        },
                        "children": [],
                    }
                ]
            }

    class _FakeResolver:
        def __init__(self) -> None:
            self._assets = _FakeAssets()

        @classmethod
        def from_api(cls, api: object, store: object, lang: object) -> _FakeResolver:
            _ = api, store, lang
            return cls()

        async def build_panel_groups(
            self,
            *,
            device_menu: str,
            permissions: list[str] | None,
            all_panels: bool,
            web_ui_only: bool = False,
        ) -> dict[str, list[str]]:
            _ = device_menu, permissions, all_panels, web_ui_only
            return {"Kocioł": ["SYM_PANEL"]}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            payload: dict[str, dict[str, object]] = {}
            for symbol in symbols:
                payload[symbol] = {
                    "label": symbol,
                    "pool": "P4" if symbol == "SYM_PANEL" else None,
                    "chan": "v" if symbol == "SYM_PANEL" else None,
                    "idx": 1 if symbol == "SYM_PANEL" else None,
                    "mapping": ({} if symbol == "SYM_PANEL" else {"command_rules": [{"command": "MODULE_RESTART", "value": 1}]}),
                    "min": None,
                    "max": None,
                    "unit": None,
                }
            return payload

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            _ = context

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
            return True, {}

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
                )
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
            api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
            object_id=1,
            modules=["M1"],
            language="en",
        )
    )

    descriptors = {item["symbol"]: item for item in payload["entity_descriptors"]}
    assert set(descriptors) == {"SYM_PANEL", "COMMAND_MODULE_RESTART"}
    # SYM_PANEL is on the everyday-UI route and SPA-visible, so it stays enabled.
    assert descriptors["SYM_PANEL"]["enabled_by_default"] is True
    # COMMAND_MODULE_RESTART is a permissions-only extra outside any panel/UI route.
    assert descriptors["COMMAND_MODULE_RESTART"]["enabled_by_default"] is False
