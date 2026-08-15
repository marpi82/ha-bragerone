"""Upstream web-app asset fingerprint helpers (visibility for cache staleness).

Matches the fingerprint shape used by py-bragerone's upstream-assets watch:
``{api_version}|{index-*.js}``. Recorded at bootstrap and compared in diagnostics
without forcing a re-bootstrap on mismatch.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from pybragerone.models.catalog import INDEX_ASSET_RE

LOGGER = logging.getLogger(__name__)

_FINGERPRINT_SEP = "|"


class _FingerprintClient(Protocol):
    """Minimal API surface needed to probe the public catalog fingerprint."""

    @property
    def one_base(self) -> str:
        """Public web-app origin used to discover ``index-*.js``."""
        ...

    async def get_system_version(self) -> Any:
        """Return a payload with a ``version`` attribute/string."""
        ...

    async def get_bytes(self, url: str) -> bytes:
        """Fetch raw bytes for a public URL."""
        ...


def build_upstream_assets_fingerprint(*, api_version: str, index_asset: str) -> str:
    """Return a stable fingerprint of API version plus frontend index asset name."""
    return f"{api_version.strip()}{_FINGERPRINT_SEP}{index_asset.strip()}"


def index_asset_from_url(url: str | None) -> str | None:
    """Extract ``index-*.js`` from an assets URL, if present."""
    if not isinstance(url, str) or not url.strip():
        return None
    match = INDEX_ASSET_RE.search(url)
    if match is None:
        return None
    return match.group(1)


async def async_discover_index_asset(client: _FingerprintClient) -> str:
    """Read ``index-*.js`` from the public web-app homepage (no login)."""
    base = str(getattr(client, "one_base", "") or "").rstrip("/")
    if not base:
        raise RuntimeError("API client has no one_base for index discovery")
    last_error = "no pages fetched"
    for page_url in (f"{base}/", f"{base}/assets/"):
        try:
            html = (await client.get_bytes(page_url)).decode("utf-8", errors="replace")
        except Exception as exc:
            last_error = str(exc)
            continue
        match = INDEX_ASSET_RE.search(html)
        if match:
            return match.group(1)
    raise RuntimeError(f"could not discover index-*.js from {base} ({last_error})")


def _version_string(version_payload: Any) -> str:
    if isinstance(version_payload, str):
        return version_payload
    version = getattr(version_payload, "version", None)
    if isinstance(version, str):
        return version
    if isinstance(version_payload, dict):
        nested = version_payload.get("version")
        if isinstance(nested, str):
            return nested
    raise RuntimeError("system version payload has no version string")


async def async_probe_upstream_assets_fingerprint(client: _FingerprintClient) -> str | None:
    """Best-effort live fingerprint; returns None when the probe fails."""
    try:
        version_payload = await client.get_system_version()
        api_version = _version_string(version_payload).strip()
        index_asset = (await async_discover_index_asset(client)).strip()
    except Exception:
        LOGGER.debug("Upstream assets fingerprint probe failed", exc_info=True)
        return None
    if not api_version or not index_asset:
        return None
    return build_upstream_assets_fingerprint(api_version=api_version, index_asset=index_asset)
