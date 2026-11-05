"""Eviction attests stoppage only after real executor work; never certifies a tail."""

import asyncio
import logging
import threading
import gc
import weakref
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import record_audio
from tests.unit.test_record_audio_seal import records, PATH
from tests.unit.test_pusher_audio_timeline import env
from utils import executors, pusher_record_barrier as barriers, pusher_record_finish as finish
from utils.batch_pipeline.record_producer_proof import producer_tokens_dead
from config import pusher_record
import routers.pusher as pusher


@pytest.mark.parametrize(
    'value,expected', [(None, 32), ('bad', 32), ('0', 8), ('8', 8), ('64', 64), ('128', 128), ('999', 128)]
)
def test_cap_default_and_clamp(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('PUSHER_MAX_CLOSED_RECORD_DRAINS', raising=False)
    else:
        monkeypatch.setenv('PUSHER_MAX_CLOSED_RECORD_DRAINS', value)
    assert finish.closed_record_drain_cap() == expected


def test_cap_logged_once(caplog):
    finish.log_closed_record_drain_cap.cache_clear()
    with caplog.at_level(logging.INFO, logger=finish.__name__):
        finish.log_closed_record_drain_cap()
        finish.log_closed_record_drain_cap()
    assert sum('event=record_closed_finish_cap' in r.message for r in caplog.records) == 1


async def test_abandon_transaction_is_exact_idempotent_and_cannot_be_recleared(records):
    old, new = barriers.PusherRecordBarrier('uid-at'), barriers.PusherRecordBarrier('uid-at')
    await old.begin_recording('record')
    old_token = old.upload_sessions['record']
    await new.begin_recording('record')
    new_token = new.upload_sessions['record']
    original = dict(records.rows[PATH]['record_upload_sessions'][old_token])
    assert record_audio.abandon_record_upload_session('uid-at', 'record', old_token)
    marked = dict(records.rows[PATH]['record_upload_sessions'][old_token])
    assert marked.items() >= original.items()
    assert marked['abandoned_at'] >= marked['process_started_at']
    writes = sum(len(tx.updates) for tx in records.transactions)
    assert record_audio.abandon_record_upload_session('uid-at', 'record', old_token)
    assert sum(len(tx.updates) for tx in records.transactions) == writes
    # A reconnect with an old recovery snapshot cannot certify an abandoned tail.
    assert not record_audio.set_record_upload_pending('uid-at', 'record', old_token, False)
    assert not await new.finish_recording('record')
    assert records.rows[PATH]['record_upload_sessions'] == {old_token: marked}
    assert new_token != old_token
    assert not records.rows[PATH]['record_audio_closed']
    assert not record_audio.abandon_record_upload_session('uid-at', 'record', 'absent')
    records.rows[PATH]['deleted'] = True
    assert not record_audio.abandon_record_upload_session('uid-at', 'record', old_token)
    records.rows.clear()
    assert not record_audio.abandon_record_upload_session('uid-at', 'record', old_token)
    assert not records.rows


@pytest.mark.parametrize('kind', ['storage', 'metadata', 'begin'])
async def test_cancelled_worker_waits_for_real_future_before_abandon(records, monkeypatch, kind):
    barrier = barriers.PusherRecordBarrier('uid-at')
    barrier.keep_close_pending = True
    if kind != 'begin':
        await barrier.begin_recording('record')
    tracker = executors.ExecutorFutureTracker(executors.storage_executor, executors.record_barrier_executor)
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    calls = []
    owners = []
    start = finish.start_background_task

    def track(coro, **kwargs):
        owner = start(coro, **kwargs)
        owners.append(owner)
        return owner

    def late_write():
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10)
        calls.append('late_write')

    register = record_audio.set_record_upload_pending
    abandon = record_audio.abandon_record_upload_session

    def slow_register(*args, **kwargs):
        late_write()
        return register(*args, **kwargs)

    def attest(*args, **kwargs):
        assert calls == ['late_write']
        calls.append('abandon')
        return abandon(*args, **kwargs)

    monkeypatch.setattr(record_audio, 'abandon_record_upload_session', attest)
    if kind == 'begin':
        monkeypatch.setattr(record_audio, 'set_record_upload_pending', slow_register)

    async def worker():
        if kind == 'begin':
            await barrier.begin_recording('record')
        elif kind == 'metadata':
            # This direct-submit path already shields, and can outlive its deadline.
            monkeypatch.setattr(barriers, 'CLOSE_METADATA_DEADLINE_SECONDS', 0.5)
            try:
                await barrier._close_metadata('record', late_write)
            except TimeoutError:
                await asyncio.Event().wait()
        else:
            await executors.run_blocking(executors.storage_executor, late_write)

    monkeypatch.setattr(finish, 'start_background_task', track)
    monkeypatch.setattr(finish, 'MAX_CLOSED_RECORD_DRAINS', 0)
    with tracker.scope():
        task = asyncio.create_task(worker())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert not finish.retain_closed_record_drain(
            task, on_capacity=lambda: finish.abandon_evicted_record_drain(task, barrier, tracker)
        )
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)
        assert tracker.pending and calls == []
        assert not owners[0].done()
        assert not barriers._process_record_tokens().tokens
        release.set()
        await asyncio.wait_for(owners[0], 5)
        assert calls == ['late_write', 'abandon']
        tokens = records.rows[PATH]['record_upload_sessions']
        assert producer_tokens_dead(tokens, None)
        assert not records.rows[PATH]['record_audio_closed']
        assert not tracker.pending
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, *owners, return_exceptions=True)


async def test_abandon_retries_admission_and_write_failure_forgets_recovery_hint(records, monkeypatch):
    barrier = barriers.PusherRecordBarrier('uid-at')
    await barrier.begin_recording('record')
    token = barrier.upload_sessions['record']
    registry = barriers._process_record_tokens()
    registry.ready('uid-at', 'record', token)
    later = barriers.PusherRecordBarrier('uid-at')
    await later.begin_recording('record')
    assert registry.recoverable_before('uid-at', 'record', later.upload_sessions['record']) == [token]
    close = barrier._close_metadata
    attempts = 0
    delays = []

    async def refuse_then_succeed(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise barriers._CloseAdmissionRefused('synthetic')
        if attempts == 2:
            raise OSError('synthetic')
        return await close(*args, **kwargs)

    async def backoff(delay):
        delays.append(delay)

    monkeypatch.setattr(barrier, '_close_metadata', refuse_then_succeed)
    monkeypatch.setattr(barriers.asyncio, 'sleep', backoff)
    await barrier.abandon_recordings()
    assert attempts == 3 and len(delays) == 2
    assert all(0 < delay <= 60 for delay in delays)
    assert registry.recoverable_before('uid-at', 'record', later.upload_sessions['record']) == []
    assert not producer_tokens_dead(records.rows[PATH]['record_upload_sessions'], None)  # Reconnect is live.
    assert not barrier.upload_sessions and not barrier.pending_clears


async def test_kill_switch_off_keeps_cancel_and_strand(monkeypatch):
    monkeypatch.setenv('PUSHER_ABANDON_EVICTED_TOKENS', 'off')
    monkeypatch.setattr(finish, 'MAX_CLOSED_RECORD_DRAINS', 0)
    callback = Mock()
    task = asyncio.create_task(asyncio.Event().wait())
    try:
        assert not finish.retain_closed_record_drain(task, on_capacity=callback)
        callback.assert_not_called()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_inherited_pending_clear_never_abandons_another_sockets_running_writer(records, monkeypatch):
    earlier, later = barriers.PusherRecordBarrier('uid-at'), barriers.PusherRecordBarrier('uid-at')
    await earlier.begin_recording('record')
    old = earlier.upload_sessions['record']
    earlier.hold_recording('record', tail_committed=True)
    await later.begin_recording('record')
    new = later.upload_sessions['record']
    close = later._close_metadata

    async def refused(*args, **kwargs):
        raise barriers._CloseAdmissionRefused('synthetic')

    monkeypatch.setattr(later, '_close_metadata', refused)
    assert not await later.finish_recording('record')
    assert ('record', old) in later.pending_clears
    monkeypatch.setattr(later, '_close_metadata', close)

    tracker = executors.ExecutorFutureTracker(executors.storage_executor)
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def old_projection():
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10)
        assert 'abandoned_at' not in records.rows[PATH]['record_upload_sessions'][old]

    owners = []
    start = finish.start_background_task

    def track(coro, **kwargs):
        owner = start(coro, **kwargs)
        owners.append(owner)
        return owner

    with tracker.scope():
        old_task = asyncio.create_task(executors.run_blocking(executors.storage_executor, old_projection))
    later_task = asyncio.create_task(asyncio.Event().wait())
    monkeypatch.setattr(finish, 'start_background_task', track)
    try:
        await asyncio.wait_for(entered.wait(), 5)
        finish.abandon_evicted_record_drain(later_task, later, executors.ExecutorFutureTracker())
        later_task.cancel()
        await asyncio.gather(later_task, return_exceptions=True)
        await asyncio.wait_for(owners[0], 5)
        sessions = records.rows[PATH]['record_upload_sessions']
        assert 'abandoned_at' in sessions[new]
        assert 'abandoned_at' not in sessions[old] and not old_task.done()
        assert not producer_tokens_dead(sessions, None)
        # Once its own writer settles, the earlier producer may attest stoppage.
        release.set()
        await asyncio.wait_for(old_task, 5)
        await tracker.wait()
        await earlier.abandon_recordings()
        assert producer_tokens_dead(records.rows[PATH]['record_upload_sessions'], None)
        assert not records.rows[PATH]['record_audio_closed']
    finally:
        release.set()
        later_task.cancel()
        await asyncio.gather(old_task, later_task, *owners, return_exceptions=True)


@pytest.mark.parametrize('value,abandon,workers', [(None, 4, 4), ('bad', 4, 4), ('0', 0, 1), ('999', 16, 8)])
def test_overflow_and_storage_bounds_are_conservative_and_clamped(monkeypatch, value, abandon, workers):
    for name in ('PUSHER_MAX_ABANDON_RECORD_DRAINS', 'PUSHER_RECORD_STORAGE_WORKERS'):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert pusher_record.abandon_record_drain_cap() == abandon
    assert pusher_record.record_storage_workers() == workers


class TrackedPcm(bytearray):
    """Weak-referenceable PCM whose slices keep the same observable type."""

    references = []

    def __init__(self, value):
        super().__init__(value)
        self.references.append(weakref.ref(self))

    def __getitem__(self, key):
        value = super().__getitem__(key)
        return type(self)(value) if isinstance(key, slice) else value


def projection_ref():
    return SimpleNamespace(
        samples=160, offset_samples=0, start=100, sample_rate=16000, frames=(), receipt=SimpleNamespace(samples=160)
    )


async def test_stalled_storage_bounds_overflow_coordinators_and_actual_pcm_work(records, monkeypatch, caplog):
    """More closures than both caps: waiters hold receipts, not queued PCM."""
    workers, cap, count = 3, 1, 8
    pool = executors.MonitoredThreadPoolExecutor(
        name='test_record_stall', max_workers=workers, max_queue_size=0, log_saturation=False
    )
    monkeypatch.setattr(finish, 'MAX_CLOSED_RECORD_DRAINS', 1)
    monkeypatch.setattr(finish, 'MAX_ABANDON_RECORD_DRAINS', cap)
    monkeypatch.setattr(TrackedPcm, 'references', [])
    entered, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    lock = threading.Lock()
    materialized = 0
    owners, tasks, trackers, barriers_ = [], [], [], []
    start = finish.start_background_task

    def track(coro, **kwargs):
        task = start(coro, **kwargs)
        owners.append(task)
        return task

    def hydrate(*args):
        nonlocal materialized
        with lock:
            materialized += 1
        return TrackedPcm(b'\x01\x00' * 160)

    def stalled_upload(*args, **kwargs):
        with lock:
            if materialized == workers:
                loop.call_soon_threadsafe(entered.set)
        assert release.wait(15)
        return []

    monkeypatch.setattr(pusher, 'read_pcm', hydrate)
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', stalled_upload)
    monkeypatch.setattr(finish, 'start_background_task', track)
    projection = SimpleNamespace(refresh=lambda *a, **kw: True)
    try:
        for _ in range(count):
            barrier = barriers.PusherRecordBarrier('uid-at')
            await barrier.begin_recording('record')
            barriers_.append(barrier)
            tracker = executors.ExecutorFutureTracker(
                pool,
                executor_overrides={executors.storage_executor: pool},
                receipt_only_functions=(pusher._project_durable_refs,),
            )
            trackers.append(tracker)
            with tracker.scope():
                tasks.append(
                    asyncio.create_task(
                        executors.run_blocking(
                            executors.storage_executor,
                            pusher._project_durable_refs,
                            [projection_ref()],
                            'uid-at',
                            'record',
                            None,
                            16000,
                            True,
                            True,
                            projection,
                        )
                    )
                )
        await asyncio.wait_for(entered.wait(), 5)
        assert finish.retain_closed_record_drain(tasks[0])
        with caplog.at_level(logging.INFO, logger=finish.__name__):
            for task, barrier, tracker in zip(tasks[1:], barriers_[1:], trackers[1:]):
                # A durable-tail hold can mark this hint recoverable even while
                # a derivative upload is in flight. Refusal must fence it too.
                barrier.hold_recording('record', tail_committed=True)
                assert not finish.retain_closed_record_drain(
                    task, on_capacity=lambda t=task, b=barrier, f=tracker: finish.abandon_evicted_record_drain(t, b, f)
                )
                task.cancel()
            await asyncio.gather(*tasks[1:], return_exceptions=True)
            await asyncio.sleep(0)
        assert len(finish._abandon_record_drains) == cap
        assert len(owners) == 2  # One retained owner, one admitted abandon owner.
        assert sum('outcome=abandon_overflow' in r.message for r in caplog.records) == count - 2
        assert materialized == workers
        assert pool.active_count == workers and pool._work_queue.qsize() == 0
        assert sum(ref() is not None for ref in TrackedPcm.references) == workers
        assert all(not tracker.pending for tracker in trackers[workers:])
        sessions = records.rows[PATH]['record_upload_sessions']
        assert len(sessions) == count and all('abandoned_at' not in value for value in sessions.values())
        registry = barriers._process_record_tokens()
        assert all(b.upload_sessions['record'] not in registry.tokens[('uid-at', 'record')][1] for b in barriers_[2:])
        # Reconnect can finish its own token, but cannot certify an overflow
        # producer whose real storage future is still blocked.
        later = barriers.PusherRecordBarrier('uid-at')
        await later.begin_recording('record')
        assert not await later.finish_recording('record')
        assert len(records.rows[PATH]['record_upload_sessions']) == count
        assert not records.rows[PATH]['record_audio_closed']
        assert trackers[2].pending  # A refused overflow producer is still writing.
        # PCM-bearing custody calls fail immediately, never join a waiter/queue.
        with trackers[-1].scope(), pytest.raises(executors.ExecutorSaturatedError):
            await executors.run_blocking(executors.storage_executor, lambda pcm: None, bytearray(320))
        assert pool._work_queue.qsize() == 0 and materialized == workers
        release.set()
        await asyncio.wait_for(asyncio.gather(tasks[0], *owners), 5)
        await asyncio.wait_for(asyncio.gather(*(tracker.wait() for tracker in trackers)), 5)
        await asyncio.sleep(0)
        assert not finish._abandon_record_drains
        assert pool.active_count == 0
        sessions = records.rows[PATH]['record_upload_sessions']
        assert sum('abandoned_at' in value for value in sessions.values()) == cap
        assert all('abandoned_at' not in sessions[b.upload_sessions['record']] for b in barriers_[2:])
        gc.collect()
        assert not any(ref() is not None for ref in TrackedPcm.references)
        # Coordinator capacity can be reused after completion.
        extra = asyncio.create_task(asyncio.Event().wait())
        tasks.append(extra)
        assert finish.abandon_evicted_record_drain(extra, barriers_[2], executors.ExecutorFutureTracker())
        extra.cancel()
        await asyncio.gather(extra, return_exceptions=True)
        await asyncio.wait_for(owners[-1], 5)
    finally:
        release.set()
        for task in tasks + owners:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, *owners, return_exceptions=True)
        pool.shutdown(wait=True, cancel_futures=True)


def test_projection_error_traceback_does_not_retain_pcm(monkeypatch):
    monkeypatch.setattr(TrackedPcm, 'references', [])
    monkeypatch.setattr(pusher, 'read_pcm', lambda *a: TrackedPcm(b'\x01\x00' * 160))

    def failed(chunks, *args, **kwargs):
        raise OSError('synthetic storage refusal')

    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', failed)
    with pytest.raises(OSError) as error:
        pusher._project_durable_refs([projection_ref()], 'uid-at', 'record', None, 16000, True, True, None)
    assert error.value.__traceback__  # Keep the failure alive, as metadata retries would.
    gc.collect()
    assert not any(ref() is not None for ref in TrackedPcm.references)


def test_projection_admission_checks_full_source_and_batch_size_before_read(monkeypatch):
    read = Mock(side_effect=AssertionError('PCM hydrated before size admission'))
    monkeypatch.setattr(pusher, 'read_pcm', read)
    ref = projection_ref()
    ref.receipt.samples = pusher.BUFFERED_AUDIO_MAX_BYTES // 2 + 1
    with pytest.raises(ValueError, match='PCM batch budget'):
        pusher._project_durable_refs([ref], 'uid-at', 'record', None, 16000, True, True, None)
    read.assert_not_called()
