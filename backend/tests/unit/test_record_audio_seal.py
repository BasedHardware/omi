"""Real pusher sessions plus strict Firestore: reconnects cannot forget custody."""

import asyncio
import json
import struct
import threading
from unittest.mock import AsyncMock

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
    assert seal_record_audio('uid-at', 'record', firestore_client=records)
    assert mark_record_upload_failed('uid-at', 'record', firestore_client=records)
    assert not seal_record_audio('uid-at', 'record', firestore_client=records)
    assert records.rows[PATH]['record_upload_failed'] and not records.rows[PATH]['record_audio_closed']


def test_missing_row_never_recreated(records):
    records.rows.clear()
    assert not seal_record_audio('uid-at', 'record', firestore_client=records)
    assert not mark_record_upload_failed('uid-at', 'record', firestore_client=records)
    assert not set_record_upload_pending('uid-at', 'record', 'producer', True, firestore_client=records)
    assert not records.rows


def test_one_session_cannot_clear_another_sessions_upload(records):
    for token in ('producer-a', 'producer-b'):
        set_record_upload_pending('uid-at', 'record', token, True, firestore_client=records)
    set_record_upload_pending('uid-at', 'record', 'producer-a', False, firestore_client=records)
    assert not seal_record_audio('uid-at', 'record', firestore_client=records)
    assert records.rows[PATH]['record_upload_sessions'] == {'producer-b': True}


@pytest.mark.parametrize('late_failure', [False, True])
async def test_real_overlapping_sessions_withhold_seal_until_old_upload_finishes(records, monkeypatch, late_failure):
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
        await _run(FakeWebSocket([_conversation('record'), _finalize()]))
        assert not records.rows[PATH]['record_audio_closed']
    finally:
        release_upload.set()
        disconnect.set()
        await asyncio.wait_for(old, 10)
    assert bool(records.rows[PATH].get('record_upload_failed')) == late_failure
    assert records.rows[PATH]['record_audio_closed'] is (not late_failure)
