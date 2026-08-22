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
from database.firestore_read_metrics import FIRESTORE_READ_OPERATIONS  # noqa: E402


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return self._data


class _Query:
    """Fake Firestore query that mimics real equality-filter semantics.

    A ``.where(filter=FieldFilter(field, '==', value))`` only matches documents where
    ``field`` is present AND equal to ``value`` — a missing field never matches, and this
    fake enforces that so a test can tell server-side filtering apart from the old
    Python-side filtering it replaces.
    """

    def __init__(self, docs):
        self.docs = docs
        self.projected_fields = None
        self.applied_filters = []
        self.page_limit = None
        self.cursor = None
        self.page_sizes = []
        self.start_after_calls = []

    def select(self, fields):
        self.projected_fields = fields
        return self

    def where(self, filter):
        self.applied_filters.append((filter.field_path, filter.op_string, filter.value))
        return self

    def order_by(self, field):
        assert field == '__name__'
        return self

    def limit(self, value):
        self.page_limit = value
        return self

    def start_after(self, cursor):
        self.cursor = cursor
        self.start_after_calls.append(cursor.id)
        return self

    def stream(self):
        filtered = self.docs
        for field_path, op_string, value in self.applied_filters:
            assert op_string == '==', f'fake only supports == filters, got {op_string}'
            # Real Firestore equality does not conflate int 1/0 with bool True/False, so
            # match on type as well as value, not just Python's `1 == True`.
            filtered = [
                doc
                for doc in filtered
                if field_path in doc._data
                and type(doc._data[field_path]) is type(value)
                and doc._data[field_path] == value
            ]
        if self.cursor is not None:
            cursor_index = next(index for index, doc in enumerate(filtered) if doc.id == self.cursor.id)
            filtered = filtered[cursor_index + 1 :]
        page = filtered[: self.page_limit]
        self.page_sizes.append(len(page))
        return page


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

    assert ai_mod.list_action_item_ids(completed=True, uid='user-9') == {
        'ids': ['done-1'],
        'completed_scope': True,
    }
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
    # `status` is never read in the function body, so it is dropped from the projection.
    assert client.query.projected_fields == ['completed', 'deleted']
    # The completion bucket is filtered server-side, not in Python.
    assert client.query.applied_filters == [('completed', '==', False)]


def test_visible_action_item_ids_excludes_legacy_null_completion_rows():
    client = _Firestore(
        [
            _Doc('legacy-done', {'completed': None, 'status': 'completed'}),
            _Doc('legacy-active', {'completed': None, 'status': 'active'}),
        ]
    )

    ids = action_items_db.get_visible_action_item_ids('user-9', completed=True, firestore_client=client)

    assert ids == []


def test_visible_action_item_ids_includes_docs_with_absent_deleted_field():
    """The common case: most rows never had `deleted` set at all. A server-side
    `.where('deleted', '==', False)` would silently drop these, since Firestore equality
    filters never match a missing field. This must stay a Python-side check."""
    client = _Firestore(
        [
            _Doc('never-deleted', {'completed': False}),
            _Doc('explicitly-not-deleted', {'completed': False, 'deleted': False}),
            _Doc('soft-deleted', {'completed': False, 'deleted': True}),
        ]
    )

    ids = action_items_db.get_visible_action_item_ids('user-9', completed=False, firestore_client=client)

    assert sorted(ids) == ['explicitly-not-deleted', 'never-deleted']
    # No `deleted` filter was pushed to Firestore.
    assert client.query.applied_filters == [('completed', '==', False)]


def test_visible_action_item_ids_records_firestore_read():
    client = _Firestore(
        [
            _Doc('active-1', {'completed': False}),
            _Doc('active-2', {'completed': False, 'deleted': True}),
            _Doc('done', {'completed': True}),  # excluded server-side by the `completed` filter
        ]
    )

    before = FIRESTORE_READ_OPERATIONS.labels(family='action_items_visible_ids', mode='bounded')._value.get()

    action_items_db.get_visible_action_item_ids('user-9', completed=False, firestore_client=client)

    after = FIRESTORE_READ_OPERATIONS.labels(family='action_items_visible_ids', mode='bounded')._value.get()
    assert after == before + 1


def test_visible_action_item_ids_uses_bounded_cursor_pages():
    client = _Firestore([_Doc(f'task-{index:04d}', {'completed': False}) for index in range(501)])

    ids = action_items_db.get_visible_action_item_ids('user-9', completed=False, firestore_client=client)

    assert len(ids) == 501
    assert client.query.page_sizes == [500, 1]
    assert client.query.start_after_calls == ['task-0499']


def test_all_action_item_ids_uses_bounded_cursor_pages():
    client = _Firestore([_Doc(f'task-{index:04d}', {}) for index in range(501)])

    ids = action_items_db.get_action_item_ids('user-9', firestore_client=client)

    assert len(ids) == 501
    assert client.query.projected_fields == []
    assert client.query.page_sizes == [500, 1]
    assert client.query.start_after_calls == ['task-0499']


def test_active_description_lookup_continues_after_first_bounded_page(monkeypatch):
    docs = [_Doc(f'task-{index:04d}', {'completed': False, 'description': 'other'}) for index in range(500)]
    docs.append(_Doc('task-0500', {'completed': False, 'description': 'Target'}))
    client = _Firestore(docs)
    monkeypatch.setattr(action_items_db, 'db', client)

    result = action_items_db.get_active_action_item_by_description('user-9', 'target')

    assert result['id'] == 'task-0500'
    assert client.query.page_sizes == [500, 1]
    assert client.query.start_after_calls == ['task-0499']


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
    result = ai_mod.batch_delete_action_items(ai_mod.BatchDeleteActionItemsRequest(ids=big_ids), uid='user-9')

    assert len(preflight_chunks) == 3
    assert len(preflight_chunks[0]) == 500
    assert len(preflight_chunks[1]) == 500
    assert len(preflight_chunks[2]) == 200
    assert result['deleted_count'] == 1200
