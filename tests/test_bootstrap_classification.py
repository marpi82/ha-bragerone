from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.bootstrap import normalize_cached_descriptors  # noqa: E402


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
        }
    ]

    normalized = normalize_cached_descriptors(descriptors)

    assert len(normalized) == 1
    assert normalized[0]["platform"] == "switch"


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
