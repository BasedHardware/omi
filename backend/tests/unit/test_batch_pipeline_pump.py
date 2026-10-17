"""Worker lifetime, lease loss and restart recovery without GPU/cloud IO."""

import asyncio
from dataclasses import replace
import threading
import time

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline import pump as module
from utils.batch_pipeline.contracts import PoolCapacity, WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.errors import FatalGpuError
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler


class Worker:
    def __init__(self, delay=0):
        self.delay = delay
        self.finished = False
        self.calls = 0

    def process_batch(self, items):
        self.calls += 1
        time.sleep(self.delay)
        self.finished = True
        return [WorkResult(v.segment_id, f'gs://synthetic/{v.segment_id}') for v in reversed(items)]


def setup(worker=None, **kwargs):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('first'), time.time())
    pump = Pump(queue, worker or Worker(), capacity=lambda: PoolCapacity(time.time(), 8), **kwargs)
    return store, queue, pump


@pytest.mark.asyncio
async def test_heartbeat_renews_while_blocking_gpu_chain_runs(monkeypatch):
    monkeypatch.setattr(module, 'HEARTBEAT_SECONDS', 0.01)
    release = threading.Event()
    worker = Worker()
    original_process = worker.process_batch

    def process(items):
        assert release.wait(5), 'heartbeat never renewed the in-flight chain twice'
        return original_process(items)

    worker.process_batch = process
    store, queue, pump = setup(worker)
    calls = []
    original = queue.heartbeat

    def renew(*args):
        calls.append(time.monotonic())
        if len(calls) >= 2:
            release.set()
        return original(*args)

    monkeypatch.setattr(queue, 'heartbeat', renew)
    assert await pump.run_once() == 1
    assert len(calls) >= 2
    assert store.rows['jobs', 'first']['state'] == 'committed'
    assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]


@pytest.mark.asyncio
async def test_lost_lease_discards_late_result(monkeypatch):
    monkeypatch.setattr(module, 'HEARTBEAT_SECONDS', 0.01)
    release = threading.Event()
    worker = Worker()
    process = worker.process_batch
    worker.process_batch = lambda items: (release.wait(5) and process(items))
    store, queue, pump = setup(worker)

    def lost(*args):
        store.rows['jobs', 'first']['token'] = 'replacement-token'
        release.set()
        return False

    monkeypatch.setattr(queue, 'heartbeat', lost)
    await pump.run_once()
    assert ('results', 'first') not in store.rows
    assert store.rows['jobs', 'first']['state'] == 'leased'
    assert pump.worker.finished


@pytest.mark.asyncio
async def test_sigterm_stops_new_pulls_but_drains_and_commits_current_work(monkeypatch):
    monkeypatch.setattr(module, 'HEARTBEAT_SECONDS', 0.01)
    worker = Worker(0.04)
    store, _, pump = setup(worker)
    stop = asyncio.Event()
    task = asyncio.create_task(pump.run(stop))
    await asyncio.sleep(0.02)
    stop.set()
    await task
    assert worker.finished and worker.calls == 1
    assert store.rows['jobs', 'first']['state'] == 'committed'


@pytest.mark.asyncio
async def test_cancel_waits_for_nonpreemptible_compute_before_heartbeat_stops(monkeypatch):
    monkeypatch.setattr(module, 'HEARTBEAT_SECONDS', 0.01)
    worker = Worker(0.04)
    store, _, pump = setup(worker)
    task = asyncio.create_task(pump.run_once())
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert worker.finished
    assert ('results', 'first') not in store.rows


@pytest.mark.asyncio
async def test_rollback_drains_and_out_of_order_completion_commits_capture_order(monkeypatch):
    store, queue, pump = setup()
    queue.enqueue(item('second', capture=2), time.time())
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    committed = []
    pump.on_committed = lambda entry: committed.append(entry['segment_id'])
    await pump.run_once()
    assert committed == ['first', 'second']
    assert store.rows['results', 'second']['previous_segment_id'] == 'first'


@pytest.mark.asyncio
async def test_restart_recovers_result_persisted_before_merge():
    store, queue, pump = setup()
    lease = queue.pull(time.time())[0]
    queue.complete(WorkResult('first', 'gs://synthetic/result'), lease.token, time.time())
    assert await pump.run_once() == 0
    assert store.rows['jobs', 'first']['state'] == 'committed'
    assert ('results', 'first') in store.rows


def test_production_heartbeat_interval_is_at_most_thirty_seconds():
    assert 0 < module.HEARTBEAT_SECONDS <= 30


@pytest.mark.asyncio
async def test_one_owner_commit_failure_does_not_suppress_other_batch_results(monkeypatch):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    store, queue, pump = setup()
    queue.enqueue(item('other', owner='light'), time.time())
    original = queue.complete

    def complete(result, token, now):
        if result.segment_id == 'first':
            raise BatchPrivacyBlocked('synthetic revoked owner')
        return original(result, token, now)

    monkeypatch.setattr(queue, 'complete', complete)
    assert await pump.run_once() == 2
    assert ('results', 'first') not in store.rows
    assert store.rows['jobs', 'other']['state'] == 'committed'


@pytest.mark.asyncio
async def test_required_compute_admission_missing_callback_never_runs_gpu(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_API_URL', raising=False)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(replace(item('gated'), requires_compute_admission=True), time.time())
    worker = Worker()
    pump = Pump(queue, worker, capacity=lambda: PoolCapacity(time.time(), 8))
    assert await pump.run_once() == 0
    assert worker.calls == 0
    assert store.rows['jobs', 'gated']['state'] == 'retry'
    assert store.rows['jobs', 'gated']['attempt'] == 0


@pytest.mark.asyncio
async def test_single_missed_heartbeat_retries_and_does_not_requeue_long_chain(monkeypatch):
    from types import SimpleNamespace

    actual_monotonic = time.monotonic
    clock = [0.0]
    monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: clock[0], monotonic=actual_monotonic))
    monkeypatch.setattr(module, 'HEARTBEAT_SECONDS', 0.002)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('long', duration=30), 0)
    release = threading.Event()
    worker = Worker()
    process = worker.process_batch
    worker.process_batch = lambda items: (release.wait(5) and process(items))
    heartbeat = queue.heartbeat
    calls = [0]

    def renew(segment, token, now):
        calls[0] += 1
        clock[0] += 20
        if calls[0] == 1:
            raise TimeoutError('one missed heartbeat')
        valid = heartbeat(segment, token, now)
        assert queue.recover(clock[0]) == 0
        if clock[0] >= 140:
            release.set()
        return valid

    monkeypatch.setattr(queue, 'heartbeat', renew)
    pump = Pump(queue, worker, capacity=lambda: PoolCapacity(clock[0], 1))
    assert await pump.run_once() == 1
    assert clock[0] >= 140  # The chain crossed the original 120s lease horizon.
    assert store.rows['jobs', 'long']['state'] == 'committed'
    assert store.rows['jobs', 'long']['attempt'] == 1


@pytest.mark.asyncio
async def test_fatal_gpu_restarts_without_fail_or_attempt_charge_then_fresh_worker_completes(monkeypatch):
    class Poisoned:
        def process_batch(self, items):
            raise FatalGpuError('synthetic CUDA OOM')

    store, queue, pump = setup(Poisoned())
    queue.enqueue(item('second', capture=2), time.time())
    monkeypatch.setattr(queue, 'fail', lambda *args: pytest.fail('fatal GPU must not fail a segment'))
    for _ in range(7):
        with pytest.raises(FatalGpuError):
            await pump.run(asyncio.Event())
        for segment in ('first', 'second'):
            job = store.rows['jobs', segment]
            assert job['state'] == 'retry' and job['attempt'] == 0
            assert job['merge_pending'] and ('results', segment) not in store.rows
            job['available_at'] = time.time() - 1
        pump._last_recovery = float('-inf')
    pump.worker = Worker()
    assert await pump.run_once() == 2
    assert store.rows['jobs', 'first']['state'] == 'committed'
    assert store.rows['jobs', 'second']['state'] == 'committed'
    assert store.rows['results', 'second']['previous_segment_id'] == 'first'


@pytest.mark.asyncio
async def test_worker_dispatch_denial_defers_without_quarantining_or_losing_audio(monkeypatch):
    from utils.batch_pipeline.contracts import HeldWork

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    calls = []

    def authorize(leases):
        calls.append([v.item.segment_id for v in leases])
        return {'allowed': calls[-1] if len(calls) == 1 else []}

    class RecheckingWorker:
        def process_batch(self, items, *, authorize_dispatch):
            assert not authorize_dispatch({v.segment_id for v in items})
            return [HeldWork(v.segment_id) for v in items]

    store, _, pump = setup(RecheckingWorker(), authorize_compute=authorize)
    assert await pump.run_once() == 1
    job = store.rows['jobs', 'first']
    assert job['state'] == 'retry' and job['attempt'] == 0
    assert ('results', 'first') not in store.rows
    assert calls == [['first'], ['first']]


@pytest.mark.asyncio
async def test_empty_asr_handoff_quarantines_first_attempt_and_stale_token_cannot_complete():
    from utils.batch_pipeline.contracts import RecoveryWork

    worker = Worker()
    worker.process_batch = lambda items: [RecoveryWork(v.segment_id) for v in items]
    store, queue, pump = setup(worker)
    await pump.run_once()
    job = store.rows['jobs', 'first']
    assert job['state'] == 'quarantined' and job['attempt'] == 1
    assert job['recovery_state'] == 'held' and not job['merge_pending']
    assert ('results', 'first') not in store.rows
    assert not queue.complete(WorkResult('first', 'gs://synthetic/stale'), '', time.time())
