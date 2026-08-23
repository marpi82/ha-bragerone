"""Runtime route visibility tests (#192)."""

from __future__ import annotations

from unittest.mock import MagicMock

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
        store=MagicMock(flatten=MagicMock(return_value={})),
        modules_meta={"dev1": {"device_menu": 0, "name": "mod"}},
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
            }
        ]
    )
    runtime._symbol_route_visible["dev1:PARAM_177"] = route_visible
    runtime._module_online["dev1"] = True
    return runtime


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


def test_route_visibility_listener_receives_callbacks() -> None:
    """Registered route-visibility listeners receive fan-out events."""
    runtime = _runtime_stub(route_visible=True)
    seen: list[tuple[str, str, bool]] = []
    runtime.add_route_visibility_listener(lambda devid, symbol, visible: seen.append((devid, symbol, visible)))
    for callback in tuple(runtime._route_visibility_listeners):
        callback("dev1", "PARAM_177", False)
    assert seen == [("dev1", "PARAM_177", False)]
