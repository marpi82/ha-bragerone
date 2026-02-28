from types import SimpleNamespace

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.bootstrap import (  # noqa: E402
    _collect_symbols_from_menu,
    _normalize_filter_mode,
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
