"""Privacy-safe instrumentation for durable speaker-learning jobs.

One counter, closed enums only: target (owner/person) and outcome (queued,
retried, stored, plus each terminal reason). Never names, transcript text,
audio, embeddings, or ids.
"""

from prometheus_client import REGISTRY, Counter


def _speaker_learning_jobs_counter() -> Counter:
    # Harness tests reload modules that import this one; reuse the registered collector
    # instead of registering a duplicate timeseries.
    try:
        return Counter(
            'omi_speaker_learning_jobs_total',
            'Durable speaker-learning job transitions by target and outcome.',
            ['target', 'outcome'],
        )
    except ValueError:
        return REGISTRY._names_to_collectors['omi_speaker_learning_jobs_total']  # type: ignore[attr-defined]


SPEAKER_LEARNING_JOBS = _speaker_learning_jobs_counter()

_TARGETS = frozenset({'person', 'owner'})
_OUTCOMES = frozenset(
    {
        'queued',
        'retried',
        'stored',
        'exhausted',
        'superseded',
        'deleted',
        'locked',
        'discarded',
        'disabled',
        'capacity_exhausted',
        'segment_limit',
        'text_mismatch',
        'insufficient_speech',
        'insufficient_words',
        'multi_speaker',
        'contaminated',
        'clip_not_clean',
        'rejected_quality',
        'rejected_embedding',
        'no_audio',
        'no_chunks',
        'uncovered_audio',
        'transcription_failed',
        'embedding_failed',
        'timeout',
        'error',
        'other',
    }
)


def record_speaker_learning_job_events(events) -> None:
    for target, outcome in events or ():
        SPEAKER_LEARNING_JOBS.labels(
            target=target if target in _TARGETS else 'person',
            outcome=outcome if outcome in _OUTCOMES else 'other',
        ).inc()
