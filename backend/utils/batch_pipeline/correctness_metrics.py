"""Observed committed transitions, never a database reconciliation or scan.

Counters are process-local and can undercount a lost transaction reply or process
exit. Sum rates/increases across CPU and GPU processes; never equate a sampled
counter delta with a durable ledger census. Labels contain only closed tokens.

`failed` counts every quarantine (CUDA, validation, empty ASR) and `recovered`
automatic recoveries with a result (epoch-2 operator successes are not counted),
so failed/admitted is not an unrecovered-empty-ASR rate.
Gate a ramp on durable job fields (`recovery_state`, `worker_empty_evidence`).
"""

import os

from prometheus_client import Counter

TRANSITIONS = Counter(
    'omi_batch_pipeline_correctness_transitions_total', 'Observed committed transitions', ['event', 'source']
)
DURATION = Counter(
    'omi_batch_pipeline_correctness_audio_seconds_total', 'Captured duration at each observed transition', ['event']
)
LABELS = Counter(
    'omi_batch_pipeline_projected_segments_total', 'New persisted segments by assignment authority', ['authority']
)


def enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_CORRECTNESS_METRICS_ENABLED', 'false').lower() == 'true'


def record(event: str, *, source: str = 'cpu', seconds: float = 0) -> None:
    if event not in {
        'admitted',
        'failed',
        'recovered',
        'committed',
        'projection_completed',
        'empty_asr_attempt',
        'no_recoverable_speech',
    }:
        raise ValueError('closed transition event required')
    if source not in {'cpu', 'gpu_pump', 'ordered_merge', 'gpu_worker'}:
        raise ValueError('closed transition source required')
    if enabled():
        TRANSITIONS.labels(event, source).inc()
        if seconds > 0:
            DURATION.labels(event).inc(seconds)


def record_labels(segments) -> None:
    if enabled():
        for segment in segments:
            authority = 'batch' if (segment.get('speaker_id_scope') or '').startswith('final:batch:') else 'legacy'
            if segment.get('speaker_match_source') == 'batch_abstention' or segment.get('speaker') is None:
                authority = 'abstained'
            LABELS.labels(authority).inc()
