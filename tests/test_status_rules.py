"""Unit tests for status_rules helpers."""

from __future__ import annotations

from custom_components.habragerone.status_rules import (
    compare_condition,
    normalize_rule_value,
    read_target_actual,
    resolve_rule_bool,
    resolve_rule_display_value,
    rule_matches,
)


def test_resolve_rule_display_value_returns_none_for_invalid_mapping() -> None:
    assert resolve_rule_display_value(descriptor={}, flat_values={}, default_actual=0) is None
    assert resolve_rule_display_value(descriptor={"mapping": "bad"}, flat_values={}, default_actual=0) is None
    assert (
        resolve_rule_display_value(
            descriptor={"mapping": {"command_rules": "bad"}},
            flat_values={},
            default_actual=0,
        )
        is None
    )


def test_resolve_rule_display_value_skips_invalid_rules_and_none_values() -> None:
    descriptor = {
        "mapping": {
            "command_rules": [
                "bad",
                {"conditions": [], "value": None},
                {
                    "conditions": [{"operation": "equalTo", "expected": 0, "targets": []}],
                    "value": "wn.OFF",
                },
            ]
        }
    }

    display = resolve_rule_display_value(descriptor=descriptor, flat_values={}, default_actual=0)

    assert display == "Off"


def test_resolve_rule_bool_maps_on_off_tokens() -> None:
    descriptor = {
        "mapping": {
            "command_rules": [
                {
                    "value": "enabled",
                    "conditions": [{"operation": "equalTo", "expected": 1, "targets": []}],
                }
            ]
        }
    }

    assert resolve_rule_bool(descriptor=descriptor, flat_values={}, default_actual=1) is True

    descriptor["mapping"]["command_rules"][0]["value"] = "disabled"
    assert resolve_rule_bool(descriptor=descriptor, flat_values={}, default_actual=1) is False

    descriptor["mapping"]["command_rules"][0]["value"] = "maybe"
    assert resolve_rule_bool(descriptor=descriptor, flat_values={}, default_actual=1) is None

    descriptor["mapping"]["command_rules"][0]["value"] = "Włączono"
    assert resolve_rule_bool(descriptor=descriptor, flat_values={}, default_actual=1) is True
    descriptor["mapping"]["command_rules"][0]["value"] = "Wyłączony"
    assert resolve_rule_bool(descriptor=descriptor, flat_values={}, default_actual=1) is False
    descriptor["mapping"]["command_rules"][0]["value"] = "Załączony"
    assert resolve_rule_bool(descriptor=descriptor, flat_values={}, default_actual=1) is True


def test_resolve_rule_bool_returns_none_for_non_string_display() -> None:
    descriptor = {"mapping": {"command_rules": [{"conditions": [], "value": 42}]}}

    assert resolve_rule_bool(descriptor=descriptor, flat_values={}, default_actual=0) is None


def test_rule_matches_defaults_to_all_logic_and_handles_invalid_conditions() -> None:
    assert rule_matches({"conditions": []}, flat_values={}, default_actual=1) is True

    assert rule_matches({"conditions": ["bad"]}, flat_values={}, default_actual=1) is False

    rule = {
        "logic": "any",
        "conditions": [
            {"operation": "equalTo", "expected": 0, "targets": [{"address": "P1.v1"}]},
            {"operation": "equalTo", "expected": 1, "targets": []},
        ],
    }
    assert rule_matches(rule, flat_values={"P1.v1": 5}, default_actual=1) is True


def test_rule_matches_uses_default_actual_when_targets_missing() -> None:
    rule = {"conditions": [{"operation": "equalTo", "expected": 7}]}

    assert rule_matches(rule, flat_values={}, default_actual=7) is True
    assert rule_matches(rule, flat_values={}, default_actual=8) is False


def test_rule_matches_rejects_invalid_target_and_operation() -> None:
    rule = {
        "conditions": [
            {"operation": 123, "expected": 1, "targets": [{"address": "P1.v1"}]},
        ]
    }
    assert rule_matches(rule, flat_values={"P1.v1": 1}, default_actual=0) is False

    rule = {
        "conditions": [
            {"operation": "equalTo", "expected": 1, "targets": ["bad"]},
        ]
    }
    assert rule_matches(rule, flat_values={}, default_actual=1) is False


def test_read_target_actual_handles_address_bit_and_mask() -> None:
    assert read_target_actual({"address": ""}, flat_values={"P1.v1": 1}) is None
    assert read_target_actual({"address": "P1.v1"}, flat_values={"P1.v1": "text"}) == "text"
    assert read_target_actual({"address": "P1.s0", "bit": 2}, flat_values={"P1.s0": 0b100}) == 1
    assert read_target_actual({"address": "P1.s0", "mask": 0x0F}, flat_values={"P1.s0": 0xF0}) == 0
    assert read_target_actual({"address": "P1.s0", "bit": 0}, flat_values={"P1.s0": 64.0}) == 0
    assert read_target_actual({"address": "P1.s0", "bit": 0}, flat_values={"P1.s0": 65.0}) == 1


def test_resolve_entity_bool_prefers_rules_then_input_bit() -> None:
    from custom_components.habragerone.status_rules import resolve_entity_bool

    descriptor = {
        "mapping": {
            "command_rules": [
                {
                    "value": "OFF",
                    "conditions": [{"operation": "equalTo", "expected": 0, "targets": [{"address": "P5.s11", "bit": 1}]}],
                },
                {
                    "value": "ON",
                    "conditions": [{"operation": "equalTo", "expected": 1, "targets": [{"address": "P5.s11", "bit": 1}]}],
                },
            ]
        }
    }
    assert resolve_entity_bool(descriptor=descriptor, flat_values={"P5.s11": 64.0}, default_actual=64.0) is False
    assert resolve_entity_bool(descriptor=descriptor, flat_values={"P5.s11": 66.0}, default_actual=66.0) is True

    # Rules missing targets: refuse multi-bit raw fallback.
    bare = {"mapping": {"command_rules": [{"value": "ON", "conditions": [{"operation": "equalTo", "expected": 1}]}]}}
    assert resolve_entity_bool(descriptor=bare, flat_values={}, default_actual=64) is False

    # Single mapping input bit recovers state when rules cannot match.
    with_input = {
        "mapping": {
            "command_rules": [],
            "inputs": [{"address": "P5.s0", "bit": 0}],
        }
    }
    assert resolve_entity_bool(descriptor=with_input, flat_values={"P5.s0": 64}, default_actual=64) is False
    assert resolve_entity_bool(descriptor=with_input, flat_values={"P5.s0": 65}, default_actual=65) is True


def test_compare_condition_supports_prefixed_and_not_equal_operations() -> None:
    assert compare_condition(operation="xa.notEqualTo", actual=1, expected=2) is True
    assert compare_condition(operation="equalTo", actual=1, expected=1) is True
    assert compare_condition(operation="unknown", actual=1, expected=1) is False


def test_normalize_rule_value_formats_tokens() -> None:
    assert normalize_rule_value("wn.OFF_MANUAL") == "Off"
    assert normalize_rule_value("some_state") == "Some State"
    assert normalize_rule_value(42) == 42
