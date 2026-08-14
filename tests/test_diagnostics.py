"""Tests for diagnostics payload generation."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.const import (  # noqa: E402
    CONF_ENTITY_DESCRIPTORS,
    DATA_DIAGNOSTIC_TREND,
    DATA_ENTITY_STATS,
    DOMAIN,
)
from custom_components.habragerone.diagnostics import async_get_config_entry_diagnostics  # noqa: E402
from tests.helpers.hass import register_config_entry  # noqa: E402


@pytest.mark.asyncio
async def test_diagnostics_redacts_password_and_reports_aligned_health(hass: HomeAssistant) -> None:
    runtime = object()
    descriptors = [
        {"platform": "sensor", "symbol": "TEMP", "writable": False},
        {"platform": "switch", "symbol": "SW1", "writable": True},
        {
            "platform": "select",
            "symbol": "MODE",
            "writable": True,
            "enum_map": {"0": "Eco", "1": "Comfort"},
        },
    ]
    stats = {
        "sensor": {"descriptor_count": 1, "created_count": 1},
        "switch": {"descriptor_count": 1, "created_count": 1},
        "select": {"descriptor_count": 1, "created_count": 1},
    }
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors, entity_stats=stats)

    payload = await async_get_config_entry_diagnostics(hass, entry)

    assert payload["entry"][CONF_PASSWORD] == "**REDACTED**"
    summary = payload["descriptor_summary"]
    assert summary["total"] == 3
    assert summary["writable"] == 2
    assert summary["enum_mapped"] == 1
    assert summary["health_status"] == "ok"
    assert summary["severity_level"] == "none"
    assert summary["health_hints"] == ["Descriptor classification and created entity counts are aligned."]
    assert "sensor" in summary["sample_symbols_by_platform"]


@pytest.mark.asyncio
async def test_diagnostics_reports_warning_when_entity_counts_mismatch(hass: HomeAssistant) -> None:
    runtime = object()
    descriptors = [
        {"platform": "sensor", "symbol": "TEMP"},
        {"platform": "switch", "symbol": "SW1"},
    ]
    stats = {
        "sensor": {"descriptor_count": 2, "created_count": 1},
        "switch": {"descriptor_count": 1, "created_count": 0},
    }
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors, entity_stats=stats)

    payload = await async_get_config_entry_diagnostics(hass, entry)
    summary = payload["descriptor_summary"]

    assert summary["health_status"] == "warning"
    assert summary["descriptor_vs_created_mismatch"] is True
    assert "switch" in summary["mismatched_platforms"]
    assert summary["severity_level"] in {"minor", "major"}
    assert any("Reload config entry" in hint for hint in summary["health_hints"])


@pytest.mark.asyncio
async def test_diagnostics_tracks_trend_and_detects_regression(hass: HomeAssistant) -> None:
    runtime = object()
    descriptors = [{"platform": "sensor", "symbol": "TEMP"}]
    stats = {"sensor": {"descriptor_count": 1, "created_count": 1}}
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors, entity_stats=stats)

    first = await async_get_config_entry_diagnostics(hass, entry)
    assert first["descriptor_summary"]["trend"]["diff_summary"]["trend_direction"] == "unknown"

    runtime_data = hass.data[DOMAIN][entry.entry_id]
    runtime_data[DATA_ENTITY_STATS] = {"sensor": {"descriptor_count": 1, "created_count": 0}}
    runtime_data[CONF_ENTITY_DESCRIPTORS] = descriptors

    second = await async_get_config_entry_diagnostics(hass, entry)
    trend = second["descriptor_summary"]["trend"]
    assert trend["changed_since_previous"] is True
    assert trend["diff_summary"]["health_status_changed"] is True
    assert trend["diff_summary"]["trend_direction"] == "regressed"
    assert DATA_DIAGNOSTIC_TREND in runtime_data


@pytest.mark.asyncio
async def test_diagnostics_reports_unknown_platforms(hass: HomeAssistant) -> None:
    runtime = object()
    descriptors = [{"platform": "climate", "symbol": "HVAC"}]
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors)

    payload = await async_get_config_entry_diagnostics(hass, entry)
    summary = payload["descriptor_summary"]

    assert summary["unknown_platforms"] == {"climate": 1}
    assert "climate" not in summary["platform_breakdown"]
