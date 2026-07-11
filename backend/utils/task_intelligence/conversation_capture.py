"""Conversation extraction adapter for the canonical Candidate lifecycle.

Keeping this boundary out of the conversation coordinator prevents task persistence
details from leaking into the already broad processing module and gives legacy test
harnesses one stable dependency seam.
"""

from datetime import datetime
from typing import Any, Sequence

import database.action_items as action_items_db
import database.candidates as candidates_db
import database.task_intelligence_control as task_control_db
from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope, TaskCreatePayload, TaskOwner
from models.candidate import CandidateAction, CandidateCreate, CandidateStatus
from models.task_intelligence import TaskWorkflowMode
from utils.task_intelligence import candidate_service
from utils.task_intelligence.backend_capture import BackendCaptureSignals, adapt_backend_capture


def capture_enabled(uid: str) -> bool:
    control = task_control_db.get_task_workflow_control(uid)
    return control.workflow_mode in {TaskWorkflowMode.shadow, TaskWorkflowMode.write, TaskWorkflowMode.read}


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


def _capture_decision(action_item: Any, conversation_id: str):
    return adapt_backend_capture(
        TaskCreatePayload(
            description=action_item.description,
            owner=getattr(action_item, 'capture_owner', None) or TaskOwner.unknown,
            due_at=action_item.due_at,
            due_confidence=1.0 if action_item.due_at else None,
        ),
        evidence_ref=EvidenceRef(
            kind=EvidenceKind.conversation,
            id=conversation_id,
            scope=EvidenceScope.canonical,
        ),
        source_surface='conversation',
        signals=_capture_signals(action_item),
    )


def canonical_fields(action_item: Any, conversation_id: str) -> dict[str, Any]:
    return {
        'status': 'completed' if action_item.completed else 'active',
        'owner': getattr(action_item, 'capture_owner', None) or 'unknown',
        'due_confidence': 1.0 if action_item.due_at else None,
        'source': 'conversation',
        'provenance': [
            EvidenceRef(
                kind=EvidenceKind.conversation,
                id=conversation_id,
                scope=EvidenceScope.canonical,
            ).model_dump(mode='python')
        ],
    }


def process_before_legacy(uid: str, conversation_id: str, action_items: Sequence[Any]) -> bool:
    """Capture proposals before the legacy writer; return true when legacy is bypassed."""
    control = task_control_db.get_task_workflow_control(uid)
    if control.workflow_mode == TaskWorkflowMode.read:
        for action_item, semantic_key, occurrence in _semantic_occurrences(action_items):
            decision = _capture_decision(action_item, conversation_id)
            if decision.candidate is None:
                continue
            candidate = candidate_service.create_candidate(
                uid,
                decision.candidate,
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
    if control.workflow_mode == TaskWorkflowMode.shadow:
        for action_item in action_items:
            _capture_decision(action_item, conversation_id)
    return False


def reconcile_after_legacy(
    uid: str,
    conversation_id: str,
    action_items: Sequence[Any],
    task_ids: Sequence[str],
) -> None:
    control = task_control_db.get_task_workflow_control(uid)
    if control.workflow_mode != TaskWorkflowMode.write:
        return
    semantic_items = _semantic_occurrences(action_items)
    for (action_item, semantic_key, occurrence), task_id in zip(semantic_items, task_ids):
        decision = _capture_decision(action_item, conversation_id)
        if decision.candidate is None:
            continue
        if decision.candidate.proposed_action != CandidateAction.create:
            candidate_service.create_candidate(
                uid,
                decision.candidate,
                idempotency_key=_idempotency_key(
                    conversation_id,
                    semantic_key,
                    occurrence,
                    purpose='judgment',
                ),
                account_generation=control.account_generation,
            )
        projection = _legacy_create_projection(decision.candidate, action_item)
        candidate = candidate_service.create_candidate(
            uid,
            projection,
            idempotency_key=_idempotency_key(
                conversation_id,
                semantic_key,
                occurrence,
                purpose='legacy_projection',
            ),
            account_generation=control.account_generation,
        )
        if candidate.status == CandidateStatus.pending:
            candidates_db.reconcile_migrated_candidate(
                uid,
                candidate.candidate_id,
                status=CandidateStatus.accepted,
                account_generation=control.account_generation,
                result_task_id=task_id,
                reason='legacy_write_projection',
            )


def legacy_document_ids(uid: str, conversation_id: str, action_items: Sequence[Any]) -> list[str] | None:
    """Return order-independent write-mode IDs derived from each item's semantic content."""
    control = task_control_db.get_task_workflow_control(uid)
    if control.workflow_mode != TaskWorkflowMode.write:
        return None
    task_ids: list[str] = []
    for _action_item, semantic_key, occurrence in _semantic_occurrences(action_items):
        task_ids.append(
            candidates_db.task_id_for_conversation_item(
                uid,
                control.account_generation,
                conversation_id,
                semantic_key,
                occurrence,
            )
        )
    return task_ids


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


def _legacy_create_projection(candidate: CandidateCreate, action_item: Any) -> CandidateCreate:
    return CandidateCreate.model_validate(
        {
            'subject_kind': 'task',
            'proposed_action': 'create',
            'task_change': {
                'description': action_item.description,
                'owner': getattr(action_item, 'capture_owner', None) or TaskOwner.unknown,
                'due_at': action_item.due_at,
                'due_confidence': 1.0 if action_item.due_at else None,
            },
            'capture_confidence': candidate.capture_confidence,
            'ownership_confidence': candidate.ownership_confidence,
            'goal_id': candidate.goal_id,
            'workstream_id': candidate.workstream_id,
            'evidence_refs': candidate.evidence_refs,
            'source_surface': 'conversation_legacy_projection',
        }
    )


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
    'capture_enabled',
    'legacy_document_ids',
    'legacy_replacement_map',
    'process_before_legacy',
    'reconcile_after_legacy',
]
