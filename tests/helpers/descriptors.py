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
    mapping: dict[str, Any] = {"command_rules": command_rules or []}
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
) -> dict[str, Any]:
    """Build a descriptor with command_rules (raw command route)."""
    return {
        "symbol": symbol,
        "devid": devid,
        "pool": pool,
        "chan": chan,
        "idx": idx,
        "platform": "switch",
        "mapping": {"command_rules": command_rules},
    }
