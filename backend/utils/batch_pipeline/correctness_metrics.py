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
CONFLICT_HOLDS = Counter(
    'omi_batch_pipeline_projection_conflict_holds_total', 'Observed assignment conflict holds', ['subtype']
)
# One sample per committed recovery settlement: what each paid recognizer
# answered, how much speech our own detectors measured, and how the unit ended.
RECOGNIZER_OUTCOMES = Counter(
    'omi_batch_pipeline_recovery_recognizer_outcomes_total',
    'Committed recovery settlements by recognizer answers, measured held speech and result',
    ['modulate', 'soniox', 'speech', 'language_guarded', 'result'],
)
RECOGNIZER_ANSWERS = frozenset({'words', 'empty', 'error', 'refused', 'started'})
SETTLEMENT_RESULTS = frozenset({'words', 'silence', 'no_recoverable_speech', 'failed_held'})
# Vendor recovery skips units below this much strict-VAD speech (BATCH_VENDOR_MIN_SPEECH_SECONDS default).
SHORT_SPEECH_SECONDS = 2.0


def speech_bucket(seconds) -> str:
    """Held speech census (the largest validated measure) as a closed label."""
    from config.batch_language_recovery import below_silence_threshold

    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds != seconds or seconds < 0:
        return 'unmeasured'
    if below_silence_threshold(seconds):
        return 'none'
    return 'under_2s' if seconds < SHORT_SPEECH_SECONDS else '2s_or_more'


def record_recovery_settlement(recognizers, speech_seconds, language_guarded, result) -> None:
    """Never raises: telemetry follows a committed settlement and cannot undo it."""
    try:
        if not enabled():
            return
        receipts = recognizers if isinstance(recognizers, dict) else {}

        def answer(provider):
            receipt = receipts.get(provider)
            outcome = receipt.get('outcome') if isinstance(receipt, dict) else None
            return outcome if outcome in RECOGNIZER_ANSWERS else 'not_called'

        RECOGNIZER_OUTCOMES.labels(
            answer('modulate'),
            answer('soniox'),
            speech_bucket(speech_seconds),
            'true' if language_guarded else 'false',
            result if result in SETTLEMENT_RESULTS else 'other',
        ).inc()
    except Exception:
        pass


def record_conflict_hold(subtype: object) -> None:
    from utils.sync.assignment_errors import bounded_sync_assignment_subtype

    if enabled():
        CONFLICT_HOLDS.labels(bounded_sync_assignment_subtype(subtype)).inc()


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
