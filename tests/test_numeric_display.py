"""Unit tests for numeric_display helpers and bootstrap transform resolution."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.bootstrap import (  # noqa: E402
    _apply_descriptor_transform_fields,
    _resolve_descriptor_numeric_transform,
)
from custom_components.habragerone.command_write import NumericTransform  # noqa: E402
from custom_components.habragerone.numeric_display import (  # noqa: E402
    apply_display_transform,
    descriptor_numeric_transform,
    descriptor_transform_precision,
    py_transform_to_ha,
)


def test_descriptor_numeric_transform_rejects_zero_and_bool_scale() -> None:
    assert descriptor_numeric_transform({"transform_scale": 0.0}) is None
    assert descriptor_numeric_transform({"transform_scale": False}) is None
    assert descriptor_numeric_transform({}) is None


def test_descriptor_numeric_transform_defaults_missing_offset() -> None:
    transform = descriptor_numeric_transform({"transform_scale": 0.1})
    assert transform == NumericTransform(scale=0.1, offset=0.0)


def test_descriptor_transform_precision_and_apply_display() -> None:
    assert descriptor_transform_precision({"transform_precision": 1}) == 1
    assert descriptor_transform_precision({"transform_precision": True}) is None
    assert descriptor_transform_precision({}) is None

    assert apply_display_transform(333, transform=None) == 333.0
    assert apply_display_transform(333, transform=NumericTransform(scale=0.1, offset=0.0), precision=1) == 33.3


def test_py_transform_to_ha_maps_shift_into_offset() -> None:
    transform = py_transform_to_ha(shift=-127.0, factor=1.0)
    assert transform == NumericTransform(scale=1.0, offset=-127.0)
    assert apply_display_transform(200, transform=transform) == 73.0


def test_apply_descriptor_transform_fields_sets_cached_keys() -> None:
    descriptor: dict[str, Any] = {}
    _apply_descriptor_transform_fields(
        descriptor,
        unit_code=49,
        transform_scale=0.1,
        transform_offset=0.0,
        transform_precision=1,
    )
    assert descriptor == {
        "unit_code": 49,
        "transform_scale": 0.1,
        "transform_offset": 0.0,
        "transform_precision": 1,
    }

    empty: dict[str, Any] = {}
    _apply_descriptor_transform_fields(
        empty,
        unit_code=None,
        transform_scale=None,
        transform_offset=0.0,
        transform_precision=None,
    )
    assert empty == {}


class _ParseResolver:
    """Stub ParamResolver exposing ``_parse_numeric_transform`` for bootstrap tests."""

    @staticmethod
    def _parse_numeric_transform(raw_expr: Any) -> SimpleNamespace | None:
        if not isinstance(raw_expr, str):
            return None
        if "zero" in raw_expr:
            return SimpleNamespace(shift=0.0, factor=0.0, precision=None)
        if "invalid" in raw_expr:
            return None
        if "bool_precision" in raw_expr:
            return SimpleNamespace(shift=0.0, factor=0.1, precision=True)
        if "toFixed" in raw_expr:
            return SimpleNamespace(shift=0.0, factor=0.1, precision=1)
        return SimpleNamespace(shift=0.0, factor=0.1, precision=None)


@pytest.mark.asyncio
async def test_resolve_descriptor_numeric_transform_unit_meta_non_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pybragerone.models.param_resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "ParamResolver", _ParseResolver)

    class _Resolver:
        async def _resolve_unit_meta(self, *, raw_unit_code: Any) -> str:
            return "not-a-mapping"

    unit_code, scale, offset, precision = await _resolve_descriptor_numeric_transform(
        _Resolver(),  # type: ignore[arg-type]
        {"unit_code": 49},
    )
    assert unit_code == 49
    assert (scale, offset, precision) == (None, None, None)


@pytest.mark.asyncio
async def test_resolve_descriptor_numeric_transform_units_source_code_non_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pybragerone.models.param_resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "ParamResolver", _ParseResolver)

    class _Resolver:
        async def _resolve_unit_meta(self, *, raw_unit_code: Any) -> list[str]:
            return ["not-a-mapping"]

    unit_code, scale, offset, precision = await _resolve_descriptor_numeric_transform(
        _Resolver(),  # type: ignore[arg-type]
        {"mapping": {"units_source": 66}},
    )
    assert unit_code == 66
    assert (scale, offset, precision) == (None, None, None)


@pytest.mark.asyncio
async def test_resolve_descriptor_numeric_transform_from_unit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    import pybragerone.models.param_resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "ParamResolver", _ParseResolver)

    class _Resolver:
        async def _resolve_unit_meta(self, *, raw_unit_code: Any) -> dict[str, str]:
            assert raw_unit_code == 49
            return {"value": "e => Number((e * .1).toFixed(1))"}

    unit_code, scale, offset, precision = await _resolve_descriptor_numeric_transform(
        _Resolver(),  # type: ignore[arg-type]
        {"unit_code": 49},
    )
    assert unit_code == 49
    assert scale == pytest.approx(0.1)
    assert offset == pytest.approx(0.0)
    assert precision == 1


@pytest.mark.asyncio
async def test_resolve_descriptor_numeric_transform_from_units_source_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pybragerone.models.param_resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "ParamResolver", _ParseResolver)

    unit_code, scale, offset, precision = await _resolve_descriptor_numeric_transform(
        SimpleNamespace(_resolve_unit_meta=AsyncMock()),  # type: ignore[arg-type]
        {"mapping": {"units_source": {"value": "x => x * 0.1"}}},
    )
    assert unit_code is None
    assert scale == pytest.approx(0.1)
    assert offset == pytest.approx(0.0)
    assert precision is None


@pytest.mark.asyncio
async def test_resolve_descriptor_numeric_transform_from_units_source_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pybragerone.models.param_resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "ParamResolver", _ParseResolver)

    class _Resolver:
        async def _resolve_unit_meta(self, *, raw_unit_code: Any) -> dict[str, str]:
            assert raw_unit_code == 66
            return {"value": "e => e * 0.1"}

    unit_code, scale, offset, precision = await _resolve_descriptor_numeric_transform(
        _Resolver(),  # type: ignore[arg-type]
        {"mapping": {"units_source": 66}},
    )
    assert unit_code == 66
    assert scale == pytest.approx(0.1)
    assert offset == pytest.approx(0.0)
    assert precision is None


@pytest.mark.asyncio
async def test_resolve_descriptor_numeric_transform_handles_missing_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StubResolver:
        pass

    import pybragerone.models.param_resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "ParamResolver", _StubResolver)

    unit_code, scale, offset, precision = await _resolve_descriptor_numeric_transform(
        SimpleNamespace(),  # type: ignore[arg-type]
        {"mapping": {"units_source": {"value": "e => e * 0.1"}}},
    )
    assert unit_code is None
    assert scale is None
    assert offset is None
    assert precision is None


@pytest.mark.asyncio
async def test_resolve_descriptor_numeric_transform_rejects_bool_precision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pybragerone.models.param_resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "ParamResolver", _ParseResolver)

    unit_code, scale, offset, precision = await _resolve_descriptor_numeric_transform(
        SimpleNamespace(),  # type: ignore[arg-type]
        {"mapping": {"units_source": {"value": "bool_precision"}}},
    )
    assert unit_code is None
    assert scale == pytest.approx(0.1)
    assert offset == pytest.approx(0.0)
    assert precision is None


@pytest.mark.asyncio
async def test_resolve_descriptor_numeric_transform_rejects_zero_factor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pybragerone.models.param_resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "ParamResolver", _ParseResolver)

    unit_code, scale, offset, precision = await _resolve_descriptor_numeric_transform(
        SimpleNamespace(),  # type: ignore[arg-type]
        {"mapping": {"units_source": {"value": "e => zero"}}},
    )
    assert unit_code is None
    assert scale is None
    assert offset is None
    assert precision is None


@pytest.mark.asyncio
async def test_resolve_descriptor_numeric_transform_invalid_expr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pybragerone.models.param_resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "ParamResolver", _ParseResolver)

    unit_code, scale, offset, precision = await _resolve_descriptor_numeric_transform(
        SimpleNamespace(),  # type: ignore[arg-type]
        {"mapping": {"units_source": {"value": "invalid expr"}}},
    )
    assert (unit_code, scale, offset, precision) == (None, None, None, None)


@pytest.mark.asyncio
async def test_resolve_descriptor_numeric_transform_unit_meta_exception_falls_through() -> None:
    class _Broken:
        async def _resolve_unit_meta(self, *, raw_unit_code: Any) -> dict[str, str]:
            raise RuntimeError("boom")

    unit_code, scale, offset, precision = await _resolve_descriptor_numeric_transform(
        _Broken(),  # type: ignore[arg-type]
        {"unit_code": 7},
    )
    assert unit_code == 7
    assert (scale, offset, precision) == (None, None, None)
