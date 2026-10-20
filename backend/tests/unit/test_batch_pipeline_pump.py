"""Worker lifetime, lease loss and restart recovery without GPU/cloud IO."""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

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
@pytest.mark.parametrize('dispatch', [False, True])
async def test_worker_dispatch_denial_defers_without_quarantining_or_losing_audio(monkeypatch, dispatch):
    from utils.batch_pipeline.contracts import HeldWork

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(dispatch).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
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


class ExclusiveWorker(Worker):
    """Records chain overlap; the GPU chain must never run twice at once."""

    def __init__(self, delay=0):
        super().__init__(delay)
        self.active = 0
        self.peak = 0
        self.started = threading.Event()
        self.guard = threading.Lock()

    def process_batch(self, items):
        with self.guard:
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.calls:
                self.started.set()  # a second chain began
        try:
            return super().process_batch(items)
        finally:
            with self.guard:
                self.active -= 1


def pipelined(worker, *, slots=1, flights=2):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('first'), time.time())
    queue.enqueue(item('second', capture=2), time.time())
    pump = Pump(queue, worker, capacity=lambda: PoolCapacity(time.time(), slots), flights=flights)
    return store, queue, pump


@pytest.mark.parametrize('flights', [0, 5])
def test_pipeline_depth_is_bounded(flights):
    with pytest.raises(ValueError):
        Pump(Scheduler(MemoryStore()), Worker(), flights=flights)


@pytest.mark.asyncio
async def test_pipelined_publication_overlaps_next_exclusive_chain_and_keeps_capture_order(monkeypatch):
    monkeypatch.setattr(module, 'HEARTBEAT_SECONDS', 0.01)
    worker = ExclusiveWorker()
    store, queue, pump = pipelined(worker)
    original = queue.complete
    overlapped = []

    def complete(result, token, now):
        if result.segment_id == 'first':
            # Serial pumps would deadlock here: the next chain cannot start
            # until this publication returns.
            overlapped.append(worker.started.wait(5))
        return original(result, token, now)

    monkeypatch.setattr(queue, 'complete', complete)
    stop = asyncio.Event()
    task = asyncio.create_task(pump.run(stop))
    for _ in range(500):
        if store.rows['jobs', 'second']['state'] == 'committed':
            break
        await asyncio.sleep(0.01)
    stop.set()
    await task
    assert overlapped == [True]
    assert worker.peak == 1 and worker.calls == 2
    assert store.rows['jobs', 'first']['state'] == 'committed'
    assert store.rows['results', 'second']['previous_segment_id'] == 'first'


def blocked_chain(worker):
    """Hold the first chain until released; record which segment entered it."""
    release, entered = threading.Event(), []
    process = worker.process_batch

    def chain(items):
        entered.extend(v.segment_id for v in items)
        return release.wait(5) and process(items)

    worker.process_batch = chain
    return release, entered


def assert_refunded_waiter(store, entered):
    # Lanes race for the GPU lock; either claimed segment may run first.
    assert len(entered) == 1
    computed = entered[0]
    waiting = 'second' if computed == 'first' else 'first'
    # The computed result is published, but never merged past its predecessor.
    assert store.rows['jobs', computed]['state'] == ('committed' if computed == 'first' else 'result_ready')
    job = store.rows['jobs', waiting]
    assert job['state'] == 'retry' and job['attempt'] == 0 and job['merge_pending'] and job['token'] == ''
    return waiting


@pytest.mark.asyncio
async def test_waiting_lane_refunds_claimed_leases_on_stop_without_attempt_charge(monkeypatch):
    monkeypatch.setattr(module, 'HEARTBEAT_SECONDS', 0.01)
    worker = ExclusiveWorker()
    release, entered = blocked_chain(worker)
    store, queue, pump = pipelined(worker)
    stop = asyncio.Event()
    task = asyncio.create_task(pump.run(stop))
    for _ in range(500):
        if entered and all(store.rows['jobs', v]['state'] == 'leased' for v in ('first', 'second')):
            break
        await asyncio.sleep(0.01)
    stop.set()
    release.set()
    await task
    assert worker.calls == 1
    assert_refunded_waiter(store, entered)


@pytest.mark.asyncio
async def test_pipelined_fatal_gpu_refunds_every_lane_and_raises(monkeypatch):
    class Poisoned:
        calls = 0

        def process_batch(self, items):
            Poisoned.calls += 1
            time.sleep(0.02)
            raise FatalGpuError('synthetic CUDA OOM')

    store, queue, pump = pipelined(Poisoned())
    monkeypatch.setattr(queue, 'fail', lambda *args: pytest.fail('fatal GPU must not fail a segment'))
    with pytest.raises(FatalGpuError):
        await pump.run(asyncio.Event())
    for segment in ('first', 'second'):
        job = store.rows['jobs', segment]
        assert job['state'] == 'retry' and job['attempt'] == 0
        assert job['merge_pending'] and ('results', segment) not in store.rows


@pytest.mark.asyncio
async def test_pipelined_maintenance_runs_off_lane_and_recovers_persisted_results():
    store, queue, pump = pipelined(ExclusiveWorker())
    lease = queue.pull(time.time())[0]
    queue.complete(WorkResult(lease.item.segment_id, 'gs://synthetic/result'), lease.token, time.time())
    lanes = []
    original = pump.run_once

    async def run_once(**kwargs):
        lanes.append(kwargs.get('maintain'))
        return await original(**kwargs)

    pump.run_once = run_once
    stop = asyncio.Event()
    task = asyncio.create_task(pump.run(stop))
    for _ in range(500):
        if all(store.rows['jobs', v]['state'] == 'committed' for v in ('first', 'second')):
            break
        await asyncio.sleep(0.01)
    stop.set()
    await task
    assert store.rows['results', 'second']['previous_segment_id'] == 'first'
    assert lanes and not any(lanes)


@pytest.mark.asyncio
@pytest.mark.parametrize('late', ['before_refund', 'after_refund'])
async def test_stopped_waiting_lane_refunds_lease_lost_to_a_timed_out_heartbeat(monkeypatch, late):
    """A timed-out renewal marks the lease lost while the token may still be ours.

    SIGTERM must still hand it back (retry, attempt unchanged); a late renewal
    landing before or after the refund must leave the job recoverable.
    """
    monkeypatch.setattr(module, 'HEARTBEAT_SECONDS', 0.01)
    monkeypatch.setattr(module, 'HEARTBEAT_TIMEOUT_SECONDS', 0.05)
    worker = ExclusiveWorker()
    release_chain, entered = blocked_chain(worker)
    store, queue, pump = pipelined(worker)
    original = queue.heartbeat
    late_started, release_late, late_result = threading.Event(), threading.Event(), []

    def heartbeat(segment, token, now):
        # Only the lane waiting behind the chain loses its renewals.
        if not entered or segment in entered:
            return original(segment, token, now)
        if not late_started.is_set():
            late_started.set()
            release_late.wait(5)  # outlives the renewal timeout, then lands
            late_result.append(original(segment, token, time.time()))
            return late_result[-1]
        raise TimeoutError('synthetic renewal timeout')

    monkeypatch.setattr(queue, 'heartbeat', heartbeat)
    stop = asyncio.Event()
    task = asyncio.create_task(pump.run(stop))

    async def until(condition):
        for _ in range(500):
            if condition():
                return
            await asyncio.sleep(0.01)
        pytest.fail('condition not reached')

    await until(late_started.is_set)
    await asyncio.sleep(0.1)  # the 0.05 s renewal wait has timed out: the waiter's lease is lost
    if late == 'before_refund':
        release_late.set()
        await until(lambda: bool(late_result))
        assert late_result == [True]  # the late beat extended a lease we still own
    stop.set()
    release_chain.set()
    await task
    waiting = assert_refunded_waiter(store, entered)
    if late == 'after_refund':
        release_late.set()
        await until(lambda: bool(late_result))
        assert late_result == [False]  # fenced by the cleared token
        assert store.rows['jobs', waiting]['state'] == 'retry'
    assert worker.calls == 1
    assert queue.recover(store.rows['jobs', waiting]['available_at'] + 1) >= 1
    assert store.rows['jobs', waiting]['state'] == 'ready'


@pytest.mark.asyncio
async def test_only_the_lease_holder_runs_recovery_and_global_drain():
    from utils.batch_pipeline.leader import PUMP_RECOVERY, LeaderLease

    store, queue, _ = setup()
    lease = queue.pull(time.time())[0]
    queue.complete(WorkResult('first', 'gs://synthetic/result'), lease.token, time.time())
    pumps = [
        Pump(
            queue,
            Worker(),
            capacity=lambda: PoolCapacity(time.time(), 8),
            leader=LeaderLease(store, PUMP_RECOVERY, ttl_seconds=30),
        )
        for _ in range(2)
    ]
    assert pumps[0].leader.acquire()  # Replica 0 already leads this tick.
    recovered = []
    original = queue.recover
    queue.recover = lambda now: recovered.append(now) or original(now)
    assert await pumps[1].run_once() == 0
    assert not recovered and store.rows['jobs', 'first']['state'] == 'result_ready'
    assert await pumps[0].run_once() == 0
    assert len(recovered) == 1 and store.rows['jobs', 'first']['state'] == 'committed'


@pytest.mark.asyncio
async def test_lease_store_failure_keeps_per_replica_recovery():
    from unittest.mock import Mock

    from utils.batch_pipeline.leader import PUMP_RECOVERY, LeaderLease

    broken = Mock()
    broken.run.side_effect = RuntimeError('lease store down')
    store, queue, _ = setup()
    lease = queue.pull(time.time())[0]
    queue.complete(WorkResult('first', 'gs://synthetic/result'), lease.token, time.time())
    pump = Pump(queue, Worker(), leader=LeaderLease(broken, PUMP_RECOVERY, ttl_seconds=30))
    assert await pump.run_once() == 0
    assert store.rows['jobs', 'first']['state'] == 'committed'


@pytest.mark.asyncio
async def test_external_sampler_owns_metrics_when_inline_sampling_is_off():
    from unittest.mock import Mock

    metrics = Mock()
    _, _, inline = setup(metrics=metrics)
    await inline.run_once()
    assert metrics.refresh.call_count == 1
    metrics.reset_mock()
    store, _, external = setup(metrics=metrics, inline_metrics=False)
    await external.run_once()
    metrics.refresh.assert_not_called()
    await external.sample_metrics()
    assert metrics.refresh.call_args.args[0] is store


@pytest.mark.asyncio
async def test_foreign_results_release_every_lease_instead_of_stranding_it():
    class Foreign:
        def process_batch(self, items):
            return [WorkResult('someone-else', 'gs://synthetic/x')]

    store, queue, pump = setup(Foreign())
    queue.enqueue(item('second', capture=2), time.time())
    with pytest.raises(ValueError):
        await pump.run_once()
    for segment in ('first', 'second'):
        job = store.rows['jobs', segment]
        assert job['state'] == 'retry' and job['token'] == '' and job['attempt'] == 1
        assert job['available_at'] - time.time() < 10  # Not LEASE_SECONDS.
        assert ('results', segment) not in store.rows


@pytest.mark.asyncio
async def test_admission_refund_error_releases_the_whole_flight(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_API_URL', raising=False)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(replace(item('gated'), requires_compute_admission=True), time.time())
    queue.enqueue(item('plain', owner='light'), time.time())
    worker = Worker()
    pump = Pump(queue, worker, capacity=lambda: PoolCapacity(time.time(), 8))

    def defer(*args):
        raise RuntimeError('ambiguous defer')

    monkeypatch.setattr(queue, 'defer', defer)
    with pytest.raises(RuntimeError):
        await pump.run_once()
    assert worker.calls == 0
    for segment in ('gated', 'plain'):
        assert store.rows['jobs', segment]['state'] == 'retry'


@pytest.mark.asyncio
async def test_partial_claim_failure_computes_and_commits_the_claimed_leases(monkeypatch):
    store, queue, pump = setup()
    queue.enqueue(item('other', owner='light'), time.time())
    original, calls = queue._pull_one, [0]

    def pull_one(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 2:
            raise RuntimeError('synthetic Aborted')
        return original(*args, **kwargs)

    monkeypatch.setattr(queue, '_pull_one', pull_one)
    assert await pump.run_once() == 1
    states = sorted(store.rows['jobs', v]['state'] for v in ('first', 'other'))
    # The claimed lease ran at once; the unclaimed job never left the queue.
    assert states == ['committed', 'ready']
