"""Conversation extraction adapter for the universal Candidate lifecycle.

Keeping this boundary out of the conversation coordinator prevents task persistence
details from leaking into the already broad processing module and gives legacy test
harnesses one stable dependency seam.
"""

from collections.abc import Callable, Sequence
from datetime import datetime
import logging
import os
from typing import Any

import database.action_items as action_items_db
import database.task_intelligence_control as task_control_db
from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope, TaskCreatePayload, TaskOwner
from models.candidate import CandidateAction
from utils.conversations.transcript_for_llm import (
    conversation_action_item_speaker_labels,
    conversation_transcript_for_action_items,
)
from utils.conversations.wake_word import find_wake_word_segment_ids
from utils.llm.usage_tracker import Features, track_usage
from utils.llm.wake_word_adjudication import (
    WakeWordAdjudication,
    adjudicate_wake_word_invocations,
)
from utils.metrics import TASK_INTELLIGENCE_ATTRIBUTION_TOTAL
from utils.task_intelligence import candidate_service
from utils.task_intelligence.backend_capture import adapt_backend_capture
from utils.task_intelligence.conversation_capture_policy import (
    WakeWordCaptureGate,
    capture_signals_for_action_item,
)

logger = logging.getLogger(__name__)

WakeWordAdjudicator = Callable[..., WakeWordAdjudication]
WAKE_WORD_ADJUDICATION_ENABLED_ENV = 'WAKE_WORD_ADJUDICATION_ENABLED'


def wake_word_adjudication_enabled() -> bool:
    """Return whether the LLM adjudicator may run.

    Default on preserves today's behaviour. An operator turns it off without a
    code deploy; the deterministic marker verdict then stands unchanged.
    """

    value = os.getenv(WAKE_WORD_ADJUDICATION_ENABLED_ENV)
    if value is None:
        return True
    return value.strip().casefold() in {'1', 'true', 'yes', 'on'}


def capture_enabled(uid: str) -> bool:
    """Return whether the universal Candidate capture path is available.

    The released helper name is retained for conversation coordinator
    compatibility. Authenticated ownership is checked by the route/store
    boundaries; memory enrollment is not consulted here.
    """

    return bool(uid)


def _record_wake_word_adjudication_outcomes(
    conversation_id: str,
    action_items: Sequence[Any],
    adjudication: WakeWordAdjudication,
) -> None:
    for invocation in adjudication.invocations:
        invocation_ids = set(invocation.segment_ids)
        if invocation.verdict == 'question':
            TASK_INTELLIGENCE_ATTRIBUTION_TOTAL.labels(
                event='wake_word_adjudication',
                subject_kind='conversation',
                code='question_descope',
            ).inc()
            logger.info(
                'wake-word question verdict intentionally not routed conversation_id=%s segment_count=%d',
                conversation_id,
                len(invocation_ids),
            )
        if invocation.verdict == 'task_command' and not any(
            invocation_ids.intersection(getattr(item, 'source_segment_ids', None) or []) for item in action_items
        ):
            TASK_INTELLIGENCE_ATTRIBUTION_TOTAL.labels(
                event='wake_word_adjudication',
                subject_kind='conversation',
                code='task_command_without_extraction',
            ).inc()
            logger.info(
                'wake-word task verdict had no intersecting extraction; no task created '
                'conversation_id=%s segment_count=%d',
                conversation_id,
                len(invocation_ids),
            )


def prepare_wake_word_capture_gate(
    uid: str,
    conversation: Any,
    people: Sequence[Any] = (),
    *,
    adjudicator: WakeWordAdjudicator = adjudicate_wake_word_invocations,
) -> WakeWordCaptureGate | None:
    """Run stage two exactly once when the deterministic matcher found an invocation."""

    transcript_segments = getattr(conversation, 'transcript_segments', ()) or ()
    matched_segment_ids = find_wake_word_segment_ids(transcript_segments)
    if not matched_segment_ids:
        return None
    if not wake_word_adjudication_enabled():
        logger.info('wake-word adjudication disabled; keeping deterministic marker verdicts')
        return None
    action_items = getattr(getattr(conversation, 'structured', None), 'action_items', ()) or ()
    marked_transcript = conversation_transcript_for_action_items(
        uid,
        conversation,
        list(people),
        mark_wake_words=True,
    )
    speaker_labels = conversation_action_item_speaker_labels(uid, conversation, list(people))
    with track_usage(uid, Features.WAKE_WORD_ADJUDICATION):
        adjudication = adjudicator(
            marked_transcript=marked_transcript,
            matched_segment_ids=matched_segment_ids,
            action_items=action_items,
            speaker_labels=speaker_labels,
            transcript_segments=transcript_segments,
        )
    _record_wake_word_adjudication_outcomes(conversation.id, action_items, adjudication)
    return WakeWordCaptureGate(
        matched_segment_ids=matched_segment_ids,
        adjudication=adjudication,
    )


def _evidence_seconds(value: Any) -> float | None:
    """Clamp a segment offset to the non-negative range EvidenceRef accepts.

    Segment offsets are relative to conversation start and audio-merge arithmetic
    lands them marginally below zero (-1e-07 is common, whole seconds happen when a
    synced file predates the conversation). Evidence offsets are absolute positions,
    so the floor is zero rather than a validation error.
    """

    if not isinstance(value, (int, float)):
        return None
    return max(0.0, float(value))


def _conversation_evidence_ref(
    action_item: Any,
    conversation_id: str,
    transcript_segments: Sequence[Any] = (),
) -> EvidenceRef:
    requested_ids = set(getattr(action_item, 'source_segment_ids', None) or [])
    supporting_segments = [segment for segment in transcript_segments if getattr(segment, 'id', None) in requested_ids]
    return EvidenceRef(
        kind=EvidenceKind.conversation,
        id=conversation_id,
        scope=EvidenceScope.canonical,
        transcript_segment_ids=[segment.id for segment in supporting_segments],
        start_seconds=_evidence_seconds(min((segment.start for segment in supporting_segments), default=None)),
        end_seconds=_evidence_seconds(max((segment.end for segment in supporting_segments), default=None)),
    )


def _capture_decision(
    action_item: Any,
    conversation_id: str,
    transcript_segments: Sequence[Any] = (),
    wake_word_gate: WakeWordCaptureGate | None = None,
):
    return adapt_backend_capture(
        TaskCreatePayload(
            description=action_item.description,
            owner=getattr(action_item, 'capture_owner', None) or TaskOwner.unknown,
            due_at=action_item.due_at,
            due_confidence=1.0 if action_item.due_at else None,
        ),
        evidence_ref=_conversation_evidence_ref(action_item, conversation_id, transcript_segments),
        source_surface='conversation',
        signals=capture_signals_for_action_item(action_item, wake_word_gate),
    )


def canonical_fields(
    action_item: Any,
    conversation_id: str,
    transcript_segments: Sequence[Any] = (),
) -> dict[str, Any]:
    return {
        'status': 'completed' if action_item.completed else 'active',
        'owner': getattr(action_item, 'capture_owner', None) or 'unknown',
        'due_confidence': 1.0 if action_item.due_at else None,
        'source': 'conversation',
        'provenance': [
            _conversation_evidence_ref(action_item, conversation_id, transcript_segments).model_dump(mode='python')
        ],
    }


def canonical_conversation_fields(action_item: Any, conversation: Any) -> dict[str, Any]:
    return canonical_fields(action_item, conversation.id, getattr(conversation, 'transcript_segments', ()) or ())


def process_before_legacy(
    uid: str,
    conversation_id: str,
    action_items: Sequence[Any],
    transcript_segments: Sequence[Any] = (),
    wake_word_gate: WakeWordCaptureGate | None = None,
) -> bool:
    """Capture every extracted item as a proposal the user must accept.

    INVARIANT I1: conversation extraction never writes an ``action_item``. Each
    item becomes a pending Candidate and reaches the task list only through an
    explicit "Add to Tasks" gesture.

    Policy rejection is handled per item, not per conversation. An item the
    policy ignores is simply not proposed; it no longer drags its siblings onto
    a writer that would bypass the user. This function therefore always reports
    that it handled the extraction.
    """

    control = task_control_db.get_task_workflow_control(uid)
    if not capture_enabled(uid):
        return False
    occurrences = _semantic_occurrences(action_items)
    decisions = [
        (
            action_item,
            semantic_key,
            occurrence,
            (
                _capture_decision(action_item, conversation_id, transcript_segments, wake_word_gate)
                if transcript_segments
                else _capture_decision(action_item, conversation_id, wake_word_gate=wake_word_gate)
            ),
        )
        for action_item, semantic_key, occurrence in occurrences
    ]
    for _, semantic_key, occurrence, decision in decisions:
        proposal = decision.candidate
        if proposal is None:
            # The policy ignored this item, or named an update target that no
            # longer resolves. Drop this item alone and keep proposing the rest.
            continue
        candidate_service.create_candidate(
            uid,
            proposal,
            idempotency_key=_idempotency_key(conversation_id, semantic_key, occurrence),
            account_generation=control.account_generation,
        )
    return True


def process_conversation_before_legacy(
    uid: str,
    conversation: Any,
    wake_word_gate: WakeWordCaptureGate | None = None,
) -> bool:
    return process_before_legacy(
        uid,
        conversation.id,
        conversation.structured.action_items,
        getattr(conversation, 'transcript_segments', ()) or (),
        wake_word_gate,
    )


def reconcile_after_legacy(
    uid: str,
    conversation_id: str,
    action_items: Sequence[Any],
    task_ids: Sequence[str],
) -> None:
    # Compatibility fallback writes complete action-item rows when the shared
    # policy intentionally rejects one extraction item. Do not synthesize a
    # partial Candidate sidecar after that writer.
    return None


def legacy_document_ids(uid: str, conversation_id: str, action_items: Sequence[Any]) -> list[str] | None:
    """Return order-independent write-mode IDs derived from each item's semantic content."""
    return None


def legacy_replacement_map(
    old_items: Sequence[dict[str, Any]],
    new_items: Sequence[Any],
    active_ids: Sequence[str],
) -> dict[str, str]:
    """Link only an extraction-provided update target; text similarity never establishes identity."""
    old_ids: set[str] = set()
    for item in old_items:
        item_id = item.get('id')
        if isinstance(item_id, str):
            old_ids.add(item_id)
    active_id_set = set(active_ids)
    retired_ids = sorted(old_ids - active_id_set)
    retired_id_set = set(retired_ids)
    replacements: dict[str, str] = {}
    for new_item, new_id in zip(new_items, active_ids):
        target_task_id = getattr(new_item, 'target_task_id', None)
        if (
            getattr(new_item, 'candidate_action', None) == 'update'
            and isinstance(target_task_id, str)
            and target_task_id in retired_id_set
        ):
            replacements[target_task_id] = new_id
    return replacements


def _semantic_key(action_item: Any) -> str:
    due_at = getattr(action_item, 'due_at', None)
    due_value = due_at.isoformat() if isinstance(due_at, datetime) else ''
    owner = getattr(action_item, 'capture_owner', None) or TaskOwner.unknown
    owner_value = owner.value if isinstance(owner, TaskOwner) else str(owner)
    parts = (
        action_items_db.normalize_action_item_description(action_item.description),
        owner_value,
        str(getattr(action_item, 'candidate_action', None) or CandidateAction.create.value),
        str(getattr(action_item, 'target_task_id', None) or ''),
        due_value,
    )
    return '\x1f'.join(parts)


def _semantic_occurrences(action_items: Sequence[Any]) -> list[tuple[Any, str, int]]:
    occurrences: dict[str, int] = {}
    result: list[tuple[Any, str, int]] = []
    for action_item in action_items:
        semantic_key = _semantic_key(action_item)
        occurrence = occurrences.get(semantic_key, 0)
        occurrences[semantic_key] = occurrence + 1
        result.append((action_item, semantic_key, occurrence))
    return result


def _idempotency_key(
    conversation_id: str,
    semantic_key: str,
    occurrence: int,
    *,
    purpose: str = 'capture',
) -> str:
    return f'conversation:{conversation_id}:item:{purpose}:{semantic_key}:{occurrence}'


__all__ = [
    'canonical_fields',
    'canonical_conversation_fields',
    'capture_enabled',
    'legacy_document_ids',
    'legacy_replacement_map',
    'process_before_legacy',
    'process_conversation_before_legacy',
    'prepare_wake_word_capture_gate',
    'reconcile_after_legacy',
    'wake_word_adjudication_enabled',
    'WAKE_WORD_ADJUDICATION_ENABLED_ENV',
]
