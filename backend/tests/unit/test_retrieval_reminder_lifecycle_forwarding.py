"""Real retrieval producers must pass saved lifecycle state to the reminder gate."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest
from database import chat_edits, notifications as notification_db
from utils.retrieval.tool_services import action_items as service
from utils.retrieval.tools import action_item_tools as tools

DUE = datetime(2099, 10, 9, 17, tzinfo=timezone.utc)


@pytest.fixture(params=['service', 'tool'])
def producer(request, monkeypatch):
    def update(*args, **kwargs):
        if 'expected_chat_state' in kwargs:
            kwargs['expected_chat_state']['after'] = dict(args[2])
        return True

    database = SimpleNamespace(
        create_action_item=MagicMock(return_value='task-1'),
        get_action_item=MagicMock(),
        get_action_items=MagicMock(return_value=[]),
        update_action_item=MagicMock(side_effect=update),
    )
    notifications = SimpleNamespace()
    for name in (
        'send_action_item_completed_notification',
        'send_action_item_created_notification',
        'send_action_item_data_message',
        'sync_action_item_reminder',
    ):
        sender = MagicMock()
        setattr(notifications, name, sender)
        monkeypatch.setattr(service, name, sender)
        monkeypatch.setattr(tools, name, sender)
    monkeypatch.setattr(service, 'action_items_db', database)
    monkeypatch.setattr(tools, 'action_items_db', database)
    monkeypatch.setattr(notification_db, 'get_user_time_zone', lambda *_: 'UTC')
    monkeypatch.setattr(chat_edits, 'snapshot', MagicMock(return_value={'completed': False}))
    monkeypatch.setattr(chat_edits, 'envelope', lambda snapshot, summary: {'_snapshot': snapshot, '_summary': summary})
    monkeypatch.setattr(tools, 'record_write', MagicMock(return_value=''))
    module = (
        service
        if request.param == 'service'
        else SimpleNamespace(
            create_action_item_tool=tools.create_action_item_tool.func,
            update_action_item_tool=tools.update_action_item_tool.func,
        )
    )
    return request.param, module, database, notifications


def _create(kind, module):
    if kind == 'service':
        return module.create_action_item_text('u1', 'Requested task', due_at=DUE.isoformat())
    return module.create_action_item_tool(
        'Requested task', due_at=DUE.isoformat(), config={'configurable': {'user_id': 'u1'}}
    )


def _update(kind, module, **changes):
    if kind == 'service':
        return module.update_action_item_text('u1', 'task-1', **changes)
    return module.update_action_item_tool('task-1', **changes, config={'configurable': {'user_id': 'u1'}})


@pytest.mark.parametrize(
    'status,completed,deleted',
    [
        ('active', False, False),
        ('cancelled', False, False),
        ('superseded', False, False),
        ('completed', True, False),
        ('active', False, True),
    ],
)
def test_create_forwards_persisted_lifecycle_instead_of_assuming_open(producer, status, completed, deleted):
    kind, module, database, notifications = producer
    database.get_action_item.return_value = {
        'id': 'task-1',
        'description': 'Saved task',
        'due_at': DUE,
        'completed': completed,
        'status': status,
        'deleted': deleted,
    }
    assert 'Added' in _create(kind, module)
    notifications.send_action_item_data_message.assert_called_once_with(
        user_id='u1',
        action_item_id='task-1',
        description='Saved task',
        due_at=DUE.isoformat(),
        completed=completed,
        status=status,
        deleted=deleted,
    )


@pytest.mark.parametrize('status,deleted', [('cancelled', False), ('superseded', False), ('active', True)])
def test_due_edit_forwards_terminal_postwrite_state(producer, status, deleted):
    kind, module, database, notifications = producer
    old = {'id': 'task-1', 'description': 'Before', 'due_at': DUE, 'completed': False, 'status': 'active'}
    saved = {**old, 'description': 'Saved', 'status': status, 'deleted': deleted}
    database.get_action_item.side_effect = [old, saved]
    _update(kind, module, due_at=DUE.isoformat())
    notifications.sync_action_item_reminder.assert_called_once_with(
        'u1',
        'task-1',
        'Saved',
        False,
        DUE,
        status=status,
        deleted=deleted,
    )


def test_description_edit_rearms_the_reminder_with_the_saved_title(producer):
    # The phone reminder shows the title it was armed with, so a rename must re-arm it.
    kind, module, database, notifications = producer
    old = {'id': 'task-1', 'description': 'Before', 'due_at': DUE, 'completed': False, 'status': 'active'}
    database.get_action_item.side_effect = [old, {**old, 'description': 'Renamed'}]
    _update(kind, module, description='Renamed')
    notifications.sync_action_item_reminder.assert_called_once_with(
        'u1',
        'task-1',
        'Renamed',
        False,
        DUE,
        status='active',
        deleted=False,
    )


def test_explicit_reopen_uses_active_saved_status_not_old_cancelled_status(producer):
    kind, module, database, notifications = producer
    old = {'id': 'task-1', 'description': 'Task', 'due_at': DUE, 'completed': False, 'status': 'cancelled'}
    database.get_action_item.side_effect = [old, {**old, 'status': 'active'}]
    _update(kind, module, completed=False)
    notifications.sync_action_item_reminder.assert_called_once_with(
        'u1',
        'task-1',
        'Task',
        False,
        DUE,
        status='active',
        deleted=False,
    )


def test_missing_postwrite_row_never_schedules_from_stale_prewrite_state(producer):
    kind, module, database, notifications = producer
    old = {'id': 'task-1', 'description': 'Task', 'due_at': DUE, 'completed': False, 'status': 'active'}
    database.get_action_item.side_effect = [old, None]
    assert "couldn't retrieve details" in _update(kind, module, completed=False)
    notifications.sync_action_item_reminder.assert_not_called()
