"""Projection debt uses real privacy/CAS transactions; never seal or content writes."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import FailedPrecondition

from database import record_projection_rebuild as jobs
from database.conversations import AudioFilesChanged
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
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
    assert jobs.apply_projection(
        'u', 'c', {'audio_files': [{'id': 'new'}]}, expected_audio_files=[], firestore_client=client
    ) is (None if fence == 'e2ee' else False)
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
    client.collection.return_value.order_by.return_value.limit.assert_called_once_with(
        consumer.MAX_COLLECTION_MARKERS + 1
    )
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
    assert [call.args for call in client.collection.return_value.document.call_args_list] == [
        (jobs.marker_id('u', 'c'),)
    ] * 2
    assert jobs.marker_id('u', 'c') != jobs.marker_id('u', 'other')
    assert client.collection.call_args.args == (jobs.COLLECTION,)
    assert set(client.collection.return_value.document.return_value.set.call_args.args[0]) == {
        'kind',
        'owner_id',
        'conversation_id',
        'requested_at',
    }


def test_job_budget_outcome_does_not_disable_seal_pass(monkeypatch):
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


@pytest.mark.parametrize('hold', ['migration', 'generation'])
def test_temporary_privacy_hold_retains_debt_until_it_clears(client, hold):
    from database.batch_pipeline_privacy import privacy_owner_key

    if hold == 'migration':
        client.rows[('users', 'u')]['migration_status'] = 'migrating'
    else:
        client.rows[('batch_pipeline_privacy', privacy_owner_key('u'))] = {'purging': True}
    before = deepcopy(client.rows)
    assert (
        jobs.apply_projection(
            'u', 'c', {'audio_files': [{'id': 'new'}]}, expected_audio_files=[], firestore_client=client
        )
        is None
    )
    assert client.rows == before
    if hold == 'migration':
        client.rows[('users', 'u')].pop('migration_status')
    else:
        client.rows.pop(('batch_pipeline_privacy', privacy_owner_key('u')))
    assert (
        jobs.apply_projection(
            'u', 'c', {'audio_files': [{'id': 'new'}]}, expected_audio_files=[], firestore_client=client
        )
        is True
    )


def test_deadline_rotates_before_discovery_and_never_clears_marker(monkeypatch):
    from utils.batch_pipeline.record_seal_budget import BudgetExhausted

    client = MagicMock()
    doc = SimpleNamespace(
        id=jobs.marker_id('u', 'c'),
        reference=MagicMock(),
        update_time='old',
        to_dict=lambda: {'kind': jobs.KIND, 'owner_id': 'u', 'conversation_id': 'c'},
    )
    client.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = [doc]

    def exhaust(*args):
        doc.reference.update.assert_called_once()
        raise BudgetExhausted()

    monkeypatch.setattr(consumer, 'rebuild', exhaust)
    with pytest.raises(BudgetExhausted):
        consumer.run(budget=SweepBudget(60), firestore_client=client)
    doc.reference.delete.assert_not_called()


@pytest.mark.parametrize('age_days,over_capacity,retired', [(0, False, False), (8, False, True), (0, True, True)])
def test_confirmed_empty_markers_retire_by_creation_age_or_collection_pressure(
    monkeypatch, age_days, over_capacity, retired
):
    from datetime import datetime, timedelta, timezone

    client = MagicMock()
    doc = SimpleNamespace(
        id=jobs.marker_id('u', 'c'),
        reference=MagicMock(),
        update_time='observed',
        create_time=datetime.now(timezone.utc) - timedelta(days=age_days),
        to_dict=lambda: {'kind': jobs.KIND, 'owner_id': 'u', 'conversation_id': 'c'},
    )
    client.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = [doc]
    monkeypatch.setattr(consumer, 'MAX_COLLECTION_MARKERS', 0 if over_capacity else 10000)
    monkeypatch.setattr(consumer, 'rebuild', lambda *_: 'no_objects')
    retire = MagicMock(return_value='retired_no_objects')
    monkeypatch.setattr(jobs, 'retire_empty', retire)
    report = consumer.run(budget=SweepBudget(60), firestore_client=client)
    doc.reference.delete.assert_not_called()
    assert bool(retire.call_count) is retired
    if retired:
        assert retire.call_args.kwargs == {
            'observed_update_time': doc.reference.update.return_value.update_time,
            'firestore_client': client,
        }
    assert report['dispositions'] == {'retired_no_objects' if retired else 'deferred': 1}
    assert report['gauges']['marker_count'] == 1
    assert report['gauges']['oldest_age_seconds'] >= age_days * 86400
    assert report['gauges']['at_capacity'] is over_capacity


def test_collection_pressure_never_discards_privacy_hold_or_incomplete_discovery(monkeypatch):
    from datetime import datetime, timedelta, timezone

    client = MagicMock()
    doc = SimpleNamespace(
        id=jobs.marker_id('u', 'c'),
        reference=MagicMock(),
        update_time='observed',
        create_time=datetime.now(timezone.utc) - timedelta(days=30),
        to_dict=lambda: {'kind': jobs.KIND, 'owner_id': 'u', 'conversation_id': 'c'},
    )
    client.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = [doc]
    monkeypatch.setattr(consumer, 'MAX_COLLECTION_MARKERS', 0)
    monkeypatch.setattr(consumer, 'rebuild', lambda *_: None)
    assert consumer.run(budget=SweepBudget(60), firestore_client=client)['dispositions'] == {'deferred': 1}
    doc.reference.delete.assert_not_called()


def test_consumer_caps_work_independently_of_collection_scan(monkeypatch):
    client = MagicMock()
    docs = [
        SimpleNamespace(
            id=jobs.marker_id('u', str(i)),
            reference=MagicMock(),
            update_time='observed',
            to_dict=lambda i=i: {'kind': jobs.KIND, 'owner_id': 'u', 'conversation_id': str(i)},
        )
        for i in range(3)
    ]
    client.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = docs
    monkeypatch.setattr(consumer, 'MAX_PER_PASS', 2)
    rebuild = MagicMock(return_value=True)
    monkeypatch.setattr(consumer, 'rebuild', rebuild)
    assert consumer.run(budget=SweepBudget(60), firestore_client=client)['dispositions'] == {'rebuilt': 2}
    assert rebuild.call_count == 2
    docs[-1].reference.update.assert_not_called()


def test_socket_cleanup_is_one_content_free_bounded_batch():
    client = MagicMock()
    jobs.mark_many('u', ['one', 'two', 'one'], firestore_client=client)
    batch = client.batch.return_value
    assert batch.set.call_count == 2
    for call in batch.set.call_args_list:
        assert set(call.args[1]) == {'kind', 'owner_id', 'conversation_id', 'requested_at'}
    batch.commit.assert_called_once_with(timeout=1, retry=None)
    with pytest.raises(ValueError):
        jobs.mark_many('u', [str(i) for i in range(jobs.MAX_MARKERS_PER_BATCH + 1)], firestore_client=client)
    assert batch.commit.call_count == 1


@pytest.fixture
def retirement_store(client, monkeypatch):
    marker = (jobs.COLLECTION, jobs.marker_id('u', 'c'))
    client.rows[marker] = {'kind': jobs.KIND, 'owner_id': 'u', 'conversation_id': 'c'}
    get = StrictFirestoreDocument.get
    version = ['rotated']

    def snapshot(ref, *args, **kwargs):
        result = get(ref, *args, **kwargs)
        if ref.path == marker:
            result.update_time = version[0]
        return result

    # Only supply immutable snapshot metadata. The fixture still enforces all
    # transactional reads-before-delete; real version fencing is emulator-tested.
    monkeypatch.setattr(StrictFirestoreDocument, 'get', snapshot)
    return client, marker, version


@pytest.mark.parametrize(
    'sessions', [{'live': True}, {'abandoned': {'abandoned_at': 0}}, None, True, [], 'missing', {}]
)
def test_empty_retirement_requires_explicit_clear_producer_map(retirement_store, sessions):
    client, marker, _ = retirement_store
    if sessions == 'missing':
        client.rows[ROW].pop('record_upload_sessions')
    else:
        client.rows[ROW]['record_upload_sessions'] = sessions
    before = deepcopy(client.rows)
    result = jobs.retire_empty('u', 'c', observed_update_time='rotated', firestore_client=client)
    clear = isinstance(sessions, dict) and not sessions
    assert result == ('retired_no_objects' if clear else 'producer_fenced')
    assert client.rows == ({key: row for key, row in before.items() if key != marker} if clear else before)
    assert client.transactions[-1].updates == []
    assert client.transactions[-1].deletes == ([marker] if clear else [])


@pytest.mark.parametrize('race', ['replacement', 'missing_marker', 'missing_owner'])
def test_empty_retirement_refuses_changed_marker_or_unknown_owner(retirement_store, race):
    client, marker, version = retirement_store
    if race == 'replacement':
        version[0] = 'newer'
    elif race == 'missing_marker':
        client.rows.pop(marker)
    else:
        client.rows.pop(ROW)
    before = deepcopy(client.rows)
    assert jobs.retire_empty('u', 'c', observed_update_time='rotated', firestore_client=client) == (
        'producer_fenced' if race == 'missing_owner' else 'changed'
    )
    assert client.rows == before
    assert not client.transactions[-1].deletes


@pytest.mark.parametrize('pressure', [False, True])
def test_old_empty_marker_keeps_producer_minted_after_discovery(retirement_store, monkeypatch, pressure):
    from datetime import datetime, timedelta, timezone

    store, marker, _ = retirement_store
    client = MagicMock()
    doc = SimpleNamespace(
        id=marker[-1],
        reference=MagicMock(),
        update_time='before_rotation',
        create_time=datetime.now(timezone.utc) - timedelta(days=8),
        to_dict=lambda: store.rows[marker],
    )
    doc.reference.update.return_value.update_time = 'rotated'
    client.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = [doc]
    monkeypatch.setattr(consumer, 'MAX_COLLECTION_MARKERS', 0 if pressure else 10000)

    def discover_then_mint(*args):
        store.rows[ROW]['record_upload_sessions'] = {'new_tail': True}
        return 'no_objects'

    monkeypatch.setattr(consumer, 'rebuild', discover_then_mint)
    retire = jobs.retire_empty
    monkeypatch.setattr(
        jobs,
        'retire_empty',
        lambda uid, cid, **kw: retire(
            uid, cid, observed_update_time=kw['observed_update_time'], firestore_client=store
        ),
    )
    report = consumer.run(budget=SweepBudget(60), firestore_client=client)
    assert report['dispositions'] == {'producer_fenced': 1}
    assert report['gauges']['pressure_blocked'] is pressure
    assert report['gauges']['pressure_fenced_count'] == (1 if pressure else 0)
    assert marker in store.rows and not store.transactions[-1].deletes
    doc.reference.delete.assert_not_called()
    doc.reference.update.assert_called_once()  # Deferred work is already rotated.


@pytest.mark.parametrize('clear_one', [False, True])
def test_pressure_alerts_when_all_empty_candidates_are_fenced(monkeypatch, clear_one):
    from datetime import datetime, timedelta, timezone

    client = MagicMock()
    docs = [
        SimpleNamespace(
            id=jobs.marker_id('u', str(i)),
            reference=MagicMock(),
            update_time='old',
            create_time=datetime.now(timezone.utc) - timedelta(days=8),
            to_dict=lambda i=i: {'kind': jobs.KIND, 'owner_id': 'u', 'conversation_id': str(i)},
        )
        for i in range(3)
    ]
    client.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = docs
    monkeypatch.setattr(consumer, 'MAX_COLLECTION_MARKERS', 2)
    monkeypatch.setattr(consumer, 'rebuild', lambda *_: 'no_objects')
    monkeypatch.setattr(
        jobs,
        'retire_empty',
        MagicMock(
            side_effect=['producer_fenced', 'producer_fenced', 'retired_no_objects' if clear_one else 'producer_fenced']
        ),
    )
    report = consumer.run(budget=SweepBudget(60), firestore_client=client)
    assert report['outcome'] == 'capacity_exceeded'
    assert report['gauges']['pressure_blocked'] is (not clear_one)
    assert report['gauges']['pressure_fenced_count'] == (2 if clear_one else 3)
    assert consumer.PRESSURE_BLOCKED.collect()[0].samples[0].value == (0 if clear_one else 1)
    for doc in docs:
        doc.reference.delete.assert_not_called()  # Only the fenced transaction may retire empty debt.
