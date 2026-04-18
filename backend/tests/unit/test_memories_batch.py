"""
Tests for the memories batch endpoint and its supporting Pinecone helper.

Regression goal: POST /v3/memories/batch must (a) compute embeddings in a
single batch call, (b) upsert all vectors in a single Pinecone request, and
(c) short-circuit cleanly when Pinecone is not configured. These properties
are what make the endpoint cheap enough to run under Cloud Armor without
fanning out N requests per memory.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

# Stub heavy deps before importing vector_db / routers.memories. These
# modules pull in `pinecone`, `google.cloud.firestore`, `firebase_admin`, and
# `utils.llm.clients.embeddings` at import time, none of which are available
# (or desirable) in the unit test environment.
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

# Stub `utils.llm.clients.embeddings` only. Don't overwrite `utils` or
# `utils.llm` as packages — other real submodules (utils.rate_limit_config,
# utils.other.endpoints) must remain importable.
if 'utils.llm.clients' not in sys.modules:
    clients_stub = types.ModuleType('utils.llm.clients')
    clients_stub.embeddings = MagicMock()
    sys.modules['utils.llm.clients'] = clients_stub


from database import vector_db  # noqa: E402


class TestUpsertMemoryVectorsBatch:
    def _setup_mocks(self, monkeypatch, *, index_none=False):
        fake_index = MagicMock()
        fake_index.upsert = MagicMock(return_value={'upserted_count': 2})
        monkeypatch.setattr(vector_db, 'index', None if index_none else fake_index)

        fake_embeddings = MagicMock()
        fake_embeddings.embed_documents = MagicMock(
            side_effect=lambda texts: [[0.1 * i, 0.2 * i] for i, _ in enumerate(texts, start=1)]
        )
        monkeypatch.setattr(vector_db, 'embeddings', fake_embeddings)
        return fake_index, fake_embeddings

    def test_batch_upsert_uses_single_embed_and_single_upsert(self, monkeypatch):
        """The whole point of the helper: one embed call + one upsert call."""
        fake_index, fake_embeddings = self._setup_mocks(monkeypatch)

        items = [
            {'memory_id': 'm1', 'content': 'apple', 'category': 'manual'},
            {'memory_id': 'm2', 'content': 'banana', 'category': 'manual'},
            {'memory_id': 'm3', 'content': 'cherry', 'category': 'interesting'},
        ]

        written = vector_db.upsert_memory_vectors_batch('uid-abc', items)

        assert written == 3
        # Exactly one embeddings call, with all three contents.
        fake_embeddings.embed_documents.assert_called_once_with(['apple', 'banana', 'cherry'])
        # Exactly one Pinecone upsert, with all three vectors.
        fake_index.upsert.assert_called_once()
        kwargs = fake_index.upsert.call_args.kwargs
        assert kwargs['namespace'] == vector_db.MEMORIES_NAMESPACE
        vectors = kwargs['vectors']
        assert [v['id'] for v in vectors] == ['uid-abc-m1', 'uid-abc-m2', 'uid-abc-m3']
        assert [v['metadata']['memory_id'] for v in vectors] == ['m1', 'm2', 'm3']
        assert [v['metadata']['category'] for v in vectors] == ['manual', 'manual', 'interesting']
        assert all(v['metadata']['uid'] == 'uid-abc' for v in vectors)

    def test_batch_upsert_empty_list_is_noop(self, monkeypatch):
        fake_index, fake_embeddings = self._setup_mocks(monkeypatch)

        written = vector_db.upsert_memory_vectors_batch('uid-abc', [])

        assert written == 0
        fake_embeddings.embed_documents.assert_not_called()
        fake_index.upsert.assert_not_called()

    def test_batch_upsert_skips_when_pinecone_not_configured(self, monkeypatch):
        """Helper must no-op cleanly when Pinecone isn't configured (tests, local dev)."""
        _, fake_embeddings = self._setup_mocks(monkeypatch, index_none=True)

        written = vector_db.upsert_memory_vectors_batch(
            'uid-abc',
            [{'memory_id': 'm1', 'content': 'hello', 'category': 'manual'}],
        )

        assert written == 0
        fake_embeddings.embed_documents.assert_not_called()


class TestBatchMemoriesRateLimitPolicy:
    def test_policy_exists_with_expected_limits(self):
        """Guardrail so the policy isn't accidentally dropped from the config."""
        from utils.rate_limit_config import RATE_POLICIES

        assert 'memories:batch' in RATE_POLICIES
        max_requests, window = RATE_POLICIES['memories:batch']
        # Intentionally tight — each request can create up to 100 memories.
        assert max_requests == 30
        assert window == 3600


class TestBatchMemoriesRequestValidation:
    """
    Pydantic-level validation on the batch request model.

    We can't import `routers.memories` in a unit test without pulling in the
    whole Firestore stack, so we parse the max cap out of the source file.
    Ugly but durable: if someone bumps MEMORIES_BATCH_MAX, the test follows.
    """

    @staticmethod
    def _module_max() -> int:
        import os
        import re

        path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'memories.py')
        with open(os.path.abspath(path), 'r') as f:
            content = f.read()
        m = re.search(r'MEMORIES_BATCH_MAX\s*=\s*(\d+)', content)
        assert m, "MEMORIES_BATCH_MAX constant not found in routers/memories.py"
        return int(m.group(1))

    def _build_request_model(self, max_length: int):
        """Reconstruct BatchMemoriesRequest locally so we can test the validator
        without importing routers.memories (which pulls in google.cloud.firestore)."""
        from pydantic import BaseModel, Field
        from typing import List as _List

        from models.memories import Memory

        class _BatchMemoriesRequest(BaseModel):
            memories: _List[Memory] = Field(max_length=max_length)

        return _BatchMemoriesRequest

    def test_module_exposes_expected_max(self):
        """Hard-coded expectation: if this drops below 100 we want a signal."""
        assert self._module_max() == 100

    def test_request_accepts_up_to_max(self):
        max_len = self._module_max()
        BatchMemoriesRequest = self._build_request_model(max_len)

        memories = [{'content': f'memory {i}', 'visibility': 'private'} for i in range(max_len)]
        req = BatchMemoriesRequest(memories=memories)
        assert len(req.memories) == max_len

    def test_request_rejects_over_max(self):
        from pydantic import ValidationError

        max_len = self._module_max()
        BatchMemoriesRequest = self._build_request_model(max_len)

        memories = [{'content': f'memory {i}', 'visibility': 'private'} for i in range(max_len + 1)]
        with pytest.raises(ValidationError):
            BatchMemoriesRequest(memories=memories)

    def test_empty_batch_is_allowed(self):
        """Empty batch is a legal no-op — endpoint returns created_count=0."""
        BatchMemoriesRequest = self._build_request_model(self._module_max())
        req = BatchMemoriesRequest(memories=[])
        assert req.memories == []
