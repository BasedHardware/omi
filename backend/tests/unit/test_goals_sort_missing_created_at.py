"""get_user_goals must not crash when a goal document is missing created_at.

The active goals were sorted with ``key=lambda x: x.get('created_at') or ''``. Goals carry a
timezone-aware datetime in created_at, so as soon as one goal lacked the field the key mixed a
datetime with an empty string, and Python's sort raised ``TypeError: '<' not supported between
instances of 'str' and 'datetime'`` -- taking down every caller (the goals endpoint, chat context,
proactive notifications, the developer API). The fix falls back to a timezone-aware datetime.min,
matching the pattern already used in create_goal, so a missing date sorts first instead of crashing.

database.goals reads through the neutral storage port (``_store()``); the tests bind a
``FakeDocumentStore`` to that seam and seed the user's goal collection directly.
"""

import os
from datetime import datetime, timezone

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import pytest

import database.goals as goals_module
from tests.store_fakes import FakeDocumentStore


@pytest.fixture
def goals(monkeypatch):
    """database.goals bound to an in-memory FakeDocumentStore through the ``_store()`` seam."""
    store = FakeDocumentStore()
    monkeypatch.setattr(goals_module, "_store", lambda: store)
    return goals_module


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _set_docs(goals, docs):
    store = goals._store()
    for data in docs:
        store.set(f"users/uid1/goals/{data['id']}", dict(data))


def test_get_user_goals_handles_goal_missing_created_at(goals):
    # One goal with a later date, one with no created_at at all, one with an earlier date.
    docs = [
        {'id': 'g_late', 'created_at': BASE.replace(day=3), 'is_active': True},
        {'id': 'g_missing', 'is_active': True},
        {'id': 'g_early', 'created_at': BASE.replace(day=1), 'is_active': True},
    ]
    _set_docs(goals, docs)

    result = goals.get_user_goals('uid1')

    # No TypeError, and ascending order with the missing-date goal first (datetime.min fallback).
    assert [g['id'] for g in result] == ['g_missing', 'g_early', 'g_late']


def test_get_user_goals_all_dated_orders_ascending(goals):
    docs = [
        {'id': 'b', 'created_at': BASE.replace(day=2), 'is_active': True},
        {'id': 'a', 'created_at': BASE.replace(day=1), 'is_active': True},
    ]
    _set_docs(goals, docs)
    assert [g['id'] for g in goals.get_user_goals('uid1')] == ['a', 'b']


def test_get_user_goals_handles_non_datetime_created_at(goals):
    # A legacy/manual goal whose created_at is a (truthy) ISO string must not crash the sort -- the
    # value is coerced to datetime.min and sorts first, rather than mixing str and datetime.
    docs = [
        {'id': 'g_dt', 'created_at': BASE.replace(day=2), 'is_active': True},
        {'id': 'g_str', 'created_at': '2026-01-05T00:00:00Z', 'is_active': True},
    ]
    _set_docs(goals, docs)
    assert [g['id'] for g in goals.get_user_goals('uid1')] == ['g_str', 'g_dt']
