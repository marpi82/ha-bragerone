"""Bootstrap regression for static menu route shells (#192)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.habragerone.bootstrap import (
    _enrich_symbol_routes_from_shell_diagnostics,
    _resolve_menu_key_for_symbol,
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


@pytest.mark.skipif(not _FIXTURE.is_file(), reason="shared py-bragerone fixture missing")
def test_shared_fixture_describes_strefy_panel() -> None:
    """Shared fixture keeps the Strefy czasowe panel title stable."""
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert payload["routes"][0]["name"] == "MAINMENU_STREFY_CZASOWE"
