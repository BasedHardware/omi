"""Real pusher sessions plus strict Firestore: reconnects cannot forget custody."""

import asyncio
import json
import struct
import threading
from typing import get_args
from unittest.mock import AsyncMock
from unittest.mock import Mock

import pytest

from database.record_audio import seal_record_audio, mark_record_upload_failed, set_record_upload_pending
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_pusher_audio_timeline import (
    env,
    FakeWebSocket,
    HeldOpenWebSocket,
    _audio,
    _conversation,
    _run,
    RATE,
)
import routers.pusher as pusher
from database import record_audio as record_audio_db
from utils.pusher_record_barrier import PusherRecordBarrier
from utils.pusher_record_barrier import RECORD_BARRIER_FAILURES
from utils.pusher_record_barrier import RECORD_SEAL_REFUSED

PATH = ('users', 'uid-at', 'conversations', 'record')


@pytest.fixture
def records(env, monkeypatch):
    client = StrictFirestore()
    client.rows[PATH] = {'record_lane_owner': 'batch_live_v1', 'status': 'completed', 'opaque_content': 'preserved'}
    monkeypatch.setattr(record_audio_db, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_audio_db, 'seal_record_audio', seal_record_audio)
    monkeypatch.setattr(record_audio_db, 'mark_record_upload_failed', mark_record_upload_failed)
    monkeypatch.setattr(record_audio_db, 'set_record_upload_pending', set_record_upload_pending)
    monkeypatch.setattr(pusher, 'process_conversation_task', AsyncMock())
    monkeypatch.setattr(pusher, 'start_background_task', lambda coro, **kwargs: coro.close())
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'false')
    return client


def _finalize():
    return struct.pack('<I', 104) + json.dumps({'conversation_id': 'record', 'language': 'en'}).encode()


@pytest.mark.parametrize('durable', [False, True])
@pytest.mark.parametrize('owner', ['batch_live_v1', 'batch_sync_v1'])
async def test_reconnect_finalize_without_audio_seals_persisted_batch_owner(records, env, monkeypatch, durable, owner):
    records.rows[PATH]['record_lane_owner'] = owner
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', str(durable).lower())
    await _run(FakeWebSocket([_conversation('record'), _finalize()]))
    assert not env  # Nothing flushed in this session.
    assert records.rows[PATH]['record_audio_closed'] is True
    assert records.rows[PATH]['opaque_content'] == 'preserved'
    assert all(not tx.sets and not tx.creates for tx in records.transactions)


@pytest.mark.parametrize('owner', [None, 'legacy_final_pass_v1'])
@pytest.mark.parametrize('durable', [False, True])
async def test_reconnect_never_seals_legacy_or_unowned(records, monkeypatch, owner, durable):
    records.rows[PATH]['record_lane_owner'] = owner
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', str(durable).lower())
    await _run(FakeWebSocket([_conversation('record'), _finalize()]))
    assert 'record_audio_closed' not in records.rows[PATH]
    assert all(not tx.updates for tx in records.transactions)


@pytest.mark.parametrize('durable', [False, True])
async def test_earlier_exhausted_upload_survives_clean_reconnect(records, monkeypatch, durable):
    def failed(*args, **kwargs):
        raise ValueError('synthetic upload failure')

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', failed)
    await _run(FakeWebSocket([_conversation('record'), _audio(100, b'\x01\x00' * RATE)]))
    assert records.rows[PATH]['record_upload_failed'] is True
    assert records.rows[PATH]['record_audio_closed'] is False
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', str(durable).lower())
    await _run(FakeWebSocket([_conversation('record'), _finalize()]))
    assert records.rows[PATH]['record_audio_closed'] is False


async def test_old_session_pending_upload_blocks_empty_reconnect(records):
    assert set_record_upload_pending('uid-at', 'record', 'old-producer', True, firestore_client=records)
    await _run(FakeWebSocket([_conversation('record'), _finalize()]))
    assert not records.rows[PATH]['record_audio_closed']
    assert records.rows[PATH]['record_upload_sessions'] == {'old-producer': True}
    assert set_record_upload_pending('uid-at', 'record', 'old-producer', False, firestore_client=records)
    await _run(FakeWebSocket([_conversation('record'), _finalize()]))
    assert records.rows[PATH]['record_audio_closed']


def test_failure_invalidates_prior_seal_and_is_sticky(records):
    assert seal_record_audio('uid-at', 'record', firestore_client=records) is None
    assert mark_record_upload_failed('uid-at', 'record', firestore_client=records)
    assert seal_record_audio('uid-at', 'record', firestore_client=records) == 'upload_failed'
    assert records.rows[PATH]['record_upload_failed'] and not records.rows[PATH]['record_audio_closed']


def test_missing_row_never_recreated(records):
    records.rows.clear()
    assert seal_record_audio('uid-at', 'record', firestore_client=records) == 'deleted'
    assert not mark_record_upload_failed('uid-at', 'record', firestore_client=records)
    assert not set_record_upload_pending('uid-at', 'record', 'producer', True, firestore_client=records)
    assert not records.rows


def test_one_session_cannot_clear_another_sessions_upload(records):
    for token in ('producer-a', 'producer-b'):
        set_record_upload_pending('uid-at', 'record', token, True, firestore_client=records)
    set_record_upload_pending('uid-at', 'record', 'producer-a', False, firestore_client=records)
    assert seal_record_audio('uid-at', 'record', firestore_client=records) == 'producer_pending'
    assert records.rows[PATH]['record_upload_sessions'] == {'producer-b': True}


@pytest.mark.parametrize('late_failure', [False, True])
@pytest.mark.parametrize('initial_owner', [None, 'batch_live_v1'])
async def test_real_overlapping_sessions_withhold_seal_until_old_upload_finishes(
    records, monkeypatch, late_failure, initial_owner
):
    records.rows[PATH]['record_lane_owner'] = initial_owner
    loop = asyncio.get_running_loop()
    uploading = asyncio.Event()
    disconnect = asyncio.Event()
    release_upload = threading.Event()
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL', 0.001)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_CHUNK_DURATION', 0.001)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_BATCH_MAX_AGE', 0.001)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_MAX_RETRIES', 0)

    def upload(*args, **kwargs):
        # Persisted before any accepted audio can be queued/uploaded.
        assert records.rows[PATH]['record_upload_sessions']
        loop.call_soon_threadsafe(uploading.set)
        assert release_upload.wait(10)
        if late_failure:
            raise OSError('synthetic delayed upload failure')

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    old = asyncio.create_task(
        _run(HeldOpenWebSocket([_conversation('record'), _audio(100, b'\x01\x00' * RATE)], disconnect))
    )
    try:
        await asyncio.wait_for(uploading.wait(), 5)
        # A finalizer may claim an unowned capture while the earlier upload is
        # still outstanding. Its pre-ownership producer token must survive.
        records.rows[PATH]['record_lane_owner'] = 'batch_live_v1'
        await _run(FakeWebSocket([_conversation('record'), _finalize()]))
        assert not records.rows[PATH]['record_audio_closed']
    finally:
        release_upload.set()
        disconnect.set()
        await asyncio.wait_for(old, 10)
    assert bool(records.rows[PATH].get('record_upload_failed')) == late_failure
    assert records.rows[PATH]['record_audio_closed'] is (not late_failure)


@pytest.mark.parametrize('phase', ['begin', 'finish', 'seal'])
async def test_firestore_bookkeeping_failure_never_prevents_audio_upload(records, env, monkeypatch, phase):
    real_pending = record_audio_db.set_record_upload_pending

    def pending(uid, cid, token, active, **kwargs):
        if active is (phase == 'begin'):
            raise OSError('synthetic bookkeeping outage')
        return real_pending(uid, cid, token, active, **kwargs)

    if phase == 'seal':
        monkeypatch.setattr(record_audio_db, 'seal_record_audio', Mock(side_effect=OSError('synthetic seal outage')))
    else:
        monkeypatch.setattr(record_audio_db, 'set_record_upload_pending', pending)
    before = RECORD_BARRIER_FAILURES.labels(stage=phase)._value.get()
    ws = FakeWebSocket([_conversation('record'), _audio(100, b'\x01\x00' * RATE)])
    await _run(ws)
    assert len(env) == 1 and len(env[0][1]['data']) == RATE * 2
    assert ws.close_code == 1000
    assert bool(records.rows[PATH].get('record_upload_failed')) is (phase == 'begin')
    assert not records.rows[PATH]['record_audio_closed']
    assert RECORD_BARRIER_FAILURES.labels(stage=phase)._value.get() == before + (1 if phase == 'begin' else 3)


async def test_failure_marker_outage_does_not_abort_remaining_uploads(records, env, monkeypatch):
    other_path = (*PATH[:-1], 'other')
    records.rows[other_path] = {'record_lane_owner': 'batch_live_v1'}
    original = pusher.upload_audio_chunks_batch

    def upload(chunks, uid, cid, *args, **kwargs):
        if cid == 'record':
            raise OSError('synthetic upload failure')
        return original(chunks, uid, cid, *args, **kwargs)

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', upload)
    monkeypatch.setattr(pusher, 'PRIVATE_CLOUD_SYNC_MAX_RETRIES', 0)
    monkeypatch.setattr(record_audio_db, 'mark_record_upload_failed', Mock(side_effect=OSError('synthetic outage')))
    before = RECORD_BARRIER_FAILURES.labels(stage='failure_marker')._value.get()
    pcm = b'\x01\x00' * RATE
    await _run(FakeWebSocket([_conversation('record'), _audio(100, pcm), _conversation('other'), _audio(200, pcm)]))
    assert [cid for cid, _ in env] == ['other']
    assert not records.rows[PATH].get('record_audio_closed')
    assert records.rows[other_path]['record_audio_closed']
    assert RECORD_BARRIER_FAILURES.labels(stage='failure_marker')._value.get() == before + 1


@pytest.mark.parametrize('persisted_cap', [False, True])
async def test_session_token_cap_never_drops_audio(records, env, monkeypatch, persisted_cap):
    before = RECORD_BARRIER_FAILURES.labels(stage='capacity')._value.get()
    if persisted_cap:
        records.rows[PATH]['record_upload_sessions'] = {str(i): True for i in range(128)}
    else:
        barrier = PusherRecordBarrier('uid-at')
        barrier.checked_conversations = {str(i) for i in range(128)}
        monkeypatch.setattr(pusher, 'PusherRecordBarrier', lambda _: barrier)
    await _run(FakeWebSocket([_conversation('record'), _audio(100, b'\x01\x00' * RATE)]))
    assert len(env) == 1
    assert records.rows[PATH]['record_upload_failed']
    assert not records.rows[PATH]['record_audio_closed']
    assert RECORD_BARRIER_FAILURES.labels(stage='capacity')._value.get() == before + 1


async def test_legacy_audio_adds_no_record_metadata_writes(records, env):
    records.rows[PATH]['record_lane_owner'] = 'legacy_final_pass_v1'
    await _run(FakeWebSocket([_conversation('record'), _audio(100, b'\x01\x00' * RATE)]))
    assert len(env) == 1
    assert all(not tx.updates for tx in records.transactions)
    assert not mark_record_upload_failed('uid-at', 'record', firestore_client=records)
    assert all(not tx.updates for tx in records.transactions)


async def test_failed_token_clear_is_retained_and_can_retry_without_failure_marker(records, monkeypatch):
    barrier = PusherRecordBarrier('uid-at')
    await barrier.begin_recording('record')
    token = barrier.upload_sessions['record']
    original = record_audio_db.set_record_upload_pending
    monkeypatch.setattr(record_audio_db, 'set_record_upload_pending', Mock(side_effect=OSError('synthetic outage')))
    assert not await barrier.finish_recording('record')
    assert barrier.upload_sessions['record'] == token
    assert ('record', token) in barrier.pending_clears
    assert not records.rows[PATH].get('record_upload_failed')
    monkeypatch.setattr(record_audio_db, 'set_record_upload_pending', original)
    assert await barrier.finish_recording('record')
    assert records.rows[PATH]['record_audio_closed']
    assert not barrier.upload_sessions and not barrier.pending_clears


async def test_close_retries_without_another_finalize_and_then_clears(records, env, monkeypatch):
    original = record_audio_db.set_record_upload_pending
    clears = []

    def pending(uid, cid, token, active, **kwargs):
        if not active:
            clears.append(token)
            if len(clears) < 3:
                raise OSError('synthetic transient clear failure')
        return original(uid, cid, token, active, **kwargs)

    monkeypatch.setattr(record_audio_db, 'set_record_upload_pending', pending)
    await _run(FakeWebSocket([_conversation('record'), _audio(100, b'\x01\x00' * RATE)]))
    assert len(env) == 1 and len(clears) == 3
    assert records.rows[PATH]['record_audio_closed']
    assert records.rows[PATH]['record_upload_sessions'] == {}


async def test_degraded_failure_persistence_uses_shared_fallback(records, monkeypatch):
    import utils.pusher_record_barrier as module

    fallback = Mock()
    monkeypatch.setattr(module, 'record_fallback', fallback)
    monkeypatch.setattr(record_audio_db, 'mark_record_upload_failed', Mock(side_effect=OSError('synthetic outage')))
    await PusherRecordBarrier('uid-at').fail_recording('record')
    fallback.assert_called_once()
    assert fallback.call_args.kwargs['component'] == 'pusher'
    assert fallback.call_args.kwargs['outcome'] == 'degraded'


@pytest.mark.parametrize(
    ('patch', 'reason'),
    [
        ({'record_upload_sessions': {'another': True}}, 'producer_pending'),
        ({'record_upload_failed': True}, 'upload_failed'),
        ({'record_lane_owner': 'legacy_final_pass_v1'}, 'not_batch_owner'),
        ({'deleted': True}, 'deleted'),
    ],
)
async def test_refused_seal_reason_is_counted_without_writes_or_identifiers(records, caplog, patch, reason):
    records.rows[PATH].update(patch)
    assert seal_record_audio('uid-at', 'record', firestore_client=records) == reason
    before = RECORD_SEAL_REFUSED.labels(reason=reason)._value.get()
    with caplog.at_level('INFO', logger='utils.pusher_record_barrier'):
        assert await PusherRecordBarrier('uid-at').finish_recording('record')
    assert RECORD_SEAL_REFUSED.labels(reason=reason)._value.get() == before + 1
    assert [r.getMessage() for r in caplog.records] == [f'event=record_seal_refused reason={reason}']
    assert all(not tx.updates for tx in records.transactions)


def test_seal_refusal_vocabulary_is_closed():
    assert set(get_args(record_audio_db.RecordSealRefusal)) == {
        'producer_pending',
        'upload_failed',
        'not_batch_owner',
        'deleted',
    }


async def test_cancelled_finish_retains_token_for_background_retry(records, monkeypatch):
    import utils.pusher_record_barrier as module

    barrier = PusherRecordBarrier('uid-at')
    await barrier.begin_recording('record')
    token = barrier.upload_sessions['record']
    entered = asyncio.Event()
    original = module.run_blocking

    async def blocked(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(module, 'run_blocking', blocked)
    task = asyncio.create_task(barrier.finish_recording('record'))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert set(records.rows[PATH]['record_upload_sessions']) == {token}
    assert records.rows[PATH]['record_audio_closed'] is False
    assert barrier.upload_sessions['record'] == token
    assert ('record', token) in barrier.pending_clears
    monkeypatch.setattr(module, 'run_blocking', original)
    assert await barrier.finish_recording('record')
    assert records.rows[PATH]['record_audio_closed']
