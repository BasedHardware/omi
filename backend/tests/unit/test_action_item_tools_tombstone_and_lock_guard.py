"""Unit tests for paywall (`is_locked: True`) and soft-delete tombstone (`deleted: True`) guards
across `action_item_tools.py`, `tool_services/action_items.py`, and `database/chat_edits.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from database import chat_edits, notifications as notification_db
from utils.retrieval.tool_services import action_items as service
from utils.retrieval.tools import action_item_tools as tools


def _make_item(
    item_id: str = 'task-1',
    *,
    description: str = 'Task description',
    deleted: bool = False,
    locked: bool = False,
    completed: bool = False,
) -> dict:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return {
        'id': item_id,
        'description': description,
        'completed': completed,
        'deleted': deleted,
        'is_locked': locked,
        'created_at': now,
        'updated_at': now,
        'due_at': None,
        'completed_at': None,
        'conversation_id': None,
    }


@pytest.fixture
def patched_env(monkeypatch):
    monkeypatch.setattr(notification_db, 'get_user_time_zone', lambda *_: 'UTC')
    monkeypatch.setattr(chat_edits, 'snapshot', MagicMock(return_value={'completed': False}))
    monkeypatch.setattr(chat_edits, 'envelope', lambda snapshot, summary: {'_snapshot': snapshot, '_summary': summary})
    monkeypatch.setattr(tools, 'record_write', MagicMock(return_value=''))
    for target in (tools, service):
        for name in (
            'send_action_item_completed_notification',
            'send_action_item_created_notification',
            'send_action_item_data_message',
            'sync_action_item_reminder',
        ):
            if hasattr(target, name):
                monkeypatch.setattr(target, name, MagicMock())


class TestActionItemToolsLockAndTombstoneGuards:
    """LangChain chat tools (`action_item_tools.py`) must withhold locked and soft-deleted tasks."""

    def test_get_action_items_tool_excludes_locked_and_deleted_items(self, patched_env, monkeypatch):
        items = [
            _make_item('locked-1', description='Secret locked task payload', locked=True),
            _make_item('deleted-1', description='Deleted tombstone payload', deleted=True),
            _make_item('visible-1', description='Visible active task'),
        ]
        monkeypatch.setattr(tools.action_items_db, 'get_action_items', lambda **kwargs: list(items))

        channel_items: list[dict] = []
        config = {'configurable': {'user_id': 'uid-1', 'channel_items': channel_items}}
        out = tools.get_action_items_tool.func(config=config)

        assert 'Visible active task' in out
        assert 'Secret locked task payload' not in out
        assert 'Deleted tombstone payload' not in out
        assert [c['id'] for c in channel_items] == ['visible-1']

    def test_get_action_items_tool_returns_empty_message_when_all_items_locked_or_deleted(
        self, patched_env, monkeypatch
    ):
        items = [
            _make_item('locked-1', description='Secret locked task', locked=True),
            _make_item('deleted-1', description='Deleted tombstone', deleted=True),
        ]
        monkeypatch.setattr(tools.action_items_db, 'get_action_items', lambda **kwargs: list(items))

        channel_items: list[dict] = []
        config = {'configurable': {'user_id': 'uid-1', 'channel_items': channel_items}}
        out = tools.get_action_items_tool.func(config=config)

        assert out == 'No action items found.'
        assert channel_items == []

    def test_update_action_item_tool_rejects_deleted_tombstone(self, patched_env, monkeypatch):
        monkeypatch.setattr(
            tools.action_items_db,
            'get_action_item',
            lambda uid, item_id: _make_item(item_id, deleted=True),
        )
        mock_update = MagicMock(return_value=True)
        monkeypatch.setattr(tools.action_items_db, 'update_action_item', mock_update)

        config = {'configurable': {'user_id': 'uid-1'}}
        out = tools.update_action_item_tool.func('deleted-1', completed=True, config=config)

        assert "Action item with ID 'deleted-1' not found" in out
        mock_update.assert_not_called()

    def test_update_action_item_tool_rejects_locked_item(self, patched_env, monkeypatch):
        monkeypatch.setattr(
            tools.action_items_db,
            'get_action_item',
            lambda uid, item_id: _make_item(item_id, locked=True),
        )
        mock_update = MagicMock(return_value=True)
        monkeypatch.setattr(tools.action_items_db, 'update_action_item', mock_update)

        config = {'configurable': {'user_id': 'uid-1'}}
        out = tools.update_action_item_tool.func('locked-1', description='Hijacked', config=config)

        assert out == 'Error: A paid plan is required to modify this action item.'
        mock_update.assert_not_called()


class TestActionItemsToolServiceLockAndTombstoneGuards:
    """Shared tool service (`tool_services/action_items.py`) must reject soft-deleted tombstones."""

    def test_get_action_items_text_excludes_deleted_and_locked_items(self, patched_env, monkeypatch):
        items = [
            _make_item('deleted-1', description='Tombstone task', deleted=True),
            _make_item('locked-1', description='Locked task', locked=True),
            _make_item('active-1', description='Live task'),
        ]
        monkeypatch.setattr(service.action_items_db, 'get_action_items', lambda **kwargs: list(items))

        source_sink: list[dict] = []
        out = service.get_action_items_text('uid-1', source_sink=source_sink)

        assert 'Live task' in out
        assert 'Tombstone task' not in out
        assert 'Locked task' not in out
        assert [s['source_id'] for s in source_sink] == ['active-1']

    def test_update_action_item_text_rejects_deleted_tombstone(self, patched_env, monkeypatch):
        monkeypatch.setattr(
            service.action_items_db,
            'get_action_item',
            lambda uid, item_id: _make_item(item_id, deleted=True),
        )
        mock_update = MagicMock(return_value=True)
        monkeypatch.setattr(service.action_items_db, 'update_action_item', mock_update)

        out = service.update_action_item_text('uid-1', 'deleted-1', completed=True)

        assert out == "Error: Action item 'deleted-1' not found."
        mock_update.assert_not_called()


class TestChatEditsDeletedTaskTombstoneFence:
    """`chat_edits.apply_update` must block overwriting already soft-deleted task tombstones while allowing soft-delete of live tasks."""

    def _make_fake_client(self, stored_doc: dict):
        state = {'doc': dict(stored_doc), 'updated_with': None}

        class FakeSnapshot:
            exists = True

            def to_dict(self):
                return dict(state['doc'])

        class FakeRef:
            def get(self, transaction=None):
                return FakeSnapshot()

            def collection(self, name):
                return self

            def document(self, doc_id):
                return self

        class FakeTx:
            def update(self, ref, updates):
                state['updated_with'] = dict(updates)
                state['doc'].update(updates)

        class FakeClient:
            def collection(self, name):
                return FakeRef()

            def transaction(self):
                return FakeTx()

        return FakeClient(), state

    def test_apply_update_rejects_already_deleted_task_tombstone(self, monkeypatch):
        monkeypatch.setattr(chat_edits.firestore, 'transactional', lambda fn: fn)
        monkeypatch.setattr(
            chat_edits,
            'run_with_transaction_contention_retry',
            lambda tx_factory, fn, operation_name=None: fn(tx_factory()),
        )
        tombstone = {'description': 'Old task', 'completed': False, 'deleted': True}
        client, state = self._make_fake_client(tombstone)
        expected = chat_edits.encode(tombstone)

        with pytest.raises(PermissionError, match='Edit target unavailable'):
            chat_edits.apply_update(
                'uid-1',
                'task',
                'task-1',
                expected,
                {'description': 'Resurrected task', 'completed': True},
                firestore_client=client,
            )
        assert state['updated_with'] is None

    def test_apply_update_allows_soft_deleting_live_task(self, monkeypatch):
        monkeypatch.setattr(chat_edits.firestore, 'transactional', lambda fn: fn)
        monkeypatch.setattr(
            chat_edits,
            'run_with_transaction_contention_retry',
            lambda tx_factory, fn, operation_name=None: fn(tx_factory()),
        )
        live_task = {'description': 'Live task', 'completed': False}
        client, state = self._make_fake_client(live_task)
        expected = chat_edits.encode(live_task)
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)

        after = chat_edits.apply_update(
            'uid-1',
            'task',
            'task-1',
            expected,
            {'deleted': True, 'deleted_at': now},
            firestore_client=client,
        )
        assert state['updated_with'] == {'deleted': True, 'deleted_at': now}
        assert chat_edits.decode(after)['deleted'] is True
