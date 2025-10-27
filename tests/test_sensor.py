import pytest
from homeassistant.setup import async_setup_component

@pytest.mark.asyncio
async def test_sensor_loads(hass):
    assert await async_setup_component(hass, "sensor", {})
