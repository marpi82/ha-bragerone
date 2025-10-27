from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

SCAN_INTERVAL = timedelta(seconds=30)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([ExampleTemperatureSensor(entry)])


class ExampleTemperatureSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Temperatura (przykład)"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_temp"

    async def async_update(self) -> None:
        # Tu podłącz realne źródło danych (np. z hass.data[DOMAIN][entry_id]["client"])
        # Na start – generujemy stałą wartość lub prostą symulację.
        self._attr_native_value = 21.5
