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
from utils.observability.demand_cohort import record_metric
from utils.observability.demand_cohort import DEMAND_COHORTS, FAILURE_DETAIL, current_demand
from utils.observability.routing_cohort import current_routing_cohort
from utils.observability.reasons import FallbackReason, LiveSttReason, reason_values
from utils.stt.failure_diagnostics import CONNECTION_LOSS_CAUSES

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
    # Non-window (Soniox/Modulate) replacement legs have no POST state; they
    # report why emitted text did not reach their VAD speech instead.
    leg: Literal['window', 'nonwindow'] = 'window'
    speech_unemitted_seconds: float = -1.0
    text_segments: int = 0
    placed_text_segments: int = 0
    provider_output_pending: bool | None = None

    def log_fields(self) -> str:
        # Bounds apply to log values, never metric labels. -1 means no text yet.
        def seconds(value: float) -> float:
            return min(86400.0, max(-1.0, value)) if math.isfinite(value) else -1.0

        def count(value: int) -> int:
            return min(1000000, max(0, value))

        fields = (
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
        if self.leg != 'nonwindow':
            return fields
        pending = -1 if self.provider_output_pending is None else int(self.provider_output_pending)
        return (
            fields + ' leg=nonwindow'
            f' speech_unemitted_seconds={seconds(self.speech_unemitted_seconds):.3f}'
            f' text_segments={count(self.text_segments)}'
            f' placed_text_segments={count(self.placed_text_segments)}'
            f' provider_output_pending={pending}'
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

ALLOWED_REASONS = reason_values(FallbackReason)

# Diagnostic detail stays in the log; metric dimensions stay fixed and live
# STT reasons share the bounded vocabulary used by cost health.
ALLOWED_CAPACITY_SUBTYPES = frozenset({'buffer_cap', 'span_cap', 'admission', 'queue_timeout'})
# Bounded ramp-watch reasons with their own failure-detail series. The local
# delivery deaths (send_queue_full / replay_send_stalled / delivery_expired)
# carry their own series instead of hiding inside capacity_full.
FAILURE_DETAIL_REASONS = frozenset(
    {
        'first_text_deadline',
        'capacity_full',
        'replay_ring_overflow',
        'gate_unavailable',
        'send_queue_full',
        'replay_send_stalled',
        'delivery_expired',
    }
)
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
        'usage_publication',
        'knowledge_graph',
        'agent_tools',
        'conversation_relevance',
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
    demand_cohort: str | None = None,
    connection_cause: str | None = None,
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

    try:
        demand = current_demand.get()
        if component_label in {'stt_selection', 'stt_live_session'} and (
            demand is not None or demand_cohort is not None
        ):
            if demand is not None and outcome_label == 'exhausted':
                demand.exhausted = True
            # An explicit cohort (the gate runs in a spawned task) beats the context var.
            detail_cohort = (
                demand_cohort
                if demand_cohort in DEMAND_COHORTS
                else (demand.cohort if demand is not None else 'ineligible')
            )
            record_metric(
                FAILURE_DETAIL,
                {
                    'demand_cohort': detail_cohort,
                    'reason': reason_label if reason_label in FAILURE_DETAIL_REASONS else 'other',
                    'capacity_subtype': (
                        (capacity_subtype if capacity_subtype in ALLOWED_CAPACITY_SUBTYPES else 'unknown')
                        if reason_label == 'capacity_full'
                        else 'none'
                    ),
                    'outcome': outcome_label,
                },
                1,
            )
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
            emit_log.warning('%s component=%s from=%s to=%s reason=%s outcome=%s subtype=%s', *fields, subtype)
        elif reason_label == 'replay_ring_overflow' and replay_diagnostics is not None:
            emit_log.warning(
                '%s component=%s from=%s to=%s reason=%s outcome=%s%s', *fields, replay_diagnostics.log_fields()
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
        elif reason_label == 'connection_lost' and connection_cause is not None:
            # Log-only: the untyped connection_lost bucket gains its transport cause.
            cause = connection_cause if connection_cause in CONNECTION_LOSS_CAUSES else 'other'
            emit_log.warning('%s component=%s from=%s to=%s reason=%s outcome=%s cause=%s', *fields, cause)
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
    """Expose zero before the first burst so increase() can observe it.

    The full provider x replacement x reason matrix is deliberate: increase()
    cannot observe a one-off burst on a lazily created counter (its first sample
    already holds the burst, and the flat tail reads as zero), and the
    retired-provider and capacity_full-by-to_mode alerts select across the whole
    from x to x reason product over 6h windows. Each series costs one entry per
    listen/pusher/gateway pod and per Cloud Run instance, so shrink this only by
    shrinking the reason vocabulary itself, never by dropping combinations.

    'text' and 'no_text' are transcript-outcome tokens, never fallback reasons,
    so they stay out of the baseline (they were silently adding 2 x 24 series
    per emitter).
    """
    providers = ('parakeet', 'modulate', 'soniox', 'deepgram')
    # Built from the enum, not utils.stt.live_reason: live_reason imports utils.observability.reasons,
    # whose package import loads this module (and runs this at import), so importing it here cycles
    # when live_reason loads first (#23074's provider_resilience does). Same set as
    # live_reason.LIVE_STT_FAILURE_REASONS.
    live_failures = reason_values(LiveSttReason) - {'text', 'no_text'}
    reasons = live_failures | {'auth', 'quota', 'last_resort', 'config_incomplete'}
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
    # Undialed selection origins report their skip (live_chain.note_skip).
    for skip in ('session_excluded', 'recovery_budget', 'circuit_open', 'policy', 'unconfigured'):
        for provider in providers:
            OMI_FALLBACK_TOTAL.labels(
                component='stt_selection',
                from_mode=provider,
                to_mode='unavailable',
                reason=skip,
                outcome='exhausted',
            )


def initialize_cache_write_fail_open_children() -> None:
    """Expose zero before the first Redis cache-write fail-open so increase() can see it."""
    for reason in ('capacity_full', 'auth_error', 'connection_error', 'timeout'):
        OMI_FALLBACK_TOTAL.labels(
            component='other',
            from_mode='cache_write',
            to_mode='skip',
            reason=reason,
            outcome='degraded',
        )


initialize_live_stt_exhausted_children()
initialize_cache_write_fail_open_children()
