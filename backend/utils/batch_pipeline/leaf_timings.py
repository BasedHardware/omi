"""Propagate the worker's private timing registry through synchronous leaf calls.

The context is installed inside the actual IO/model thread, never at submission.
Other artifact callers have no active profiler and retain a no-op fast path.
"""

from contextlib import contextmanager
from contextvars import ContextVar
import time

from utils.batch_pipeline.stage_timings import StageTimings

STAGES = frozenset(
    {
        'download',
        'download_metadata',
        'decrypt',
        'decode',
        'encrypt',
        'upload',
        'artifact_register',
        'embedding',
        'flight_embedding',
    }
)
_ACTIVE: ContextVar[StageTimings | None] = ContextVar('batch_pipeline_leaf_timings', default=None)


@contextmanager
def active(timings: StageTimings | None):
    token = _ACTIVE.set(timings)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


@contextmanager
def measure(stage: str):
    if stage not in STAGES:
        raise ValueError('worker leaf timing stage must be static')
    timings = _ACTIVE.get()
    histogram = timings.duration if timings is not None else None
    if histogram is None:
        yield
        return
    try:
        started = time.perf_counter()
    except Exception:
        yield
        return
    try:
        yield
    finally:
        try:
            histogram.labels(stage).observe(max(0.0, time.perf_counter() - started))
        except Exception:
            pass  # Preserve results, original exceptions and cancellation.


def call(stage, function, *args, **kwargs):
    with measure(stage):
        return function(*args, **kwargs)


@contextmanager
def embedding_hook(model):
    """Time pyannote's existing embedding hook; restore it even on model failure.

    The dedicated chain already serializes model calls. No model precision,
    CUDA synchronization, input, clustering or result is changed.
    """
    timings = _ACTIVE.get()
    if timings is None or timings.duration is None:
        yield
        return
    original = getattr(model, 'get_embeddings', None)
    if not callable(original):
        yield
        return
    installed = False
    try:
        object.__setattr__(model, 'get_embeddings', lambda *a, **kw: call('embedding', original, *a, **kw))
        installed = True
    except Exception:
        pass  # An unsupported model layout must not prevent inference.
    try:
        yield
    finally:
        if installed:
            try:
                object.__setattr__(model, 'get_embeddings', original)
            except Exception:
                pass  # A telemetry cleanup failure cannot replace a model failure.
