"""Worker IO custody boundaries, with deterministic barriers and no GPU/cloud."""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading
import time

import numpy as np
from prometheus_client import CollectorRegistry, Counter
import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from diarizer import batch_pipeline as worker_module
from diarizer.batch_pipeline_models import StagedAudio
from diarizer.batch_pipeline_runtime import SynchronizedWorker
from tests.unit.test_batch_pipeline_worker import setup_worker, item
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_artifacts import setup as artifacts_setup, item as artifact_item
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline import pump as pump_module, worker_metrics
from utils.batch_pipeline.audio import audio_unit, with_context
from utils.batch_pipeline.contracts import FailedWork, WorkResult
from utils.batch_pipeline.errors import FatalGpuError
from utils.batch_pipeline.compute_client import InvalidReceipt
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.worker_io import DecodeBudget, PendingResults


@pytest.fixture(autouse=True)
def ordinary_chain(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setattr(worker_module, 'inspect_worker_vad', lambda work, samples: (work.duration_seconds, []))


def test_pending_persist_releases_model_lock_but_never_returns_early():
    started, release, settled = threading.Event(), threading.Event(), threading.Event()
    lock = threading.Lock()
    caller = threading.get_ident()
    model_threads = []

    def persist(work, payload):
        started.set()
        assert release.wait(3)
        settled.set()
        return 'encrypted://result'

    def vad(samples):
        assert lock.locked()
        model_threads.append(threading.get_ident())
        return [(0, 2)]

    worker, _, _, _, _, _ = setup_worker(persist=persist, gpu_lock=lock, vad=vad, io_concurrency=5)
    pending = worker.process_batch_deferred([item()])
    assert isinstance(pending, PendingResults) and started.wait(1)
    assert not lock.locked() and not settled.is_set()
    with ThreadPoolExecutor(1) as executor:
        finishing = executor.submit(pending.settle)
        try:
            assert not finishing.done()
        finally:
            release.set()
        assert finishing.result(2) == [WorkResult('a', 'encrypted://result')]
    assert model_threads == [caller] and settled.is_set()


def test_persist_failure_is_per_unit_after_unlock(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    lock = threading.Lock()

    def persist(work, payload):
        if work.segment_id == 'bad':
            raise RuntimeError('synthetic persist failure')
        return 'encrypted://good'

    worker, _, _, _, _, failures = setup_worker(persist=persist, gpu_lock=lock, io_concurrency=5)
    pending = worker.process_batch_deferred([item('bad'), item('good')])
    assert not lock.locked()
    results = pending.settle()
    assert [r.segment_id for r in results if isinstance(r, WorkResult)] == ['good']
    assert [r.segment_id for r in results if isinstance(r, FailedWork)] == ['bad']
    assert failures == [('bad', 'RuntimeError')]


def test_fatal_cuda_synchronize_drains_deferred_io_before_raising():
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def persist(work, payload):
        started.set()
        assert release.wait(3)
        finished.set()
        return 'encrypted://result'

    def synchronize():
        raise RuntimeError('CUDA error: illegal memory access')

    worker, _, _, _, _, _ = setup_worker(persist=persist, io_concurrency=5)
    wrapped = SynchronizedWorker(worker, synchronize)
    with ThreadPoolExecutor(1) as executor:
        running = executor.submit(wrapped.process_batch_deferred, [item()])
        try:
            assert started.wait(1) and not running.done()
        finally:
            release.set()
        with pytest.raises(FatalGpuError):
            running.result(2)
    assert finished.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize('lost', [False, True])
async def test_other_lane_computes_during_persist_and_renewal_covers_settlement(monkeypatch, lost):
    monkeypatch.setattr(pump_module, 'HEARTBEAT_SECONDS', 0.01)
    loop = asyncio.get_running_loop()
    persisting, renewed = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('first'), time.time())

    def persist(work, payload):
        if work.segment_id == 'first':
            loop.call_soon_threadsafe(persisting.set)
            assert release.wait(3)
        return 'encrypted://' + work.segment_id

    worker, _, _, _, _, _ = setup_worker(persist=persist, io_concurrency=5)
    pump = Pump(queue, SynchronizedWorker(worker, lambda: None), flights=2)
    heartbeat = queue.heartbeat
    calls = []

    def renew(segment, token, now):
        calls.append(segment)
        if segment == 'first' and len(calls) >= 2:
            loop.call_soon_threadsafe(renewed.set)
        return False if lost and segment == 'first' else heartbeat(segment, token, now)

    monkeypatch.setattr(queue, 'heartbeat', renew)
    running = asyncio.create_task(pump.run_once(maintain=False))
    try:
        await asyncio.wait_for(persisting.wait(), 2)
        await asyncio.wait_for(renewed.wait(), 2)
        await asyncio.wait_for(pump._gpu.acquire(), 1)
        pump._gpu.release()
        assert store.rows['jobs', 'first']['state'] == 'leased'
        queue.enqueue(item('second'), time.time())
        assert await asyncio.wait_for(pump.run_once(maintain=False), 2) == 1
        assert store.rows['jobs', 'second']['state'] == 'committed'
        assert ('results', 'first') not in store.rows
    finally:
        release.set()
        await asyncio.wait_for(running, 2)
    assert store.rows['jobs', 'first']['state'] == ('leased' if lost else 'committed')
    assert (('results', 'first') in store.rows) is not lost
    assert worker._decode_budget.seconds == 0


@pytest.mark.asyncio
async def test_sigterm_drains_current_persist_with_renewal(monkeypatch):
    monkeypatch.setattr(pump_module, 'HEARTBEAT_SECONDS', 0.01)
    loop = asyncio.get_running_loop()
    persisting = asyncio.Event()
    release = threading.Event()

    def persist(work, payload):
        loop.call_soon_threadsafe(persisting.set)
        assert release.wait(3)
        return 'encrypted://result'

    worker, _, _, _, _, _ = setup_worker(persist=persist, io_concurrency=5)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    pump = Pump(queue, SynchronizedWorker(worker, lambda: None), flights=2, poll_seconds=0.01)
    stop = asyncio.Event()
    running = asyncio.create_task(pump.run(stop))
    started = time.monotonic()
    try:
        await asyncio.wait_for(persisting.wait(), 2)
        stop.set()
        assert not running.done() and ('results', 'a') not in store.rows
    finally:
        release.set()
        await asyncio.wait_for(running, 3)
    assert time.monotonic() - started < 1500
    assert store.rows['jobs', 'a']['state'] == 'committed'
    assert worker._decode_budget.seconds == 0


def test_preparation_audio_bound_is_shared_and_released_only_after_io_drains():
    release = threading.Event()
    budget = DecodeBudget(1800)
    with ThreadPoolExecutor(2) as executor:
        first = budget.submit(executor, lambda work: release.wait(2), item('a', 1000))
        second = budget.submit(executor, lambda work: release.wait(2), item('b', 800))
        try:
            assert budget.seconds == 1800
            assert budget.submit(executor, lambda work: None, item('c', 1)) is None
            assert budget.submit(executor, lambda work: None, item('a', 1)) is None
            with pytest.raises(ValueError, match='another attempt'):
                first.take(replace(first.item))
        finally:
            release.set()
            first.close()
            second.close()
    assert budget.seconds == 0


def test_queued_preparation_cancels_without_waiting_for_executor_capacity():
    release, occupied = threading.Event(), threading.Event()
    budget = DecodeBudget()
    with ThreadPoolExecutor(1) as executor:

        def blocker():
            occupied.set()
            assert release.wait(3)

        blocker_future = executor.submit(blocker)
        assert occupied.wait(1)
        handle = budget.submit(executor, lambda work: None, item())
        try:
            started = time.monotonic()
            handle.cancel()
            handle.close()
            assert time.monotonic() - started < 0.2
            assert budget.seconds == 0 and handle.future is None
        finally:
            release.set()
            blocker_future.result(1)


@pytest.mark.asyncio
async def test_repeated_cancellation_drains_persist_before_renewal_ends(monkeypatch):
    monkeypatch.setattr(pump_module, 'HEARTBEAT_SECONDS', 0.01)
    loop = asyncio.get_running_loop()
    persisting, renewed = asyncio.Event(), asyncio.Event()
    release, settled = threading.Event(), threading.Event()
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())

    def persist(work, payload):
        loop.call_soon_threadsafe(persisting.set)
        assert release.wait(3)
        settled.set()
        return 'encrypted://result'

    worker, _, _, _, _, _ = setup_worker(persist=persist, io_concurrency=5)
    pump = Pump(queue, SynchronizedWorker(worker, lambda: None))
    heartbeat = queue.heartbeat

    def renew(*args):
        loop.call_soon_threadsafe(renewed.set)
        return heartbeat(*args)

    monkeypatch.setattr(queue, 'heartbeat', renew)
    running = asyncio.create_task(pump.run_once(maintain=False))
    try:
        await asyncio.wait_for(persisting.wait(), 2)
        running.cancel()
        await asyncio.sleep(0)
        running.cancel()
        await asyncio.wait_for(renewed.wait(), 2)
        assert not running.done() and not settled.is_set()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await running
    assert settled.is_set() and worker._decode_budget.seconds == 0
    assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]


@pytest.mark.parametrize('cause', ['stop', 'lost', 'recovered', 'privacy'])
@pytest.mark.asyncio
async def test_waiting_preparation_cancelled_on_stop_lease_loss_or_privacy(monkeypatch, cause):
    monkeypatch.setattr(pump_module, 'HEARTBEAT_SECONDS', 0.01)
    loop = asyncio.get_running_loop()
    decoded, discarded, renewed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = []
    stop = asyncio.Event()
    worker, _, _, _, _, _ = setup_worker(io_concurrency=2)

    def decode(work):
        loop.call_soon_threadsafe(decoded.set)
        if cause == 'privacy':
            raise BatchPrivacyBlocked('synthetic')
        return np.zeros(32000, dtype=np.float32)

    worker.decode = decode
    prepare = worker.prepare_first

    def observed_prepare(items):
        handle = prepare(items)
        cancel = handle.cancel

        def observed_cancel():
            cancel()
            loop.call_soon_threadsafe(discarded.set)

        handle.cancel = observed_cancel
        return handle

    worker.prepare_first = observed_prepare
    worker.vad = lambda samples: calls.append('model') or []
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    pump = Pump(queue, worker, flights=2)
    if cause == 'lost':
        monkeypatch.setattr(queue, 'heartbeat', lambda *args: False)
    if cause == 'recovered':
        heartbeat = queue.heartbeat

        def recover_renewal(*args):
            if not discarded.is_set():
                return False
            valid = heartbeat(*args)
            loop.call_soon_threadsafe(renewed.set)
            return valid

        monkeypatch.setattr(queue, 'heartbeat', recover_renewal)
    await pump._gpu.acquire()
    running = asyncio.create_task(pump.run_once(stop_event=stop, maintain=False))
    try:
        await asyncio.wait_for(decoded.wait(), 2)
        if cause == 'stop':
            stop.set()
        if cause == 'lost':
            await asyncio.wait_for(discarded.wait(), 2)
        if cause == 'recovered':
            await asyncio.wait_for(renewed.wait(), 2)
        if cause == 'stop':
            await asyncio.wait_for(discarded.wait(), 2)
    finally:
        pump._gpu.release()
        await asyncio.wait_for(running, 3)
    assert not calls and ('results', 'a') not in store.rows
    assert worker._decode_budget.seconds == 0
    if cause == 'recovered':
        assert store.rows['jobs', 'a']['state'] == 'retry'
        assert store.rows['jobs', 'a']['attempt'] == 0


def test_released_attempt_cannot_overwrite_another_attempts_staged_context():
    first, second = item(duration=1), item(duration=1)
    blobs = [
        with_context(
            audio_unit(100, b'\x00\x00' * 16000).wav,
            {
                'stt_language': lang,
                'stt_language_evidence': 'declared',
                'stt_language_confidence': 1.0,
            },
        )
        for lang in ('en', 'vi')
    ]
    source = StagedAudio(lambda work: blobs[0] if work is first else blobs[1])
    source.decode(first)
    source.decode(second)
    assert source.language(first) == 'en'
    assert source.language(second) == 'vi'


@pytest.mark.parametrize('shadow', ['silent', 'speech', 'unavailable'])
def test_shadow_cannot_change_words_speakers_clocks_or_model_calls(monkeypatch, shadow):
    baseline, _, saved, _, diarized, _ = setup_worker(io_concurrency=1)
    expected = baseline.process_batch([item()])
    worker, _, actual, _, actual_diarized, _ = setup_worker(io_concurrency=5)
    if shadow == 'unavailable':

        def inspect(*args):
            raise RuntimeError('synthetic shadow failure')

    else:
        inspect = lambda work, samples: (work.duration_seconds, [] if shadow == 'silent' else [{'start': 0, 'end': 1}])
    monkeypatch.setattr(worker_module, 'inspect_worker_vad', inspect)
    prepared = worker.prepare_first([work := item()])
    try:
        assert worker.process_batch_deferred([work], prepared=prepared).settle() == expected
    finally:
        prepared.close()
    assert actual == saved and actual_diarized == diarized


def test_privacy_delete_during_persist_never_publishes(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    artifacts, objects, policy = artifacts_setup()
    work = artifact_item()
    worker, _, _, _, _, _ = setup_worker(
        decode=lambda work: np.zeros(16000, dtype=np.float32),
        vad=lambda samples: [],
        persist=artifacts.persist_result,
        io_concurrency=5,
    )
    objects.after_upload = lambda: setattr(policy, 'context', ProtectionContext('enhanced', 1))
    results = worker.process_batch_deferred([work]).settle()
    assert not [r for r in results if isinstance(r, WorkResult)]
    assert [r.segment_id for r in results if isinstance(r, FailedWork)] == [work.segment_id]
    assert not objects.objects


def test_closed_metric_events_and_completed_seconds_include_silence_once():
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    queue = Scheduler(MemoryStore(), metrics=metrics)
    queue.enqueue(item(), 0)
    lease = queue.pull(0)[0]
    queue.fail('a', lease.token, 1)
    queue.recover(100)
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'retry'}) == 1
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'requeued'}) == 1
    lease = queue.pull(100)[0]
    result = WorkResult('a', 'encrypted://result', 'silence')
    assert queue.complete(result, lease.token, 101)
    assert queue.complete(result, lease.token, 102)
    assert registry.get_sample_value('omi_batch_pipeline_completed_audio_seconds_total', {'outcome': 'silence'}) == 2
    assert registry.get_sample_value('omi_batch_pipeline_events_total', {'event': 'completed'}) == 1
    for event in [
        'leased',
        'completed',
        'retry',
        'requeued',
        'lease_expired',
        'dead',
        'committed',
        'quarantined',
        'recovery_held',
        'admission_policy_deferred',
        'admission_unevaluated_deferred',
    ]:
        metrics.record(event)
    with pytest.raises(ValueError):
        metrics.record('synthetic-dynamic-event')
    for collector in worker_metrics.COLLECTORS:
        for metric in collector.collect():
            for sample in metric.samples:
                assert set(sample.labels) <= {'outcome', 'le'}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'error,outcome',
    [
        (TimeoutError(), 'timeout'),
        (ConnectionError(), 'transport'),
        (InvalidReceipt(), 'invalid_receipt'),
        (None, 'received'),
    ],
)
async def test_admission_fault_counters_keep_every_unpermitted_unit_deferred(monkeypatch, error, outcome):
    registry = CollectorRegistry()
    monkeypatch.setattr(
        worker_metrics,
        'ADMISSION',
        Counter('omi_batch_pipeline_admission_receipts_total', '', ['outcome'], registry=registry),
    )
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(replace(item(), requires_compute_admission=True), time.time())
    worker, _, saved, _, _, _ = setup_worker(io_concurrency=1)

    def authorize(leases):
        if error is not None:
            raise error
        return {'allowed': [], 'retry_after': {}}

    assert await Pump(queue, worker, authorize_compute=authorize).run_once(maintain=False) == 0
    assert not saved and worker.counts['items'] == 0
    assert store.rows['jobs', 'a']['state'] == 'retry' and store.rows['jobs', 'a']['attempt'] == 0
    assert registry.get_sample_value('omi_batch_pipeline_admission_receipts_total', {'outcome': outcome}) == 1


def test_broken_shadow_clock_and_counter_cannot_change_result(monkeypatch):
    worker, _, saved, _, _, failures = setup_worker(io_concurrency=5)

    def broken(*args):
        raise RuntimeError('synthetic unavailable observation')

    monkeypatch.setattr(worker_module.time, 'thread_time', broken)
    monkeypatch.setattr(worker_metrics, 'strict_vad', broken)
    assert worker.process_batch([item()])[0].outcome == 'success'
    assert saved['a']['words'][0]['word'] == 'hello' and not failures
