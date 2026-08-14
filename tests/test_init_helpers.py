"""Tests for integration setup helper functions."""

from __future__ import annotations

import ssl

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.__init__ import (  # noqa: E402
    _build_ssl_context,
    _descriptors_require_refresh,
)


def test_descriptors_require_refresh_rejects_non_list() -> None:
    assert _descriptors_require_refresh(None) is True
    assert _descriptors_require_refresh({"symbol": "X"}) is True


def test_descriptors_require_refresh_rejects_empty_list() -> None:
    """Zero entities is a transient failure (e.g. an offline module), never a valid cache."""
    assert _descriptors_require_refresh([]) is True


def test_descriptors_require_refresh_select_without_options() -> None:
    descriptors = [{"platform": "select", "symbol": "MODE"}]
    assert _descriptors_require_refresh(descriptors) is True


def test_descriptors_require_refresh_select_with_empty_options() -> None:
    descriptors = [{"platform": "select", "symbol": "MODE", "options": []}]
    assert _descriptors_require_refresh(descriptors) is True


def test_descriptors_require_refresh_accepts_valid_cached_payload() -> None:
    descriptors = [
        {"platform": "sensor", "symbol": "TEMP"},
        {"platform": "select", "symbol": "MODE", "options": ["Eco", "Comfort"]},
    ]
    assert _descriptors_require_refresh(descriptors) is False


def test_build_ssl_context_returns_default_context() -> None:
    context = _build_ssl_context()
    assert isinstance(context, ssl.SSLContext)
