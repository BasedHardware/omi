"""Shared fallback / resilience telemetry for the Python backend.

Silent UX healing is allowed; silent ops is not. New degrade/failover branches
must call ``record_fallback`` instead of inventing per-domain counters.

Contract fields (same mental model as desktop Swift/Rust emitters):
  component, from_mode, to_mode, reason, outcome
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Literal, TypedDict

from utils.metrics import OMI_FALLBACK_TOTAL

logger = logging.getLogger(__name__)

FallbackOutcome = Literal['recovered', 'degraded', 'exhausted']


@dataclass(frozen=True)
class ReplayLagDiagnostics:
    """Numeric snapshot at replay-ring overflow; never contains customer content."""

    capture_seconds: float
    admitted_seconds: float
    seconds_since_text: float
    posts_since_anchor: int
    empty_posts_since_anchor: int
    post_in_flight: bool
    empty_streak: int
    cut_pending: bool
    pacing_wait: bool

    def log_fields(self) -> str:
        # Bounds apply to log values, never metric labels. -1 means no text yet.
        def seconds(value: float) -> float:
            return min(86400.0, max(-1.0, value)) if math.isfinite(value) else -1.0

        def count(value: int) -> int:
            return min(1000000, max(0, value))

        return (
            f' un_emitted_capture_seconds={seconds(self.capture_seconds):.3f}'
            f' vad_admitted_seconds={seconds(self.admitted_seconds):.3f}'
            f' seconds_since_text={seconds(self.seconds_since_text):.3f}'
            f' posts_since_anchor={count(self.posts_since_anchor)}'
            f' empty_posts_since_anchor={count(self.empty_posts_since_anchor)}'
            f' post_in_flight={int(bool(self.post_in_flight))}'
            f' empty_streak={count(self.empty_streak)}'
            f' cut_pending={int(bool(self.cut_pending))}'
            f' pacing_wait={int(bool(self.pacing_wait))}'
        )


class CapacityFallbackKwargs(TypedDict, total=False):
    capacity_subtype: str
    replay_diagnostics: ReplayLagDiagnostics


def capacity_fallback_kwargs(
    subtype: str | None, diagnostics: ReplayLagDiagnostics | None = None
) -> CapacityFallbackKwargs:
    """Add capacity detail only when present; other fallback calls stay unchanged."""
    result: CapacityFallbackKwargs = {}
    if subtype is not None:
        result['capacity_subtype'] = subtype
    if diagnostics is not None:
        result['replay_diagnostics'] = diagnostics
    return result


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
        'last_resort',
        'connection_lost',
        'modulate_serve_error',
        'capability_mismatch',
        'auth',
        'quota',
        'local_heal',
        'policy',
        'dispatch_disabled',
        'byok',
        'malformed_doc',
        'capacity_full',
        'first_text_deadline',
        'empty_streak',
        'allocation_rejected',
        'private_tool_output_in_context',
        'not_authorized',
        'authorization_unavailable',
        'unmigrated_principal',
        'other',
        'none',
    }
)

# Diagnostic detail in the log only. The shared metric's reason vocabulary and
# label dimensions remain unchanged.
ALLOWED_CAPACITY_SUBTYPES = frozenset({'buffer_cap', 'span_cap', 'admission', 'replay_ring_cap'})

ALLOWED_COMPONENTS = frozenset(
    {
        'sync_dispatch',
        'pusher',
        'stt_selection',
        'stt_live_session',
        'vad',
        'audio_merge',
        'webhook',
        'realtime_hub',
        'ptt_cascade',
        'gemini_model',
        'gemini_proxy',
        'gemini_stream_proxy',
        'llm_gateway',
        'memory_analytics',
        'redis_ratelimit',
        'silent_mic',
        'firestore_read',
        'knowledge_graph',
        'agent_tools',
        'conversation_finalization',
        'conversation_notes',
        'daily_summary',
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
    capacity_subtype: str | None = None,
    replay_diagnostics: ReplayLagDiagnostics | None = None,
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
        fields = (FALLBACK_EVENT, component_label, from_label, to_label, reason_label, outcome_label)
        if reason_label == 'capacity_full':
            subtype = capacity_subtype if capacity_subtype in ALLOWED_CAPACITY_SUBTYPES else 'unknown'
            detail = (
                replay_diagnostics.log_fields()
                if subtype == 'replay_ring_cap' and replay_diagnostics is not None
                else ''
            )
            emit_log.warning(
                '%s component=%s from=%s to=%s reason=%s outcome=%s subtype=%s%s', *fields, subtype, detail
            )
        else:
            emit_log.warning('%s component=%s from=%s to=%s reason=%s outcome=%s', *fields)
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
