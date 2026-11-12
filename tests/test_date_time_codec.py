"""DATE_TIME codec via library re-export (``date_time_codec`` → ``pybragerone``)."""

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
    assert format_server_date_time(2512251200) == "2512251200"
    assert format_server_date_time(2512251200.0) == "2512251200"


def test_luxon_cutoff_not_python_percent_y() -> None:
    """``yy`` 61-68 must follow Luxon cutoff 60 (1961-1968), not Python ``%y``."""
    assert parse_server_date_time("6101011200") == datetime(1961, 1, 1, 12, 0)
    assert parse_server_date_time("6801011200") == datetime(1968, 1, 1, 12, 0)
    assert format_server_date_time(datetime(1961, 1, 1, 12, 0)) == "6101011200"
    assert format_server_date_time(datetime(2061, 1, 1, 12, 0)) is None


def test_parse_naive_datetime_truncates_seconds() -> None:
    assert parse_server_date_time(datetime(2025, 12, 25, 12, 0, 45, 123)) == datetime(2025, 12, 25, 12, 0)


def test_aware_datetime_rejected() -> None:
    aware = datetime(2025, 12, 25, 12, 0, tzinfo=UTC)
    assert parse_server_date_time(aware) is None
    assert format_server_date_time(aware) is None


def test_parse_display_form_and_factory_default() -> None:
    assert parse_server_date_time("2025/12/25 12:00") == datetime(2025, 12, 25, 12, 0)
    assert parse_server_date_time("0001011200") == datetime(2000, 1, 1, 12, 0)
    assert parse_server_date_time(1011200) == datetime(2000, 1, 1, 12, 0)
    assert parse_server_date_time(1011200.0) == datetime(2000, 1, 1, 12, 0)
    assert parse_server_date_time("2000/01/01 12:00") == datetime(2000, 1, 1, 12, 0)
    assert format_server_date_time("0001011200") == "0001011200"
    assert format_server_date_time("1011200") == "0001011200"
    assert format_server_date_time(datetime(2000, 1, 1, 12, 0)) == "0001011200"
    assert format_server_date_time("2000/01/01 12:00") == "0001011200"
    assert format_server_date_time("2512251200") == "2512251200"
    assert parse_server_date_time("25122512") is None
    assert parse_server_date_time("12345678901") is None
    assert parse_server_date_time("not-a-date") is None


def test_format_rejects_empty_and_bool() -> None:
    assert format_server_date_time("") is None
    assert format_server_date_time("   ") is None
    assert format_server_date_time(None) is None
    assert format_server_date_time(True) is None
    assert parse_server_date_time(True) is None
    assert parse_server_date_time(None) is None
    assert parse_server_date_time("") is None
    assert parse_server_date_time("   ") is None
    assert format_server_date_time("2025/13/40 99:99") is None
    assert format_server_date_time("abcdefghij") is None
    assert parse_server_date_time("2513139999") is None
    assert format_server_date_time("2513139999") is None
    assert format_server_date_time(2503111430.5) is None
    assert format_server_date_time(-1) is None
    assert format_server_date_time(12345678901) is None
    assert format_server_date_time("12345678901") is None
    assert format_server_date_time(object()) is None
