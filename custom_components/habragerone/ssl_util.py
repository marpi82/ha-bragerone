"""SSL helpers that keep certificate loading off the Home Assistant event loop."""

from __future__ import annotations

import ssl

from homeassistant.core import HomeAssistant


def build_ssl_context() -> ssl.SSLContext:
    """Create a default verifying SSL context (blocking; run in an executor)."""
    return ssl.create_default_context()


async def async_ssl_verify_context(hass: HomeAssistant) -> ssl.SSLContext:
    """Build a verifying SSLContext via HA's executor."""
    return await hass.async_add_executor_job(build_ssl_context)
