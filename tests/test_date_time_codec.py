"""Tests for the in-tree DATE_TIME codec used until the library pin lands."""

from __future__ import annotations

from datetime import UTC, datetime

from custom_components.habragerone.date_time_codec import (
    format_server_date_time,
    parse_server_date_time,
)


def test_parse_and_format_round_trip_wire_string() -> None:
    parsed = parse_server_date_time("2512251200")
    assert parsed == datetime(2025, 12, 25, 12, 0)
    assert format_server_date_time(parsed) == "2512251200"
    aware = datetime(2025, 12, 25, 12, 0, tzinfo=UTC)
    assert parse_server_date_time(aware) == datetime(2025, 12, 25, 12, 0)
    assert format_server_date_time(2512251200) == "2512251200"
    assert format_server_date_time(2512251200.0) == "2512251200"


def test_parse_display_form_and_unset_sentinel() -> None:
    assert parse_server_date_time("2025/12/25 12:00") == datetime(2025, 12, 25, 12, 0)
    assert parse_server_date_time("0001011200") is None
    assert format_server_date_time("0001011200") == "0001011200"
    assert format_server_date_time("2512251200") == "2512251200"
    assert parse_server_date_time("25122512") is None
    assert parse_server_date_time("not-a-date") is None


def test_format_rejects_empty_and_bool() -> None:
    assert format_server_date_time("") is None
    assert format_server_date_time("   ") is None
    assert format_server_date_time(None) is None
    assert format_server_date_time(True) is None
    assert parse_server_date_time(True) is None
    assert parse_server_date_time(None) is None
    assert format_server_date_time("2025/13/40 99:99") is None
    assert format_server_date_time("abcdefghij") is None
    assert parse_server_date_time("2513139999") is None  # invalid month/day/time digits
    assert format_server_date_time("2513139999") is None
