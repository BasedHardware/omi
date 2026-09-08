"""get_user_goals must not crash when a goal document is missing created_at.

The active goals were sorted with ``key=lambda x: x.get('created_at') or ''``. Goals carry a
timezone-aware datetime in created_at, so as soon as one goal lacked the field the key mixed a
datetime with an empty string, and Python's sort raised ``TypeError: '<' not supported between
instances of 'str' and 'datetime'`` -- taking down every caller (the goals endpoint, chat context,
proactive notifications, the developer API). The fix falls back to a timezone-aware datetime.min,
matching the pattern already used in create_goal, so a missing date sorts first instead of crashing.

database.goals binds ``db`` at import (``from database._client import db``), so the fake
``database._client`` must be active before the module is exec'd. This is the sanctioned
Tier-2 "fake must precede import" case: see backend/docs/test_isolation.md and
testing/import_isolation.load_module_fresh.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def goals():
    """Load a fresh database.goals against a stubbed database._client + firestore chain."""
    client_stub = ModuleType("database._client")
    client_stub.db = MagicMock(name="db")

    firestore_stub = ModuleType("google.cloud.firestore")
    firestore_stub.FieldFilter = MagicMock()
    google_pkg = ModuleType("google")
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []  # type: ignore[attr-defined]

    fv1_stub = ModuleType("google.cloud.firestore_v1")
    fv1_stub.FieldFilter = MagicMock()

    fakes = {
        "database._client": client_stub,
        "google": google_pkg,
        "google.cloud": google_cloud_pkg,
        "google.cloud.firestore": firestore_stub,
        "google.cloud.firestore_v1": fv1_stub,
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "database.goals",
            os.path.join(str(_BACKEND), "database", "goals.py"),
        )
        yield module


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


def _set_docs(goals, docs):
    chain = goals.db.collection.return_value.document.return_value.collection.return_value
    chain.where.return_value.limit.return_value.stream.return_value = docs


def test_get_user_goals_handles_goal_missing_created_at(goals):
    # One goal with a later date, one with no created_at at all, one with an earlier date.
    docs = [
        _Doc('g_late', {'id': 'g_late', 'created_at': BASE.replace(day=3), 'is_active': True}),
        _Doc('g_missing', {'id': 'g_missing', 'is_active': True}),
        _Doc('g_early', {'id': 'g_early', 'created_at': BASE.replace(day=1), 'is_active': True}),
    ]
    _set_docs(goals, docs)

    result = goals.get_user_goals('uid1')

    # No TypeError, and ascending order with the missing-date goal first (datetime.min fallback).
    assert [g['id'] for g in result] == ['g_missing', 'g_early', 'g_late']


def test_get_user_goals_all_dated_orders_ascending(goals):
    docs = [
        _Doc('b', {'id': 'b', 'created_at': BASE.replace(day=2), 'is_active': True}),
        _Doc('a', {'id': 'a', 'created_at': BASE.replace(day=1), 'is_active': True}),
    ]
    _set_docs(goals, docs)
    assert [g['id'] for g in goals.get_user_goals('uid1')] == ['a', 'b']


def test_get_user_goals_handles_non_datetime_created_at(goals):
    # A legacy/manual goal whose created_at is a (truthy) ISO string must not crash the sort -- the
    # value is coerced to datetime.min and sorts first, rather than mixing str and datetime.
    docs = [
        _Doc('g_dt', {'id': 'g_dt', 'created_at': BASE.replace(day=2), 'is_active': True}),
        _Doc('g_str', {'id': 'g_str', 'created_at': '2026-01-05T00:00:00Z', 'is_active': True}),
    ]
    _set_docs(goals, docs)
    assert [g['id'] for g in goals.get_user_goals('uid1')] == ['g_str', 'g_dt']
