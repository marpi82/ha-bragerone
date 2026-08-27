"""Bootstrap regression for static menu route shells (#192)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.habragerone.bootstrap import (
    _enrich_symbol_routes_from_shell_diagnostics,
    _primary_route_identity,
    _resolve_menu_key_for_symbol,
    _route_dep_index_from_menu,
    _route_visibility_deps_for_symbol,
    _stable_menu_key_from_route_meta,
)

_FIXTURE = (
    Path(__file__)
    .resolve()
    .parents[1]
    .joinpath(
        "..",
        "py-bragerone",
        "tests",
        "fixtures",
        "menu_strefy_czasowe.json",
    )
    .resolve()
)


def test_shell_diagnostics_skips_blank_titles() -> None:
    """Accepted shell rows without panel/title text are ignored."""
    diagnostics = [
        {
            "title": "",
            "panel_title": "   ",
            "name": "MAINMENU_X",
            "path": "x",
            "accepted": True,
            "panel_shell": True,
        }
    ]
    symbol_routes: dict[str, list[dict[str, Any]]] = {}
    _enrich_symbol_routes_from_shell_diagnostics({"PARAM_1": "Anything"}, symbol_routes, diagnostics)
    assert symbol_routes == {}


def test_shell_diagnostics_indexes_title_when_panel_title_missing() -> None:
    """Shell rows without panel_title still index under ``title``."""
    diagnostics = [
        {
            "title": "Strefy czasowe",
            "panel_title": "",
            "name": "MAINMENU_STREFY_CZASOWE",
            "path": "timezones",
            "accepted": True,
            "panel_shell": True,
        }
    ]
    symbol_routes: dict[str, list[dict[str, Any]]] = {}
    _enrich_symbol_routes_from_shell_diagnostics({"PARAM_177": "Strefy czasowe"}, symbol_routes, diagnostics)
    assert symbol_routes["PARAM_177"][0]["path"] == "timezones"


def test_route_dep_index_skips_routes_without_name_or_path() -> None:
    """Routes with blank name and path are omitted from the dep index."""
    menu = SimpleNamespace(
        routes=[
            SimpleNamespace(
                name="",
                path="",
                meta=None,
                children=[],
                component=None,
            )
        ]
    )
    assert _route_dep_index_from_menu(menu) == {}


def test_route_visibility_deps_handles_payload_edge_cases() -> None:
    """Non-mapping payloads and malformed status paths contribute no deps."""
    routes = [{"name": "MAINMENU_X", "path": "x"}]
    dep_index: dict[tuple[str, str], list[str]] = {}
    assert _route_visibility_deps_for_symbol(routes, dep_index, payload=None, flat_values={}) == []
    assert (
        _route_visibility_deps_for_symbol(
            routes,
            dep_index,
            payload={"mapping": "bad"},
            flat_values={},
        )
        == []
    )
    assert (
        _route_visibility_deps_for_symbol(
            routes,
            dep_index,
            payload={"mapping": {"paths": {"status": [{"group": "P6", "use": "s", "number": "x"}]}}},
            flat_values={},
        )
        == []
    )


def test_primary_route_identity_skips_blank_entries() -> None:
    """Blank route entries are skipped until a usable name/path appears."""
    assert _primary_route_identity([{"name": "", "path": ""}, {"name": "MAINMENU_X", "path": ""}]) == (
        "MAINMENU_X",
        "",
    )


def test_shell_diagnostics_skips_non_shell_and_rejected_rows() -> None:
    """Shell enrichment ignores non-shell and rejected diagnostics rows."""
    diagnostics = [
        {"title": "Regular", "accepted": True, "panel_shell": False},
        {"title": "Hidden", "accepted": False, "panel_shell": True, "panel_title": "Hidden"},
    ]
    symbol_routes: dict[str, list[dict[str, Any]]] = {}
    _enrich_symbol_routes_from_shell_diagnostics({"PARAM_1": "Hidden"}, symbol_routes, diagnostics)
    assert symbol_routes == {}


def test_shell_diagnostics_skips_blank_panel_path() -> None:
    """Blank panel paths do not receive shell route meta."""
    diagnostics = [
        {
            "title": "Strefy czasowe",
            "panel_title": "Strefy czasowe",
            "name": "MAINMENU_STREFY_CZASOWE",
            "path": "timezones",
            "accepted": True,
            "panel_shell": True,
        }
    ]
    symbol_routes: dict[str, list[dict[str, Any]]] = {}
    _enrich_symbol_routes_from_shell_diagnostics({"PARAM_177": "   "}, symbol_routes, diagnostics)
    assert symbol_routes == {}


def test_shell_diagnostics_enrich_symbol_routes() -> None:
    """Panel-shell diagnostics attach route meta for static-route symbols."""
    diagnostics = [
        {
            "title": "Strefy czasowe",
            "panel_title": "Strefy czasowe",
            "name": "MAINMENU_STREFY_CZASOWE",
            "path": "timezones",
            "accepted": True,
            "panel_shell": True,
        }
    ]
    panel_paths = {"PARAM_177": "Strefy czasowe", "PARAM_219": "Strefy czasowe"}
    symbol_routes: dict[str, list[dict[str, Any]]] = {}
    _enrich_symbol_routes_from_shell_diagnostics(panel_paths, symbol_routes, diagnostics)
    assert symbol_routes["PARAM_177"][0]["name"] == "MAINMENU_STREFY_CZASOWE"
    assert symbol_routes["PARAM_219"][0]["path"] == "timezones"
    assert _stable_menu_key_from_route_meta(symbol_routes["PARAM_177"]) == "MAINMENU_STREFY_CZASOWE"
    assert (
        _resolve_menu_key_for_symbol(
            symbol="PARAM_219",
            panel_path="Strefy czasowe",
            symbol_routes=symbol_routes,
            panel_menu_keys={},
        )
        == "MAINMENU_STREFY_CZASOWE"
    )


def test_shell_diagnostics_enrich_requires_localized_panel_title() -> None:
    """Unresolved MAINMENU_* titles must not silently match localized panel paths.

    Live bootstrap used bare ``routes`` i18n for diagnostics while panel groups used
    ``_panel_title_i18n`` — enrichment then left PARAM_219 without ``menu_key`` and
    group-by-menu hid the Strefy czasowe child device. Bootstrap must localize both.
    """
    diagnostics = [
        {
            "title": "MAINMENU_STREFY_CZASOWE",
            "panel_title": "MAINMENU_STREFY_CZASOWE",
            "name": "MAINMENU_STREFY_CZASOWE",
            "path": "timezones",
            "accepted": True,
            "panel_shell": True,
        }
    ]
    symbol_routes: dict[str, list[dict[str, Any]]] = {}
    _enrich_symbol_routes_from_shell_diagnostics(
        {"PARAM_219": "Strefy czasowe"},
        symbol_routes,
        diagnostics,
    )
    assert symbol_routes == {}


def test_shell_diagnostics_skip_existing_route_meta() -> None:
    """Symbols that already have route meta are not overwritten by shell enrichment."""
    diagnostics = [
        {
            "title": "Strefy czasowe",
            "panel_title": "Strefy czasowe",
            "name": "MAINMENU_STREFY_CZASOWE",
            "path": "timezones",
            "accepted": True,
            "panel_shell": True,
        }
    ]
    symbol_routes: dict[str, list[dict[str, Any]]] = {
        "PARAM_177": [{"name": "existing.route", "path": "keep", "ancestors": []}],
    }
    _enrich_symbol_routes_from_shell_diagnostics({"PARAM_177": "Strefy czasowe"}, symbol_routes, diagnostics)
    assert symbol_routes["PARAM_177"][0]["name"] == "existing.route"


def test_menu_key_resolves_for_shell_route_meta() -> None:
    """Group-by-menu child device key resolves from enriched shell route meta."""
    routes = [
        {
            "name": "MAINMENU_STREFY_CZASOWE",
            "path": "timezones",
            "ancestors": [],
        }
    ]
    key = _resolve_menu_key_for_symbol(
        symbol="PARAM_177",
        panel_path="Strefy czasowe",
        symbol_routes={"PARAM_177": routes},
        panel_menu_keys={},
    )
    assert key == "MAINMENU_STREFY_CZASOWE"


def test_primary_route_identity_returns_first_name_or_path() -> None:
    """Primary route identity prefers the first non-empty route tuple."""
    assert _primary_route_identity([{"name": "MAINMENU_X", "path": "timezones"}]) == ("MAINMENU_X", "timezones")
    assert _primary_route_identity([{"name": "", "path": "circulation"}]) == ("", "circulation")
    assert _primary_route_identity([]) == ("", "")


def test_route_dep_index_from_menu_collects_dependency_keys() -> None:
    """Bootstrap builds a route dep index from menu status parameters."""
    menu = SimpleNamespace(
        routes=[
            SimpleNamespace(
                name="MAINMENU_STREFY_CZASOWE",
                path="timezones",
                meta=SimpleNamespace(
                    parameters=SimpleNamespace(
                        status=[SimpleNamespace(group="P6", number=219, use="s")],
                    )
                ),
                children=[],
                component=None,
            )
        ]
    )
    index = _route_dep_index_from_menu(menu)
    assert index[("MAINMENU_STREFY_CZASOWE", "timezones")] == ["P6.s219"]


def test_route_visibility_deps_for_symbol_merges_route_and_payload() -> None:
    """Descriptor route deps merge route index keys and mapping status paths."""
    routes = [{"name": "MAINMENU_STREFY_CZASOWE", "path": "timezones"}]
    dep_index = {("MAINMENU_STREFY_CZASOWE", "timezones"): ["P6.s219"]}
    payload = {
        "mapping": {
            "paths": {
                "status": [{"group": "P6", "number": 219, "use": "s", "bit": 0, "condition": "INVISIBLE"}],
            }
        }
    }
    deps = _route_visibility_deps_for_symbol(
        routes,
        dep_index,
        payload=payload,
        flat_values={"P6.s219": 0},
    )
    assert deps == ["P6.s219"]


@pytest.mark.skipif(not _FIXTURE.is_file(), reason="shared py-bragerone fixture missing")
def test_shared_fixture_describes_strefy_panel() -> None:
    """Shared fixture keeps the Strefy czasowe panel title stable."""
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert payload["routes"][0]["name"] == "MAINMENU_STREFY_CZASOWE"


def test_async_build_bootstrap_payload_enriches_shell_routes_and_route_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap enriches shell routes and persists route visibility paths (#192)."""
    import asyncio
    import sys
    from typing import Any, cast

    from custom_components.habragerone.bootstrap import async_build_bootstrap_payload
    from custom_components.habragerone.const import CONF_ROUTE_VISIBILITY_PATH, CONF_UI_ROUTE_SYMBOL

    class _FakeParamStore:
        def ingest_prime_payload(self, _payload: dict[str, object]) -> None:
            return None

        def flatten(self) -> dict[str, object]:
            return {"P6.v219": 1}

    shell_menu = SimpleNamespace(
        routes=[
            SimpleNamespace(
                name="MAINMENU_STREFY_CZASOWE",
                path="timezones",
                meta=SimpleNamespace(display_dropdown="!![]"),
                children=[],
                component=None,
            )
        ]
    )

    class _FakeAssets:
        def __init__(self) -> None:
            self.calls = 0

        async def get_module_menu(self, device_menu: object, permissions: object) -> SimpleNamespace:
            _ = device_menu, permissions
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(routes=[])
            return shell_menu

    class _FakeResolver:
        def __init__(self) -> None:
            self._assets = _FakeAssets()
            self._current_devid = "M1"

        @staticmethod
        def _iter_routes_with_ancestors(routes: object) -> list[tuple[object, tuple[object, ...]]]:
            if not isinstance(routes, list):
                return []
            return [(route, ()) for route in routes]

        @staticmethod
        def route_visibility_dependency_keys(route: object, ancestors: object = ()) -> list[str]:
            _ = route, ancestors
            return []

        @staticmethod
        def _status_paths_for_visibility(mapping: object, flat_values: object) -> list[dict[str, object]]:
            _ = mapping, flat_values
            return []

        @classmethod
        def from_api(cls, api: object, store: object, lang: object) -> _FakeResolver:
            _ = api, store, lang
            return cls()

        async def build_panel_groups(
            self,
            *,
            device_menu: object,
            permissions: object,
            all_panels: bool,
            web_ui_only: bool = False,
            flat_values: object | None = None,
        ) -> dict[str, list[str]]:
            _ = device_menu, permissions, all_panels, flat_values
            if web_ui_only:
                return {"Strefy czasowe": ["PARAM_177"]}
            return {"Strefy czasowe": ["PARAM_177"]}

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

        async def _panel_title_i18n(self, menu: object) -> dict[str, str]:
            _ = menu
            return {"MAINMENU_STREFY_CZASOWE": "Strefy czasowe"}

        def panel_route_diagnostics_from_menu(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
            _ = args, kwargs
            return [
                {
                    "title": "Strefy czasowe",
                    "panel_title": "Strefy czasowe",
                    "name": "MAINMENU_STREFY_CZASOWE",
                    "path": "timezones",
                    "accepted": True,
                    "panel_shell": True,
                }
            ]

        def set_runtime_context(self, context: dict[str, object] | None) -> None:
            if isinstance(context, dict):
                self._current_devid = str(context.get("devid", ""))

        def parameter_visibility_diagnostics(
            self,
            *,
            desc: dict[str, object],
            resolved: object,
            flat_values: dict[str, object],
        ) -> tuple[bool, dict[str, object]]:
            _ = desc, resolved, flat_values
            return True, {}

        async def resolve_value(self, symbol: str) -> SimpleNamespace:
            _ = symbol
            return SimpleNamespace(value=1, value_label="1")

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
            self,
            module_ids: list[str],
            return_data: bool = False,
        ) -> tuple[int, dict[str, object]]:
            _ = module_ids, return_data
            return 200, {}

    monkeypatch.setattr(sys.modules["pybragerone.models.param"], "ParamStore", _FakeParamStore)
    monkeypatch.setattr(sys.modules["pybragerone.models.param_resolver"], "ParamResolver", _FakeResolver)

    payload = asyncio.run(
        async_build_bootstrap_payload(
            api=cast(Any, _FakeApi()),
            object_id=1,
            modules=["M1"],
            language="pl",
        )
    )
    descriptor = payload["entity_descriptors"][0]
    assert descriptor["symbol"] == "PARAM_177"
    assert descriptor[CONF_UI_ROUTE_SYMBOL] is True
    assert descriptor[CONF_ROUTE_VISIBILITY_PATH] == "timezones"
