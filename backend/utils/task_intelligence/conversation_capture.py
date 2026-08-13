"""Conversation extraction adapter for the universal Candidate lifecycle.

Keeping this boundary out of the conversation coordinator prevents task persistence
details from leaking into the already broad processing module and gives legacy test
harnesses one stable dependency seam.
"""

from datetime import datetime
from typing import Any, Sequence

import database.action_items as action_items_db
import database.task_intelligence_control as task_control_db
from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope, TaskCreatePayload, TaskOwner
from models.candidate import CandidateAction
from utils.task_intelligence import candidate_service
from utils.task_intelligence.backend_capture import BackendCaptureSignals, adapt_backend_capture


def capture_enabled(uid: str) -> bool:
    """Return whether the universal Candidate capture path is available.

    The released helper name is retained for conversation coordinator
    compatibility. Authenticated ownership is checked by the route/store
    boundaries; memory enrollment is not consulted here.
    """

    return bool(uid)


def _concrete_deliverable(action_item: Any) -> bool:
    """Fail closed: only treat as concrete when extraction supplies an explicit True."""

    raw = getattr(action_item, 'concrete_deliverable', None)
    return raw is True


def _capture_signals(action_item: Any) -> BackendCaptureSignals:
    capture_kind = getattr(action_item, 'capture_kind', None)
    raw_candidate_action = getattr(action_item, 'candidate_action', None)
    candidate_action = raw_candidate_action if isinstance(raw_candidate_action, str) else 'create'
    raw_target_task_id = getattr(action_item, 'target_task_id', None)
    target_task_id = raw_target_task_id if isinstance(raw_target_task_id, str) else None
    raw_capture_confidence = getattr(action_item, 'capture_confidence', None)
    capture_confidence = float(raw_capture_confidence) if isinstance(raw_capture_confidence, (int, float)) else 0.5
    raw_ownership_confidence = getattr(action_item, 'ownership_confidence', None)
    ownership_confidence = (
        float(raw_ownership_confidence) if isinstance(raw_ownership_confidence, (int, float)) else 0.5
    )
    return BackendCaptureSignals(
        explicit_command=capture_kind == 'explicit_command',
        clear_commitment=capture_kind == 'clear_commitment',
        direct_request=capture_kind == 'direct_request' or capture_kind is None,
        inferred_next_step=capture_kind == 'inferred_next_step',
        concrete_deliverable=_concrete_deliverable(action_item),
        owner=getattr(action_item, 'capture_owner', None) or TaskOwner.unknown,
        already_done=candidate_action == 'complete',
        refines_task=target_task_id if candidate_action in {'update', 'complete'} else None,
        capture_confidence=capture_confidence,
        ownership_confidence=ownership_confidence,
    )


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
        start_seconds=min((segment.start for segment in supporting_segments), default=None),
        end_seconds=max((segment.end for segment in supporting_segments), default=None),
    )


def _capture_decision(
    action_item: Any,
    conversation_id: str,
    transcript_segments: Sequence[Any] = (),
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
        signals=_capture_signals(action_item),
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
) -> bool:
    """Capture proposals before the compatibility writer.

    A rejected policy result has no Candidate representation. In that case we
    explicitly return ``False`` before writing any other Candidate so the
    caller runs its existing action-item writer for the complete extraction.
    This is the no-drop fence: one ignored extraction item cannot make the
    whole conversation disappear or create a mixed duplicate write.
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
                _capture_decision(action_item, conversation_id, transcript_segments)
                if transcript_segments
                else _capture_decision(action_item, conversation_id)
            ),
        )
        for action_item, semantic_key, occurrence in occurrences
    ]
    if any(decision.candidate is None for _, _, _, decision in decisions):
        return False
    for _, semantic_key, occurrence, decision in decisions:
        proposal = decision.candidate
        assert proposal is not None, "candidate policy fence must run before writes"
        candidate = candidate_service.create_candidate(
            uid,
            proposal,
            idempotency_key=_idempotency_key(conversation_id, semantic_key, occurrence),
            account_generation=control.account_generation,
        )
        if decision.policy.outcome in {'auto_accept_silent', 'create_direct'}:
            candidate_service.accept_candidate(
                uid,
                candidate.candidate_id,
                account_generation=control.account_generation,
            )
    return True


def process_conversation_before_legacy(uid: str, conversation: Any) -> bool:
    return process_before_legacy(
        uid,
        conversation.id,
        conversation.structured.action_items,
        getattr(conversation, 'transcript_segments', ()) or (),
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
    'reconcile_after_legacy',
]
