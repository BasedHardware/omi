"""GET /v1/users/recaps/{period}: weekly and monthly recaps (#4468).

The route resolves the period in the user's timezone, reads the daily recaps for
it and the period before in one bounded query, ranks people from the period's
conversations, and fails open (without people) if that scan breaks.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from routers import recaps as recaps_mod

UID = 'u1'


def _summary(day: str, conversations: int, minutes: int):
    return {
        'id': f'sum-{day}',
        'date': day,
        'stats': {'total_conversations': conversations, 'total_duration_minutes': minutes},
    }


def _conversation(person_id: str, seconds: float):
    return {
        'id': f'c-{person_id}',
        'started_at': datetime(2026, 9, 30, 15, tzinfo=timezone.utc),
        'transcript_segments': [{'person_id': person_id, 'start': 0.0, 'end': seconds, 'text': 'hi'}],
    }


@pytest.fixture
def deps(monkeypatch):
    calls = {}
    summaries = MagicMock(
        return_value=[
            _summary('2026-10-01', 6, 120),
            _summary('2026-09-28', 3, 50),
            _summary('2026-09-24', 4, 90),
        ]
    )

    def people_scan(uid, *, start_date, end_date, budget):
        calls['people_scan'] = (uid, start_date, end_date)
        return iter([_conversation('p-sam', 300.0), _conversation('p-ana', 60.0)])

    monkeypatch.setattr(recaps_mod.notification_db, 'get_user_time_zone', lambda _uid: 'America/New_York')
    monkeypatch.setattr(recaps_mod.daily_summaries_db, 'get_daily_summaries', summaries)
    monkeypatch.setattr(recaps_mod, 'recap_people_scan', people_scan)
    monkeypatch.setattr(
        recaps_mod.users_db, 'get_people', lambda _uid: [{'id': 'p-sam', 'name': 'Sam'}, {'id': 'p-ana', 'name': 'Ana'}]
    )
    monkeypatch.setattr(recaps_mod, 'conversation_scan_budget', lambda _request, route: MagicMock(truncated=False))
    monkeypatch.setattr(recaps_mod, 'local_today', lambda _tz: date(2026, 10, 4))
    return summaries, calls


def _get(period='week', day=None):
    return recaps_mod.get_period_recap(request=MagicMock(), period=period, date=day, uid=UID)


def test_week_recap_reads_both_periods_in_one_query_and_ranks_people(deps):
    summaries, calls = deps

    recap = _get('week', '2026-10-01')

    summaries.assert_called_once_with(UID, limit=62, offset=0, start_date='2026-09-21', end_date='2026-10-04')
    assert (recap.start_date, recap.end_date) == ('2026-09-28', '2026-10-04')
    assert recap.stats.total_conversations == 9
    assert recap.previous.total_conversations == 4
    assert recap.busiest_day.date == '2026-10-01'
    assert [(p.name, p.talk_minutes) for p in recap.top_people] == [('Sam', 5), ('Ana', 1)]
    assert calls['people_scan'] == (
        UID,
        datetime(2026, 9, 28, 4, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 5, 3, 59, 59, 999999, tzinfo=timezone.utc),
    )


def test_month_recap_defaults_to_the_current_month_in_the_users_timezone(deps):
    summaries, _ = deps

    recap = _get('month')

    assert (recap.start_date, recap.end_date) == ('2026-10-01', '2026-10-31')
    assert summaries.call_args.kwargs['start_date'] == '2026-09-01'


@pytest.mark.parametrize('day', ['2026-10-05', '2026-13-01', 'yesterday'])
def test_future_or_malformed_dates_are_rejected(deps, day):
    with pytest.raises(HTTPException) as error:
        _get('week', day)

    assert error.value.status_code == 422


def test_unknown_period_is_rejected(deps):
    with pytest.raises(HTTPException) as error:
        _get('year')

    assert error.value.status_code == 422


def test_people_scan_failure_still_serves_the_recap_and_records_the_fallback(deps, monkeypatch):
    fallbacks = []

    def broken_scan(uid, **_kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(recaps_mod, 'recap_people_scan', broken_scan)
    monkeypatch.setattr(recaps_mod, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    recap = _get('week', '2026-10-01')

    assert recap.stats.total_conversations == 9
    assert recap.top_people == []
    assert fallbacks and fallbacks[0]['outcome'] == 'degraded'
