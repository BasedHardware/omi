"""Action-item completion streak: database.get_completion_streak and GET /v1/scores/streak.

The streak is a consecutive-day engagement metric over action-item completions, bucketed by
``completed_at`` in the caller's IANA time zone. A day counts when at least one non-deleted item
was completed that day. The current streak stays alive through today until the day ends (it anchors
on yesterday when nothing has been completed yet today), while the longest streak scans the window.

These tests drive the pure day-bucketing/counting logic through an injected fake Firestore client
(the ``firestore_client=`` seam), plus the endpoint's timezone validation. No Redis/Firestore/network.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import database.action_items as action_items_db
import routers.scores as scores


def _utc(year, month, day, hour=12):
    return datetime(year, month, day, hour, 0, tzinfo=timezone.utc)


class _FakeDoc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _FakeActionItems:
    """Minimal Firestore stand-in for collection().document().collection().where().stream().

    The test seeds only in-window docs, so the range filter is a no-op here.
    """

    def __init__(self, docs):
        self._docs = [_FakeDoc(d) for d in docs]

    def collection(self, _name):
        return self

    def document(self, _uid):
        return self

    def where(self, filter=None):
        return self

    def stream(self):
        return iter(self._docs)


def _item(completed_at, *, completed=True, deleted=False):
    return {'completed': completed, 'deleted': deleted, 'completed_at': completed_at}


def _streak(docs, *, tz='UTC', today='2026-06-15'):
    return action_items_db.get_completion_streak('u', tz=tz, today=today, firestore_client=_FakeActionItems(docs))


class TestCompletionStreak:
    def test_no_completed_items(self):
        assert _streak([]) == {
            'current_streak': 0,
            'longest_streak': 0,
            'completed_today': False,
            'last_completed_date': None,
        }

    def test_completed_today_and_prior_two_days(self):
        result = _streak([_item(_utc(2026, 6, 15)), _item(_utc(2026, 6, 14)), _item(_utc(2026, 6, 13))])
        assert result['current_streak'] == 3
        assert result['completed_today'] is True
        assert result['longest_streak'] == 3
        assert result['last_completed_date'] == '2026-06-15'

    def test_streak_alive_through_yesterday_when_today_empty(self):
        # Completed yesterday and the day before, nothing yet today -> still a live streak of 2.
        result = _streak([_item(_utc(2026, 6, 14)), _item(_utc(2026, 6, 13))])
        assert result['current_streak'] == 2
        assert result['completed_today'] is False
        assert result['last_completed_date'] == '2026-06-14'

    def test_gap_resets_current_but_longest_tracks_best(self):
        # 14,13 give current=2 (through yesterday); gap at 12; 11,10,9 give a longest run of 3.
        docs = [
            _item(_utc(2026, 6, 14)),
            _item(_utc(2026, 6, 13)),
            _item(_utc(2026, 6, 11)),
            _item(_utc(2026, 6, 10)),
            _item(_utc(2026, 6, 9)),
        ]
        result = _streak(docs)
        assert result['current_streak'] == 2
        assert result['longest_streak'] == 3

    def test_multiple_completions_same_day_count_once(self):
        docs = [_item(_utc(2026, 6, 15, 9)), _item(_utc(2026, 6, 15, 17)), _item(_utc(2026, 6, 14))]
        assert _streak(docs)['current_streak'] == 2

    def test_deleted_and_incomplete_items_ignored(self):
        docs = [
            _item(_utc(2026, 6, 15)),
            _item(_utc(2026, 6, 14), deleted=True),
            _item(_utc(2026, 6, 13), completed=False),
        ]
        result = _streak(docs)
        assert result['current_streak'] == 1
        assert result['completed_today'] is True

    def test_timezone_buckets_completed_at_to_local_day(self):
        # 2026-01-02T02:00Z is 2026-01-01 21:00 in America/New_York -> local day 2026-01-01.
        docs = [_item(datetime(2026, 1, 2, 2, 0, tzinfo=timezone.utc))]
        ny = _streak(docs, tz='America/New_York', today='2026-01-01')
        assert ny['completed_today'] is True
        assert ny['last_completed_date'] == '2026-01-01'
        # The same instant is 2026-01-02 in UTC.
        utc = _streak(docs, tz='UTC', today='2026-01-02')
        assert utc['last_completed_date'] == '2026-01-02'


class TestStreakEndpoint:
    def test_invalid_timezone_is_400(self):
        with pytest.raises(HTTPException) as ei:
            scores.get_streak(tz='Not/AZone', uid='u')
        assert ei.value.status_code == 400

    def test_endpoint_returns_helper_result(self):
        payload = {
            'current_streak': 4,
            'longest_streak': 9,
            'completed_today': True,
            'last_completed_date': '2026-06-15',
        }
        with patch.object(scores.action_items_db, 'get_completion_streak', return_value=payload) as helper:
            result = scores.get_streak(tz='America/Los_Angeles', uid='u1')
        assert result == payload
        helper.assert_called_once_with('u1', tz='America/Los_Angeles')
