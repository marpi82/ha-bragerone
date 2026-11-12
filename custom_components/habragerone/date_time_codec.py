"""SPA DATE_TIME helpers (``yyMMddHHmm`` ↔ datetime).

Mirrors ``pybragerone.models.date_time`` so the HA datetime platform stays
usable when the installed library pin lags. Prefer the library module once
``manifest.json`` / ``pyproject.toml`` pin a release that includes the
factory-default wall-clock semantics (#372 / py-bragerone#487).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

_SERVER_FMT = "%y%m%d%H%M"
_DISPLAY_FMT = "%Y/%m/%d %H:%M"


def parse_server_date_time(raw: Any) -> datetime | None:
    """Parse Brager wire / display DATE_TIME into a naive datetime.

    Factory-default wire ``0001011200`` / ``2000-01-01 12:00`` is a normal
    wall-clock value (not ``None``). Timezone-aware inputs are rejected.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is not None:
            return None
        return raw.replace(second=0, microsecond=0)
    text = str(raw).strip()
    if not text:
        return None
    if isinstance(raw, float) and raw.is_integer():
        text = str(int(raw))
    elif isinstance(raw, int):
        text = str(raw)
    if text.isdigit():
        # JSON numbers drop leading zeros (year 00 / factory default).
        text = text.zfill(10)
        if len(text) != 10:
            return None
        try:
            parsed = datetime.strptime(text, _SERVER_FMT)
        except ValueError:
            return None
        return parsed.replace(second=0, microsecond=0)
    try:
        parsed = datetime.strptime(text, _DISPLAY_FMT)
    except ValueError:
        return None
    return parsed.replace(second=0, microsecond=0)


def format_server_date_time(value: Any) -> str | None:
    """Encode datetime / display string to Brager ``yyMMddHHmm``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            digits = text.zfill(10) if 1 <= len(text) <= 10 else text
            if len(digits) != 10:
                return None
            return digits if parse_server_date_time(digits) is not None else None
        parsed = parse_server_date_time(text)
        return parsed.strftime(_SERVER_FMT) if parsed is not None else None
    if isinstance(value, int | float):
        if isinstance(value, float) and not value.is_integer():
            return None
        if int(value) < 0:
            return None
        digits = str(int(value)).zfill(10)
        if len(digits) != 10:
            return None
        return digits if parse_server_date_time(digits) is not None else None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return None
        truncated = value.replace(second=0, microsecond=0)
        return truncated.strftime(_SERVER_FMT)
    return None
