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

import sys
import types
from unittest.mock import MagicMock


def _ensure_module(name):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
    return sys.modules[name]


for mod_name in [
    'firebase_admin',
    'firebase_admin.auth',
    'google',
    'google.cloud',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.base_query',
]:
    _ensure_module(mod_name)


class _FakeFirestoreClient:
    def collection(self, *a, **kw):
        return MagicMock()

    def batch(self):
        return MagicMock()


sys.modules['google.cloud.firestore'].Client = _FakeFirestoreClient
sys.modules['google.cloud.firestore'].SERVER_TIMESTAMP = object()
sys.modules['google.cloud.firestore'].Query = MagicMock()


class _FieldFilter:
    def __init__(self, field, op, value):
        self.field = field
        self.op = op
        self.value = value


sys.modules['google.cloud.firestore'].FieldFilter = _FieldFilter
sys.modules['google.cloud.firestore_v1'].FieldFilter = _FieldFilter
sys.modules['google.cloud.firestore_v1.base_query'].FieldFilter = _FieldFilter
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

# Stub firestore client singleton.
client_stub = types.ModuleType('database._client')
client_stub.db = MagicMock()
sys.modules['database._client'] = client_stub


from database import action_items as action_items_db  # noqa: E402

# ---------------------------------------------------------------------------
# create_action_item — db layer
# ---------------------------------------------------------------------------


def _make_doc(doc_id, data=None):
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data or {}
    return doc


def _stub_collection(monkeypatch, existing_docs):
    """Stub db.collection('users').document(uid).collection('action_items').

    Returns a tuple ``(action_items_ref, captured)`` where ``captured`` is a
    dict that records add() calls for assertions.
    """
    captured = {'added': []}

    fake_query = MagicMock()
    # Chain: .where(...).where(...).limit(N).stream() — every intermediate
    # call returns the same fake so we don't have to model a query builder.
    fake_query.where.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.stream.return_value = iter(existing_docs)

    fake_action_items_ref = MagicMock()
    fake_action_items_ref.where.return_value = fake_query

    def _add(payload):
        captured['added'].append(payload)
        ref = MagicMock()
        ref.id = 'newly-created-id'
        return (None, ref)

    fake_action_items_ref.add.side_effect = _add

    fake_user_doc = MagicMock()
    fake_user_doc.collection.return_value = fake_action_items_ref

    fake_users = MagicMock()
    fake_users.document.return_value = fake_user_doc

    monkeypatch.setattr(action_items_db, 'db', MagicMock(collection=MagicMock(return_value=fake_users)))
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


# ---------------------------------------------------------------------------
# router-layer content key
# ---------------------------------------------------------------------------


def _import_router_helper():
    """Routers depend on a lot of upstream modules; stub the heaviest so the
    helper can be imported without real Firestore/Pinecone/Redis."""

    for mod_name in [
        'utils',
        'utils.executors',
        'utils.users',
        'utils.other',
        'utils.other.endpoints',
        'utils.notifications',
        'utils.task_sync',
        'database.conversations',
        'database.redis_db',
        'database.vector_db',
    ]:
        _ensure_module(mod_name)

    sys.modules['utils.executors'].critical_executor = MagicMock()
    sys.modules['utils.executors'].db_executor = MagicMock()
    sys.modules['utils.users'].get_user_display_name = lambda *a, **k: ''
    sys.modules['utils.other.endpoints'].get_current_user_uid = lambda: ''
    sys.modules['utils.other'].endpoints = sys.modules['utils.other.endpoints']
    sys.modules['utils.notifications'].send_notification = lambda *a, **k: None
    sys.modules['utils.notifications'].send_action_item_data_message = lambda *a, **k: None
    sys.modules['utils.notifications'].send_action_item_update_message = lambda *a, **k: None
    sys.modules['utils.notifications'].send_action_item_deletion_message = lambda *a, **k: None
    sys.modules['utils.notifications'].send_action_items_batch_deletion_message = lambda *a, **k: None
    sys.modules['utils.notifications'].sync_action_item_reminder = lambda *a, **k: None
    sys.modules['utils.task_sync'].auto_sync_action_item = lambda *a, **k: None
    sys.modules['database.vector_db'].upsert_action_item_vector = lambda *a, **k: None
    sys.modules['database.vector_db'].upsert_action_item_vectors_batch = lambda *a, **k: None
    sys.modules['database.vector_db'].delete_action_item_vector = lambda *a, **k: None
    sys.modules['database.vector_db'].delete_action_item_vectors_batch = lambda *a, **k: None
    sys.modules['database.vector_db'].search_action_items_by_vector = lambda *a, **k: []

    from routers import action_items as action_items_router

    return action_items_router


def test_content_key_is_stable_for_same_input():
    router = _import_router_helper()
    a = router._content_idempotency_key('uid-1', 'Buy milk')
    b = router._content_idempotency_key('uid-1', 'Buy milk')
    assert a == b


def test_content_key_normalizes_case_and_whitespace():
    router = _import_router_helper()
    a = router._content_idempotency_key('uid-1', 'Buy Milk')
    b = router._content_idempotency_key('uid-1', '  buy milk  ')
    assert a == b


def test_content_key_separates_users():
    router = _import_router_helper()
    a = router._content_idempotency_key('uid-1', 'Buy milk')
    b = router._content_idempotency_key('uid-2', 'Buy milk')
    assert a != b


def test_content_key_separates_descriptions():
    router = _import_router_helper()
    a = router._content_idempotency_key('uid-1', 'Buy milk')
    b = router._content_idempotency_key('uid-1', 'Buy bread')
    assert a != b


def test_content_key_avoids_separator_collision():
    """Length-prefixed encoding must distinguish (uid='org', desc='user:task')
    from (uid='org:user', desc='task'). A naive ``f"{uid}:{desc}"`` encoding
    would collapse both to the same hash; the length prefix prevents this."""
    router = _import_router_helper()
    a = router._content_idempotency_key('org', 'user:task')
    b = router._content_idempotency_key('org:user', 'task')
    assert a != b
