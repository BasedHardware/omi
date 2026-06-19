from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_memory_contracts import DurableMemoryPatch, deterministic_contract_id
from models.v17_memory_operations import MemoryOperation, MemoryOperationStatus, logical_payload_digest
from models.v17_product_memory import (
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    V17MemoryItem,
    new_memory_id,
)


class ApplyStatus(str, Enum):
    committed = "committed"
    idempotent_skip = "idempotent_skip"
    retryable_head_mismatch = "retryable_head_mismatch"
    generation_mismatch = "generation_mismatch"
    source_not_active = "source_not_active"
    payload_mismatch = "payload_mismatch"
    invalid_patch = "invalid_patch"


class MemoryOutboxEventType(str, Enum):
    projection_sync = "projection_sync"
    vector_sync = "vector_sync"
    export_sync = "export_sync"
    delete_sync = "delete_sync"


class MemoryOutboxStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    delivered = "delivered"
    retryable_failure = "retryable_failure"
    dead_letter = "dead_letter"


class MemoryControlState(BaseModel):
    uid: str
    head_commit_id: str
    account_generation: int
    source_generation: int
    commit_sequence: int = 0
    projection_watermark_commit_id: Optional[str] = None
    projection_watermark_sequence: int = 0
    vector_watermark_commit_id: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("uid", "head_commit_id")
    @classmethod
    def validate_required_nonblank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("required control fields must not be blank")
        return value

    @field_validator("account_generation", "source_generation", "commit_sequence", "projection_watermark_sequence")
    @classmethod
    def validate_nonnegative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("control counters must be nonnegative")
        return value

    def next_commit_id(self, operation_id: str) -> str:
        return (
            "commit_"
            + deterministic_contract_id(
                "v17-memory-commit",
                {
                    "uid": self.uid,
                    "head_commit_id": self.head_commit_id,
                    "operation_id": operation_id,
                    "commit_sequence": self.commit_sequence + 1,
                },
            )[:32]
        )

    def advance_head(self, commit_id: str) -> "MemoryControlState":
        if not commit_id or not commit_id.strip():
            raise ValueError("commit_id must not be blank")
        return self.model_copy(
            update={
                "head_commit_id": commit_id,
                "commit_sequence": self.commit_sequence + 1,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def advance_projection_watermark(self, event: "MemoryOutboxEvent") -> "MemoryControlState":
        if not event.commit_id or not event.commit_id.strip():
            raise ValueError("projection watermark commit_id must not be blank")
        if event.account_generation != self.account_generation:
            raise ValueError("projection watermark account_generation mismatch")
        if event.commit_sequence != self.projection_watermark_sequence + 1:
            raise ValueError("projection watermark cannot skip commits or move backwards")
        if self.projection_watermark_commit_id and event.parent_commit_id != self.projection_watermark_commit_id:
            raise ValueError("projection watermark parent chain mismatch")
        return self.model_copy(
            update={
                "projection_watermark_commit_id": event.commit_id,
                "projection_watermark_sequence": event.commit_sequence,
                "updated_at": datetime.now(timezone.utc),
            }
        )


class MemoryOutboxEvent(BaseModel):
    event_id: str
    uid: str
    event_type: MemoryOutboxEventType
    status: MemoryOutboxStatus = MemoryOutboxStatus.pending
    commit_id: str
    parent_commit_id: str
    commit_sequence: int
    memory_id: Optional[str] = None
    operation_id: str
    account_generation: int
    source_generation: int
    payload: Dict[str, Any] = Field(default_factory=dict)
    available_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attempt_count: int = 0

    @field_validator("event_id", "uid", "commit_id", "operation_id")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("outbox identifiers must not be blank")
        return value


def _event_id(event_type: MemoryOutboxEventType, commit_id: str, memory_id: Optional[str], operation_id: str) -> str:
    return (
        "evt_"
        + deterministic_contract_id(
            "v17-memory-outbox",
            {
                "event_type": event_type.value,
                "commit_id": commit_id,
                "memory_id": memory_id,
                "operation_id": operation_id,
            },
        )[:32]
    )


class ApplyResult(BaseModel):
    status: ApplyStatus
    control_state: MemoryControlState
    operation: MemoryOperation
    memory_items: List[V17MemoryItem] = Field(default_factory=list)
    outbox_events: List[MemoryOutboxEvent] = Field(default_factory=list)
    reason: Optional[str] = None


def _materialize_memory_item(
    *, uid: str, patch: DurableMemoryPatch, evidence: List[MemoryEvidence], commit_id: str, sequence: int
) -> V17MemoryItem:
    now = datetime.now(timezone.utc)
    return V17MemoryItem(
        memory_id=patch.target_memory_id or patch.new_memory_id or new_memory_id(),
        uid=uid,
        version=1,
        tier=MemoryTier.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=patch.memory_text,
        evidence=evidence,
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=now,
        updated_at=now,
        expires_at=None,
        ledger_commit_id=commit_id,
        ledger_sequence=sequence,
        item_revision=1,
        source_commit_id=commit_id,
        source_commit_sequence=sequence,
        content_hash=deterministic_contract_id(
            "v17-memory-content", {"content": patch.memory_text, "evidence_ids": patch.evidence_ids}
        ),
        account_generation=0,
    )


def _stale_operation(operation: MemoryOperation) -> MemoryOperation:
    data = operation.model_dump()
    data.update({"status": MemoryOperationStatus.stale_generation, "updated_at": datetime.now(timezone.utc)})
    return MemoryOperation(**data)


def _operation_digest_for_patch(patch: DurableMemoryPatch) -> str:
    return logical_payload_digest(
        {
            "decision": patch.decision.value,
            "memory_text": patch.memory_text,
            "target_memory_id": patch.target_memory_id,
            "result_status": patch.result_status.value,
            "supersedes": patch.supersedes,
        }
    )


def _barrier_outbox_events(
    *, operation: MemoryOperation, control_state: MemoryControlState, commit_id: str, sequence: int
) -> List[MemoryOutboxEvent]:
    return [
        MemoryOutboxEvent(
            event_id=_event_id(event_type, commit_id, None, operation.operation_id),
            uid=operation.uid,
            event_type=event_type,
            commit_id=commit_id,
            parent_commit_id=control_state.head_commit_id,
            commit_sequence=sequence,
            memory_id=None,
            operation_id=operation.operation_id,
            account_generation=control_state.account_generation,
            source_generation=control_state.source_generation,
            payload={"action": "barrier"},
        )
        for event_type in [MemoryOutboxEventType.projection_sync, MemoryOutboxEventType.vector_sync]
    ]


def apply_long_term_patch_transaction(
    *, control_state: MemoryControlState, operation: MemoryOperation, patch_payload: Dict[str, Any]
) -> ApplyResult:
    """Pure transaction skeleton for Milestone 3.

    Production Firestore integration must perform these reads/writes atomically:
    control head/generations, operation journal status, memory item mutation, and outbox append.
    """
    raw = dict(patch_payload)
    evidence = raw.pop("evidence", None) or [
        MemoryEvidence(
            evidence_id=evidence_id,
            source_type="unknown",
            source_id=f"source_for_{evidence_id}",
            source_version="unknown",
            artifact_preservation=ArtifactPreservationState.preserved,
        )
        for evidence_id in raw.get("evidence_ids", [])
    ]
    try:
        patch = DurableMemoryPatch(**raw)
    except Exception as exc:
        return ApplyResult(
            status=ApplyStatus.invalid_patch,
            control_state=control_state,
            operation=operation,
            reason=type(exc).__name__,
        )
    if _operation_digest_for_patch(patch) != operation.logical_payload_digest:
        return ApplyResult(
            status=ApplyStatus.payload_mismatch,
            control_state=control_state,
            operation=operation,
            reason="patch digest does not match operation logical payload digest",
        )
    if operation.status == MemoryOperationStatus.committed:
        return ApplyResult(status=ApplyStatus.idempotent_skip, control_state=control_state, operation=operation)
    if (
        operation.account_generation != control_state.account_generation
        or operation.source_generation != control_state.source_generation
    ):
        return ApplyResult(
            status=ApplyStatus.generation_mismatch,
            control_state=control_state,
            operation=_stale_operation(operation),
            reason="operation generation does not match control state",
        )
    if operation.observed_head_commit_id and operation.observed_head_commit_id != control_state.head_commit_id:
        return ApplyResult(
            status=ApplyStatus.retryable_head_mismatch,
            control_state=control_state,
            operation=operation,
            reason="observed head does not match current head",
        )

    if any(item.source_state != SourceState.active for item in evidence):
        return ApplyResult(
            status=ApplyStatus.source_not_active,
            control_state=control_state,
            operation=operation,
            reason="cannot apply memory patch from deleted/purged source evidence",
        )
    commit_id = control_state.next_commit_id(operation.operation_id)
    next_control = control_state.advance_head(commit_id)
    if patch.decision == "skip_duplicate" or patch.decision.value == "skip_duplicate":
        outbox_events = _barrier_outbox_events(
            operation=operation, control_state=control_state, commit_id=commit_id, sequence=next_control.commit_sequence
        )
        committed_operation = operation.mark_committed(
            commit_id,
            committed_sequence=next_control.commit_sequence,
            committed_memory_item_ids=[],
            committed_outbox_event_ids=[event.event_id for event in outbox_events],
        )
        return ApplyResult(
            status=ApplyStatus.committed,
            control_state=next_control,
            operation=committed_operation,
            memory_items=[],
            outbox_events=outbox_events,
        )
    memory_item = _materialize_memory_item(
        uid=operation.uid, patch=patch, evidence=evidence, commit_id=commit_id, sequence=next_control.commit_sequence
    )
    outbox_events = [
        MemoryOutboxEvent(
            event_id=_event_id(event_type, commit_id, memory_item.memory_id, operation.operation_id),
            uid=operation.uid,
            event_type=event_type,
            commit_id=commit_id,
            parent_commit_id=control_state.head_commit_id,
            commit_sequence=next_control.commit_sequence,
            memory_id=memory_item.memory_id,
            operation_id=operation.operation_id,
            account_generation=control_state.account_generation,
            source_generation=control_state.source_generation,
            payload={"memory_id": memory_item.memory_id, "tier": memory_item.tier.value, "action": "upsert"},
        )
        for event_type in [MemoryOutboxEventType.projection_sync, MemoryOutboxEventType.vector_sync]
    ]
    committed_operation = operation.mark_committed(
        commit_id,
        committed_sequence=next_control.commit_sequence,
        committed_memory_item_ids=[memory_item.memory_id],
        committed_outbox_event_ids=[event.event_id for event in outbox_events],
    )
    return ApplyResult(
        status=ApplyStatus.committed,
        control_state=next_control,
        operation=committed_operation,
        memory_items=[memory_item],
        outbox_events=outbox_events,
    )
