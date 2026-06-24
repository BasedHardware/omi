"""Regression test for database.action_items.batch_sync_update_action_items.

PATCH /v1/action-items/sync-batch funnels reminder-sync updates into
``batch_sync_update_action_items``. Firestore's ``batch.update()`` raises a
``NotFound`` for a document that does not exist, and the failure surfaces at
``batch.commit()`` — so a single stale/deleted reminder id supplied by the
client would 500 the entire sync batch (dropping every other update in it).

The router pre-fetch only flags *locked* items; genuinely MISSING ids still
flowed straight into ``batch.update``. The fix pre-filters the entries to
documents that actually exist (via ``db.get_all``) and skips the rest.

This test drives the db helper directly with a mix of existing and missing ids
and asserts:
  * no NotFound escapes (no 500), and
  * ``batch.update`` is invoked only for the ids that exist.

Red (pre-fix): ``batch.update`` is called for the missing id, the fake batch
raises NotFound exactly like Firestore, and the call blows up.

Import bootstrap mirrors test_action_item_idempotency.py: stub the heavy
``database._client`` singleton and the ``google.cloud.firestore*`` modules,
then import the real ``database.action_items``.
"""

import sys
import types
from unittest.mock import MagicMock


def _ensure_module(name):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
    return sys.modules[name]


for _mod_name in [
    'firebase_admin',
    'firebase_admin.auth',
    'google',
    'google.cloud',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.base_query',
]:
    _ensure_module(_mod_name)


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

# Stub the firestore client singleton so importing the module does not init
# real credentials.
_client_stub = types.ModuleType('database._client')
_client_stub.db = MagicMock()
sys.modules['database._client'] = _client_stub


from database import action_items as mod  # noqa: E402


class _NotFound(Exception):
    """Stand-in for google.api_core.exceptions.NotFound (raised by Firestore
    when batch.update targets a document that does not exist)."""


class _DocRef:
    def __init__(self, doc_id):
        self.id = doc_id


class _Snapshot:
    def __init__(self, doc_id, exists):
        self.id = doc_id
        self.exists = exists
        self.reference = _DocRef(doc_id)


class _Collection:
    def document(self, doc_id):
        return _DocRef(doc_id)


class _FakeBatch:
    """A batch that mirrors Firestore: update() on a missing doc raises NotFound."""

    def __init__(self, existing_ids):
        self._existing = existing_ids
        self.updated_ids = []

    def update(self, doc_ref, data):
        if doc_ref.id not in self._existing:
            # Firestore reports the missing doc as a NotFound; raise it eagerly
            # at update() time so the test fails loudly without the existence
            # pre-filter (real Firestore surfaces it at commit()).
            raise _NotFound(f"No document to update: {doc_ref.id}")
        self.updated_ids.append(doc_ref.id)

    def commit(self):
        pass


class _PatchDb:
    """Context manager: swap module.db for a fake and restore it afterwards."""

    def __init__(self, module, fake_db):
        self._module = module
        self._fake = fake_db
        self._orig = None

    def __enter__(self):
        self._orig = self._module.db
        self._module.db = self._fake
        return self._fake

    def __exit__(self, *exc):
        self._module.db = self._orig
        return False


def _make_db(existing_ids):
    existing_ids = set(existing_ids)
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value = _Collection()

    batch = _FakeBatch(existing_ids)
    db.batch.return_value = batch

    def _get_all(refs):
        return [_Snapshot(ref.id, ref.id in existing_ids) for ref in refs]

    db.get_all.side_effect = _get_all
    return db, batch


def test_missing_id_does_not_blow_up_the_sync_batch():
    """A deleted/stale id mixed with valid ids must not raise NotFound and must
    not be sent to batch.update; the valid ids still get updated."""
    existing = {'alive-1', 'alive-2'}
    updates = [
        {'id': 'alive-1', 'data': {'exported': True}},
        {'id': 'ghost', 'data': {'exported': True}},  # does not exist anymore
        {'id': 'alive-2', 'data': {'sort_order': 3}},
    ]

    db, batch = _make_db(existing)
    with _PatchDb(mod, db):
        # Must not raise NotFound on the missing 'ghost' id.
        mod.batch_sync_update_action_items('uid-xyz', updates)

    # Only the existing ids were written.
    assert set(batch.updated_ids) == existing
    assert 'ghost' not in batch.updated_ids


def test_all_missing_ids_commit_nothing():
    """If every id is missing, nothing is updated and no error is raised."""
    db, batch = _make_db(set())
    updates = [
        {'id': 'gone-1', 'data': {'exported': True}},
        {'id': 'gone-2', 'data': {'exported': True}},
    ]

    with _PatchDb(mod, db):
        mod.batch_sync_update_action_items('uid-xyz', updates)

    assert batch.updated_ids == []


def test_all_existing_ids_all_updated():
    """Sanity: when every id exists, every entry is written (no over-filtering)."""
    existing = {'a', 'b', 'c'}
    updates = [{'id': i, 'data': {'exported': True}} for i in ['a', 'b', 'c']]

    db, batch = _make_db(existing)
    with _PatchDb(mod, db):
        mod.batch_sync_update_action_items('uid-xyz', updates)

    assert set(batch.updated_ids) == existing
