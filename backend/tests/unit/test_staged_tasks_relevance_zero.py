"""Regression test: migrate_ai_tasks must keep the best (relevance_score == 0) AI task.

database.staged_tasks.migrate_ai_tasks keeps the top 3 AI action items by relevance_score
ascending (best first) and moves the rest to staged_tasks. The sort key used
`x.get('relevance_score') or 999`, which coerces a valid best score of 0 (relevance_score is
an int in 0-1000 where 0 is most relevant) to 999, sorting the single most relevant task last
so it gets moved out of action_items instead of kept. The key now maps only a genuinely missing
(None) score to 999.

Seam: database.staged_tasks reads/writes exclusively through the module-level `db`, so a fake
db that streams action-item docs and records batched writes exercises the real migration path.
"""

import database.staged_tasks as staged_tasks


class _FakeDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    def __init__(self, docs):
        self._docs = docs

    def where(self, **kwargs):
        return self

    def select(self, *args, **kwargs):
        return self

    def stream(self):
        return iter(self._docs)


class _FakeDocRef:
    def __init__(self, doc_id):
        self.id = doc_id


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def where(self, **kwargs):
        return _FakeQuery(self._docs)

    def document(self, doc_id=None):
        return _FakeDocRef(doc_id)


class _FakeUserDoc:
    def __init__(self, action_docs):
        self._action_docs = action_docs

    def collection(self, name):
        # Only action_items is streamed; staged_tasks is used solely for .document(id).
        return _FakeCollection(self._action_docs if name == 'action_items' else [])


class _FakeUsersCollection:
    def __init__(self, action_docs):
        self._action_docs = action_docs

    def document(self, uid):
        return _FakeUserDoc(self._action_docs)


class _FakeBatch:
    def __init__(self, moved_ids):
        self._moved_ids = moved_ids

    def set(self, ref, data):
        # A set into staged_tasks is a "move out of action_items".
        self._moved_ids.append(ref.id)

    def delete(self, ref):
        pass

    def commit(self):
        pass


class _FakeDB:
    def __init__(self, action_docs, moved_ids):
        self._action_docs = action_docs
        self._moved_ids = moved_ids

    def collection(self, name):  # 'users'
        return _FakeUsersCollection(self._action_docs)

    def batch(self):
        return _FakeBatch(self._moved_ids)


def test_migrate_keeps_relevance_zero_task(monkeypatch):
    # Five AI tasks; ascending best-first means score 0 is the single best and must be kept.
    action_docs = [
        _FakeDoc('t0', {'source': 'screenshot', 'relevance_score': 0}),  # best (0)
        _FakeDoc('t1', {'source': 'screenshot', 'relevance_score': 1}),
        _FakeDoc('t2', {'source': 'screenshot', 'relevance_score': 2}),
        _FakeDoc('t3', {'source': 'screenshot', 'relevance_score': 3}),
        _FakeDoc('t4', {'source': 'screenshot', 'relevance_score': 4}),
    ]
    moved_ids: list[str] = []
    monkeypatch.setattr(staged_tasks, 'db', _FakeDB(action_docs, moved_ids))

    staged_tasks.migrate_ai_tasks('u1')

    # Keep the three lowest scores (t0, t1, t2); move the rest. The best (t0, score 0)
    # must NOT be moved out. With the old `or 999` key it sorted last and was moved.
    assert 't0' not in moved_ids
    assert set(moved_ids) == {'t3', 't4'}


def test_migrate_still_sorts_missing_score_last(monkeypatch):
    # A genuinely missing score must still sort last (moved), distinct from a 0.
    action_docs = [
        _FakeDoc('z', {'source': 'screenshot', 'relevance_score': 0}),
        _FakeDoc('a', {'source': 'screenshot', 'relevance_score': 5}),
        _FakeDoc('b', {'source': 'screenshot', 'relevance_score': 7}),
        _FakeDoc('none', {'source': 'screenshot'}),  # missing relevance_score
    ]
    moved_ids: list[str] = []
    monkeypatch.setattr(staged_tasks, 'db', _FakeDB(action_docs, moved_ids))

    staged_tasks.migrate_ai_tasks('u1')

    # Keep z(0), a(5), b(7); the missing-score task sorts last and is moved.
    assert moved_ids == ['none']
