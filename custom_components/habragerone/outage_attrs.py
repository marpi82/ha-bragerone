"""Shared connectivity outage attribute helpers for entity + diagnostics UI."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

_OUTAGE_KEYS = ("down_since", "down_for_s", "reason", "last_down_for_s", "last_reason")


def extract_outage_fields(event: Any) -> dict[str, float | str | None]:
    """Pull additive outage fields from a gateway event or mapping (duck-typed).

    Booleans are rejected (``bool`` is a subclass of ``int``), empty strings become
    ``None``, and numeric values are normalized to ``float``.
    """
    snapshot: dict[str, float | str | None] = {}
    for key in _OUTAGE_KEYS:
        value = event.get(key) if isinstance(event, Mapping) else getattr(event, key, None)
        if isinstance(value, bool):
            snapshot[key] = None
        elif isinstance(value, (int, float)):
            snapshot[key] = float(value)
        elif isinstance(value, str) and value:
            snapshot[key] = value
        else:
            snapshot[key] = None
    return snapshot


def outage_snapshot_has_values(snapshot: Mapping[str, Any]) -> bool:
    """Return ``True`` when *snapshot* carries any non-``None`` outage field."""
    return any(snapshot.get(key) is not None for key in _OUTAGE_KEYS)


def outage_state_attributes(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build HA entity/diagnostic attributes from an outage snapshot.

    While down, ``down_for_s`` is derived from wall-clock ``down_since``
    (``time.time()`` epoch from the library — not monotonic) whenever attributes
    are recomputed (typically on the next connectivity/session state write —
    Home Assistant does not refresh attributes on a timer). ``reason`` /
    ``last_reason`` are client observation sources, not plant hardware diagnostics.

    While an outage is active (``down_since`` set), only live ``down_*`` /
    ``reason`` are exposed — prior-cycle ``last_*`` stay hidden until restore.
    """
    if not isinstance(snapshot, Mapping):
        return {}
    attrs: dict[str, Any] = {}
    down_since = snapshot.get("down_since")
    if isinstance(down_since, bool):
        down_since = None
    if isinstance(down_since, (int, float)):
        since = float(down_since)
        attrs["down_since"] = since
        attrs["down_for_s"] = round(max(0.0, time.time() - since), 1)
        reason = snapshot.get("reason")
        if isinstance(reason, str) and reason:
            attrs["reason"] = reason
        return attrs
    last_down = snapshot.get("last_down_for_s")
    if isinstance(last_down, bool):
        last_down = None
    if isinstance(last_down, (int, float)):
        attrs["last_down_for_s"] = round(float(last_down), 1)
    last_reason = snapshot.get("last_reason")
    if isinstance(last_reason, str) and last_reason:
        attrs["last_reason"] = last_reason
    return attrs
