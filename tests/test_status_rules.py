"""Unit tests for status_rules helpers."""

from __future__ import annotations

import builtins

import pytest

from custom_components.habragerone.status_rules import (
    compare_condition,
    normalize_rule_value,
    read_target_actual,
    resolve_rule_bool,
    resolve_rule_display_value,
    rule_matches,
    status_binary_has_sync_path,
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

    from custom_components.habragerone.status_rules import status_label_to_bool

    # PumpState / diode SPA labels — enum tags and Polish manual parentheticals.
    assert status_label_to_bool("e.ON_MANUAL") is True
    assert status_label_to_bool("e.OFF_MANUAL") is False
    assert status_label_to_bool("ON") is True
    assert status_label_to_bool("OFF") is False
    assert status_label_to_bool("Włączone (ręcznie)") is True
    assert status_label_to_bool("Wyłączony (ręcznie)") is False
    assert status_label_to_bool("DiodeState['ON']") is True
    assert status_label_to_bool("maybe") is None

    # Empty / paren-only / quote-only leftovers after normalization.
    assert status_label_to_bool("   ") is None
    assert status_label_to_bool("()") is None
    assert status_label_to_bool("'") is None

    # Prefix fallback when the token is not an exact on/off set member.
    assert status_label_to_bool("ON_STANDBY") is True
    assert status_label_to_bool("OFF_STANDBY") is False


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
    # Bools are not bitmasks — leave the raw value untouched.
    assert read_target_actual({"address": "P1.s0", "bit": 0}, flat_values={"P1.s0": True}) is True
    assert read_target_actual({"address": "P1.s0", "bit": 0}, flat_values={"P1.s0": 1.5}) == 1.5


def test_status_binary_has_sync_path() -> None:
    from custom_components.habragerone.status_rules import (
        status_rule_selector_addresses,
        try_resolve_status_binary_sync,
    )

    with_rules = {
        "mapping": {
            "command_rules": [
                {"value": "On", "conditions": [{"operation": "equalTo", "expected": 1, "targets": []}]},
            ]
        }
    }
    assert status_binary_has_sync_path(descriptor=with_rules, flat_values={}, default_actual=1) is True
    assert try_resolve_status_binary_sync(descriptor=with_rules, flat_values={}, default_actual=1) is True

    with_bits = {"mapping": {"inputs": [{"address": "P5.s11", "bit": 1}]}}
    assert status_binary_has_sync_path(descriptor=with_bits, flat_values={"P5.s11": 64.0}, default_actual=64.0) is True
    # Bit 1 of 64 is clear → off; bit 1 of 2 is set → on.
    assert try_resolve_status_binary_sync(descriptor=with_bits, flat_values={"P5.s11": 64.0}, default_actual=64.0) is False
    assert try_resolve_status_binary_sync(descriptor=with_bits, flat_values={"P5.s11": 2.0}, default_actual=2.0) is True

    bare = {"mapping": {"command_rules": []}}
    assert status_binary_has_sync_path(descriptor=bare, flat_values={}, default_actual=64.0) is False

    assert status_binary_has_sync_path(descriptor={"mapping": "bad"}, flat_values={}, default_actual=1) is False
    assert (
        status_binary_has_sync_path(
            descriptor={"mapping": {"inputs": "bad"}},
            flat_values={},
            default_actual=1,
        )
        is False
    )

    # Rule list that yields a non-boolean / undefined value keeps resolver fallback.
    numeric_then = {
        "mapping": {
            "paths": {
                "value": [
                    {
                        "if": [{"expected": 1, "operation": "equalTo", "value": [{"group": "P1", "number": 0, "use": "v"}]}],
                        "then": 42,
                    }
                ]
            },
            "command_rules": [],
            "inputs": [],
        }
    }
    assert status_binary_has_sync_path(descriptor=numeric_then, flat_values={"P1.v0": 1}, default_actual=1) is False
    assert try_resolve_status_binary_sync(descriptor=numeric_then, flat_values={"P1.v0": 1}, default_actual=1) is None

    # Elseif selectors are refresh dependencies even when not the primary pool address.
    assert status_rule_selector_addresses(numeric_then["mapping"]) == {"P1.v0"}
    assert status_rule_selector_addresses(
        {
            "raw": {
                "any": [
                    {
                        "elseif": [
                            {
                                "expected": 1,
                                "operation": "equalTo",
                                "value": [{"group": "P2", "number": 0, "use": "s"}],
                            }
                        ],
                        "then": "ON",
                    }
                ]
            }
        }
    ) == {"P2.s0"}
    from custom_components.habragerone.status_rules import (
        _addresses_from_status_rules,
        status_value_rules_fingerprint,
    )

    assert status_value_rules_fingerprint(None) is None
    assert status_value_rules_fingerprint({"paths": {"value": [{"else": "OFF"}]}}) == repr([{"else": "OFF"}])
    # Equivalent trees fingerprint identically regardless of dict key insertion order.
    assert status_value_rules_fingerprint(
        {"paths": {"value": [{"then": "ON", "if": [{"expected": 1, "operation": "equalTo", "value": []}]}]}}
    ) == status_value_rules_fingerprint(
        {"paths": {"value": [{"if": [{"operation": "equalTo", "value": [], "expected": 1}], "then": "ON"}]}}
    )
    assert status_rule_selector_addresses(None) == set()
    assert status_rule_selector_addresses({"paths": {}}) == set()

    # Skip non-mapping / malformed selectors while still collecting valid ones.
    assert status_rule_selector_addresses(
        {
            "paths": {
                "value": [
                    "skip-me",
                    {
                        "if": [
                            "bad-cond",
                            {"expected": 1, "operation": "equalTo", "value": "not-list"},
                            {
                                "expected": 1,
                                "operation": "equalTo",
                                "value": [
                                    "bad-sel",
                                    {"group": "P9", "number": "x", "use": "s"},
                                    {"group": "P9", "number": 1, "use": ""},
                                    {"group": "P9", "number": 2, "use": "s"},
                                ],
                            },
                        ],
                        "then": "ON",
                    },
                ]
            }
        }
    ) == {"P9.s2"}
    # Defensive continues for callers that pass unfiltered rule lists.
    assert _addresses_from_status_rules(
        [
            "skip-me",
            {
                "if": [
                    "bad-cond",
                    {"expected": 1, "operation": "equalTo", "value": "not-list"},
                    {
                        "expected": 1,
                        "operation": "equalTo",
                        "value": [
                            "bad-sel",
                            {"group": " ", "number": 1, "use": "s"},
                            {"group": "P8", "number": 3, "use": "v"},
                        ],
                    },
                ],
                "then": "ON",
            },
        ]
    ) == {"P8.v3"}

    # Matched then:null / unmatched SPA rules must not fall through to raw bit coerce.
    spa_then_null = {
        "mapping": {
            "paths": {
                "value": [
                    {
                        "if": [
                            {
                                "expected": None,
                                "operation": "equalTo",
                                "value": [{"group": "P31", "number": 50, "use": "s"}],
                            }
                        ],
                        "then": None,
                    },
                    {"else": "OFF"},
                ]
            },
            "inputs": [{"address": "P31.s12", "bit": 0, "mask": 1}],
        }
    }
    assert (
        try_resolve_status_binary_sync(
            descriptor=spa_then_null,
            flat_values={"P31.s12": 1},
            default_actual=1,
        )
        is None
    )
    assert status_binary_has_sync_path(descriptor=spa_then_null, flat_values={"P31.s12": 1}, default_actual=1) is False

    # Preferred bit/mask with a non-numeric actual falls back to coerce_status_bool.
    bit_bool = {"mapping": {"inputs": [{"address": "P5.s11", "bit": 1}]}}
    assert try_resolve_status_binary_sync(descriptor=bit_bool, flat_values={"P5.s11": True}, default_actual=1) is True
    assert (
        try_resolve_status_binary_sync(
            descriptor={"mapping": {"inputs": [{"address": "P5.s11"}]}},
            flat_values={"P5.s11": 1},
            default_actual=1,
        )
        is None
    )


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

    # Non-mapping ``mapping`` skips the inputs path entirely.
    assert resolve_entity_bool(descriptor={"mapping": "bad"}, flat_values={}, default_actual=1) is True

    # Single mapping input bit recovers state when rules cannot match.
    with_input = {
        "mapping": {
            "command_rules": [],
            "inputs": [{"address": "P5.s0", "bit": 0}],
        }
    }
    assert resolve_entity_bool(descriptor=with_input, flat_values={"P5.s0": 64}, default_actual=64) is False
    assert resolve_entity_bool(descriptor=with_input, flat_values={"P5.s0": 65}, default_actual=65) is True

    # Inputs without bit/mask → raw coercion.
    no_bits = {"mapping": {"command_rules": [], "inputs": [{"address": "P5.s0"}]}}
    assert resolve_entity_bool(descriptor=no_bits, flat_values={"P5.s0": 1}, default_actual=1) is True

    # Dual-bit PumpState inputs (bit 1 ON/OFF + bit 3 manual): prefer lowest bit.
    pump_bits = {
        "mapping": {
            "command_rules": [],
            "inputs": [{"address": "P5.s11", "bit": 1}, {"address": "P5.s11", "bit": 3}],
        }
    }
    assert resolve_entity_bool(descriptor=pump_bits, flat_values={"P5.s11": 64.0}, default_actual=64.0) is False
    assert resolve_entity_bool(descriptor=pump_bits, flat_values={"P5.s11": 66.0}, default_actual=66.0) is True
    assert resolve_entity_bool(descriptor=pump_bits, flat_values={"P5.s11": 8.0}, default_actual=8.0) is False

    # Different addresses / mask-only multi-inputs → refuse and coerce raw.
    split_addr = {
        "mapping": {
            "command_rules": [],
            "inputs": [{"address": "P5.s11", "bit": 1}, {"address": "P5.s12", "bit": 1}],
        }
    }
    assert resolve_entity_bool(descriptor=split_addr, flat_values={"P5.s11": 2}, default_actual=64) is False
    mask_only = {
        "mapping": {
            "command_rules": [],
            "inputs": [{"address": "P5.s11", "mask": 2}, {"address": "P5.s11", "mask": 8}],
        }
    }
    assert resolve_entity_bool(descriptor=mask_only, flat_values={"P5.s11": 2}, default_actual=64) is False

    # Bit input present but actual is non-numeric → raw fallback.
    weird = {"mapping": {"command_rules": [], "inputs": [{"address": "P5.s0", "bit": 0}]}}
    assert resolve_entity_bool(descriptor=weird, flat_values={"P5.s0": "on"}, default_actual="on") is True


def test_resolve_entity_bool_evaluates_paths_value_mask_rules() -> None:
    """SPA pump-diode paths.value if/elseif/else+mask (prefix-agnostic)."""
    from custom_components.habragerone.status_rules import (
        mapping_has_status_value_rules,
        resolve_entity_bool,
        resolve_rule_bool,
        resolve_rule_display_value,
        status_binary_has_sync_path,
    )

    rules = [
        {
            "if": [{"expected": None, "operation": "equalTo", "value": [{"group": "P31", "number": 50, "use": "s"}]}],
            "then": None,
        },
        {
            "elseif": [
                {
                    "expected": 0,
                    "operation": "notEqualTo",
                    "value": [{"group": "P31", "number": 50, "use": "s", "mask": 0x0A}],
                }
            ],
            "then": "ON",
        },
        {"else": "OFF"},
    ]
    descriptor = {"mapping": {"paths": {"value": rules}, "command_rules": [], "inputs": []}}
    assert mapping_has_status_value_rules(descriptor["mapping"]) is True
    assert status_binary_has_sync_path(descriptor=descriptor, flat_values={"P31.s50": 0x0A}, default_actual=0x0A) is True
    assert resolve_entity_bool(descriptor=descriptor, flat_values={"P31.s50": 0x0A}, default_actual=0x0A) is True
    assert resolve_entity_bool(descriptor=descriptor, flat_values={"P31.s50": 0x01}, default_actual=0x01) is False
    assert status_binary_has_sync_path(descriptor=descriptor, flat_values={"P31.s50": 0x0A}, default_actual=0x0A) is True
    # Missing register: equalTo null → then null (undefined), not else OFF.
    assert resolve_rule_display_value(descriptor=descriptor, flat_values={}, default_actual=0) is None
    assert resolve_rule_bool(descriptor=descriptor, flat_values={}, default_actual=0) is None
    assert status_binary_has_sync_path(descriptor=descriptor, flat_values={}, default_actual=0) is False

    # Library evaluator also handles ClauseOperation / greaterThan.
    from custom_components.habragerone.status_rules import evaluate_status_value_rules

    gt = evaluate_status_value_rules(
        mapping={
            "paths": {
                "value": [
                    {
                        "if": [
                            {
                                "expected": 5,
                                "operation": "ClauseOperation['greaterThan']",
                                "value": [{"group": "P2", "number": 0, "use": "v"}],
                            }
                        ],
                        "then": "ON",
                        "else": "OFF",
                    }
                ]
            }
        },
        flat_values={"P2.v0": 9},
    )
    assert gt == "ON"

    # Inline else on the same rule as a nonmatching if.
    inline = {
        "mapping": {
            "paths": {
                "value": [
                    {
                        "if": [
                            {
                                "expected": 9,
                                "operation": "equalTo",
                                "value": [{"group": "P31", "number": 50, "use": "s"}],
                            }
                        ],
                        "then": "ON",
                        "else": "OFF",
                    }
                ]
            },
            "command_rules": [],
            "inputs": [],
        }
    }
    assert resolve_entity_bool(descriptor=inline, flat_values={"P31.s50": 0x01}, default_actual=0x01) is False

    # raw.any / dict then / void 0 expected / junk selectors.
    raw_any = {
        "mapping": {
            "raw": {
                "any": [
                    "skip",
                    {
                        "if": [
                            {
                                "expected": "void 0",
                                "operation": "t.equalTo",
                                "value": [
                                    {"group": "P9", "number": 1, "use": "v"},
                                    {"bad": True},
                                ],
                            }
                        ],
                        "then": {"value": "e.ON"},
                    },
                    {"else": {"value": "e.OFF"}},
                ]
            },
            "command_rules": [],
            "inputs": [],
        }
    }
    assert mapping_has_status_value_rules(raw_any["mapping"]) is True
    assert resolve_rule_display_value(descriptor=raw_any, flat_values={}, default_actual=0) == "On"

    assert mapping_has_status_value_rules(None) is False
    assert mapping_has_status_value_rules({"paths": {"value": [{"no": "rules"}]}}) is False

    from custom_components.habragerone.status_rules import mapping_has_status_label_rules

    assert mapping_has_status_label_rules({"paths": {"value": [{"else": "OFF"}]}}) is True
    assert mapping_has_status_label_rules({"paths": {"value": ["skip", {"else": {"value": 1}}]}}) is True
    assert mapping_has_status_label_rules(None) is False
    assert (
        mapping_has_status_label_rules(
            {
                "paths": {
                    "value": [
                        {"if": [{"expected": None, "operation": "equalTo", "value": []}], "then": None},
                        {"else": [{"group": "P12", "number": 0, "use": "a"}]},
                    ]
                }
            }
        )
        is False
    )

    # Branch coverage: junk rules, empty/invalid selectors, missing≠null, Mapping else.
    from custom_components.habragerone import status_rules as status_rules_mod

    junk_rules = [
        "skip",
        {
            "if": [{"operation": 1, "expected": 1, "value": [{"group": "P1", "number": 0, "use": "v"}]}],
            "then": "Z",
        },
        {"if": [{"operation": "equalTo", "expected": 1, "value": []}], "then": "A"},
        {"if": [{"operation": "equalTo", "expected": 1, "value": [None]}], "then": "B"},
        {
            "if": [{"operation": "equalTo", "expected": 1, "value": [{"group": 1, "number": 0, "use": "v"}]}],
            "then": "C",
        },
        {
            "if": [
                {
                    "operation": "notEqualTo",
                    "expected": None,
                    "value": [{"group": "P99", "number": 0, "use": "v"}],
                }
            ],
            "then": "D",
        },
        {"else": {"value": "OFF"}},
    ]
    assert status_rules_mod._eval_spa_value_rules(junk_rules, flat_values={}) == "OFF"


def test_status_value_rules_local_fallback_when_library_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover the offline equalTo/notEqualTo evaluator used without ComputedValueEvaluator."""
    from custom_components.habragerone import status_rules as status_rules_mod
    from custom_components.habragerone.status_rules import evaluate_status_value_rules

    monkeypatch.setattr(status_rules_mod, "_library_evaluator_available", lambda: False)
    assert status_rules_mod._evaluate_rules_via_library([{"else": "OFF"}], flat_values={}) is None

    assert (
        evaluate_status_value_rules(
            mapping={
                "paths": {
                    "value": [
                        {
                            "if": [
                                {
                                    "expected": "void 0",
                                    "operation": "t.equalTo",
                                    "value": [{"group": "P8", "number": 1, "use": "s"}],
                                }
                            ],
                            "then": {"value": "e.ON"},
                        }
                    ]
                }
            },
            flat_values={},
        )
        == "e.ON"
    )
    assert (
        evaluate_status_value_rules(
            mapping={
                "paths": {
                    "value": [
                        {
                            "if": [
                                {
                                    "expected": 2,
                                    "operation": "equalTo",
                                    "value": [{"group": "P8", "number": 1, "use": "s", "mask": 0x0F}],
                                }
                            ],
                            "then": "ON",
                            "else": "OFF",
                        }
                    ]
                }
            },
            flat_values={"P8.s1": 0x12},
        )
        == "ON"
    )
    assert (
        evaluate_status_value_rules(
            mapping={
                "paths": {
                    "value": [
                        {
                            "if": [
                                {
                                    "expected": None,
                                    "operation": "notEqualTo",
                                    "value": [{"group": "P7", "number": 0, "use": "v"}],
                                }
                            ],
                            "then": "ON",
                        },
                        {"else": "OFF"},
                    ]
                }
            },
            flat_values={},
        )
        == "OFF"
    )


def test_library_evaluator_available_handles_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing pybragerone import reports the library evaluator as unavailable."""
    from custom_components.habragerone import status_rules as status_rules_mod

    real_import = builtins.__import__

    def _boom(name: str, globals: object = None, locals: object = None, fromlist: object = (), level: int = 0) -> object:
        if name.startswith("pybragerone"):
            raise ImportError("forced")
        return real_import(name, globals, locals, fromlist, level)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", _boom)
    assert status_rules_mod._library_evaluator_available() is False


def test_library_and_local_evaluators_skip_non_matching_selectors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover for-loop continues: bad flat keys and multi-selector equalTo miss→hit."""
    from custom_components.habragerone import status_rules as status_rules_mod
    from custom_components.habragerone.status_rules import evaluate_status_value_rules

    # Non-string / empty keys are ignored when seeding ParamStore for the library path.
    assert (
        status_rules_mod._evaluate_rules_via_library(
            [{"else": "OFF"}],
            flat_values={"": 1, 12: 2, "P1.v0": 0},
        )
        == "OFF"
    )

    # First selector misses, second hits (local fallback for-loop continue).
    monkeypatch.setattr(status_rules_mod, "_library_evaluator_available", lambda: False)
    assert (
        evaluate_status_value_rules(
            mapping={
                "paths": {
                    "value": [
                        {
                            "if": [
                                {
                                    "expected": 1,
                                    "operation": "equalTo",
                                    "value": [
                                        {"group": "P1", "number": 0, "use": "v"},
                                        {"group": "P1", "number": 1, "use": "v"},
                                    ],
                                }
                            ],
                            "then": "ON",
                        }
                    ]
                }
            },
            flat_values={"P1.v0": 0, "P1.v1": 1},
        )
        == "ON"
    )


def test_compare_condition_supports_prefixed_and_not_equal_operations() -> None:
    assert compare_condition(operation="xa.notEqualTo", actual=1, expected=2) is True
    assert compare_condition(operation="equalTo", actual=1, expected=1) is True
    assert compare_condition(operation="unknown", actual=1, expected=1) is False


def test_normalize_rule_value_formats_tokens() -> None:
    assert normalize_rule_value("wn.OFF_MANUAL") == "Off"
    assert normalize_rule_value("some_state") == "Some State"
    assert normalize_rule_value(42) == 42
