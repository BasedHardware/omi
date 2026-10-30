"""Regression test for parse_event_times when dateTime is explicitly None alongside a valid date."""

from datetime import datetime, timezone

from utils.conversations.calendar_utils import parse_event_times


def test_parse_event_times_falls_back_to_date_when_datetime_is_none():
    event = {
        "start": {"dateTime": None, "date": "2026-08-18"},
        "end": {"dateTime": None, "date": "2026-08-19"},
    }
    start_dt, end_dt = parse_event_times(event)
    assert start_dt == datetime(2026, 8, 18, 0, 0, 0, tzinfo=timezone.utc)
    assert end_dt == datetime(2026, 8, 18, 23, 59, 59, tzinfo=timezone.utc)