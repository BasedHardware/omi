"""Deterministic reproduction test for missing @after_write / dream_dirty signal on action item deletions.

In database/action_items.py:
`create_action_item`, `create_action_items_batch`, `update_action_item`, and `restore_channel_write`
are all decorated with `@after_write('action_items')` to notify the dream memory/reflection subsystem
(`database.dream_dirty.notify` -> `database.dream_store.mark_dirty`) of state mutations.

However, `delete_action_item`, `delete_action_items_batch`, and `delete_action_items_for_conversation`
previously omitted the dream dirty signal. When action items are deleted, the dream agent never receives
a dirty-state signal, leading to desynchronized memories and autonomous reflection loops acting on stale/deleted tasks.

This suite stubs bump_action_items_list_version and _purge_proactivity_source to keep all tests 100% hermetic.
"""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'test-key')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest
import database.action_items as action_items_db


class _FakeDocRef:
    def __init__(self, doc_id: str, exists: bool = True):
        self.id = doc_id
        self._exists = exists

    def get(self):
        mock_snapshot = MagicMock()
        mock_snapshot.exists = self._exists
        mock_snapshot.id = self.id
        return mock_snapshot

    def delete(self):
        pass


class _FakeDoc:
    def __init__(self, doc_id: str):
        self.id = doc_id
        self.reference = _FakeDocRef(doc_id, exists=True)


class _FakeCollection:
    def __init__(self, existing_ids: set[str]):
        self.existing_ids = existing_ids

    def document(self, doc_id: str):
        return _FakeDocRef(doc_id, exists=(doc_id in self.existing_ids))

    def where(self, *args, **kwargs):
        return self

    def stream(self):
        return [_FakeDoc(doc_id) for doc_id in sorted(self.existing_ids)]


class _FakeDB:
    def __init__(self, existing_ids: set[str]):
        self.existing_ids = existing_ids

    def collection(self, name: str):
        col_mock = MagicMock()
        col_mock.document.return_value.collection.return_value = _FakeCollection(self.existing_ids)
        return col_mock

    def batch(self):
        batch_mock = MagicMock()
        batch_mock.delete.return_value = None
        batch_mock.commit.return_value = None
        return batch_mock

    def transaction(self):
        return MagicMock()


@pytest.fixture(autouse=True)
def _stub_dependencies(monkeypatch: pytest.MonkeyPatch):
    """Keep tests hermetic by stubbing Redis and proactivity purge."""
    monkeypatch.setattr(action_items_db, 'bump_action_items_list_version', lambda uid: None)
    monkeypatch.setattr(action_items_db, '_purge_proactivity_source', lambda uid, item_id: None)


def test_delete_action_item_triggers_dream_dirty_signal(monkeypatch: pytest.MonkeyPatch):
    """delete_action_item must signal dream_dirty when deleting an existing action item."""
    fake_db = _FakeDB(existing_ids={'task-123'})
    monkeypatch.setattr(action_items_db, 'db', fake_db)
    monkeypatch.setattr('database.dream_dirty.mode', lambda: 'on')

    with patch('database.dream_dirty.mark_dirty') as mock_mark_dirty:
        success = action_items_db.delete_action_item('uid-user-1', 'task-123')
        assert success is True

        mock_mark_dirty.assert_called_once_with('uid-user-1', [('action_items', 'task-123')])


def test_delete_action_items_batch_triggers_dream_dirty_signal(monkeypatch: pytest.MonkeyPatch):
    """delete_action_items_batch must signal dream_dirty with all deleted item IDs."""
    fake_db = _FakeDB(existing_ids={'task-1', 'task-2'})
    monkeypatch.setattr(action_items_db, 'db', fake_db)
    monkeypatch.setattr('database.dream_dirty.mode', lambda: 'on')

    with patch('database.dream_dirty.mark_dirty') as mock_mark_dirty:
        deleted = action_items_db.delete_action_items_batch('uid-user-1', ['task-1', 'task-2'])
        assert deleted == ['task-1', 'task-2']

        mock_mark_dirty.assert_called_once_with('uid-user-1', [('action_items', 'task-1'), ('action_items', 'task-2')])


def test_delete_action_item_nonexistent_does_not_signal_dirty(monkeypatch: pytest.MonkeyPatch):
    """delete_action_item returning False (item does not exist) must not signal dream_dirty."""
    fake_db = _FakeDB(existing_ids=set())
    monkeypatch.setattr(action_items_db, 'db', fake_db)
    monkeypatch.setattr('database.dream_dirty.mode', lambda: 'on')

    with patch('database.dream_dirty.mark_dirty') as mock_mark_dirty:
        success = action_items_db.delete_action_item('uid-user-1', 'nonexistent-task')
        assert success is False
        mock_mark_dirty.assert_not_called()


def test_delete_action_items_for_conversation_triggers_dream_dirty_signal(monkeypatch: pytest.MonkeyPatch):
    """delete_action_items_for_conversation must notify dream_dirty with the deleted item IDs."""
    fake_db = _FakeDB(existing_ids={'task-conv-1', 'task-conv-2'})
    monkeypatch.setattr(action_items_db, 'db', fake_db)
    monkeypatch.setattr('database.dream_dirty.mode', lambda: 'on')

    with patch('database.dream_dirty.mark_dirty') as mock_mark_dirty:
        total = action_items_db.delete_action_items_for_conversation('uid-user-1', 'conv-100')
        assert total == 2

        mock_mark_dirty.assert_called_once_with(
            'uid-user-1', [('action_items', 'task-conv-1'), ('action_items', 'task-conv-2')]
        )
