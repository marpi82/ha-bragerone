from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "habragerone"))

from command_write import (  # type: ignore[import-not-found]
    NumericTransform,
    WriteContext,
    WriteValidationError,
    enum_display_to_raw,
    enum_raw_to_display,
    prepare_write,
    select_command_route,
)


def test_enum_display_to_raw_label_conversion() -> None:
    mapping = {"Eco": 2, "Comfort": 3}
    assert enum_display_to_raw("Eco", mapping) == 2


def test_enum_raw_to_display_conversion() -> None:
    mapping = {"Eco": 2, "Comfort": 3}
    assert enum_raw_to_display(2, mapping) == "Eco"


def test_enum_invalid_value_raises_clear_error() -> None:
    mapping = {"Eco": 2, "Comfort": 3}
    with pytest.raises(WriteValidationError, match="Invalid enum value"):
        enum_display_to_raw("Turbo", mapping)


def test_prepare_write_applies_inverse_transform() -> None:
    context = WriteContext(
        symbol="P4.v1",
        has_parameter_address=True,
        has_command_rule=False,
        transform=NumericTransform(scale=0.1, offset=0.0),
        raw_min=0,
        raw_max=400,
    )
    prepared = prepare_write(20.0, context=context)

    assert prepared.raw_value == 200
    assert prepared.route == "parameter_write"


def test_prepare_write_rejects_out_of_range_value() -> None:
    context = WriteContext(
        symbol="P4.v1",
        has_parameter_address=True,
        has_command_rule=False,
        transform=NumericTransform(scale=0.1, offset=0.0),
        raw_min=0,
        raw_max=100,
    )

    with pytest.raises(WriteValidationError, match="exceeds maximum"):
        prepare_write(20.0, context=context)


def test_route_selection_behavior() -> None:
    assert select_command_route(has_parameter_address=True, has_command_rule=True) == "parameter_write"
    assert select_command_route(has_parameter_address=False, has_command_rule=True) == "raw_command"

    with pytest.raises(WriteValidationError, match="No command route available"):
        select_command_route(has_parameter_address=False, has_command_rule=False)
