"""
Tests for find_similar_action_items — the helper that powers semantic dedup
during conversation extraction.

Critical contract: the helper must (a) return [] when Pinecone isn't
configured, (b) filter matches below the threshold, (c) swallow Pinecone
exceptions and return [] (so a Pinecone outage degrades to "no dedup
context" rather than failing the whole conversation pipeline), and
(d) preserve match order from Pinecone (most-similar first).
"""

import sys
import types
from unittest.mock import MagicMock

# Stub heavy deps before importing vector_db. Same pattern as test_memories_batch.
for mod_name in [
    'pinecone',
    'firebase_admin',
    'firebase_admin.auth',
    'google',
    'google.cloud',
    'google.cloud.firestore',
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

sys.modules['pinecone'].Pinecone = MagicMock


class _FakeFirestoreClient:
    def collection(self, *a, **kw):
        return MagicMock()

    def batch(self):
        return MagicMock()


sys.modules['google.cloud.firestore'].Client = _FakeFirestoreClient
sys.modules['google.cloud.firestore'].ArrayUnion = MagicMock
sys.modules['google.cloud.firestore'].ArrayRemove = MagicMock
sys.modules['google.cloud.firestore'].Increment = MagicMock
sys.modules['google.cloud.firestore'].SERVER_TIMESTAMP = object()
sys.modules['google.cloud.firestore'].DELETE_FIELD = object()
sys.modules['google.cloud.firestore'].FieldFilter = MagicMock
sys.modules['google.cloud.firestore'].Query = MagicMock
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

if 'utils.llm.clients' not in sys.modules:
    clients_stub = types.ModuleType('utils.llm.clients')
    clients_stub.embeddings = MagicMock()
    sys.modules['utils.llm.clients'] = clients_stub


from database import vector_db  # noqa: E402


def _setup_mocks(monkeypatch, *, index_none=False, query_response=None, embed_raises=None, query_raises=None):
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
    def test_returns_empty_when_pinecone_not_configured(self, monkeypatch):
        """No-op cleanly when Pinecone isn't initialized (tests, local dev, env-var-missing)."""
        _, fake_embeddings = _setup_mocks(monkeypatch, index_none=True)

        result = vector_db.find_similar_action_items('uid-abc', 'buy milk')

        assert result == []
        # Embedding call must not happen — no point spending OpenAI tokens if Pinecone is down.
        fake_embeddings.embed_query.assert_not_called()

    def test_filters_below_threshold(self, monkeypatch):
        """Threshold defines what counts as a candidate; everything below is dropped."""
        response = {
            'matches': [
                {'metadata': {'action_item_id': 'a1'}, 'score': 0.92},
                {'metadata': {'action_item_id': 'a2'}, 'score': 0.71},
                {'metadata': {'action_item_id': 'a3'}, 'score': 0.45},  # below default 0.6
                {'metadata': {'action_item_id': 'a4'}, 'score': 0.10},  # below default 0.6
            ]
        }
        _setup_mocks(monkeypatch, query_response=response)

        result = vector_db.find_similar_action_items('uid-abc', 'buy milk')

        assert [r['action_item_id'] for r in result] == ['a1', 'a2']
        assert [r['score'] for r in result] == [0.92, 0.71]

    def test_threshold_param_is_respected(self, monkeypatch):
        """Caller can tighten or loosen by passing threshold."""
        response = {
            'matches': [
                {'metadata': {'action_item_id': 'a1'}, 'score': 0.92},
                {'metadata': {'action_item_id': 'a2'}, 'score': 0.71},
                {'metadata': {'action_item_id': 'a3'}, 'score': 0.45},
            ]
        }
        _setup_mocks(monkeypatch, query_response=response)

        result = vector_db.find_similar_action_items('uid-abc', 'buy milk', threshold=0.85)

        assert [r['action_item_id'] for r in result] == ['a1']

    def test_limit_param_passed_to_pinecone(self, monkeypatch):
        """limit drives top_k on the Pinecone query."""
        fake_index, _ = _setup_mocks(monkeypatch, query_response={'matches': []})

        vector_db.find_similar_action_items('uid-abc', 'buy milk', limit=25)

        kwargs = fake_index.query.call_args.kwargs
        assert kwargs['top_k'] == 25
        assert kwargs['namespace'] == vector_db.ACTION_ITEMS_NAMESPACE
        assert kwargs['filter'] == {'uid': 'uid-abc'}

    def test_pinecone_exception_returns_empty(self, monkeypatch):
        """A Pinecone outage must not fail the conversation pipeline."""
        _setup_mocks(monkeypatch, query_raises=RuntimeError('pinecone is down'))

        result = vector_db.find_similar_action_items('uid-abc', 'buy milk')

        assert result == []

    def test_embedding_exception_returns_empty(self, monkeypatch):
        """An OpenAI embeddings outage must not fail the conversation pipeline."""
        _setup_mocks(monkeypatch, embed_raises=RuntimeError('openai is down'))

        result = vector_db.find_similar_action_items('uid-abc', 'buy milk')

        assert result == []

    def test_empty_query_still_calls_pinecone(self, monkeypatch):
        """The helper itself doesn't gate on empty query — that's the caller's concern.
        Embedding an empty string is harmless; Pinecone returns no matches; helper returns []."""
        _setup_mocks(monkeypatch, query_response={'matches': []})

        result = vector_db.find_similar_action_items('uid-abc', '')

        assert result == []

    def test_preserves_pinecone_match_order(self, monkeypatch):
        """Pinecone returns matches sorted by relevance; we must not re-order."""
        response = {
            'matches': [
                {'metadata': {'action_item_id': 'first'}, 'score': 0.95},
                {'metadata': {'action_item_id': 'second'}, 'score': 0.85},
                {'metadata': {'action_item_id': 'third'}, 'score': 0.70},
            ]
        }
        _setup_mocks(monkeypatch, query_response=response)

        result = vector_db.find_similar_action_items('uid-abc', 'something')

        assert [r['action_item_id'] for r in result] == ['first', 'second', 'third']

    def test_drops_matches_with_missing_action_item_id(self, monkeypatch):
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
        _setup_mocks(monkeypatch, query_response=response)

        result = vector_db.find_similar_action_items('uid-abc', 'q')

        assert [r['action_item_id'] for r in result] == ['good-1', 'good-2']
        assert all(r['action_item_id'] for r in result)
