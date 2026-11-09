"""Unit tests for bootstrap helper functions."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.bootstrap import (  # noqa: E402
    EntityDescriptor,
    _card_descriptor_has_measurement_unit,
    _coerce_raw,
    _command_rule_names,
    _descriptor_for_value_slot,
    _enum_maps,
    _extract_options,
    _extract_symbol_token,
    _finalize_slot_descriptor,
    _has_display_value,
    _has_named_command_rule,
    _has_runtime_raw_value,
    _is_action_command_name,
    _is_boiler_panel,
    _is_command_like_symbol,
    _rule_address_dedupe_key,
    _value_slots_from_payload,
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


def test_enum_maps_filters_values_list_with_units_source_by_min_max() -> None:
    mapping = {
        "units_source": {
            "0": "Off",
            "1": "Pump",
            "2": "Return protection",
            "3": "Pump + circulation",
            "4": "3D valve",
        },
        "values": [0, 1, 2, 3, 4],
    }
    enum_map, raw_to_label = _enum_maps(mapping, minimum=1, maximum=3)

    assert enum_map == {
        "Pump": 1,
        "Return protection": 2,
        "Pump + circulation": 3,
    }
    assert raw_to_label == {
        "1": "Pump",
        "2": "Return protection",
        "3": "Pump + circulation",
    }
    assert _extract_options(mapping, minimum=1, maximum=3) == [
        "Pump",
        "Return protection",
        "Pump + circulation",
    ]


def test_enum_maps_filters_units_source_items_without_values_list() -> None:
    mapping = {"units_source": {"0": "A", "1": "B", "2": "C", "3": "D"}}
    enum_map, raw_to_label = _enum_maps(mapping, minimum=1, maximum=2)

    assert enum_map == {"B": 1, "C": 2}
    assert raw_to_label == {"1": "B", "2": "C"}


def test_enum_maps_filters_bare_values_list_and_descriptor_unit() -> None:
    enum_map, raw_to_label = _enum_maps({"values": [0, 1, 2, 3]}, minimum=1, maximum=2)
    assert enum_map == {"1": 1, "2": 2}
    assert raw_to_label == {"1": "1", "2": "2"}

    enum_map, raw_to_label = _enum_maps(
        {},
        descriptor_unit={"0": "Zero", "1": "One", "2": "Two", "3": "Three"},
        minimum=1,
        maximum=2,
    )
    assert enum_map == {"One": 1, "Two": 2}
    assert raw_to_label == {"1": "One", "2": "Two"}


def test_enum_maps_keeps_non_numeric_and_bool_raw_when_bounds_present() -> None:
    enum_map, _ = _enum_maps(
        {"units_source": {"true": "Yes", "false": "No", "auto": "Auto"}, "values": ["true", "false", "auto"]},
        minimum=0,
        maximum=1,
    )
    assert enum_map == {"Yes": True, "No": False, "Auto": "auto"}


def test_enum_maps_without_bounds_keeps_full_range() -> None:
    mapping = {"units_source": {"0": "A", "1": "B", "2": "C"}, "values": [0, 1, 2]}
    enum_map, _ = _enum_maps(mapping)
    assert enum_map == {"A": 0, "B": 1, "C": 2}


def test_normalize_cached_descriptors_filters_select_options_by_min_max() -> None:
    descriptors = [
        {
            "symbol": "VALVE_FUNC",
            "devid": "MOD1",
            "pool": "P4",
            "chan": "v",
            "idx": 2,
            "min": 1,
            "max": 3,
            "mapping": {
                "command_rules": [{"command": "setValve", "value": 1}],
                "values": [0, 1, 2, 3, 4],
                "units_source": {
                    "0": "Off",
                    "1": "Pump",
                    "2": "Return protection",
                    "3": "Pump + circulation",
                    "4": "3D valve",
                },
            },
            "writable": True,
            "menu_kinds": ["write"],
            # Stale full option list from an older bootstrap cache.
            "options": ["Off", "Pump", "Return protection", "Pump + circulation", "3D valve"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "select"
    assert normalized[0]["options"] == ["Pump", "Return protection", "Pump + circulation"]
    assert normalized[0]["enum_map"] == {
        "Pump": 1,
        "Return protection": 2,
        "Pump + circulation": 3,
    }
    # Pre-#212 caches omit enabled_by_default; normalize fills True as a safe default.
    assert normalized[0]["enabled_by_default"] is True


def test_normalize_cached_descriptors_preserves_explicit_enabled_by_default() -> None:
    """Descriptors that already carry enabled_by_default must keep the cached flag (#212)."""
    descriptors = [
        {
            "symbol": "PARAM_0",
            "devid": "MOD1",
            "pool": "P6",
            "chan": "v",
            "idx": 0,
            "writable": False,
            "enabled_by_default": False,
            "mapping": {},
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["enabled_by_default"] is False


def test_runtime_visibility_helpers() -> None:
    assert _has_display_value(value=None, value_label="  ready  ") is True
    assert _has_display_value(value="  ", value_label=None) is False
    assert _has_display_value(value=0, value_label=None) is True
    assert _has_display_value(value="ready", value_label=None) is True
    assert (
        _has_display_value(
            value=None,
            value_label=None,
            mapping={"paths": {"value": [{"else": "OFF"}]}},
        )
        is True
    )
    assert _has_display_value(value=None, value_label=None, mapping={"paths": {"value": []}}) is False
    # Schedule / password composites (then/else = selector lists) are not display values.
    schedule_mapping = {
        "paths": {
            "value": [
                {
                    "if": [{"expected": None, "operation": "equalTo", "value": [{"group": "P6", "number": 177, "use": "v"}]}],
                    "then": None,
                },
                {
                    "else": [
                        {"group": "P12", "number": 0, "use": "a"},
                        {"group": "P12", "number": 0, "use": "b"},
                    ]
                },
            ]
        }
    }
    assert _has_display_value(value=None, value_label=None, mapping=schedule_mapping) is False


def test_rule_address_dedupe_key_and_measurement_unit_helpers() -> None:
    """Footer diodes share address+rule fingerprint; measurement units keep companions."""
    rules = [{"else": "OFF"}]
    mapping = {"paths": {"value": rules}}
    from custom_components.habragerone.status_rules import status_value_rules_fingerprint

    assert _rule_address_dedupe_key(payload={"pool": "P0", "chan": "s", "idx": 1}, mapping=mapping) == (
        "P0",
        "s",
        1,
        status_value_rules_fingerprint(mapping),
    )
    assert _rule_address_dedupe_key(payload={"pool": "P0", "chan": "s", "idx": "x"}, mapping=mapping) is None
    assert _rule_address_dedupe_key(payload={"pool": "P0", "chan": "s", "idx": 1}, mapping={"paths": {}}) is None
    assert _rule_address_dedupe_key(
        payload={"pool": "P0", "chan": "s", "idx": 1},
        mapping={"raw": {"value": rules}, "paths": "bad"},
    ) == ("P0", "s", 1, repr(rules))
    assert _rule_address_dedupe_key(payload={"pool": "P0", "chan": "s", "idx": 1}, mapping={"raw": {}}) is None
    # raw.any uses the same rule-list selector as evaluation.
    assert _rule_address_dedupe_key(
        payload={"pool": "P0", "chan": "s", "idx": 1},
        mapping={"raw": {"any": [{"else": "OFF"}]}},
    ) == ("P0", "s", 1, repr([{"else": "OFF"}]))
    # Ordinary address selectors in paths.value must not fingerprint as rules.
    assert (
        _rule_address_dedupe_key(
            payload={"pool": "P0", "chan": "v", "idx": 1},
            mapping={"paths": {"value": [{"group": "P0", "number": 1, "use": "v"}]}},
        )
        is None
    )

    assert _card_descriptor_has_measurement_unit({"transform_scale": 0.01}) is True
    assert _card_descriptor_has_measurement_unit({"unit_code": 49}) is True
    assert _card_descriptor_has_measurement_unit({"unit_code": "49"}) is True
    assert _card_descriptor_has_measurement_unit({"unit": "°C"}) is True
    assert _card_descriptor_has_measurement_unit({"unit": "HEAT_PUMP_STATE"}) is False
    assert _card_descriptor_has_measurement_unit({"unit": True}) is False
    assert _card_descriptor_has_measurement_unit({}) is False

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


def test_value_slots_from_payload_filters_invalid_entries() -> None:
    """Only complete slot address dicts survive; missing value_slots → empty."""
    assert _value_slots_from_payload({}) == []
    assert _value_slots_from_payload({"value_slots": "bad"}) == []
    assert _value_slots_from_payload(
        {
            "value_slots": [
                {"slot": "value", "pool": "P31", "chan": "s", "idx": 12},
                {"slot": "value2", "pool": "P30", "chan": "v", "idx": 25},
                {"slot": "bad", "pool": "P1", "chan": "v"},  # missing idx
                {"slot": "", "pool": "P1", "chan": "v", "idx": 0},
                "skip-me",
            ]
        }
    ) == [
        {"slot": "value", "pool": "P31", "chan": "s", "idx": 12},
        {"slot": "value2", "pool": "P30", "chan": "v", "idx": 25},
    ]


def test_descriptor_for_value_slot_keeps_primary_symbol_and_suffixes_companions() -> None:
    """Primary slot keeps stable unique_id symbol; companions get #valueN + label."""
    base: EntityDescriptor = {
        "key": "DEV1:STATUS_POMPY",
        "symbol": "STATUS_POMPY",
        "devid": "DEV1",
        "label": "Heat pump status",
        "pool": "P31",
        "chan": "s",
        "idx": 12,
        "writable": False,
        "options": ["Off", "On"],
        "enum_map": {"Off": 0, "On": 1},
        "raw_to_label": {"0": "Off", "1": "On"},
        "mapping": {"component_type": "STATUS"},
        "unit": {"0": "Off", "1": "On"},
    }
    primary = _descriptor_for_value_slot(
        base,
        slot={"slot": "value", "pool": "P31", "chan": "s", "idx": 12},
        parent_label="Heat pump status",
    )
    assert primary["symbol"] == "STATUS_POMPY"
    assert primary["key"] == "DEV1:STATUS_POMPY"
    assert primary["label"] == "Heat pump status"
    assert primary["options"] == ["Off", "On"]

    companion = _descriptor_for_value_slot(
        {
            **base,
            "writable": True,
            "min": 0,
            "max": 100,
            "menu_kinds": ["read", "write"],
            "mapping": {
                "component_type": "STATUS",
                "command_rules": [{"command": "BOILER_START", "value": "ON"}],
                "units_source": "BOILER_STATE",
            },
        },
        slot={"slot": "value2", "pool": "P30", "chan": "v", "idx": 25},
        parent_label="Heat pump status",
    )
    assert companion["symbol"] == "STATUS_POMPY#value2"
    assert companion["key"] == "DEV1:STATUS_POMPY#value2"
    assert companion["label"] == "Heat pump status (value2)"
    assert companion["pool"] == "P30"
    assert companion["chan"] == "v"
    assert companion["idx"] == 25
    assert companion["writable"] is False
    assert companion["min"] is None
    assert companion["max"] is None
    assert companion["menu_kinds"] == ["read"]
    assert companion["mapping"] == {}
    assert companion["options"] == []
    assert companion["enum_map"] == {}
    assert companion.get("unit") is None

    finalized = _finalize_slot_descriptor(companion)
    assert finalized is not None
    assert finalized["platform"] == "sensor"

    status_companion = _descriptor_for_value_slot(
        {
            **base,
            "writable": True,
            "mapping": {
                "component_type": "STATUS",
                "command_rules": [{"command": "BOILER_START", "value": "ON"}],
                "inputs": [{"address": "P5.s0"}],
                "paths": {
                    "value": [{"else": "ON"}],
                    "unit": [{"group": "P5", "number": 0, "use": "u"}],
                },
                "raw": {"any": [{"else": "OFF"}], "meta": 1},
            },
        },
        slot={"slot": "value3", "pool": "P32", "chan": "s", "idx": 1},
        parent_label="Heat pump status",
    )
    assert status_companion["symbol"] == "STATUS_POMPY#value3"
    assert status_companion["chan"] == "s"
    assert status_companion["writable"] is False
    # Status companions keep parent enum maps / unit, but drop write/command metadata
    # and the primary card's SPA value rules (paths.value / raw.any).
    assert status_companion["options"] == ["Off", "On"]
    assert status_companion["enum_map"] == {"Off": 0, "On": 1}
    assert status_companion.get("unit") == {"0": "Off", "1": "On"}
    assert status_companion["mapping"] == {
        "component_type": "STATUS",
        "paths": {"unit": [{"group": "P5", "number": 0, "use": "u"}]},
        "raw": {"meta": 1},
    }

    # Value-only paths/raw containers are dropped entirely after stripping rules.
    value_only_companion = _descriptor_for_value_slot(
        {
            **base,
            "mapping": {
                "component_type": "STATUS",
                "paths": {"value": [{"else": "ON"}]},
                "raw": {"any": [{"else": "OFF"}]},
            },
        },
        slot={"slot": "value3", "pool": "P32", "chan": "s", "idx": 2},
        parent_label="Heat pump status",
    )
    assert value_only_companion["mapping"] == {"component_type": "STATUS"}
    # Non-dict paths/raw entries are left untouched.
    weird_container = _descriptor_for_value_slot(
        {
            **base,
            "mapping": {"component_type": "STATUS", "paths": "bad", "raw": ["x"]},
        },
        slot={"slot": "value3", "pool": "P32", "chan": "s", "idx": 3},
        parent_label="Heat pump status",
    )
    assert weird_container["mapping"] == {"component_type": "STATUS", "paths": "bad", "raw": ["x"]}

    status_without_mapping = _descriptor_for_value_slot(
        {**base, "mapping": None},
        slot={"slot": "value3", "pool": "P32", "chan": "s", "idx": 1},
        parent_label="Heat pump status",
    )
    assert status_without_mapping["writable"] is False
    assert status_without_mapping.get("mapping") is None

    plain_unit = _descriptor_for_value_slot(
        {
            **base,
            "unit": "°C",
            "unit_code": 1,
            "transform_scale": 0.1,
            "transform_offset": 0.0,
            "transform_precision": 1,
        },
        slot={"slot": "value2", "pool": "P30", "chan": "v", "idx": 25},
        parent_label="Heat pump status",
    )
    # SPA parseValue formats companions through the card measurement unit (primary u).
    assert plain_unit.get("unit") == "°C"
    assert plain_unit.get("unit_code") == 1
    assert plain_unit.get("transform_scale") == 0.1
    assert plain_unit.get("transform_precision") == 1

    enum_only = _descriptor_for_value_slot(
        {
            **base,
            "unit": "HEAT_PUMP_STATE",
            "unit_code": "HEAT_PUMP_STATE",
        },
        slot={"slot": "value2", "pool": "P30", "chan": "v", "idx": 25},
        parent_label="Heat pump status",
    )
    assert enum_only.get("unit") is None
    assert "unit_code" not in enum_only


def test_normalize_cached_descriptors_keeps_composite_companions_read_only() -> None:
    """Cached #valueN rows stay sensors even when parent write metadata is present."""
    normalized = normalize_cached_descriptors(
        [
            {
                "symbol": "STATUS_POMPY#value2",
                "devid": "DEV1",
                "pool": "P30",
                "chan": "v",
                "idx": 25,
                "writable": True,
                "min": 0,
                "max": 100,
                "menu_kinds": ["write"],
                "mapping": {
                    "component_type": "STATUS",
                    "command_rules": [{"command": "BOILER_START", "value": "ON"}],
                    "units_source": {"0": "Off", "1": "On"},
                },
                "unit": {"0": "Off", "1": "On"},
                "enabled_by_default": False,
            }
        ]
    )
    assert len(normalized) == 1
    companion = normalized[0]
    assert companion["writable"] is False
    assert companion["platform"] == "sensor"
    assert companion["mapping"] == {}
    assert companion["options"] == []
    assert companion["min"] is None
    assert companion["max"] is None


def test_finalize_slot_descriptor_returns_none_when_not_exposable() -> None:
    """Slot clones without a direct address / write capability are dropped."""
    assert (
        _finalize_slot_descriptor(
            {
                "symbol": "STATUS_POMPY#value2",
                "writable": False,
                "pool": None,
                "chan": None,
                "idx": None,
                "mapping": {},
            }
        )
        is None
    )
