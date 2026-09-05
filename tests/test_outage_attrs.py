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


def test_outage_state_attributes_live_down_for_s() -> None:
    attrs = outage_state_attributes({"down_since": 1_700_000_000.0, "reason": "ws", "last_down_for_s": None})
    assert attrs["down_since"] == 1_700_000_000.0
    assert attrs["reason"] == "ws"
    assert isinstance(attrs["down_for_s"], float)
    assert attrs["down_for_s"] >= 0.0


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
