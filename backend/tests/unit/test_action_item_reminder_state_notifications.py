"""Real reminder transports admit canonical lifecycle, not just completed=False."""

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from config.action_item_reminder_policy import should_schedule_action_item_reminder
from config.action_item_reminder_triggers import ACTION_ITEM_REMINDER_FIELDS, action_item_write_affects_reminder
from utils import notifications

DUE = datetime(2027, 1, 15, 9, 0, tzinfo=timezone.utc)


def configure_reminder_transports(monkeypatch):
    """Keep production helper admission, replace only external delivery."""
    fcm = []

    def capture_fcm(user_id, tag, **kwargs):
        fcm.append({'user_id': user_id, 'tag': tag, **kwargs})
        return 1

    monkeypatch.setattr(notifications, '_send_to_user', capture_fcm)
    return SimpleNamespace(fcm=fcm)


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
def test_non_active_tasks_cancel_the_fcm_reminder(reminder_transports, method, completed, status, deleted):
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


@pytest.mark.parametrize('status', [None, 'active'])
@pytest.mark.parametrize('method', ['sync', 'create'])
def test_active_and_legacy_tasks_arm_the_fcm_reminder(reminder_transports, status, method):
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


@pytest.mark.parametrize('due_at', [None, ''])
def test_clearing_due_date_cancels_the_reminder(reminder_transports, due_at):
    notifications.sync_action_item_reminder('test-user', 'task-1', 'Synthetic task', False, due_at, status='active')

    assert [call['data']['type'] for call in reminder_transports.fcm] == ['action_item_delete']


def test_existing_five_positional_sync_call_retains_legacy_active_behavior(reminder_transports):
    notifications.sync_action_item_reminder('test-user', 'task-1', 'Synthetic task', False, DUE.isoformat())

    assert [call['data']['type'] for call in reminder_transports.fcm] == ['action_item_update']


def test_existing_four_positional_create_call_retains_legacy_active_behavior(reminder_transports):
    notifications.send_action_item_data_message('test-user', 'task-1', 'Synthetic task', DUE.isoformat())

    assert [call['data']['type'] for call in reminder_transports.fcm] == ['action_item_reminder']


def test_reconcile_fields_are_exactly_what_a_reminder_is_armed_from(reminder_transports):
    # The phone keeps whatever the armed message carried; the admission predicate reads the rest.
    # A field added to either side must also make task writers reconcile the reminder.
    notifications.sync_action_item_reminder('test-user', 'task-1', 'Synthetic task', False, DUE, status='active')
    shown_fields = set(reminder_transports.fcm[0]['data']) - {'type', 'action_item_id'}
    lifecycle_fields = set(inspect.signature(should_schedule_action_item_reminder).parameters)

    assert ACTION_ITEM_REMINDER_FIELDS == shown_fields | lifecycle_fields


@pytest.mark.parametrize(
    'update_data,expected',
    [
        ({'description': 'Renamed task'}, True),
        ({'due_at': None}, True),
        ({'completed': True, 'completed_at': DUE}, True),
        ({'status': 'cancelled'}, True),
        ({'deleted': True, 'deleted_at': DUE}, True),
        ({'sort_order': 3, 'indent_level': 1}, False),
        ({'exported': True, 'export_platform': 'apple_reminders'}, False),
    ],
)
def test_only_writes_to_armed_fields_reconcile_the_reminder(update_data, expected):
    assert action_item_write_affects_reminder(update_data) is expected
