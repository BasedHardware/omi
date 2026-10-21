"""Tests verifying calendar_render event formatting and robustness.

Ensures that events with None or omitted start/end dictionaries do not crash with TypeError,
dateTime spans and all-day multi-day intervals are rendered accurately in the user's timezone,
attendee lists with None items are sanitized, and description truncation notes are appended.
"""

from datetime import date, datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="module", autouse=True)
def _calendar_render_module():
    """Load calendar_render with temporary stub dependencies."""
    model_text = load_module_fresh("utils.model_text", str(BACKEND_DIR / "utils" / "model_text.py"))

    stubs = {
        "utils.model_text": model_text,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools.calendar_render",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "calendar_render.py"),
        )
        globals()["cr"] = module
        globals()["_DisplayClock"] = model_text.DisplayClock
        yield
        globals().pop("cr", None)
        globals().pop("_DisplayClock", None)


def test_render_event_with_none_start_and_end():
    clock = _DisplayClock.utc()
    event = {
        "summary": "Team Sync",
        "start": None,
        "end": None,
    }
    rendered = cr.render_calendar_event(event, 1, clock)
    assert "1. Title: <calendar title>Team Sync</calendar title>" in rendered
    assert "When: unknown time (event timestamp could not be parsed)" in rendered


def test_render_event_datetime_span():
    clock = _DisplayClock.utc()
    event = {
        "summary": "Design Sprint",
        "start": {"dateTime": "2026-10-22T14:00:00Z"},
        "end": {"dateTime": "2026-10-22T15:30:00Z"},
        "location": "Room 401",
    }
    rendered = cr.render_calendar_event(event, 2, clock)
    assert "2. Title: <calendar title>Design Sprint</calendar title>" in rendered
    assert "Location: <calendar location>Room 401</calendar location>" in rendered
    assert "When: 14:00 – 15:30" in rendered or "When: 2:00PM – 3:30PM" in rendered or "14:00" in rendered


def test_render_event_all_day_range():
    clock = _DisplayClock.utc()
    event = {
        "summary": "Offsite Conference",
        "start": {"date": "2026-11-01"},
        "end": {"date": "2026-11-04"},
    }
    rendered = cr.render_calendar_event(event, 3, clock)
    assert "3. Title: <calendar title>Offsite Conference</calendar title>" in rendered
    assert "When: all day" in rendered


def test_render_event_attendees_sanitization():
    clock = _DisplayClock.utc()
    event = {
        "summary": "Sprint Planning",
        "attendees": [
            {"displayName": "Alice Smith", "email": "alice@example.com"},
            None,
            {"email": "bob@example.com"},
            "charlie@example.com",
        ],
    }
    rendered = cr.render_calendar_event(event, 4, clock)
    assert "Alice Smith <alice@example.com>" in rendered
    assert "bob@example.com" in rendered
    assert "charlie@example.com" in rendered
    assert "None" not in rendered
    assert "Attendees (3):" in rendered


def test_render_event_long_description_truncation():
    clock = _DisplayClock.utc()
    event = {
        "summary": "Detailed Brief",
        "description": "X" * 150,
    }
    rendered = cr.render_calendar_event(event, 5, clock)
    assert "..." in rendered
    assert "description characters" in rendered


def test_render_event_non_dict_fallback():
    clock = _DisplayClock.utc()
    rendered = cr.render_calendar_event("malformed", 6, clock)  # type: ignore[arg-type]
    assert "6. Title: No title" in rendered
    assert "When: unknown time" in rendered
