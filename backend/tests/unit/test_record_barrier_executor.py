"""Record custody retries cannot occupy integration consumers' DB workers."""

import asyncio
import json
import os
import struct
import threading
from types import SimpleNamespace
from concurrent.futures import Executor, Future
from unittest.mock import Mock

import pytest

from utils import executors
from utils import pusher_record_barrier as barrier_module
from tests.unit.test_pusher_audio_timeline import env, HeldOpenWebSocket, _audio, _conversation, _run, RATE
from tests.unit.test_record_audio_seal import records
from tests.unit.test_record_audio_seal import PATH
import routers.pusher as pusher


async def test_all_barrier_transactions_use_isolated_pool(records, monkeypatch):
    """Exercise real begin, clear, seal and failure marker against strict Firestore."""
    db_submit = Mock(side_effect=AssertionError('barrier used shared DB pool'))
    monkeypatch.setattr(executors.db_executor, 'submit', db_submit)
    seen = []
    for name in ('set_record_upload_pending', 'seal_record_audio', 'mark_record_upload_failed'):
        original = getattr(barrier_module.record_audio_db, name)

        def capture(*args, _fn=original, _name=name, **kwargs):
            seen.append((_name, threading.current_thread().name))
            return _fn(*args, **kwargs)

        monkeypatch.setattr(barrier_module.record_audio_db, name, capture)
    barrier = barrier_module.PusherRecordBarrier('uid-at')
    await barrier.begin_recording('record')
    assert await barrier.finish_recording('record')
    await barrier.fail_recording('record')
    assert [name for name, _ in seen] == [
        'set_record_upload_pending',
        'set_record_upload_pending',
        'seal_record_audio',
        'mark_record_upload_failed',
    ]
    assert all(thread.startswith('record-barrier') for _, thread in seen)
    db_submit.assert_not_called()
    assert executors.record_barrier_executor in executors._ALL_EXECUTORS


class HeldExecutor(Executor):
    """A full worker/queue whose pending calls finish only when explicitly released."""

    def __init__(self):
        self.pending = []
        self.submitted = asyncio.Event()

    def submit(self, fn, /, *args, **kwargs):
        future = Future()
        self.pending.append((future, fn, args, kwargs))
        self.submitted.set()
        return future

    def release(self):
        for future, fn, args, kwargs in self.pending:
            if not future.cancelled():
                future.set_result(fn(*args, **kwargs))
        self.pending.clear()


async def test_saturated_barrier_does_not_block_real_transcript_or_audio_consumers(env, monkeypatch):
    """Keep a barrier call pending while a separate real pusher session drains both queues."""
    held = HeldExecutor()
    monkeypatch.setattr(barrier_module, 'record_barrier_executor', held)
    # This integration-only session does not itself need recording custody.
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda _: False)
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda _: 0)
    monkeypatch.setattr(pusher, 'TRANSCRIPT_QUEUE_FLUSH_INTERVAL', 0.001)
    received = {'transcript': asyncio.Event(), 'audio': asyncio.Event()}
    loop = asyncio.get_running_loop()

    async def consume(kind, *args, **kwargs):
        # Both production integration paths need shared DB capacity.
        await executors.run_blocking(executors.db_executor, lambda: loop.call_soon_threadsafe(received[kind].set))

    async def transcript(*args, **kwargs):
        await consume('transcript')

    async def audio(*args, **kwargs):
        await consume('audio')

    monkeypatch.setattr(pusher, 'trigger_realtime_integrations', transcript)
    monkeypatch.setattr(pusher, 'realtime_transcript_webhook', transcript)
    monkeypatch.setattr(pusher, 'send_audio_bytes_developer_webhook', audio)
    barrier = barrier_module.PusherRecordBarrier('uid-at')
    pending = asyncio.create_task(barrier.begin_recording('held-record'))
    release_session = asyncio.Event()
    session = None
    try:
        await asyncio.wait_for(held.submitted.wait(), 5)
        transcript_frame = struct.pack('<I', 102) + json.dumps({'segments': [{'text': 'test'}]}).encode()
        ws = HeldOpenWebSocket(
            [_conversation('integration'), transcript_frame, _audio(100, b'\x01\x00' * RATE)], release_session
        )
        session = asyncio.create_task(_run(ws))
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in received.values())), 5)
        assert not pending.done(), 'Consumers must drain before barrier capacity returns'
    finally:
        held.release()
        release_session.set()
        await pending
        if session is not None:
            await asyncio.wait_for(session, 10)


def test_barrier_worker_and_queue_bounds_and_capacity_metric():
    pool = executors.record_barrier_executor
    assert pool._max_workers == int(os.getenv('PUSHER_RECORD_BARRIER_EXECUTOR_WORKERS', '16'))
    assert executors.db_executor._max_workers == int(os.getenv('PUSHER_DB_EXECUTOR_WORKERS', '32'))
    assert pool.max_queue_size == 64 and pool.wait_on_saturation
    assert executors.EXECUTOR_MAX_WORKERS.labels(executor='record_barrier')._value.get() == pool._max_workers
    assert executors.EXECUTOR_MAX_WORKERS.labels(executor='db')._value.get() == executors.db_executor._max_workers


@pytest.mark.parametrize('reason', ['admission', 'outstanding'])
@pytest.mark.parametrize('attempts', [0, 4])
@pytest.mark.parametrize('stage', ['finish', 'seal'])
async def test_admission_refusal_keeps_write_failure_ladder_and_token(records, monkeypatch, reason, attempts, stage):
    barrier = barrier_module.PusherRecordBarrier('uid-at')
    await barrier.begin_recording('record')
    token = barrier.upload_sessions['record']
    barrier.keep_close_pending = True
    if attempts:
        barrier.close_failures['record'] = attempts
    monkeypatch.setattr(barrier_module, 'time', SimpleNamespace(monotonic=lambda: 100.0))
    # Exercise both ends of the fixed jitter range without real-clock sleeps.
    monkeypatch.setattr(barrier_module.random, 'uniform', lambda low, high: low if attempts == 0 else high)
    active, outstanding = threading.BoundedSemaphore(4), threading.BoundedSemaphore(12)
    occupied = active if reason == 'admission' else outstanding
    for _ in range(4 if reason == 'admission' else 12):
        occupied.acquire()
    monkeypatch.setattr(barrier_module, '_close_retry_slots', active)
    monkeypatch.setattr(barrier_module, '_close_outstanding_slots', outstanding)
    if stage == 'seal':
        # An empty reconnect reaches the same refusal at seal, without clearing
        # the earlier producer's durable token.
        barrier = barrier_module.PusherRecordBarrier('uid-at')
        barrier.keep_close_pending = True
        if attempts:
            barrier.close_failures['record'] = attempts
    counter = barrier_module.RECORD_CLOSE_REFUSALS.labels(reason=reason)
    before = counter._value.get()
    failures = {s: barrier_module.RECORD_BARRIER_FAILURES.labels(stage=s)._value.get() for s in ('finish', 'seal')}
    transactions = len(records.transactions)
    assert not await barrier.finish_recording('record')
    assert barrier.close_failures == ({'record': attempts} if attempts else {})
    assert barrier.close_retry_at['record'] == 100.0 + (0.5 if attempts == 0 else 2.0)
    assert counter._value.get() == before + 1
    # Repeated scans before the retry time do not touch admission or storage.
    for _ in range(10):
        assert not await barrier.finish_recording('record')
    assert counter._value.get() == before + 1
    assert len(records.transactions) == transactions
    assert set(records.rows[PATH]['record_upload_sessions']) == {token}
    for s, value in failures.items():
        assert barrier_module.RECORD_BARRIER_FAILURES.labels(stage=s)._value.get() == value


@pytest.mark.parametrize('stage', ['finish', 'seal'])
async def test_real_write_failure_still_advances_ladder(records, monkeypatch, stage):
    barrier = barrier_module.PusherRecordBarrier('uid-at')
    await barrier.begin_recording('record')
    barrier.keep_close_pending = True
    monkeypatch.setattr(barrier_module, 'time', SimpleNamespace(monotonic=lambda: 100.0))
    monkeypatch.setattr(barrier_module.random, 'uniform', lambda low, high: high)
    name = 'set_record_upload_pending' if stage == 'finish' else 'seal_record_audio'
    monkeypatch.setattr(barrier_module.record_audio_db, name, Mock(side_effect=OSError('synthetic write failure')))
    counter = barrier_module.RECORD_BARRIER_FAILURES.labels(stage=stage)
    before = counter._value.get()
    assert not await barrier.finish_recording('record')
    assert barrier.close_failures == {'record': 1}
    assert barrier.close_retry_at['record'] == 102.0
    assert counter._value.get() == before + 1
    if stage == 'finish':
        assert records.rows[PATH]['record_upload_sessions']
        assert barrier.pending_clears
    else:
        assert not records.rows[PATH]['record_upload_sessions']
        assert not records.rows[PATH]['record_audio_closed']


async def test_four_held_calls_fifth_close_retries_when_one_slot_frees(records, monkeypatch):
    barrier = barrier_module.PusherRecordBarrier('uid-at')
    await barrier.begin_recording('record')
    token = barrier.upload_sessions['record']
    barrier.keep_close_pending = True
    held = HeldExecutor()
    pool = barrier_module.record_barrier_executor
    monkeypatch.setattr(barrier_module, 'record_barrier_executor', held)
    active = threading.BoundedSemaphore(4)
    monkeypatch.setattr(barrier_module, '_close_retry_slots', active)
    monkeypatch.setattr(barrier_module, '_close_outstanding_slots', threading.BoundedSemaphore(12))
    holders = [asyncio.create_task(barrier._close_metadata('other', lambda: True)) for _ in range(4)]
    try:
        await asyncio.sleep(0)  # Each holder submits synchronously before its first await.
        assert len(held.pending) == 4
        assert not await barrier.finish_recording('record')
        assert len(held.pending) == 4  # Fifth call was never submitted.
        assert set(records.rows[PATH]['record_upload_sessions']) == {token}
        assert barrier.pending_clears == {('record', token)}
        assert barrier.upload_sessions['record'] == token
        # Free exactly one of the four slots; the other calls stay held.
        future, fn, args, kwargs = held.pending.pop(0)
        future.set_result(fn(*args, **kwargs))
        await asyncio.wait_for(holders[0], 5)
        monkeypatch.setattr(barrier_module, 'record_barrier_executor', pool)
        retry_at = barrier.close_retry_at['record']
        monkeypatch.setattr(barrier_module, 'time', SimpleNamespace(monotonic=lambda: retry_at))
        assert await barrier.finish_recording('record')
        assert all(not task.done() for task in holders[1:])
        assert not records.rows[PATH]['record_upload_sessions']
        assert records.rows[PATH]['record_audio_closed']
        assert not barrier.pending_clears and not barrier.upload_sessions
        assert not barrier.close_failures and not barrier.close_retry_at
    finally:
        held.release()
        await asyncio.wait_for(asyncio.gather(*holders), 5)


def test_close_refusal_metric_has_only_closed_reason_labels():
    samples = [sample for family in barrier_module.RECORD_CLOSE_REFUSALS.collect() for sample in family.samples]
    assert {tuple(sample.labels.items()) for sample in samples} == {
        (('reason', 'admission'),),
        (('reason', 'outstanding'),),
    }
