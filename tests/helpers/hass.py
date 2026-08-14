"""Home Assistant test harness helpers."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.habragerone.const import (
    CONF_ENTITY_DESCRIPTORS,
    CONF_OBJECT_ID,
    DATA_ENTITY_STATS,
    DATA_RUNTIME,
    DOMAIN,
)


def register_config_entry(
    hass: HomeAssistant,
    *,
    entry_id: str = "test-entry-id",
    runtime: Any,
    descriptors: list[dict[str, Any]],
    entity_stats: dict[str, Any] | None = None,
) -> MockConfigEntry:
    """Register a config entry with runtime + cached descriptors in hass.data."""
    entry = MockConfigEntry(
        entry_id=entry_id,
        domain=DOMAIN,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_OBJECT_ID: 1,
        },
    )
    entry.add_to_hass(hass)

    entry_payload: dict[str, Any] = {
        DATA_RUNTIME: runtime,
        CONF_ENTITY_DESCRIPTORS: descriptors,
    }
    if entity_stats is not None:
        entry_payload[DATA_ENTITY_STATS] = entity_stats

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry_payload
    return entry
