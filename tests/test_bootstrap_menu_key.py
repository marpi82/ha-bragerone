"""Unit tests for stable menu_key selection used by device grouping (#165/#176)."""

from __future__ import annotations

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.bootstrap import (  # noqa: E402
    _menu_group_title_from_panel_path,
    _menu_title_from_panel_path,
    _stable_menu_key_from_route_meta,
)


def test_stable_menu_key_prefers_modules_menu_name() -> None:
    routes = [
        {"name": "modules.menu.boiler", "path": "boiler", "display_name": "Kocioł"},
        {"name": "modules.menu.dhw", "path": "dhw", "display_name": "CWU"},
    ]
    assert _stable_menu_key_from_route_meta(routes) == "modules.menu.boiler"


def test_stable_menu_key_prefers_parent_ancestor_over_leaf() -> None:
    routes = [
        {
            "name": "modules.menu.valve1",
            "path": "valve1",
            "ancestors": [{"name": "modules.menu.thermostats", "path": "thermostats"}],
        },
    ]
    assert _stable_menu_key_from_route_meta(routes) == "modules.menu.thermostats"


def test_stable_menu_key_uses_ancestor_path_when_name_unstable() -> None:
    routes = [
        {
            "name": "localized valve",
            "path": "valve1",
            "ancestors": [{"name": "Menu termostatów", "path": "thermostats"}],
        },
    ]
    assert _stable_menu_key_from_route_meta(routes) == "thermostats"


def test_stable_menu_key_falls_back_to_path() -> None:
    routes = [
        {"name": "localized title", "path": "valve1"},
    ]
    assert _stable_menu_key_from_route_meta(routes) == "valve1"


def test_stable_menu_key_accepts_mainmenu_tokens() -> None:
    routes = [{"name": "MAINMENU_BOILER", "path": ""}]
    assert _stable_menu_key_from_route_meta(routes) == "MAINMENU_BOILER"


def test_stable_menu_key_accepts_companies_prefix_and_menu_token() -> None:
    assert (
        _stable_menu_key_from_route_meta([{"name": "companies.modules.menu.dhw", "path": "dhw"}]) == "companies.modules.menu.dhw"
    )
    assert _stable_menu_key_from_route_meta([{"name": "MENU_BOILER", "path": ""}]) == "MENU_BOILER"


def test_stable_menu_key_falls_back_to_any_nonempty_name() -> None:
    assert _stable_menu_key_from_route_meta([{"name": "custom.route", "path": ""}]) == "custom.route"


def test_stable_menu_key_returns_none_when_empty() -> None:
    assert _stable_menu_key_from_route_meta([]) is None
    assert _stable_menu_key_from_route_meta([{"name": "", "path": ""}]) is None


def test_menu_title_from_panel_path_uses_leaf() -> None:
    assert _menu_title_from_panel_path("Termostaty/Zawór 1") == "Zawór 1"
    assert _menu_title_from_panel_path("Kocioł") == "Kocioł"
    assert _menu_title_from_panel_path("  ") == ""


def test_menu_group_title_from_panel_path_uses_root() -> None:
    assert _menu_group_title_from_panel_path("Menu termostatów/Zawór 1") == "Menu termostatów"
    assert _menu_group_title_from_panel_path("Kocioł") == "Kocioł"
    assert _menu_group_title_from_panel_path("  ") == ""
