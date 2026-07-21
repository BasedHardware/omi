from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_admission import valid_required_processing_receipt
from models.memory_contracts import (
    DurableMemoryPatch,
    DurablePatchDecision,
    LifecycleState,
    deterministic_contract_id,
)
from models.memory_operations import MemoryOperation, MemoryOperationStatus, logical_payload_digest
from models.memory_domain import (
    MemoryLayer,
    MemoryProcessingState,
    assert_legal_state,
    physical_status_to_record_status,
)
from models.product_memory import (
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    MemoryItem,
)
from utils.memory.short_term_lifecycle import default_short_term_expiry

logger = logging.getLogger(__name__)


class ApplyStatus(str, Enum):
    committed = "committed"
    idempotent_skip = "idempotent_skip"
    retryable_head_mismatch = "retryable_head_mismatch"
    generation_mismatch = "generation_mismatch"
    source_not_active = "source_not_active"
    target_not_active = "target_not_active"
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
    last_promotion_run_at: Optional[datetime] = None
    last_consolidation_run_at: Optional[datetime] = None
    legacy_backfill_processed_count: int = 0
    legacy_backfill_source_fingerprint: Optional[str] = None
    legacy_backfill_completed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("uid", "head_commit_id")
    @classmethod
    def validate_required_nonblank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("required control fields must not be blank")
        return value

    @field_validator(
        "account_generation",
        "source_generation",
        "commit_sequence",
        "projection_watermark_sequence",
        "legacy_backfill_processed_count",
    )
    @classmethod
    def validate_nonnegative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("control counters must be nonnegative")
        return value

    @field_validator("last_promotion_run_at", "last_consolidation_run_at", "legacy_backfill_completed_at", "updated_at")
    @classmethod
    def coerce_timezone_aware(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def next_commit_id(self, operation_id: str) -> str:
        return (
            "commit_"
            + deterministic_contract_id(
                "memory-commit",
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
            "memory-outbox",
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
    memory_items: List[MemoryItem] = Field(default_factory=list)
    outbox_events: List[MemoryOutboxEvent] = Field(default_factory=list)
    reason: Optional[str] = None


def _deterministic_materialized_memory_id(*, uid: str, patch: DurableMemoryPatch, commit_id: str) -> str:
    if patch.target_memory_id:
        return patch.target_memory_id
    if patch.new_memory_id:
        return patch.new_memory_id
    return (
        "mem_"
        + deterministic_contract_id(
            "memory-materialized-item",
            {
                "uid": uid,
                "commit_id": commit_id,
                "patch_id": patch.patch_id,
                "idempotency_key": patch.idempotency_key,
            },
        )[:32]
    )


def _processing_state_for_promotion(
    promotion: Optional[Dict[str, Any]],
    *,
    fallback: ProcessingState,
) -> ProcessingState:
    processing_status = str((promotion or {}).get("processing_status") or "")
    if processing_status in {"pending_processing", "processing_failed_retryable", "pending_admission"}:
        return ProcessingState.pending
    if processing_status == "processed":
        return ProcessingState.processed
    return fallback


def _materialize_memory_item(
    *,
    uid: str,
    patch: DurableMemoryPatch,
    evidence: List[MemoryEvidence],
    commit_id: str,
    sequence: int,
    account_generation: int,
    promotion: Optional[Dict[str, Any]] = None,
) -> MemoryItem:
    now = datetime.now(timezone.utc)
    tier = patch.initial_tier
    expires_at = default_short_term_expiry(now) if tier == MemoryTier.short_term else None
    status = MemoryItemStatus.active
    processing_state = _processing_state_for_promotion(promotion, fallback=ProcessingState.processed)
    assert_legal_state(
        MemoryLayer(tier.value),
        physical_status_to_record_status(status.value),
        MemoryProcessingState(processing_state.value),
    )
    return MemoryItem(
        memory_id=_deterministic_materialized_memory_id(uid=uid, patch=patch, commit_id=commit_id),
        uid=uid,
        version=1,
        tier=tier,
        status=status,
        processing_state=processing_state,
        content=patch.memory_text,
        evidence=evidence,
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility=patch.visibility or "private",
        user_asserted=bool(patch.user_asserted),
        captured_at=now,
        updated_at=now,
        expires_at=expires_at,
        ledger_commit_id=commit_id,
        ledger_sequence=sequence,
        item_revision=1,
        source_commit_id=commit_id,
        source_commit_sequence=sequence,
        content_hash=deterministic_contract_id(
            "memory-content", {"content": patch.memory_text, "evidence_ids": patch.evidence_ids}
        ),
        account_generation=account_generation,
        promotion=promotion,
        subject_entity_id=patch.subject_entity_id,
        predicate=patch.predicate,
        arguments=dict(patch.arguments or {}),
    )


def _resolved_update_content(existing: MemoryItem, patch: DurableMemoryPatch) -> Optional[str]:
    """Preserve existing content when patch omits or blanks memory_text."""
    if patch.memory_text is not None and patch.memory_text.strip():
        return patch.memory_text
    return existing.content


def _apply_update_memory_item(
    *,
    existing: MemoryItem,
    patch: DurableMemoryPatch,
    evidence: List[MemoryEvidence],
    commit_id: str,
    sequence: int,
    promotion_audit: Optional[Dict[str, Any]] = None,
    extra_updates: Optional[Dict[str, Any]] = None,
) -> MemoryItem:
    now = max(datetime.now(timezone.utc), existing.captured_at, existing.updated_at)
    if patch.target_tier is not None:
        tier = patch.target_tier
    else:
        tier = existing.tier
    content = _resolved_update_content(existing, patch)
    status = existing.status
    if patch.result_status in {LifecycleState.hidden, LifecycleState.rejected}:
        status = MemoryItemStatus.hidden
    elif patch.result_status == LifecycleState.superseded:
        status = MemoryItemStatus.superseded
    elif patch.result_status == LifecycleState.active:
        status = MemoryItemStatus.active

    if tier == MemoryTier.short_term:
        expires_at = (
            existing.expires_at if existing.expires_at is not None else default_short_term_expiry(existing.captured_at)
        )
    else:
        expires_at = None
    processing_state = _processing_state_for_promotion(
        promotion_audit,
        fallback=existing.processing_state,
    )
    if tier == MemoryTier.long_term:
        processing_state = ProcessingState.processed
    assert_legal_state(
        MemoryLayer(tier.value),
        physical_status_to_record_status(status.value),
        MemoryProcessingState(processing_state.value),
    )
    updates: Dict[str, Any] = {
        "tier": tier,
        "status": status,
        "processing_state": processing_state,
        "content": content,
        "evidence": evidence or existing.evidence,
        "updated_at": now,
        "expires_at": expires_at,
        "ledger_commit_id": commit_id,
        "ledger_sequence": sequence,
        "version": existing.version + 1,
        "item_revision": existing.item_revision + 1,
    }
    if patch.memory_text is not None and patch.memory_text.strip():
        updates["content_hash"] = deterministic_contract_id(
            "memory-content",
            {
                "content": patch.memory_text,
                "evidence_ids": [item.evidence_id for item in (evidence or existing.evidence)],
            },
        )
    if promotion_audit is not None:
        updates["promotion"] = promotion_audit
    if patch.subject_entity_id is not None:
        updates["subject_entity_id"] = patch.subject_entity_id
    if patch.predicate is not None:
        updates["predicate"] = patch.predicate
    if patch.arguments:
        updates["arguments"] = dict(patch.arguments)
    if extra_updates:
        updates.update(extra_updates)
    return existing.model_copy(update=updates)


def _stale_operation(operation: MemoryOperation) -> MemoryOperation:
    data = operation.dict()
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


def _coerce_iso_timestamp(value: str, *, field: str) -> Optional[datetime]:
    """Parse a stored ISO timestamp string, tolerating a trailing 'Z'.

    Returns None on a malformed value so the caller can drop just that one field instead of
    letting a single drifted string abort the whole patch. Logs the field name only, never the
    raw value, which can carry memory text.
    """
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Dropping malformed timestamp field %s in long-term memory patch", field)
        return None


def apply_long_term_patch_transaction(
    *, control_state: MemoryControlState, operation: MemoryOperation, patch_payload: Dict[str, Any]
) -> ApplyResult:
    """Pure transaction skeleton for Milestone 3.

    Production Firestore integration must perform these reads/writes atomically:
    control head/generations, operation journal status, memory item mutation, and outbox append.
    """
    raw = dict(patch_payload)
    existing_item_raw = raw.pop("existing_item", None)
    promotion_audit = raw.pop("promotion_audit", None)
    promotion_metadata = raw.pop("promotion", None)
    expected_item_revision = raw.pop("expected_item_revision", None)
    expected_content_hash = raw.pop("expected_content_hash", None)
    extra_item_updates: Dict[str, Any] = {}
    for optional_key in (
        "corroboration_count",
        "last_corroborated_at",
        "captured_at",
        "updated_at",
        "expires_at",
        "superseded_by",
        "kg_extracted",
        "confidence",
        "sensitivity_labels",
    ):
        if optional_key in raw:
            extra_item_updates[optional_key] = raw.pop(optional_key)
    for timestamp_key in ("last_corroborated_at", "captured_at", "updated_at", "expires_at"):
        if timestamp_key in extra_item_updates and isinstance(extra_item_updates[timestamp_key], str):
            coerced = _coerce_iso_timestamp(extra_item_updates[timestamp_key], field=timestamp_key)
            if coerced is None:
                # Drop just the malformed field; the item keeps its existing (update path) or
                # materialized (create path) value instead of the whole patch raising ValueError.
                extra_item_updates.pop(timestamp_key)
            else:
                extra_item_updates[timestamp_key] = coerced
    if (
        "confidence" in extra_item_updates
        and extra_item_updates["confidence"] is not None
        and not isinstance(extra_item_updates["confidence"], (int, float))
    ):
        extra_item_updates.pop("confidence")
    evidence = raw.pop("evidence", None) or [
        MemoryEvidence(
            evidence_id=evidence_id,
            source_type="unknown",
            source_id=f"source_for_{evidence_id}",
            source_version="unknown",
            artifact_preservation=ArtifactPreservationState.preserved,
        )
        for evidence_id in (raw.get("evidence_ids") or [])
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
    if patch.decision == DurablePatchDecision.update:
        if existing_item_raw is None:
            return ApplyResult(
                status=ApplyStatus.invalid_patch,
                control_state=control_state,
                operation=operation,
                reason="update patch requires authoritative existing_item",
            )
        existing_item = (
            existing_item_raw if isinstance(existing_item_raw, MemoryItem) else MemoryItem(**existing_item_raw)
        )
        if not patch.target_memory_id or existing_item.memory_id != patch.target_memory_id:
            return ApplyResult(
                status=ApplyStatus.invalid_patch,
                control_state=control_state,
                operation=operation,
                reason="update patch target_memory_id mismatch",
            )
        if expected_item_revision is not None and existing_item.item_revision != expected_item_revision:
            return ApplyResult(
                status=ApplyStatus.invalid_patch,
                control_state=control_state,
                operation=operation,
                reason="update patch expected_item_revision mismatch",
            )
        if expected_content_hash is not None and existing_item.content_hash != expected_content_hash:
            return ApplyResult(
                status=ApplyStatus.invalid_patch,
                control_state=control_state,
                operation=operation,
                reason="update patch expected_content_hash mismatch",
            )
        if patch.target_tier == MemoryTier.long_term:
            admission_metadata = promotion_audit if isinstance(promotion_audit, dict) else existing_item.promotion or {}
            proposed_content = _resolved_update_content(existing_item, patch) or ""
            if admission_metadata.get("required") and not valid_required_processing_receipt(
                content=proposed_content,
                item_revision=existing_item.item_revision,
                promotion=admission_metadata,
            ):
                return ApplyResult(
                    status=ApplyStatus.invalid_patch,
                    control_state=control_state,
                    operation=operation,
                    reason="required durable memory is missing processing receipt",
                )
        memory_item = _apply_update_memory_item(
            existing=existing_item,
            patch=patch,
            evidence=evidence,
            commit_id=commit_id,
            sequence=next_control.commit_sequence,
            promotion_audit=promotion_audit,
            extra_updates=extra_item_updates or None,
        )
    else:
        memory_item = _materialize_memory_item(
            uid=operation.uid,
            patch=patch,
            evidence=evidence,
            commit_id=commit_id,
            sequence=next_control.commit_sequence,
            account_generation=control_state.account_generation,
            promotion=promotion_metadata,
        )
        if extra_item_updates:
            memory_item = MemoryItem(**{**memory_item.dict(), **extra_item_updates})
    outbox_events = []
    if (
        memory_item.processing_state == ProcessingState.processed
        and (memory_item.promotion or {}).get("user_review") is not False
    ):
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


__all__ = [
    "ApplyResult",
    "ApplyStatus",
    "MemoryControlState",
    "MemoryOutboxEvent",
    "MemoryOutboxEventType",
    "MemoryOutboxStatus",
    "apply_long_term_patch_transaction",
]
