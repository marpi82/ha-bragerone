"""Unit tests for stable menu_key selection used by device grouping (#165/#176)."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.bootstrap import (  # noqa: E402
    _collect_symbol_route_meta_from_menu,
    _menu_group_title_from_panel_path,
    _menu_title_from_panel_path,
    _path_menu_token,
    _stable_menu_key_from_route_meta,
)


def _param(token: str) -> SimpleNamespace:
    return SimpleNamespace(token=token)


def test_collect_symbol_route_meta_includes_ancestors() -> None:
    child = SimpleNamespace(
        name="modules.menu.valve1",
        path="valve1",
        component="ValveView",
        meta=SimpleNamespace(
            displayName="Zawór 1",
            isVisibleOnSideMenu=True,
            displayDropdown=False,
            parameters=SimpleNamespace(read=[_param("PARAM_VALVE_1")], write=[], status=[], special=[]),
        ),
        parameters=None,
        children=None,  # non-list children must be ignored (no crash)
    )
    parent = SimpleNamespace(
        name="modules.menu.thermostats",
        path="thermostats",
        component="ThermostatsView",
        meta=SimpleNamespace(
            displayName="Menu termostatów",
            isVisibleOnSideMenu=True,
            displayDropdown=True,
            parameters=SimpleNamespace(read=[], write=[], status=[], special=[]),
        ),
        parameters=None,
        children=[child],
    )
    menu = SimpleNamespace(routes=[parent])

    routes = _collect_symbol_route_meta_from_menu(menu)
    assert "PARAM_VALVE_1" in routes
    payload = routes["PARAM_VALVE_1"][0]
    assert payload["name"] == "modules.menu.valve1"
    assert payload["ancestors"] == [{"name": "modules.menu.thermostats", "path": "thermostats"}]
    assert _stable_menu_key_from_route_meta(routes["PARAM_VALVE_1"]) == "modules.menu.thermostats"


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


def test_stable_menu_key_skips_invalid_ancestor_entries() -> None:
    routes = [
        {
            "name": "modules.menu.valve1",
            "path": "valve1",
            "ancestors": ["bad", {"name": 123, "path": None}, {"name": "modules.menu.thermostats", "path": "t"}],
        },
    ]
    assert _stable_menu_key_from_route_meta(routes) == "modules.menu.thermostats"


def test_stable_menu_key_skips_invalid_entries_when_falling_back_to_path() -> None:
    routes = [
        {
            "name": "localized valve",
            "path": "valve1",
            "ancestors": [
                "bad",
                {"name": "Menu i18n", "path": "/"},
                {"name": "Menu i18n", "path": "."},
                {"name": "Menu i18n", "path": "thermostats"},
            ],
        },
    ]
    assert _stable_menu_key_from_route_meta(routes) == "thermostats"


def test_stable_menu_key_falls_through_unusable_ancestors_to_leaf() -> None:
    routes = [
        {
            "name": "modules.menu.valve1",
            "path": "valve1",
            "ancestors": ["bad", {"name": "Menu i18n", "path": "/"}, {"name": "Menu i18n", "path": None}],
        },
    ]
    assert _stable_menu_key_from_route_meta(routes) == "modules.menu.valve1"


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


def test_path_menu_token_rejects_non_strings() -> None:
    assert _path_menu_token(None) is None
    assert _path_menu_token(12) is None
    assert _path_menu_token("/") is None
    assert _path_menu_token(".") is None
    assert _path_menu_token("..") is None
    assert _path_menu_token("valve/1") == "valve/1"


def test_menu_title_from_panel_path_uses_leaf() -> None:
    assert _menu_title_from_panel_path("Termostaty/Zawór 1") == "Zawór 1"
    assert _menu_title_from_panel_path("Kocioł") == "Kocioł"
    assert _menu_title_from_panel_path("  ") == ""


def test_menu_group_title_from_panel_path_uses_root() -> None:
    assert _menu_group_title_from_panel_path("Menu termostatów/Zawór 1") == "Menu termostatów"
    assert _menu_group_title_from_panel_path("Kocioł") == "Kocioł"
    assert _menu_group_title_from_panel_path("  ") == ""
