"""Shared fallback / resilience telemetry for the Python backend.

Silent UX healing is allowed; silent ops is not. New degrade/failover branches
must call ``record_fallback`` instead of inventing per-domain counters.

Contract fields (same mental model as desktop Swift/Rust emitters):
  component, from_mode, to_mode, reason, outcome
"""

from __future__ import annotations

import logging
from typing import Literal

from utils.metrics import OMI_FALLBACK_TOTAL

logger = logging.getLogger(__name__)

FallbackOutcome = Literal['recovered', 'degraded', 'exhausted']

FALLBACK_EVENT = 'omi_fallback_event'

_LABEL_MAX_LENGTH = 64
_SAFE_LABEL_CHARS = frozenset('._:-')

ALLOWED_OUTCOMES = frozenset({'recovered', 'degraded', 'exhausted'})

ALLOWED_REASONS = frozenset(
    {
        'timeout',
        'provider_5xx',
        'provider_429',
        'enqueue_failed',
        'config_incomplete',
        'circuit_open',
        'capability_mismatch',
        'auth',
        'quota',
        'local_heal',
        'policy',
        'dispatch_disabled',
        'byok',
        'malformed_doc',
        'capacity_full',
        'allocation_zero',
        'allocation_rejected',
        'other',
        'none',
    }
)

ALLOWED_COMPONENTS = frozenset(
    {
        'sync_dispatch',
        'pusher',
        'stt_selection',
        'vad',
        'audio_merge',
        'webhook',
        'realtime_hub',
        'ptt_cascade',
        'gemini_model',
        'gemini_proxy',
        'gemini_stream_proxy',
        'llm_gateway',
        'redis_ratelimit',
        'silent_mic',
        'firestore_read',
        'other',
    }
)


def record_fallback(
    *,
    component: str,
    from_mode: str,
    to_mode: str,
    reason: str,
    outcome: str,
    log: logging.Logger | None = None,
) -> None:
    """Increment ``omi_fallback_total`` and emit a matching warning log.

    Never raises. Unknown reasons/components are bucketed to ``other``.
    Invalid outcomes are bucketed to ``degraded`` so the counter still fires.
    """
    component_label = bucket_component(component)
    from_label = safe_label(from_mode, default='none')
    to_label = safe_label(to_mode, default='none')
    reason_label = bucket_reason(reason)
    outcome_label = bucket_outcome(outcome)

    try:
        OMI_FALLBACK_TOTAL.labels(
            component=component_label,
            from_mode=from_label,
            to_mode=to_label,
            reason=reason_label,
            outcome=outcome_label,
        ).inc()
    except Exception:
        pass

    emit_log = log or logger
    try:
        emit_log.warning(
            '%s component=%s from=%s to=%s reason=%s outcome=%s',
            FALLBACK_EVENT,
            component_label,
            from_label,
            to_label,
            reason_label,
            outcome_label,
        )
    except Exception:
        pass


def bucket_reason(reason: str, *, allowed: frozenset[str] | None = None) -> str:
    allowed_set = allowed or ALLOWED_REASONS
    label = safe_label(reason, default='other')
    if label in allowed_set:
        return label
    return 'other'


def bucket_outcome(outcome: str) -> str:
    label = safe_label(outcome, default='degraded')
    if label in ALLOWED_OUTCOMES:
        return label
    return 'degraded'


def bucket_component(component: str) -> str:
    label = safe_label(component, default='other')
    if label in ALLOWED_COMPONENTS:
        return label
    return 'other'


def safe_label(value: object, *, default: str = 'unknown') -> str:
    text = str(value or '').strip().casefold()
    if not text:
        text = default
    normalized = ''.join(char if char.isalnum() or char in _SAFE_LABEL_CHARS else '_' for char in text)
    return (normalized or default)[:_LABEL_MAX_LENGTH]
