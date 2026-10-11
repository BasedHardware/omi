"""Real reminder transports admit canonical lifecycle, not just completed=False."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from config.action_item_reminder_policy import should_schedule_action_item_reminder
from utils import commitment_followup_tasks, notifications

DUE = datetime(2027, 1, 15, 9, 0, tzinfo=timezone.utc)


def configure_reminder_transports(monkeypatch):
    """Keep production helper/queue admission, replace only external delivery."""
    fcm = []
    queued = []

    def capture_fcm(user_id, tag, **kwargs):
        fcm.append({'user_id': user_id, 'tag': tag, **kwargs})
        return 1

    def capture_queue(queue, url, task_name, payload, **kwargs):
        queued.append({'queue': queue, 'url': url, 'task_name': task_name, 'payload': payload, **kwargs})

    monkeypatch.setenv('COMMITMENT_FOLLOWUP_TASKS_QUEUE', 'projects/test/locations/test/queues/reminders')
    monkeypatch.setenv('COMMITMENT_FOLLOWUP_TASKS_HANDLER_URL', 'https://reminder-test.invalid/followup')
    monkeypatch.setenv('COMMITMENT_FOLLOWUP_TASKS_INVOKER_SA', 'reminder-test@example.invalid')
    monkeypatch.setattr(notifications, '_send_to_user', capture_fcm)
    monkeypatch.setattr(commitment_followup_tasks, 'enabled', lambda _uid: True)
    monkeypatch.setattr(commitment_followup_tasks.cloud_tasks, 'enqueue_named_task', capture_queue)
    return SimpleNamespace(fcm=fcm, queued=queued)


@pytest.fixture
def reminder_transports(monkeypatch):
    return configure_reminder_transports(monkeypatch)


@pytest.mark.parametrize(
    'completed,due_at,status,deleted,expected',
    [
        (False, DUE, None, False, True),
        (False, DUE, 'active', False, True),
        (True, DUE, None, False, False),
        (True, DUE, 'active', False, False),
        (False, None, 'active', False, False),
        (False, '', None, False, False),
        (False, DUE, 'completed', False, False),
        (False, DUE, 'cancelled', False, False),
        (False, DUE, 'superseded', False, False),
        (False, DUE, 'future-status', False, False),
        (False, DUE, '', False, False),
        (False, DUE, 'active', True, False),
        (False, DUE, None, True, False),
    ],
)
def test_reminder_admission_uses_canonical_lifecycle(completed, due_at, status, deleted, expected):
    assert (
        should_schedule_action_item_reminder(completed=completed, due_at=due_at, status=status, deleted=deleted)
        is expected
    )


@pytest.mark.parametrize('method', ['sync', 'create'])
@pytest.mark.parametrize(
    'completed,status,deleted',
    [
        (False, 'cancelled', False),
        (False, 'superseded', False),
        (False, 'completed', False),
        (False, 'future-status', False),
        (False, '', False),
        (False, 'active', True),
        (True, 'completed', False),
    ],
)
def test_non_active_tasks_cancel_fcm_without_enqueuing_followup(
    reminder_transports, method, completed, status, deleted
):
    if method == 'sync':
        notifications.sync_action_item_reminder(
            'test-user', 'task-1', 'Synthetic task', completed, DUE, status=status, deleted=deleted
        )
    else:
        notifications.send_action_item_data_message(
            'test-user',
            'task-1',
            'Synthetic task',
            DUE.isoformat(),
            completed=completed,
            status=status,
            deleted=deleted,
        )

    assert [call['data']['type'] for call in reminder_transports.fcm] == ['action_item_delete']
    assert reminder_transports.fcm[0]['data']['action_item_id'] == 'task-1'
    assert reminder_transports.queued == []


@pytest.mark.parametrize('status', [None, 'active'])
@pytest.mark.parametrize('method', ['sync', 'create'])
def test_active_and_legacy_tasks_arm_both_fcm_and_followup(reminder_transports, status, method):
    if method == 'sync':
        notifications.sync_action_item_reminder('test-user', 'task-1', 'Synthetic task', False, DUE, status=status)
        expected_type = 'action_item_update'
    else:
        notifications.send_action_item_data_message(
            'test-user', 'task-1', 'Synthetic task', DUE.isoformat(), status=status
        )
        expected_type = 'action_item_reminder'

    assert len(reminder_transports.fcm) == 1
    assert reminder_transports.fcm[0]['data'] == {
        'type': expected_type,
        'action_item_id': 'task-1',
        'description': 'Synthetic task',
        'due_at': DUE.isoformat(),
    }
    assert reminder_transports.fcm[0]['is_background'] is True
    assert len(reminder_transports.queued) == 1
    queued = reminder_transports.queued[0]
    assert queued['queue'] == 'projects/test/locations/test/queues/reminders'
    assert queued['payload'] == {'uid': 'test-user', 'task_id': 'task-1', 'due_revision': DUE.isoformat()}


@pytest.mark.parametrize('due_at', [None, ''])
def test_clearing_due_date_cancels_without_queue_work(reminder_transports, due_at):
    notifications.sync_action_item_reminder('test-user', 'task-1', 'Synthetic task', False, due_at, status='active')

    assert [call['data']['type'] for call in reminder_transports.fcm] == ['action_item_delete']
    assert reminder_transports.queued == []


def test_existing_five_positional_sync_call_retains_legacy_active_behavior(reminder_transports):
    notifications.sync_action_item_reminder('test-user', 'task-1', 'Synthetic task', False, DUE.isoformat())

    assert [call['data']['type'] for call in reminder_transports.fcm] == ['action_item_update']
    assert len(reminder_transports.queued) == 1


def test_existing_four_positional_create_call_retains_legacy_active_behavior(reminder_transports):
    notifications.send_action_item_data_message('test-user', 'task-1', 'Synthetic task', DUE.isoformat())

    assert [call['data']['type'] for call in reminder_transports.fcm] == ['action_item_reminder']
    assert len(reminder_transports.queued) == 1
