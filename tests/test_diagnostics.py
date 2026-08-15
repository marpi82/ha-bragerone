"""Tests for diagnostics payload generation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    assert "Descriptor classification and created entity counts are aligned." in summary["health_hints"]
    assert any("fingerprint not recorded" in hint for hint in summary["health_hints"])
    assert summary["upstream_assets_fingerprint"]["cached"] is None
    assert summary["upstream_assets_fingerprint"]["mismatched"] is False
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


@pytest.mark.asyncio
async def test_diagnostics_includes_module_connectivity(hass: HomeAssistant) -> None:
    from custom_components.habragerone.const import DATA_RUNTIME
    from tests.helpers.fakes import make_runtime

    runtime, _api, gateway, _store = make_runtime(modules_meta={"DEV1": {"name": "Boiler", "connectedAt": 99}})
    gateway.modules = ["DEV1", "DEV2"]
    gateway._online["DEV1"] = True
    gateway._connected_at["DEV1"] = 99
    runtime._module_online["DEV1"] = True
    entry = register_config_entry(hass, runtime=runtime, descriptors=[{"platform": "sensor", "symbol": "TEMP"}])
    hass.data[DOMAIN][entry.entry_id][DATA_RUNTIME] = runtime

    payload = await async_get_config_entry_diagnostics(hass, entry)
    connectivity = payload["connectivity"]
    assert connectivity["DEV1"]["online"] is True
    assert connectivity["DEV1"]["connectedAt"] == 99
    assert "DEV2" in connectivity


@pytest.mark.asyncio
async def test_diagnostics_connectivity_without_gateway_modules_list(hass: HomeAssistant) -> None:
    from custom_components.habragerone.const import DATA_RUNTIME
    from tests.helpers.fakes import make_runtime

    runtime, _api, gateway, _store = make_runtime(modules_meta={"DEV1": {"name": "Boiler"}})
    gateway.modules = "not-a-list"  # type: ignore[assignment]
    runtime._module_online["DEV1"] = False
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    hass.data[DOMAIN][entry.entry_id][DATA_RUNTIME] = runtime
    payload = await async_get_config_entry_diagnostics(hass, entry)
    assert payload["connectivity"]["DEV1"]["online"] is False


@pytest.mark.asyncio
async def test_diagnostics_skips_blank_devid_connectivity(hass: HomeAssistant) -> None:
    from custom_components.habragerone.const import DATA_RUNTIME
    from tests.helpers.fakes import make_runtime

    runtime, _api, gateway, _store = make_runtime(
        modules_meta={"": {"name": "bad"}, "DEV1": {"name": "Boiler", "connectedAt": 1}}
    )
    gateway.modules = ["", "DEV1"]
    runtime._module_online["DEV1"] = True
    entry = register_config_entry(hass, runtime=runtime, descriptors=[])
    hass.data[DOMAIN][entry.entry_id][DATA_RUNTIME] = runtime

    payload = await async_get_config_entry_diagnostics(hass, entry)
    assert "" not in payload["connectivity"]
    assert payload["connectivity"]["DEV1"]["online"] is True


@pytest.mark.asyncio
async def test_diagnostics_reports_upstream_assets_fingerprint_mismatch(hass: HomeAssistant) -> None:
    from custom_components.habragerone.const import CONF_UPSTREAM_ASSETS_FINGERPRINT, DATA_API

    runtime = object()
    descriptors = [{"platform": "sensor", "symbol": "TEMP"}]
    stats = {"sensor": {"descriptor_count": 1, "created_count": 1}}
    entry = register_config_entry(hass, runtime=runtime, descriptors=descriptors, entity_stats=stats)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_UPSTREAM_ASSETS_FINGERPRINT: "2.08|index-Old.js"},
    )

    api = SimpleNamespace(
        one_base="https://one.brager.pl",
        get_system_version=AsyncMock(return_value=SimpleNamespace(version="2.08")),
        get_bytes=AsyncMock(return_value=b'<script src="/assets/index-New.js"></script>'),
    )
    hass.data[DOMAIN][entry.entry_id][DATA_API] = api

    payload = await async_get_config_entry_diagnostics(hass, entry)
    assets = payload["descriptor_summary"]["upstream_assets_fingerprint"]
    assert assets["cached"] == "2.08|index-Old.js"
    assert assets["live"] == "2.08|index-New.js"
    assert assets["mismatched"] is True
    assert payload["descriptor_summary"]["health_status"] == "warning"
    assert any("different upstream web-app bundle" in hint for hint in payload["descriptor_summary"]["health_hints"])


@pytest.mark.asyncio
async def test_diagnostics_reports_live_fingerprint_probe_failure(hass: HomeAssistant) -> None:
    from custom_components.habragerone.const import CONF_UPSTREAM_ASSETS_FINGERPRINT, DATA_API

    entry = register_config_entry(
        hass,
        runtime=object(),
        descriptors=[{"platform": "sensor", "symbol": "TEMP"}],
        entity_stats={"sensor": {"descriptor_count": 1, "created_count": 1}},
    )
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_UPSTREAM_ASSETS_FINGERPRINT: "2.08|index-Old.js"},
    )
    api = SimpleNamespace(
        one_base="https://one.brager.pl",
        get_system_version=AsyncMock(side_effect=RuntimeError("offline")),
        get_bytes=AsyncMock(),
    )
    hass.data[DOMAIN][entry.entry_id][DATA_API] = api

    payload = await async_get_config_entry_diagnostics(hass, entry)
    assets = payload["descriptor_summary"]["upstream_assets_fingerprint"]
    assert assets["cached"] == "2.08|index-Old.js"
    assert assets["live"] is None
    assert assets["mismatched"] is False
    assert assets["probe_error"] == "live probe failed"


@pytest.mark.asyncio
async def test_diagnostics_reports_api_client_missing_probe_methods(hass: HomeAssistant) -> None:
    from custom_components.habragerone.const import CONF_UPSTREAM_ASSETS_FINGERPRINT, DATA_API

    entry = register_config_entry(
        hass,
        runtime=object(),
        descriptors=[{"platform": "sensor", "symbol": "TEMP"}],
        entity_stats={"sensor": {"descriptor_count": 1, "created_count": 1}},
    )
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_UPSTREAM_ASSETS_FINGERPRINT: "2.08|index-Old.js"},
    )
    hass.data[DOMAIN][entry.entry_id][DATA_API] = object()

    payload = await async_get_config_entry_diagnostics(hass, entry)
    assets = payload["descriptor_summary"]["upstream_assets_fingerprint"]
    assert assets["probe_error"] == "api client missing probe methods"


@pytest.mark.asyncio
async def test_diagnostics_skips_connectivity_when_entry_data_not_dict(hass: HomeAssistant) -> None:
    entry = register_config_entry(hass, runtime=object(), descriptors=[])
    hass.data[DOMAIN][entry.entry_id] = "not-a-dict"  # type: ignore[assignment]
    payload = await async_get_config_entry_diagnostics(hass, entry)
    assert payload["connectivity"] == {}
