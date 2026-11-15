"""Pre-review regressions: publication ordering, metadata failures and expiry."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from google.api_core.exceptions import ServiceUnavailable
import pytest
from starlette.responses import JSONResponse

from config import record_seal_rules as lease
from config.record_audio import record_identity
from database import record_audio, record_custody_append as custody, record_token_lease_metrics as metrics
from database import record_custody_receipts as receipts, record_recovery_gate as gate
from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from database.batch_pipeline_record_lease_recovery import recovery_segment
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction
from tests.unit.test_record_token_lease import NOW, PATH, ROW, POD
from utils import pusher_record_barrier as barrier_module
from utils.batch_pipeline import record_lease_append as append
from utils.sync import record_token_lease as request


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(custody.time, 'time', lambda: NOW)
    client = StrictFirestore({PATH: ROW, ('users', 'synthetic'): {'private_cloud_sync_enabled': True}})
    monkeypatch.setattr(custody, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_audio, 'get_firestore_client', lambda: client)
    return client


@pytest.mark.parametrize(
    'clocks',
    [{}, {'finished_at': None}, {'started_at': None}, {'finished_at': datetime(2026, 1, 1)}, {'started_at': 'invalid'}],
)
async def test_unfinished_or_invalid_clock_upload_keeps_original_success(world, monkeypatch, clocks):
    row = {**ROW, 'status': 'in_progress', 'record_audio_closed': False, **clocks}
    if not clocks:
        row.pop('finished_at')
    world.rows[PATH] = row
    storage = Mock(side_effect=AssertionError('unfinished row attempted gap retention'))
    monkeypatch.setattr(append.gap, 'create_storage_client', storage)
    response = JSONResponse(status_code=202, content={'status': 'queued'})

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'live')
        await append.retain_upload('synthetic', 'record', row, ['wal'], Mock())
        request.stored(['wal'], ['archive'])
        return response

    assert await upload() is response
    assert world.rows[PATH]['record_upload_revision'] == 8
    storage.assert_not_called()


@pytest.mark.parametrize('field', ['finished_at', 'started_at'])
@pytest.mark.parametrize('value', [None, 'invalid', datetime(2026, 1, 1)])
def test_closed_retention_guards_each_timestamp_before_io(monkeypatch, field, value):
    row = {
        **ROW,
        'record_audio_closed': True,
        'started_at': datetime.fromtimestamp(NOW - 90000, timezone.utc),
        field: value,
    }
    storage = Mock(side_effect=AssertionError('invalid clock performed storage IO'))
    monkeypatch.setattr(append.gap, 'create_storage_client', storage)
    append.retain('synthetic', 'record', row, ['wal'])
    storage.assert_not_called()


async def test_new_pusher_token_preserves_late_observation_after_lost_commit(world, monkeypatch):
    original = StrictFirestoreTransaction._commit
    lost = []

    def commit(tx):
        original(tx)
        if not lost:
            lost.append(True)
            raise ServiceUnavailable('committed registration response lost')

    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit)
    monkeypatch.setattr(barrier_module, 'producer_identity', lambda: POD)
    barrier = barrier_module.PusherRecordBarrier('synthetic')
    before = metrics.LATE_APPEND._value.get()
    try:
        await barrier.begin_recording('record')
        token = barrier.upload_sessions['record']
        assert world.rows[PATH]['record_upload_sessions'][token]['append_late']
        assert world.rows[PATH]['record_upload_revision'] == 8
        assert 'record' in barrier.late_appends
        barrier.append_committed('record')
        barrier.append_committed('record')
        assert metrics.LATE_APPEND._value.get() == before + 1
    finally:
        barrier._forget_lease('record')


@pytest.mark.parametrize('returned', [[], ['archive-a']])
async def test_selected_subset_preserves_success_and_accounts_real_append(world, returned):
    before = metrics.LATE_APPEND._value.get()
    response = JSONResponse(status_code=202, content={'status': 'queued'})

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'mixed')
        archived = await request.archive(
            lambda uid, paths, metadata: returned if paths[0] == 'selected' else [],
            'synthetic',
            ['selected', 'unselected'],
            {},
        )
        request.stored(['selected', 'unselected'], archived)
        return response

    assert await upload() is response
    assert world.rows[PATH]['record_upload_revision'] == 7 + bool(returned)
    assert metrics.LATE_APPEND._value.get() == before + bool(returned)
    assert 'custody:mixed' not in world.rows[PATH]['record_upload_sessions']


@pytest.mark.parametrize('mode', ['serve', 'shadow'])
async def test_renewal_failure_does_not_interrupt_live_audio(world, monkeypatch, mode):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    monkeypatch.setattr(barrier_module, 'producer_identity', lambda: POD)
    barrier = barrier_module.PusherRecordBarrier('synthetic')
    await barrier.begin_recording('record')
    original_time = barrier.lease_renewed_at['record']
    barrier.lease_renewed_at['record'] = original_time - 7200
    failure = Mock(side_effect=OSError('metadata is unavailable'))
    monkeypatch.setattr(record_audio, 'renew_record_token_lease', failure)
    stored = []
    try:
        await barrier.renew_recording('record')
        # This is the caller order used by both receive and upload batches:
        # the failed metadata side channel must return to the storage lane.
        stored.append(b'live audio')
        await barrier.renew_recording('record')
        assert failure.call_count == 2  # clock not advanced on failure
        assert barrier.lease_renewed_at['record'] == original_time - 7200
        assert stored == [b'live audio']
        assert 'record' not in barrier.failed_recordings
    finally:
        barrier._forget_lease('record')


@pytest.mark.parametrize('error', [OSError('failed begin'), record_audio.RecordUploadCapacityExceeded('capacity')])
async def test_failed_registration_cannot_be_resurrected_by_same_frame(world, monkeypatch, error):
    monkeypatch.setattr(record_audio, 'set_record_upload_pending', Mock(side_effect=error))
    renew = Mock(side_effect=AssertionError('unregistered candidate was resurrected'))
    monkeypatch.setattr(record_audio, 'renew_record_token_lease', renew)
    barrier = barrier_module.PusherRecordBarrier('synthetic')
    await barrier.begin_recording('record')
    assert 'record' in barrier.upload_sessions  # candidate retained for abandonment
    assert 'record' not in barrier.registered_sessions
    await barrier.renew_recording('record')
    renew.assert_not_called()
    assert world.rows[PATH]['record_upload_revision'] == 8  # failure marker only


async def test_fail_recording_releases_all_lease_bookkeeping(world, monkeypatch):
    barrier = barrier_module.PusherRecordBarrier('synthetic')
    await barrier.begin_recording('record')
    barrier.lease_locks['record'] = asyncio.Lock()
    before = metrics.ACTIVE._value.get()
    assert 'record' in barrier.late_appends
    await barrier.fail_recording('record')
    assert not barrier.lease_renewed_at and not barrier.lease_locks and not barrier.late_appends
    assert not barrier.registered_sessions
    assert metrics.ACTIVE._value.get() == before - 1


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_recovery_is_parked_until_original_publication_even_after_rollback(world, monkeypatch, mode):
    content, original = record_identity('synthetic', 'record')
    world.rows[PATH]['record_audio_closed'] = False
    world.rows[PATH]['record_upload_sessions'] = {}
    original_path = ('batch_pipeline_dev_jobs', original)
    world.rows[original_path] = {'state': 'ready', 'record_input_upload_revision': 7}
    assert custody.begin('synthetic', 'record', 'custody:waiting', firestore_client=world)
    custody.finish('synthetic', 'record', 'custody:waiting', accepted=True, firestore_client=world)
    segment = recovery_segment('synthetic', 'record')
    recovery = ('batch_pipeline_dev_jobs', segment)
    assert world.rows[recovery]['state'] == gate.WAITING_STATE
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    assert not gate.promote(world, 'batch_pipeline_dev', segment, NOW)
    assert world.rows[recovery]['state'] == gate.WAITING_STATE
    assert not gate.promote(world, 'batch_pipeline_dev', segment, NOW + 1)
    assert not world.transactions[-1].has_written  # stale scans cannot rewrite the backoff
    world.rows[original_path]['state'] = 'committed'
    assert gate.promote(world, 'batch_pipeline_dev', segment, NOW + 61)
    assert world.rows[recovery]['state'] == 'record_pending'
    assert not gate.promote(world, 'batch_pipeline_dev', segment, NOW + 62)


@pytest.mark.parametrize('accepted', [False, True])
@pytest.mark.parametrize('operation', ['finish', 'recover'])
@pytest.mark.parametrize('authority', ['erasing', 'missing_user', 'deleted_row'])
def test_every_receipt_write_enrolls_erasure_authority(world, accepted, operation, authority):
    assert custody.begin('synthetic', 'record', 'custody:erase', firestore_client=world)
    world.rows[PATH].pop('finished_at')  # prepare_recovery would return early
    if authority == 'erasing':
        world.rows['batch_pipeline_privacy', privacy_owner_key('synthetic')] = {'purging': True, 'generation': 1}
    elif authority == 'missing_user':
        world.rows.pop(('users', 'synthetic'))
    else:
        world.rows[PATH]['deleted'] = True
    before = deepcopy(world.rows)
    with pytest.raises(BatchPrivacyBlocked):
        if operation == 'finish':
            custody.finish('synthetic', 'record', 'custody:erase', accepted=accepted, firestore_client=world)
        else:
            custody.recover_committed('synthetic', 'record', 'custody:erase', firestore_client=world)
    assert world.rows == before
    assert not any('record_custody_recoveries' in path for path in world.rows)


def test_finish_receipt_expiry_outlives_request_and_is_exported(world):
    assert receipts.RETENTION_SECONDS > lease.custody_token_lease_seconds()
    assert custody.begin('synthetic', 'record', 'custody:expiry', firestore_client=world)
    custody.finish('synthetic', 'record', 'custody:expiry', accepted=False, firestore_client=world)
    receipt = next(row for path, row in world.rows.items() if 'record_custody_recoveries' in path)
    assert receipt['expires_at'] == datetime.fromtimestamp(NOW + receipts.RETENTION_SECONDS, timezone.utc)


def test_receipt_prune_uses_bounded_expired_page_only(monkeypatch):
    docs = [SimpleNamespace(reference=object()) for _ in range(3)]
    pages = Mock(side_effect=[docs])
    monkeypatch.setattr(receipts, 'expired_page', pages)
    client = Mock()
    budget = SimpleNamespace(check=lambda: None, timeout=lambda: 10)
    assert receipts.prune(client, now=NOW, budget=budget) == 3
    assert client.batch.return_value.delete.call_count == 3
    client.batch.return_value.commit.assert_called_once_with(timeout=10, retry=None)


async def test_failure_during_inflight_renewal_cannot_restore_bookkeeping(world, monkeypatch):
    barrier = barrier_module.PusherRecordBarrier('synthetic')
    await barrier.begin_recording('record')
    barrier.lease_renewed_at['record'] -= 7200
    before = metrics.ACTIVE._value.get()
    entered, release = asyncio.Event(), asyncio.Event()
    original = barrier_module.run_blocking

    async def renew(executor, fn, *args, **kwargs):
        if fn is record_audio.renew_record_token_lease:
            entered.set()
            await release.wait()
            kwargs['late_observation']['late'] = True
            return True
        return await original(executor, fn, *args, **kwargs)

    monkeypatch.setattr(barrier_module, 'run_blocking', renew)
    task = asyncio.create_task(barrier.renew_recording('record'))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        await barrier.fail_recording('record')
    finally:
        release.set()
        await task
    assert not barrier.registered_sessions
    assert not barrier.lease_renewed_at and not barrier.lease_locks and not barrier.late_appends
    assert metrics.ACTIVE._value.get() == before - 1


def test_active_repair_promotion_does_not_depend_on_enabling_the_idle_worker():
    from pathlib import Path
    import yaml

    chart = Path(__file__).resolve().parents[2] / 'charts/batch-pipeline-worker'
    defaults = yaml.safe_load((chart / 'values.yaml').read_text())
    prod = yaml.safe_load((chart / 'prod_omi_batch-pipeline-worker_values.yaml').read_text())
    repair = defaults['recordSealRepair'] | prod['recordSealRepair']
    worker = defaults['recordSealWorker'] | prod['recordSealWorker']
    assert repair['enabled'] and repair['runtimeEnabled'] and not repair['suspend']
    assert repair['mode'] == 'apply' and repair['serverFlags']
    assert worker['runtimeEnabled'] is False and worker['serverFlags'] == {}


def test_custody_heartbeat_cannot_renew_a_previously_mislabelled_pusher(world):
    # Older manifest code overwrote signal_source even on a pod-owned token.
    # Identity, not that mutable label alone, distinguishes a custody fence.
    frame = {**POD, 'last_signal_at': NOW - 7200, 'lease_expires_at': NOW - 3600, 'signal_source': 'custody_append'}
    fence = {
        'pod': '',
        'process_started_at': NOW - 2000,
        'last_signal_at': NOW - 2000,
        'lease_expires_at': NOW + 1900,
        'signal_source': 'custody_append',
    }
    world.rows[PATH].update(
        record_audio_closed=False,
        record_audio_partial=None,
        record_upload_sessions={'old-frame': frame, 'custody:live': fence},
    )
    assert record_audio.renew_record_token_lease(
        'synthetic', 'record', source='custody_append', session='custody:live', firestore_client=world
    )
    tokens = world.rows[PATH]['record_upload_sessions']
    assert tokens['old-frame'] == frame
    assert tokens['custody:live']['last_signal_at'] == NOW
    assert tokens['custody:live']['lease_expires_at'] == NOW + lease.custody_token_lease_seconds()
    assert world.rows[PATH]['record_upload_revision'] == 7
