from __future__ import annotations
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, CONF_API_KEY

TO_REDACT = {CONF_API_KEY}

async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry):
    data = {**entry.data}
    return async_redact_data({"entry_data": data, "runtime": hass.data.get(DOMAIN, {}).get(entry.entry_id)}, TO_REDACT)
