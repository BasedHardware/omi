"""No-op updates reuse their required read; real changes retain commit invalidation."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.datetime_helpers import DatetimeWithNanoseconds

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


@pytest.mark.parametrize('value', [[{'ordinal': True}], [{'ordinal': 1}]])
def test_structured_fields_keep_write_and_invalidation_even_when_python_equal(stored, value):
    state, ref, bumps, _ = stored
    state.row['provenance'] = [{'ordinal': 1}]
    assert items.update_action_item('owner', 'task', {'provenance': value}) is True
    assert ref.get.call_count == ref.update.call_count == 1
    bumps.assert_called_once_with('owner')


@pytest.mark.parametrize('linked', [False, True])
def test_real_sdk_completion_timestamp_replay_reuses_identity_without_writing(stored, monkeypatch, linked):
    state, ref, bumps, followups = stored
    state.row['completed_at'] = DatetimeWithNanoseconds.from_rfc3339('2026-01-01T00:00:00.123456789Z')
    patch = {'completed': True, 'completed_at': datetime(2026, 10, 19, tzinfo=timezone.utc)}
    transaction = Mock()
    if linked:
        patch['goal_id'] = None
        monkeypatch.setattr(items.firestore, 'transactional', lambda fn: fn)
        monkeypatch.setattr(items, 'validate_task_relationship_in_transaction', Mock())
        monkeypatch.setattr(
            items, 'run_with_transaction_contention_retry', lambda factory, fn, **kwargs: fn(transaction)
        )
    assert items.update_action_item('owner', 'task', patch) is True
    assert ref.get.call_count == 1
    ref.update.assert_not_called()
    transaction.update.assert_not_called()
    bumps.assert_not_called()
    followups.assert_called_once_with('owner', 'task')
    assert state.row['completed_at'].nanosecond == 123456789


def test_distinct_sdk_nanoseconds_are_written_even_when_datetime_equality_conflates_them(stored):
    state, ref, bumps, _ = stored
    previous = DatetimeWithNanoseconds.from_rfc3339('2026-01-01T00:00:00.123456789Z')
    changed = DatetimeWithNanoseconds.from_rfc3339('2026-01-01T00:00:00.123456790Z')
    assert previous == changed and previous.nanosecond != changed.nanosecond
    state.row['completed_at'] = previous
    assert items.update_action_item('owner', 'task', {'completed_at': changed}) is True
    ref.update.assert_called_once()
    assert ref.update.call_args.args[0]['completed_at'].nanosecond == 123456790
    bumps.assert_called_once_with('owner')


def test_arbitrary_scalar_subclass_equality_is_never_trusted(stored):
    class UntrustedText(str):
        def __eq__(self, other):
            raise AssertionError('arbitrary equality must not be evaluated')

    state, ref, bumps, _ = stored
    value = UntrustedText('Task')
    state.row['description'] = value
    assert items.update_action_item('owner', 'task', {'description': value}) is True
    ref.update.assert_called_once()
    bumps.assert_called_once_with('owner')
