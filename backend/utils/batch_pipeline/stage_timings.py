"""Content-free wall timings for the dedicated worker's serialized chain."""

from contextlib import contextmanager
import time

from prometheus_client import CollectorRegistry, Histogram

STAGES = frozenset(
    {
        'pump_cycle',
        'maintenance',
        'pull',
        'admission',
        'worker_flight',
        'publication',
        'ordered_merge',
        'projection',
        'fetch_decode',
        'vad',
        'windows',
        'asr',
        'asr_recovery',
        'diarize',
        'persist',
        'cuda_sync',
    }
)


class StageTimings:
    def __init__(self, registry: CollectorRegistry | None = None):
        self.duration = (
            Histogram(
                'omi_batch_pipeline_stage_seconds',
                'Wall time including executor wait; pump_cycle and worker_flight contain child stages',
                ['stage'],
                buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 20, 40, 80, 160, 320),
                registry=registry,
            )
            if registry is not None
            else None
        )

    def call(self, stage, function, *args, **kwargs):
        with self.measure(stage):
            return function(*args, **kwargs)

    @contextmanager
    def measure(self, stage: str):
        if stage not in STAGES:
            raise ValueError('worker timing stage must be static')
        started = time.perf_counter()
        try:
            yield
        finally:
            if self.duration is not None:
                try:
                    self.duration.labels(stage).observe(max(0.0, time.perf_counter() - started))
                except Exception:
                    pass  # Telemetry cannot invalidate compute or a durable transition.
