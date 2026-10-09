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
from utils.observability.routing_cohort import current_routing_cohort
from utils.stt.live_reason import LIVE_STT_REASONS

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


@dataclass(frozen=True)
class FirstTextDeadlineDiagnostics:
    """Immutable numeric startup state before cancellation clears the window."""

    admitted_seconds: float
    posts: int
    empty_posts: int
    answered_empty_stranded_flushes: int
    seconds_since_first_speech: float
    episode_admitted_seconds: float
    seconds_since_deadline_speech: float
    answered_empty_admitted_seconds: float

    def log_fields(self) -> str:
        def seconds(value: float) -> float:
            return min(86400.0, max(0.0, value)) if math.isfinite(value) else -1.0

        def count(value: int) -> int:
            return min(1000000, max(0, value))

        return (
            f' vad_admitted_seconds={seconds(self.admitted_seconds):.3f}'
            f' posts={count(self.posts)}'
            f' empty_posts={count(self.empty_posts)}'
            f' answered_empty_stranded_flushes={count(self.answered_empty_stranded_flushes)}'
            f' seconds_since_first_speech={seconds(self.seconds_since_first_speech):.3f}'
            f' episode_admitted_seconds={seconds(self.episode_admitted_seconds):.3f}'
            f' seconds_since_deadline_speech={seconds(self.seconds_since_deadline_speech):.3f}'
            f' answered_empty_admitted_seconds={seconds(self.answered_empty_admitted_seconds):.3f}'
        )


class FirstTextFallbackKwargs(TypedDict, total=False):
    first_text_diagnostics: FirstTextDeadlineDiagnostics


def first_text_fallback_kwargs(diagnostics: FirstTextDeadlineDiagnostics | None) -> FirstTextFallbackKwargs:
    return {} if diagnostics is None else {'first_text_diagnostics': diagnostics}


class CapacityFallbackKwargs(TypedDict, total=False):
    capacity_subtype: str
    replay_diagnostics: ReplayLagDiagnostics


class FailureFallbackKwargs(TypedDict, total=False):
    failure_subtype: str


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

ALLOWED_REASONS = LIVE_STT_REASONS | frozenset(
    {
        'gate_unavailable',
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

# Diagnostic detail stays in the log; metric dimensions stay fixed and live
# STT reasons share the bounded vocabulary used by cost health.
ALLOWED_CAPACITY_SUBTYPES = frozenset({'buffer_cap', 'span_cap', 'admission', 'replay_ring_cap', 'queue_timeout'})
ALLOWED_STT_FAILURE_SUBTYPES = frozenset(
    {
        'initialization_failed',
        'connection_lost',
        'send_failed',
        'socket_unavailable',
        'modulate_serve_error',
        'provider_rate_limited',
        'soniox_idle_timeout',
        'soniox_request_timeout',
        'soniox_rotation',
        'provider_5xx',
        'capacity_full',
        'first_text_deadline',
        'empty_streak',
        'soniox_invalid_hint',
        'untyped',
    }
)

ALLOWED_COMPONENTS = frozenset(
    {
        'screen_task_gate',
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
    first_text_diagnostics: FirstTextDeadlineDiagnostics | None = None,
    failure_subtype: str | None = None,
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

    cohort = current_routing_cohort.get()
    if cohort is not None and component_label in {'stt_selection', 'stt_live_session'} and outcome_label == 'exhausted':
        cohort.exhausted = True

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
        elif reason_label == 'first_text_deadline' and first_text_diagnostics is not None:
            emit_log.warning(
                '%s component=%s from=%s to=%s reason=%s outcome=%s%s',
                *fields,
                first_text_diagnostics.log_fields(),
            )
        elif reason_label == 'other' and failure_subtype is not None:
            subtype = failure_subtype if failure_subtype in ALLOWED_STT_FAILURE_SUBTYPES else 'unknown'
            emit_log.warning('%s component=%s from=%s to=%s reason=%s outcome=%s subtype=%s', *fields, subtype)
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


def initialize_live_stt_exhausted_children() -> None:
    """Expose zero before the first burst so increase() can observe it."""
    providers = ('parakeet', 'modulate', 'soniox', 'deepgram')
    reasons = LIVE_STT_REASONS | {'auth', 'quota', 'last_resort', 'config_incomplete'}
    for reason in sorted(reasons):
        for provider in providers:
            for replacement in providers:
                OMI_FALLBACK_TOTAL.labels(
                    component='stt_live_session',
                    from_mode=provider,
                    to_mode=replacement,
                    reason=reason,
                    outcome='exhausted',
                )
            OMI_FALLBACK_TOTAL.labels(
                component='stt_live_session',
                from_mode=provider,
                to_mode='unavailable',
                reason=reason,
                outcome='exhausted',
            )
            OMI_FALLBACK_TOTAL.labels(
                component='stt_selection',
                from_mode=provider,
                to_mode='unavailable',
                reason=reason,
                outcome='exhausted',
            )


initialize_live_stt_exhausted_children()
