"""Tests for content-hash idempotency on create_action_item.

`database.action_items.create_action_item` historically allocated a fresh
document id on every call. A flaky-network retry from the desktop client
would happily produce a duplicate document. The fix:

- ``create_action_item(..., idempotency_key=<key>)``: when supplied, the
  function looks for an existing doc with that key (any state) and returns
  its id without creating a new one. The key is stored on the document so
  later calls can find it.

- ``routers/action_items.create_action_item`` (the FastAPI handler) computes
  a stable key from ``sha256(f"{uid}:{normalized_description}")`` so a
  retried POST of the same task collapses to the original.

These tests exercise the db-layer contract (idempotency hit / miss / no-key
backwards compat) against the neutral storage port (``FakeDocumentStore``),
and the router-layer key derivation.
"""

from unittest.mock import MagicMock

import pytest

from database import action_items as action_items_db  # noqa: E402
from database.firestore_transaction_retry import FirestoreAborted, FirestoreContentionExhausted  # noqa: E402
from routers import action_items as action_items_router  # noqa: E402
from tests.store_fakes import FakeDocumentStore, _FakeTransaction

_UID = 'uid'

# ---------------------------------------------------------------------------
# create_action_item — db layer
# ---------------------------------------------------------------------------


def _make_store(existing=(), *, control_generation=None):
    store = FakeDocumentStore()
    for doc_id, data in existing:
        store._docs[f'users/{_UID}/action_items/{doc_id}'] = dict(data)
    if control_generation is not None:
        store._docs[f'users/{_UID}/task_intelligence_control/state'] = {'account_generation': control_generation}
    return store


def _bind(monkeypatch, store):
    monkeypatch.setattr(action_items_db, '_store', lambda: store)


def _action_item_docs(store):
    prefix = f'users/{_UID}/action_items/'
    return {path[len(prefix):]: data for path, data in store._docs.items() if path.startswith(prefix)}


def test_no_idempotency_key_creates_new_doc(monkeypatch):
    """Backwards-compat: existing callers that do not pass a key see no change."""
    store = _make_store()
    _bind(monkeypatch, store)
    result = action_items_db.create_action_item(_UID, {'description': 'Buy milk', 'completed': False})
    docs = _action_item_docs(store)
    assert result in docs
    assert len(docs) == 1
    assert 'idempotency_key' not in docs[result]


def test_idempotency_hit_on_active_returns_existing_id(monkeypatch):
    """Hit on an active (non-completed, non-deleted) doc collapses the call."""
    store = _make_store([('existing-id', {'completed': False, 'deleted': False, 'idempotency_key': 'abc123'})])
    _bind(monkeypatch, store)
    result = action_items_db.create_action_item(
        _UID, {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
    )
    assert result == 'existing-id'
    assert len(_action_item_docs(store)) == 1, "no new document should be created on idempotency hit"


def test_idempotency_falls_through_when_only_match_is_deleted(monkeypatch):
    """A soft-deleted match must not block recreation — the user explicitly
    deleted it, so a fresh POST is a recreation, not a retry."""
    store = _make_store([('deleted-id', {'completed': False, 'deleted': True, 'idempotency_key': 'abc123'})])
    _bind(monkeypatch, store)
    result = action_items_db.create_action_item(
        _UID, {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
    )
    assert result != 'deleted-id', "deleted match must not short-circuit"
    docs = _action_item_docs(store)
    assert len(docs) == 2
    assert docs[result].get('idempotency_key') == 'abc123'


def test_idempotency_miss_writes_key_on_new_doc(monkeypatch):
    store = _make_store()
    _bind(monkeypatch, store)
    result = action_items_db.create_action_item(
        _UID, {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
    )
    docs = _action_item_docs(store)
    assert len(docs) == 1
    assert docs[result].get('idempotency_key') == 'abc123'


def test_idempotency_does_not_return_prior_generation_task(monkeypatch):
    class _RecordingStore(FakeDocumentStore):
        def __init__(self):
            super().__init__()
            self.query_filters = []

        def query(self, collection, *, filters=None, **kwargs):
            self.query_filters.append(list(filters or []))
            return super().query(collection, filters=filters, **kwargs)

    store = _RecordingStore()
    store._docs[f'users/{_UID}/action_items/old-generation-id'] = {
        'completed': False,
        'deleted': False,
        'account_generation': 6,
        'idempotency_key': 'abc123',
    }
    store._docs[f'users/{_UID}/task_intelligence_control/state'] = {'account_generation': 7}
    _bind(monkeypatch, store)

    result = action_items_db.create_action_item(
        _UID, {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
    )
    docs = _action_item_docs(store)
    assert result != 'old-generation-id'
    assert docs[result]['account_generation'] == 7
    # The idempotency lookup is scoped to the current account generation.
    assert any(('account_generation', '==', 7) in filters for filters in store.query_filters)


def test_reserved_document_id_is_idempotent_across_crash_retry(monkeypatch):
    store = _make_store()
    _bind(monkeypatch, store)

    first = action_items_db.create_action_item(
        _UID, {'description': 'Buy milk', 'completed': False}, document_id='task-reserved'
    )
    second = action_items_db.create_action_item(
        _UID, {'description': 'Buy milk', 'completed': False}, document_id='task-reserved'
    )

    assert first == second == 'task-reserved'
    assert list(_action_item_docs(store)) == ['task-reserved']


def test_create_retries_precommit_contention_without_duplicate_write(monkeypatch):
    class _RetryingStore(FakeDocumentStore):
        """Runs the write callback twice to simulate a transaction contention retry.

        A stable, pre-generated document id must make the retry overwrite the same path rather
        than allocate a fresh one, so the collection ends with exactly one document.
        """

        def __init__(self):
            super().__init__()
            self.fn_calls = 0

        def run_transaction(self, fn, *, attempts=3):
            self.fn_calls += 1
            fn(_FakeTransaction(self))  # first attempt, discarded (as if aborted pre-commit)
            self.fn_calls += 1
            return fn(_FakeTransaction(self))  # retry commits

    store = _RetryingStore()
    _bind(monkeypatch, store)

    result = action_items_db.create_action_item(
        _UID,
        {'description': 'Buy milk', 'completed': False},
        idempotency_key='abc123',
    )

    docs = _action_item_docs(store)
    assert store.fn_calls == 2
    assert len(docs) == 1
    assert result in docs


def test_concurrent_same_key_creates_do_not_duplicate_when_query_is_blind(monkeypatch):
    """The pre-transaction idempotency query cannot observe a concurrent, not-yet-committed sibling
    create — modeled here by a query that always misses. The transaction-visible reservation must
    still collapse two same-key creates to a single document. Without the reservation each call
    allocates its own uuid and the collection ends with two duplicates.
    """

    class _QueryBlindStore(FakeDocumentStore):
        def query(self, collection, *, filters=None, **kwargs):  # noqa: D401 - test double
            return []

    store = _QueryBlindStore()
    _bind(monkeypatch, store)

    first = action_items_db.create_action_item(
        _UID, {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
    )
    second = action_items_db.create_action_item(
        _UID, {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
    )

    assert first == second, 'the reservation must return the winner id to the racing sibling'
    assert len(_action_item_docs(store)) == 1, 'the transactional reservation must prevent a duplicate'


def test_reservation_falls_through_when_reserved_target_completed(monkeypatch):
    """A reservation pointing at a now-completed task must not block a fresh create (parity with the
    query's ``completed == False`` semantic): the user completed it and is re-adding it."""

    class _QueryBlindStore(FakeDocumentStore):
        def query(self, collection, *, filters=None, **kwargs):
            return []

    store = _QueryBlindStore()
    _bind(monkeypatch, store)

    first = action_items_db.create_action_item(
        _UID, {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
    )
    # The reserved task is completed out-of-band.
    store._docs[f'users/{_UID}/action_items/{first}']['completed'] = True

    second = action_items_db.create_action_item(
        _UID, {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
    )

    assert second != first, 'a completed reserved target must not short-circuit a new create'
    assert len(_action_item_docs(store)) == 2


def test_create_maps_exhausted_contention_to_firestore_contention_exhausted(monkeypatch):
    """When the store transaction exhausts contention (raw ``Aborted`` escapes ``run_transaction``),
    create_action_item must surface ``FirestoreContentionExhausted`` so the route maps it to 503 —
    not leak a raw provider error as an unmapped 500."""

    class _AbortingStore(FakeDocumentStore):
        def run_transaction(self, fn, *, attempts=3):
            raise FirestoreAborted('transaction contention')

    _bind(monkeypatch, _AbortingStore())

    with pytest.raises(FirestoreContentionExhausted):
        action_items_db.create_action_item(
            _UID, {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
        )


def test_batch_create_maps_exhausted_contention_to_firestore_contention_exhausted(monkeypatch):
    class _AbortingStore(FakeDocumentStore):
        def run_transaction(self, fn, *, attempts=3):
            raise FirestoreAborted('transaction contention')

    _bind(monkeypatch, _AbortingStore())

    with pytest.raises(FirestoreContentionExhausted):
        action_items_db.create_action_items_batch(_UID, [{'description': 'Buy milk', 'completed': False}])


def test_linked_update_maps_exhausted_contention_to_firestore_contention_exhausted(monkeypatch):
    class _AbortingStore(FakeDocumentStore):
        def run_transaction(self, fn, *, attempts=3):
            raise FirestoreAborted('transaction contention')

    _bind(monkeypatch, _AbortingStore())

    # goal_id routes update_action_item through its transactional (contention-mapped) path.
    with pytest.raises(FirestoreContentionExhausted):
        action_items_db.update_action_item(_UID, 'task-1', {'goal_id': 'goal-1'})


def test_create_does_not_convert_non_contention_errors(monkeypatch):
    """Only genuine contention becomes FirestoreContentionExhausted; unrelated failures propagate."""

    class _BrokenStore(FakeDocumentStore):
        def run_transaction(self, fn, *, attempts=3):
            raise RuntimeError('unrelated failure')

    _bind(monkeypatch, _BrokenStore())

    with pytest.raises(RuntimeError, match='unrelated failure'):
        action_items_db.create_action_item(
            _UID, {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
        )


# ---------------------------------------------------------------------------
# router-layer content key
# ---------------------------------------------------------------------------


def test_content_key_is_stable_for_same_input():
    a = action_items_router._content_idempotency_key('uid-1', 'Buy milk')
    b = action_items_router._content_idempotency_key('uid-1', 'Buy milk')
    assert a == b


def test_content_key_normalizes_case_and_whitespace():
    a = action_items_router._content_idempotency_key('uid-1', 'Buy Milk')
    b = action_items_router._content_idempotency_key('uid-1', '  buy milk  ')
    assert a == b


def test_content_key_separates_users():
    a = action_items_router._content_idempotency_key('uid-1', 'Buy milk')
    b = action_items_router._content_idempotency_key('uid-2', 'Buy milk')
    assert a != b


def test_content_key_separates_descriptions():
    a = action_items_router._content_idempotency_key('uid-1', 'Buy milk')
    b = action_items_router._content_idempotency_key('uid-1', 'Buy bread')
    assert a != b


def test_content_key_avoids_separator_collision():
    """Length-prefixed encoding must distinguish (uid='org', desc='user:task')
    from (uid='org:user', desc='task'). A naive ``f"{uid}:{desc}"`` encoding
    would collapse both to the same hash; the length prefix prevents this."""
    a = action_items_router._content_idempotency_key('org', 'user:task')
    b = action_items_router._content_idempotency_key('org:user', 'task')
    assert a != b


def test_create_dispatches_auto_sync_outside_the_database_pool(monkeypatch):
    postprocess_pool = object()
    submitted_to = []
    database_submissions = []

    monkeypatch.setattr(action_items_router, 'postprocess_executor', postprocess_pool, raising=False)
    monkeypatch.setattr(
        action_items_router,
        'submit_with_context',
        lambda executor, function: submitted_to.append(executor),
        raising=False,
    )
    legacy_db_executor = getattr(action_items_router, 'db_executor', MagicMock())
    monkeypatch.setattr(legacy_db_executor, 'submit', lambda function: database_submissions.append(function))
    monkeypatch.setattr(action_items_router, 'db_executor', legacy_db_executor, raising=False)
    monkeypatch.setattr(action_items_router.task_links, 'validate_task_links', lambda *args, **kwargs: None)
    monkeypatch.setattr(action_items_db, 'create_action_item', lambda *args, **kwargs: 'task-1')
    monkeypatch.setattr(
        action_items_db,
        'get_action_item',
        lambda *args, **kwargs: {'id': 'task-1', 'description': 'Plan launch', 'completed': False},
    )
    monkeypatch.setattr(action_items_router, 'upsert_action_item_vector', lambda *args, **kwargs: None)

    result = action_items_router.create_action_item(
        action_items_router.CreateActionItemRequest(description='Plan launch'),
        uid='user-1',
    )

    assert result.id == 'task-1'
    assert submitted_to == [postprocess_pool], (
        'the task auto-sync coordinator must run on postprocess_executor so its storage '
        'children can acquire db_executor workers'
    )
    assert database_submissions == [], 'the task auto-sync coordinator must never occupy a db_executor worker'
