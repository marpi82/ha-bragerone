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


class _BootstrapResolverRouteStubMixin:
    """Static ParamResolver hooks used during bootstrap route metadata (#192)."""

    @staticmethod
    def _iter_routes_with_ancestors(routes: object) -> list[tuple[object, tuple[object, ...]]]:
        _ = routes
        return []

    @staticmethod
    def _status_paths_for_visibility(mapping: object, flat_values: object) -> list[dict[str, object]]:
        _ = mapping, flat_values
        return []

    @staticmethod
    def route_visibility_dependency_keys(route: object, ancestors: object = ()) -> list[str]:
        _ = route, ancestors
        return []

    @staticmethod
    def panel_route_diagnostics_from_menu(*args: object, **kwargs: object) -> list[dict[str, object]]:
        _ = args, kwargs
        return []


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

    class _FakeResolver(_BootstrapResolverRouteStubMixin):
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
            flat_values: object | None = None,
        ) -> dict[str, list[str]]:
            _ = permissions, all_panels, web_ui_only, flat_values
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

    class _FakeResolver(_BootstrapResolverRouteStubMixin):
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
            flat_values: object | None = None,
        ) -> dict[str, list[str]]:
            _ = device_menu, permissions, all_panels, web_ui_only, flat_values
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


def test_async_build_bootstrap_payload_enabled_default_edge_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover non-UI routes, visibility/resolve failures, and extras synthetic paths (#212)."""

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
                        "name": "Extras",
                        "parameters": {
                            "read": [{"parameter": {"token": "PARAM_READ_ONLY"}}],
                            "write": [
                                {"parameter": {"token": "COMMAND_UNRESOLVED_RESTART"}},
                                {"parameter": {"token": "PARAM_WRITE_NO_RULE"}},
                                {"parameter": {"token": "PARAM_WRITE_MISSING"}},
                            ],
                            "status": [],
                            "special": [],
                        },
                        "children": [],
                    }
                ]
            }

    class _FakeResolver(_BootstrapResolverRouteStubMixin):
        def __init__(self) -> None:
            self._assets = _FakeAssets()
            self._describe_calls = 0

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
            flat_values: object | None = None,
        ) -> dict[str, list[str]]:
            _ = device_menu, permissions, all_panels, flat_values
            # Full permission set includes installer-only symbols; everyday UI only sees SYM_UI.
            if web_ui_only:
                return {"Kocioł": ["SYM_UI", "SYM_VIS_FAIL", "SYM_RESOLVE_FAIL"]}
            return {
                "Kocioł": ["SYM_UI", "SYM_VIS_FAIL", "SYM_RESOLVE_FAIL"],
                "Installer": ["SYM_NON_UI"],
            }

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            self._describe_calls += 1
            # Extras batch is the second describe_symbols call in this fixture — fail it so
            # command-like tokens stay unresolved for the synthetic-button path below.
            if self._describe_calls == 2:
                raise RuntimeError("extras describe failed")
            payload: dict[str, dict[str, object]] = {}
            for symbol in symbols:
                if symbol.startswith("COMMAND_") or symbol in {"PARAM_WRITE_MISSING", "PARAM_WRITE_NO_RULE"}:
                    continue
                payload[symbol] = {
                    "label": symbol,
                    "pool": "P4",
                    "chan": "v",
                    "idx": 1,
                    "mapping": {},
                    "min": None,
                    "max": None,
                    "unit": None,
                }
            return payload

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            _ = context

        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            if symbol == "SYM_RESOLVE_FAIL":
                raise RuntimeError("resolve failed")
            return SimpleNamespace(value=1, value_label="1")

        def parameter_visibility_diagnostics(
            self,
            *,
            desc: dict[str, object],
            resolved: object,
            flat_values: dict[str, object],
        ) -> tuple[bool, dict[str, object]]:
            _ = resolved, flat_values
            label = str(desc.get("label") or "")
            if label == "SYM_VIS_FAIL":
                raise RuntimeError("visibility failed")
            return True, {}

        def panel_route_diagnostics_from_menu(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            _ = args, kwargs
            return []

        class _I18n:
            async def get_namespace(self, _name: str) -> dict[str, object]:
                return {}

        _i18n = _I18n()

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
    assert descriptors["SYM_UI"]["enabled_by_default"] is True
    # Visibility diagnostics blew up → fail-open to enabled for UI-route symbols.
    assert descriptors["SYM_VIS_FAIL"]["enabled_by_default"] is True
    # resolve_value blew up → enabled_by_default follows the UI-route flag (True here).
    assert descriptors["SYM_RESOLVE_FAIL"]["enabled_by_default"] is True
    # Present in permission panels but not everyday UI routes → disabled by default.
    assert descriptors["SYM_NON_UI"]["enabled_by_default"] is False
    # Unresolved command-like extra becomes a synthetic disabled button.
    assert descriptors["COMMAND_UNRESOLVED_RESTART"]["enabled_by_default"] is False
    assert descriptors["COMMAND_UNRESOLVED_RESTART"]["platform"] == "button"
    # Read-only / write-without-command extras must not invent entities.
    assert "PARAM_READ_ONLY" not in descriptors
    assert "PARAM_WRITE_NO_RULE" not in descriptors
    assert "PARAM_WRITE_MISSING" not in descriptors


def test_async_build_bootstrap_payload_skips_extra_write_without_command_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extras with write kind but no named command rule must not become entities (#212)."""

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
                        "name": "Extras",
                        "parameters": {
                            "read": [],
                            "write": [{"parameter": {"token": "PARAM_WRITE_EMPTY_RULES"}}],
                            "status": [],
                            "special": [],
                        },
                        "children": [],
                    }
                ]
            }

    class _FakeResolver(_BootstrapResolverRouteStubMixin):
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
            flat_values: object | None = None,
        ) -> dict[str, list[str]]:
            _ = device_menu, permissions, all_panels, web_ui_only, flat_values
            return {"Kocioł": ["SYM_PANEL"]}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            payload: dict[str, dict[str, object]] = {}
            for symbol in symbols:
                if symbol == "PARAM_WRITE_EMPTY_RULES":
                    payload[symbol] = {
                        "label": symbol,
                        "pool": None,
                        "chan": None,
                        "idx": None,
                        "mapping": {"command_rules": []},
                        "min": None,
                        "max": None,
                        "unit": None,
                    }
                else:
                    payload[symbol] = {
                        "label": symbol,
                        "pool": "P4",
                        "chan": "v",
                        "idx": 1,
                        "mapping": {},
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

    symbols = {item["symbol"] for item in payload["entity_descriptors"]}
    assert symbols == {"SYM_PANEL"}
    assert "PARAM_WRITE_EMPTY_RULES" not in symbols


def test_async_build_bootstrap_payload_skips_extra_with_non_action_command_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extras whose command name is not action-like must not be accepted (#212)."""

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
                        "name": "Extras",
                        "parameters": {
                            "read": [],
                            "write": [
                                {"parameter": {"token": "SYM_PANEL"}},
                                {"parameter": {"token": "PARAM_WRITE_HARMLESS"}},
                            ],
                            "status": [],
                            "special": [],
                        },
                        "children": [],
                    }
                ]
            }

    class _FakeResolver(_BootstrapResolverRouteStubMixin):
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
            flat_values: object | None = None,
        ) -> dict[str, list[str]]:
            _ = device_menu, permissions, all_panels, web_ui_only, flat_values
            return {"Kocioł": ["SYM_PANEL"]}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            payload: dict[str, dict[str, object]] = {}
            for symbol in symbols:
                if symbol == "PARAM_WRITE_HARMLESS":
                    payload[symbol] = {
                        "label": symbol,
                        "pool": None,
                        "chan": None,
                        "idx": None,
                        "mapping": {"command_rules": [{"command": "SET_FOO", "value": 1}]},
                        "min": None,
                        "max": None,
                        "unit": None,
                    }
                else:
                    payload[symbol] = {
                        "label": symbol,
                        "pool": "P4",
                        "chan": "v",
                        "idx": 1,
                        "mapping": {},
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

    symbols = {item["symbol"] for item in payload["entity_descriptors"]}
    assert symbols == {"SYM_PANEL"}
    assert "PARAM_WRITE_HARMLESS" not in symbols


def test_async_build_bootstrap_payload_accepts_sample_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accepted-debug samples stop growing after 500 symbols (#212)."""

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P4.v1": 42}

    symbols_all = [f"SYM_{idx}" for idx in range(510)]

    class _FakeResolver(_BootstrapResolverRouteStubMixin):
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
            flat_values: object | None = None,
        ) -> dict[str, list[str]]:
            _ = device_menu, permissions, all_panels, web_ui_only, flat_values
            return {"Kocioł": list(symbols_all)}

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

    assert len(payload["entity_descriptors"]) == 510
    debug = payload.get("bootstrap_debug") or {}
    module_debug = (debug.get("modules") or {}).get("M1") or {}
    accepted_debug = module_debug.get("accepted_debug")
    assert isinstance(accepted_debug, list)
    assert len(accepted_debug) == 500
