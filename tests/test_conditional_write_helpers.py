"""Coverage for conditional raw.any write / binary helper branches."""

from __future__ import annotations

import pytest

from custom_components.habragerone.bootstrap import _mapping_has_parameter_write
from custom_components.habragerone.entity_common import (
    _any_rules_bind_register_values,
    _try_active_any_branch_value,
    descriptor_current_raw_value,
)
from custom_components.habragerone.runtime import (
    _parameter_address_from_active_any_branch_command,
    _parameter_address_from_rule_payload,
)
from custom_components.habragerone.status_rules import (
    _addresses_from_rule_payload,
    _spa_conditions_match_for_binary,
    _status_payload_to_bool,
    evaluate_status_binary_from_rules,
    first_selector_address_value,
    select_raw_any_branch,
)
from tests.helpers.fakes import FakeStore


def test_parameter_address_from_rule_payload_variants() -> None:
    assert _parameter_address_from_rule_payload({"group": "P32", "number": 221, "use": "v"}) == ("P32", "v", 221)
    assert _parameter_address_from_rule_payload([{"address": "P32.v7"}]) == ("P32", "v", 7)
    assert _parameter_address_from_rule_payload([{"address": "P32.vX"}, "skip"]) is None
    assert _parameter_address_from_rule_payload([{"address": ".v7"}]) is None
    assert _parameter_address_from_rule_payload([{"address": "P32."}]) is None
    assert _parameter_address_from_rule_payload([{"group": "P32", "number": 1, "use": ""}]) is None
    assert _parameter_address_from_rule_payload("bad") is None
    assert _parameter_address_from_active_any_branch_command({"raw": "nope"}, flat_values={}) is None
    assert _parameter_address_from_active_any_branch_command(
        {
            "raw": {
                "any": [
                    {
                        "else": {
                            "command": [{"group": "P32", "number": 221, "use": "v"}],
                        }
                    }
                ]
            }
        },
        flat_values={},
    ) == ("P32", "v", 221)


def test_any_branch_helpers_edge_cases() -> None:
    assert _any_rules_bind_register_values(["skip", {"then": "ON"}]) is False
    assert _any_rules_bind_register_values([{"else": {"value": [{"number": 0}]}}]) is False
    assert _any_rules_bind_register_values([{"else": {"value": [{"group": "P1", "number": 0, "use": "v"}]}}]) is True
    store = FakeStore(flat_values={"P1.v0": 3})
    handled, value = _try_active_any_branch_value(store, {"raw": {"any": [{"else": "ON"}]}})
    assert handled is False
    assert value is None
    handled, value = _try_active_any_branch_value(store, {"raw": None})
    assert handled is False
    assert select_raw_any_branch("nope", flat_values={}) is None
    assert select_raw_any_branch(
        ["skip", {"else": {"value": [{"group": "P1", "number": 0, "use": "v"}]}}],
        flat_values={"P1.v0": 3},
    ) == {"value": [{"group": "P1", "number": 0, "use": "v"}]}
    # Second else is ignored once the first else payload was captured.
    assert select_raw_any_branch(
        [
            {"else": {"value": [{"group": "P1", "number": 0, "use": "v"}]}},
            {"else": {"value": [{"group": "P9", "number": 9, "use": "v"}]}},
        ],
        flat_values={},
    ) == {"value": [{"group": "P1", "number": 0, "use": "v"}]}
    assert first_selector_address_value(None, flat_values={}) is None
    assert first_selector_address_value({"value": "not-a-list"}, flat_values={}) is None
    assert (
        first_selector_address_value({"value": ["skip", {"group": "P1", "number": 0, "use": "v"}]}, flat_values={"P1.v0": 3}) == 3
    )
    assert _addresses_from_rule_payload([{"group": "P1", "number": 0, "use": "v"}]) == {"P1.v0"}
    assert _addresses_from_rule_payload(["skip", {"group": "P1", "number": 0, "use": "v"}]) == {"P1.v0"}
    assert _addresses_from_rule_payload({"group": "P1"}) == set()
    assert _addresses_from_rule_payload({"value": [{"group": "P2", "number": 1, "use": "s"}]}) == {"P2.s1"}


def test_binary_condition_helpers_cover_reject_paths() -> None:
    assert _spa_conditions_match_for_binary(["bad"], flat_values={}) is False
    assert _spa_conditions_match_for_binary([{"operation": 1}], flat_values={}) is None
    assert (
        _spa_conditions_match_for_binary(
            [{"operation": "t.equalTo", "expected": 1, "value": [{"group": "P1", "number": 0, "use": "v"}]}],
            flat_values={"P1.v0": 1},
        )
        is True
    )
    assert evaluate_status_binary_from_rules(mapping={"paths": {"value": []}}, flat_values={}) is None
    assert (
        evaluate_status_binary_from_rules(
            mapping={
                "paths": {
                    "value": [
                        "skip",
                        {
                            "if": [
                                {
                                    "expected": 1,
                                    "operation": "equalTo",
                                    "value": [{"group": "P1", "number": 0, "use": "v"}],
                                }
                            ],
                            "then": None,
                        },
                    ]
                }
            },
            flat_values={"P1.v0": 1},
        )
        is None
    )
    assert first_selector_address_value({"value": [{"group": "P1", "number": "bad", "use": "v"}]}, flat_values={}) is None
    assert (
        _mapping_has_parameter_write({"command_rules": ["skip", {"value": [{"group": "P1", "number": 0, "use": "v"}]}]}) is True
    )
    # command_rules command list (no value) still marks a write target.
    assert _mapping_has_parameter_write({"command_rules": [{"command": [{"group": "P1", "number": 0, "use": "v"}]}]}) is True
    # Mapping command_rules without value/command selectors must not short-circuit as writable.
    assert _mapping_has_parameter_write({"command_rules": [{"kind": "else", "value": "ON"}]}) is False
    assert (
        _mapping_has_parameter_write(
            {"raw": {"any": ["skip", {"else": {"command": [{"group": "P1", "number": 0, "use": "v"}]}}]}}
        )
        is True
    )
    # raw Mapping with non-list any must fall through as non-writable.
    assert _mapping_has_parameter_write({"raw": {"any": {"else": {}}}}) is False
    assert (
        evaluate_status_binary_from_rules(
            mapping={"paths": {"value": [{"else": {"value": "ON"}}]}},
            flat_values={},
        )
        is True
    )
    assert _status_payload_to_bool({"value": "OFF"}) is False
    assert _status_payload_to_bool({"group": "P1", "number": 0, "use": "v"}) is None


def test_descriptor_current_raw_value_skips_status_string_any_branches() -> None:
    store = FakeStore(flat_values={"P5.s0": 1, "P5.v0": 9})
    descriptor = {
        "pool": "P5",
        "chan": "v",
        "idx": 0,
        "mapping": {
            "raw": {
                "any": [
                    {
                        "if": [{"expected": 1, "operation": "equalTo", "value": [{"group": "P5", "number": 0, "use": "s"}]}],
                        "then": "ON",
                    }
                ]
            }
        },
    }
    assert descriptor_current_raw_value(store, descriptor) == 9


@pytest.mark.asyncio
async def test_async_write_uses_rule_command_list_and_address_string() -> None:
    from tests.helpers.descriptors import writable_parameter_descriptor
    from tests.helpers.fakes import make_runtime

    runtime, api, _gateway, store = make_runtime()
    store.upsert("P31.s13", 4)
    descriptor = writable_parameter_descriptor(pool="P32", chan="v", idx=0, raw_min=0, raw_max=400)
    descriptor["mapping"]["command_rules"] = []
    descriptor["mapping"]["raw"] = {
        "any": [
            {
                "else": {
                    "command": [{"address": "P32.v221"}],
                    "value": [{"address": "P32.v221"}],
                }
            }
        ]
    }
    await runtime.async_write(descriptor=descriptor, input_display_value=19)
    assert api.calls[-1]["parameter"] == "v221"

    # Direct command list on the active rule (no value selectors).
    descriptor2 = writable_parameter_descriptor(pool="P32", chan="v", idx=0, raw_min=0, raw_max=400)
    descriptor2["mapping"]["command_rules"] = [
        {"kind": "else", "conditions": [], "command": [{"group": "P32", "number": 42, "use": "v"}]}
    ]
    await runtime.async_write(descriptor=descriptor2, input_display_value=11)
    assert api.calls[-1]["parameter"] == "v42"

    # Active command family with n/x overrides descriptor min/max at write time.
    store.upsert("P32.v55", 10)
    store.upsert("P32.n55", 5)
    store.upsert("P32.x55", 50)
    descriptor3 = writable_parameter_descriptor(pool="P32", chan="v", idx=0, raw_min=0, raw_max=400)
    descriptor3["mapping"]["command_rules"] = [
        {"kind": "else", "conditions": [], "command": [{"group": "P32", "number": 55, "use": "v"}]}
    ]
    await runtime.async_write(descriptor=descriptor3, input_display_value=12)
    assert api.calls[-1]["parameter"] == "v55"

    # Family present without numeric n/x keeps descriptor bounds (false branches).
    store.upsert("P32.v56", 10)
    store.upsert("P32.n56", "nope")
    store.upsert("P32.x56", "nope")
    descriptor4 = writable_parameter_descriptor(pool="P32", chan="v", idx=0, raw_min=0, raw_max=400)
    descriptor4["mapping"]["command_rules"] = [
        {"kind": "else", "conditions": [], "command": [{"group": "P32", "number": 56, "use": "v"}]}
    ]
    await runtime.async_write(descriptor=descriptor4, input_display_value=13)
    assert api.calls[-1]["parameter"] == "v56"


def test_address_string_selectors_bind_and_refresh() -> None:
    from custom_components.habragerone.entity_common import descriptor_refresh_keys

    store = FakeStore(flat_values={"P32.v0": 21, "P32.v221": 19, "P31.s13": 4})
    descriptor = {
        "pool": "P32",
        "chan": "v",
        "idx": 0,
        "mapping": {
            "raw": {
                "any": [
                    {
                        "else": {
                            "command": [{"address": "P32.v221"}],
                            "value": [{"address": "P32.v221"}],
                        }
                    }
                ]
            }
        },
    }
    assert descriptor_current_raw_value(store, descriptor) == 19
    keys = descriptor_refresh_keys(descriptor)
    assert "P32.v221" in keys


def test_clause_operation_equal_to_selects_then_branch() -> None:
    assert select_raw_any_branch(
        [
            {
                "if": [
                    {
                        "expected": 0,
                        "operation": "ClauseOperation['equalTo']",
                        "value": [{"bit": 2, "group": "P31", "number": 13, "use": "s"}],
                    }
                ],
                "then": {"command": [{"group": "P32", "number": 0, "use": "v"}]},
            },
            {"else": {"command": [{"group": "P32", "number": 221, "use": "v"}]}},
        ],
        flat_values={"P31.s13": 0},
    ) == {"command": [{"group": "P32", "number": 0, "use": "v"}]}


def test_status_binary_unwraps_value_null_payload() -> None:
    assert (
        evaluate_status_binary_from_rules(
            mapping={
                "paths": {
                    "value": [
                        {
                            "if": [
                                {
                                    "expected": 1,
                                    "operation": "equalTo",
                                    "value": [{"group": "P1", "number": 0, "use": "v"}],
                                }
                            ],
                            "then": {"value": None},
                        },
                        {"else": "ON"},
                    ]
                }
            },
            flat_values={"P1.v0": 1},
        )
        is None
    )


@pytest.mark.asyncio
async def test_async_write_rejects_unsupported_raw_any_predicate() -> None:
    from homeassistant.exceptions import HomeAssistantError

    from tests.helpers.descriptors import writable_parameter_descriptor
    from tests.helpers.fakes import make_runtime

    runtime, _api, _gateway, store = make_runtime()
    store.upsert("P31.s13", 0)
    descriptor = writable_parameter_descriptor(pool="P32", chan="v", idx=0, raw_min=0, raw_max=400)
    descriptor["mapping"]["command_rules"] = []
    descriptor["mapping"]["raw"] = {
        "any": [
            {
                "if": [
                    {
                        "expected": 1,
                        "operation": "ClauseOperation['matches']",
                        "value": [{"group": "P31", "number": 13, "use": "s"}],
                    }
                ],
                "then": {"command": [{"group": "P32", "number": 0, "use": "v"}]},
            },
            {"else": {"command": [{"group": "P32", "number": 221, "use": "v"}]}},
        ]
    }
    with pytest.raises(HomeAssistantError, match=r"Unsupported raw\.any"):
        await runtime.async_write(descriptor=descriptor, input_display_value=19)

    # Supported predicates but non-Mapping then → no command address.
    from custom_components.habragerone.runtime import _parameter_address_from_active_any_branch_command

    assert (
        _parameter_address_from_active_any_branch_command(
            {
                "raw": {
                    "any": [
                        {
                            "if": [
                                {
                                    "expected": 1,
                                    "operation": "equalTo",
                                    "value": [{"group": "P1", "number": 0, "use": "v"}],
                                }
                            ],
                            "then": "ON",
                        },
                        {"else": {"command": [{"group": "P32", "number": 221, "use": "v"}]}},
                    ]
                }
            },
            flat_values={"P1.v0": 1},
        )
        is None
    )


def test_bootstrap_any_branch_address_and_unit_helpers() -> None:
    from custom_components.habragerone.bootstrap import (
        _any_branch_active_value_address,
        _apply_branch_register_bounds,
        _has_named_command_rule,
        _has_runtime_raw_value,
        _is_command_like_symbol,
        _is_value_channel_selector,
        _unit_code_for_address,
    )

    assert _has_runtime_raw_value(payload={"pool": "P1"}, mapping=None, flat_values={}) is False
    assert _is_command_like_symbol("") is False
    assert _has_named_command_rule(None) is False
    assert _has_named_command_rule({"command_rules": "bad"}) is False
    assert _has_named_command_rule({"command_rules": ["skip"]}) is False

    assert _any_branch_active_value_address(mapping=None, flat_values={}) is None
    assert _any_branch_active_value_address(mapping={"raw": "bad"}, flat_values={}) is None
    assert (
        _any_branch_active_value_address(
            mapping={"raw": {"any": [{"else": "ON"}]}},
            flat_values={},
        )
        is None
    )
    assert (
        _any_branch_active_value_address(
            mapping={"raw": {"any": [{"else": {"value": "nope"}}]}},
            flat_values={},
        )
        is None
    )
    assert (
        _any_branch_active_value_address(
            mapping={"raw": {"any": [{"else": {"value": ["skip", {"address": "P32.v221"}]}}]}},
            flat_values={},
        )
        == "P32.v221"
    )
    assert (
        _any_branch_active_value_address(
            mapping={"raw": {"any": [{"else": {"value": ["skip", {"foo": 1}]}}]}},
            flat_values={},
        )
        is None
    )
    assert _unit_code_for_address(address="bad", flat_values={}) is None
    assert _unit_code_for_address(address="P32.", flat_values={}) is None
    assert _unit_code_for_address(address="P32.vX", flat_values={}) is None
    assert _unit_code_for_address(address="P32.v221", flat_values={"P32.u221": ""}) is None
    assert _unit_code_for_address(address="P32.v221", flat_values={"P32.u221": 12}) == 12
    assert _is_value_channel_selector({"address": "P32.v221"}) is True
    assert _is_value_channel_selector({"address": "P32.vX"}) is False
    assert _is_value_channel_selector({"address": "P32.s1"}) is False
    descriptor: dict[str, object] = {"min": 0, "max": 400}
    _apply_branch_register_bounds(descriptor, active_addr=None, flat_values={})
    assert descriptor == {"min": 0, "max": 400}
    _apply_branch_register_bounds(descriptor, active_addr="P32.vX", flat_values={"P32.n0": 1})
    assert descriptor == {"min": 0, "max": 400}
    _apply_branch_register_bounds(descriptor, active_addr="P32.", flat_values={})
    assert descriptor == {"min": 0, "max": 400}
    _apply_branch_register_bounds(
        descriptor,
        active_addr="P32.v221",
        flat_values={"P32.n221": 150, "P32.x221": 250},
    )
    assert descriptor == {"min": 150, "max": 250}
    # Only one bound present / non-numeric companion.
    only_min: dict[str, object] = {"min": 0, "max": 400}
    _apply_branch_register_bounds(only_min, active_addr="P32.v7", flat_values={"P32.n7": 11, "P32.x7": "nope"})
    assert only_min == {"min": 11, "max": 400}
    only_max: dict[str, object] = {"min": 0, "max": 400}
    _apply_branch_register_bounds(only_max, active_addr="P32.v8", flat_values={"P32.n8": "nope", "P32.x8": 22})
    assert only_max == {"min": 0, "max": 22}


def test_descriptor_active_raw_limits_edge_cases() -> None:
    from custom_components.habragerone.entity_common import descriptor_active_raw_limits

    store = FakeStore(flat_values={"P32.v221": 19, "P32.n221": 15, "P32.x221": 25})
    assert descriptor_active_raw_limits(store, {"min": 1, "max": 2}) == (1, 2)
    assert descriptor_active_raw_limits(store, {"min": 1, "max": 2, "mapping": {"raw": "bad"}}) == (1, 2)
    assert descriptor_active_raw_limits(
        store,
        {"min": 1, "max": 2, "mapping": {"raw": {"any": [{"else": "ON"}]}}},
    ) == (1, 2)
    # Matching if with non-Mapping then while else still binds selectors → no branch.
    assert descriptor_active_raw_limits(
        FakeStore(flat_values={"P1.v0": 1}),
        {
            "min": 1,
            "max": 2,
            "mapping": {
                "raw": {
                    "any": [
                        {
                            "if": [
                                {
                                    "expected": 1,
                                    "operation": "equalTo",
                                    "value": [{"group": "P1", "number": 0, "use": "v"}],
                                }
                            ],
                            "then": "ON",
                        },
                        {"else": {"value": [{"group": "P32", "number": 221, "use": "v"}]}},
                    ]
                }
            },
        },
    ) == (1, 2)
    assert descriptor_active_raw_limits(
        store,
        {
            "min": 1,
            "max": 2,
            "mapping": {
                "raw": {
                    "any": [
                        {"else": {"value": ["skip", {"address": "P32.v221"}]}},
                    ]
                }
            },
        },
    ) == (15, 25)
    # Active family with only max bound.
    assert descriptor_active_raw_limits(
        FakeStore(flat_values={"P32.v10": 1, "P32.x10": 99}),
        {
            "min": 1,
            "max": 2,
            "mapping": {"raw": {"any": [{"else": {"value": [{"address": "P32.v10"}]}}]}},
        },
    ) == (1, 99)
    assert descriptor_active_raw_limits(
        FakeStore(flat_values={"P32.v11": 1, "P32.n11": 5}),
        {
            "min": 1,
            "max": 2,
            "mapping": {"raw": {"any": [{"else": {"value": [{"address": "P32.v11"}]}}]}},
        },
    ) == (5, 2)
    # Bad address / missing family keep descriptor bounds.
    assert descriptor_active_raw_limits(
        FakeStore(flat_values={}),
        {
            "min": 1,
            "max": 2,
            "mapping": {"raw": {"any": [{"else": {"value": [{"address": "P9.vX"}]}}]}},
        },
    ) == (1, 2)
    # Selected else has non-list value while a sibling branch still binds selectors.
    assert descriptor_active_raw_limits(
        FakeStore(flat_values={}),
        {
            "min": 1,
            "max": 2,
            "mapping": {
                "raw": {
                    "any": [
                        {
                            "if": [
                                {
                                    "expected": 1,
                                    "operation": "equalTo",
                                    "value": [{"group": "P1", "number": 0, "use": "v"}],
                                }
                            ],
                            "then": {"value": [{"group": "P32", "number": 0, "use": "v"}]},
                        },
                        {"else": {"value": "not-list"}},
                    ]
                }
            },
        },
    ) == (1, 2)
    assert descriptor_active_raw_limits(
        FakeStore(flat_values={}),
        {
            "min": 1,
            "max": 2,
            "mapping": {
                "raw": {
                    "any": [
                        {
                            "if": [
                                {
                                    "expected": 1,
                                    "operation": "equalTo",
                                    "value": [{"group": "P1", "number": 0, "use": "v"}],
                                }
                            ],
                            "then": {"value": [{"group": "P32", "number": 0, "use": "v"}]},
                        },
                        {"else": {"value": [{"foo": 1}]}},
                    ]
                }
            },
        },
    ) == (1, 2)
    assert descriptor_active_raw_limits(
        FakeStore(flat_values={}),
        {
            "min": 1,
            "max": 2,
            "mapping": {
                "raw": {
                    "any": [
                        {
                            "if": [
                                {
                                    "expected": 1,
                                    "operation": "equalTo",
                                    "value": [{"group": "P1", "number": 0, "use": "v"}],
                                }
                            ],
                            "then": {"value": [{"group": "P32", "number": 0, "use": "v"}]},
                        },
                        {"else": {"value": [{"address": "P9.v"}]}},
                    ]
                }
            },
        },
    ) == (1, 2)
    assert descriptor_active_raw_limits(
        FakeStore(flat_values={}),
        {
            "min": 1,
            "max": 2,
            "mapping": {"raw": {"any": [{"else": {"value": [{"address": "P9.v9"}]}}]}},
        },
    ) == (1, 2)


def test_spa_operation_helpers_and_compare_ops() -> None:
    from custom_components.habragerone.status_rules import (
        _address_from_spa_selector,
        compare_condition,
        raw_any_conditions_are_supported,
        spa_operation_name,
    )

    assert spa_operation_name(None) is None
    assert spa_operation_name("   ") is None
    assert spa_operation_name("ClauseOperation['equalTo']") == "equalTo"
    assert spa_operation_name("t.equalTo") == "equalTo"
    assert _address_from_spa_selector({"address": ".v7"}) is None
    assert _address_from_spa_selector({"address": "P32."}) is None
    assert raw_any_conditions_are_supported("nope") is True
    assert raw_any_conditions_are_supported(["skip", {"if": "bad"}]) is True
    assert raw_any_conditions_are_supported([{"if": ["bad"]}]) is False
    assert (
        raw_any_conditions_are_supported(
            [
                {
                    "if": [{"operation": "equalTo", "expected": 1, "value": [{"group": "P1", "number": 0, "use": "v"}]}],
                    "elseif": "bad",
                }
            ]
        )
        is True
    )
    assert (
        raw_any_conditions_are_supported([{"if": [{"operation": "ClauseOperation['matches']", "expected": 1, "value": []}]}])
        is False
    )
    assert compare_condition(operation="greaterThan", actual=3, expected=1) is True
    assert compare_condition(operation="greaterThanOrEqualTo", actual=1, expected=1) is True
    assert compare_condition(operation="lessThan", actual=1, expected=3) is True
    assert compare_condition(operation="lessThanOrEqualTo", actual=1, expected=1) is True
    assert compare_condition(operation="unknown", actual=1, expected=1) is False
