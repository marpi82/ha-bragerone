"""Platform entities detach route-visibility listeners on removal (#192)."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.binary_sensor import BragerStatusBinarySensor  # noqa: E402
from custom_components.habragerone.const import (  # noqa: E402
    CONF_ROUTE_VISIBILITY_NAME,
    CONF_ROUTE_VISIBILITY_PATH,
    CONF_UI_ROUTE_SYMBOL,
)
from custom_components.habragerone.number import BragerSymbolNumber  # noqa: E402
from custom_components.habragerone.select import BragerSymbolSelect  # noqa: E402
from custom_components.habragerone.sensor import BragerSymbolSensor  # noqa: E402
from custom_components.habragerone.switch import BragerSymbolSwitch  # noqa: E402
from tests.helpers.descriptors import (  # noqa: E402
    binary_sensor_descriptor,
    select_descriptor,
    sensor_descriptor,
    switch_descriptor,
    writable_parameter_descriptor,
)
from tests.helpers.fakes import make_runtime  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


def _ui_route_descriptor(descriptor_factory: Any) -> dict[str, Any]:
    descriptor = descriptor_factory()
    descriptor.update(
        {
            CONF_UI_ROUTE_SYMBOL: True,
            CONF_ROUTE_VISIBILITY_NAME: "MAINMENU_X",
            CONF_ROUTE_VISIBILITY_PATH: "timezones",
        }
    )
    return descriptor


@pytest.mark.parametrize(
    ("entity_cls", "descriptor_factory", "entity_id"),
    [
        (BragerStatusBinarySensor, binary_sensor_descriptor, "binary_sensor.test"),
        (BragerSymbolNumber, writable_parameter_descriptor, "number.test"),
        (BragerSymbolSelect, select_descriptor, "select.test"),
        (BragerSymbolSensor, sensor_descriptor, "sensor.test"),
        (BragerSymbolSwitch, switch_descriptor, "switch.test"),
    ],
)
@pytest.mark.asyncio
async def test_platform_entity_unsubscribes_route_visibility(
    hass: HomeAssistant,
    entity_cls: type[Any],
    descriptor_factory: Any,
    entity_id: str,
) -> None:
    """UI-route entities detach route visibility listeners on removal."""
    runtime, *_rest = make_runtime(flat_values={"P5.s0": 1, "P6.v0": 1, "P4.v1": 1})
    descriptor = _ui_route_descriptor(descriptor_factory)
    entry = register_config_entry(hass, runtime=runtime, descriptors=[descriptor])
    entity = entity_cls(entry=entry, runtime=runtime, descriptor=descriptor)
    entity.hass = hass
    entity.entity_id = entity_id

    await entity.async_added_to_hass()
    assert callable(entity._unsubscribe_route_visibility)

    await entity.async_will_remove_from_hass()
    assert entity._unsubscribe_route_visibility is None
    assert entity._unsubscribe_listener is None
