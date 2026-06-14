"""Unit tests for the temporal-memory "constantly updated brain" + hybrid retrieval.

Covers the deterministic pieces that don't need Firestore/Pinecone/LLM:
  - BM25 + Reciprocal Rank Fusion (hybrid retrieval, point #2)
  - MemoryDB temporal lifecycle fields (valid_at / invalid_at / is_active, point #3)
"""

import os
import sys
from types import ModuleType
from datetime import datetime, timezone

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_test_secret_key_for_unit_tests_only_000000000000000000')

# Stub database._client so importing models.memories doesn't spin up Firestore.
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
database_pkg = sys.modules.setdefault('database', ModuleType('database'))
database_pkg.__path__ = [os.path.join(_BACKEND_DIR, 'database')]
_client_stub = ModuleType('database._client')
_client_stub.document_id_from_seed = lambda seed: 'id-' + str(abs(hash(seed)) % (10**12))
sys.modules['database._client'] = _client_stub

from utils.retrieval.hybrid import bm25_scores, rrf_rerank  # noqa: E402
from models.memories import Memory, MemoryDB, MemoryCategory  # noqa: E402


class TestBM25:
    def test_exact_keyword_match_scores_highest(self):
        docs = [
            "the user phone number is 12345",
            "the user likes hiking",
            "favorite food is pizza",
        ]
        scores = bm25_scores("phone number", docs)
        assert len(scores) == 3
        assert scores[0] == max(scores) > 0
        assert scores[1] == 0.0 and scores[2] == 0.0

    def test_empty_docs(self):
        assert bm25_scores("anything", []) == []

    def test_no_query_term_match(self):
        assert bm25_scores("zzz", ["hello world"]) == [0.0]


class TestRRF:
    def test_keyword_lifts_buried_vector_hit(self):
        # Vector order is a, b, c (c last). The keyword query matches only c, so fusion
        # must lift c above b — proof the keyword signal is actually applied.
        candidates = [
            {'id': 'a', 'content': 'user enjoys hiking and trails'},
            {'id': 'b', 'content': 'user likes pizza'},
            {'id': 'c', 'content': 'user phone number is 415 555 1234'},
        ]
        out = rrf_rerank("phone number", candidates, limit=3)
        ids = [o['id'] for o in out]
        assert ids.index('c') < ids.index('b')
        assert all('_hybrid_score' in o for o in out)

    def test_limit_truncates(self):
        cands = [{'id': str(i), 'content': f'memory number {i}'} for i in range(10)]
        assert len(rrf_rerank("memory", cands, limit=3)) == 3

    def test_does_not_mutate_input(self):
        cands = [{'id': 'a', 'content': 'x'}]
        rrf_rerank("x", cands, 1)
        assert '_hybrid_score' not in cands[0]

    def test_empty(self):
        assert rrf_rerank("q", [], 5) == []


class TestMemoryLifecycle:
    def _bare(self, **over):
        base = dict(
            id='x',
            uid='u',
            content='c',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        base.update(over)
        return MemoryDB(**base)

    def test_new_memory_defaults_to_active(self):
        m = self._bare()
        assert m.invalid_at is None
        assert m.superseded_by is None
        assert m.is_active is True

    def test_from_memory_sets_valid_at_and_active(self):
        mem = Memory(content='Loves ice cream', category=MemoryCategory.system)
        db = MemoryDB.from_memory(mem, uid='u', conversation_id='conv1', manually_added=False)
        assert db.valid_at is not None
        assert db.invalid_at is None
        assert db.is_active is True

    def test_invalidated_memory_is_not_active(self):
        m = self._bare(invalid_at=datetime.now(timezone.utc), superseded_by='y')
        assert m.is_active is False
        assert m.superseded_by == 'y'
