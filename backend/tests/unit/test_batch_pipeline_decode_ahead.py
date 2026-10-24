"""Bounded CPU read-ahead using production worker/pump code; no GPU or cloud."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading
import time

import pytest

from config.batch_pipeline import worker_decode_concurrency
from diarizer.batch_pipeline_prefetch import DecodeAhead
from diarizer.batch_pipeline_runtime import SynchronizedWorker
from tests.unit.test_batch_pipeline_worker_io import Model, flight
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline import pump as pump_module
from utils.batch_pipeline.contracts import PoolCapacity, WorkResult
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler


@pytest.mark.parametrize('concurrency', [1, 2, 3, 4])
def test_all_flights_share_count_and_audio_budget_and_do_not_decode_twice(concurrency):
    calls = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        ahead = DecodeAhead(executor, lambda i: calls.append(i.segment_id) or i.segment_id, concurrency)
        items = flight(count=8, seconds=600)
        first, second = ahead.prepare(items[:4]), ahead.prepare(items[4:])
        assert ahead.items == concurrency - 1
        assert ahead.seconds == 600 * (concurrency - 1)
        assert [first.decode(i) for i in items[:4]] == [i.segment_id for i in items[:4]]
        assert [second.decode(i) for i in items[4:]] == [i.segment_id for i in items[4:]]
        first.close()
        second.close()
        assert sorted(calls) == sorted(i.segment_id for i in items)
        assert ahead.items == 0 and ahead.seconds == 0


def test_oversized_item_uses_normal_decode_and_discard_drains_running_io():
    started, release = threading.Event(), threading.Event()

    def decode(i):
        started.set()
        assert release.wait(5)
        return i.segment_id

    with ThreadPoolExecutor(max_workers=1) as executor:
        ahead = DecodeAhead(executor, decode, 4)
        long = ahead.prepare(flight(count=1, seconds=3600))
        assert not long.pending and ahead.items == 0
        prepared = ahead.prepare(flight(count=4, seconds=1000))
        assert ahead.items == 1 and ahead.seconds == 1000
        assert started.wait(5)
        closed = threading.Event()
        thread = threading.Thread(target=lambda: (prepared.close(), closed.set()))
        thread.start()
        assert not closed.wait(0.02)
        release.set()
        thread.join(5)
        assert closed.is_set() and ahead.items == 0
        prepared.close()  # idempotent; no double release
        assert ahead.seconds == 0


def test_prepared_worker_parity_and_per_item_decode_failure():
    baseline = Model(scale=0.01)
    serial_worker = baseline.worker(3, decode_concurrency=1)
    expected = serial_worker.process_batch(flight())
    model = Model(scale=0.01)
    worker = model.worker(3, decode_concurrency=4)
    prepared = worker.prepare_batch(flight())
    try:
        assert worker.process_batch(flight(), prepared=prepared) == expected
        assert model.saved == baseline.saved
    finally:
        prepared.close()
    assert worker.decode_ahead.items == 0 and not model.gpu_overlap

    failed = Model(scale=0.01)

    def decode(i):
        if i.segment_id == 's0':
            raise ValueError('synthetic decode failure')
        return failed.decode(i)

    worker = failed.worker(3, decode_concurrency=4, decode=decode)
    prepared = worker.prepare_batch(flight())
    try:
        results = worker.process_batch(flight(), prepared=prepared)
        assert [r.segment_id for r in results] == [f's{i}' for i in range(1, 7)]
        assert worker.counts['failed'] == 1
    finally:
        prepared.close()
    assert worker.decode_ahead.items == 0


def test_serial_io_disables_preparation_and_invalid_pull_cannot_leak_reservations():
    worker = Model(scale=0).worker(1, decode_concurrency=4)
    assert worker.prepare_batch(flight()) is None
    with ThreadPoolExecutor(max_workers=1) as executor:
        ahead = DecodeAhead(executor, lambda i: i, 4)
        unit = flight(count=1)[0]
        with pytest.raises(ValueError, match='distinct'):
            ahead.prepare([unit, unit])
        assert ahead.items == 0 and ahead.seconds == 0


@pytest.mark.parametrize(
    'raw,expected', [(None, 1), ('1', 1), ('2', 2), ('3', 3), ('4', 4), ('0', 1), ('5', 1), ('x', 1)]
)
def test_decode_concurrency_defaults_and_kill_switch(monkeypatch, raw, expected):
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_DECODE_CONCURRENCY', raising=False)
    if raw is not None:
        monkeypatch.setenv('BATCH_PIPELINE_WORKER_DECODE_CONCURRENCY', raw)
    assert worker_decode_concurrency() == expected
    worker = Model(scale=0).worker(3)
    assert worker.decode_ahead.limit == expected - 1
    if expected == 1:
        assert worker.prepare_batch(flight()) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['success', 'stop', 'stolen', 'failure', 'cancel'])
async def test_decode_overlaps_gpu_with_live_heartbeats_and_fenced_publication(monkeypatch, mode):
    """Hold the first GPU call until the next flight has decoded outside its lock."""
    monkeypatch.setattr(pump_module, 'HEARTBEAT_SECONDS', 0.01)
    model = Model(scale=0.01)
    worker = model.worker(3, decode_concurrency=2)
    gpu_entered, next_decoded, release_gpu = threading.Event(), threading.Event(), threading.Event()
    computed, decoded = [], []
    stop = asyncio.Event()

    def decode(i):
        decoded.append(i.segment_id)
        if i.segment_id == 's1':
            next_decoded.set()
            if mode == 'failure':
                raise ValueError('synthetic failed next lease')
        return model.decode(i)

    worker.decode = decode
    worker.decode_ahead.decode = decode
    process = worker.process_batch

    def compute(items, **kwargs):
        computed.extend(i.segment_id for i in items)
        if items[0].segment_id == 's0':
            gpu_entered.set()
            assert release_gpu.wait(5)
        return process(items, **kwargs)

    worker.process_batch = compute
    store = MemoryStore()
    scheduler = Scheduler(store)
    for i in range(2):
        scheduler.enqueue(replace(item(f's{i}', capture=i + 1), duration_seconds=41), time.time())
    pump = Pump(
        scheduler,
        SynchronizedWorker(worker, synchronize=lambda: None),
        capacity=lambda: PoolCapacity(time.time(), 1),
        flights=2,
    )
    renewals = []
    heartbeat = scheduler.heartbeat

    def renew(segment, token, now):
        renewals.append(segment)
        if mode == 'stolen' and segment == 's1':
            store.rows['jobs', segment]['token'] = 'new-holder'
            return False
        return heartbeat(segment, token, now)

    monkeypatch.setattr(scheduler, 'heartbeat', renew)
    # Deterministically start the first flight before the next claims.
    first = asyncio.create_task(pump.run_once(maintain=False, stop_event=stop))
    try:
        for _ in range(500):
            if gpu_entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert gpu_entered.is_set()
        second = asyncio.create_task(pump.run_once(maintain=False, stop_event=stop))
        for _ in range(500):
            if next_decoded.is_set() and 's1' in renewals:
                break
            await asyncio.sleep(0.01)
        assert next_decoded.is_set() and 's1' in renewals
        assert not first.done() and computed == ['s0']
        if mode == 'stop':
            stop.set()
        if mode == 'cancel':
            second.cancel()
            with pytest.raises(asyncio.CancelledError):
                await second
        release_gpu.set()
        await first
        if mode != 'cancel':
            await second
        assert decoded.count('s0') == 1 and decoded.count('s1') == 1
        assert store.rows['jobs', 's0']['state'] == 'committed'
        if mode == 'success':
            assert store.rows['jobs', 's1']['state'] == 'committed'
            assert store.rows['results', 's1']['previous_segment_id'] == 's0'
            # A replay using the retired token cannot produce a second commit.
            assert not scheduler.complete(results_for('s1'), 'retired-token', time.time())
        else:
            assert ('results', 's1') not in store.rows
        if mode == 'stop':
            assert store.rows['jobs', 's1']['state'] == 'retry'
            assert store.rows['jobs', 's1']['attempt'] == 0
        assert worker.decode_ahead.items == 0 and worker.decode_ahead.seconds == 0
        assert not model.gpu_overlap
    finally:
        release_gpu.set()
        worker._io.shutdown(wait=True)


def results_for(segment):
    return WorkResult(segment, 'gs://synthetic/duplicate')


@pytest.mark.asyncio
async def test_released_segment_retry_cannot_consume_stale_attempt_context(monkeypatch):
    monkeypatch.setattr(pump_module, 'HEARTBEAT_SECONDS', 0.01)
    model = Model(scale=0.01)
    entered, release = threading.Event(), threading.Event()
    metadata, decoded = {}, []

    def decode(unit):
        samples = model.decode(unit)
        # Model the destructive per-segment metadata seam in StagedAudio.
        metadata[unit.segment_id] = 'en'
        decoded.append(unit.segment_id)
        return samples

    def vad(samples):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return model.vad(samples)

    worker = model.worker(
        3, decode_concurrency=2, decode=decode, vad=vad, language_of=lambda unit: metadata.pop(unit.segment_id, None)
    )
    store = MemoryStore()
    scheduler = Scheduler(store)
    scheduler.enqueue(replace(item('s0'), duration_seconds=41), time.time())
    pump = Pump(
        scheduler,
        SynchronizedWorker(worker, synchronize=lambda: None),
        capacity=lambda: PoolCapacity(time.time(), 1),
        flights=2,
    )
    first = asyncio.create_task(pump.run_once(maintain=False))
    second = None
    try:
        for _ in range(500):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert entered.is_set() and decoded == ['s0']
        old_token = store.rows['jobs', 's0']['token']
        assert scheduler.defer('s0', old_token, time.time(), 1)
        await asyncio.sleep(1.05)
        scheduler.recover(time.time())
        second = asyncio.create_task(pump.run_once(maintain=False))
        for _ in range(500):
            if pump._flight_segments.get('s0') == 2:
                break
            await asyncio.sleep(0.01)
        assert pump._flight_segments['s0'] == 2
        await asyncio.sleep(0.05)
        assert decoded == ['s0']  # Replacement must not overwrite the old cache.
        release.set()
        await asyncio.gather(first, second)
        assert decoded == ['s0', 's0'] and not worker.counts['failed']
        assert store.rows['jobs', 's0']['state'] == 'committed'
        assert len([key for key in store.rows if key[0] == 'results']) == 1
        assert not scheduler.complete(results_for('s0'), old_token, time.time())
        assert not pump._flight_segments and worker.decode_ahead.items == 0
    finally:
        release.set()
        await asyncio.gather(first, *([second] if second is not None else []), return_exceptions=True)
        worker._io.shutdown(wait=True)


@pytest.mark.asyncio
async def test_paired_latency_model_preserves_payloads_and_reports_capacity():
    """Illustrative IO-latency model, not an L4 capacity qualification."""
    baseline_saved = None
    baseline_wall = None
    for concurrency in (1, 2, 3, 4):
        model = Model(scale=0.1)
        worker = model.worker(3, decode_concurrency=concurrency)
        store = MemoryStore()
        scheduler = Scheduler(store)
        for unit in flight(count=16):
            scheduler.enqueue(unit, time.time())
        pump = Pump(
            scheduler,
            SynchronizedWorker(worker, synchronize=lambda: None),
            capacity=lambda: PoolCapacity(time.time(), 8),
            flights=2,
        )
        started = time.perf_counter()
        try:
            while sum(await asyncio.gather(pump.run_once(maintain=False), pump.run_once(maintain=False))):
                pass
        finally:
            worker._io.shutdown(wait=True)
        wall = time.perf_counter() - started
        assert len(model.saved) == 16
        assert all(store.rows['jobs', unit.segment_id]['state'] == 'committed' for unit in flight(count=16))
        assert not model.gpu_overlap and worker.decode_ahead.items == 0
        if baseline_saved is None:
            baseline_saved, baseline_wall = model.saved, wall
        assert model.saved == baseline_saved
        ratio = baseline_wall / wall
        print(
            f'X1_LATENCY_MODEL N={concurrency} wall_s={wall:.4f} ratio={ratio:.4f} historical_reference_per_min={21.5 * ratio:.2f}'
        )
