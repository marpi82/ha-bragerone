"""Tests for config_flow helper functions not covered elsewhere."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from tests.conftest import install_pybragerone_stubs

install_pybragerone_stubs()

from custom_components.habragerone.config_flow import (  # noqa: E402
    _build_modules_step_schema,
    _device_grouping_values,
    _entity_filter_mode_values,
    _extract_language_label,
    _extract_selected_module_filter_modes,
    _language_label_from_row,
    _looks_like_language_code_label,
    _module_choices,
    _ui_field_labels,
)
from custom_components.habragerone.const import (  # noqa: E402
    CONF_DEVICE_GROUPING,
    CONF_ENTITY_FILTER_MODE,
    CONF_MODULES,
    DEFAULT_DEVICE_GROUPING,
    DEVICE_GROUPING_BY_MENU,
    DEVICE_GROUPING_FLAT,
    FILTER_MODE_UI,
)


def test_module_choices_skips_empty_devid_and_formats_label() -> None:
    modules = [
        {"devid": "", "name": "Skip me"},
        {"devid": "DEV1", "name": "Boiler", "moduleVersion": "2.1"},
        {"devid": "DEV2", "moduleTitle": "Pump", "moduleVersion": "1.0"},
    ]

    assert _module_choices(modules) == [
        ("DEV1", "Boiler (devid=DEV1, version=2.1)"),
        ("DEV2", "Pump (devid=DEV2, version=1.0)"),
    ]


def test_ui_field_labels_supports_polish_and_english() -> None:
    assert _ui_field_labels("pl-PL")["language"] == "Język"
    assert _ui_field_labels("en")["language"] == "Language"


def test_entity_filter_mode_values_supports_polish_and_english() -> None:
    assert "Filtrowanie po menu UI (codzienny web UI)" in _entity_filter_mode_values(ui_language="pl").values()
    assert "UI menu filtering (everyday web UI)" in _entity_filter_mode_values(ui_language="en").values()


def test_extract_selected_module_filter_modes_rejects_invalid_mode() -> None:
    user_input: dict[str, Any] = {CONF_ENTITY_FILTER_MODE: "unknown-mode"}
    assert (
        _extract_selected_module_filter_modes(
            user_input=user_input,
            module_ids=["DEV1"],
            default_mode=FILTER_MODE_UI,
        )
        is None
    )


def test_extract_selected_module_filter_modes_maps_all_modules() -> None:
    user_input: dict[str, Any] = {CONF_ENTITY_FILTER_MODE: FILTER_MODE_UI}
    assert _extract_selected_module_filter_modes(
        user_input=user_input,
        module_ids=["DEV1", "DEV2"],
        default_mode=FILTER_MODE_UI,
    ) == {"DEV1": FILTER_MODE_UI, "DEV2": FILTER_MODE_UI}


def test_device_grouping_values_supports_polish_and_english() -> None:
    assert "Grupuj po menu" in _device_grouping_values(ui_language="pl")[DEVICE_GROUPING_BY_MENU]
    assert "Group by menu" in _device_grouping_values(ui_language="en")[DEVICE_GROUPING_BY_MENU]


def test_build_modules_step_schema_contains_modules_and_filter_mode() -> None:
    schema = _build_modules_step_schema(
        module_choices=[("DEV1", "Boiler")],
        module_values={"DEV1": "Boiler"},
        default_modules=["DEV1"],
        module_filter_defaults={"DEV1": FILTER_MODE_UI},
        filter_values=_entity_filter_mode_values(ui_language="en"),
        grouping_values=_device_grouping_values(ui_language="en"),
    )

    parsed = schema(
        {
            CONF_MODULES: ["DEV1"],
            CONF_ENTITY_FILTER_MODE: FILTER_MODE_UI,
            CONF_DEVICE_GROUPING: DEVICE_GROUPING_FLAT,
        },
    )
    assert parsed[CONF_MODULES] == ["DEV1"]
    assert parsed[CONF_DEVICE_GROUPING] == DEFAULT_DEVICE_GROUPING


def test_extract_language_label_handles_string_and_dict() -> None:
    assert _extract_language_label(" English ", lang_id="en") == "English"
    assert _extract_language_label({"en": "Polski", "de": "Deutsch"}, lang_id="en") == "Polski"
    assert _extract_language_label({"de": "Deutsch"}, lang_id="en") == "Deutsch"
    assert _extract_language_label(123, lang_id="en") is None


def test_looks_like_language_code_label_detects_code_like_labels() -> None:
    assert _looks_like_language_code_label("en", lang_id="en") is True
    assert _looks_like_language_code_label("en US", lang_id="en") is True
    assert _looks_like_language_code_label("English", lang_id="en") is False


def test_language_label_from_row_prefers_native_name() -> None:
    row = {"nativeName": "Polski", "name": "pl"}
    assert _language_label_from_row(row, lang_id="pl") == "Polski"

    fallback_row = {"name": "pl"}
    assert _language_label_from_row(fallback_row, lang_id="pl") == "pl"


def test_build_modules_step_schema_rejects_invalid_filter_mode() -> None:
    schema = _build_modules_step_schema(
        module_choices=[("DEV1", "Boiler")],
        module_values={"DEV1": "Boiler"},
        default_modules=["DEV1"],
        module_filter_defaults={"DEV1": FILTER_MODE_UI},
        filter_values=_entity_filter_mode_values(ui_language="en"),
        grouping_values=_device_grouping_values(ui_language="en"),
    )
    try:
        schema({CONF_MODULES: ["DEV1"], CONF_ENTITY_FILTER_MODE: "bad", CONF_DEVICE_GROUPING: DEVICE_GROUPING_FLAT})
    except vol.Invalid:
        return
    raise AssertionError("Expected vol.Invalid for unknown filter mode")


def test_build_modules_step_schema_rejects_invalid_device_grouping() -> None:
    schema = _build_modules_step_schema(
        module_choices=[("DEV1", "Boiler")],
        module_values={"DEV1": "Boiler"},
        default_modules=["DEV1"],
        module_filter_defaults={"DEV1": FILTER_MODE_UI},
        filter_values=_entity_filter_mode_values(ui_language="en"),
        grouping_values=_device_grouping_values(ui_language="en"),
    )
    try:
        schema(
            {
                CONF_MODULES: ["DEV1"],
                CONF_ENTITY_FILTER_MODE: FILTER_MODE_UI,
                CONF_DEVICE_GROUPING: "by-area",
            }
        )
    except vol.Invalid:
        return
    raise AssertionError("Expected vol.Invalid for unknown device grouping")
