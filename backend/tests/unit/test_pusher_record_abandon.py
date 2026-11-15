"""Eviction attests stoppage only after real executor work; never certifies a tail."""

import asyncio
import logging
import threading
from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from database import record_audio
from tests.unit.test_record_audio_seal import records, PATH
from tests.unit.test_pusher_audio_timeline import env
from utils import executors, pusher_record_barrier as barriers, pusher_record_finish as finish
from utils.batch_pipeline.record_producer_proof import producer_tokens_dead
from config import pusher_record


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


@pytest.mark.parametrize('value,expected', [(None, 4), ('bad', 4), ('0', 0), ('999', 16)])
def test_abandon_bound_defaults_to_four_and_is_clamped(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('PUSHER_MAX_ABANDON_RECORD_DRAINS', raising=False)
    else:
        monkeypatch.setenv('PUSHER_MAX_ABANDON_RECORD_DRAINS', value)
    assert pusher_record.abandon_record_drain_cap() == expected


async def test_shared_storage_settles_before_four_coordinators_attest(records, monkeypatch, caplog):
    """Shared storage admits more than four writes; abandonment remains bounded."""
    cap, count = 4, 8
    monkeypatch.setattr(finish, 'MAX_CLOSED_RECORD_DRAINS', 1)
    monkeypatch.setattr(finish, 'MAX_ABANDON_RECORD_DRAINS', cap)
    monkeypatch.setenv('PUSHER_ABANDON_EVICTED_TOKENS', 'on')
    entered, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    lock = threading.Lock()
    running = 0
    owners, tasks, trackers, barriers_ = [], [], [], []
    start = finish.start_background_task

    def track(coro, **kwargs):
        owner = start(coro, **kwargs)
        owners.append(owner)
        return owner

    def stalled_write():
        nonlocal running
        assert threading.current_thread().name.startswith('storage')
        with lock:
            running += 1
            if running == count:
                loop.call_soon_threadsafe(entered.set)
        assert release.wait(15)

    monkeypatch.setattr(finish, 'start_background_task', track)
    try:
        for _ in range(count):
            barrier = barriers.PusherRecordBarrier('uid-at')
            await barrier.begin_recording('record')
            barriers_.append(barrier)
            tracker = executors.ExecutorFutureTracker(executors.storage_executor)
            trackers.append(tracker)
            with tracker.scope():
                tasks.append(asyncio.create_task(executors.run_blocking(executors.storage_executor, stalled_write)))
        await asyncio.wait_for(entered.wait(), 5)
        assert running == count  # No removed four-worker custody rejection gate.
        assert finish.retain_closed_record_drain(tasks[0])
        with caplog.at_level(logging.INFO, logger=finish.__name__):
            for task, barrier, tracker in zip(tasks[1:], barriers_[1:], trackers[1:]):
                barrier.hold_recording('record', tail_committed=True)
                assert not finish.retain_closed_record_drain(
                    task, on_capacity=lambda t=task, b=barrier, f=tracker: finish.abandon_evicted_record_drain(t, b, f)
                )
                task.cancel()
            await asyncio.gather(*tasks[1:], return_exceptions=True)
            await asyncio.sleep(0)
        assert len(finish._abandon_record_drains) == cap
        assert len(owners) == cap + 1  # Retained owner plus four abandon owners.
        assert sum('outcome=abandon_overflow' in r.message for r in caplog.records) == count - cap - 1
        assert all(tracker.pending for tracker in trackers)
        sessions = records.rows[PATH]['record_upload_sessions']
        assert len(sessions) == count and all('abandoned_at' not in value for value in sessions.values())
        registry = barriers._process_record_tokens()
        assert all(b.upload_sessions['record'] not in registry.tokens[('uid-at', 'record')][1] for b in barriers_[1:])
        later = barriers.PusherRecordBarrier('uid-at')
        await later.begin_recording('record')
        assert not await later.finish_recording('record')
        assert len(records.rows[PATH]['record_upload_sessions']) == count
        assert not records.rows[PATH]['record_audio_closed']
        release.set()
        await asyncio.wait_for(asyncio.gather(tasks[0], *owners), 5)
        await asyncio.wait_for(asyncio.gather(*(tracker.wait() for tracker in trackers)), 5)
        await asyncio.sleep(0)
        assert not finish._abandon_record_drains
        sessions = records.rows[PATH]['record_upload_sessions']
        assert sum('abandoned_at' in value for value in sessions.values()) == cap
        assert all('abandoned_at' not in sessions[b.upload_sessions['record']] for b in barriers_[cap + 1 :])
        extra = asyncio.create_task(asyncio.Event().wait())
        tasks.append(extra)
        assert finish.abandon_evicted_record_drain(extra, barriers_[-1], executors.ExecutorFutureTracker())
        extra.cancel()
        await asyncio.gather(extra, return_exceptions=True)
        await asyncio.wait_for(owners[-1], 5)
    finally:
        release.set()
        for task in tasks + owners:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, *owners, return_exceptions=True)
        await asyncio.wait_for(asyncio.gather(*(tracker.wait() for tracker in trackers)), 5)


async def test_frame_batch_renewal_is_throttled_and_late_append_bumps_revision(records, monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'shadow')
    epoch = [10000.0]
    monotonic = [10000.0]
    monkeypatch.setattr(record_audio.time, 'time', lambda: epoch[0])
    monkeypatch.setattr(barriers, 'producer_identity', lambda: {'pod': 'synthetic-pusher', 'process_started_at': 9000})

    monkeypatch.setattr(barriers, 'time', SimpleNamespace(time=lambda: epoch[0], monotonic=lambda: monotonic[0]))
    barrier = barriers.PusherRecordBarrier('uid-at')
    await barrier.begin_recording('record')
    token = barrier.upload_sessions['record']
    revision = records.rows[PATH]['record_upload_revision']
    before = len(records.transactions)
    await barrier.renew_recording('record')
    assert len(records.transactions) == before
    epoch[0] += 1800
    monotonic[0] += 1800
    await barrier.renew_recording('record')
    assert records.rows[PATH]['record_upload_sessions'][token]['last_signal_at'] == epoch[0]
    assert records.rows[PATH]['record_upload_revision'] == revision
    epoch[0] += 3601
    monotonic[0] += 3601
    await barrier.renew_recording('record')
    assert records.rows[PATH]['record_upload_revision'] == revision + 1
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'off')
    before = len(records.transactions)
    epoch[0] += 7200
    monotonic[0] += 7200
    await barrier.renew_recording('record')
    assert len(records.transactions) == before
    await barrier.finish_recording('record')


async def test_receive_and_projection_batches_share_one_committed_renewal(records, monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'shadow')
    monkeypatch.setattr(barriers, 'producer_identity', lambda: {'pod': 'synthetic-pusher', 'process_started_at': 100})
    barrier = barriers.PusherRecordBarrier('uid-at')
    await barrier.begin_recording('record')
    barrier.lease_renewed_at['record'] -= 1801
    entered, release = threading.Event(), threading.Event()
    renew = record_audio.renew_record_token_lease
    calls = []

    def slow(*args, **kwargs):
        calls.append(kwargs['source'])
        entered.set()
        assert release.wait(10)
        return renew(*args, **kwargs)

    monkeypatch.setattr(record_audio, 'renew_record_token_lease', slow)
    first = asyncio.create_task(barrier.renew_recording('record'))
    second = None
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        second = asyncio.create_task(barrier.renew_recording('record'))
        await asyncio.sleep(0)
        assert calls == ['frames']
        assert not first.done() and not second.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), 5)
        assert calls == ['frames']
        await barrier.finish_recording('record')
        assert not barrier.lease_locks
    finally:
        release.set()
        await asyncio.gather(first, *(task for task in (second,) if task is not None), return_exceptions=True)


async def test_delayed_begin_response_cannot_hide_a_lapsed_lease(records, monkeypatch):

    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    epoch, monotonic = [10000.0], [10000.0]
    monkeypatch.setattr(record_audio.time, 'time', lambda: epoch[0])
    monkeypatch.setattr(barriers, 'time', SimpleNamespace(time=lambda: epoch[0], monotonic=lambda: monotonic[0]))
    monkeypatch.setattr(barriers, 'producer_identity', lambda: {'pod': 'synthetic-pusher', 'process_started_at': 9000})
    register = record_audio.set_record_upload_pending

    def delayed_response(*args, **kwargs):
        result = register(*args, **kwargs)
        epoch[0] += 3601
        monotonic[0] += 3601
        return result

    monkeypatch.setattr(record_audio, 'set_record_upload_pending', delayed_response)
    barrier = barriers.PusherRecordBarrier('uid-at')
    await barrier.begin_recording('record')
    assert producer_tokens_dead(records.rows[PATH]['record_upload_sessions'], None, uid='uid-at')
    await barrier.renew_recording('record')
    assert records.rows[PATH]['record_upload_revision'] == 2
    assert not producer_tokens_dead(records.rows[PATH]['record_upload_sessions'], None, uid='uid-at')
    await barrier.finish_recording('record')


async def test_projection_after_partial_clear_restores_its_exact_producer(records, monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'shadow')
    monkeypatch.setattr(barriers, 'producer_identity', lambda: {'pod': 'synthetic-pusher', 'process_started_at': 100})
    barrier = barriers.PusherRecordBarrier('uid-at')
    await barrier.begin_recording('record')
    token = barrier.upload_sessions['record']
    revision = records.rows[PATH]['record_upload_revision']
    records.rows[PATH].update(record_upload_sessions={}, record_audio_partial={'upload_revision': revision})
    barrier.lease_renewed_at['record'] -= 3601
    await barrier.renew_recording('record')
    assert set(records.rows[PATH]['record_upload_sessions']) == {token}
    assert records.rows[PATH]['record_upload_revision'] == revision + 1
    await barrier.finish_recording('record')
    assert not records.rows[PATH].get('record_audio_closed')  # Partial is never a complete seal.


async def test_failed_renewal_retains_fence_across_rollback(records, monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    barrier = barriers.PusherRecordBarrier('uid-at')
    await barrier.begin_recording('record')
    barrier.lease_renewed_at['record'] -= 7200
    real = record_audio.renew_record_token_lease
    monkeypatch.setattr(record_audio, 'renew_record_token_lease', Mock(side_effect=OSError('unavailable')))
    try:
        assert not await barrier.renew_recording('record')
        monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'off')
        assert not await barrier.renew_recording('record')
        monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
        monkeypatch.setattr(record_audio, 'renew_record_token_lease', real)
        assert await barrier.renew_recording('record')
    finally:
        barrier._forget_lease('record')
