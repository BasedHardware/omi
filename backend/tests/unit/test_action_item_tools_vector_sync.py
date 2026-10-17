"""Regression tests for action-item vector index synchronization across chat tools,
tool services, and chat undo.
"""

from datetime import datetime, timezone

import pytest

from database import chat_edits, vector_db
from utils.messaging import undo
from utils.retrieval.tool_services import action_items as action_item_service
from utils.retrieval.tools import action_item_tools, edit_tools

CONFIG = {'configurable': {'user_id': 'owner', 'chat_session_id': 'session', 'user_timezone': 'UTC'}}
FUTURE_DUE = '2099-10-11T12:00:00+00:00'


@pytest.fixture
def quiet_notifications(monkeypatch):
    for mod in (action_item_tools, action_item_service):
        monkeypatch.setattr(mod, 'send_action_item_created_notification', lambda *args, **kwargs: None)
        monkeypatch.setattr(mod, 'send_action_item_completed_notification', lambda *args, **kwargs: None)
        monkeypatch.setattr(mod, 'send_action_item_data_message', lambda *args, **kwargs: None)
        monkeypatch.setattr(mod, 'sync_action_item_reminder', lambda *args, **kwargs: None)
    monkeypatch.setattr(action_item_tools, 'record_write', lambda *args, **kwargs: '')


def test_create_action_item_tool_indexes_vector_and_survives_outage(monkeypatch, quiet_notifications):
    upserted = []
    created_row = {
        'id': 'task-1',
        'description': 'Send Q4 board deck',
        'completed': False,
        'due_at': None,
        'deleted': False,
    }
    monkeypatch.setattr(action_item_tools.action_items_db, 'create_action_item', lambda uid, data: 'task-1')
    monkeypatch.setattr(action_item_tools.action_items_db, 'get_action_item', lambda uid, item_id: dict(created_row))
    monkeypatch.setattr(
        action_item_tools,
        'upsert_action_item_vector',
        lambda uid, item_id, desc: upserted.append((uid, item_id, desc)),
    )

    result = action_item_tools.create_action_item_tool.func('  Send Q4 board deck  ', config=CONFIG)

    assert 'Added: Send Q4 board deck' in result
    assert upserted == [('owner', 'task-1', 'Send Q4 board deck')]

    def _boom(*args, **kwargs):
        raise RuntimeError('pinecone unavailable')

    monkeypatch.setattr(action_item_tools, 'upsert_action_item_vector', _boom)
    result_outage = action_item_tools.create_action_item_tool.func('Send Q4 board deck', config=CONFIG)
    assert 'Added: Send Q4 board deck' in result_outage


def test_update_action_item_tool_reindexes_on_description_and_deletes_vector_on_soft_delete(
    monkeypatch, quiet_notifications
):
    upserted = []
    deleted = []
    row = {
        'id': 'task-1',
        'description': 'Draft contract',
        'completed': False,
        'due_at': None,
        'deleted': False,
    }

    monkeypatch.setattr(action_item_tools.action_items_db, 'get_action_item', lambda uid, item_id: dict(row))
    monkeypatch.setattr(
        action_item_tools.action_items_db,
        'update_action_item',
        lambda uid, item_id, values, **kwargs: row.update(values)
        or kwargs['expected_chat_state'].update(after=chat_edits.encode(dict(row)))
        or True,
    )
    monkeypatch.setattr(chat_edits, 'snapshot', lambda *args: chat_edits.encode(dict(row)))
    monkeypatch.setattr(
        action_item_tools,
        'upsert_action_item_vector',
        lambda uid, item_id, desc: upserted.append((uid, item_id, desc)),
    )
    monkeypatch.setattr(
        action_item_tools,
        'delete_action_item_vector',
        lambda uid, item_id: deleted.append((uid, item_id)),
    )

    # Completion-only update must not re-embed the unchanged description
    res_complete = action_item_tools.update_action_item_tool.func('task-1', completed=True, config=CONFIG)
    assert 'Successfully updated' in res_complete
    assert upserted == []
    assert deleted == []

    # Description update must re-index with the updated description
    res_desc = action_item_tools.update_action_item_tool.func(
        'task-1', description='Finalize vendor contract', config=CONFIG
    )
    assert 'Successfully updated' in res_desc
    assert upserted == [('owner', 'task-1', 'Finalize vendor contract')]
    assert deleted == []

    # Soft-delete via update_action_item_tool(delete=True) must drop the vector
    res_delete = action_item_tools.update_action_item_tool.func('task-1', delete=True, config=CONFIG)
    assert 'Successfully updated' in res_delete
    assert deleted == [('owner', 'task-1')]


def test_tool_service_create_and_update_sync_vectors(monkeypatch, quiet_notifications):
    upserted = []
    deleted = []
    row = {
        'id': 'task-svc-1',
        'description': 'Review PR',
        'completed': False,
        'due_at': None,
        'deleted': False,
    }
    monkeypatch.setattr(action_item_service, 'clock_for_uid', lambda uid: None)
    monkeypatch.setattr(action_item_service.action_items_db, 'create_action_item', lambda uid, data: 'task-svc-1')
    monkeypatch.setattr(action_item_service.action_items_db, 'get_action_item', lambda uid, item_id: dict(row))
    monkeypatch.setattr(
        action_item_service.action_items_db,
        'update_action_item',
        lambda uid, item_id, values: row.update(values) or True,
    )
    monkeypatch.setattr(
        action_item_service,
        'upsert_action_item_vector',
        lambda uid, item_id, desc: upserted.append((uid, item_id, desc)),
    )
    monkeypatch.setattr(
        action_item_service,
        'delete_action_item_vector',
        lambda uid, item_id: deleted.append((uid, item_id)),
    )

    created_msg = action_item_service.create_action_item_text('owner', 'Review PR')
    assert 'Added: Review PR' in created_msg
    assert upserted == [('owner', 'task-svc-1', 'Review PR')]

    updated_msg = action_item_service.update_action_item_text('owner', 'task-svc-1', description='Review security PR')
    assert 'Updated' in updated_msg
    assert upserted[-1] == ('owner', 'task-svc-1', 'Review security PR')


def test_undo_apply_inverse_reconciles_task_vectors(monkeypatch):
    upserted = []
    deleted = []
    restored_state = {'id': 'task-1', 'description': 'Original task', 'completed': False, 'deleted': False}

    from database import action_items
    from utils import notifications

    monkeypatch.setattr(chat_edits, 'restore', lambda *args: None)
    monkeypatch.setattr(action_items, 'bump_action_items_list_version', lambda *args: None)
    monkeypatch.setattr(action_items, 'get_action_item', lambda uid, item_id: dict(restored_state))
    monkeypatch.setattr(action_items, 'restore_channel_write', lambda uid, item_id, after, before: True)
    monkeypatch.setattr(notifications, 'sync_action_item_reminder', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        vector_db,
        'upsert_action_item_vector',
        lambda uid, item_id, desc: upserted.append((uid, item_id, desc)),
    )
    monkeypatch.setattr(
        vector_db,
        'delete_action_item_vector',
        lambda uid, item_id: deleted.append((uid, item_id)),
    )

    # 1. Undoing a soft-delete restores the vector in Pinecone
    undo.apply_inverse(
        'owner',
        {
            'kind': 'task',
            'object_id': 'task-1',
            'before': edit_tools.envelope({'description': 'Original task', 'deleted': False}, 'Original task'),
            'after': edit_tools.envelope(
                {
                    'description': 'Original task',
                    'deleted': True,
                    'deleted_at': datetime.now(timezone.utc).isoformat(),
                },
                'Original task',
            ),
        },
    )
    assert upserted == [('owner', 'task-1', 'Original task')]
    assert deleted == []

    # 2. Undoing a description edit re-indexes the previous description
    upserted.clear()
    undo.apply_inverse(
        'owner',
        {
            'kind': 'task',
            'object_id': 'task-1',
            'before': edit_tools.envelope({'description': 'Original task', 'completed': False}, 'Original task'),
            'after': edit_tools.envelope({'description': 'Edited task', 'completed': False}, 'Edited task'),
        },
    )
    assert upserted == [('owner', 'task-1', 'Original task')]

    # 3. Undoing a completion-only edit does not re-embed unchanged description
    upserted.clear()
    undo.apply_inverse(
        'owner',
        {
            'kind': 'task',
            'object_id': 'task-1',
            'before': edit_tools.envelope({'description': 'Original task', 'completed': False}, 'Original task'),
            'after': edit_tools.envelope({'description': 'Original task', 'completed': True}, 'Original task'),
        },
    )
    assert upserted == []
    assert deleted == []

    # 4. Undoing a channel task creation (before=None) deletes the task's vector
    undo.apply_inverse(
        'owner',
        {
            'kind': 'task',
            'object_id': 'task-created-1',
            'before': None,
            'after': {'id': 'task-created-1', 'description': 'Created in chat', 'completed': False},
        },
    )
    assert deleted == [('owner', 'task-created-1')]
