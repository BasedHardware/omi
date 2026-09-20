"""Focus sessions and stats must use the user's calendar day, not the UTC one.

`get_focus_sessions(date=...)` built its window as midnight-to-midnight UTC, so for a
user west of UTC "today" started in the middle of yesterday afternoon: an evening
session was counted on tomorrow and last night's sessions were counted as today's.
The day window now follows the zone the caller resolves for the user.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from database import focus_sessions


class _Query:
    def __init__(self, recorder):
        self._recorder = recorder

    def order_by(self, *args, **kwargs):
        return self

    def where(self, filter=None):
        self._recorder.append(filter)
        return self

    def offset(self, _value):
        return self

    def limit(self, _value):
        return self

    def stream(self):
        return []


@pytest.fixture
def filters(monkeypatch):
    recorded = []
    query = _Query(recorded)
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value = query
    monkeypatch.setattr(focus_sessions, "db", db)

    class _Filter:
        def __init__(self, field_path, op_string, value):
            self.field_path = field_path
            self.op_string = op_string
            self.value = value

    monkeypatch.setattr(focus_sessions, "FieldFilter", _Filter)
    return recorded


def _window(recorded):
    start = next(f.value for f in recorded if f.op_string == ">=")
    end = next(f.value for f in recorded if f.op_string == "<")
    return start, end


def test_the_day_window_starts_at_local_midnight(filters):
    focus_sessions.get_focus_sessions("uid", date="2026-09-20", tz=ZoneInfo("America/Los_Angeles"))

    start, end = _window(filters)
    assert start == datetime(2026, 9, 20, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert start.astimezone(timezone.utc) == datetime(2026, 9, 20, 7, tzinfo=timezone.utc)
    assert (end - start).total_seconds() == 24 * 3600


def test_an_evening_session_is_not_pushed_onto_the_next_day(filters):
    focus_sessions.get_focus_sessions("uid", date="2026-09-20", tz=ZoneInfo("America/Los_Angeles"))

    start, end = _window(filters)
    evening = datetime(2026, 9, 20, 18, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert start <= evening < end


def test_a_session_from_last_night_is_not_counted_as_today(filters):
    focus_sessions.get_focus_sessions("uid", date="2026-09-20", tz=ZoneInfo("Asia/Kolkata"))

    start, end = _window(filters)
    last_night = datetime(2026, 9, 19, 23, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert not (start <= last_night < end)


def test_no_zone_keeps_the_previous_utc_window(filters):
    focus_sessions.get_focus_sessions("uid", date="2026-09-20")

    start, _ = _window(filters)
    assert start == datetime(2026, 9, 20, tzinfo=timezone.utc)


def test_stats_label_the_local_day_when_no_date_is_given(filters, monkeypatch):
    stats = focus_sessions.get_focus_stats("uid", tz=ZoneInfo("Pacific/Kiritimati"))

    expected = datetime.now(ZoneInfo("Pacific/Kiritimati")).strftime("%Y-%m-%d")
    assert stats["date"] == expected
