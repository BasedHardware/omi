"""Content-free wall timings for the dedicated worker's serialized chain."""

from contextlib import contextmanager
import time

from prometheus_client import CollectorRegistry, Histogram

from config.batch_pipeline import stage_profiling_enabled

STAGES = frozenset(
    {
        'pump_cycle',
        'maintenance',
        'pull',
        'admission',
        'worker_flight',
        'publication',
        'renew',
        'ordered_merge',
        'projection',
        'fetch_decode',
        'vad',
        'windows',
        'asr',
        'asr_recovery',
        'flight_segment',
        'flight_diarize',
        'diarize',
        'persist',
        'cuda_sync',
    }
)


class StageTimings:
    """Per-stage wall-clock histogram; a disabled or unwired instance is a no-op.

    ``BATCH_PIPELINE_STAGE_PROFILING_ENABLED`` gates histogram creation once at
    construction (see ``config.batch_pipeline.stage_profiling_enabled``); the
    dedicated runtime passes its explicit ``CollectorRegistry`` so samples are
    exposed only on the worker's own ``/metrics`` endpoint.
    """

    def __init__(self, registry: CollectorRegistry | None = None):
        self.duration = (
            Histogram(
                'omi_batch_pipeline_stage_seconds',
                'Wall time including executor wait; pump_cycle and worker_flight contain child stages',
                ['stage'],
                buckets=(
                    0.00001,
                    0.00005,
                    0.0001,
                    0.0005,
                    0.001,
                    0.0025,
                    0.005,
                    0.01,
                    0.05,
                    0.1,
                    0.5,
                    1,
                    2,
                    5,
                    10,
                    20,
                    40,
                    80,
                    160,
                    320,
                ),
                registry=registry,
            )
            if registry is not None and stage_profiling_enabled()
            else None
        )

    def call(self, stage, function, *args, **kwargs):
        with self.measure(stage):
            return function(*args, **kwargs)

    @contextmanager
    def measure(self, stage: str):
        if stage not in STAGES:
            raise ValueError('worker timing stage must be static')
        histogram = self.duration
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
                pass  # Telemetry cannot invalidate compute or a durable transition.
