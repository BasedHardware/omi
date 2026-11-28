"""Allocate dedicated-worker ASR CUDA stream time across windows in one dispatch."""

from collections import Counter as Counts
from collections.abc import Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from typing import Any

from prometheus_client import Counter

_Dispatch = tuple[str, tuple[str, ...], list[str], float, Any, Any]
_current: ContextVar[list[_Dispatch] | None] = ContextVar('batch_asr_spend', default=None)
_cohorts: ContextVar[tuple[str, tuple[str, ...]]] = ContextVar('batch_asr_cohorts', default=('unknown', ()))


def audio_cohort(speech_seconds: float | None, *, shadow: bool = False) -> str:
    if shadow:
        return 'shadow'
    if speech_seconds is None:
        return 'unknown'
    if speech_seconds == 0:
        return 'silence'
    return 'under_2s' if speech_seconds < 2 else 'at_least_2s'


@contextmanager
def windows(stage: str, cohorts: Iterable[str]):
    token = _cohorts.set((stage, tuple(cohorts)))
    try:
        yield
    finally:
        _cohorts.reset(token)


class AsrSpend:
    def __init__(self, registry):
        grouping = ['stage', 'audio', 'outcome', 'timing']
        self.dispatches = Counter(
            'omi_batch_asr_dispatches_total',
            'Parakeet model dispatches including failures',
            ['stage'],
            registry=registry,
        )
        self.windows = Counter(
            'omi_batch_asr_windows_total', 'Windows submitted to the model', grouping, registry=registry
        )
        self.gpu = Counter(
            'omi_batch_asr_gpu_seconds_total',
            'CUDA stream elapsed seconds allocated equally across windows in each dispatch',
            grouping[:-1],
            registry=registry,
        )
        self.wall = Counter(
            'omi_batch_asr_dispatch_wall_seconds_total',
            'Model dispatch wall seconds allocated equally across windows in each dispatch',
            grouping,
            registry=registry,
        )

    @contextmanager
    def flight(self):
        pending: list[_Dispatch] = []
        token = _current.set(pending)
        try:
            yield
        finally:
            _current.reset(token)
            # The runtime has already synchronized the worker's device. Elapsed
            # reads can fail on a poisoned stream. Keep those windows in coverage.
            for stage, cohorts, outcomes, wall, start, end in pending:
                labels = Counts(zip(cohorts, outcomes if len(outcomes) == len(cohorts) else ['unknown'] * len(cohorts)))
                try:
                    seconds = start.elapsed_time(end) / 1000 if start and end and end.query() else None
                except Exception:
                    seconds = None
                try:
                    self.dispatches.labels(stage).inc()
                    total = sum(labels.values())
                    timing = 'cuda' if seconds is not None else 'unknown'
                    for (audio, outcome), count in labels.items():
                        share = count / total
                        self.windows.labels(stage, audio, outcome, timing).inc(count)
                        self.wall.labels(stage, audio, outcome, timing).inc(wall * share)
                        if seconds is not None:
                            self.gpu.labels(stage, audio, outcome).inc(seconds * share)
                except Exception:
                    pass  # Metrics must never invalidate the model result.


@contextmanager
def measure(torch, model, size):
    pending = _current.get()
    if pending is None:
        yield None
        return
    stage, cohorts = _cohorts.get()
    if len(cohorts) != size:
        cohorts = ('unknown',) * size
    start = end = stream = None
    try:
        stream = torch.cuda.current_stream(model.device)
        start = torch.cuda.Event(enable_timing=True)
        start.record(stream)
    except Exception:
        start = None
    outcomes: list[str] = []
    started = perf_counter()
    try:
        yield outcomes
    finally:
        wall = perf_counter() - started
        if start is not None:
            try:
                end = torch.cuda.Event(enable_timing=True)
                end.record(stream)
            except Exception:
                end = None
        pending.append((stage, cohorts, outcomes, wall, start, end))
