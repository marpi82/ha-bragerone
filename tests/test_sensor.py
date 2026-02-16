import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


@pytest.mark.asyncio
async def test_sensor_loads(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "sensor", {})
