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
    query = chain.where.return_value
    query.stream.return_value = docs
    query.limit.return_value.stream.return_value = docs


class _DocIdOrderedQuery:
    """Fake Firestore query that streams in document-id order and honours .limit(n)."""

    def __init__(self, docs):
        self._docs = list(docs)

    def limit(self, count):
        return _DocIdOrderedQuery(self._docs[:count])

    def stream(self):
        return iter(self._docs)


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


def test_get_user_goals_does_not_drop_active_goals_behind_ended_first_page(goals):
    docs = [
        _Doc('g1_achieved', {'id': 'g1_achieved', 'status': 'achieved', 'is_active': True, 'created_at': BASE.replace(day=1)}),
        _Doc('g2_abandoned', {'id': 'g2_abandoned', 'status': 'abandoned', 'is_active': True, 'created_at': BASE.replace(day=2)}),
        _Doc('g3_achieved', {'id': 'g3_achieved', 'status': 'achieved', 'is_active': True, 'created_at': BASE.replace(day=3)}),
        _Doc('g4_active', {'id': 'g4_active', 'status': 'background', 'is_active': True, 'created_at': BASE.replace(day=4)}),
        _Doc('g5_active', {'id': 'g5_active', 'status': 'background', 'is_active': True, 'created_at': BASE.replace(day=5)}),
        _Doc('g6_active', {'id': 'g6_active', 'status': 'paused', 'is_active': True, 'created_at': BASE.replace(day=6)}),
    ]
    chain = goals.db.collection.return_value.document.return_value.collection.return_value
    saved_where = chain.where.return_value
    try:
        chain.where.side_effect = lambda **_kwargs: _DocIdOrderedQuery(docs)
        result = goals.get_user_goals('uid1', limit=3)
    finally:
        chain.where.side_effect = None
        chain.where.return_value = saved_where

    assert [g['id'] for g in result] == ['g4_active', 'g5_active', 'g6_active']


def test_get_user_goals_returns_oldest_active_goals_regardless_of_doc_id_order(goals):
    docs = [
        _Doc('goal_a', {'id': 'goal_a', 'status': 'background', 'is_active': True, 'created_at': BASE.replace(day=6)}),
        _Doc('goal_b', {'id': 'goal_b', 'status': 'background', 'is_active': True, 'created_at': BASE.replace(day=5)}),
        _Doc('goal_c', {'id': 'goal_c', 'status': 'background', 'is_active': True, 'created_at': BASE.replace(day=4)}),
        _Doc('goal_d', {'id': 'goal_d', 'status': 'background', 'is_active': True, 'created_at': BASE.replace(day=1)}),
        _Doc('goal_e', {'id': 'goal_e', 'status': 'background', 'is_active': True, 'created_at': BASE.replace(day=2)}),
        _Doc('goal_f', {'id': 'goal_f', 'status': 'background', 'is_active': True, 'created_at': BASE.replace(day=3)}),
    ]
    chain = goals.db.collection.return_value.document.return_value.collection.return_value
    saved_where = chain.where.return_value
    try:
        chain.where.side_effect = lambda **_kwargs: _DocIdOrderedQuery(docs)
        result = goals.get_user_goals('uid1', limit=3)
    finally:
        chain.where.side_effect = None
        chain.where.return_value = saved_where

    assert [g['id'] for g in result] == ['goal_d', 'goal_e', 'goal_f']
    assert goals.get_user_goals('uid1', limit=0) == []

