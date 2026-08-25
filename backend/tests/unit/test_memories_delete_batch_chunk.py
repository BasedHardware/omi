"""Regression test: memory deletes must be chunked under the Firestore batch limit.

database.memories.delete_memories and delete_all_memories accumulated every delete into a
single WriteBatch and committed once. Firestore rejects a batch with more than 500 writes, so
a user with more than 500 memories made batch.commit() raise, and the delete (including the
account-deletion path) removed nothing. Both functions now chunk at 499, mirroring
unlock_all_memories. The fake below models the real 500-write limit by raising on an oversized
commit, so the pre-fix single-batch code fails here.
"""

import database.memories as memories

_FIRESTORE_BATCH_LIMIT = 500


class _FakeBatch:
    def __init__(self, commit_sink):
        self._commit_sink = commit_sink
        self.deletes = 0

    def delete(self, reference):
        self.deletes += 1

    def commit(self):
        if self.deletes > _FIRESTORE_BATCH_LIMIT:
            raise ValueError("Firestore batch too large: max 500 writes per commit")
        self._commit_sink.append(self.deletes)


class _FakeDoc:
    def __init__(self, i):
        self.reference = f"ref-{i}"
        self.id = f"mem-{i}"


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def document(self, _uid):
        return self

    def collection(self, _name):
        return self

    def stream(self):
        return iter(self._docs)


class _FakeDb:
    def __init__(self, n_docs, commit_sink):
        self._docs = [_FakeDoc(i) for i in range(n_docs)]
        self._commit_sink = commit_sink

    def collection(self, _name):
        return _FakeCollection(self._docs)

    def batch(self):
        return _FakeBatch(self._commit_sink)


def test_delete_all_memories_chunks_over_firestore_batch_limit():
    commit_sink = []
    fake = _FakeDb(1000, commit_sink)

    memories.delete_all_memories("u1", firestore_client=fake)  # must not raise

    assert sum(commit_sink) == 1000  # every memory deleted
    assert len(commit_sink) >= 2  # split across batches
    assert all(c <= _FIRESTORE_BATCH_LIMIT for c in commit_sink)


def test_delete_memories_chunks_over_firestore_batch_limit():
    commit_sink = []
    fake = _FakeDb(1000, commit_sink)

    memories.delete_memories("u1", firestore_client=fake)  # must not raise

    assert sum(commit_sink) == 1000
    assert len(commit_sink) >= 2
    assert all(c <= _FIRESTORE_BATCH_LIMIT for c in commit_sink)


def test_delete_all_memories_small_count_single_commit():
    commit_sink = []
    fake = _FakeDb(3, commit_sink)

    memories.delete_all_memories("u1", firestore_client=fake)

    assert commit_sink == [3]
