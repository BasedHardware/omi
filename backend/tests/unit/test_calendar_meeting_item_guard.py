"""GET /v1/calendar/meetings/{id} must not 500 on a malformed stored meeting.

The single-item endpoint built CalendarMeetingContext(**meeting) unguarded, so a legacy or
malformed stored meeting 500'd the request. The list endpoint already skips such records; the
single-item path now treats a malformed meeting as unavailable (404), consistent with the list,
and logs only a safe id + the exception type (a ValidationError's str() would leak the meeting
title / participant emails / link / notes).

Test isolation: routers.calendar_meetings imports cleanly, so the test imports it normally,
patches the import-cheap db helper with monkeypatch.setattr, and calls the handler directly.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from datetime import datetime, timezone  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from routers import calendar_meetings as cm_mod  # noqa: E402
from models.calendar_context import CalendarMeetingContext  # noqa: E402


def _valid_meeting():
    return {
        'calendar_event_id': 'e1',
        'title': 'Standup',
        'start_time': datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc),
        'duration_minutes': 30,
    }


def test_get_meeting_returns_context(monkeypatch):
    monkeypatch.setattr(cm_mod.calendar_db, 'get_meeting', lambda uid, mid: _valid_meeting())
    result = cm_mod.get_calendar_meeting(meeting_id='e1', uid='u1')
    assert isinstance(result, CalendarMeetingContext)
    assert result.calendar_event_id == 'e1'


def test_get_meeting_malformed_returns_404_not_500(monkeypatch):
    # Missing required fields (title/start_time/duration_minutes) -> 404, not an unhandled 500.
    monkeypatch.setattr(cm_mod.calendar_db, 'get_meeting', lambda uid, mid: {'calendar_event_id': 'e2'})
    with pytest.raises(HTTPException) as ei:
        cm_mod.get_calendar_meeting(meeting_id='e2', uid='u1')
    assert ei.value.status_code == 404


def test_get_meeting_missing_returns_404(monkeypatch):
    monkeypatch.setattr(cm_mod.calendar_db, 'get_meeting', lambda uid, mid: None)
    with pytest.raises(HTTPException) as ei:
        cm_mod.get_calendar_meeting(meeting_id='nope', uid='u1')
    assert ei.value.status_code == 404
