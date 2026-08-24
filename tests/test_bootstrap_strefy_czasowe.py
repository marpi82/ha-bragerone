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
    panel_paths = {"PARAM_177": "Strefy czasowe"}
    symbol_routes: dict[str, list[dict[str, Any]]] = {}
    _enrich_symbol_routes_from_shell_diagnostics(panel_paths, symbol_routes, diagnostics)
    assert symbol_routes["PARAM_177"][0]["name"] == "MAINMENU_STREFY_CZASOWE"
    assert _stable_menu_key_from_route_meta(symbol_routes["PARAM_177"]) == "MAINMENU_STREFY_CZASOWE"


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
