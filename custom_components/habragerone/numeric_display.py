"""Helpers for display↔raw numeric transforms cached on entity descriptors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .command_write import NumericTransform


def descriptor_numeric_transform(descriptor: Mapping[str, Any]) -> NumericTransform | None:
    """Build a write/display transform from cached descriptor fields.

    Library unit transforms use ``display = (raw + shift) * factor``. Home Assistant
    caches the equivalent ``display = raw * scale + offset`` form where
    ``scale = factor`` and ``offset = shift * factor``.
    """
    scale = descriptor.get("transform_scale")
    if not isinstance(scale, int | float) or isinstance(scale, bool):
        return None
    if float(scale) == 0.0:
        return None
    offset = descriptor.get("transform_offset")
    offset_f = float(offset) if isinstance(offset, int | float) and not isinstance(offset, bool) else 0.0
    return NumericTransform(scale=float(scale), offset=offset_f)


def descriptor_transform_precision(descriptor: Mapping[str, Any]) -> int | None:
    """Return cached display precision when present."""
    precision = descriptor.get("transform_precision")
    if isinstance(precision, int) and not isinstance(precision, bool) and precision >= 0:
        return precision
    return None


def apply_display_transform(
    raw_value: int | float,
    *,
    transform: NumericTransform | None,
    precision: int | None = None,
) -> float:
    """Convert a raw backend value to the user-facing display number."""
    display = float(raw_value) if transform is None else float(raw_value) * transform.scale + transform.offset
    if precision is not None:
        return float(round(display, precision))
    return display


def py_transform_to_ha(*, shift: float, factor: float) -> NumericTransform:
    """Map pybragerone ``(raw + shift) * factor`` onto HA ``raw * scale + offset``."""
    return NumericTransform(scale=float(factor), offset=float(shift) * float(factor))
