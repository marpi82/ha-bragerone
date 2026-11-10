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
    evaluate_status_binary_from_rules,
    first_selector_address_value,
    select_raw_any_branch,
)
from tests.helpers.fakes import FakeStore


def test_parameter_address_from_rule_payload_variants() -> None:
    assert _parameter_address_from_rule_payload({"group": "P32", "number": 221, "use": "v"}) == ("P32", "v", 221)
    assert _parameter_address_from_rule_payload([{"address": "P32.v7"}]) == ("P32", "v", 7)
    assert _parameter_address_from_rule_payload([{"address": "P32.vX"}, "skip"]) is None
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
    assert first_selector_address_value(None, flat_values={}) is None
    assert first_selector_address_value({"value": "not-a-list"}, flat_values={}) is None
    assert (
        first_selector_address_value({"value": ["skip", {"group": "P1", "number": 0, "use": "v"}]}, flat_values={"P1.v0": 3}) == 3
    )
    assert _addresses_from_rule_payload([{"group": "P1", "number": 0, "use": "v"}]) == {"P1.v0"}
    assert _addresses_from_rule_payload({"value": [{"group": "P2", "number": 1, "use": "s"}]}) == {"P2.s1"}


def test_binary_condition_helpers_cover_reject_paths() -> None:
    assert _spa_conditions_match_for_binary(["bad"], flat_values={}) is False
    assert _spa_conditions_match_for_binary([{"operation": 1}], flat_values={}) is False
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
    assert (
        _mapping_has_parameter_write(
            {"raw": {"any": ["skip", {"else": {"command": [{"group": "P1", "number": 0, "use": "v"}]}}]}}
        )
        is True
    )


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
