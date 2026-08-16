"""Tests for content-hash idempotency on create_action_item.

`database.action_items.create_action_item` historically allocated a fresh
Firestore id on every call. A flaky-network retry from the desktop client
would happily produce a duplicate document. The fix:

- ``create_action_item(..., idempotency_key=<key>)``: when supplied, the
  function looks for an existing doc with that key (any state) and returns
  its id without creating a new one. The key is stored on the document so
  later calls can find it.

- ``routers/action_items.create_action_item`` (the FastAPI handler) computes
  a stable key from ``sha256(f"{uid}:{normalized_description}")`` so a
  retried POST of the same task collapses to the original.

These tests exercise the db-layer contract (idempotency hit / miss / no-key
backwards compat) and the router-layer key derivation.
"""

from unittest.mock import MagicMock

from google.api_core.exceptions import Aborted

from database import action_items as action_items_db  # noqa: E402
from database import firestore_transaction_retry
from routers import action_items as action_items_router  # noqa: E402

# ---------------------------------------------------------------------------
# create_action_item — db layer
# ---------------------------------------------------------------------------


def _make_doc(doc_id, data=None):
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data or {}
    return doc


def _stub_collection(monkeypatch, existing_docs, *, control_generation=None):
    """Stub db.collection('users').document(uid).collection('action_items').

    Returns a tuple ``(action_items_ref, captured)`` where ``captured`` is a
    dict that records add() calls for assertions.
    """
    captured = {'added': [], 'set': {}, 'filters': []}

    fake_query = MagicMock()

    # Chain: .where(...).where(...).limit(N).stream() — every intermediate
    # call returns the same fake so we don't have to model a query builder.
    def _where(*, filter):
        captured['filters'].append((filter.field_path, filter.op_string, filter.value))
        return fake_query

    fake_query.where.side_effect = _where
    fake_query.limit.return_value = fake_query

    def _stream(**kwargs):
        generation_filters = [value for field, operator, value in captured['filters'] if field == 'account_generation']
        if not generation_filters:
            return iter(existing_docs)
        generation = generation_filters[-1]
        return iter([doc for doc in existing_docs if doc.to_dict().get('account_generation') == generation])

    fake_query.stream.side_effect = _stream

    fake_action_items_ref = MagicMock()
    fake_action_items_ref.where.side_effect = _where

    def _add(payload):
        captured['added'].append(payload)
        ref = MagicMock()
        ref.id = 'newly-created-id'
        return (None, ref)

    fake_action_items_ref.add.side_effect = _add
    document_refs = {}

    def _document(document_id=None):
        if document_id is None:
            document_id = 'newly-created-id'
        if document_id in document_refs:
            return document_refs[document_id]
        ref = MagicMock()
        ref.id = document_id
        ref.get.side_effect = lambda **kwargs: MagicMock(
            exists=document_id in captured['set'],
            to_dict=lambda: captured['set'].get(document_id, {}),
        )

        def _set(payload):
            captured['set'][document_id] = payload
            if document_id == 'newly-created-id':
                captured['added'].append(payload)

        ref.set.side_effect = _set
        document_refs[document_id] = ref
        return ref

    fake_action_items_ref.document.side_effect = _document

    fake_control_ref = MagicMock()
    fake_control_ref.get.side_effect = lambda **kwargs: MagicMock(
        exists=control_generation is not None,
        to_dict=lambda: {'account_generation': control_generation} if control_generation is not None else {},
    )
    fake_control_collection = MagicMock()
    fake_control_collection.document.return_value = fake_control_ref

    fake_user_doc = MagicMock()
    fake_user_doc.collection.side_effect = lambda name: (
        fake_action_items_ref if name == action_items_db.action_items_collection else fake_control_collection
    )

    fake_users = MagicMock()
    fake_users.document.return_value = fake_user_doc

    transaction = MagicMock()
    transaction.set.side_effect = lambda ref, payload: ref.set(payload)
    fake_db = MagicMock(collection=MagicMock(return_value=fake_users))
    fake_db.transaction.return_value = transaction
    monkeypatch.setattr(action_items_db, 'db', fake_db)
    monkeypatch.setattr(
        action_items_db.firestore,
        'transactional',
        lambda function: lambda transaction: function(transaction),
    )
    return captured


def test_no_idempotency_key_creates_new_doc(monkeypatch):
    """Backwards-compat: existing callers that do not pass a key see no change."""
    captured = _stub_collection(monkeypatch, [])
    result = action_items_db.create_action_item('uid', {'description': 'Buy milk', 'completed': False})
    assert result == 'newly-created-id'
    assert len(captured['added']) == 1
    assert 'idempotency_key' not in captured['added'][0]


def test_idempotency_hit_on_active_returns_existing_id(monkeypatch):
    """Hit on an active (non-completed, non-deleted) doc collapses the call."""
    captured = _stub_collection(
        monkeypatch,
        [_make_doc('existing-id', {'completed': False, 'deleted': False})],
    )
    result = action_items_db.create_action_item(
        'uid', {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
    )
    assert result == 'existing-id'
    assert captured['added'] == [], "no new document should be created on idempotency hit"


def test_idempotency_falls_through_when_only_match_is_deleted(monkeypatch):
    """A soft-deleted match must not block recreation — the user explicitly
    deleted it, so a fresh POST is a recreation, not a retry."""
    captured = _stub_collection(
        monkeypatch,
        [_make_doc('deleted-id', {'completed': False, 'deleted': True})],
    )
    result = action_items_db.create_action_item(
        'uid', {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
    )
    assert result == 'newly-created-id', "deleted match must not short-circuit"
    assert len(captured['added']) == 1
    assert captured['added'][0].get('idempotency_key') == 'abc123'


def test_idempotency_miss_writes_key_on_new_doc(monkeypatch):
    captured = _stub_collection(monkeypatch, [])
    result = action_items_db.create_action_item(
        'uid', {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
    )
    assert result == 'newly-created-id'
    assert len(captured['added']) == 1
    assert captured['added'][0].get('idempotency_key') == 'abc123'


def test_idempotency_does_not_return_prior_generation_task(monkeypatch):
    captured = _stub_collection(
        monkeypatch,
        [_make_doc('old-generation-id', {'completed': False, 'deleted': False, 'account_generation': 6})],
        control_generation=7,
    )
    result = action_items_db.create_action_item(
        'uid', {'description': 'Buy milk', 'completed': False}, idempotency_key='abc123'
    )
    assert result == 'newly-created-id'
    assert captured['added'][0]['account_generation'] == 7
    assert ('account_generation', '==', 7) in captured['filters']


def test_reserved_document_id_is_idempotent_across_crash_retry(monkeypatch):
    captured = _stub_collection(monkeypatch, [])

    first = action_items_db.create_action_item(
        'uid', {'description': 'Buy milk', 'completed': False}, document_id='task-reserved'
    )
    second = action_items_db.create_action_item(
        'uid', {'description': 'Buy milk', 'completed': False}, document_id='task-reserved'
    )

    assert first == second == 'task-reserved'
    assert list(captured['set']) == ['task-reserved']
    assert captured['added'] == []


def test_create_retries_precommit_contention_without_duplicate_write(monkeypatch):
    captured = _stub_collection(monkeypatch, [])
    attempts = 0

    def transactional(function):
        def wrapped(transaction):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise Aborted('read contention')
            return function(transaction)

        return wrapped

    def fast_retry(transaction_factory, operation, **kwargs):
        return firestore_transaction_retry.run_with_transaction_contention_retry(
            transaction_factory,
            operation,
            **kwargs,
            sleep=lambda _delay: None,
            random_value=lambda: 0.0,
        )

    monkeypatch.setattr(action_items_db.firestore, 'transactional', transactional)
    monkeypatch.setattr(action_items_db, 'run_with_transaction_contention_retry', fast_retry)

    result = action_items_db.create_action_item(
        'uid',
        {'description': 'Buy milk', 'completed': False},
        idempotency_key='abc123',
    )

    assert result == 'newly-created-id'
    assert attempts == 2
    assert len(captured['added']) == 1


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
        'the task auto-sync coordinator must run on postprocess_executor so its Firestore '
        'children can acquire db_executor workers'
    )
    assert database_submissions == [], 'the task auto-sync coordinator must never occupy a db_executor worker'
