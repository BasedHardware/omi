"""Owner-scoped summary rows and transactional task-link projection.

Task/Candidate resolution owns the transaction. This module only reads the chosen
row and prepares its conversation patch; it never creates or accepts a task.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter, ValidationError

from database._client import get_firestore_client
from database.read_boundary import MalformedDocError, parse_payload_strict
from models.action_item import EvidenceRef, TaskCreatePayload
from models.candidate import CandidateCreate, SummaryTaskReference
from models.structured import ActionItem
from models.task_intelligence import StableId


class SummaryTaskNotFoundError(Exception):
    pass


class SummaryTaskConflictError(Exception):
    pass


@dataclass(frozen=True)
class SummaryTaskRow:
    reference: Any
    conversation_id: str
    structured: dict[str, Any]
    item: ActionItem
    index: int

    def linked_patch(self, task_id: str) -> dict[str, Any]:
        structured = deepcopy(self.structured)
        structured['action_items'][self.index]['target_task_id'] = task_id
        return {'structured': structured}

    def proposal(self) -> CandidateCreate:
        return parse_payload_strict(
            CandidateCreate,
            {
                'subject_kind': 'task',
                'proposed_action': 'create',
                'task_change': TaskCreatePayload(
                    description=self.item.description,
                    owner=self.item.capture_owner or 'unknown',
                    due_at=self.item.due_at,
                    due_confidence=1.0 if self.item.due_at else None,
                ),
                'capture_confidence': self.item.capture_confidence if self.item.capture_confidence is not None else 0.5,
                'ownership_confidence': (
                    self.item.ownership_confidence if self.item.ownership_confidence is not None else 0.5
                ),
                'source_surface': 'conversation',
                'evidence_refs': [
                    EvidenceRef(
                        kind='conversation',
                        scope='canonical',
                        id=self.conversation_id,
                        transcript_segment_ids=self.item.source_segment_ids,
                    )
                ],
            },
            document_path=f'conversations/{self.conversation_id}/structured/action_items/{self.index}',
        )


def read_summary_task_row(
    uid: str,
    selected: SummaryTaskReference,
    *,
    transaction: Any = None,
    firestore_client: Any = None,
) -> SummaryTaskRow:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(selected.conversation_id)
    snapshot = ref.get(transaction=transaction)
    data = snapshot.to_dict() if snapshot.exists else None
    if not data or data.get('deleted'):
        raise SummaryTaskNotFoundError('Conversation not found')
    if data.get('is_locked'):
        raise SummaryTaskConflictError('Conversation is locked')
    structured = data.get('structured')
    items = structured.get('action_items') if isinstance(structured, dict) else None
    if not isinstance(items, list) or selected.action_item_index >= len(items):
        raise SummaryTaskNotFoundError('Summary action item not found')
    raw_item = items[selected.action_item_index]
    if not isinstance(raw_item, dict) or raw_item.get('deleted'):
        raise SummaryTaskNotFoundError('Summary action item not found')
    try:
        item = parse_payload_strict(
            ActionItem,
            raw_item,
            document_path=f'conversations/{selected.conversation_id}/structured/action_items/{selected.action_item_index}',
        )
    except MalformedDocError as exc:
        raise SummaryTaskConflictError('Summary action item is unavailable; refresh the conversation') from exc
    if item.description != selected.expected_description:
        raise SummaryTaskConflictError('Summary action item changed; refresh the conversation')
    if item.completed and not item.target_task_id:
        raise SummaryTaskConflictError('Summary action item is already completed')
    if item.candidate_action in {'update', 'complete'} and not item.target_task_id:
        raise SummaryTaskConflictError('Summary action item does not create a task')
    if item.due_at is not None and item.due_at.tzinfo is None:
        raise SummaryTaskConflictError('Summary action item has an invalid due date')
    row = SummaryTaskRow(ref, selected.conversation_id, structured, item, selected.action_item_index)
    try:
        if item.target_task_id is not None:
            TypeAdapter(StableId).validate_python(item.target_task_id)
        row.proposal()
    except (ValidationError, MalformedDocError) as exc:
        raise SummaryTaskConflictError('Summary action item is unavailable; refresh the conversation') from exc
    return row
