"""Apple Reminders export must settle the sync request, or the pending-sync read starves.

Extraction sets ``sync_requested=True`` on every task of an Apple Reminders user and
sends a silent push; the device reports the finished export through the single-item
``PATCH /v1/action-items/{id}`` with ``exported=True``. Only the sync-batch route cleared
the flag, so every exported task stayed a "pending" candidate. ``GET
/v1/action-items/pending-sync`` reads 50 ``sync_requested`` rows and discards the
exported ones in Python, so once 50 settled rows sort ahead of a task whose push was
missed, that task is never returned and never reaches Apple Reminders.
"""

from unittest.mock import MagicMock, patch

import database.action_items as action_items_db
from models.action_item import ActionItemUpdateRequest


class _Snapshot:
    def __init__(self, store, doc_id):
        self._store, self.id = store, doc_id
        self.exists = doc_id in store
        self.reference = _DocRef(store, doc_id)

    def to_dict(self):
        return dict(self._store[self.id]) if self.exists else None


class _DocRef:
    def __init__(self, store, doc_id):
        self._store, self.id = store, doc_id

    def get(self, **_):
        return _Snapshot(self._store, self.id)

    def update(self, data):
        self._store[self.id].update(data)


class _Query:
    """Equality filters, then limit, in Firestore's default ``__name__`` order."""

    def __init__(self, store, filters=(), limit=None):
        self._store, self._filters, self._limit = store, tuple(filters), limit

    def where(self, filter):
        return _Query(self._store, self._filters + ((filter.field_path, filter.value),), self._limit)

    def limit(self, count):
        return _Query(self._store, self._filters, count)

    def stream(self, **_):
        rows = [
            _Snapshot(self._store, doc_id)
            for doc_id in sorted(self._store)
            if all(self._store[doc_id].get(field) == value for field, value in self._filters)
        ]
        return iter(rows[: self._limit] if self._limit is not None else rows)

    def document(self, doc_id):
        return _DocRef(self._store, doc_id)


class _FakeDb:
    def __init__(self, items):
        self.store = {doc_id: dict(data) for doc_id, data in items.items()}

    def collection(self, _name):
        user_doc = MagicMock()
        user_doc.collection.return_value = _Query(self.store)
        users = MagicMock()
        users.document.return_value = user_doc
        return users


def _exported(index):
    return {
        'description': f'old {index}',
        'completed': False,
        'sync_requested': True,
        'exported': True,
        'export_platform': 'apple_reminders',
        'apple_reminder_id': f'r{index}',
    }


def test_single_item_export_clears_sync_requested():
    fake = _FakeDb({'t1': {'description': 'x', 'completed': False, 'sync_requested': True}})
    payload = ActionItemUpdateRequest(
        exported=True, export_platform='apple_reminders', apple_reminder_id='r1'
    ).storage_payload()

    with patch.object(action_items_db, 'db', fake), patch.object(action_items_db, 'bump_action_items_list_version'):
        assert action_items_db.update_action_item('u1', 't1', payload) is True

    assert fake.store['t1']['exported'] is True
    assert fake.store['t1']['sync_requested'] is False


def test_update_without_export_leaves_sync_requested_alone():
    fake = _FakeDb({'t1': {'description': 'x', 'completed': False, 'sync_requested': True}})

    with patch.object(action_items_db, 'db', fake), patch.object(action_items_db, 'bump_action_items_list_version'):
        action_items_db.update_action_item('u1', 't1', {'description': 'renamed'})

    assert fake.store['t1']['sync_requested'] is True


def test_pending_sync_returns_a_missed_task_behind_fifty_settled_rows_and_settles_them():
    items = {f'a{index:03d}': _exported(index) for index in range(50)}
    items['z-new'] = {'description': 'needs export', 'completed': False, 'sync_requested': True}
    fake = _FakeDb(items)

    with patch.object(action_items_db, 'db', fake):
        first = action_items_db.get_pending_apple_reminders_sync('u1')
        second = action_items_db.get_pending_apple_reminders_sync('u1')

    assert all(fake.store[f'a{index:03d}']['sync_requested'] is False for index in range(50))
    assert [item['id'] for item in second['pending_export']] == ['z-new']
    assert fake.store['z-new']['sync_requested'] is True
    # The first read still returned nothing; it settled the rows so the second could.
    assert first['pending_export'] == []


def test_an_explicit_sync_requested_in_the_same_update_is_kept():
    """Reprocess markers may set exported and sync_requested together; the caller's value wins."""
    fake = _FakeDb({'t1': {'description': 'x', 'completed': False, 'sync_requested': False}})

    with patch.object(action_items_db, 'db', fake), patch.object(action_items_db, 'bump_action_items_list_version'):
        action_items_db.update_action_item(
            'u1', 't1', {'exported': True, 'export_platform': 'asana', 'sync_requested': True}
        )

    assert fake.store['t1']['sync_requested'] is True
