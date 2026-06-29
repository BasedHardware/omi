"""get_user_goals must not crash when a goal document is missing created_at.

The active goals were sorted with ``key=lambda x: x.get('created_at') or ''``. Goals carry a
timezone-aware datetime in created_at, so as soon as one goal lacked the field the key mixed a
datetime with an empty string, and Python's sort raised ``TypeError: '<' not supported between
instances of 'str' and 'datetime'`` -- taking down every caller (the goals endpoint, chat context,
proactive notifications, the developer API). The fix falls back to a timezone-aware datetime.min,
matching the pattern already used in create_goal, so a missing date sorts first instead of crashing.

database.goals builds a Firestore client at import, so database._client is stubbed before import and
the query chain is replaced with a controllable mock.
"""

import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

_client_stub = types.ModuleType('database._client')
_client_stub.db = MagicMock(name='db')
sys.modules['database._client'] = _client_stub

import database.goals as goals  # noqa: E402

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


def _set_docs(docs):
    chain = goals.db.collection.return_value.document.return_value.collection.return_value
    chain.where.return_value.limit.return_value.stream.return_value = docs


def test_get_user_goals_handles_goal_missing_created_at():
    # One goal with a later date, one with no created_at at all, one with an earlier date.
    docs = [
        _Doc('g_late', {'id': 'g_late', 'created_at': BASE.replace(day=3), 'is_active': True}),
        _Doc('g_missing', {'id': 'g_missing', 'is_active': True}),
        _Doc('g_early', {'id': 'g_early', 'created_at': BASE.replace(day=1), 'is_active': True}),
    ]
    _set_docs(docs)

    result = goals.get_user_goals('uid1')

    # No TypeError, and ascending order with the missing-date goal first (datetime.min fallback).
    assert [g['id'] for g in result] == ['g_missing', 'g_early', 'g_late']


def test_get_user_goals_all_dated_orders_ascending():
    docs = [
        _Doc('b', {'id': 'b', 'created_at': BASE.replace(day=2), 'is_active': True}),
        _Doc('a', {'id': 'a', 'created_at': BASE.replace(day=1), 'is_active': True}),
    ]
    _set_docs(docs)
    assert [g['id'] for g in goals.get_user_goals('uid1')] == ['a', 'b']
