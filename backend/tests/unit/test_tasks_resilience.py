"""Unit tests for tasks database input validation, resilience, and error boundaries.

Verifies:
- Whitespace stripping and strict validation of task_id and task_data.
- Rejection of empty/blank task_id, path delimiter '/' injection, and non-dict payloads.
- Idempotent merge on update preventing NotFound exceptions during async callbacks.
- Stream error boundaries and malformed document tolerance in get_task_by_action_request.
- Whitespace stripping and safe None returns on empty action or request_id.
- Custom Firestore client injection across all methods.
"""

from unittest.mock import MagicMock
import pytest

import database.tasks as tasks_db


class _FakeDocSnapshot:
    def __init__(self, doc_id: str, data: dict, exists: bool = True):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, doc_id: str, store: dict):
        self.id = doc_id
        self._store = store

    def set(self, data: dict, merge: bool = False):
        if merge and self.id in self._store:
            self._store[self.id].update(data)
        else:
            self._store[self.id] = dict(data)

    def get(self):
        if self.id in self._store:
            return _FakeDocSnapshot(self.id, self._store[self.id], exists=True)
        return _FakeDocSnapshot(self.id, None, exists=False)


class _FakeQuery:
    def __init__(self, items: list, should_fail: bool = False):
        self._items = items
        self._should_fail = should_fail
        self._filters = []
        self._limit_val = None

    def where(self, filter=None, **kwargs):
        self._filters.append(filter or kwargs)
        return self

    def limit(self, count: int):
        self._limit_val = count
        return self

    def stream(self):
        if self._should_fail:
            raise RuntimeError("Firestore query stream network timeout")
        for item in self._items:
            yield item


class _FakeCollection:
    def __init__(self, store: dict, query_items: list = None, should_fail_query: bool = False):
        self._store = store
        self._query_items = query_items if query_items is not None else []
        self._should_fail_query = should_fail_query

    def document(self, doc_id: str):
        return _FakeDocRef(doc_id, self._store)

    def where(self, filter=None, **kwargs):
        query = _FakeQuery(self._query_items, should_fail=self._should_fail_query)
        return query.where(filter=filter, **kwargs)


class _FakeFirestoreClient:
    def __init__(self, query_items: list = None, should_fail_query: bool = False):
        self._store = {}
        self._query_items = query_items if query_items is not None else []
        self._should_fail_query = should_fail_query

    def collection(self, name: str):
        assert name == tasks_db.TASKS_COLLECTION
        return _FakeCollection(self._store, self._query_items, self._should_fail_query)


# --- Tests for create ---


def test_create_persists_valid_task_and_strips_whitespace():
    client = _FakeFirestoreClient()
    payload = {'id': '  task-123  ', 'action': 'test_action', 'status': 'processing'}
    tasks_db.create(payload, firestore_client=client)

    assert 'task-123' in client._store
    assert client._store['task-123']['action'] == 'test_action'


def test_create_rejects_missing_or_empty_id():
    client = _FakeFirestoreClient()
    with pytest.raises(ValueError, match="id cannot be empty"):
        tasks_db.create({'id': ''}, firestore_client=client)

    with pytest.raises(ValueError, match="id cannot be empty"):
        tasks_db.create({'id': '   '}, firestore_client=client)

    with pytest.raises(ValueError, match="id cannot be empty"):
        tasks_db.create({}, firestore_client=client)


def test_create_rejects_path_delimiters():
    client = _FakeFirestoreClient()
    with pytest.raises(ValueError, match="cannot contain path delimiters"):
        tasks_db.create({'id': 'tasks/sub-task'}, firestore_client=client)


def test_create_rejects_non_dict_payload():
    client = _FakeFirestoreClient()
    with pytest.raises(ValueError, match="task_data must be a dictionary"):
        tasks_db.create("invalid", firestore_client=client)


# --- Tests for update ---


def test_update_idempotently_merges_data():
    client = _FakeFirestoreClient()
    client._store['task-1'] = {'id': 'task-1', 'status': 'processing', 'created_at': 100}

    tasks_db.update(' task-1 ', {'status': 'done'}, firestore_client=client)

    assert client._store['task-1']['status'] == 'done'
    assert client._store['task-1']['created_at'] == 100


def test_update_creates_if_not_exists_without_throwing_not_found():
    client = _FakeFirestoreClient()
    tasks_db.update('task-new', {'id': 'task-new', 'status': 'done'}, firestore_client=client)

    assert client._store['task-new']['status'] == 'done'


def test_update_rejects_invalid_task_id():
    client = _FakeFirestoreClient()
    with pytest.raises(ValueError, match="task_id cannot be empty"):
        tasks_db.update('  ', {'status': 'done'}, firestore_client=client)

    with pytest.raises(ValueError, match="cannot contain path delimiters"):
        tasks_db.update('user/task', {'status': 'done'}, firestore_client=client)


def test_update_rejects_non_dict():
    client = _FakeFirestoreClient()
    with pytest.raises(ValueError, match="task_data must be a dictionary"):
        tasks_db.update('task-1', 'invalid', firestore_client=client)


# --- Tests for get_task_by_action_request ---


def test_get_task_by_action_request_returns_matching_task():
    matching_doc = _FakeDocSnapshot('doc-1', {'id': 't-1', 'action': 'action_a', 'request_id': 'req-99'})
    client = _FakeFirestoreClient(query_items=[matching_doc])

    res = tasks_db.get_task_by_action_request(' action_a ', ' req-99 ', firestore_client=client)
    assert res == {'id': 't-1', 'action': 'action_a', 'request_id': 'req-99'}


def test_get_task_by_action_request_returns_none_on_empty_args():
    client = _FakeFirestoreClient()
    assert tasks_db.get_task_by_action_request('', 'req-1', firestore_client=client) is None
    assert tasks_db.get_task_by_action_request('action', '', firestore_client=client) is None
    assert tasks_db.get_task_by_action_request('  ', '  ', firestore_client=client) is None


def test_get_task_by_action_request_tolerates_corrupted_doc_snapshots():
    corrupt_doc = _FakeDocSnapshot('doc-bad', None)
    valid_doc = _FakeDocSnapshot('doc-good', {'id': 't-2', 'action': 'act', 'request_id': 'req'})
    client = _FakeFirestoreClient(query_items=[corrupt_doc, valid_doc])

    res = tasks_db.get_task_by_action_request('act', 'req', firestore_client=client)
    assert res == {'id': 't-2', 'action': 'act', 'request_id': 'req'}


def test_get_task_by_action_request_handles_stream_exceptions_gracefully():
    client = _FakeFirestoreClient(should_fail_query=True)
    res = tasks_db.get_task_by_action_request('act', 'req', firestore_client=client)
    assert res is None
