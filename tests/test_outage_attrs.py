"""Unit tests for connectivity outage attribute helpers."""

from __future__ import annotations

import types

from custom_components.habragerone.outage_attrs import extract_outage_fields, outage_state_attributes


def test_extract_outage_fields_from_event() -> None:
    event = types.SimpleNamespace(
        down_since=10.0,
        down_for_s=1.5,
        reason="disconnect",
        last_down_for_s=None,
        last_reason=None,
        unrelated=True,
    )
    assert extract_outage_fields(event) == {
        "down_since": 10.0,
        "down_for_s": 1.5,
        "reason": "disconnect",
        "last_down_for_s": None,
        "last_reason": None,
    }


def test_extract_outage_fields_from_mapping() -> None:
    assert extract_outage_fields(
        {
            "down_since": True,
            "down_for_s": 2,
            "reason": "",
            "last_down_for_s": 9,
            "last_reason": "ws",
        }
    ) == {
        "down_since": None,
        "down_for_s": 2.0,
        "reason": None,
        "last_down_for_s": 9.0,
        "last_reason": "ws",
    }


def test_outage_state_attributes_live_down_for_s() -> None:
    attrs = outage_state_attributes({"down_since": 1_700_000_000.0, "reason": "ws", "last_down_for_s": None})
    assert attrs["down_since"] == 1_700_000_000.0
    assert attrs["reason"] == "ws"
    assert isinstance(attrs["down_for_s"], float)
    assert attrs["down_for_s"] >= 0.0


def test_outage_state_attributes_hides_last_during_active_outage() -> None:
    """Prior-cycle last_* must not appear while down_since is set (Bugbot)."""
    attrs = outage_state_attributes(
        {
            "down_since": 1_700_000_000.0,
            "down_for_s": 3.0,
            "reason": "disconnect",
            "last_down_for_s": 99.0,
            "last_reason": "stop",
        }
    )
    assert attrs["reason"] == "disconnect"
    assert "last_down_for_s" not in attrs
    assert "last_reason" not in attrs


def test_outage_state_attributes_active_without_reason() -> None:
    attrs = outage_state_attributes({"down_since": 1_700_000_000.0, "reason": None})
    assert attrs["down_since"] == 1_700_000_000.0
    assert "reason" not in attrs
    assert "last_down_for_s" not in attrs


def test_outage_state_attributes_last_only_when_up() -> None:
    attrs = outage_state_attributes(
        {"down_since": None, "down_for_s": None, "reason": None, "last_down_for_s": 12.34, "last_reason": "disconnect"}
    )
    assert attrs == {"last_down_for_s": 12.3, "last_reason": "disconnect"}


def test_outage_state_attributes_empty() -> None:
    assert outage_state_attributes(None) == {}
    assert outage_state_attributes({}) == {}


def test_extract_and_attrs_reject_bool_and_empty_strings() -> None:
    event = types.SimpleNamespace(
        down_since=True,
        down_for_s=False,
        reason="",
        last_down_for_s=True,
        last_reason="",
    )
    assert extract_outage_fields(event) == {
        "down_since": None,
        "down_for_s": None,
        "reason": None,
        "last_down_for_s": None,
        "last_reason": None,
    }
    attrs = outage_state_attributes({"down_since": True, "reason": "", "last_down_for_s": False, "last_reason": ""})
    assert attrs == {}
