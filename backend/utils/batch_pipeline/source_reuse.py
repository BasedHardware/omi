"""Bounded exact-source counters and live kill switch; no CPU intake imports."""

from prometheus_client import Counter
from config.batch_pipeline_source_reuse import enabled as enabled

EVENTS = Counter('omi_batch_pipeline_source_reuse_total', 'Observed exact-source reuse decisions', ['event'])
SECONDS = Counter(
    'omi_batch_pipeline_source_reuse_seconds_total', 'Observed source input seconds, not GPU wall time', ['event']
)


def observe(event: str, seconds: float = 0.0) -> None:
    if event not in {
        'reused',
        'avoided_asr_input',
        'alias_wait',
        'alias_refusal',
        'uncovered_tail',
        'duplicate_projection_refusal',
        'custody_failure',
        'fallback',
    }:
        raise ValueError('closed source reuse event required')
    EVENTS.labels(event).inc()
    if seconds > 0:
        SECONDS.labels(event).inc(seconds)
