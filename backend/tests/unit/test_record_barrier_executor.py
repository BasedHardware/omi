"""Record custody retries cannot occupy integration consumers' DB workers."""

import asyncio
import json
import os
import struct
import threading
from concurrent.futures import Executor, Future
from unittest.mock import Mock

from utils import executors
from utils import pusher_record_barrier as barrier_module
from tests.unit.test_pusher_audio_timeline import env, HeldOpenWebSocket, _audio, _conversation, _run, RATE
from tests.unit.test_record_audio_seal import records
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
