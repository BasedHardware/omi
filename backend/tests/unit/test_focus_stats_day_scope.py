"""focus-stats reports one day, not the user's whole history.

get_focus_stats used to hand its optional date straight to
get_focus_sessions, which only applies a created_at window when a date is
actually given.  A request without one therefore aggregated every session
the user had ever recorded -- up to the 5000-row cap -- and returned the
total under a single date, so the first focus-stats read of an account
showed months of focus as though it had all happened today.
"""

from datetime import datetime, timezone

import database.focus_sessions as focus_db


def _capture(monkeypatch):
    """Record the date get_focus_stats scopes its query to."""
    seen = {}

    def fake_get_focus_sessions(uid, date=None, limit=100, offset=0):
        seen['date'] = date
        seen['limit'] = limit
        return []

    monkeypatch.setattr(focus_db, 'get_focus_sessions', fake_get_focus_sessions)
    return seen


def test_stats_without_a_date_query_one_day(monkeypatch):
    seen = _capture(monkeypatch)

    result = focus_db.get_focus_stats('uid-1')

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    # None here is the defect: it disables the created_at window entirely.
    assert seen['date'] == today
    assert result['date'] == today


def test_stats_with_a_date_query_that_date(monkeypatch):
    seen = _capture(monkeypatch)

    result = focus_db.get_focus_stats('uid-1', date='2026-03-09')

    assert seen['date'] == '2026-03-09'
    assert result['date'] == '2026-03-09'


def test_reported_date_matches_the_day_queried(monkeypatch):
    """The label and the window must never disagree -- that pairing is what
    made the old behaviour read as a plausible daily figure rather than an
    obvious error."""
    seen = _capture(monkeypatch)

    result = focus_db.get_focus_stats('uid-1')

    assert result['date'] == seen['date']
