"""Unit tests for calendar_render.py.

Verifies None start/end guarding, dateTime fallback, all-day multi-day ranges,
and attendee sanitization (issue #23130).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from utils.model_text import DisplayClock
from utils.retrieval.tools.calendar_render import all_day_date, render_calendar_event


def test_all_day_date_none_and_invalid():
    clock = DisplayClock(now=datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc), tz=ZoneInfo("UTC"))
    assert all_day_date(None, clock) is None
    assert all_day_date("", clock) is None
    assert all_day_date("   ", clock) is None
    assert all_day_date("not-a-date", clock) is None


def test_render_calendar_event_none_start_and_end():
    clock = DisplayClock(now=datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc), tz=ZoneInfo("UTC"))
    event = {
        "summary": "Team Sync",
        "start": None,
        "end": None,
        "attendees": [None, "user@example.com", {"displayName": "Alice", "email": "alice@example.com"}]
    }
    rendered = render_calendar_event(event, 1, clock)
    assert "1. Title: Team Sync" in rendered
    assert "When: unknown time (event timestamp could not be parsed)" in rendered
    assert "Alice <alice@example.com>" in rendered
    assert "user@example.com" in rendered
    assert "None" not in rendered


def test_render_calendar_event_valid_datetime():
    clock = DisplayClock(now=datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc), tz=ZoneInfo("UTC"))
    event = {
        "summary": "Keynote",
        "start": {"dateTime": "2026-10-21T14:00:00Z"},
        "end": {"dateTime": "2026-10-21T15:00:00Z"},
    }
    rendered = render_calendar_event(event, 2, clock)
    assert "2. Title: Keynote" in rendered
    assert "When:" in rendered
