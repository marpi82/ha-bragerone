"""Unit tests for bootstrap helper functions."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.bootstrap import (  # noqa: E402
    _coerce_raw,
    _command_rule_names,
    _enum_maps,
    _extract_symbol_token,
    _has_display_value,
    _has_named_command_rule,
    _has_runtime_raw_value,
    _is_action_command_name,
    _is_boiler_panel,
    _is_command_like_symbol,
    normalize_cached_descriptors,
)


def test_extract_symbol_token_reads_nested_mapping_and_object_fields() -> None:
    assert _extract_symbol_token("PARAM_1") == "PARAM_1"
    assert _extract_symbol_token("bad token") is None
    assert _extract_symbol_token({"token": "COMMAND_RESTART"}) == "COMMAND_RESTART"
    assert _extract_symbol_token({"parameter": {"token": "STATUS_P1_0"}}) == "STATUS_P1_0"
    assert _extract_symbol_token({"symbol": "PARAM_2"}) == "PARAM_2"
    assert _extract_symbol_token(SimpleNamespace(token="PARAM_3")) == "PARAM_3"
    assert _extract_symbol_token(SimpleNamespace(parameter=SimpleNamespace(name="PARAM_4"))) == "PARAM_4"


def test_extract_symbol_token_respects_recursion_depth() -> None:
    nested: dict[str, object] = {}
    current = nested
    for _ in range(5):
        child: dict[str, object] = {"parameter": {}}
        current["parameter"] = child
        current = child
    current["parameter"] = {"token": "PARAM_DEEP"}

    assert _extract_symbol_token(nested) is None


def test_coerce_raw_parses_bool_int_float_and_text() -> None:
    assert _coerce_raw(True) is True
    assert _coerce_raw(3.5) == 3.5
    assert _coerce_raw("true") is True
    assert _coerce_raw("42") == 42
    assert _coerce_raw("3.14") == 3.14
    assert _coerce_raw("plain") == "plain"


def test_enum_maps_builds_from_units_source_and_descriptor_unit() -> None:
    enum_map, raw_to_label = _enum_maps(
        {"units_source": {"0": "Off", "1": "On"}, "values": [0, 1]},
    )
    assert enum_map == {"Off": 0, "On": 1}
    assert raw_to_label == {"0": "Off", "1": "On"}

    enum_map, raw_to_label = _enum_maps(
        {},
        descriptor_unit={"1": "Low", "2": "High"},
    )
    assert enum_map == {"Low": 1, "High": 2}
    assert raw_to_label == {"1": "Low", "2": "High"}


def test_runtime_visibility_helpers() -> None:
    assert _has_display_value(value=None, value_label="  ready  ") is True
    assert _has_display_value(value="  ", value_label=None) is False
    assert _has_display_value(value=0, value_label=None) is True

    assert _has_runtime_raw_value(
        payload={"pool": "P4", "chan": "v", "idx": 1},
        mapping=None,
        flat_values={"P4.v1": 12},
    )
    assert _has_runtime_raw_value(
        payload={"pool": "P4", "chan": "v", "idx": 1},
        mapping={"inputs": [{"address": "P4.s2"}]},
        flat_values={"P4.s2": 1},
    )
    assert not _has_runtime_raw_value(
        payload={"pool": "P4", "chan": "v", "idx": 1},
        mapping={"inputs": [{"address": "P4.s2"}]},
        flat_values={},
    )


def test_command_symbol_helpers() -> None:
    assert _is_boiler_panel("Kocioł")
    assert _is_command_like_symbol("COMMAND_MODULE_RESTART")
    assert _is_command_like_symbol("MODULE_X_RESTART")
    assert not _is_command_like_symbol("PARAM_1")
    assert _has_named_command_rule({"command_rules": [{"command": "START"}]})
    assert _command_rule_names({"command_rules": [{"command": "void 0"}, {"command": " BOILER_START "}]}) == {"BOILER_START"}
    assert _is_action_command_name("MODULE_RESTART")


def test_normalize_cached_descriptors_classifies_status_fallback_paths() -> None:
    descriptors = [
        {
            "symbol": "STATUS_P5_1",
            "devid": "MOD1",
            "pool": "P5",
            "chan": "s",
            "idx": 1,
            "mapping": {"units_source": 12345, "values": [0, 1, 2]},
            "unit": {"0": "Idle", "1": "Work", "2": "Fault"},
            "writable": False,
            "menu_kinds": ["status"],
        },
        {
            "symbol": "PARAM_TOGGLE",
            "devid": "MOD1",
            "pool": "P4",
            "chan": "v",
            "idx": 9,
            "mapping": {"component_type": "toggle"},
            "writable": True,
            "menu_kinds": ["write"],
        },
        {
            "symbol": "PARAM_SWITCHISH",
            "devid": "MOD1",
            "pool": "P4",
            "chan": "s",
            "idx": 2,
            "mapping": {},
            "writable": True,
            "menu_kinds": ["write"],
        },
    ]

    normalized = normalize_cached_descriptors(descriptors)
    by_symbol = {item["symbol"]: item for item in normalized}

    assert by_symbol["STATUS_P5_1"]["platform"] == "sensor"
    assert by_symbol["PARAM_TOGGLE"]["platform"] == "switch"
    assert by_symbol["PARAM_SWITCHISH"]["platform"] == "switch"


def test_normalize_cached_descriptors_skips_non_dict_entries() -> None:
    assert normalize_cached_descriptors(["bad"]) == []
