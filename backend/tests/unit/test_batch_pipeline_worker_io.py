"""Worker-flight artifact IO overlap: bounded prefetch and bounded encrypted writes.

Fakes model per-item GCS fetch+decrypt+decode latency and per-item encrypted
result write latency as sleeps; GPU stages are sleeps on the calling thread.
Run this file directly to print realistic-latency wall times per flight.
"""

import random
import sys
import threading
import time

import pytest

from config.batch_pipeline import worker_io_concurrency
from diarizer import batch_pipeline
from diarizer.batch_pipeline import PipelineWorker
from utils.batch_pipeline.contracts import Priority, WorkItem, WorkResult
from utils.batch_pipeline.errors import FatalGpuError


class Samples:
    def __init__(self, seconds):
        self.size = int(seconds * 16000)

    def __len__(self):
        return self.size

    def __getitem__(self, key):
        return Samples((key.stop - key.start) / 16000)


def flight(count=7, seconds=41):
    # Production flights average ~7 items / ~287 audio seconds.
    return [
        WorkItem(f's{i}', f'owner-{i}', 100 + i, f'encrypted://s{i}', seconds, Priority.FRESH) for i in range(count)
    ]


class Model:
    """Latency-model fakes; records thread ownership and overlap."""

    def __init__(self, *, scale=1.0, seed=7, vad=0.05, asr=0.12, diarize=0.15):
        rng = random.Random(seed)
        self.fetch_s = [rng.uniform(0.150, 0.400) * scale for _ in range(64)]
        self.persist_s = [rng.uniform(0.100, 0.300) * scale for _ in range(64)]
        self.vad_s, self.asr_s, self.diarize_s = vad * scale, asr * scale, diarize * scale
        self.main = threading.get_ident()
        self.guard = threading.Lock()
        self.gpu_threads = set()
        self.gpu_active = 0
        self.gpu_overlap = False
        self.fetch_active = self.fetch_peak = 0
        self.persist_active = self.persist_peak = 0
        self.decoded_unconsumed = set()
        self.decoded_peak = 0
        self.saved = {}

    def _gpu(self, seconds):
        with self.guard:
            self.gpu_threads.add(threading.get_ident())
            self.gpu_active += 1
            self.gpu_overlap |= self.gpu_active > 1
        time.sleep(seconds)
        with self.guard:
            self.gpu_active -= 1

    def decode(self, item):
        index = int(item.segment_id[1:])
        with self.guard:
            self.fetch_active += 1
            self.fetch_peak = max(self.fetch_peak, self.fetch_active)
        time.sleep(self.fetch_s[index])
        with self.guard:
            self.fetch_active -= 1
            self.decoded_unconsumed.add(item.segment_id)
            self.decoded_peak = max(self.decoded_peak, len(self.decoded_unconsumed))
        return Samples(item.duration_seconds)

    def vad(self, samples):
        # The worker calls VAD right after consuming the decoded item.
        with self.guard:
            self.decoded_unconsumed.clear()
        self._gpu(self.vad_s)
        return [(0, len(samples) / 16000)]

    def transcribe_batch(self, samples):
        self._gpu(self.asr_s)
        return [[{'word': 'hello', 'timestamp': [0.1, 0.2]}] for _ in samples]

    def diarize(self, samples):
        self._gpu(self.diarize_s)
        return {'turns': []}

    def persist(self, item, payload):
        index = int(item.segment_id[1:])
        with self.guard:
            self.persist_active += 1
            self.persist_peak = max(self.persist_peak, self.persist_active)
        time.sleep(self.persist_s[index])
        with self.guard:
            self.persist_active -= 1
        self.saved[item.segment_id] = payload
        return 'encrypted-result://' + item.segment_id

    def worker(self, io_concurrency, **overrides):
        settings = dict(
            language_of=lambda item: 'en',  # Synthetic English fixture.
            decode=self.decode,
            vad=self.vad,
            words_providers={'parakeet': self},
            diarizers={'pyannote': self.diarize},
            persist=self.persist,
            io_concurrency=io_concurrency,
            gpu_lock=threading.Lock(),
        )
        settings.update(overrides)
        return PipelineWorker(**settings)


def timed_flight(io_concurrency, *, scale=1.0, items=None):
    model = Model(scale=scale)
    worker = model.worker(io_concurrency)
    started = time.perf_counter()
    results = worker.process_batch(items or flight())
    return time.perf_counter() - started, results, model


def test_overlap_cuts_flight_wall_time_and_keeps_results_identical():
    serial, serial_results, serial_model = timed_flight(1, scale=0.25)
    overlapped, results, model = timed_flight(3, scale=0.25)
    assert results == serial_results
    assert [r.segment_id for r in results] == [f's{i}' for i in range(7)]
    assert all(isinstance(r, WorkResult) and r.outcome == 'success' for r in results)
    assert model.saved == serial_model.saved
    # Serial model floor: sum(fetch)+sum(persist)+GPU. Overlap hides most IO.
    io_hidden = serial - overlapped
    assert io_hidden > 0.35 * (sum(model.fetch_s[:7]) + sum(model.persist_s[:7]))
    assert overlapped < 0.7 * serial


def test_gpu_stages_stay_on_calling_thread_and_never_overlap():
    _, _, model = timed_flight(4, scale=0.05)
    assert model.gpu_threads == {model.main}
    assert not model.gpu_overlap
    assert model.fetch_peak <= 4 and model.persist_peak <= 4


def test_serial_setting_uses_no_io_threads():
    worker = Model().worker(1)
    assert worker._io is None
    _, _, model = timed_flight(1, scale=0.02)
    assert model.fetch_peak == 1 and model.persist_peak == 1


@pytest.mark.parametrize('limit', [2, 3])
def test_prefetch_is_bounded_by_count(limit):
    _, _, model = timed_flight(limit, scale=0.05, items=flight(count=12, seconds=10))
    assert model.fetch_peak <= limit
    assert model.decoded_peak <= limit


def test_prefetch_respects_ahead_audio_budget(monkeypatch):
    # Two 1000s items exceed the 1800s ahead budget: only the next one prefetches.
    monkeypatch.setattr(batch_pipeline, 'PREFETCH_AHEAD_SECONDS', 1800)
    model = Model(scale=0.05)
    worker = model.worker(4)
    worker.config = type(worker.config)(max_unit_seconds=7200)
    worker.process_batch(flight(count=6, seconds=1000))
    assert model.fetch_peak <= 2
    assert model.decoded_peak <= 2


def test_prefetch_never_crosses_the_two_hour_decode_group():
    model = Model(scale=0.05)
    worker = model.worker(4)
    seen = []
    original = worker._process

    def process(group, **kwargs):
        seen.append((list(i.segment_id for i in group), set(model.decoded_unconsumed)))
        return original(group, **kwargs)

    worker._process = process
    worker.process_batch(flight(count=4, seconds=3000))
    # Each group starts with nothing decoded from a later group.
    assert [ids for ids, _ in seen] == [['s0', 's1'], ['s2', 's3']]
    assert all(not pending for _, pending in seen)


def test_fetch_and_persist_failures_stay_per_item_and_in_order():
    model = Model(scale=0.02)
    failures = []

    def decode(item):
        if item.segment_id == 's1':
            raise ValueError('synthetic-private-fetch-error')
        return model.decode(item)

    def persist(item, payload):
        if item.segment_id == 's4':
            raise ValueError('synthetic-private-persist-error')
        return model.persist(item, payload)

    worker = model.worker(3, decode=decode, persist=persist, on_failure=lambda i, e: failures.append(i.segment_id))
    results = worker.process_batch(flight())
    assert [r.segment_id for r in results] == ['s0', 's2', 's3', 's5', 's6']
    assert sorted(failures) == ['s1', 's4']
    assert worker.counts['failed'] == 2


def test_fatal_gpu_error_drains_io_before_raising():
    model = Model(scale=0.1)

    def vad(samples):
        if len(model.saved) == 0 and model.vad_calls == 1:
            raise RuntimeError('CUDA error: an illegal memory access was encountered')
        model.vad_calls += 1
        return model.vad(samples)

    model.vad_calls = 0
    worker = model.worker(4, vad=vad)
    with pytest.raises(FatalGpuError):
        worker.process_batch(flight())
    # No fetch or write may still be running after the flight is abandoned.
    assert model.fetch_active == 0 and model.persist_active == 0
    with pytest.raises(FatalGpuError):
        worker.process_batch(flight(count=1))


def test_fatal_diarization_error_waits_for_inflight_writes():
    model = Model(scale=0.1)
    calls = []

    def diarize(samples):
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError('CUDA error: unspecified launch failure')
        return model.diarize(samples)

    worker = model.worker(3, diarizers={'pyannote': diarize})
    with pytest.raises(FatalGpuError):
        worker.process_batch(flight())
    assert model.persist_active == 0


@pytest.mark.parametrize(
    'raw,expected',
    [(None, 3), ('1', 1), ('4', 4), ('8', 8), ('0', 3), ('9', 3), ('x', 3), ('-2', 3)],
)
def test_io_concurrency_knob(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv('BATCH_PIPELINE_WORKER_IO_CONCURRENCY', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_WORKER_IO_CONCURRENCY', raw)
    assert worker_io_concurrency() == expected
    assert Model().worker(None).io_concurrency == expected


def _report():
    print('7 items x 41s; fetch 150-400ms, persist 100-300ms, VAD 50ms/item, ASR 120ms/batch, diarize 150ms/item')
    for count in (7, 8):
        for concurrency in (1, 2, 3, 4):
            runs = [timed_flight(concurrency, items=flight(count=count))[0] for _ in range(3)]
            print(f'items={count} io_concurrency={concurrency} wall_s={sorted(runs)[1]:.3f}')


if __name__ == '__main__':
    sys.exit(_report())
