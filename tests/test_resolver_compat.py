"""Tests for ParamResolver ``devid`` signature-compat helpers (#386 / py-bragerone#502)."""

from __future__ import annotations

import pytest

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.resolver_compat import (  # noqa: E402
    accepts_devid,
    devid_kwargs,
    resolve_value_for_devid,
)


def _legacy(symbol: str) -> str:
    return symbol


def _explicit(symbol: str, *, devid: str | None = None) -> str:
    return f"{symbol}:{devid}"


def _var_kw(symbol: str, **kwargs: object) -> str:
    return f"{symbol}:{kwargs.get('devid')}"


def _positional_only(symbol: str, devid: str | None = None, /) -> str:
    return symbol


def test_accepts_devid_detects_signatures() -> None:
    assert accepts_devid(_legacy) is False
    assert accepts_devid(_explicit) is True
    assert accepts_devid(_var_kw) is True
    assert accepts_devid(_positional_only) is False


def test_accepts_devid_returns_false_when_signature_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import inspect

    def _boom(_func: object) -> inspect.Signature:
        raise ValueError("no signature")

    monkeypatch.setattr(inspect, "signature", _boom)
    assert accepts_devid(_explicit) is False


def test_devid_kwargs_requires_devid_and_support() -> None:
    assert devid_kwargs(_explicit, "DEV1") == {"devid": "DEV1"}
    assert devid_kwargs(_explicit, " DEV1 ") == {"devid": "DEV1"}
    assert devid_kwargs(_explicit, None) == {}
    assert devid_kwargs(_explicit, " ") == {}
    assert devid_kwargs(_legacy, "DEV1") == {}


@pytest.mark.asyncio
async def test_resolve_value_for_devid_forwards_only_when_supported() -> None:
    class _New:
        async def resolve_value(self, symbol: str, *, devid: str | None = None) -> str:
            return f"{symbol}:{devid}"

    class _Old:
        async def resolve_value(self, symbol: str) -> str:
            return symbol

    assert await resolve_value_for_devid(_New(), "S", devid="DEV1") == "S:DEV1"
    assert await resolve_value_for_devid(_New(), "S") == "S:None"
    assert await resolve_value_for_devid(_Old(), "S", devid="DEV1") == "S"
