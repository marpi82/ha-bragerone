"""Descriptor fixtures for platform and runtime write tests."""

from __future__ import annotations

from typing import Any


def writable_parameter_descriptor(
    *,
    symbol: str = "PARAM_0",
    devid: str = "DEV1",
    pool: str = "P6",
    chan: str = "v",
    idx: int = 0,
    parameter_name: str | None = "parameters.PARAM_0",
    raw_min: float | None = None,
    raw_max: float | None = None,
    command_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a descriptor that routes writes through the parameter path."""
    mapping: dict[str, Any] = {"command_rules": command_rules if command_rules is not None else []}
    if parameter_name is not None:
        mapping["raw"] = {"name": parameter_name}
    descriptor: dict[str, Any] = {
        "symbol": symbol,
        "devid": devid,
        "pool": pool,
        "chan": chan,
        "idx": idx,
        "platform": "number",
        "mapping": mapping,
    }
    if raw_min is not None:
        descriptor["min"] = raw_min
    if raw_max is not None:
        descriptor["max"] = raw_max
    return descriptor


def command_rule_descriptor(
    *,
    symbol: str = "URUCHOMIENIE_KOTLA",
    devid: str = "DEV1",
    pool: str = "P5",
    chan: str = "s",
    idx: int = 0,
    command_rules: list[dict[str, Any]],
    platform: str = "switch",
    label: str | None = None,
    panel_path: str | None = None,
    module_name: str | None = "boiler_module",
) -> dict[str, Any]:
    """Build a descriptor with command_rules (raw command route)."""
    descriptor: dict[str, Any] = {
        "symbol": symbol,
        "devid": devid,
        "pool": pool,
        "chan": chan,
        "idx": idx,
        "platform": platform,
        "mapping": {"command_rules": command_rules},
    }
    if label is not None:
        descriptor["label"] = label
    if panel_path is not None:
        descriptor["panel_path"] = panel_path
    if module_name is not None:
        descriptor["module_name"] = module_name
    return descriptor


def switch_descriptor(
    *,
    symbol: str = "SWITCH_0",
    devid: str = "DEV1",
    pool: str = "P5",
    chan: str = "s",
    idx: int = 0,
    mapping_inputs: list[dict[str, str]] | None = None,
    command_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a switch-platform descriptor."""
    mapping: dict[str, Any] = {"command_rules": command_rules if command_rules is not None else []}
    if mapping_inputs:
        mapping["inputs"] = mapping_inputs
    return {
        "symbol": symbol,
        "devid": devid,
        "pool": pool,
        "chan": chan,
        "idx": idx,
        "platform": "switch",
        "label": "Test switch",
        "module_name": "module_a",
        "mapping": mapping,
    }


def select_descriptor(
    *,
    symbol: str = "MODE_SELECT",
    devid: str = "DEV1",
    pool: str = "P6",
    chan: str = "v",
    idx: int = 0,
    options: list[str] | None = None,
    enum_map: dict[str, str | int] | None = None,
    raw_to_label: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a select-platform descriptor with enum options."""
    return {
        "symbol": symbol,
        "devid": devid,
        "pool": pool,
        "chan": chan,
        "idx": idx,
        "platform": "select",
        "label": "Operating mode",
        "module_name": "module_a",
        "options": ["Eco", "Comfort"] if options is None else options,
        "enum_map": {"Eco": 2, "Comfort": 3} if enum_map is None else enum_map,
        "raw_to_label": {"2": "Eco", "3": "Comfort"} if raw_to_label is None else raw_to_label,
        "mapping": {"command_rules": []},
    }


def binary_sensor_descriptor(
    *,
    symbol: str = "FLAG_0",
    devid: str = "DEV1",
    pool: str = "P5",
    chan: str = "s",
    idx: int = 0,
    command_rules: list[dict[str, Any]] | None = None,
    mapping_inputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a binary_sensor-platform descriptor."""
    mapping: dict[str, Any] = {"command_rules": command_rules if command_rules is not None else []}
    if mapping_inputs:
        mapping["inputs"] = mapping_inputs
    return {
        "symbol": symbol,
        "devid": devid,
        "pool": pool,
        "chan": chan,
        "idx": idx,
        "platform": "binary_sensor",
        "label": "Pump active",
        "module_name": "module_a",
        "mapping": mapping,
    }


def button_descriptor(
    *,
    symbol: str = "ACTION_BTN",
    devid: str = "DEV1",
    command_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a button-platform descriptor."""
    return {
        "symbol": symbol,
        "devid": devid,
        "pool": "P5",
        "chan": "s",
        "idx": 0,
        "platform": "button",
        "label": "Reset alarm",
        "module_name": "module_a",
        "mapping": {
            "command_rules": command_rules if command_rules is not None else [{"command": "RESET_ALARM", "value": True}],
        },
    }


def sensor_descriptor(
    *,
    symbol: str = "TEMP_1",
    devid: str = "DEV1",
    pool: str = "P6",
    chan: str = "v",
    idx: int = 0,
    unit: str | None = "°C",
    raw_to_label: dict[str, str] | None = None,
    command_rules: list[dict[str, Any]] | None = None,
    mapping_channels: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a sensor-platform descriptor."""
    mapping: dict[str, Any] = {"command_rules": command_rules if command_rules is not None else []}
    if mapping_channels is not None:
        mapping["channels"] = mapping_channels
    descriptor: dict[str, Any] = {
        "symbol": symbol,
        "devid": devid,
        "pool": pool,
        "chan": chan,
        "idx": idx,
        "platform": "sensor",
        "label": "Boiler temperature",
        "module_name": "module_a",
        "mapping": mapping,
    }
    if unit is not None:
        descriptor["unit"] = unit
    if raw_to_label is not None:
        descriptor["raw_to_label"] = raw_to_label
    return descriptor
