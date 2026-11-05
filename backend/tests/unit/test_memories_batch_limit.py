"""Deterministic reproduction test for Firestore 500-write batch limit in database/memories.py.

Firestore restricts WriteBatch operations to at most 500 mutations per commit.
When attempting to delete or mutate more than 500 documents in a single batch,
Firestore raises:
`google.api_core.exceptions.InvalidArgument: 400 Transaction or write batch too large`.

In database/memories.py:
Batch deletion operations must chunk writes into batches of <= 500 items
(e.g., `for i in range(0, len(items), 500): chunk = items[i : i + 500]`)
so that a user with > 500 memories can delete them without crashing.

This test mocks the Firestore client 100% offline and verifies:
1. Batch operations with > 500 items without chunking fail deterministically with InvalidArgument (RED phase).
2. Chunked batch deletions split operations into batches of <= 500 items and succeed (GREEN phase).
3. Under-limit batch deletions (e.g. 10 items) commit once.
4. Empty batch deletion requests return immediately as a no-op without creating or committing a batch.
"""

import os
from typing import Any, List

import pytest
from google.api_core.exceptions import InvalidArgument

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.memories as memories

_FIRESTORE_BATCH_LIMIT = 500


class _BatchLimitEnforcingBatch:
    """Mock Firestore batch that enforces the 500 operations-per-commit limit."""

    def __init__(self, commit_sink: List[int]):
        self._commit_sink = commit_sink
        self.operations = 0

    def delete(self, reference: Any) -> None:
        self.operations += 1

    def update(self, reference: Any, data: Any) -> None:
        self.operations += 1

    def set(self, reference: Any, data: Any) -> None:
        self.operations += 1

    def commit(self) -> None:
        if self.operations > _FIRESTORE_BATCH_LIMIT:
            raise InvalidArgument(
                f"400 Transaction or write batch too large: maximum {_FIRESTORE_BATCH_LIMIT} operations allowed, got {self.operations}"
            )
        self._commit_sink.append(self.operations)


class _FakeDoc:
    def __init__(self, doc_id: str):
        self.id = doc_id
        self.reference = f"ref-{doc_id}"


class _FakeDocument:
    def __init__(self, doc_id: str, collection: "_FakeCollection"):
        self.id = doc_id
        self.reference = f"ref-{doc_id}"
        self._collection = collection

    def collection(self, name: str) -> "_FakeCollection":
        return self._collection


class _FakeCollection:
    def __init__(self, docs: List[_FakeDoc]):
        self._docs = docs

    def document(self, doc_id: str) -> _FakeDocument:
        return _FakeDocument(doc_id, self)

    def collection(self, name: str) -> "_FakeCollection":
        return self

    def stream(self):
        return iter(self._docs)


class _FakeDb:
    def __init__(self, n_docs: int = 0):
        self.commit_sink: List[int] = []
        self._docs = [_FakeDoc(f"mem-{i}") for i in range(n_docs)]

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._docs)

    def batch(self) -> _BatchLimitEnforcingBatch:
        return _BatchLimitEnforcingBatch(self.commit_sink)


def test_unchunked_batch_delete_exceeding_limit_raises_invalid_argument():
    """Prove that committing more than 500 operations in a single Firestore batch deterministically raises 400 InvalidArgument."""
    commit_sink: List[int] = []
    batch = _BatchLimitEnforcingBatch(commit_sink)
    for i in range(600):
        batch.delete(f"ref-{i}")

    with pytest.raises(InvalidArgument) as exc_info:
        batch.commit()
    assert "400 Transaction or write batch too large" in str(exc_info.value)
    assert commit_sink == []


def test_delete_memories_batch_chunks_over_500_items():
    """Verify delete_memories_batch chunks > 500 items into batches of <= 500 without crashing."""
    fake_db = _FakeDb()
    memory_ids = [f"mem-{i}" for i in range(1200)]

    memories.delete_memories_batch("test-uid", memory_ids, firestore_client=fake_db)

    # 1200 items chunked at <= 500 items per batch -> [500, 500, 200]
    assert sum(fake_db.commit_sink) == 1200
    assert len(fake_db.commit_sink) >= 3
    assert all(c <= _FIRESTORE_BATCH_LIMIT for c in fake_db.commit_sink)


def test_delete_memories_batch_under_limit_single_commit():
    """Verify delete_memories_batch with items <= 500 executes in a single commit."""
    fake_db = _FakeDb()
    memory_ids = [f"mem-{i}" for i in range(10)]

    memories.delete_memories_batch("test-uid", memory_ids, firestore_client=fake_db)

    assert fake_db.commit_sink == [10]


def test_delete_memories_batch_empty_noop():
    """Verify empty list is an immediate no-op."""
    fake_db = _FakeDb()

    memories.delete_memories_batch("test-uid", [], firestore_client=fake_db)

    assert fake_db.commit_sink == []


def test_delete_memories_stream_chunks_over_500_items():
    """Verify delete_memories streaming > 500 documents chunks deletions into batches <= 500."""
    fake_db = _FakeDb(n_docs=1050)

    memories.delete_memories("test-uid", firestore_client=fake_db)

    assert sum(fake_db.commit_sink) == 1050
    assert len(fake_db.commit_sink) >= 3
    assert all(c <= _FIRESTORE_BATCH_LIMIT for c in fake_db.commit_sink)


def test_delete_all_memories_stream_chunks_over_500_items():
    """Verify delete_all_memories streaming > 500 documents chunks deletions into batches <= 500."""
    fake_db = _FakeDb(n_docs=1050)

    memories.delete_all_memories("test-uid", firestore_client=fake_db)

    assert sum(fake_db.commit_sink) == 1050
    assert len(fake_db.commit_sink) >= 3
    assert all(c <= _FIRESTORE_BATCH_LIMIT for c in fake_db.commit_sink)
