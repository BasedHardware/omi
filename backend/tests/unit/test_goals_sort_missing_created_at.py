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

Regression guard added for PR #23293: ``get_user_goals`` must not push its ``limit`` into the
Firestore query. A query-level limit bounds the page in document-id order before the in-Python
achieved/abandoned filter runs, so a user whose first page is entirely ended goals silently
receives fewer than ``limit`` active goals. ``_DocIdOrderedQuery`` mimics that production
behaviour so the regression test below fails against the old implementation and pins the new one.
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
    """Wire the fake Firestore chain so this module is implementation-shape agnostic.

    ``get_user_goals`` streams the full active collection and bounds the result in Python since
    PR #23293, so production now exercises the direct ``where(...).stream()`` path. The old
    ``where(...).limit(...).stream()`` chain is wired in parallel so the tests that pin
    sort/coercion semantics keep passing on either call shape and only exercise the behaviour
    they are named after; the query-limit starvation case is pinned separately by
    ``_DocIdOrderedQuery`` below, which honours ``.limit`` the way production Firestore does.
    """
    chain = goals.db.collection.return_value.document.return_value.collection.return_value
    query = chain.where.return_value
    query.stream.return_value = docs  # post-#23293 shape: no query-level limit
    query.limit.return_value.stream.return_value = docs  # pre-#23293 shape (mock ignores the bound)


class _DocIdOrderedQuery:
    """Fake Firestore query that honours ``.limit(n)`` the way production does: the page is cut
    in document-id (list) order before any in-Python filtering can run. The MagicMock helper
    above ignores ``.limit`` entirely, which cannot pin the page-starvation regression."""

    def __init__(self, docs):
        self._docs = docs

    def limit(self, n):
        return _DocIdOrderedQuery(self._docs[:n])

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


def test_get_user_goals_query_limit_must_not_starve_active_goals_behind_ended_page(goals):
    """The doc-id-first page being all achieved/abandoned must not reduce the active set.

    Regression for PR #23293: the old implementation applied ``.limit(limit)`` at the Firestore
    query level, bounding the page in document-id order BEFORE the in-Python achieved/abandoned
    filter ran. A user whose first page contained only ended goals silently received fewer than
    ``limit`` active goals from every caller (proactive suggestions, chat context, the goals API).
    The fake query below honours ``.limit`` in doc-id order exactly like production Firestore, so
    this test fails against the old implementation (a page of three ended goals yields zero active
    goals) and pins the new one: stream the full active set, filter, oldest-first, then slice.
    """
    docs = [
        # Doc-id-ordered first page: entirely ended goals.
        _Doc('g1_achieved', {'id': 'g1_achieved', 'status': 'achieved', 'created_at': BASE.replace(day=1)}),
        _Doc('g2_abandoned', {'id': 'g2_abandoned', 'status': 'abandoned', 'created_at': BASE.replace(day=2)}),
        _Doc('g3_achieved', {'id': 'g3_achieved', 'status': 'achieved', 'created_at': BASE.replace(day=3)}),
        # Active goals live behind the ended page in doc-id order.
        _Doc('g4_active', {'id': 'g4_active', 'status': 'background', 'created_at': BASE.replace(day=4)}),
        _Doc('g5_active', {'id': 'g5_active', 'status': 'background', 'created_at': BASE.replace(day=5)}),
        _Doc('g6_active', {'id': 'g6_active', 'status': 'paused', 'created_at': BASE.replace(day=6)}),
    ]
    chain = goals.db.collection.return_value.document.return_value.collection.return_value
    saved_where = chain.where.return_value
    try:
        chain.where.side_effect = lambda **kwargs: _DocIdOrderedQuery(docs)

        result = goals.get_user_goals('uid1', limit=3)
    finally:
        # Restore the shared module-scoped mock so other tests in this module stay isolated.
        chain.where.side_effect = None
        chain.where.return_value = saved_where

    # All three active goals are returned despite sitting behind an all-ended doc-id page,
    # oldest-first. Under the old implementation this returned [] (page was all ended goals).
    assert [g['id'] for g in result] == ['g4_active', 'g5_active', 'g6_active']
