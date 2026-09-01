"""Diagnostics support for BragerOne integration."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENTITY_DESCRIPTORS,
    CONF_PLATFORM,
    CONF_UPSTREAM_ASSETS_FINGERPRINT,
    DATA_API,
    DATA_DIAGNOSTIC_TREND,
    DATA_ENTITY_STATS,
    DATA_RUNTIME,
    DOMAIN,
    PLATFORMS,
)
from .runtime import BragerRuntime
from .upstream_assets import async_probe_upstream_assets_fingerprint

REDACT_KEYS = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, object]:
    """Return diagnostics payload for a config entry."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    descriptors_raw = runtime.get(CONF_ENTITY_DESCRIPTORS) if isinstance(runtime, dict) else None
    descriptors = descriptors_raw if isinstance(descriptors_raw, list) else []

    connectivity: dict[str, dict[str, object]] = {}
    cloud_session: dict[str, object] | None = None
    if isinstance(runtime, dict):
        brager_runtime = runtime.get(DATA_RUNTIME)
        if isinstance(brager_runtime, BragerRuntime):
            devids: set[str] = set(brager_runtime.modules_meta)
            gateway_modules = getattr(brager_runtime.gateway, "modules", None)
            if isinstance(gateway_modules, list):
                devids.update(str(devid) for devid in gateway_modules)
            for devid in sorted(devids):
                if not devid:
                    continue
                meta = brager_runtime.modules_meta.get(devid, {})
                connected_at = meta.get("connectedAt") if isinstance(meta, dict) else None
                connectivity[devid] = {
                    "online": brager_runtime.module_online(devid),
                    "connectedAt": connected_at if isinstance(connected_at, int) else None,
                }
            age_fn = getattr(brager_runtime.gateway, "last_param_update_age_s", None)
            age_s = age_fn() if callable(age_fn) else None
            live_age_fn = getattr(brager_runtime.gateway, "last_live_param_update_age_s", None)
            live_age_s = live_age_fn() if callable(live_age_fn) else None
            cloud_session = {
                "up": brager_runtime.cloud_session_up(),
                "supported": brager_runtime.supports_cloud_session,
                "last_param_update_age_s": round(age_s, 1) if isinstance(age_s, (int, float)) else None,
                "last_live_param_update_age_s": round(live_age_s, 1) if isinstance(live_age_s, (int, float)) else None,
            }

    platform_counter: Counter[str] = Counter()
    writable_counter = 0
    enum_counter = 0
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            continue
        platform = str(descriptor.get(CONF_PLATFORM, "sensor"))
        platform_counter[platform] += 1
        if bool(descriptor.get("writable")):
            writable_counter += 1
        enum_map = descriptor.get("enum_map")
        if isinstance(enum_map, dict) and len(enum_map) > 0:
            enum_counter += 1

    platform_breakdown = {platform: platform_counter.get(platform, 0) for platform in PLATFORMS}
    unknown_platforms = {
        platform: count for platform, count in sorted(platform_counter.items()) if platform not in set(PLATFORMS)
    }

    sample_symbols_by_platform: dict[str, list[str]] = {}
    for platform in [*PLATFORMS, *unknown_platforms.keys()]:
        symbols: list[str] = []
        for descriptor in descriptors:
            if not isinstance(descriptor, dict):
                continue
            if str(descriptor.get(CONF_PLATFORM, "sensor")) != platform:
                continue
            symbol = descriptor.get("symbol")
            if isinstance(symbol, str) and symbol and symbol not in symbols:
                symbols.append(symbol)
            if len(symbols) >= 5:
                break
        if symbols:
            sample_symbols_by_platform[platform] = symbols

    runtime_stats_raw = runtime.get(DATA_ENTITY_STATS) if isinstance(runtime, dict) else None
    runtime_stats = runtime_stats_raw if isinstance(runtime_stats_raw, dict) else {}
    created_total = 0
    runtime_descriptor_total = 0
    supplemental_total = 0
    for stats in runtime_stats.values():
        if not isinstance(stats, dict):
            continue
        created_count = stats.get("created_count")
        if isinstance(created_count, int):
            created_total += created_count
        descriptor_count = stats.get("descriptor_count")
        if isinstance(descriptor_count, int):
            runtime_descriptor_total += descriptor_count
        supplemental_count = stats.get("supplemental_count")
        if isinstance(supplemental_count, int):
            supplemental_total += supplemental_count

    expected_entity_total = len(descriptors) + supplemental_total
    all_platforms = set(PLATFORMS) | set(platform_breakdown.keys()) | set(runtime_stats.keys()) | set(unknown_platforms.keys())
    platform_creation_deltas: dict[str, int] = {}
    for platform in sorted(all_platforms):
        expected = platform_breakdown.get(platform, 0)
        platform_stats = runtime_stats.get(platform)
        created = 0
        supplemental = 0
        if isinstance(platform_stats, dict):
            maybe_created = platform_stats.get("created_count")
            if isinstance(maybe_created, int):
                created = maybe_created
            maybe_supplemental = platform_stats.get("supplemental_count")
            if isinstance(maybe_supplemental, int):
                supplemental = maybe_supplemental
        platform_creation_deltas[platform] = (expected + supplemental) - created

    descriptor_vs_created_mismatch = (
        runtime_descriptor_total != len(descriptors)
        or created_total != expected_entity_total
        or any(delta != 0 for delta in platform_creation_deltas.values())
    )

    mismatched_platforms = [platform for platform, delta in sorted(platform_creation_deltas.items()) if delta != 0]

    total_missing = sum(delta for delta in platform_creation_deltas.values() if delta > 0)
    total_extra = sum(-delta for delta in platform_creation_deltas.values() if delta < 0)
    mismatch_penalty = (len(mismatched_platforms) * 15) + (total_missing * 10) + (total_extra * 8)
    severity_score = min(100, mismatch_penalty)

    if severity_score == 0:
        severity_level = "none"
    elif severity_score < 35:
        severity_level = "minor"
    else:
        severity_level = "major"

    health_status = "warning" if descriptor_vs_created_mismatch else "ok"
    health_hints: list[str] = []
    if descriptor_vs_created_mismatch:
        health_hints.append("Reload config entry and compare descriptor vs created counts.")
        health_hints.append("Check entity platform setup logs for filtered or invalid descriptors.")
        if mismatched_platforms:
            health_hints.append(f"Investigate platform deltas for: {', '.join(mismatched_platforms)}.")
    else:
        health_hints.append("Descriptor classification and created entity counts are aligned.")

    cached_fingerprint_raw = entry.data.get(CONF_UPSTREAM_ASSETS_FINGERPRINT)
    cached_fingerprint = cached_fingerprint_raw if isinstance(cached_fingerprint_raw, str) and cached_fingerprint_raw else None
    live_fingerprint: str | None = None
    fingerprint_probe_error: str | None = None
    api_client = runtime.get(DATA_API) if isinstance(runtime, dict) else None
    if api_client is not None and hasattr(api_client, "get_system_version") and hasattr(api_client, "get_bytes"):
        live_fingerprint = await async_probe_upstream_assets_fingerprint(api_client)
        if live_fingerprint is None:
            fingerprint_probe_error = "live probe failed"
    elif api_client is None:
        fingerprint_probe_error = "api client unavailable"
    else:
        fingerprint_probe_error = "api client missing probe methods"

    assets_mismatched = bool(cached_fingerprint and live_fingerprint and cached_fingerprint != live_fingerprint)
    assets_fingerprint: dict[str, object] = {
        "cached": cached_fingerprint,
        "live": live_fingerprint,
        "mismatched": assets_mismatched,
    }
    if fingerprint_probe_error and live_fingerprint is None:
        assets_fingerprint["probe_error"] = fingerprint_probe_error

    if cached_fingerprint is None:
        health_hints.append("Upstream assets fingerprint not recorded yet; it is stored on the next bootstrap refresh.")
    elif assets_mismatched:
        health_status = "warning"
        health_hints.append(
            "Cached descriptors were built against a different upstream web-app bundle; "
            "review before forcing a bootstrap refresh (mismatch alone does not re-bootstrap)."
        )
        health_hints.append(f"Cached fingerprint: {cached_fingerprint}; live: {live_fingerprint}.")

    summary_core: dict[str, object] = {
        "total": len(descriptors),
        "writable": writable_counter,
        "enum_mapped": enum_counter,
        "platform_breakdown": platform_breakdown,
        "unknown_platforms": unknown_platforms,
        "sample_symbols_by_platform": sample_symbols_by_platform,
        "runtime_entity_stats": runtime_stats,
        "created_total": created_total,
        "runtime_descriptor_total": runtime_descriptor_total,
        "platform_creation_deltas": platform_creation_deltas,
        "descriptor_vs_created_mismatch": descriptor_vs_created_mismatch,
        "mismatched_platforms": mismatched_platforms,
        "total_missing_entities": total_missing,
        "total_extra_entities": total_extra,
        "severity_score": severity_score,
        "severity_level": severity_level,
        "health_status": health_status,
        "health_hints": health_hints,
        "upstream_assets_fingerprint": assets_fingerprint,
    }

    summary_fingerprint = hashlib.sha256(json.dumps(summary_core, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    generated_at_utc = datetime.now(tz=UTC).isoformat()

    previous_fingerprint: str | None = None
    previous_generated_at_utc: str | None = None
    previous_severity_score: int | None = None
    previous_severity_level: str | None = None
    previous_health_status: str | None = None
    previous_platform_creation_deltas: dict[str, int] = {}
    if isinstance(runtime, dict):
        trend_raw = runtime.get(DATA_DIAGNOSTIC_TREND)
        if isinstance(trend_raw, dict):
            prev_fp = trend_raw.get("fingerprint")
            prev_ts = trend_raw.get("generated_at_utc")
            prev_score = trend_raw.get("severity_score")
            prev_level = trend_raw.get("severity_level")
            prev_health = trend_raw.get("health_status")
            prev_deltas = trend_raw.get("platform_creation_deltas")
            if isinstance(prev_fp, str):
                previous_fingerprint = prev_fp
            if isinstance(prev_ts, str):
                previous_generated_at_utc = prev_ts
            if isinstance(prev_score, int):
                previous_severity_score = prev_score
            if isinstance(prev_level, str):
                previous_severity_level = prev_level
            if isinstance(prev_health, str):
                previous_health_status = prev_health
            if isinstance(prev_deltas, dict):
                previous_platform_creation_deltas = {
                    str(platform): int(delta) for platform, delta in prev_deltas.items() if isinstance(delta, int)
                }

        runtime[DATA_DIAGNOSTIC_TREND] = {
            "fingerprint": summary_fingerprint,
            "generated_at_utc": generated_at_utc,
            "severity_score": severity_score,
            "severity_level": severity_level,
            "health_status": health_status,
            "platform_creation_deltas": platform_creation_deltas,
        }

    changed_since_previous = bool(previous_fingerprint and previous_fingerprint != summary_fingerprint)

    all_delta_platforms = set(platform_creation_deltas) | set(previous_platform_creation_deltas)
    platform_delta_diff: dict[str, int] = {}
    for platform in sorted(all_delta_platforms):
        current_delta = platform_creation_deltas.get(platform, 0)
        previous_delta = previous_platform_creation_deltas.get(platform, 0)
        delta_change = current_delta - previous_delta
        if delta_change != 0:
            platform_delta_diff[platform] = delta_change

    severity_score_delta = None if previous_severity_score is None else (severity_score - previous_severity_score)
    severity_level_changed = bool(previous_severity_level and previous_severity_level != severity_level)
    health_status_changed = bool(previous_health_status and previous_health_status != health_status)

    if previous_fingerprint is None:
        trend_direction = "unknown"
        trend_reason = "No previous diagnostics snapshot available."
    elif health_status_changed:
        if previous_health_status == "warning" and health_status == "ok":
            trend_direction = "improved"
            trend_reason = "Health status changed from warning to ok."
        elif previous_health_status == "ok" and health_status == "warning":
            trend_direction = "regressed"
            trend_reason = "Health status changed from ok to warning."
        else:
            trend_direction = "stable"
            trend_reason = "Health status changed but not enough context for direction."
    elif severity_score_delta is not None and severity_score_delta < 0:
        trend_direction = "improved"
        trend_reason = f"Severity score decreased by {abs(severity_score_delta)}."
    elif severity_score_delta is not None and severity_score_delta > 0:
        trend_direction = "regressed"
        trend_reason = f"Severity score increased by {severity_score_delta}."
    else:
        trend_direction = "stable"
        trend_reason = "No severity or health-status change detected."

    trend_diff_summary = {
        "severity_score_delta": severity_score_delta,
        "severity_level_changed": severity_level_changed,
        "health_status_changed": health_status_changed,
        "platform_delta_diff": platform_delta_diff,
        "trend_direction": trend_direction,
        "trend_reason": trend_reason,
    }

    trend = {
        "fingerprint": summary_fingerprint,
        "generated_at_utc": generated_at_utc,
        "previous_fingerprint": previous_fingerprint,
        "previous_generated_at_utc": previous_generated_at_utc,
        "changed_since_previous": changed_since_previous,
        "diff_summary": trend_diff_summary,
    }

    summary_core["trend"] = trend

    return async_redact_data(
        {
            "entry": dict(entry.data),
            "runtime_keys": sorted(runtime.keys()) if isinstance(runtime, dict) else [],
            "descriptor_summary": summary_core,
            "connectivity": connectivity,
            "cloud_session": cloud_session,
        },
        REDACT_KEYS,
    )
