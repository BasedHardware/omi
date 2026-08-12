"""GET /v1/action-items/ids returns the user's action-item IDs (lightweight reconciliation).

The full list endpoint returns every field for every task; there was no cheap way to fetch
just the set of IDs a user has. This reuses the IDs-only get_action_item_ids helper.

Test isolation: routers.action_items imports cleanly, so the test imports it normally,
patches the import-cheap db helper with monkeypatch.setattr, and calls the handler directly.
"""

import os

import pytest
from fastapi import HTTPException

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from routers import action_items as ai_mod  # noqa: E402
from database import action_items as action_items_db  # noqa: E402


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return self._data


class _Query:
    def __init__(self, docs):
        self.docs = docs
        self.projected_fields = None

    def select(self, fields):
        self.projected_fields = fields
        return self

    def stream(self):
        return self.docs


class _CollectionPath:
    def __init__(self, query):
        self.query = query

    def document(self, _):
        return self

    def collection(self, _):
        return self.query


class _Firestore:
    def __init__(self, docs):
        self.query = _Query(docs)

    def collection(self, _):
        return _CollectionPath(self.query)


def test_list_action_item_ids_returns_ids(monkeypatch):
    monkeypatch.setattr(ai_mod.action_items_db, 'get_action_item_ids', lambda uid: ['a1', 'a2', 'a3'])
    assert ai_mod.list_action_item_ids(completed=None, uid='u1') == {'ids': ['a1', 'a2', 'a3']}


def test_list_action_item_ids_empty(monkeypatch):
    monkeypatch.setattr(ai_mod.action_items_db, 'get_action_item_ids', lambda uid: [])
    assert ai_mod.list_action_item_ids(completed=None, uid='u1') == {'ids': []}


def test_list_action_item_ids_scopes_to_caller(monkeypatch):
    seen = {}

    def fake(uid):
        seen['uid'] = uid
        return []

    monkeypatch.setattr(ai_mod.action_items_db, 'get_action_item_ids', fake)
    ai_mod.list_action_item_ids(completed=None, uid='user-9')
    assert seen['uid'] == 'user-9'


def test_list_action_item_ids_scopes_select_all_to_completion_bucket(monkeypatch):
    seen = {}

    def fake(uid, *, completed):
        seen.update(uid=uid, completed=completed)
        return ['done-1']

    monkeypatch.setattr(ai_mod.action_items_db, 'get_visible_action_item_ids', fake)

    assert ai_mod.list_action_item_ids(completed=True, uid='user-9') == {'ids': ['done-1']}
    assert seen == {'uid': 'user-9', 'completed': True}


def test_visible_action_item_ids_matches_explicit_bucket_and_excludes_deleted():
    client = _Firestore(
        [
            _Doc('active', {'completed': False}),
            _Doc('legacy-active', {'completed': None}),
            _Doc('legacy-status-active', {'status': 'active'}),
            _Doc('legacy-status-done', {'status': 'completed'}),
            _Doc('done', {'completed': True}),
            _Doc('deleted-active', {'completed': False, 'deleted': True}),
        ]
    )

    ids = action_items_db.get_visible_action_item_ids('user-9', completed=False, firestore_client=client)

    assert ids == ['active']
    assert client.query.projected_fields == ['completed', 'status', 'deleted']


def test_visible_action_item_ids_excludes_legacy_null_completion_rows():
    client = _Firestore(
        [
            _Doc('legacy-done', {'completed': None, 'status': 'completed'}),
            _Doc('legacy-active', {'completed': None, 'status': 'active'}),
        ]
    )

    ids = action_items_db.get_visible_action_item_ids('user-9', completed=True, firestore_client=client)

    assert ids == []


def test_batch_delete_rejects_locked_items_before_any_delete(monkeypatch):
    monkeypatch.setattr(
        ai_mod.action_items_db,
        'get_action_items_by_ids',
        lambda uid, ids: [{'id': ids[0], 'is_locked': True}],
    )
    delete_calls = []
    monkeypatch.setattr(
        ai_mod.action_items_db,
        'delete_action_items_batch',
        lambda uid, ids: delete_calls.append((uid, ids)),
    )

    with pytest.raises(HTTPException) as error:
        ai_mod.batch_delete_action_items(ai_mod.BatchDeleteActionItemsRequest(ids=['locked-1']), uid='user-9')

    assert error.value.status_code == 402
    assert delete_calls == []


def test_batch_delete_preflight_chunks_large_id_lists(monkeypatch):
    """Lock preflight must be chunked so large Select All batches don't hit
    Firestore batch-get limits or load unbounded document data in one RPC."""
    preflight_chunks: list[list[str]] = []

    def fake_get(uid, ids):
        preflight_chunks.append(list(ids))
        return []

    monkeypatch.setattr(ai_mod.action_items_db, 'get_action_items_by_ids', fake_get)
    monkeypatch.setattr(
        ai_mod.action_items_db,
        'delete_action_items_batch',
        lambda uid, ids: ids,
    )
    monkeypatch.setattr(ai_mod, 'delete_action_item_vectors_batch', lambda *a, **kw: None)
    monkeypatch.setattr(ai_mod, 'send_action_items_batch_deletion_message', lambda *a, **kw: None)
    monkeypatch.setattr(ai_mod, '_wake_task_changes', lambda *a, **kw: None)

    # 1,200 IDs should be split into 3 chunks: 500 + 500 + 200
    big_ids = [f'task-{i}' for i in range(1200)]
    result = ai_mod.batch_delete_action_items(
        ai_mod.BatchDeleteActionItemsRequest(ids=big_ids), uid='user-9'
    )

    assert len(preflight_chunks) == 3
    assert len(preflight_chunks[0]) == 500
    assert len(preflight_chunks[1]) == 500
    assert len(preflight_chunks[2]) == 200
    assert result['deleted_count'] == 1200
