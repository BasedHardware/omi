"""Process-local Prometheus counters for batch diarization skip decisions.

Labels are closed tokens only; never segment IDs, owners or clocks. Sum across
worker processes. ``decision`` is one of DECISIONS.
"""

from prometheus_client import Counter

DECISIONS = frozenset(
    {
        'full_flag_off',
        'full_kept_over_80pct',
        'full_no_evidence',
        'full_compaction_error',
        'full_compacted_empty',
        'compacted',
        'skipped_short',
    }
)

DIARIZATION_DECISIONS = Counter(
    'omi_batch_pipeline_diarization_decisions_total', 'Batch worker diarization decisions per unit', ['decision']
)
DIARIZATION_AUDIO_SECONDS = Counter(
    'omi_batch_pipeline_diarization_audio_seconds_total',
    'Batch unit audio seconds and seconds actually sent to the diarizer',
    ['kind'],
)
COMPACTED_UNASSIGNED_UNITS = Counter(
    'omi_batch_pipeline_compacted_unassigned_units_total',
    'Persisted speech-only diarization results with at least one word outside every turn',
)
COMPACTED_UNASSIGNED_WORDS = Counter(
    'omi_batch_pipeline_compacted_unassigned_words_total',
    'Words outside every turn in persisted speech-only diarization results',
)


def record_decision(decision: str, *, unit_seconds: float = 0.0, diarized_seconds: float = 0.0) -> None:
    if decision not in DECISIONS:
        raise ValueError('closed diarization decision required')
    try:
        DIARIZATION_DECISIONS.labels(decision=decision).inc()
        if unit_seconds > 0:
            DIARIZATION_AUDIO_SECONDS.labels(kind='unit').inc(unit_seconds)
        if diarized_seconds > 0:
            DIARIZATION_AUDIO_SECONDS.labels(kind='diarized').inc(diarized_seconds)
    except Exception:
        pass  # Observability cannot change a diarization result.


def record_compacted_unassigned(words: int) -> None:
    if words <= 0:
        return
    try:
        COMPACTED_UNASSIGNED_UNITS.inc()
        COMPACTED_UNASSIGNED_WORDS.inc(words)
    except Exception:
        pass
