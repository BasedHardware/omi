"""Regression test for database.action_items.batch_update_action_items.

PATCH /v1/action-items/batch (router batch_update_action_items) forwards the
client-supplied list of {id, sort_order, indent_level} straight into the db
helper, which issued ``batch.update(doc_ref, ...)`` for every id with no
existence check. In Firestore, ``batch.update()`` on a document that does not
exist raises ``google.api_core.exceptions.NotFound`` when the batch commits —
so a single stale/deleted id supplied by a client 500s the whole batch and
drops every other (valid) reorder in the request.

The fix pre-filters the requested ids to those that actually exist via
``db.get_all`` (the same existence-batch pattern used by
``folders.bulk_move_conversations_to_folder``) and skips missing ids, so one
stale id no longer poisons the batch.

This test models a faithful Firestore: ``batch.update`` records its target
doc refs and ``batch.commit`` raises NotFound if any update targeted a doc the
backing store does not contain (matching real commit-time behavior). It also
asserts ``batch.update`` is invoked only for the existing id.

Red (pre-fix): missing id flows to batch.update -> commit raises NotFound.
Green (post-fix): missing id is filtered out -> no NotFound, only valid id updated.
"""

import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Pre-stub the heavy deps that database.action_items imports at module top
# (google.cloud.firestore + the Firestore client singleton in database._client)
# so the real module loads without touching Firestore. Same pattern as
# tests/unit/test_action_item_idempotency.py.
for _mod_name in [
    'firebase_admin',
    'firebase_admin.auth',
    'google',
    'google.cloud',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)

sys.modules['google.cloud.firestore'].Client = MagicMock
sys.modules['google.cloud.firestore'].SERVER_TIMESTAMP = object()
sys.modules['google.cloud.firestore'].Query = MagicMock()
sys.modules['google.cloud.firestore'].FieldFilter = MagicMock
sys.modules['google.cloud.firestore_v1'].FieldFilter = MagicMock
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

# Stub the Firestore client singleton; the real module does `from ._client import db`.
_client_stub = types.ModuleType('database._client')
_client_stub.db = MagicMock()
sys.modules['database._client'] = _client_stub

# Ensure the real `database` package (with its on-disk __path__) is importable so
# `database.action_items` resolves to the real source, not a stub. Drop any cached
# stub of the submodule so the real one loads.
_database_pkg = sys.modules.get('database')
if _database_pkg is None or not getattr(_database_pkg, '__path__', None):
    _database_pkg = types.ModuleType('database')
    _database_pkg.__path__ = [os.path.join(_BACKEND_DIR, 'database')]
    sys.modules['database'] = _database_pkg
sys.modules.pop('database.action_items', None)

# Import the real module under test. Importing as `database.action_items` (rather
# than from a file with a bare name) keeps its `from ._client import db` relative
# import resolvable against the stubbed database._client above.
from database import action_items as mod  # noqa: E402


class _FakeNotFound(Exception):
    """Stand-in for google.api_core.exceptions.NotFound (commit-time error)."""


class _Item:
    """Minimal stand-in for BatchUpdateActionItemEntry."""

    def __init__(self, id, sort_order=None, indent_level=None):
        self.id = id
        self.sort_order = sort_order
        self.indent_level = indent_level


class _FakeBatch:
    def __init__(self, existing_ids):
        self._existing_ids = existing_ids
        self.updated_ids = []
        self.commits = 0

    def update(self, doc_ref, data):
        # Record which document id this update targeted.
        self.updated_ids.append(doc_ref._doc_id)

    def commit(self):
        self.commits += 1
        # Real Firestore raises NotFound at commit if any update targeted a
        # document that does not exist.
        for doc_id in self.updated_ids:
            if doc_id not in self._existing_ids:
                raise _FakeNotFound(f"No document to update: {doc_id}")


class _FakeDocRef:
    def __init__(self, doc_id):
        self._doc_id = doc_id


class _FakeDocSnapshot:
    def __init__(self, doc_id, exists):
        self.id = doc_id
        self.exists = exists


class _FakeCollection:
    def document(self, doc_id):
        return _FakeDocRef(doc_id)


def _build_db(existing_ids):
    """Build a fake `db` whose collection('action_items') resolves doc refs and
    whose get_all reports only `existing_ids` as existing."""
    collection = _FakeCollection()

    user_doc = MagicMock()
    user_doc.collection.return_value = collection

    users = MagicMock()
    users.document.return_value = user_doc

    fake_batch = _FakeBatch(existing_ids)

    db = MagicMock()
    db.collection.return_value = users
    db.batch.return_value = fake_batch

    def _get_all(doc_refs):
        return [_FakeDocSnapshot(ref._doc_id, ref._doc_id in existing_ids) for ref in doc_refs]

    db.get_all.side_effect = _get_all
    return db, fake_batch


def test_missing_id_does_not_raise_not_found(monkeypatch):
    """A client-supplied id that does not exist must not 500 the batch."""
    existing_ids = {'exists-1'}
    db, fake_batch = _build_db(existing_ids)
    monkeypatch.setattr(mod, 'db', db)

    items = [
        _Item('exists-1', sort_order=1, indent_level=0),
        _Item('missing-1', sort_order=2, indent_level=0),  # stale / deleted id
    ]

    # Pre-fix: 'missing-1' reaches batch.update -> commit raises _FakeNotFound.
    # Post-fix: 'missing-1' is filtered out via db.get_all and skipped.
    mod.batch_update_action_items('uid', items)

    # Only the existing id should have been written.
    assert fake_batch.updated_ids == [
        'exists-1'
    ], f"batch.update must run only for existing ids, got {fake_batch.updated_ids}"


def test_all_missing_ids_commits_nothing(monkeypatch):
    """If every requested id is missing, the helper must be a clean no-op."""
    db, fake_batch = _build_db(existing_ids=set())
    monkeypatch.setattr(mod, 'db', db)

    items = [_Item('gone-1', sort_order=1), _Item('gone-2', indent_level=2)]

    mod.batch_update_action_items('uid', items)

    assert fake_batch.updated_ids == []


def test_valid_ids_still_updated(monkeypatch):
    """Regression guard: the happy path (all ids exist) still updates each."""
    existing_ids = {'a', 'b'}
    db, fake_batch = _build_db(existing_ids)
    monkeypatch.setattr(mod, 'db', db)

    items = [_Item('a', sort_order=1), _Item('b', indent_level=3)]

    mod.batch_update_action_items('uid', items)

    assert sorted(fake_batch.updated_ids) == ['a', 'b']
    assert fake_batch.commits >= 1
