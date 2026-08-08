"""Regression test: memory deletes must be chunked under the Firestore batch limit.

database.memories.delete_memories and delete_all_memories accumulated every delete into a
single WriteBatch and committed once. Firestore rejects a batch with more than 500 writes, so
a user with more than 500 memories made batch.commit() raise, and the delete (including the
account-deletion path) removed nothing. Both functions now chunk at 499, mirroring
unlock_all_memories. The store below models the real 500-write limit by raising on an oversized
commit, so the pre-fix single-batch code fails here.
"""

import pytest

import database.memories as memories
from tests.store_fakes import FakeDocumentStore

_FIRESTORE_BATCH_LIMIT = 500


class _TrackingBatch:
    def __init__(self, store, commit_sink):
        self._store = store
        self._commit_sink = commit_sink
        self._ops = 0

    def set(self, path, data, *, merge=False):
        self._ops += 1
        self._store.set(path, data, merge=merge)

    def update(self, path, data):
        self._ops += 1
        self._store.update(path, data)

    def delete(self, path):
        self._ops += 1
        self._store.delete(path)

    def commit(self):
        if self._ops > _FIRESTORE_BATCH_LIMIT:
            raise ValueError("Firestore batch too large: max 500 writes per commit")
        self._commit_sink.append(self._ops)
        self._ops = 0


class _ChunkStore(FakeDocumentStore):
    def __init__(self, n_docs, commit_sink):
        super().__init__()
        for i in range(n_docs):
            self.set(f"users/u1/memories/mem-{i}", {"id": f"mem-{i}"})
        self._commit_sink = commit_sink

    def batch(self):
        return _TrackingBatch(self, self._commit_sink)


@pytest.fixture
def make_store(monkeypatch):
    def _make(n_docs, commit_sink):
        store = _ChunkStore(n_docs, commit_sink)
        monkeypatch.setattr(memories, "_store", lambda: store)
        return store

    return _make


def test_delete_all_memories_chunks_over_firestore_batch_limit(make_store):
    commit_sink = []
    make_store(1000, commit_sink)

    memories.delete_all_memories("u1")  # must not raise

    assert sum(commit_sink) == 1000  # every memory deleted
    assert len(commit_sink) >= 2  # split across batches
    assert all(c <= _FIRESTORE_BATCH_LIMIT for c in commit_sink)


def test_delete_memories_chunks_over_firestore_batch_limit(make_store):
    commit_sink = []
    make_store(1000, commit_sink)

    memories.delete_memories("u1")  # must not raise

    assert sum(commit_sink) == 1000
    assert len(commit_sink) >= 2
    assert all(c <= _FIRESTORE_BATCH_LIMIT for c in commit_sink)


def test_delete_all_memories_small_count_single_commit(make_store):
    commit_sink = []
    make_store(3, commit_sink)

    memories.delete_all_memories("u1")

    assert commit_sink == [3]
