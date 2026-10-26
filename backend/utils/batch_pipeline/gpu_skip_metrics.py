"""Process-local Prometheus counters for batch diarization skip decisions.

Labels are closed tokens only; never segment IDs, owners or clocks. Sum across
worker processes. ``decision`` is one of DECISIONS, ``outcome`` one of
UNIT_OUTCOMES, ``speakers`` one of SPEAKER_TOKENS and ``flight`` one of
FLIGHT_TOKENS.
"""

from typing import Any

from prometheus_client import Counter, Histogram

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
UNIT_OUTCOMES = frozenset({'silence', 'skipped_single', 'diarized'})
SPEAKER_TOKENS = frozenset({'0', '1', '2', '3', '4', '5', '6_plus'})
FLIGHT_TOKENS = frozenset({'off', 'on'})

UNIT_OUTCOME = Counter(
    'omi_batch_pipeline_unit_diarization_outcome_total',
    'Units reaching persistence assembly by final diarization outcome',
    ['outcome'],
)
UNIT_SPEAKERS = Counter(
    'omi_batch_pipeline_unit_speakers_total',
    'Units reaching persistence assembly by distinct diarized speaker count',
    ['speakers', 'flight'],
)
UNIT_TURNS = Histogram(
    'omi_batch_pipeline_unit_speaker_turns',
    'Speaker turns per unit reaching persistence assembly',
    ['flight'],
    buckets=(1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048),
)

COMPACTED_UNASSIGNED_UNITS = Counter(
    'omi_batch_pipeline_compacted_unassigned_units_total',
    'Persisted speech-only diarization results with at least one word outside every turn',
)
COMPACTED_UNASSIGNED_WORDS = Counter(
    'omi_batch_pipeline_compacted_unassigned_words_total',
    'Words outside every turn in persisted speech-only diarization results',
)

WORKER_COUNTERS = (
    DIARIZATION_DECISIONS,
    DIARIZATION_AUDIO_SECONDS,
    COMPACTED_UNASSIGNED_UNITS,
    COMPACTED_UNASSIGNED_WORDS,
    UNIT_OUTCOME,
    UNIT_SPEAKERS,
    UNIT_TURNS,
)


def register_on(registry) -> None:
    """Also expose this module's collectors on an explicit registry.

    The dedicated worker serves /metrics from the CollectorRegistry built in
    diarizer.batch_pipeline_runtime, not the prometheus_client default, so
    default-registered counters are invisible from worker pods unless they are
    registered here too (the historical omi_batch_pipeline_diarization_decisions
    gap and the FP32-parity unit families).
    """
    for collector in WORKER_COUNTERS:
        registry.register(collector)


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


def record_unit_diarization(outcome: str, turns: Any, *, flight_batching: bool) -> None:
    """Count-only per-unit diarization shape, for FP32 flight-batching parity gates.

    Units are counted at persistence assembly, not at durable commit. Labels
    carry speaker-count buckets and the worker's flight-batching mode only;
    no segment IDs, owners, words, clocks or audio.
    """
    if outcome not in UNIT_OUTCOMES:
        raise ValueError('closed unit diarization outcome required')
    try:
        flight = 'on' if flight_batching else 'off'
        turns = list(turns or ())
        speakers = len({t['speaker'] for t in turns if isinstance(t, dict) and t.get('speaker')})
        token = str(speakers) if speakers <= 5 else '6_plus'
        UNIT_OUTCOME.labels(outcome=outcome).inc()
        UNIT_SPEAKERS.labels(speakers=token, flight=flight).inc()
        UNIT_TURNS.labels(flight=flight).observe(len(turns))
    except Exception:
        pass  # Observability cannot change a diarization result.
