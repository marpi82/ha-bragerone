"""SPA DATE_TIME helpers (``yyMMddHHmm`` ↔ datetime).

Mirrors ``pybragerone.models.date_time`` so the HA datetime platform can land
before the library pin that ships that module. Prefer the library import once
``manifest.json`` / ``pyproject.toml`` pin a release that includes it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

_SERVER_FMT = "%y%m%d%H%M"
_DISPLAY_FMT = "%Y/%m/%d %H:%M"
_UNSET_RAW = "0001011200"


def parse_server_date_time(raw: Any) -> datetime | None:
    """Parse Brager wire / display DATE_TIME into a naive datetime."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None) if raw.tzinfo is not None else raw
    text = str(raw).strip()
    if not text or text == _UNSET_RAW:
        return None
    if isinstance(raw, float) and raw.is_integer():
        text = str(int(raw))
    elif isinstance(raw, int):
        text = str(raw)
    if text.isdigit():
        if len(text) != 10:
            return None
        try:
            return datetime.strptime(text, _SERVER_FMT)
        except ValueError:
            return None
    try:
        return datetime.strptime(text, _DISPLAY_FMT)
    except ValueError:
        return None


def format_server_date_time(value: Any) -> str | None:
    """Encode datetime / display string to Brager ``yyMMddHHmm``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text == _UNSET_RAW:
            return _UNSET_RAW
        if text.isdigit() and len(text) == 10:
            return text if parse_server_date_time(text) is not None else None
        parsed = parse_server_date_time(text)
        return parsed.strftime(_SERVER_FMT) if parsed is not None else None
    parsed = parse_server_date_time(value)
    return parsed.strftime(_SERVER_FMT) if parsed is not None else None
