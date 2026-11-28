"""Unit tests for calendar_render.py.

Verifies None start/end guarding, dateTime fallback, all-day multi-day ranges,
attendee sanitization, and description truncation notes (issue #23130).
"""

from zoneinfo import ZoneInfo

from utils.model_text import DisplayClock
from utils.retrieval.tools.calendar_render import all_day_date, render_calendar_event


def _utc_clock() -> DisplayClock:
    return DisplayClock(tz=ZoneInfo("UTC"), name="UTC")


def test_all_day_date_none_and_invalid():
    clock = _utc_clock()
    assert all_day_date(None, clock) is None
    assert all_day_date("", clock) is None
    assert all_day_date("   ", clock) is None
    assert all_day_date("not-a-date", clock) is None
    valid = all_day_date("2026-10-21", clock)
    assert valid is not None
    assert valid[0].isoformat() == "2026-10-21"


def test_render_calendar_event_none_start_and_end():
    clock = _utc_clock()
    event = {
        "summary": "Team Sync",
        "start": None,
        "end": None,
        "attendees": [None, "user@example.com", {"displayName": "Alice", "email": "alice@example.com"}],
    }
    rendered = render_calendar_event(event, 1, clock)
    assert "Team Sync" in rendered
    assert "When: unknown time (event timestamp could not be parsed)" in rendered
    assert "Alice <alice@example.com>" in rendered
    assert "user@example.com" in rendered
    assert "None" not in rendered


def test_render_calendar_event_valid_datetime_and_missing_end():
    clock = _utc_clock()
    event = {
        "summary": "Keynote",
        "start": {"dateTime": "2026-10-21T14:00:00Z"},
        "end": {"dateTime": "2026-10-21T15:00:00Z"},
    }
    rendered = render_calendar_event(event, 2, clock)
    assert "Keynote" in rendered
    assert "When:" in rendered
    assert "unknown time" not in rendered

    # Missing end dateTime falls back cleanly to unknown time
    event_no_end = {
        "summary": "Incomplete Event",
        "start": {"dateTime": "2026-10-21T14:00:00Z"},
        "end": {},
    }
    rendered_no_end = render_calendar_event(event_no_end, 3, clock)
    assert "When: unknown time (event timestamp could not be parsed)" in rendered_no_end


def test_render_calendar_event_all_day_and_description_truncation():
    clock = _utc_clock()
    long_desc = "A" * 150
    event = {
        "summary": "Offsite",
        "start": {"date": "2026-10-21"},
        "end": {"date": "2026-10-24"},
        "description": long_desc,
    }
    rendered = render_calendar_event(event, 4, clock)
    assert "When: all day," in rendered
    assert "–" in rendered
    assert "Showing 100 of 150 description characters" in rendered
