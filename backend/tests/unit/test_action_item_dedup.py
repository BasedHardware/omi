"""
Tests for find_similar_action_items — the helper that powers semantic dedup
during conversation extraction.

Critical contract: the helper must (a) return [] when Pinecone isn't
configured, (b) filter matches below the threshold, (c) swallow Pinecone
exceptions and return [] (so a Pinecone outage degrades to "no dedup
context" rather than failing the whole conversation pipeline), and
(d) preserve match order from Pinecone (most-similar first).

database.vector_db binds ``embeddings`` at import (``from utils.llm.clients
import embeddings``) and ``from pinecone import Pinecone``, and its
transitive imports pull in database._client -> google.cloud.firestore and
firebase_admin.auth. Those heavy deps must be faked *before* the module is
exec'd. This is the sanctioned Tier-2 "fake must precede import" case: see
backend/docs/test_isolation.md and testing/import_isolation.load_module_fresh.
"""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


class _FakeFirestoreClient:
    def collection(self, *a, **kw):
        return MagicMock()

    def batch(self):
        return MagicMock()


@pytest.fixture(scope="module")
def vector_db():
    """Load a fresh database.vector_db against stubbed heavy deps.

    Stubs pinecone / firebase_admin / google.cloud.firestore (transitively
    pulled by database._client) and utils.llm.clients (binds ``embeddings``
    eagerly). The module is exec'd fresh inside the stub block so the fakes
    are active at import time. Everything is restored on teardown.
    """
    pinecone_stub = ModuleType("pinecone")
    pinecone_stub.Pinecone = MagicMock

    firebase_auth_stub = ModuleType("firebase_admin.auth")
    firebase_auth_stub.InvalidIdTokenError = type("InvalidIdTokenError", (Exception,), {})
    firebase_stub = ModuleType("firebase_admin")
    firebase_stub.auth = firebase_auth_stub

    google_pkg = ModuleType("google")
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []  # type: ignore[attr-defined]
    firestore_stub = ModuleType("google.cloud.firestore")
    firestore_stub.Client = _FakeFirestoreClient
    firestore_stub.ArrayUnion = MagicMock()
    firestore_stub.ArrayRemove = MagicMock()
    firestore_stub.Increment = MagicMock()
    firestore_stub.SERVER_TIMESTAMP = object()
    firestore_stub.DELETE_FIELD = object()
    firestore_stub.FieldFilter = MagicMock()
    firestore_stub.Query = MagicMock()
    google_cloud_pkg.firestore = firestore_stub

    clients_stub = ModuleType("utils.llm.clients")
    clients_stub.embeddings = MagicMock()

    fakes = {
        "pinecone": pinecone_stub,
        "firebase_admin": firebase_stub,
        "firebase_admin.auth": firebase_auth_stub,
        "google": google_pkg,
        "google.cloud": google_cloud_pkg,
        "google.cloud.firestore": firestore_stub,
        "utils.llm.clients": clients_stub,
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "action_item_dedup_vector_db",
            os.path.join(str(_BACKEND), "database", "vector_db.py"),
        )
        yield module


def _setup_mocks(
    monkeypatch,
    vector_db,
    *,
    index_none=False,
    query_response=None,
    embed_raises=None,
    query_raises=None,
):
    fake_index = MagicMock()
    if query_raises is not None:
        fake_index.query = MagicMock(side_effect=query_raises)
    else:
        fake_index.query = MagicMock(return_value=query_response or {'matches': []})
    monkeypatch.setattr(vector_db, 'index', None if index_none else fake_index)

    fake_embeddings = MagicMock()
    if embed_raises is not None:
        fake_embeddings.embed_query = MagicMock(side_effect=embed_raises)
    else:
        fake_embeddings.embed_query = MagicMock(return_value=[0.1, 0.2, 0.3])
    monkeypatch.setattr(vector_db, 'embeddings', fake_embeddings)
    return fake_index, fake_embeddings


class TestFindSimilarActionItems:
    def test_returns_empty_when_pinecone_not_configured(self, monkeypatch, vector_db):
        """No-op cleanly when Pinecone isn't initialized (tests, local dev, env-var-missing)."""
        _, fake_embeddings = _setup_mocks(monkeypatch, vector_db, index_none=True)

        result = vector_db.find_similar_action_items('uid-abc', 'buy milk')

        assert result == []
        # Embedding call must not happen — no point spending OpenAI tokens if Pinecone is down.
        fake_embeddings.embed_query.assert_not_called()

    def test_filters_below_threshold(self, monkeypatch, vector_db):
        """Threshold defines what counts as a candidate; everything below is dropped."""
        response = {
            'matches': [
                {'metadata': {'action_item_id': 'a1'}, 'score': 0.92},
                {'metadata': {'action_item_id': 'a2'}, 'score': 0.71},
                {'metadata': {'action_item_id': 'a3'}, 'score': 0.45},  # below default 0.6
                {'metadata': {'action_item_id': 'a4'}, 'score': 0.10},  # below default 0.6
            ]
        }
        _setup_mocks(monkeypatch, vector_db, query_response=response)

        result = vector_db.find_similar_action_items('uid-abc', 'buy milk')

        assert [r['action_item_id'] for r in result] == ['a1', 'a2']
        assert [r['score'] for r in result] == [0.92, 0.71]

    def test_threshold_param_is_respected(self, monkeypatch, vector_db):
        """Caller can tighten or loosen by passing threshold."""
        response = {
            'matches': [
                {'metadata': {'action_item_id': 'a1'}, 'score': 0.92},
                {'metadata': {'action_item_id': 'a2'}, 'score': 0.71},
                {'metadata': {'action_item_id': 'a3'}, 'score': 0.45},
            ]
        }
        _setup_mocks(monkeypatch, vector_db, query_response=response)

        result = vector_db.find_similar_action_items('uid-abc', 'buy milk', threshold=0.85)

        assert [r['action_item_id'] for r in result] == ['a1']

    def test_limit_param_passed_to_pinecone(self, monkeypatch, vector_db):
        """limit drives top_k on the Pinecone query."""
        fake_index, _ = _setup_mocks(monkeypatch, vector_db, query_response={'matches': []})

        vector_db.find_similar_action_items('uid-abc', 'buy milk', limit=25)

        kwargs = fake_index.query.call_args.kwargs
        assert kwargs['top_k'] == 25
        assert kwargs['namespace'] == vector_db.ACTION_ITEMS_NAMESPACE
        assert kwargs['filter'] == {'uid': 'uid-abc'}

    def test_pinecone_exception_returns_empty(self, monkeypatch, vector_db):
        """A Pinecone outage must not fail the conversation pipeline."""
        _setup_mocks(monkeypatch, vector_db, query_raises=RuntimeError('pinecone is down'))

        result = vector_db.find_similar_action_items('uid-abc', 'buy milk')

        assert result == []

    def test_embedding_exception_returns_empty(self, monkeypatch, vector_db):
        """An OpenAI embeddings outage must not fail the conversation pipeline."""
        _setup_mocks(monkeypatch, vector_db, embed_raises=RuntimeError('openai is down'))

        result = vector_db.find_similar_action_items('uid-abc', 'buy milk')

        assert result == []

    def test_empty_query_still_calls_pinecone(self, monkeypatch, vector_db):
        """The helper itself doesn't gate on empty query — that's the caller's concern.
        Embedding an empty string is harmless; Pinecone returns no matches; helper returns []."""
        _setup_mocks(monkeypatch, vector_db, query_response={'matches': []})

        result = vector_db.find_similar_action_items('uid-abc', '')

        assert result == []

    def test_preserves_pinecone_match_order(self, monkeypatch, vector_db):
        """Pinecone returns matches sorted by relevance; we must not re-order."""
        response = {
            'matches': [
                {'metadata': {'action_item_id': 'first'}, 'score': 0.95},
                {'metadata': {'action_item_id': 'second'}, 'score': 0.85},
                {'metadata': {'action_item_id': 'third'}, 'score': 0.70},
            ]
        }
        _setup_mocks(monkeypatch, vector_db, query_response=response)

        result = vector_db.find_similar_action_items('uid-abc', 'something')

        assert [r['action_item_id'] for r in result] == ['first', 'second', 'third']

    def test_drops_matches_with_missing_action_item_id(self, monkeypatch, vector_db):
        """A malformed Pinecone match (missing/empty action_item_id metadata) must be
        dropped per-match, not poison the whole dedup context. Returning None as an id
        would crash get_action_items_by_ids downstream."""
        response = {
            'matches': [
                {'metadata': {'action_item_id': 'good-1'}, 'score': 0.90},
                {'metadata': {}, 'score': 0.85},  # missing action_item_id
                {'metadata': {'action_item_id': None}, 'score': 0.80},  # explicit None
                {'metadata': {'action_item_id': ''}, 'score': 0.75},  # empty string
                {'metadata': {'action_item_id': 'good-2'}, 'score': 0.70},
            ]
        }
        _setup_mocks(monkeypatch, vector_db, query_response=response)

        result = vector_db.find_similar_action_items('uid-abc', 'q')

        assert [r['action_item_id'] for r in result] == ['good-1', 'good-2']
        assert all(r['action_item_id'] for r in result)


class TestQueryConversationVectors:
    def test_start_date_only_builds_one_sided_filter(self, monkeypatch, vector_db):
        fake_index, fake_embeddings = _setup_mocks(
            monkeypatch,
            vector_db,
            query_response={'matches': [{'id': 'uid-abc-conv-1'}]},
        )

        result = vector_db.query_vectors('coffee', 'uid-abc', starts_at=100, ends_at=None, k=3)

        assert result == ['conv-1']
        fake_embeddings.embed_query.assert_called_once_with('coffee')
        kwargs = fake_index.query.call_args.kwargs
        assert kwargs['filter'] == {'uid': 'uid-abc', 'created_at': {'$gte': 100}}
        assert kwargs['top_k'] == 3

    def test_end_date_only_builds_one_sided_filter(self, monkeypatch, vector_db):
        fake_index, _ = _setup_mocks(monkeypatch, vector_db, query_response={'matches': []})

        assert vector_db.query_vectors('coffee', 'uid-abc', starts_at=None, ends_at=200) == []

        kwargs = fake_index.query.call_args.kwargs
        assert kwargs['filter'] == {'uid': 'uid-abc', 'created_at': {'$lte': 200}}

    def test_invalid_date_filter_returns_empty_without_embedding(self, monkeypatch, vector_db):
        fake_index, fake_embeddings = _setup_mocks(monkeypatch, vector_db, query_response={'matches': []})

        assert vector_db.query_vectors('coffee', 'uid-abc', starts_at=300, ends_at=200) == []

        fake_embeddings.embed_query.assert_not_called()
        fake_index.query.assert_not_called()
