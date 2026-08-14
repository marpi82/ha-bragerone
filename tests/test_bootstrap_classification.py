from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.bootstrap import (  # noqa: E402
    _collect_symbol_kinds_from_route,
    _is_menu_command_action,
    _mapping_has_parameter_write,
    _normalize_panel_path,
    normalize_cached_descriptors,
)


def test_normalize_cached_descriptors_filters_non_exposable_tokens() -> None:
    descriptors = [
        {
            "symbol": "INTERNAL_TOKEN",
            "devid": "MOD1",
            "pool": None,
            "chan": None,
            "idx": None,
            "mapping": {},
            "writable": False,
        },
        {
            "symbol": "PARAM_P4_1",
            "devid": "MOD1",
            "pool": "P4",
            "chan": "v",
            "idx": 1,
            "mapping": {},
            "writable": False,
        },
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["symbol"] == "PARAM_P4_1"
    assert normalized[0]["platform"] == "sensor"


def test_normalize_cached_descriptors_classifies_status_channel_as_binary_sensor() -> None:
    descriptors = [
        {
            "symbol": "PARAM_P5_40",
            "devid": "MOD1",
            "pool": "P5",
            "chan": "s",
            "idx": 40,
            "mapping": {},
            "writable": False,
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "binary_sensor"


def test_normalize_cached_descriptors_classifies_status_with_enum_unit_as_sensor() -> None:
    descriptors = [
        {
            "symbol": "STATUS_P5_0",
            "devid": "MOD1",
            "pool": "P5",
            "chan": "s",
            "idx": 0,
            "mapping": {"units_source": 9998, "values": []},
            "unit": {"0": "Postoj", "1": "Praca", "2": "Rozpalanie"},
            "writable": False,
            "menu_kinds": ["status"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "sensor"
    assert normalized[0]["options"] == ["Postoj", "Praca", "Rozpalanie"]


def test_normalize_cached_descriptors_classifies_on_off_status_rules_as_binary_sensor() -> None:
    descriptors = [
        {
            "symbol": "STATUS_P5_19",
            "devid": "MOD1",
            "pool": "P5",
            "chan": "s",
            "idx": 19,
            "mapping": {
                "units_source": 9996,
                "command_rules": [
                    {"value": "wn.ON", "conditions": [{"operation": "xa.equalTo", "expected": 1}]},
                    {"value": "wn.OFF", "conditions": [{"operation": "xa.equalTo", "expected": 0}]},
                ],
            },
            "unit": None,
            "writable": False,
            "menu_kinds": ["status"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "binary_sensor"


def test_normalize_cached_descriptors_classifies_binary_status_unit_as_binary_sensor() -> None:
    descriptors = [
        {
            "symbol": "STATUS_P5_22",
            "devid": "MOD1",
            "pool": "P5",
            "chan": "s",
            "idx": 22,
            "mapping": {"units_source": 9994, "command_rules": []},
            "unit": {"0": "Wyłączone", "1": "Włączone"},
            "writable": False,
            "menu_kinds": ["status"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "binary_sensor"


def test_normalize_cached_descriptors_classifies_binary_status_unit_independent_of_labels() -> None:
    descriptors = [
        {
            "symbol": "STATUS_P5_77",
            "devid": "MOD1",
            "pool": "P5",
            "chan": "s",
            "idx": 77,
            "mapping": {"units_source": 12345, "command_rules": []},
            "unit": {"0": "BeliebigAus", "1": "BeliebigEin"},
            "writable": False,
            "menu_kinds": ["status"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "binary_sensor"


def test_normalize_cached_descriptors_classifies_binary_read_unit_as_binary_sensor() -> None:
    descriptors = [
        {
            "symbol": "PARAM_61",
            "devid": "MOD1",
            "pool": "P5",
            "chan": "v",
            "idx": 61,
            "mapping": {},
            "unit": {"0": "Wyłączony", "1": "Załączony"},
            "writable": False,
            "menu_kinds": ["read"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "binary_sensor"


def test_normalize_cached_descriptors_classifies_status_with_binary_units_source_as_binary_sensor() -> None:
    descriptors = [
        {
            "symbol": "STATUS_P5_22",
            "devid": "MOD1",
            "pool": "P5",
            "chan": "s",
            "idx": 22,
            "mapping": {"units_source": 9994},
            "unit": "wn.9994",
            "writable": False,
            "menu_kinds": ["status"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "binary_sensor"


def test_normalize_cached_descriptors_keeps_writable_status_symbol_as_non_binary() -> None:
    descriptors = [
        {
            "symbol": "URUCHOMIENIE_KOTLA",
            "devid": "MOD1",
            "pool": "P5",
            "chan": "s",
            "idx": 0,
            "mapping": {"command_rules": [{"command": "BOILER_START", "value": "OFF"}]},
            "writable": True,
            "menu_kinds": ["write"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] != "binary_sensor"


def test_normalize_cached_descriptors_classifies_enum_writable_as_select() -> None:
    descriptors = [
        {
            "symbol": "MODE",
            "devid": "MOD1",
            "pool": "P4",
            "chan": "v",
            "idx": 2,
            "mapping": {
                "command_rules": [{"command": "setMode", "value": 1}],
                "values": [0, 1, 2],
                "units_source": {"0": "Off", "1": "Eco", "2": "Boost"},
            },
            "writable": True,
            "menu_kinds": ["write"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "select"
    assert normalized[0]["options"] == ["Off", "Eco", "Boost"]


def test_normalize_cached_descriptors_classifies_switch_like_rules_as_switch() -> None:
    descriptors = [
        {
            "symbol": "PUMP_ENABLE",
            "devid": "MOD1",
            "pool": "P4",
            "chan": "v",
            "idx": 3,
            "mapping": {
                "command_rules": [
                    {"command": "turnOn", "logic": "on", "value": 1},
                    {"command": "turnOff", "logic": "off", "value": 0},
                ]
            },
            "writable": True,
            "menu_kinds": ["write"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "switch"


def test_normalize_cached_descriptors_defaults_writable_value_channel_to_number() -> None:
    descriptors = [
        {
            "symbol": "PARAM_49",
            "devid": "MOD1",
            "pool": "P6",
            "chan": "v",
            "idx": 49,
            "mapping": {"command_rules": []},
            "writable": True,
            "menu_kinds": ["write"],
            "min": None,
            "max": None,
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "number"


def test_normalize_cached_descriptors_classifies_write_without_address_as_button() -> None:
    descriptors = [
        {
            "symbol": "SYNC_ACTION",
            "devid": "MOD1",
            "pool": None,
            "chan": None,
            "idx": None,
            "mapping": {
                "command_rules": [{"command": "syncNow", "value": 1}],
                "component_type": "action",
            },
            "writable": True,
            "menu_kinds": ["write"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "button"


def test_normalize_cached_descriptors_filters_ui_only_component_types() -> None:
    descriptors = [
        {
            "symbol": "PASSWORD_MENU",
            "devid": "MOD1",
            "pool": "P4",
            "chan": "v",
            "idx": 90,
            "mapping": {
                "component_type": "password_menu",
            },
            "writable": False,
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert normalized == []


def test_normalize_cached_descriptors_uses_menu_kinds_for_writable() -> None:
    descriptors = [
        {
            "symbol": "STATUS_P5_11",
            "devid": "MOD1",
            "pool": "P5",
            "chan": "s",
            "idx": 11,
            "mapping": {"command_rules": [{"command": "BOILER_START", "value": "OFF"}]},
            "writable": True,
            "menu_kinds": ["status"],
        },
        {
            "symbol": "URUCHOMIENIE_KOTLA",
            "devid": "MOD1",
            "pool": "P5",
            "chan": "s",
            "idx": 0,
            "mapping": {"command_rules": [{"command": "BOILER_START", "value": "OFF"}]},
            "writable": False,
            "menu_kinds": ["write"],
        },
    ]

    normalized = normalize_cached_descriptors(descriptors)
    by_symbol = {item["symbol"]: item for item in normalized}

    assert by_symbol["STATUS_P5_11"]["writable"] is False
    assert by_symbol["URUCHOMIENIE_KOTLA"]["writable"] is True


def test_normalize_cached_descriptors_treats_special_command_symbol_as_writable() -> None:
    descriptors = [
        {
            "symbol": "COMMAND_MODULE_RESTART",
            "devid": "MOD1",
            "pool": None,
            "chan": None,
            "idx": None,
            "mapping": {"command_rules": [{"command": "MODULE_RESTART", "value": "ONLINE"}]},
            "writable": False,
            "menu_kinds": ["special"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["writable"] is True
    assert normalized[0]["platform"] == "button"


def test_normalize_cached_descriptors_treats_special_with_named_command_as_writable() -> None:
    descriptors = [
        {
            "symbol": "PARAM_999",
            "devid": "MOD1",
            "pool": None,
            "chan": None,
            "idx": None,
            "mapping": {"command_rules": [{"command": "MODULE_RESTART", "value": "ONLINE"}]},
            "writable": False,
            "menu_kinds": ["special"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["writable"] is True
    assert normalized[0]["platform"] == "button"


def test_normalize_cached_descriptors_unresolved_command_symbol_is_button() -> None:
    descriptors = [
        {
            "symbol": "COMMAND_MODULE_RESTART",
            "devid": "MOD1",
            "pool": None,
            "chan": None,
            "idx": None,
            "mapping": {"command_rules": [{"command": "COMMAND_MODULE_RESTART"}]},
            "writable": False,
            "menu_kinds": ["special"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["writable"] is True
    assert normalized[0]["platform"] == "button"


def test_normalize_panel_path_drops_only_first_menu_level() -> None:
    assert _normalize_panel_path("Menu palnika/Zawór 1") == "Menu palnika/Zawór 1"
    assert _normalize_panel_path("General menu/Burner/Fan") == "General menu/Burner/Fan"
    assert _normalize_panel_path("SingleLevel") == "SingleLevel"
    assert _normalize_panel_path("Boiler") == "Boiler"
    assert _normalize_panel_path("DHW") == "DHW"
    assert _normalize_panel_path("Valve 1") == "Valve 1"


def test_collect_symbol_kinds_from_route_reads_nested_parameter_token() -> None:
    class _Param:
        def __init__(self, token: str) -> None:
            self.token = token

    class _Entry:
        def __init__(self, token: str) -> None:
            self.parameter = _Param(token)

    class _Params:
        def __init__(self) -> None:
            self.read: list[object] = []
            self.write = [_Entry("COMMAND_MODULE_RESTART")]
            self.status: list[object] = []
            self.special: list[object] = []

    class _Route:
        def __init__(self) -> None:
            self.parameters = _Params()
            self.meta = None

    kinds = _collect_symbol_kinds_from_route(_Route())

    assert "COMMAND_MODULE_RESTART" in kinds
    assert "write" in kinds["COMMAND_MODULE_RESTART"]


def test_collect_symbol_kinds_from_route_reads_nested_parameter_token_from_dict() -> None:
    route = {
        "parameters": {
            "read": [],
            "write": [{"parameter": {"token": "COMMAND_MODULE_RESTART"}}],
            "status": [],
            "special": [],
        }
    }

    kinds = _collect_symbol_kinds_from_route(route)

    assert "COMMAND_MODULE_RESTART" in kinds
    assert "write" in kinds["COMMAND_MODULE_RESTART"]


def test_collect_symbol_kinds_from_route_reads_parameter_string_token_from_dict() -> None:
    route = {
        "parameters": {
            "read": [],
            "write": [{"parameter": "COMMAND_MODULE_RESTART"}],
            "status": [],
            "special": [],
        }
    }

    kinds = _collect_symbol_kinds_from_route(route)

    assert "COMMAND_MODULE_RESTART" in kinds
    assert "write" in kinds["COMMAND_MODULE_RESTART"]


def test_mapping_has_parameter_write_accepts_value_channel_aliases() -> None:
    """Cover alternate ParamMap field names used by inline/index factories."""
    assert _mapping_has_parameter_write(None) is False
    assert _mapping_has_parameter_write({}) is False
    assert _mapping_has_parameter_write({"paths": "bad"}) is False
    assert _mapping_has_parameter_write({"paths": {"command": "bad"}}) is False
    assert _mapping_has_parameter_write({"paths": {"command": ["skip", 1]}}) is False

    assert (
        _mapping_has_parameter_write(
            {
                "paths": {
                    "command": [
                        {"pool": "P10", "index": 2, "path": "value"},
                    ]
                }
            }
        )
        is True
    )
    assert (
        _mapping_has_parameter_write(
            {
                "paths": {
                    "command": [
                        {"group": "", "number": 1, "use": "v"},
                        {"group": "P6", "idx": 61, "pathType": "V"},
                    ]
                }
            }
        )
        is True
    )
    assert (
        _mapping_has_parameter_write(
            {
                "paths": {
                    "command": [
                        {"group": "P6", "number": "61", "use": "v"},
                        {"group": "P6", "number": 61, "chan": "   "},
                        {"group": "P6", "number": 61, "chan": "s"},
                    ]
                }
            }
        )
        is False
    )


def test_is_menu_command_action_uses_parameter_write_unless_status_symbol() -> None:
    mapping = {"paths": {"command": [{"group": "P6", "number": 239, "use": "v"}]}}
    assert _is_menu_command_action(symbol="PARAM_239", symbol_kinds=set(), mapping=mapping) is True
    assert _is_menu_command_action(symbol="STATUS_P5_10", symbol_kinds={"status"}, mapping=mapping) is False
    assert _is_menu_command_action(symbol="PARAM_1", symbol_kinds={"read"}, mapping={"paths": {"command": []}}) is False
    assert _is_menu_command_action(symbol="PARAM_1", symbol_kinds={"write"}, mapping=None) is True
    assert (
        _is_menu_command_action(
            symbol="CUSTOM_ACTION",
            symbol_kinds={"special"},
            mapping={"command_rules": [{"command": "MODULE_RESTART"}]},
        )
        is True
    )
    assert _mapping_has_parameter_write({"paths": {"command": [{"group": "P6", "number": 1, "chan": "v"}]}}) is True


def test_normalize_cached_descriptors_treats_status_menu_param_with_write_path_as_select() -> None:
    """Editable Tak/Nie PARAMs listed only under menu status must become select."""
    descriptors = [
        {
            "symbol": "PARAM_61",
            "devid": "MOD1",
            "pool": "P6",
            "chan": "v",
            "idx": 61,
            "min": 0,
            "max": 1,
            "unit": {"0": "Wyłączony", "1": "Załączony"},
            "mapping": {
                "paths": {
                    "value": [{"group": "P6", "number": 61, "use": "v"}],
                    "command": [{"group": "P6", "number": 61, "use": "v", "raw": "!![]"}],
                    "min": [],
                    "max": [],
                    "unit": [],
                    "status": [],
                }
            },
            "writable": False,
            "menu_kinds": ["status"],
        },
        {
            "symbol": "PARAM_239",
            "devid": "MOD1",
            "pool": "P6",
            "chan": "v",
            "idx": 239,
            "min": 0,
            "max": 1,
            "unit": {"0": "Nie", "1": "Tak"},
            "mapping": {
                "paths": {
                    "command": [{"group": "P6", "number": 239, "use": "v"}],
                }
            },
            "writable": False,
            "menu_kinds": ["status"],
        },
    ]

    normalized = normalize_cached_descriptors(descriptors)
    by_symbol = {item["symbol"]: item for item in normalized}

    assert by_symbol["PARAM_61"]["writable"] is True
    assert by_symbol["PARAM_61"]["platform"] == "select"
    assert by_symbol["PARAM_61"]["options"] == ["Wyłączony", "Załączony"]
    assert by_symbol["PARAM_239"]["writable"] is True
    assert by_symbol["PARAM_239"]["platform"] == "select"
    assert by_symbol["PARAM_239"]["options"] == ["Nie", "Tak"]


def test_normalize_cached_descriptors_treats_panel_only_param_with_write_path_as_number() -> None:
    """PARAM16_* feeder setpoints have empty menu_kinds but still expose paths.command."""
    descriptors = [
        {
            "symbol": "PARAM16_2",
            "devid": "MOD1",
            "pool": "P10",
            "chan": "v",
            "idx": 2,
            "min": 259,
            "max": 370,
            "unit": None,
            "mapping": {
                "paths": {
                    "value": [{"group": "P10", "number": 2, "use": "v"}],
                    "command": [{"group": "P10", "number": 2, "use": "v", "raw": "!![]"}],
                    "min": [{"group": "P10", "number": 2, "use": "n"}],
                    "max": [{"group": "P10", "number": 2, "use": "x"}],
                }
            },
            "writable": False,
            "menu_kinds": [],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["writable"] is True
    assert normalized[0]["platform"] == "number"


def test_normalize_cached_descriptors_keeps_status_symbol_readonly_without_value_write() -> None:
    descriptors = [
        {
            "symbol": "STATUS_P5_14",
            "devid": "MOD1",
            "pool": "P5",
            "chan": "s",
            "idx": 14,
            "unit": "wn.9994",
            "mapping": {
                "paths": {
                    "value": [
                        {
                            "if": [
                                {
                                    "expected": 1,
                                    "operation": "equalTo",
                                    "value": [{"group": "P5", "number": 14, "use": "s", "bit": 1}],
                                }
                            ],
                            "then": "ON",
                        }
                    ],
                    "command": [],
                },
                "command_rules": [],
            },
            "writable": False,
            "menu_kinds": ["status"],
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["writable"] is False
    assert normalized[0]["platform"] == "binary_sensor"
