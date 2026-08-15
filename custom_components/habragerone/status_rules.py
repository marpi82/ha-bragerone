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
    return status_label_to_bool(display)


def status_label_to_bool(value: Any) -> bool | None:
    """Map a STATUS display label/token to on/off, or None when unknown."""
    if not isinstance(value, str):
        return None
    norm = value.strip().casefold()
    if norm in _BOOL_TRUE_TOKENS:
        return True
    if norm in _BOOL_FALSE_TOKENS:
        return False
    return None


def resolve_entity_bool(
    *,
    descriptor: Mapping[str, Any],
    flat_values: Mapping[str, Any],
    default_actual: Any,
) -> bool:
    """Resolve on/off for switches and binary sensors.

    Prefer command-rule labels, then bit/mask inputs from the mapping (when several
    bits share one address, use the lowest bit — e.g. PumpState ON/OFF on bit 1
    before manual bit 3), and finally a conservative raw coercion that refuses
    multi-bit status words.
    """
    rule_value = resolve_rule_bool(descriptor=descriptor, flat_values=flat_values, default_actual=default_actual)
    if rule_value is not None:
        return rule_value

    mapping = descriptor.get("mapping")
    if isinstance(mapping, Mapping):
        inputs = mapping.get("inputs")
        if isinstance(inputs, list):
            bit_inputs = [
                entry
                for entry in inputs
                if isinstance(entry, Mapping) and (isinstance(entry.get("bit"), int) or isinstance(entry.get("mask"), int))
            ]
            preferred = _preferred_bit_input(bit_inputs)
            if preferred is not None:
                actual = read_target_actual(preferred, flat_values=flat_values)
                if isinstance(actual, int | float) and not isinstance(actual, bool):
                    return bool(int(actual))

    return coerce_status_bool(default_actual)


def _preferred_bit_input(bit_inputs: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """Pick the best bit/mask input when command rules did not resolve."""
    if not bit_inputs:
        return None
    if len(bit_inputs) == 1:
        return bit_inputs[0]

    addresses = {str(entry.get("address") or "") for entry in bit_inputs}
    if len(addresses) != 1:
        return None

    numbered = [entry for entry in bit_inputs if isinstance(entry.get("bit"), int)]
    if not numbered:
        return None
    return min(numbered, key=lambda entry: int(entry["bit"]))


_BOOL_TRUE_TOKENS = frozenset(
    {
        "on",
        "on manual",
        "enabled",
        "true",
        "yes",
        "1",
        "tak",
        "włączony",
        "wlaczony",
        "włączone",
        "wlaczone",
        "włączono",
        "wlaczono",
        "załączony",
        "zalaczony",
        "załączone",
        "zalaczone",
        "załączono",
        "zalaczono",
    }
)
_BOOL_FALSE_TOKENS = frozenset(
    {
        "off",
        "off manual",
        "disabled",
        "false",
        "no",
        "0",
        "nie",
        "wyłączony",
        "wylaczony",
        "wyłączone",
        "wylaczone",
        "wyłączono",
        "wylaczono",
    }
)


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


def _as_bitmask_int(value: Any) -> int | None:
    """Coerce JSON numbers (including floats like ``64.0``) to ints for bit ops."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def read_target_actual(target: Mapping[str, Any], *, flat_values: Mapping[str, Any]) -> Any:
    """Read target value from flat payload, optionally applying bit/mask."""
    address = target.get("address")
    if not isinstance(address, str) or not address.strip():
        return None
    value = flat_values.get(address.strip())
    bitmask_value = _as_bitmask_int(value)
    if bitmask_value is None:
        return value
    bit = target.get("bit")
    if isinstance(bit, int):
        return (bitmask_value >> bit) & 1
    mask = target.get("mask")
    if isinstance(mask, int):
        return bitmask_value & mask
    return bitmask_value


def coerce_status_bool(value: Any) -> bool:
    """Coerce obvious on/off tokens; refuse multi-bit status words without a rule."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        as_int = int(value)
        if as_int in (0, 1):
            return bool(as_int)
        return False
    if isinstance(value, str):
        norm = value.strip().casefold()
        if norm in _BOOL_TRUE_TOKENS:
            return True
        if norm in _BOOL_FALSE_TOKENS:
            return False
    return False


def compare_condition(*, operation: str, actual: Any, expected: Any) -> bool:
    """Evaluate one rule operation against actual and expected values."""
    op = operation.strip()
    if "." in op:
        op = op.rsplit(".", 1)[-1]
    if op == "equalTo":
        return bool(actual == expected)
    if op == "notEqualTo":
        return bool(actual != expected)
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
