"""Shared worker harness for the persist re-strike lane suites.

Every lane suite drives the real PipelineWorker.process_batch with a scripted
persist stub, a recorded sleep, and the sibling env pins the worker suite
uses. The lane is each suite's subject; the parent base fails at import time
(the RED half), and this harness keeps the behavioral cells one line each.

Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results
"""

from contextlib import nullcontext
from dataclasses import replace

import pytest
from google.api_core.exceptions import InvalidArgument

from config.batch_pipeline import Priority
from diarizer import batch_pipeline as bp
from diarizer.batch_pipeline import PipelineWorker
from utils.batch_pipeline.contracts import WorkItem

try:
    from diarizer.batch_pipeline import (
        PERSIST_RESTRIKE_BASE_SECONDS,
        PERSIST_RESTRIKE_MAX_ATTEMPTS,
        PERSIST_RESTRIKE_MAX_SECONDS,
        persist_loss_is_contention,
        persist_loss_is_restrikeable,
        persist_restrike_delay,
        persist_restrike_storm_after,
    )
except ImportError:  # the lane is the subject; the parent fails at runtime (the RED half)
    pass

GATE = 'BATCH_PIPELINE_PERSIST_RESTRIKE_ENABLED'
WORKER_LOGGER = 'diarizer.batch_pipeline'


class Samples:
    def __init__(self, seconds):
        self.size = int(seconds * 16000)

    def __len__(self):
        return self.size

    def __getitem__(self, key):
        return Samples((key.stop - key.start) / 16000)


class Words:
    def __init__(self):
        self.calls = []

    def transcribe_batch(self, samples):
        self.calls.append([len(s) / 16000 for s in samples])
        return [[{'word': 'hello', 'timestamp': [0.1, 0.2]}] for _ in samples]


def item(key='a', duration=2):
    return WorkItem(key, 'owner-' + key, 100, 'encrypted://' + key, duration, Priority.FRESH)


class ScriptedPersist:
    """Persist stub playing one scripted step per call: 'OK', a URI string, or a raise.

    Once the script is exhausted every further call replays ``default`` — 'OK'
    for recovery scripts, or pass a fault instance for exhaustion scripts.
    """

    def __init__(self, script=(), default='OK'):
        self.script = list(script)
        self.default = default
        self.calls = []
        self.payloads = []

    def __call__(self, work, payload):
        self.calls.append(work.segment_id)
        self.payloads.append(payload)
        step = self.script.pop(0) if self.script else self.default
        if step == 'OK':
            return 'OK'
        if isinstance(step, BaseException):
            raise step
        return step


class SleepRecorder:
    def __init__(self):
        self.delays = []

    def __call__(self, delay, *args, **kwargs):
        self.delays.append(round(delay, 6))


class RecordingTimings:
    """Pass-through stage timings that record every span name in order."""

    def __init__(self):
        self.spans = []

    def call(self, name, fn, *args, **kwargs):
        self.spans.append(name)
        return fn(*args, **kwargs)

    def measure(self, name):
        return nullcontext()


def pin_full_gpu_stages(monkeypatch):
    """The stage pins the worker suite runs under; call from each file's autouse fixture."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')


def build_worker(persist, timings=None, **over):
    provider = Words()
    decoded, diarized, failures = [], [], []

    def decode(work):
        decoded.append(work.segment_id)
        return Samples(work.duration_seconds)

    def diarize(samples):
        diarized.append(len(samples))
        return {'turns': []}

    settings = dict(
        language_of=lambda unit: 'en',
        decode=decode,
        vad=lambda samples: [(0, len(samples) / 16000)],
        words_providers={'parakeet': provider},
        diarizers={'pyannote': diarize},
        persist=persist,
        io_concurrency=1,
        on_failure=lambda unit, error: failures.append((unit.segment_id, error)),
    )
    if timings is not None:
        settings['timings'] = timings
    settings.update(over)
    worker = PipelineWorker(**settings)
    return worker, dict(provider=provider, decoded=decoded, diarized=diarized, failures=failures)


def script_for(strikes, final='OK', fault=None):
    """Literal persist script: `strikes` transport faults, then `final`.

    `strikes` must stay under the lane cap (recovery needs a call left for
    `final`); an exhaustion script passes the same fault as both builder and
    ``default`` through ``ScriptedPersist(script, default=fault)``.
    """
    source = fault if fault is not None else InvalidArgument
    return [source('burst') for _ in range(strikes)] + [final]


def exhaust_script(fault=None):
    """Literal exhaustion script: the cap worth of faults, replayed past the cap."""
    source = fault if fault is not None else InvalidArgument
    return ScriptedPersist([source('burst')] * 3, default=source('burst'))


def contention(stamp=0.0, message='register storm'):
    """A `FirestoreContentionExhausted` carrying the given damper stamp."""
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    return FirestoreContentionExhausted(message, reason='attempts_exhausted', retry_after=stamp)


def stamped(stamp, message='stamped'):
    """A plain fault object carrying a raw `retry_after` attribute."""
    import types

    fault = types.SimpleNamespace(args=(message,))
    fault.retry_after = stamp
    return fault


class StampCarrier(RuntimeError):
    """A foreign RuntimeError subclass carrying an arbitrary `retry_after`."""

    def __init__(self, message='carrier', stamp=0.0):
        super().__init__(message)
        self.retry_after = stamp


class PerSegmentPersist:
    """Route each segment to its own scripted persist (sibling-independence cells)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, work, payload):
        self.calls.append(work.segment_id)
        return self.routes[work.segment_id](work, payload)


def run_lane(monkeypatch, script, gate='true', safety_net='false', **over):
    """Build the worker with the script under the gate and run one unit through process_batch."""
    pin_full_gpu_stages(monkeypatch)
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', safety_net)
    monkeypatch.setenv(GATE, gate)
    sleeps = SleepRecorder()
    monkeypatch.setattr(bp.time, 'sleep', sleeps)
    persist = script if isinstance(script, (ScriptedPersist, PerSegmentPersist)) else ScriptedPersist(script)
    timings = over.pop('timings', None)
    unit = over.pop('unit', item())
    worker, meta = build_worker(persist, timings=timings, **over)
    results = worker.process_batch([unit])
    return dict(
        results=results,
        worker=worker,
        persist=persist,
        sleeps=sleeps,
        meta=meta,
        timings=timings,
    )


def run_two_units(monkeypatch, script, gate='true', **over):
    """Run two units through one worker with one scripted persist (script plays across both)."""
    pin_full_gpu_stages(monkeypatch)
    monkeypatch.setenv(GATE, gate)
    sleeps = SleepRecorder()
    monkeypatch.setattr(bp.time, 'sleep', sleeps)
    persist = script if isinstance(script, (ScriptedPersist, PerSegmentPersist)) else ScriptedPersist(script)
    worker, meta = build_worker(persist, **over)
    results = worker.process_batch([over.pop('first', item('a')), over.pop('second', item('b'))])
    return dict(results=results, worker=worker, persist=persist, sleeps=sleeps, meta=meta)
