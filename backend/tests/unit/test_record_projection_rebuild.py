"""Projection debt uses real privacy/CAS transactions; never seal or content writes."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import FailedPrecondition

from database import record_projection_rebuild as jobs
from database.conversations import AudioFilesChanged
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import record_projection_rebuild as consumer
from utils.batch_pipeline.record_seal_budget import SweepBudget

ROW = ('users', 'u', 'conversations', 'c')


@pytest.fixture
def client():
    return StrictFirestore(
        {
            ('users', 'u'): {'private_cloud_sync_enabled': True},
            ROW: {
                'audio_files': [],
                'private_cloud_sync_enabled': True,
                'content': 'untouched',
                'record_upload_sessions': {},
                'record_audio_closed': False,
            },
        }
    )


def test_rebuild_only_updates_playback_metadata(client):
    before = deepcopy(client.rows[ROW])
    assert jobs.apply_projection(
        'u', 'c', {'audio_files': [{'id': 'new'}]}, expected_audio_files=[], firestore_client=client
    )
    assert client.rows[ROW] == {**before, 'audio_files': [{'id': 'new'}]}
    assert client.transactions[-1].updates == [(ROW, {'audio_files': [{'id': 'new'}]})]


@pytest.mark.parametrize(
    'fence', ['tombstone', 'deleted', 'redirect', 'discarded', 'missing', 'account', 'e2ee', 'sync']
)
def test_privacy_refusal_never_recreates_or_updates_conversation(client, fence):
    if fence == 'tombstone':
        client.rows[('users', 'u', 'deleted_conversations', 'c')] = {}
    elif fence == 'missing':
        client.rows.pop(ROW)
    elif fence == 'account':
        client.rows[('account_deletions', 'u')] = {'wipe_status': 'completed'}
    elif fence == 'e2ee':
        client.rows[('users', 'u')]['data_protection_level'] = 'e2ee'
    elif fence == 'sync':
        client.rows[ROW]['private_cloud_sync_enabled'] = False
    elif fence == 'redirect':
        client.rows[ROW].update(deleted=True, sync_merged_into='target')
        client.rows[('users', 'u', 'conversations', 'target')] = {}
    else:
        client.rows[ROW][fence] = True
    before = deepcopy(client.rows)
    assert (
        jobs.apply_projection(
            'u', 'c', {'audio_files': [{'id': 'new'}]}, expected_audio_files=[], firestore_client=client
        )
        is False
    )
    assert client.rows == before


def test_peer_projection_race_is_retained_for_retry(client):
    client.rows[ROW]['audio_files'] = [{'id': 'peer'}]
    with pytest.raises(AudioFilesChanged):
        jobs.apply_projection(
            'u', 'c', {'audio_files': [{'id': 'new'}]}, expected_audio_files=[], firestore_client=client
        )
    assert client.rows[ROW]['audio_files'] == [{'id': 'peer'}]


@pytest.mark.parametrize('result', [True, False, None, OSError('private path')])
def test_consumer_clears_only_observed_marker_and_rotates_failed_work(monkeypatch, result):
    client = MagicMock()
    ref = MagicMock()
    doc = SimpleNamespace(
        id=jobs.marker_id('u', 'c'),
        reference=ref,
        update_time='observed',
        to_dict=lambda: {'kind': jobs.KIND, 'owner_id': 'u', 'conversation_id': 'c'},
    )
    client.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = [doc]
    rebuild = MagicMock(side_effect=result) if isinstance(result, Exception) else MagicMock(return_value=result)
    monkeypatch.setattr(consumer, 'rebuild', rebuild)
    report = consumer.run(budget=SweepBudget(60), firestore_client=client)
    client.collection.assert_called_once_with(jobs.COLLECTION)
    client.collection.return_value.order_by.assert_called_once_with('requested_at')
    client.collection.return_value.order_by.return_value.limit.assert_called_once_with(128)
    assert client.write_option.call_args_list[0].kwargs == {'last_update_time': 'observed'}
    if result is True or result is False:
        ref.delete.assert_called_once()
        assert client.write_option.call_args.kwargs == {'last_update_time': ref.update.return_value.update_time}
    else:
        ref.delete.assert_not_called()
    ref.update.assert_called_once()
    assert 'private' not in str(report) and 'owner_id' not in str(report)


def test_consumer_never_deletes_concurrently_replaced_debt(monkeypatch):
    client = MagicMock()
    ref = MagicMock()
    ref.delete.side_effect = FailedPrecondition('newer marker')
    doc = SimpleNamespace(
        id=jobs.marker_id('u', 'c'),
        reference=ref,
        update_time='old',
        to_dict=lambda: {'kind': jobs.KIND, 'owner_id': 'u', 'conversation_id': 'c'},
    )
    client.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = [doc]
    monkeypatch.setattr(consumer, 'rebuild', lambda *_: True)
    assert consumer.run(budget=SweepBudget(60), firestore_client=client)['dispositions'] == {'changed': 1}
    ref.update.assert_called_once()


@pytest.mark.parametrize('mode', ['off', 'plan'])
def test_kill_switch_and_preview_never_rebuild_or_write(monkeypatch, mode):
    client = MagicMock()
    doc = SimpleNamespace(
        id=jobs.marker_id('u', 'c'),
        reference=MagicMock(),
        update_time='old',
        to_dict=lambda: {'kind': jobs.KIND, 'owner_id': 'u', 'conversation_id': 'c'},
    )
    client.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = [doc]
    rebuild = MagicMock(side_effect=AssertionError('must not rebuild'))
    monkeypatch.setattr(consumer, 'rebuild', rebuild)
    if mode == 'off':
        monkeypatch.setenv('PUSHER_PROJECTION_DEBT_DURABLE_ENABLED', 'off')
    consumer.run(mode='plan' if mode == 'plan' else 'apply', budget=SweepBudget(60), firestore_client=client)
    rebuild.assert_not_called()
    doc.reference.delete.assert_not_called()
    doc.reference.update.assert_not_called()
    if mode == 'off':
        client.collection.assert_not_called()


def test_marker_is_content_free_and_coalesces_by_owner():
    client = MagicMock()
    jobs.mark_due('u', 'c', firestore_client=client)
    jobs.mark_due('u', 'c', firestore_client=client)
    assert jobs.marker_id('u', 'c') != jobs.marker_id('u', 'other')
    assert client.collection.call_args.args == (jobs.COLLECTION,)
    assert set(client.collection.return_value.document.return_value.set.call_args.args[0]) == {
        'kind',
        'owner_id',
        'conversation_id',
        'requested_at',
    }


def test_budget_exhaustion_keeps_rotated_marker_and_does_not_disable_seal_pass(monkeypatch):
    from config import record_seal_repair as config
    from utils.batch_pipeline.record_seal_budget import BudgetExhausted

    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'settings', lambda: (8, 270, 1500, 'apply'))
    monkeypatch.setattr(consumer, 'run', MagicMock(side_effect=BudgetExhausted()))
    assert consumer.run_job()['outcome'] == 'budget_exhausted'


def test_rebuild_updates_metadata_but_retains_marker_while_producer_is_pending(client):
    client.rows[ROW]['record_upload_sessions'] = {'live': True}
    assert (
        jobs.apply_projection(
            'u', 'c', {'audio_files': [{'id': 'tail'}]}, expected_audio_files=[], firestore_client=client
        )
        is None
    )
    assert client.rows[ROW]['audio_files'] == [{'id': 'tail'}]
    assert client.rows[ROW]['record_upload_sessions'] == {'live': True}
    assert client.rows[ROW]['record_audio_closed'] is False


def test_invalid_marker_rotates_without_rebuild_or_deletion(monkeypatch):
    client = MagicMock()
    doc = SimpleNamespace(
        id='wrong',
        reference=MagicMock(),
        update_time='old',
        to_dict=lambda: {'kind': jobs.KIND, 'owner_id': 'u', 'conversation_id': 'c'},
    )
    client.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = [doc]
    rebuild = MagicMock()
    monkeypatch.setattr(consumer, 'rebuild', rebuild)
    assert consumer.run(budget=SweepBudget(60), firestore_client=client)['dispositions'] == {'invalid': 1}
    doc.reference.update.assert_called_once()
    doc.reference.delete.assert_not_called()
    rebuild.assert_not_called()
