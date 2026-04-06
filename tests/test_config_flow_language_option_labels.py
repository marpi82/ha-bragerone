"""Tests for config-flow language option label formatting."""

from __future__ import annotations

from custom_components.habragerone.config_flow import _format_language_option_label


def test_format_language_option_label_drops_ascii_code_prefix() -> None:
    assert _format_language_option_label(label_base="Polski", flag="pl") == "Polski"
    assert _format_language_option_label(label_base="Deutsch", flag="de") == "Deutsch"


def test_format_language_option_label_keeps_emoji_like_marker() -> None:
    assert _format_language_option_label(label_base="Polski", flag="🇵🇱") == "🇵🇱 Polski"
