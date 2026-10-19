"""Regression test: memory deletes must be chunked under the Firestore batch limit.

database.memories.delete_memories and delete_all_memories accumulated every delete into a
single WriteBatch and committed once. Firestore rejects a batch with more than 500 writes, so
a user with more than 500 memories made batch.commit() raise, and the delete (including the
account-deletion path) removed nothing. Both functions now chunk at 499, mirroring
unlock_all_memories. The fake below models the real 500-write limit by raising on an oversized
commit, so the pre-fix single-batch code fails here.
"""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

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


class _UnlockDoc:
    def __init__(self, path):
        self.reference = path


class _UnlockQuery:
    def select(self, fields):
        assert fields == []
        return self

    def limit(self, count):
        return _UnlockQuery(self._docs[:count])

    def __init__(self, docs):
        self._docs = docs

    def stream(self):
        return iter(self._docs)


class _UnlockCollection:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def document(self, doc_id):
        return _UnlockDocument(self._db, f"{self._path}/{doc_id}")

    def where(self, *, filter):
        self._db.filters.append((self._path, filter.field_path, filter.op_string, filter.value))
        return _UnlockQuery(self._db.docs_by_collection.get(self._path, []))


class _UnlockDocument:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def collection(self, name):
        return _UnlockCollection(self._db, f"{self._path}/{name}")

    def get(self):
        payload = self._db.markers.get(self._path)
        return SimpleNamespace(exists=payload is not None, to_dict=lambda: payload)


class _UnlockBatch:
    def __init__(self, db):
        self._db = db
        self._updates = []

    def update(self, reference, payload):
        self._updates.append((reference, payload))

    def commit(self):
        self._db.updates.extend(self._updates)


class _UnlockDb:
    def __init__(self):
        self.docs_by_collection = {
            "users/u1/memories": [_UnlockDoc("legacy-locked")],
            "users/u1/memory_items": [_UnlockDoc("canonical-locked")],
        }
        self.markers = {}
        self.filters = []
        self.updates = []

    def collection(self, path):
        return _UnlockCollection(self, path)

    def batch(self):
        return _UnlockBatch(self)


def test_unlock_all_memories_updates_legacy_and_canonical_lock_fields(monkeypatch):
    fake = _UnlockDb()
    monkeypatch.setattr(memories, "external_write_fence", lambda *args, **kwargs: nullcontext())

    memories.unlock_all_memories("u1", firestore_client=fake)

    assert ("users/u1/memories", "is_locked", "==", True) in fake.filters
    assert ("users/u1/memory_items", "promotion.is_locked", "==", True) in fake.filters
    assert ("legacy-locked", {"is_locked": False}) in fake.updates
    assert ("canonical-locked", {"promotion.is_locked": False}) in fake.updates


def test_unlock_memories_bounds_each_legacy_and_canonical_page(monkeypatch):
    fake = _UnlockDb()
    fake.docs_by_collection = {
        "users/u1/memories": [_UnlockDoc(f"legacy-{i}") for i in range(101)],
        "users/u1/memory_items": [_UnlockDoc(f"canonical-{i}") for i in range(101)],
    }
    monkeypatch.setattr(memories, "external_write_fence", lambda *args, **kwargs: nullcontext())
    unlocked = memories.unlock_all_memories("u1", firestore_client=fake, limit=100)
    assert unlocked == 200
    assert unlocked.page_saturated is True
    assert len(fake.updates) == 200


def test_unlock_memories_short_pages_are_not_saturated(monkeypatch):
    fake = _UnlockDb()
    fake.docs_by_collection = {
        "users/u1/memories": [_UnlockDoc(f"legacy-{i}") for i in range(60)],
        "users/u1/memory_items": [_UnlockDoc(f"canonical-{i}") for i in range(60)],
    }
    monkeypatch.setattr(memories, "external_write_fence", lambda *args, **kwargs: nullcontext())
    unlocked = memories.unlock_all_memories("u1", firestore_client=fake, limit=100)
    assert unlocked == 120
    assert unlocked.page_saturated is False


def _allow_unlocked_data_plane(monkeypatch):
    """Deletion authority is the data plane, not the content client under test."""
    import database.account_deletion_marker as marker

    monkeypatch.setattr(marker, 'get_data_plane_firestore_client', lambda: _UnlockDb())


@pytest.mark.parametrize('limit', [None, 100])
def test_unlock_action_items_empty_locked_query_does_not_bump_list_cache(monkeypatch, limit):
    import database.action_items as action_items

    fake = _UnlockDb()
    fake.docs_by_collection['users/u1/action_items'] = []
    invalidations = []
    monkeypatch.setattr(action_items, 'db', fake)
    _allow_unlocked_data_plane(monkeypatch)
    monkeypatch.setattr(action_items, 'bump_action_items_list_version', lambda uid: invalidations.append(uid))
    assert action_items.unlock_all_action_items('u1', limit=limit) == 0
    assert fake.updates == []
    assert invalidations == []


def test_has_recoverable_locked_content_stops_at_the_first_locked_collection(monkeypatch):
    import database.locked_content as locked_content

    fake = _UnlockDb()
    fake.docs_by_collection = {
        'users/u1/conversations': [_UnlockDoc('conversation-locked')],
        'users/u1/memories': [_UnlockDoc('legacy-locked')],
        'users/u1/memory_items': [_UnlockDoc('canonical-locked')],
        'users/u1/action_items': [_UnlockDoc('task-locked')],
    }
    monkeypatch.setattr(locked_content, 'db', fake)
    assert locked_content.has_recoverable_locked_content('u1') is True
    assert [path for path, *_rest in fake.filters] == ['users/u1/conversations']


def test_has_recoverable_locked_content_checks_every_paid_lock_field(monkeypatch):
    import database.locked_content as locked_content

    fake = _UnlockDb()
    fake.docs_by_collection = {
        'users/u1/action_items': [_UnlockDoc('task-locked')],
    }
    monkeypatch.setattr(locked_content, 'db', fake)
    assert locked_content.has_recoverable_locked_content('u1') is True
    assert fake.filters == [
        ('users/u1/conversations', 'is_locked', '==', True),
        ('users/u1/memories', 'is_locked', '==', True),
        ('users/u1/memory_items', 'promotion.is_locked', '==', True),
        ('users/u1/action_items', 'is_locked', '==', True),
    ]


def test_has_recoverable_locked_content_is_false_when_nothing_is_locked(monkeypatch):
    import database.locked_content as locked_content

    fake = _UnlockDb()
    fake.docs_by_collection = {}
    monkeypatch.setattr(locked_content, 'db', fake)
    assert locked_content.has_recoverable_locked_content('u1') is False
    assert len(fake.filters) == 4


def test_unlock_action_items_bounds_updates_and_invalidates_list(monkeypatch):
    import database.action_items as action_items

    fake = _UnlockDb()
    fake.docs_by_collection = {'users/u1/action_items': [_UnlockDoc(f'task-{i}') for i in range(101)]}
    invalidations = []
    monkeypatch.setattr(action_items, 'db', fake)
    _allow_unlocked_data_plane(monkeypatch)
    monkeypatch.setattr(action_items, 'bump_action_items_list_version', lambda uid: invalidations.append(uid))
    assert action_items.unlock_all_action_items('u1', limit=100) == 100
    assert len(fake.updates) == 100
    assert all(update['is_locked'] is False and update['updated_at'] for _, update in fake.updates)
    assert invalidations == ['u1']


@pytest.mark.parametrize('kind', ['conversations', 'action_items'])
@pytest.mark.parametrize('limit', [None, 100])
def test_unlock_helpers_fence_deletion_visible_after_memory_page(monkeypatch, kind, limit):
    import database.account_deletion_marker as marker
    from database import action_items, conversations
    from database.legal_holds import DestructiveOperationInProgress

    content = _UnlockDb()
    data_plane = _UnlockDb()
    content.docs_by_collection[f'users/u1/{kind}'] = [_UnlockDoc(f'{kind}-locked')]
    # The earlier memory page has committed before deletion becomes visible.
    monkeypatch.setattr(memories, 'external_write_fence', lambda *args, **kwargs: nullcontext())
    assert memories.unlock_all_memories('u1', firestore_client=content, limit=100) == 2
    committed = list(content.updates)
    # Uninjected fences read account_deletions on the data-plane client.
    data_plane.markers['account_deletions/u1'] = {'wipe_status': 'in_progress'}
    monkeypatch.setattr(marker, 'get_data_plane_firestore_client', lambda: data_plane)
    module = conversations if kind == 'conversations' else action_items
    monkeypatch.setattr(module, 'db', content)
    invalidations = []
    cache_name = 'invalidate_people_stats_cache' if kind == 'conversations' else 'bump_action_items_list_version'
    monkeypatch.setattr(module, cache_name, lambda uid: invalidations.append(uid))
    with pytest.raises(DestructiveOperationInProgress):
        getattr(module, f'unlock_all_{kind}')('u1', limit=limit)
    assert content.updates == committed
    assert 'account_deletions/u1' not in content.markers
    assert invalidations == []
