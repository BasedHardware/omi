"""No-op updates reuse their required read; real changes retain commit invalidation."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import action_items as items

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def stored(monkeypatch):
    state = SimpleNamespace(
        row=dict(
            description='Task',
            completed=True,
            status='completed',
            completed_at=NOW,
            updated_at=NOW,
            goal_id=None,
            workstream_id=None,
        ),
        exists=True,
    )
    ref = Mock()
    ref.get.side_effect = lambda **kwargs: SimpleNamespace(exists=state.exists, to_dict=lambda: dict(state.row))
    fake = SimpleNamespace(
        collection=lambda _: SimpleNamespace(
            document=lambda _: SimpleNamespace(collection=lambda _: SimpleNamespace(document=lambda _: ref))
        ),
        transaction=Mock(),
    )
    monkeypatch.setattr(items, 'db', fake)
    bumps, followups = Mock(), Mock()
    monkeypatch.setattr(items, 'bump_action_items_list_version', bumps)
    monkeypatch.setattr(items, '_record_followup_completion', followups)
    return state, ref, bumps, followups


def test_same_completion_and_description_preserve_version_and_timestamp(stored):
    state, ref, bumps, followups = stored
    assert items.update_action_item('owner', 'task', {'description': 'Task', 'completed': True}) is True
    assert ref.get.call_count == 1
    ref.update.assert_not_called()
    bumps.assert_not_called()
    followups.assert_called_once_with('owner', 'task')
    assert state.row['updated_at'] == NOW


@pytest.mark.parametrize(
    'patch',
    [
        {'description': 'Changed'},
        {'due_at': None},
        {'sort_order': 0},
        {'completed': False},
        {'updated_at': datetime(2026, 10, 19, tzinfo=timezone.utc)},
    ],
)
def test_changes_and_absent_fields_still_write_and_invalidate(stored, patch):
    _, ref, bumps, _ = stored
    assert items.update_action_item('owner', 'task', patch) is True
    assert ref.get.call_count == ref.update.call_count == 1
    bumps.assert_called_once_with('owner')


def test_kill_switch_restores_touch_write(stored, monkeypatch):
    _, ref, bumps, _ = stored
    monkeypatch.setenv('OMI_DEV_ACTION_ITEMS_SKIP_NOOP_WRITES_ENABLED', 'false')
    assert items.update_action_item('owner', 'task', {'description': 'Task'}) is True
    assert ref.update.call_count == 1
    bumps.assert_called_once()


def test_missing_row_stays_false(stored):
    state, ref, bumps, _ = stored
    state.exists = False
    assert items.update_action_item('owner', 'task', {'description': 'Task'}) is False
    ref.update.assert_not_called()
    bumps.assert_not_called()


def test_linked_noop_still_validates_relationship_and_reads_transactionally(stored, monkeypatch):
    _, ref, bumps, followups = stored
    transaction = Mock()
    monkeypatch.setattr(items.firestore, 'transactional', lambda fn: fn)
    validate = Mock()
    monkeypatch.setattr(items, 'validate_task_relationship_in_transaction', validate)
    monkeypatch.setattr(items, 'run_with_transaction_contention_retry', lambda factory, fn, **kwargs: fn(transaction))
    assert items.update_action_item('owner', 'task', {'goal_id': None, 'completed': True}) is True
    validate.assert_called_once()
    ref.get.assert_called_once_with(transaction=transaction)
    transaction.update.assert_not_called()
    bumps.assert_not_called()
    followups.assert_called_once()


def test_conditional_chat_edit_never_short_circuits(stored, monkeypatch):
    _, ref, bumps, _ = stored
    apply = Mock(return_value={'description': 'Task'})
    monkeypatch.setattr(items.chat_edits, 'apply_update', apply)
    state = {'before': {'description': 'Task'}}
    assert items.update_action_item('owner', 'task', {'description': 'Task'}, expected_chat_state=state) is True
    apply.assert_called_once()
    assert state['after'] == {'description': 'Task'}
    bumps.assert_called_once()
