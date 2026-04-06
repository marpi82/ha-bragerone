"""Helpers for evaluating BragerOne status command rules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def resolve_rule_display_value(
    *,
    descriptor: Mapping[str, Any],
    flat_values: Mapping[str, Any],
    default_actual: Any,
) -> Any | None:
    """Return the first matched rule value normalized for display."""
    mapping = descriptor.get("mapping")
    if not isinstance(mapping, Mapping):
        return None
    command_rules = mapping.get("command_rules")
    if not isinstance(command_rules, list) or not command_rules:
        return None

    for rule in command_rules:
        if not isinstance(rule, Mapping):
            continue
        if not rule_matches(rule, flat_values=flat_values, default_actual=default_actual):
            continue
        value = rule.get("value")
        if value is None:
            continue
        return normalize_rule_value(value)
    return None


def resolve_rule_bool(
    *,
    descriptor: Mapping[str, Any],
    flat_values: Mapping[str, Any],
    default_actual: Any,
) -> bool | None:
    """Resolve rule output to boolean for binary-state entities."""
    display = resolve_rule_display_value(descriptor=descriptor, flat_values=flat_values, default_actual=default_actual)
    if not isinstance(display, str):
        return None
    norm = display.strip().casefold()
    if norm in {"on", "on manual", "enabled", "true", "yes"}:
        return True
    if norm in {"off", "off manual", "disabled", "false", "no"}:
        return False
    return None


def rule_matches(rule: Mapping[str, Any], *, flat_values: Mapping[str, Any], default_actual: Any) -> bool:
    """Check whether all/any rule conditions match current values."""
    conditions = rule.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        return True

    condition_results: list[bool] = []
    for cond in conditions:
        if not isinstance(cond, Mapping):
            return False
        condition_results.append(_condition_matches(cond, flat_values=flat_values, default_actual=default_actual))

    logic = str(rule.get("logic") or "").strip().casefold()
    if logic == "any":
        return any(condition_results)
    return all(condition_results)


def _condition_matches(cond: Mapping[str, Any], *, flat_values: Mapping[str, Any], default_actual: Any) -> bool:
    operation = cond.get("operation")
    expected = cond.get("expected")
    targets = cond.get("targets")
    if not isinstance(operation, str):
        return False
    if not isinstance(targets, list) or not targets:
        return compare_condition(operation=operation, actual=default_actual, expected=expected)
    for target in targets:
        if not isinstance(target, Mapping):
            return False
        actual = read_target_actual(target, flat_values=flat_values)
        if not compare_condition(operation=operation, actual=actual, expected=expected):
            return False
    return True


def read_target_actual(target: Mapping[str, Any], *, flat_values: Mapping[str, Any]) -> Any:
    """Read target value from flat payload, optionally applying bit/mask."""
    address = target.get("address")
    if not isinstance(address, str) or not address.strip():
        return None
    value = flat_values.get(address.strip())
    if not isinstance(value, int):
        return value
    bit = target.get("bit")
    if isinstance(bit, int):
        return (value >> bit) & 1
    mask = target.get("mask")
    if isinstance(mask, int):
        return value & mask
    return value


def compare_condition(*, operation: str, actual: Any, expected: Any) -> bool:
    """Evaluate one rule operation against actual and expected values."""
    op = operation.strip()
    if "." in op:
        op = op.rsplit(".", 1)[-1]
    if op == "equalTo":
        return actual == expected
    if op == "notEqualTo":
        return actual != expected
    return False


def normalize_rule_value(value: Any) -> Any:
    """Normalize token-like rule values to user-friendly text."""
    if isinstance(value, str):
        token = value.strip()
        if "." in token:
            token = token.rsplit(".", 1)[-1]
        norm = token.casefold()
        if norm.startswith("on"):
            return "On"
        if norm.startswith("off"):
            return "Off"
        return token.replace("_", " ").title()
    return value

