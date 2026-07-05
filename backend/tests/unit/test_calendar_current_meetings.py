"""Unit tests for GET /v1/calendar/current-meetings (meetings in progress now).

routers.calendar_meetings imports cleanly, so the endpoint is tested directly with
patch.object on the calendar_db seam (no sys.modules mutation).
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

from datetime import datetime, timezone
from unittest.mock import patch

import database.calendar_meetings as calendar_db
from routers import calendar_meetings as cal_router


def _valid_record(event_id="evt1"):
    return {
        "calendar_event_id": event_id,
        "title": "Standup",
        "start_time": datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc),
        "duration_minutes": 30,
    }


def test_empty_returns_empty_and_uses_zero_width_window():
    with patch.object(calendar_db, "get_meetings_in_time_range", return_value=[]) as m:
        result = cal_router.get_current_meetings(uid="u1", at=None)
    assert result == []
    args = m.call_args[0]
    assert args[0] == "u1"
    assert args[1] == args[2]  # start == end (a zero-width "now" window)
    assert args[1].tzinfo == timezone.utc


def test_naive_at_is_treated_as_utc():
    naive = datetime(2026, 7, 5, 9, 30, 0)
    with patch.object(calendar_db, "get_meetings_in_time_range", return_value=[]) as m:
        cal_router.get_current_meetings(uid="u1", at=naive)
    passed = m.call_args[0][1]
    assert passed == naive.replace(tzinfo=timezone.utc)
    assert m.call_args[0][1] == m.call_args[0][2]


def test_aware_at_passes_through():
    aware = datetime(2026, 7, 5, 9, 30, 0, tzinfo=timezone.utc)
    with patch.object(calendar_db, "get_meetings_in_time_range", return_value=[]) as m:
        cal_router.get_current_meetings(uid="u1", at=aware)
    assert m.call_args[0][1] == aware


def test_valid_records_mapped_to_context():
    recs = [_valid_record("a"), _valid_record("b")]
    with patch.object(calendar_db, "get_meetings_in_time_range", return_value=recs):
        result = cal_router.get_current_meetings(uid="u1", at=None)
    assert [m.calendar_event_id for m in result] == ["a", "b"]


def test_malformed_record_is_skipped():
    recs = [_valid_record("ok"), {"title": "missing required fields"}]
    with patch.object(calendar_db, "get_meetings_in_time_range", return_value=recs):
        result = cal_router.get_current_meetings(uid="u1", at=None)
    assert [m.calendar_event_id for m in result] == ["ok"]
