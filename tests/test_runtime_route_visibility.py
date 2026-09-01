"""Runtime route visibility tests (#192)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.habragerone.const import (
    CONF_ROUTE_VISIBILITY_DEPS,
    CONF_ROUTE_VISIBILITY_NAME,
    CONF_ROUTE_VISIBILITY_PATH,
    CONF_UI_ROUTE_SYMBOL,
)
from custom_components.habragerone.entity_common import entity_is_available
from custom_components.habragerone.runtime import BragerRuntime


def _runtime_stub(*, route_visible: bool = True) -> BragerRuntime:
    runtime = BragerRuntime(
        api=MagicMock(),
        gateway=MagicMock(modules=[]),
        store=MagicMock(flatten=MagicMock(return_value={}), flatten_for_devid=MagicMock(return_value={})),
        modules_meta={"dev1": {"device_menu": 0, "name": "mod", "permissions": []}},
        language="pl",
    )
    runtime.register_route_visibility(
        [
            {
                "devid": "dev1",
                "symbol": "PARAM_177",
                CONF_UI_ROUTE_SYMBOL: True,
                CONF_ROUTE_VISIBILITY_NAME: "MAINMENU_STREFY_CZASOWE",
                CONF_ROUTE_VISIBILITY_PATH: "timezones",
                CONF_ROUTE_VISIBILITY_DEPS: ["P1.s0"],
            },
            {
                "devid": "dev1",
                "symbol": "PARAM_219",
                CONF_UI_ROUTE_SYMBOL: True,
                CONF_ROUTE_VISIBILITY_NAME: "modules.menu.circulation",
                CONF_ROUTE_VISIBILITY_PATH: "circulation",
                CONF_ROUTE_VISIBILITY_DEPS: ["P6.v219"],
            },
        ]
    )
    runtime._symbol_route_visible["dev1:PARAM_177"] = route_visible
    runtime._symbol_route_visible["dev1:PARAM_219"] = route_visible
    runtime._module_online["dev1"] = True
    return runtime


def _attach_menu_resolver(runtime: BragerRuntime, *, routes: list[SimpleNamespace]) -> AsyncMock:
    menu = SimpleNamespace(routes=routes)
    resolver = AsyncMock()
    resolver.get_module_menu = AsyncMock(return_value=menu)
    runtime._status_resolver = resolver
    return resolver


def test_entity_is_available_hides_ui_route_when_route_not_visible() -> None:
    """UI-route entities become unavailable when route visibility is false."""
    runtime = _runtime_stub(route_visible=False)
    descriptor = {
        "symbol": "PARAM_177",
        CONF_UI_ROUTE_SYMBOL: True,
    }
    assert entity_is_available(runtime, devid="dev1", has_value=True, descriptor=descriptor) is False


def test_entity_is_available_keeps_non_ui_route_when_route_hidden() -> None:
    """Non UI-route entities ignore route visibility gating."""
    runtime = _runtime_stub(route_visible=False)
    descriptor = {
        "symbol": "PARAM_9",
        CONF_UI_ROUTE_SYMBOL: False,
    }
    assert entity_is_available(runtime, devid="dev1", has_value=True, descriptor=descriptor) is True


def test_entity_is_available_uses_symbol_argument_without_descriptor() -> None:
    """Symbol-only availability checks still honor route visibility."""
    runtime = _runtime_stub(route_visible=False)
    assert entity_is_available(runtime, devid="dev1", has_value=True, symbol="PARAM_177") is False


def test_route_visible_for_symbol_defaults_true_for_unknown_symbols() -> None:
    """Symbols outside the route visibility index stay visible."""
    runtime = _runtime_stub(route_visible=False)
    assert runtime.route_visible_for_symbol("dev1", "UNKNOWN") is True


def test_register_route_visibility_skips_non_ui_descriptors() -> None:
    """Only UI-route descriptors populate the visibility index."""
    runtime = BragerRuntime(
        api=MagicMock(),
        gateway=MagicMock(modules=[]),
        store=MagicMock(flatten=MagicMock(return_value={}), flatten_for_devid=MagicMock(return_value={})),
        modules_meta={},
        language="pl",
    )
    runtime.register_route_visibility([{"devid": "dev1", "symbol": "PARAM_9", CONF_UI_ROUTE_SYMBOL: False}])
    assert runtime._symbol_route_lookup == {}


def test_route_visibility_listener_receives_callbacks() -> None:
    """Registered route-visibility listeners receive fan-out events."""
    runtime = _runtime_stub(route_visible=True)
    seen: list[tuple[str, str, bool]] = []
    runtime.add_route_visibility_listener(lambda devid, symbol, visible: seen.append((devid, symbol, visible)))
    for callback in tuple(runtime._route_visibility_listeners):
        callback("dev1", "PARAM_177", False)
    assert seen == [("dev1", "PARAM_177", False)]


@pytest.mark.asyncio
async def test_refresh_route_visibility_updates_symbol_state() -> None:
    """Route visibility refresh re-evaluates indexed symbols from prime values."""
    runtime = _runtime_stub(route_visible=True)
    circulation_route = SimpleNamespace(
        name="modules.menu.circulation",
        path="circulation",
        meta=SimpleNamespace(display_dropdown="P6.v219"),
        children=[],
    )
    _attach_menu_resolver(runtime, routes=[circulation_route])
    runtime.store.flatten_for_devid.return_value = {"P6.v219": 0}

    await runtime.refresh_route_visibility({"PARAM_219"})

    assert runtime.route_visible_for_symbol("dev1", "PARAM_219") is False
    runtime.store.flatten_for_devid.assert_called_once_with("dev1")


@pytest.mark.asyncio
async def test_refresh_route_visibility_caches_flat_values_per_devid() -> None:
    """Per-module flatten snapshots are computed once per refresh pass."""
    runtime = _runtime_stub(route_visible=True)
    route_a = SimpleNamespace(
        name="modules.menu.circulation",
        path="circulation",
        meta=SimpleNamespace(display_dropdown="P6.v219"),
        children=[],
    )
    route_b = SimpleNamespace(
        name="MAINMENU_STREFY_CZASOWE",
        path="timezones",
        meta=SimpleNamespace(display_dropdown="![]"),
        children=[],
    )
    _attach_menu_resolver(runtime, routes=[route_a, route_b])

    await runtime.refresh_route_visibility(None)

    assert runtime.store.flatten_for_devid.call_count == 1
    runtime.store.flatten_for_devid.assert_called_with("dev1")


@pytest.mark.asyncio
async def test_refresh_route_visibility_notifies_listeners_on_change() -> None:
    """Visibility flips notify registered listeners."""
    runtime = _runtime_stub(route_visible=True)
    timezone_route = SimpleNamespace(
        name="MAINMENU_STREFY_CZASOWE",
        path="timezones",
        meta=SimpleNamespace(display_dropdown="![]"),
        children=[],
    )
    _attach_menu_resolver(runtime, routes=[timezone_route])

    seen: list[tuple[str, str, bool]] = []
    runtime.add_route_visibility_listener(lambda devid, symbol, visible: seen.append((devid, symbol, visible)))
    await runtime.refresh_route_visibility({"PARAM_177"})
    assert seen == [("dev1", "PARAM_177", False)]


@pytest.mark.asyncio
async def test_menu_for_devid_uses_cached_permissions() -> None:
    """Route visibility menu fetch passes bootstrap permissions to the resolver."""
    runtime = _runtime_stub()
    route = SimpleNamespace(name="MAINMENU_STREFY_CZASOWE", path="timezones", meta=None, children=[])
    resolver = _attach_menu_resolver(runtime, routes=[route])
    runtime.modules_meta["dev1"]["permissions"] = ["DISPLAY_PARAMETER_LEVEL_1"]

    menu_first = await runtime._menu_for_devid("dev1", resolver)
    menu_second = await runtime._menu_for_devid("dev1", resolver)

    assert menu_first is menu_second
    resolver.get_module_menu.assert_awaited_once_with(device_menu=0, permissions=["DISPLAY_PARAMETER_LEVEL_1"])


@pytest.mark.asyncio
async def test_menu_for_devid_coerces_digit_string_device_menu() -> None:
    """Digit-string device_menu values from stored modules_meta still fetch a menu."""
    runtime = _runtime_stub()
    runtime.modules_meta["dev1"] = {"device_menu": "101", "name": "mod", "permissions": ["DISPLAY_PARAMETER_LEVEL_1"]}
    route = SimpleNamespace(name="MAINMENU_STREFY_CZASOWE", path="timezones", meta=None, children=[])
    resolver = _attach_menu_resolver(runtime, routes=[route])

    menu = await runtime._menu_for_devid("dev1", resolver)

    assert menu is not None
    resolver.get_module_menu.assert_awaited_once_with(device_menu=101, permissions=["DISPLAY_PARAMETER_LEVEL_1"])


@pytest.mark.asyncio
async def test_menu_for_devid_coerces_padded_digit_string_device_menu() -> None:
    """Whitespace-padded digit strings coerce to int for menu lookup."""
    runtime = _runtime_stub()
    runtime.modules_meta["dev1"] = {"device_menu": " 0 ", "permissions": []}
    route = SimpleNamespace(name="MAINMENU_STREFY_CZASOWE", path="timezones", meta=None, children=[])
    resolver = _attach_menu_resolver(runtime, routes=[route])

    menu = await runtime._menu_for_devid("dev1", resolver)

    assert menu is not None
    resolver.get_module_menu.assert_awaited_once_with(device_menu=0, permissions=[])


def test_parse_device_menu_id_rejects_non_digit_values() -> None:
    """Non-int, non-digit-string device_menu values are rejected."""
    assert BragerRuntime._parse_device_menu_id("bad") is None
    assert BragerRuntime._parse_device_menu_id("M1") is None
    assert BragerRuntime._parse_device_menu_id(None) is None
    assert BragerRuntime._parse_device_menu_id(True) is None
    assert BragerRuntime._parse_device_menu_id(0) == 0
    assert BragerRuntime._parse_device_menu_id("42") == 42
