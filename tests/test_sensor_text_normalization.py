"""Tests for sensor text-state normalization."""

from __future__ import annotations

from custom_components.habragerone.sensor import _normalize_text_state


def test_normalize_text_state_lowercases_first_letter() -> None:
    assert _normalize_text_state("Włączone") == "włączone"
    assert _normalize_text_state("Załączony") == "załączony"


def test_normalize_text_state_leaves_non_text_or_empty() -> None:
    assert _normalize_text_state(1) == 1
    assert _normalize_text_state("") == ""
    assert _normalize_text_state("  ") == ""

