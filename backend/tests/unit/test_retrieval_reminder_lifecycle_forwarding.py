"""Real retrieval producers must pass saved lifecycle state to the reminder gate."""

import contextvars
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND = Path(__file__).resolve().parents[2]
DUE = datetime(2099, 10, 9, 17, tzinfo=timezone.utc)


@pytest.fixture(params=['service', 'tool'])
def producer(request):
    database = ModuleType('database.action_items')
    database.create_action_item = MagicMock(return_value='task-1')
    database.get_action_item = MagicMock()
    database.update_action_item = MagicMock(return_value=True)
    database.get_action_items = MagicMock(return_value=[])
    notifications = ModuleType('utils.notifications')
    for name in (
        'send_action_item_completed_notification',
        'send_action_item_created_notification',
        'send_action_item_data_message',
        'sync_action_item_reminder',
    ):
        setattr(notifications, name, MagicMock())
    notification_db = ModuleType('database.notifications')
    notification_db.get_user_time_zone = MagicMock(return_value='UTC')
    render = ModuleType('utils.conversations.render')
    render.format_local_time = lambda *args: ''
    render.resolve_display_tz = lambda *args: (timezone.utc, 'UTC')
    conversation_services = ModuleType('utils.retrieval.tool_services.conversations')
    conversation_services.parse_iso_date = lambda value, field: datetime.fromisoformat(value)
    safety = ModuleType('utils.retrieval.safety')
    safety.safe_isoformat = lambda value: value.isoformat() if value else None
    chat_scope = ModuleType('utils.retrieval.chat_scope')
    chat_scope.apply_chat_scope_dates = lambda scope, start, end: (start, end, None)
    chat_scope.chat_scope_from_config = lambda config: None
    agentic = ModuleType('utils.retrieval.agentic')
    agentic.agent_config_context = contextvars.ContextVar('reminder-test-config', default=None)
    messaging_undo = ModuleType('utils.messaging.undo')
    messaging_undo.record_write = MagicMock(return_value='')
    langchain_tools = ModuleType('langchain_core.tools')
    langchain_tools.tool = lambda fn: fn
    langchain_runnables = ModuleType('langchain_core.runnables')
    langchain_runnables.RunnableConfig = dict
    fakes = {
        'database.action_items': database,
        'database.notifications': notification_db,
        'utils.notifications': notifications,
        'utils.conversations.render': render,
        'utils.retrieval.tool_services.conversations': conversation_services,
        'utils.retrieval.safety': safety,
        'utils.retrieval.chat_scope': chat_scope,
        'utils.retrieval.agentic': agentic,
        'utils.messaging.undo': messaging_undo,
        'langchain_core.tools': langchain_tools,
        'langchain_core.runnables': langchain_runnables,
    }
    module_name = (
        'utils.retrieval.tool_services.action_items'
        if request.param == 'service'
        else 'utils.retrieval.tools.action_item_tools'
    )
    with stub_modules(fakes):
        module = load_module_fresh(module_name, str(BACKEND / (module_name.replace('.', '/') + '.py')))
        yield request.param, module, database, notifications


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
