"""Unit tests for stable menu_key selection used by device grouping (#165/#176)."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.bootstrap import (  # noqa: E402
    _collect_symbol_route_meta_from_menu,
    _menu_group_title_from_panel_path,
    _menu_keys_by_panel_path,
    _menu_title_from_panel_path,
    _path_menu_token,
    _resolve_menu_key_for_symbol,
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


def test_resolve_menu_key_inherits_from_panel_sibling() -> None:
    """Panel-only PARAM16_* can inherit Podajnik menu_key from a routed sibling."""
    panel_paths = {
        "STATUS_FEEDER": "Podajnik",
        "PARAM16_2": "Podajnik",
    }
    symbol_routes = {
        "STATUS_FEEDER": [{"name": "modules.menu.feeder", "path": "feeder", "ancestors": []}],
        # PARAM16_2 intentionally missing from routes (panel-only / empty kinds)
    }
    panel_menu_keys = _menu_keys_by_panel_path(panel_paths, symbol_routes)
    assert panel_menu_keys["Podajnik"] == "modules.menu.feeder"
    assert (
        _resolve_menu_key_for_symbol(
            symbol="PARAM16_2",
            panel_path="Podajnik",
            symbol_routes=symbol_routes,
            panel_menu_keys=panel_menu_keys,
        )
        == "modules.menu.feeder"
    )


def test_resolve_menu_key_inherits_via_group_title() -> None:
    panel_paths = {
        "STATUS_VALVE": "Menu termostatów/Zawór 1",
        "PARAM_ORPHAN": "Menu termostatów/Zawór 2",
    }
    symbol_routes = {
        "STATUS_VALVE": [
            {
                "name": "modules.menu.valve1",
                "path": "valve1",
                "ancestors": [{"name": "modules.menu.thermostats", "path": "thermostats"}],
            }
        ],
    }
    panel_menu_keys = _menu_keys_by_panel_path(panel_paths, symbol_routes)
    assert (
        _resolve_menu_key_for_symbol(
            symbol="PARAM_ORPHAN",
            panel_path="Menu termostatów/Zawór 2",
            symbol_routes=symbol_routes,
            panel_menu_keys=panel_menu_keys,
        )
        == "modules.menu.thermostats"
    )


def test_resolve_menu_key_prefers_own_route_meta() -> None:
    panel_paths = {"PARAM_A": "Podajnik", "PARAM_B": "Podajnik"}
    symbol_routes = {
        "PARAM_A": [{"name": "modules.menu.feeder", "path": "feeder"}],
        "PARAM_B": [{"name": "modules.menu.other", "path": "other"}],
    }
    panel_menu_keys = _menu_keys_by_panel_path(panel_paths, symbol_routes)
    assert (
        _resolve_menu_key_for_symbol(
            symbol="PARAM_B",
            panel_path="Podajnik",
            symbol_routes=symbol_routes,
            panel_menu_keys=panel_menu_keys,
        )
        == "modules.menu.other"
    )


def test_menu_keys_by_panel_path_skips_blank_and_non_string_paths() -> None:
    panel_paths = {
        "STATUS_OK": "Podajnik",
        "BAD_BLANK": "   ",
        "BAD_TYPE": 12,  # type: ignore[dict-item]
    }
    symbol_routes = {
        "STATUS_OK": [{"name": "modules.menu.feeder", "path": "feeder"}],
        "BAD_BLANK": [{"name": "modules.menu.feeder", "path": "feeder"}],
        "BAD_TYPE": [{"name": "modules.menu.feeder", "path": "feeder"}],
    }
    panel_menu_keys = _menu_keys_by_panel_path(panel_paths, symbol_routes)  # type: ignore[arg-type]
    assert panel_menu_keys == {"Podajnik": "modules.menu.feeder"}


def test_resolve_menu_key_returns_none_without_path_or_sibling() -> None:
    assert (
        _resolve_menu_key_for_symbol(
            symbol="PARAM_ORPHAN",
            panel_path="   ",
            symbol_routes={},
            panel_menu_keys={"Podajnik": "modules.menu.feeder"},
        )
        is None
    )
    assert (
        _resolve_menu_key_for_symbol(
            symbol="PARAM_ORPHAN",
            panel_path="Inny panel",
            symbol_routes={},
            panel_menu_keys={"Podajnik": "modules.menu.feeder"},
        )
        is None
    )
