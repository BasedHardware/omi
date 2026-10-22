"""Unit tests verifying get_user_goals filters terminal statuses and sorts oldest-first.

Addresses issue #22778:
get_user_goals previously applied .limit(limit) directly to the Firestore query without
an order_by('created_at'), returning a page in arbitrary document-id order. Filtering
achieved and abandoned goals after the query-level limit shortened the returned page, and
newer goals could displace older active goals simply due to document-id sorting.

The fix streams the active collection without a query-level limit, filters out terminal
statuses (achieved, abandoned), sorts oldest-first via _goal_created_at_sort_key, and then
slices [:limit].
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]
BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = dict(data)
        if 'id' not in self._data:
            self._data['id'] = doc_id

    def to_dict(self):
        return dict(self._data)


@pytest.fixture(scope="module")
def goals():
    """Load a fresh database.goals against a stubbed database._client + firestore chain."""
    client_stub = ModuleType("database._client")
    client_stub.db = MagicMock(name="db")

    firestore_stub = ModuleType("google.cloud.firestore")
    firestore_stub.FieldFilter = MagicMock()
    google_pkg = ModuleType("google")
    google_pkg.__path__ = []
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []

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


def _set_stream_docs(goals, docs):
    chain = goals.db.collection.return_value.document.return_value.collection.return_value
    chain.where.return_value.stream.return_value = docs
    chain.where.return_value.limit.return_value.stream.return_value = docs


def test_get_user_goals_returns_oldest_first_regardless_of_doc_order(goals):
    # Documents streamed in arbitrary doc ID order (newest first in stream)
    docs = [
        _Doc('g3', {'created_at': BASE.replace(day=3), 'is_active': True, 'status': 'in_progress'}),
        _Doc('g1', {'created_at': BASE.replace(day=1), 'is_active': True, 'status': 'in_progress'}),
        _Doc('g4', {'created_at': BASE.replace(day=4), 'is_active': True, 'status': 'in_progress'}),
        _Doc('g2', {'created_at': BASE.replace(day=2), 'is_active': True, 'status': 'in_progress'}),
    ]
    _set_stream_docs(goals, docs)

    # limit=3 should return the 3 oldest (g1, g2, g3), dropping g4
    result = goals.get_user_goals('user1', limit=3)
    assert [g['id'] for g in result] == ['g1', 'g2', 'g3']


def test_get_user_goals_filters_achieved_and_abandoned_without_truncating_page(goals):
    # First two documents are ended (achieved and abandoned)
    docs = [
        _Doc('g_achieved', {'created_at': BASE.replace(day=1), 'is_active': True, 'status': 'achieved'}),
        _Doc('g_abandoned', {'created_at': BASE.replace(day=2), 'is_active': True, 'status': 'abandoned'}),
        _Doc('g_act1', {'created_at': BASE.replace(day=3), 'is_active': True, 'status': 'active'}),
        _Doc('g_act2', {'created_at': BASE.replace(day=4), 'is_active': True, 'status': 'in_progress'}),
        _Doc('g_act3', {'created_at': BASE.replace(day=5), 'is_active': True, 'status': 'focused'}),
    ]
    _set_stream_docs(goals, docs)

    # limit=3 should not come back short; it should skip achieved & abandoned and return all 3 active ones
    result = goals.get_user_goals('user1', limit=3)
    assert len(result) == 3
    assert [g['id'] for g in result] == ['g_act1', 'g_act2', 'g_act3']


def test_get_user_goals_dateless_legacy_goals_sort_first(goals):
    docs = [
        _Doc('g_dated', {'created_at': BASE.replace(day=5), 'is_active': True, 'status': 'in_progress'}),
        _Doc('g_legacy', {'is_active': True, 'status': 'in_progress'}),
    ]
    _set_stream_docs(goals, docs)

    result = goals.get_user_goals('user1', limit=2)
    assert [g['id'] for g in result] == ['g_legacy', 'g_dated']


def test_get_user_goals_none_or_negative_limit_returns_all_active(goals):
    docs = [
        _Doc('g1', {'created_at': BASE.replace(day=1), 'is_active': True, 'status': 'in_progress'}),
        _Doc('g2', {'created_at': BASE.replace(day=2), 'is_active': True, 'status': 'in_progress'}),
        _Doc('g3', {'created_at': BASE.replace(day=3), 'is_active': True, 'status': 'in_progress'}),
    ]
    _set_stream_docs(goals, docs)

    result_none = goals.get_user_goals('user1', limit=None)
    assert len(result_none) == 3
    assert [g['id'] for g in result_none] == ['g1', 'g2', 'g3']

    result_neg = goals.get_user_goals('user1', limit=-1)
    assert len(result_neg) == 3
