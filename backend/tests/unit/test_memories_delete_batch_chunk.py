"""Regression test: memory deletes must be chunked under the Firestore batch limit.

database.memories.delete_memories and delete_all_memories accumulated every delete into a
single WriteBatch and committed once. Firestore rejects a batch with more than 500 writes, so
a user with more than 500 memories made batch.commit() raise, and the delete (including the
account-deletion path) removed nothing. The fake below models the real 500-write limit by
raising on an oversized commit, so the pre-fix single-batch code fails here.
"""

import database.memories as memories

_FIRESTORE_BATCH_LIMIT = 500


class _FakeBatch:
    def __init__(self, commit_sink, record_sink):
        self._commit_sink = commit_sink
        self._record_sink = record_sink
        self.deletes = 0
        self.sets = 0

    def delete(self, reference):
        self.deletes += 1

    def set(self, reference, payload):
        self.sets += 1
        self._record_sink.append(dict(payload))

    def commit(self):
        if self.deletes + self.sets > _FIRESTORE_BATCH_LIMIT:
            raise ValueError("Firestore batch too large: max 500 writes per commit")
        self._commit_sink.append((self.deletes, self.sets))


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
        self.staged_records = []

    def collection(self, _name):
        return _FakeCollection(self._docs)

    def batch(self):
        return _FakeBatch(self._commit_sink, self.staged_records)


def test_delete_all_memories_chunks_over_firestore_batch_limit():
    commit_sink = []
    fake = _FakeDb(1000, commit_sink)

    result = memories.delete_all_memories("u1", firestore_client=fake)  # must not raise

    assert sum(deletes for deletes, _sets in commit_sink) == 1000  # every memory deleted
    assert sum(sets for _deletes, sets in commit_sink) == 0
    assert result.committed_count == 1000
    assert len(commit_sink) >= 2  # split across batches
    assert all(deletes + sets <= _FIRESTORE_BATCH_LIMIT for deletes, sets in commit_sink)


def test_delete_memories_chunks_over_firestore_batch_limit():
    commit_sink = []
    fake = _FakeDb(1000, commit_sink)

    memories.delete_memories("u1", firestore_client=fake)  # must not raise

    assert sum(deletes for deletes, _sets in commit_sink) == 1000
    assert sum(sets for _deletes, sets in commit_sink) == 0
    assert len(commit_sink) >= 2
    assert all(deletes + sets <= _FIRESTORE_BATCH_LIMIT for deletes, sets in commit_sink)


def test_delete_memories_batch_returns_verified_delete_count():
    commit_sink = []
    fake = _FakeDb(0, commit_sink)

    result = memories.delete_memories_batch(
        "u1",
        [f"mem-{index}" for index in range(1000)],
        firestore_client=fake,
    )

    assert result.committed_count == 1000
    assert commit_sink == [(499, 0), (499, 0), (2, 0)]


def test_delete_all_memories_small_count_single_commit():
    commit_sink = []
    fake = _FakeDb(3, commit_sink)

    result = memories.delete_all_memories("u1", firestore_client=fake)

    assert commit_sink == [(3, 0)]
    assert result.committed_count == 3
