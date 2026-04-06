"""Tests for rule-based status value mapping."""

from __future__ import annotations

from custom_components.habragerone.status_rules import resolve_rule_display_value


def test_resolve_rule_display_value_for_boiler_status_tokens() -> None:
    descriptor = {
        "mapping": {
            "command_rules": [
                {
                    "value": "WORK",
                    "conditions": [{"operation": "equalTo", "expected": 768, "targets": [{"address": "P5.s5"}]}],
                }
            ]
        }
    }

    display = resolve_rule_display_value(descriptor=descriptor, flat_values={"P5.s5": 768}, default_actual=65)

    assert display == "Work"


def test_resolve_rule_display_value_for_prefixed_operation_and_bit_target() -> None:
    descriptor = {
        "mapping": {
            "command_rules": [
                {
                    "value": "wn.ON",
                    "conditions": [{"operation": "xa.equalTo", "expected": 1, "targets": [{"address": "P5.s19", "bit": 1}]}],
                }
            ]
        }
    }

    display = resolve_rule_display_value(descriptor=descriptor, flat_values={"P5.s19": 2}, default_actual=0)

    assert display == "On"


def test_resolve_rule_display_value_honors_any_logic() -> None:
    descriptor = {
        "mapping": {
            "command_rules": [
                {
                    "logic": "any",
                    "value": "STOP",
                    "conditions": [
                        {"operation": "equalTo", "expected": 1, "targets": [{"address": "P5.s4", "bit": 5}]},
                        {"operation": "equalTo", "expected": 0, "targets": [{"address": "P6.v13"}]},
                    ],
                }
            ]
        }
    }

    display = resolve_rule_display_value(descriptor=descriptor, flat_values={"P5.s4": 32, "P6.v13": 2}, default_actual=65)

    assert display == "Stop"
