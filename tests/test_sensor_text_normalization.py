"""Tests for sensor text-state normalization."""

from __future__ import annotations

from custom_components.habragerone.sensor import _normalize_text_state


def test_normalize_text_state_lowercases_first_letter() -> None:
    assert _normalize_text_state("Włączone") == "włączone"
    assert _normalize_text_state("Załączony") == "załączony"
    assert _normalize_text_state("Stop") == "stop"


def test_normalize_text_state_keeps_all_caps_enum_tags() -> None:
    assert _normalize_text_state("STOP") == "STOP"
    assert _normalize_text_state("STOP_BOILER") == "STOP_BOILER"
    assert _normalize_text_state("WORK") == "WORK"


def test_normalize_text_state_leaves_non_text_or_empty() -> None:
    assert _normalize_text_state(1) == 1
    assert _normalize_text_state("") == ""
    assert _normalize_text_state("  ") == ""
