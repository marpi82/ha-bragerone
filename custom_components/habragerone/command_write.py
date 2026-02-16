"""Utilities for safe command write conversion and validation."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

type RawValue = str | int | float | bool
type CommandRoute = Literal["parameter_write", "raw_command"]

LOGGER = logging.getLogger(__name__)


class WriteValidationError(ValueError):
    """Raised when a command write value cannot be validated or converted."""


@dataclass(frozen=True, slots=True)
class NumericTransform:
    """Represents a display-to-raw linear transform.

    Display value is modeled as: ``display = raw * scale + offset``.
    Write conversion applies the inverse: ``raw = (display - offset) / scale``.
    """

    scale: float = 1.0
    offset: float = 0.0


@dataclass(frozen=True, slots=True)
class WriteContext:
    """Input metadata required to build a safe command write value."""

    symbol: str
    has_parameter_address: bool
    has_command_rule: bool
    enum_mapping: Mapping[str, RawValue] | None = None
    transform: NumericTransform | None = None
    raw_min: float | None = None
    raw_max: float | None = None


@dataclass(frozen=True, slots=True)
class PreparedWrite:
    """A validated command write payload ready for sending."""

    symbol: str
    input_display_value: RawValue
    raw_value: RawValue
    route: CommandRoute


def enum_display_to_raw(display_value: RawValue, enum_mapping: Mapping[str, RawValue]) -> RawValue:
    """Convert display enum label/option into raw backend value.

    Args:
        display_value: User-facing value coming from HA service/entity input.
        enum_mapping: Mapping from display label to raw backend value.

    Returns:
        Raw backend value.

    Raises:
        WriteValidationError: When conversion is not possible.
    """
    if display_value in enum_mapping:
        return enum_mapping[str(display_value)]

    if display_value in enum_mapping.values():
        return display_value

    labels = ", ".join(sorted(enum_mapping.keys()))
    raise WriteValidationError(f"Invalid enum value '{display_value}'. Allowed labels: [{labels}] or matching raw mapped value.")


def enum_raw_to_display(raw_value: RawValue, enum_mapping: Mapping[str, RawValue]) -> RawValue:
    """Convert raw backend enum value to display label when mapping exists."""
    for label, mapped_raw in enum_mapping.items():
        if mapped_raw == raw_value:
            return label
    return raw_value


def select_command_route(*, has_parameter_address: bool, has_command_rule: bool) -> CommandRoute:
    """Select command route according to available metadata."""
    if has_parameter_address:
        return "parameter_write"
    if has_command_rule:
        return "raw_command"
    raise WriteValidationError("No command route available: missing parameter address and command rule.")


def _coerce_number(raw_value: float) -> int | float:
    if raw_value.is_integer():
        return int(raw_value)
    return raw_value


def _inverse_transform(value: int | float, transform: NumericTransform) -> int | float:
    if transform.scale == 0:
        raise WriteValidationError("Invalid transform: scale cannot be 0.")
    return _coerce_number((float(value) - transform.offset) / transform.scale)


def _validate_raw_bounds(*, raw_value: int | float, raw_min: float | None, raw_max: float | None, symbol: str) -> None:
    if raw_min is not None and raw_value < raw_min:
        raise WriteValidationError(f"Raw value {raw_value} for '{symbol}' is below minimum {raw_min}.")
    if raw_max is not None and raw_value > raw_max:
        raise WriteValidationError(f"Raw value {raw_value} for '{symbol}' exceeds maximum {raw_max}.")


def prepare_write(input_display_value: RawValue, *, context: WriteContext) -> PreparedWrite:
    """Prepare write payload with enum conversion, inverse transform and bounds validation."""
    converted_value: RawValue = input_display_value
    if context.enum_mapping is not None:
        converted_value = enum_display_to_raw(input_display_value, context.enum_mapping)

    numeric_raw_value: int | float | None = None
    if isinstance(converted_value, int | float) and not isinstance(converted_value, bool):
        numeric_raw_value = converted_value
        if context.transform is not None:
            numeric_raw_value = _inverse_transform(numeric_raw_value, context.transform)
        _validate_raw_bounds(
            raw_value=numeric_raw_value,
            raw_min=context.raw_min,
            raw_max=context.raw_max,
            symbol=context.symbol,
        )
        converted_value = numeric_raw_value

    route = select_command_route(
        has_parameter_address=context.has_parameter_address,
        has_command_rule=context.has_command_rule,
    )

    LOGGER.debug(
        "Prepared command write: symbol=%s input_display_value=%s raw_value=%s route=%s",
        context.symbol,
        input_display_value,
        converted_value,
        route,
    )

    return PreparedWrite(
        symbol=context.symbol,
        input_display_value=input_display_value,
        raw_value=converted_value,
        route=route,
    )
