"""Speech-positive zero-word sync segments must not settle as silence after a degraded chain.

Prod runs ``SYNC_EMPTY_MULTILINGUAL_RECOVERY_ENABLED=false``, so the strict-VAD
multilingual recovery never runs and a double-empty segment is recorded as
``expected_silence`` with no error — the job completes with zero words even when
the audio is speech and the provider chain was failing (2026-10-23 staging soak:
Parakeet blackholed, Modulate credit-starved at language detection, every
speech-positive unit completed empty).

This guard runs the same free strict local VAD at that silence decision. When
the audio carries at least ``LONG_SPEECH_HANDOFF_SECONDS`` of speech AND the
chain that produced the empty was degraded — a recent prerecorded vendor
failure noted by the adapters, or a credit/auth refusal recorded by the vendor
guard — the segment fails with the existing retryable ``empty_unexpected``
outcome instead of completing as silence. Genuine silence, short speech, and
healthy-chain empties keep today's behavior.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from prometheus_client import Counter

from config.batch_pipeline import LONG_SPEECH_HANDOFF_SECONDS
from config.refactor_switches import default_on as rollout_default_on
from utils.stt.outcomes import bounded_provider

logger = logging.getLogger(__name__)

# Vocabulary shared with utils.stt.prerecorded_health (imported lazily so the
# sync pipeline stays importable under the router isolation harness, where
# utils.stt is a non-package stub).
CREDIT_AUTH = 'credit_auth'
PROVIDER_ERROR = 'provider_error'

# A Cloud Tasks redelivery proves a prior attempt failed somewhere — often the
# provider error this guard exists for — on an instance whose in-memory state
# this one cannot see. Durable per-unit degradation evidence.
_prior_failed_attempt: ContextVar[bool] = ContextVar('sync_prior_failed_attempt', default=False)


@contextmanager
def prior_failed_attempt(value: bool) -> Iterator[None]:
    """Mark this coordinator attempt as a redelivery of a failed attempt."""
    token = _prior_failed_attempt.set(bool(value))
    try:
        yield
    finally:
        _prior_failed_attempt.reset(token)


GUARD_TOTAL = Counter(
    'omi_sync_empty_success_guard_total',
    'Zero-word sync segment dispositions at the silence decision, by provider and reason',
    ['provider', 'reason'],
)

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


def chain_degradation() -> str | None:
    """The strongest degradation signal for this unit's chain.

    Credit/auth outranks a generic provider error: an out-of-credits refusal is
    deterministic until the account is funded, and both the vendor guard's
    recorded refusals and the adapters' typed budget failures carry it. A Cloud
    Tasks redelivery follows: the prior attempt failed somewhere — possibly on
    another instance whose failure state left no trace here.
    """
    from utils.stt.prerecorded_health import recent_provider_failure
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
    if _prior_failed_attempt.get():
        return PROVIDER_ERROR
    return recent_provider_failure()


def settle(path: str, *, provider: str) -> tuple[bool, str]:
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
    degradation = chain_degradation()
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
