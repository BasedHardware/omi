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
        'allocation_rejected',
        'private_tool_output_in_context',
        'not_authorized',
        'authorization_unavailable',
        'unmigrated_principal',
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
        'memory_analytics',
        'redis_ratelimit',
        'silent_mic',
        'firestore_read',
        'knowledge_graph',
        'agent_tools',
        'conversation_finalization',
        # Vector store (ADR-0033): an unconfigured store makes writes and deletes no-ops, and a capability
        # silently lost is the thing this counter exists for. Without the label it buckets to 'other'.
        'vector_store',
        # Object store (ADR-0032): an unset public endpoint makes every signed URL carry the internal host.
        'object_store',
        # Egress toward a third-party vendor, denied by posture (ADR-0057).
        'vendor_egress',
        # Push TRANSPORT selection (ADR-0011) — distinct from 'pusher', which is the websocket service.
        # utils/push/selector.py has recorded under this name since it was written, and it bucketed to
        # 'other': a push backend degraded by a typo, or by a declared UnifiedPush with no base URL, was
        # indistinguishable from every other unlabelled fallback (BACKLOG L18).
        'push',
        # The auth chain's single fail-open: the LOCAL_DEVELOPMENT uid-123 bypass (ADR-0034, BACKLOG L14).
        # 'auth' is also a REASON in this module; the two namespaces are separate and both are correct.
        'auth',
        # The document-store port itself (ADR-0015/0044): a guarantee the adapter could not give on this
        # deployment — today, a batch that could not run in one transaction because the server has none
        # (BACKLOG L25). Distinct from 'firestore_read', which is one backend's read path.
        'document_store',
        # Speaker identity (BACKLOG L20): the matcher unreachable, the batch diarizer failing, or an
        # enrolment that stored no embedding. All three keep the conversation — and lose WHO said it.
        'speaker',
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
