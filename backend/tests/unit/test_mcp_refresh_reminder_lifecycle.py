"""Real MCP/refresh/dispatcher paths retain lifecycle until the reminder decision.

All heavy service leaves are fixture-scoped stubs. The policy, MCP response
cleaner, notification helpers, dispatcher, and refresh orchestrator are real.
"""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, package_submodule_stubs, stub_modules

BACKEND = Path(__file__).resolve().parents[2]
DUE = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
PUBLIC_KEYS = {'id', 'description', 'completed', 'created_at', 'due_at', 'completed_at', 'conversation_id'}


@pytest.fixture
def world(monkeypatch):
    # notifications still imports provider/LLM leaves; no client or account
    # access is needed to drive its real silent scheduling/cancellation helpers.
    fakes = package_submodule_stubs('database')
    firebase = AutoMockModule('firebase_admin')
    firebase.__path__ = []
    llm = AutoMockModule('utils.llm')
    llm.__path__ = []
    fakes.update(
        {
            'firebase_admin': firebase,
            'firebase_admin.messaging': AutoMockModule('firebase_admin.messaging'),
            'firebase_admin.auth': AutoMockModule('firebase_admin.auth'),
            'utils.executors': AutoMockModule('utils.executors'),
            'utils.llm': llm,
            'utils.llm.notifications': AutoMockModule('utils.llm.notifications'),
            'utils.metrics': AutoMockModule('utils.metrics'),
            'utils.task_sync': AutoMockModule('utils.task_sync'),
        }
    )
    monkeypatch.delenv('COMMITMENT_FOLLOWUP_TASKS_QUEUE', raising=False)
    with stub_modules(fakes):
        notifications = load_module_fresh('utils.notifications', str(BACKEND / 'utils/notifications.py'))
        load_module_fresh('utils.mcp_data', str(BACKEND / 'utils/mcp_data.py'))
        actions = load_module_fresh('utils.mcp_action_items', str(BACKEND / 'utils/mcp_action_items.py'))
        dispatcher = load_module_fresh('utils.notification_dispatch', str(BACKEND / 'utils/notification_dispatch.py'))
        refresh = load_module_fresh(
            'utils.conversations.action_item_refresh', str(BACKEND / 'utils/conversations/action_item_refresh.py')
        )
        sent = []
        monkeypatch.setattr(
            notifications, '_send_to_user', lambda uid, tag, **kwargs: sent.append((uid, kwargs['data']))
        )
        external = AsyncMock()
        monkeypatch.setattr(refresh, 'auto_sync_action_items_batch', external)
        yield SimpleNamespace(
            actions=actions,
            db=fakes['database.action_items'],
            refresh_db=fakes['database.action_item_refresh'],
            dispatcher=dispatcher,
            refresh=refresh,
            sent=sent,
            external=external,
        )


def task(task_id='task-1', **fields):
    return {
        'id': task_id,
        'description': 'Synthetic task',
        'completed': False,
        'created_at': DUE,
        'due_at': DUE,
        'completed_at': None,
        'conversation_id': 'conversation-1',
        **fields,
    }


@pytest.mark.parametrize('status', ['cancelled', 'superseded'])
def test_mcp_due_update_cancels_using_raw_status_but_keeps_public_response_unchanged(world, status):
    existing = task(status='active')
    saved = task(status=status, private_metadata='not-public')
    world.db.get_action_item.side_effect = [existing, saved]
    world.db.update_action_item.return_value = True

    result = world.actions.update_action_item('synthetic-owner', 'task-1', due_at=DUE)

    assert world.sent == [('synthetic-owner', {'type': 'action_item_delete', 'action_item_id': 'task-1'})]
    assert set(result) == PUBLIC_KEYS
    assert result['completed'] is False
    assert result['due_at'] == DUE
    assert 'status' not in result and 'private_metadata' not in result


def test_mcp_completion_uses_post_write_status_before_cleaning_response(world):
    world.db.get_action_item.side_effect = [task(status='active'), task(status='cancelled')]
    world.db.mark_action_item_completed.return_value = True

    result = world.actions.set_completed('synthetic-owner', 'task-1', completed=False)

    assert world.sent == [('synthetic-owner', {'type': 'action_item_delete', 'action_item_id': 'task-1'})]
    assert set(result) == PUBLIC_KEYS
    assert 'status' not in result


def test_mcp_create_replay_uses_saved_terminal_state_not_open_request(world):
    world.db.create_action_item.return_value = 'task-1'
    world.db.get_action_item.return_value = task(status='superseded')

    result = world.actions.create_action_item('synthetic-owner', 'Synthetic task', due_at=DUE, completed=False)

    assert world.sent == [('synthetic-owner', {'type': 'action_item_delete', 'action_item_id': 'task-1'})]
    assert set(result) == PUBLIC_KEYS


def test_mcp_legacy_due_update_still_reschedules_without_adding_lifecycle_to_public_output(world):
    world.db.get_action_item.side_effect = [task(), task()]
    world.db.update_action_item.return_value = True

    result = world.actions.update_action_item('synthetic-owner', 'task-1', due_at=DUE)

    assert world.sent == [
        (
            'synthetic-owner',
            {
                'type': 'action_item_update',
                'action_item_id': 'task-1',
                'description': 'Synthetic task',
                'due_at': DUE.isoformat(),
            },
        )
    ]
    assert set(result) == PUBLIC_KEYS


@pytest.mark.parametrize('fields', [{'status': 'cancelled'}, {'status': 'superseded'}, {'deleted': True}])
def test_direct_refresh_dispatch_cannot_lose_lifecycle_before_silent_transport(world, fields):
    result = world.dispatcher.dispatch_action_item_reminder(
        user_id='synthetic-owner',
        action_item_id='task-1',
        description='Synthetic task',
        due_at=DUE.isoformat(),
        **fields
    )

    assert result.status == world.dispatcher.NotificationDispatchStatus.DISPATCHED
    assert world.sent == [('synthetic-owner', {'type': 'action_item_delete', 'action_item_id': 'task-1'})]


def test_refresh_reloads_current_lifecycle_and_preserves_undated_active_auto_sync(world):
    rows = [
        task('cancelled', status='cancelled'),
        task('superseded', status='superseded'),
        task('deleted', deleted=True),
        task('completed', status='completed', completed=True),
        task('active', status='active'),
        task('legacy'),
        task('undated', status='active', due_at=None),
        task('exported', status='active', exported=True),
        task('linked', status='active', apple_reminder_id='existing-external-id'),
    ]
    world.refresh_db.pending_rows.return_value = rows
    enumerated = [task(row['id'], status='active') for row in rows]

    world.refresh._deliver('synthetic-owner', 'conversation-1', enumerated)

    world.refresh_db.pending_rows.assert_called_once_with(
        'synthetic-owner', 'conversation-1', [row['id'] for row in rows]
    )
    assert [data['action_item_id'] for _, data in world.sent] == ['active', 'legacy']
    assert all(data['type'] == 'action_item_reminder' for _, data in world.sent)
    world.external.assert_awaited_once_with('synthetic-owner', [rows[4], rows[5], rows[6]])


def test_refresh_passes_saved_lifecycle_to_dispatcher(world, monkeypatch):
    saved = task(status='active')
    world.refresh_db.pending_rows.return_value = [saved]
    calls = []
    monkeypatch.setattr(world.refresh, 'dispatch_action_item_reminder', lambda **kwargs: calls.append(kwargs))

    world.refresh._deliver('synthetic-owner', 'conversation-1', [saved])

    assert calls == [
        {
            'user_id': 'synthetic-owner',
            'action_item_id': 'task-1',
            'description': 'Synthetic task',
            'due_at': DUE.isoformat(),
            'completed': False,
            'status': 'active',
            'deleted': False,
        }
    ]
