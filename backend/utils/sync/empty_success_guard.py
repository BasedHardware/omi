"""Speech-positive zero-word sync segments must not settle as silence after a degraded chain.

Prod runs ``SYNC_EMPTY_MULTILINGUAL_RECOVERY_ENABLED=false``, so the strict-VAD
multilingual recovery never runs and a double-empty segment is recorded as
``expected_silence`` with no error — the job completes with zero words even when
the audio is speech and the provider chain was failing (2026-10-23 staging soak:
Parakeet blackholed, Modulate credit-starved at language detection, every
speech-positive unit completed empty).

This guard runs the same free strict local VAD at that silence decision. When
the audio carries at least ``LONG_SPEECH_HANDOFF_SECONDS`` of speech AND the
chain that produced the empty was degraded — a provider-class failure already
recorded for this job (durable across Cloud Tasks retries and instances), this
segment's own swallowed LID probe failure, or a credit/auth refusal in the
vendor guard — the segment fails with the existing retryable
``empty_unexpected`` outcome instead of completing as silence. Genuine
silence, short speech, and healthy-chain empties keep today's behavior.
"""

from __future__ import annotations

import logging
import os

from config.batch_pipeline import LONG_SPEECH_HANDOFF_SECONDS
from config.refactor_switches import default_on as rollout_default_on
from utils.metrics import OMI_SYNC_EMPTY_SUCCESS_GUARD_TOTAL
from utils.stt.outcomes import bounded_provider

logger = logging.getLogger(__name__)

# Vocabulary shared with utils.stt.prerecorded_health (imported lazily so the
# sync pipeline stays importable under the router isolation harness, where
# utils.stt is a non-package stub).
CREDIT_AUTH = 'credit_auth'
PROVIDER_ERROR = 'provider_error'

# Durable per-job marker: some segment of this job (any attempt, any instance)
# ended in a provider-class failure. Written by the pipeline's segment-failure
# recorder; read here before a zero-word segment settles as silence.
PRIOR_PROVIDER_FAILURE_TAG = 'prior_provider_failure'
# Outcomes that prove the provider chain failed for this job. A failure before
# any provider call (lease loss, cancellation, pre-transcription timeout) never
# reaches that recorder, so a healthy chain that was merely redelivered stays
# healthy.
PROVIDER_CLASS_OUTCOMES = frozenset(('upstream_error', 'timeout', 'provider_budget_exhausted', 'empty_unexpected'))

# The collector lives in utils.metrics (the metric-owner module that outlives
# per-test stub windows): this module is imported alongside the sync pipeline,
# which isolated test harnesses re-execute, and an import-time Counter here
# re-registers as a duplicated timeseries.
GUARD_TOTAL = OMI_SYNC_EMPTY_SUCCESS_GUARD_TOTAL

HELD_PROVIDER_ERROR = 'held_provider_error'
HELD_CREDIT_AUTH = 'held_credit_auth'
SILENCE_CONFIRMED = 'silence_confirmed'
SPEECH_BELOW_THRESHOLD = 'speech_below_threshold'
INSPECTION_UNAVAILABLE = 'inspection_unavailable'
GUARD_DISABLED = 'guard_disabled'
SPEECH_POSITIVE_HEALTHY_CHAIN = 'speech_positive_healthy_chain'
REASONS = frozenset(
    {
        HELD_PROVIDER_ERROR,
        HELD_CREDIT_AUTH,
        SILENCE_CONFIRMED,
        SPEECH_BELOW_THRESHOLD,
        INSPECTION_UNAVAILABLE,
        GUARD_DISABLED,
        SPEECH_POSITIVE_HEALTHY_CHAIN,
    }
)


def enabled() -> bool:
    # Only the explicit kill value disables the guard; malformed values stay safe.
    return rollout_default_on(
        'SYNC_EMPTY_SUCCESS_GUARD_ENABLED',
        os.getenv('SYNC_EMPTY_SUCCESS_GUARD_ENABLED', 'true').strip().lower() != 'false',
    )


def chain_degradation(job_id: str | None) -> str | None:
    """The strongest degradation signal for this unit's chain.

    Credit/auth outranks a generic provider error: an out-of-credits refusal is
    deterministic until the account is funded, and both the vendor guard's
    recorded refusals and the typed budget failures carry it. The per-job
    marker follows: some segment of this job ended in a provider-class failure,
    on this or a prior Cloud Tasks attempt, on this or another instance. The
    dispatch note is last: this segment's own swallowed LID probe failure.
    """
    from utils.stt.vendor_guard import (
        ENDPOINT_LID,
        ENDPOINT_STT,
        breaker_budget_exhausted,
        quota_failures_in_window,
    )

    if (
        breaker_budget_exhausted(ENDPOINT_STT)
        or breaker_budget_exhausted(ENDPOINT_LID)
        or quota_failures_in_window(ENDPOINT_STT)
        or quota_failures_in_window(ENDPOINT_LID)
    ):
        return CREDIT_AUTH
    if job_id and _job_prior_provider_failure(job_id):
        return PROVIDER_ERROR
    from utils.stt.prerecorded_health import recent_dispatch_failure

    return recent_dispatch_failure()


def _job_prior_provider_failure(job_id: str) -> bool:
    """Strict bool: a stubbed or unreadable marker never degrades a chain."""
    try:
        from database.sync_jobs import was_marked_once

        marked = was_marked_once(job_id, PRIOR_PROVIDER_FAILURE_TAG)
    except Exception:
        return False
    return marked is True


def settle(path: str, *, provider: str, job_id: str | None = None) -> tuple[bool, str]:
    """Decide a zero-word segment's disposition before it is recorded as silence.

    Returns ``(held, reason)``. ``held`` means the caller must fail the segment
    with the retryable ``empty_unexpected`` outcome instead of recording
    ``expected_silence``. Never raises for audio or VAD problems: an inspection
    failure keeps today's silence behavior and is counted.
    """
    label = bounded_provider(provider)
    if not enabled():
        return _settled(label, GUARD_DISABLED, held=False)
    from utils.sync.empty_recovery import inspect_strict

    try:
        _pcm, duration, spans = inspect_strict(path)
    except Exception:
        return _settled(label, INSPECTION_UNAVAILABLE, held=False)
    speech_seconds = sum(span['end'] - span['start'] for span in spans)
    try:
        logger.info(
            'event=sync_empty_success_guard outcome=inspected provider=%s duration_seconds=%.3f '
            'vad_spans=%d speech_seconds=%.3f',
            label,
            duration,
            len(spans),
            speech_seconds,
        )
    except Exception:
        pass
    if not spans:
        return _settled(label, SILENCE_CONFIRMED, held=False)
    if speech_seconds < LONG_SPEECH_HANDOFF_SECONDS:
        return _settled(label, SPEECH_BELOW_THRESHOLD, held=False)
    degradation = chain_degradation(job_id)
    if degradation == CREDIT_AUTH:
        return _settled(label, HELD_CREDIT_AUTH, held=True)
    if degradation == PROVIDER_ERROR:
        return _settled(label, HELD_PROVIDER_ERROR, held=True)
    return _settled(label, SPEECH_POSITIVE_HEALTHY_CHAIN, held=False)


def _settled(provider: str, reason: str, *, held: bool) -> tuple[bool, str]:
    try:
        GUARD_TOTAL.labels(provider, reason).inc()
    except Exception:
        pass
    return held, reason
