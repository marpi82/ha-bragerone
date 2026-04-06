"""Tests for language label extraction in config flow."""

from __future__ import annotations

from custom_components.habragerone.config_flow import _extract_lang_map_from_app_namespace


def test_extract_lang_map_from_app_namespace_direct_lang_dict() -> None:
    app_namespace = {
        "lang": {
            "pl": "Polski",
            "en": "English",
            "de": "Deutsch",
        }
    }

    result = _extract_lang_map_from_app_namespace(app_namespace)

    assert result == {"pl": "Polski", "en": "English", "de": "Deutsch"}


def test_extract_lang_map_from_app_namespace_nested_lang_dict() -> None:
    app_namespace = {
        "app": {
            "one": {
                "module": {"screen": {"boiler": "Kocioł"}},
            },
            "lang": {
                "es": "Español",
                "fr": "Français",
            },
        }
    }

    result = _extract_lang_map_from_app_namespace(app_namespace)

    assert result == {"es": "Español", "fr": "Français"}
