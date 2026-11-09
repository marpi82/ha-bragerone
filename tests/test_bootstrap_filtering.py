from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from typing import Any, cast

import pytest

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.bootstrap import (  # noqa: E402
    BootstrapTransientError,
    _collect_symbols_from_menu,
    _normalize_filter_mode,
    async_build_bootstrap_payload,
)
from custom_components.habragerone.const import CONF_UI_ROUTE_SYMBOL, DEFAULT_ENTITY_FILTER_MODE  # noqa: E402


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
    # Everyday-UI symbols that fail SPA visibility are not materialised (#341).
    # M1's fake resolver returns not-visible; M2's passes and is created enabled.
    assert set(descriptors) == {("M2", "SYM_M2")}
    assert descriptors[("M2", "SYM_M2")]["enabled_by_default"] is True
    m1_rejections = payload["bootstrap_debug"]["modules"]["M1"]["rejections"]
    assert any(row.get("reason") == "hidden:spa_visibility" for row in m1_rejections)


def test_async_build_bootstrap_payload_expands_composite_value_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multi-slot describe payloads become one entity per SPA value_slot (#339)."""

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P31.s12": 1, "P30.v25": 40}

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
            return {"panel": ["STATUS_POMPY", "PARAM_PASSWORD"]}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            payload: dict[str, dict[str, object]] = {
                "STATUS_POMPY": {
                    "label": "Heat pump status",
                    "pool": "P31",
                    "chan": "s",
                    "idx": 12,
                    "mapping": {"component_type": "STATUS"},
                    "min": None,
                    "max": None,
                    "unit": {"0": "Off", "1": "On"},
                    "value_slots": [
                        {"slot": "value", "pool": "P31", "chan": "s", "idx": 12},
                        {"slot": "value2", "pool": "P30", "chan": "v", "idx": 25},
                        {"slot": "value3", "pool": "P29", "chan": "v", "idx": 1},
                    ],
                },
                "PARAM_PASSWORD": {
                    "label": "Installer password",
                    "pool": "P1",
                    "chan": "v",
                    "idx": 9,
                    "mapping": {"component_type": "password"},
                    "min": None,
                    "max": None,
                    "unit": None,
                },
            }
            return {symbol: payload[symbol] for symbol in symbols if symbol in payload}

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            _ = context

        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            _ = symbol
            return SimpleNamespace(value=1, value_label="On")

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

    import custom_components.habragerone.bootstrap as bootstrap_mod

    real_finalize = bootstrap_mod._finalize_slot_descriptor

    def _finalize_drop_value3(descriptor: dict[str, object]) -> dict[str, object] | None:
        if str(descriptor.get("symbol") or "").endswith("#value3"):
            return None
        return real_finalize(descriptor)

    monkeypatch.setattr(bootstrap_mod, "_finalize_slot_descriptor", _finalize_drop_value3)

    payload = asyncio.run(
        async_build_bootstrap_payload(
            api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
            object_id=1,
            modules=["M1"],
            language="en",
        )
    )

    by_symbol = {item["symbol"]: item for item in payload["entity_descriptors"]}
    assert set(by_symbol) == {"STATUS_POMPY", "STATUS_POMPY#value2"}
    assert by_symbol["STATUS_POMPY"]["pool"] == "P31"
    assert by_symbol["STATUS_POMPY"]["chan"] == "s"
    assert by_symbol["STATUS_POMPY#value2"]["pool"] == "P30"
    assert by_symbol["STATUS_POMPY#value2"]["chan"] == "v"
    assert by_symbol["STATUS_POMPY#value2"]["label"] == "Heat pump status (value2)"


def test_async_build_bootstrap_payload_dedupes_rules_per_module_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Identical address+rule on two modules must both keep a descriptor."""

    rules = [{"else": "OFF"}]
    mapping = {"paths": {"value": rules}, "component_type": "STATUS"}

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P0.s1": 0}

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
            return {"panel": ["STATUS_PUMP"]}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            return {
                symbol: {
                    "symbol": symbol,
                    "label": "Pump",
                    "pool": "P0",
                    "chan": "s",
                    "idx": 1,
                    "mapping": mapping,
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
            return SimpleNamespace(value=0, value_label="Off")

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
                    devid=devid,
                    name=devid,
                    moduleTitle=devid,
                    moduleVersion="1.0",
                    gateway=_FakeGateway(),
                    moduleInterface="if1",
                    moduleAddress="addr1",
                    permissions=[],
                    deviceMenu=devid,
                    connectedAt="now",
                )
                for devid in ("M1", "M2")
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
    by_module = {(item["devid"], item["symbol"]) for item in payload["entity_descriptors"]}
    assert by_module == {("M1", "STATUS_PUMP"), ("M2", "STATUS_PUMP")}


def test_async_build_bootstrap_payload_discovers_status_bar_and_dedupes_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STATUS_BAR_* tokens join candidates; shared address+rule collapses duplicates."""

    rules = [
        {
            "if": [{"expected": None, "operation": "equalTo", "value": [{"group": "P0", "number": 1, "use": "s"}]}],
            "then": None,
        },
        {"else": "OFF"},
    ]
    mapping = {"paths": {"value": rules}, "component_type": "STATUS"}

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P0.s1": 0}

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
            return {"panel": ["STATUS_PUMP"]}

        async def discover_status_bar_parameter_tokens(self) -> set[object]:
            return {"STATUS_BAR_PUMP", 12}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            payload: dict[str, dict[str, object]] = {
                "STATUS_PUMP": {
                    "label": "Pump",
                    "pool": "P0",
                    "chan": "s",
                    "idx": 1,
                    "mapping": mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                },
                "STATUS_BAR_PUMP": {
                    "label": "Footer pump",
                    "pool": "P0",
                    "chan": "s",
                    "idx": 1,
                    "mapping": mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                },
            }
            return {symbol: payload[symbol] for symbol in symbols if symbol in payload}

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            _ = context

        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            _ = symbol
            return SimpleNamespace(value=0, value_label="Off")

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

    assert payload["bootstrap_debug"]["status_bar_tokens"] == ["STATUS_BAR_PUMP"]
    symbols = {item["symbol"] for item in payload["entity_descriptors"]}
    # First accepted address+rule wins; the footer duplicate is rejected.
    assert symbols == {"STATUS_PUMP"}
    rejections = payload["bootstrap_debug"]["modules"]["M1"]["rejections"]
    assert any(row.get("reason") == "duplicate_address_rule" for row in rejections)


def test_async_build_bootstrap_payload_rejects_schedules_and_undefined_status_bar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schedule composites and absent STATUS_BAR diodes must not become entities."""

    schedule_mapping = {
        "paths": {
            "value": [
                {
                    "if": [{"expected": None, "operation": "equalTo", "value": [{"group": "P6", "number": 177, "use": "v"}]}],
                    "then": None,
                },
                {"else": [{"group": "P12", "number": 0, "use": "a"}, {"group": "P12", "number": 0, "use": "b"}]},
            ]
        }
    }
    status_bar_mapping = {
        "paths": {
            "value": [
                {
                    "if": [{"expected": 1, "operation": "equalTo", "value": [{"group": "P31", "number": 12, "use": "s"}]}],
                    "then": "ON",
                },
                # SPA heat-pump footers end in ``else: null`` when the register is absent.
                {"else": None},
            ]
        }
    }
    live_status_mapping = {
        "paths": {
            "value": [
                {
                    "if": [{"expected": 1, "operation": "equalTo", "value": [{"group": "P5", "number": 11, "use": "s"}]}],
                    "then": "ON",
                },
                {"else": "OFF"},
            ]
        }
    }

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            # Live pump status present; heat-pump compressor register absent.
            return {"P5.s11": 1}

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
            return {"panel": ["PARAM_P12_0", "STATUS_PUMP"]}

        async def discover_status_bar_parameter_tokens(self) -> set[object]:
            return {"STATUS_BAR_COMPRESSOR", "STATUS_BAR_BLOWER"}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            # Blower has an ``else: OFF`` fallback — evaluate yields a label even without raw.
            blower_mapping = {
                "paths": {
                    "value": [
                        {
                            "if": [
                                {
                                    "expected": 1,
                                    "operation": "equalTo",
                                    "value": [{"group": "P31", "number": 55, "use": "s"}],
                                }
                            ],
                            "then": "ON",
                        },
                        {"else": "OFF"},
                    ]
                }
            }
            payload: dict[str, dict[str, object]] = {
                "PARAM_P12_0": {
                    "label": "Schedule",
                    "pool": "P6",
                    "chan": "v",
                    "idx": 177,
                    "mapping": schedule_mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                    "writable": True,
                },
                "STATUS_PUMP": {
                    "label": "Pump",
                    "pool": "P5",
                    "chan": "s",
                    "idx": 11,
                    "mapping": live_status_mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                },
                "STATUS_BAR_COMPRESSOR": {
                    "label": "Compressor",
                    "pool": "P31",
                    "chan": "s",
                    "idx": 12,
                    "mapping": status_bar_mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                },
                "STATUS_BAR_BLOWER": {
                    "label": "Blower",
                    "pool": "P31",
                    "chan": "s",
                    "idx": 55,
                    "mapping": blower_mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                },
            }
            return {symbol: payload[symbol] for symbol in symbols if symbol in payload}

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            _ = context

        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            if symbol == "STATUS_PUMP":
                return SimpleNamespace(value="ON", value_label="On")
            return SimpleNamespace(value=None, value_label=None)

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
    # else: OFF without a live register must not become an unavailable entity.
    assert symbols == {"STATUS_PUMP"}
    rejections = payload["bootstrap_debug"]["modules"]["M1"]["rejections"]
    assert any(row.get("symbol") == "PARAM_P12_0" and row.get("reason") == "no_display_value" for row in rejections)
    assert any(
        row.get("symbol") == "STATUS_BAR_COMPRESSOR" and row.get("reason") == "undefined_status_rules" for row in rejections
    )
    assert any(row.get("symbol") == "STATUS_BAR_BLOWER" and row.get("reason") == "undefined_status_rules" for row in rejections)


def test_async_build_bootstrap_payload_keeps_status_bar_when_register_is_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STATUS_BAR diodes with a live register and rule label stay entities."""

    mapping = {
        "paths": {
            "value": [
                {
                    "if": [{"expected": 1, "operation": "equalTo", "value": [{"group": "P31", "number": 12, "use": "s"}]}],
                    "then": "ON",
                },
                {"else": "OFF"},
            ]
        }
    }

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P31.s12": 0}

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
            return {"panel": ["STATUS_BAR_LIVE"]}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            return {
                "STATUS_BAR_LIVE": {
                    "label": "Live",
                    "pool": "P31",
                    "chan": "s",
                    "idx": 12,
                    "mapping": mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                }
            }

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            _ = context

        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            _ = symbol
            return SimpleNamespace(value=None, value_label=None)

        def parameter_visibility_diagnostics(
            self,
            *,
            desc: dict[str, object],
            resolved: object,
            flat_values: dict[str, object],
        ) -> tuple[bool, dict[str, object]]:
            _ = desc, resolved, flat_values
            return True, {}

    class _FakeApi:
        async def get_modules(self, object_id: int) -> list[SimpleNamespace]:
            _ = object_id
            return [
                SimpleNamespace(
                    devid="M1",
                    name="Module 1",
                    moduleTitle="Module 1",
                    moduleVersion="1.0",
                    gateway=SimpleNamespace(model_dump=lambda mode="json": {}),
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
    assert {item["symbol"] for item in payload["entity_descriptors"]} == {"STATUS_BAR_LIVE"}


def test_async_build_bootstrap_payload_rejects_null_guard_despite_secondary_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matched then:null must reject even when a secondary mapping.inputs address is live."""

    spa_then_null_mapping = {
        "paths": {
            "value": [
                {
                    "if": [
                        {
                            "expected": None,
                            "operation": "equalTo",
                            "value": [{"group": "P31", "number": 50, "use": "s"}],
                        }
                    ],
                    "then": None,
                },
                {"else": "OFF"},
            ]
        },
        "inputs": [{"address": "P31.s12", "bit": 0, "mask": 1}],
    }

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            # Primary existence guard target absent; companion input populated.
            return {"P31.s12": 1}

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
            return {"panel": ["STATUS_BAR_NULL_GUARD"]}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            return {
                "STATUS_BAR_NULL_GUARD": {
                    "label": "Null guard",
                    "pool": "P31",
                    "chan": "s",
                    "idx": 50,
                    "mapping": spa_then_null_mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                }
            }

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            _ = context

        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            _ = symbol
            return SimpleNamespace(value=None, value_label=None)

        def parameter_visibility_diagnostics(
            self,
            *,
            desc: dict[str, object],
            resolved: object,
            flat_values: dict[str, object],
        ) -> tuple[bool, dict[str, object]]:
            _ = desc, resolved, flat_values
            return True, {}

    class _FakeApi:
        async def get_modules(self, object_id: int) -> list[SimpleNamespace]:
            _ = object_id
            return [
                SimpleNamespace(
                    devid="M1",
                    name="Module 1",
                    moduleTitle="Module 1",
                    moduleVersion="1.0",
                    gateway=SimpleNamespace(model_dump=lambda mode="json": {}),
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
    assert payload["entity_descriptors"] == []
    rejections = payload["bootstrap_debug"]["modules"]["M1"]["rejections"]
    assert any(
        row.get("symbol") == "STATUS_BAR_NULL_GUARD" and row.get("reason") == "undefined_status_rules" for row in rejections
    )


def test_async_build_bootstrap_payload_caps_undefined_status_rejection_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """undefined_status_rules still drop entities after the 500-row sample fills."""

    fillers = [f"SYM_FILL_{idx}" for idx in range(500)]
    status_bar_mapping = {
        "paths": {
            "value": [
                {
                    "if": [{"expected": 1, "operation": "equalTo", "value": [{"group": "P31", "number": 12, "use": "s"}]}],
                    "then": "ON",
                },
                {"else": None},
            ]
        }
    }

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {}

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
            return {"panel": [*fillers, "STATUS_BAR_COMPRESSOR"]}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            payload: dict[str, dict[str, object]] = {
                "STATUS_BAR_COMPRESSOR": {
                    "label": "Compressor",
                    "pool": "P31",
                    "chan": "s",
                    "idx": 12,
                    "mapping": status_bar_mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                },
            }
            for symbol in fillers:
                payload[symbol] = {
                    "label": symbol,
                    "pool": "P9",
                    "chan": "v",
                    "idx": 0,
                    "mapping": {},
                    "min": None,
                    "max": None,
                    "unit": None,
                }
            return {symbol: payload[symbol] for symbol in symbols if symbol in payload}

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            _ = context

        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            _ = symbol
            return SimpleNamespace(value=None, value_label=None)

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
    assert payload["entity_descriptors"] == []
    rejections = payload["bootstrap_debug"]["modules"]["M1"]["rejections"]
    assert len(rejections) == 500
    assert all(row.get("reason") == "no_display_value" for row in rejections)
    # Still omitted even though the rejection sample no longer records them.
    assert "STATUS_BAR_COMPRESSOR" not in {row.get("symbol") for row in rejections}


def test_async_build_bootstrap_payload_raises_on_prime_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed primes must not produce a cacheable empty descriptor set."""

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {}

    class _FakeResolver(_BootstrapResolverRouteStubMixin):
        @classmethod
        def from_api(cls, api: object, store: object, lang: object) -> _FakeResolver:
            _ = api, store, lang
            return cls()

    class _FakeApi:
        async def get_modules(self, object_id: int) -> list[SimpleNamespace]:
            _ = object_id
            return [
                SimpleNamespace(
                    devid="M1",
                    name="Module 1",
                    moduleTitle="Module 1",
                    moduleVersion="1.0",
                    gateway=SimpleNamespace(model_dump=lambda mode="json": {}),
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
            return 503, {}

    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _FakeResolver)

    with pytest.raises(BootstrapTransientError, match="HTTP 503"):
        asyncio.run(
            async_build_bootstrap_payload(
                api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
                object_id=1,
                modules=["M1"],
                language="en",
            )
        )


def test_async_build_bootstrap_payload_accepts_prime_204_without_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 204 may omit a body; bootstrap continues with an empty prime store."""

    class _FakeParamStore:
        def __init__(self) -> None:
            self.ingested: list[dict[str, object]] = []

        def ingest_prime_payload(self, payload: dict[str, object]) -> None:
            self.ingested.append(payload)

        def flatten(self) -> dict[str, object]:
            return {}

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
            return {"panel": ["SYM_UI"]}

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

    store = _FakeParamStore()

    class _FakeApi:
        async def get_modules(self, object_id: int) -> list[SimpleNamespace]:
            _ = object_id
            return [
                SimpleNamespace(
                    devid="M1",
                    name="Module 1",
                    moduleTitle="Module 1",
                    moduleVersion="1.0",
                    gateway=SimpleNamespace(model_dump=lambda mode="json": {}),
                    moduleInterface="if1",
                    moduleAddress="addr1",
                    permissions=[],
                    deviceMenu="M1",
                    connectedAt="now",
                )
            ]

        async def modules_parameters_prime(self, module_ids: list[str], return_data: bool = False) -> tuple[int, object]:
            _ = module_ids, return_data
            return 204, None

    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", lambda: store)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _FakeResolver)

    payload = asyncio.run(
        async_build_bootstrap_payload(
            api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
            object_id=1,
            modules=["M1"],
            language="en",
        )
    )
    assert store.ingested == []
    assert {item["symbol"] for item in payload["entity_descriptors"]} == {"SYM_UI"}


def test_async_build_bootstrap_payload_raises_on_prime_non_dict_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 200 with a non-dict body is treated as a retryable prime failure."""

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {}

    class _FakeResolver(_BootstrapResolverRouteStubMixin):
        @classmethod
        def from_api(cls, api: object, store: object, lang: object) -> _FakeResolver:
            _ = api, store, lang
            return cls()

    class _FakeApi:
        async def get_modules(self, object_id: int) -> list[SimpleNamespace]:
            _ = object_id
            return [
                SimpleNamespace(
                    devid="M1",
                    name="Module 1",
                    moduleTitle="Module 1",
                    moduleVersion="1.0",
                    gateway=SimpleNamespace(model_dump=lambda mode="json": {}),
                    moduleInterface="if1",
                    moduleAddress="addr1",
                    permissions=[],
                    deviceMenu="M1",
                    connectedAt="now",
                )
            ]

        async def modules_parameters_prime(self, module_ids: list[str], return_data: bool = False) -> tuple[int, object]:
            _ = module_ids, return_data
            return 200, ["not", "a", "dict"]

    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _FakeResolver)

    with pytest.raises(BootstrapTransientError, match="non-dict"):
        asyncio.run(
            async_build_bootstrap_payload(
                api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
                object_id=1,
                modules=["M1"],
                language="en",
            )
        )


def test_async_build_bootstrap_payload_raises_on_unexpected_prime_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-tuple prime responses must abort before any cache write."""

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {}

    class _FakeResolver(_BootstrapResolverRouteStubMixin):
        @classmethod
        def from_api(cls, api: object, store: object, lang: object) -> _FakeResolver:
            _ = api, store, lang
            return cls()

    class _FakeApi:
        async def get_modules(self, object_id: int) -> list[SimpleNamespace]:
            _ = object_id
            return [
                SimpleNamespace(
                    devid="M1",
                    name="Module 1",
                    moduleTitle="Module 1",
                    moduleVersion="1.0",
                    gateway=SimpleNamespace(model_dump=lambda mode="json": {}),
                    moduleInterface="if1",
                    moduleAddress="addr1",
                    permissions=[],
                    deviceMenu="M1",
                    connectedAt="now",
                )
            ]

        async def modules_parameters_prime(self, module_ids: list[str], return_data: bool = False) -> int:
            _ = module_ids, return_data
            return 200

    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _FakeResolver)

    with pytest.raises(BootstrapTransientError, match="unexpected payload"):
        asyncio.run(
            async_build_bootstrap_payload(
                api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
                object_id=1,
                modules=["M1"],
                language="en",
            )
        )


def test_async_build_bootstrap_payload_raises_on_resolve_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-symbol resolve exceptions abort bootstrap so a partial cache is never persisted."""

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P4.v1": 1}

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
            return {"panel": ["SYM_OK", "SYM_RESOLVE_FAIL"]}

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
            _ = desc, resolved, flat_values
            return True, {}

    class _FakeApi:
        async def get_modules(self, object_id: int) -> list[SimpleNamespace]:
            _ = object_id
            return [
                SimpleNamespace(
                    devid="M1",
                    name="Module 1",
                    moduleTitle="Module 1",
                    moduleVersion="1.0",
                    gateway=SimpleNamespace(model_dump=lambda mode="json": {}),
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

    with pytest.raises(BootstrapTransientError, match="Symbol resolution failed"):
        asyncio.run(
            async_build_bootstrap_payload(
                api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
                object_id=1,
                modules=["M1"],
                language="en",
            )
        )


def test_async_build_bootstrap_payload_raises_on_resolve_failure_after_rejection_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve failures still abort bootstrap when the rejection sample is already full."""

    fillers = [f"SYM_FILL_{idx}" for idx in range(500)]

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {}

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
            return {"panel": [*fillers, "SYM_RESOLVE_FAIL"]}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            payload: dict[str, dict[str, object]] = {
                "SYM_RESOLVE_FAIL": {
                    "label": "Boom",
                    "pool": "P4",
                    "chan": "v",
                    "idx": 1,
                    "mapping": {},
                    "min": None,
                    "max": None,
                    "unit": None,
                }
            }
            for symbol in fillers:
                payload[symbol] = {
                    "label": symbol,
                    "pool": "P9",
                    "chan": "v",
                    "idx": 0,
                    "mapping": {},
                    "min": None,
                    "max": None,
                    "unit": None,
                }
            return {symbol: payload[symbol] for symbol in symbols if symbol in payload}

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            _ = context

        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            if symbol == "SYM_RESOLVE_FAIL":
                raise RuntimeError("resolve failed")
            return SimpleNamespace(value=None, value_label=None)

        def parameter_visibility_diagnostics(
            self,
            *,
            desc: dict[str, object],
            resolved: object,
            flat_values: dict[str, object],
        ) -> tuple[bool, dict[str, object]]:
            _ = desc, resolved, flat_values
            return True, {}

    class _FakeApi:
        async def get_modules(self, object_id: int) -> list[SimpleNamespace]:
            _ = object_id
            return [
                SimpleNamespace(
                    devid="M1",
                    name="Module 1",
                    moduleTitle="Module 1",
                    moduleVersion="1.0",
                    gateway=SimpleNamespace(model_dump=lambda mode="json": {}),
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

    with pytest.raises(BootstrapTransientError, match="Symbol resolution failed"):
        asyncio.run(
            async_build_bootstrap_payload(
                api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
                object_id=1,
                modules=["M1"],
                language="en",
            )
        )


def test_async_build_bootstrap_payload_prefers_ui_footer_over_installer_twin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Everyday-UI STATUS_BAR_* keeps the address key when the menu twin is installer-only."""

    rules = [{"else": "OFF"}]
    mapping = {"paths": {"value": rules}, "component_type": "STATUS"}

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P0.s1": 0}

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
            _ = device_menu, permissions, all_panels, flat_values
            if web_ui_only:
                return {}
            return {"installer": ["STATUS_INSTALLER_PUMP"]}

        async def discover_status_bar_parameter_tokens(self) -> set[object]:
            return {"STATUS_BAR_PUMP"}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            payload: dict[str, dict[str, object]] = {
                "STATUS_INSTALLER_PUMP": {
                    "label": "Installer pump",
                    "pool": "P0",
                    "chan": "s",
                    "idx": 1,
                    "mapping": mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                },
                "STATUS_BAR_PUMP": {
                    "label": "Footer pump",
                    "pool": "P0",
                    "chan": "s",
                    "idx": 1,
                    "mapping": mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                },
            }
            return {symbol: payload[symbol] for symbol in symbols if symbol in payload}

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            _ = context

        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            _ = symbol
            return SimpleNamespace(value=0, value_label="Off")

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

    by_symbol = {item["symbol"]: item for item in payload["entity_descriptors"]}
    assert set(by_symbol) == {"STATUS_BAR_PUMP"}
    assert by_symbol["STATUS_BAR_PUMP"].get("enabled_by_default") is True
    rejections = payload["bootstrap_debug"]["modules"]["M1"]["rejections"]
    assert any(
        row.get("symbol") == "STATUS_INSTALLER_PUMP" and row.get("reason") == "duplicate_address_rule" for row in rejections
    )


def test_async_build_bootstrap_payload_tolerates_status_bar_discovery_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Status-bar discovery errors / non-set results stay non-fatal."""

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P4.v1": 1}

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

    def _run_with_discover(discover) -> dict[str, object]:
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
                return {"panel": ["PARAM_1"]}

            async def discover_status_bar_parameter_tokens(self) -> object:
                return await discover()

            async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
                return {
                    "PARAM_1": {
                        "label": "Param",
                        "pool": "P4",
                        "chan": "v",
                        "idx": 1,
                        "mapping": {},
                        "min": None,
                        "max": None,
                        "unit": None,
                    }
                }

            def set_runtime_context(self, context: dict[str, object] | None) -> None:
                _ = context

            async def resolve_value(self, symbol: str) -> SimpleNamespace:
                _ = symbol
                return SimpleNamespace(value=1, value_label=None)

            def parameter_visibility_diagnostics(
                self,
                *,
                desc: dict[str, object],
                resolved: object,
                flat_values: dict[str, object],
            ) -> tuple[bool, dict[str, object]]:
                _ = desc, resolved, flat_values
                return True, {}

        monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
        monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _FakeResolver)
        return asyncio.run(
            async_build_bootstrap_payload(
                api=cast(Any, _FakeApi()),  # type: ignore[arg-type]
                object_id=1,
                modules=["M1"],
                language="en",
            )
        )

    async def _raise() -> set[str]:
        raise RuntimeError("offline assets")

    async def _list_result() -> list[str]:
        return ["STATUS_BAR_PUMP"]

    for discover in (_raise, _list_result):
        payload = _run_with_discover(discover)
        assert "status_bar_tokens" not in payload["bootstrap_debug"]
        assert {item["symbol"] for item in payload["entity_descriptors"]} == {"PARAM_1"}


def test_async_build_bootstrap_payload_skips_duplicate_sample_when_rejections_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate address+rule still drops the twin after the 500-row rejection sample fills."""

    hidden = [f"SYM_HIDDEN_{idx}" for idx in range(500)]
    rules = [{"else": "OFF"}]
    mapping = {"paths": {"value": rules}, "component_type": "STATUS"}

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P0.s1": 0}

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
            # Hidden first so rejection sample fills before address dedupe.
            return {"panel": [*hidden, "STATUS_PUMP"]}

        async def discover_status_bar_parameter_tokens(self) -> set[str]:
            return {"STATUS_BAR_PUMP"}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            payload: dict[str, dict[str, object]] = {
                "STATUS_PUMP": {
                    "symbol": "STATUS_PUMP",
                    "label": "Pump",
                    "pool": "P0",
                    "chan": "s",
                    "idx": 1,
                    "mapping": mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                },
                "STATUS_BAR_PUMP": {
                    "symbol": "STATUS_BAR_PUMP",
                    "label": "Footer pump",
                    "pool": "P0",
                    "chan": "s",
                    "idx": 1,
                    "mapping": mapping,
                    "min": None,
                    "max": None,
                    "unit": None,
                },
            }
            for symbol in hidden:
                payload[symbol] = {
                    "symbol": symbol,
                    "label": symbol,
                    "pool": "P9",
                    "chan": "v",
                    "idx": 0,
                    "mapping": {},
                    "min": None,
                    "max": None,
                    "unit": None,
                }
            return {symbol: payload[symbol] for symbol in symbols if symbol in payload}

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            _ = context

        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            _ = symbol
            return SimpleNamespace(value=0, value_label="Off")

        def parameter_visibility_diagnostics(
            self,
            *,
            desc: dict[str, object],
            resolved: object,
            flat_values: dict[str, object],
        ) -> tuple[bool, dict[str, object]]:
            _ = resolved, flat_values
            symbol = str(desc.get("symbol") or desc.get("label") or "")
            if symbol.startswith("SYM_HIDDEN_"):
                return False, {"reason": "hidden:test"}
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
    assert {item["symbol"] for item in payload["entity_descriptors"]} == {"STATUS_PUMP"}
    rejections = payload["bootstrap_debug"]["modules"]["M1"]["rejections"]
    assert len(rejections) == 500
    assert all(row.get("reason") != "duplicate_address_rule" for row in rejections)


def test_async_build_bootstrap_payload_caps_spa_visibility_rejection_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPA-hidden rejects keep excluding symbols after the 500-row diagnostic sample fills (#341)."""

    hidden_symbols = [f"SYM_HIDDEN_{idx}" for idx in range(501)]

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
            return {"panel": list(hidden_symbols)}

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
            return False, {"reason": "spa_hidden"}

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

    assert payload["entity_descriptors"] == []
    rejections = payload["bootstrap_debug"]["modules"]["M1"]["rejections"]
    assert len(rejections) == 500
    assert all(row.get("reason") == "hidden:spa_visibility" for row in rejections)


def test_async_build_bootstrap_payload_does_not_recreate_spa_hidden_ui_write_as_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPA-hidden everyday-UI write symbols must not reappear via the secondary extras pass (#341)."""

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
                        "name": "Boiler",
                        "parameters": {
                            "read": [],
                            "write": [{"parameter": {"token": "URUCHOMIENIE_KOTLA"}}],
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
            _ = device_menu, permissions, all_panels, flat_values
            # Present on both the full candidate set and the everyday-UI probe.
            if web_ui_only:
                return {"Boiler": ["URUCHOMIENIE_KOTLA"]}
            return {"Boiler": ["URUCHOMIENIE_KOTLA"]}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            return {
                symbol: {
                    "label": symbol,
                    "pool": "P4",
                    "chan": "v",
                    "idx": 1,
                    "mapping": {"command_rules": [{"command": "BOILER_START", "value": "OFF"}]},
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
            return SimpleNamespace(value=0, value_label="OFF")

        def parameter_visibility_diagnostics(
            self,
            *,
            desc: dict[str, object],
            resolved: object,
            flat_values: dict[str, object],
        ) -> tuple[bool, dict[str, object]]:
            _ = desc, resolved, flat_values
            return False, {"reason": "spa_hidden"}

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
    assert "URUCHOMIENIE_KOTLA" not in symbols
    rejections = payload["bootstrap_debug"]["modules"]["M1"]["rejections"]
    assert any(row.get("reason") == "hidden:spa_visibility" for row in rejections)


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
    """Cover non-UI routes, visibility failures, and extras synthetic paths (#212)."""

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
                return {"Kocioł": ["SYM_UI", "SYM_VIS_FAIL"]}
            return {
                "Kocioł": ["SYM_UI", "SYM_VIS_FAIL"],
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
            _ = symbol
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


def test_ui_route_index_ignores_bootstrap_flat_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """UI-route indexing stays structural; prime dropdown values only affect enabled_by_default."""
    structural_calls: list[tuple[bool, bool]] = []

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P6.v219": 0}

    class _FakeAssets:
        async def get_module_menu(self, *, device_menu: str, permissions: list[str] | None) -> dict[str, object]:
            _ = device_menu, permissions
            return {"routes": []}

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
            use_store_flat_values: bool = True,
        ) -> dict[str, list[str]]:
            _ = device_menu, permissions, all_panels, flat_values
            structural_calls.append((web_ui_only, use_store_flat_values))
            return {"Panel": ["SYM_DROPDOWN"]} if not use_store_flat_values else {}

        async def describe_symbols(self, symbols: list[str]) -> dict[str, dict[str, object]]:
            return {
                symbol: {
                    "label": symbol,
                    "pool": "P6",
                    "chan": "v",
                    "idx": 219,
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
            return True, {"reason": "visible:default"}

        def panel_route_diagnostics_from_menu(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            _ = args, kwargs
            return []

        class _I18n:
            async def get_namespace(self, _name: str) -> dict[str, object]:
                return {}

        _i18n = _I18n()

    class _FakeApi:
        async def get_modules(self, object_id: int) -> list[SimpleNamespace]:
            _ = object_id
            return [
                SimpleNamespace(
                    devid="M1",
                    name="Module 1",
                    moduleTitle="Module 1",
                    moduleVersion="1.0",
                    gateway=SimpleNamespace(model_dump=lambda mode="json": {}),
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

    descriptor = next(item for item in payload["entity_descriptors"] if item["symbol"] == "SYM_DROPDOWN")
    assert structural_calls == [(False, False), (True, False)]
    assert descriptor[CONF_UI_ROUTE_SYMBOL] is True
    assert descriptor["enabled_by_default"] is True
