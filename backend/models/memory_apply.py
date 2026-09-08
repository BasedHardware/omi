from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_admission import valid_required_processing_receipt
from models.memory_contracts import (
    DurableMemoryPatch,
    DurablePatchDecision,
    LifecycleState,
    deterministic_contract_id,
)
from models.memory_operations import MemoryOperation, MemoryOperationStatus, MemoryOperationType, logical_payload_digest
from models.memory_promotion import (
    MemoryGraphAssertion,
    PromotionGraphPlan,
    build_memory_graph_assertion,
    valid_promotion_admission,
)
from models.memory_domain import (
    MemoryLayer,
    MemoryProcessingState,
    assert_legal_state,
    physical_status_to_record_status,
)
from models.product_memory import (
    RESTRICTED_SENSITIVITY_LABELS,
    MemoryItem,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    normalized_memory_content_key,
)
from utils.memory.short_term_lifecycle import default_short_term_expiry

logger = logging.getLogger(__name__)
_GRAPH_PREDICATE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

_PATCH_MUTATION_IDENTITY_EXCLUDED_KEYS = {
    "schema_version",
    "patch_id",
    "packet_id",
    "run_id",
    "observed_head_commit_id",
    "idempotency_key",
    "decision",
    "result_status",
    "target_memory_id",
    "memory_text",
    "supersedes",
    "existing_item",
    "superseded_items",
    "evidence",
    "mutation_metadata",
}


class ApplyStatus(str, Enum):
    committed = "committed"
    idempotent_skip = "idempotent_skip"
    retryable_head_mismatch = "retryable_head_mismatch"
    generation_mismatch = "generation_mismatch"
    source_not_active = "source_not_active"
    target_not_active = "target_not_active"
    payload_mismatch = "payload_mismatch"
    invalid_patch = "invalid_patch"


class WriterMode(str, Enum):
    """Authoritative memory-writer state for one user.

    Transition modes are deliberate stop-the-world fences for ordinary memory
    writers.  Account deletion and privacy enforcement are separate
    authorities and must not be routed through this admission state.
    """

    compatibility = "compatibility"
    transitioning_to_ledger = "transitioning_to_ledger"
    ledger = "ledger"
    transitioning_to_compatibility = "transitioning_to_compatibility"


class MemoryWriterClass(str, Enum):
    compatibility = "compatibility"
    ledger = "ledger"
    user = "user"


class WriterAdmissionError(RuntimeError):
    """The requested writer class is not admitted by the current control mode."""


def require_writer_admitted(
    control: "MemoryControlState",
    writer_class: MemoryWriterClass,
    *,
    allow_ledger_migration: bool = False,
) -> None:
    """Raise unless the writer owns the stable mode or explicit migration seam."""
    try:
        requested = MemoryWriterClass(writer_class)
    except ValueError as exc:
        raise WriterAdmissionError("unknown memory writer class") from exc

    if requested == MemoryWriterClass.user and control.writer_mode in {
        WriterMode.compatibility,
        WriterMode.ledger,
    }:
        return
    if control.writer_mode == WriterMode.compatibility:
        if requested == MemoryWriterClass.compatibility:
            return
        if requested == MemoryWriterClass.ledger and allow_ledger_migration:
            return
    elif control.writer_mode == WriterMode.ledger and requested == MemoryWriterClass.ledger:
        return
    elif (
        control.writer_mode == WriterMode.transitioning_to_ledger
        and requested == MemoryWriterClass.ledger
        and allow_ledger_migration
    ):
        return
    raise WriterAdmissionError(
        f"{requested.value} writer is not admitted while writer mode is {control.writer_mode.value}"
    )


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
    writer_mode: WriterMode = WriterMode.compatibility
    writer_epoch: int = 0
    writer_transition_owner: Optional[str] = None
    ledger_migration_migrated_count: int = 0
    ledger_migration_adjudicated_count: int = 0
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
        "writer_epoch",
        "ledger_migration_migrated_count",
        "ledger_migration_adjudicated_count",
        "commit_sequence",
        "projection_watermark_sequence",
        "legacy_backfill_processed_count",
    )
    @classmethod
    def validate_nonnegative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("control counters must be nonnegative")
        return value

    @field_validator("writer_epoch", mode="before")
    @classmethod
    def validate_writer_epoch_is_an_integer(cls, value: Any) -> Any:
        # Writer epochs are CAS fences.  Coercing strings or booleans would let
        # a malformed control document accidentally participate in a cutover.
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("writer_epoch must be an integer")
        return value

    @model_validator(mode="after")
    def validate_writer_transition_owner(self) -> "MemoryControlState":
        transitioning = self.writer_mode in {
            WriterMode.transitioning_to_ledger,
            WriterMode.transitioning_to_compatibility,
        }
        owner = (self.writer_transition_owner or "").strip()
        if transitioning and not owner:
            raise ValueError("transitioning writer mode requires an owner")
        if not transitioning and self.writer_transition_owner is not None:
            raise ValueError("stable writer mode cannot retain a transition owner")
        if self.writer_transition_owner is not None and self.writer_transition_owner != owner:
            raise ValueError("writer transition owner must not contain surrounding whitespace")
        return self

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
    graph_assertions: List[MemoryGraphAssertion] = Field(default_factory=list)
    outbox_events: List[MemoryOutboxEvent] = Field(default_factory=list)
    reason: Optional[str] = None


def _canonical_mutation_identity_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_mutation_identity_value(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _canonical_mutation_identity_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_mutation_identity_value(item) for item in value]
    if isinstance(value, set):
        normalized = [_canonical_mutation_identity_value(item) for item in value]
        return sorted(normalized, key=repr)
    return value


def build_patch_mutation_identity(patch_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return every item-affecting patch field not already in the base operation digest."""
    return {
        key: _canonical_mutation_identity_value(value)
        for key, value in patch_payload.items()
        if key not in _PATCH_MUTATION_IDENTITY_EXCLUDED_KEYS
    }


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


def memory_content_hash(*, content: Optional[str], evidence_ids: List[str]) -> str:
    return deterministic_contract_id(
        "memory-content",
        {"content": content, "evidence_ids": evidence_ids},
    )


def _valid_graph_enrichment_receipt(
    raw_receipt: Any,
    *,
    operation: MemoryOperation,
    existing_item: MemoryItem,
    control_state: MemoryControlState,
    graph_plan: Optional[PromotionGraphPlan],
) -> bool:
    """Validate the persisted receipt before allowing a graph-only LTM mutation."""
    if not isinstance(raw_receipt, dict) or graph_plan is None:
        return False
    if raw_receipt.get("schema_version") != "canonical_memory_graph_enrichment_receipt.v1":
        return False
    evidence_ids = raw_receipt.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not evidence_ids:
        return False
    if any(not isinstance(value, str) or not value.strip() for value in evidence_ids):
        return False
    normalized_evidence_ids = sorted(value.strip() for value in evidence_ids)
    if len(normalized_evidence_ids) != len(set(normalized_evidence_ids)):
        return False

    def nonnegative_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    receipt_id = raw_receipt.get("receipt_id")
    uid = raw_receipt.get("uid")
    memory_id = raw_receipt.get("memory_id")
    content_hash = raw_receipt.get("content_hash")
    plan_hash = raw_receipt.get("plan_hash")
    item_revision = raw_receipt.get("item_revision")
    account_generation = raw_receipt.get("account_generation")
    source_generation = raw_receipt.get("source_generation")
    if not all(
        isinstance(value, str) and value.strip() for value in (receipt_id, uid, memory_id, content_hash, plan_hash)
    ):
        return False
    if not all(nonnegative_int(value) for value in (item_revision, account_generation, source_generation)):
        return False
    expected_id = (
        "ger_"
        + deterministic_contract_id(
            "canonical-memory-graph-enrichment-receipt",
            {
                "schema_version": raw_receipt["schema_version"],
                "uid": uid,
                "memory_id": memory_id,
                "item_revision": item_revision,
                "content_hash": content_hash,
                "evidence_ids": normalized_evidence_ids,
                "account_generation": account_generation,
                "source_generation": source_generation,
                "plan_hash": plan_hash,
            },
        )[:32]
    )
    return (
        receipt_id == expected_id
        and uid == operation.uid
        and memory_id == existing_item.memory_id
        and item_revision == existing_item.item_revision
        and content_hash == existing_item.content_hash
        and normalized_evidence_ids == sorted(record.evidence_id for record in existing_item.evidence)
        and account_generation == control_state.account_generation
        and source_generation == control_state.source_generation
        and plan_hash == graph_plan.plan_hash
    )


def _processing_state_for_promotion(
    promotion: Optional[Dict[str, Any]],
    *,
    fallback: ProcessingState,
) -> ProcessingState:
    processing_status = str((promotion or {}).get("processing_status") or "")
    if processing_status in {"pending_processing", "processing_failed_retryable", "pending_admission"}:
        return ProcessingState.pending
    if processing_status == "processing_blocked":
        return ProcessingState.blocked
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
        normalized_content_key=normalized_memory_content_key(patch.memory_text),
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
        content_hash=memory_content_hash(content=patch.memory_text, evidence_ids=patch.evidence_ids),
        account_generation=account_generation,
        promotion=promotion,
        subject_entity_id=patch.subject_entity_id,
        predicate=patch.predicate,
        arguments=dict(patch.arguments or {}),
        ledger_schema_version=patch.ledger_schema_version,
        kind=patch.kind,
        subject_scope=patch.subject_scope,
        half_life_days=patch.half_life_days,
        belief_class=patch.belief_class,
        slot=patch.slot,
        body=patch.body,
        valid_from=patch.valid_from or now,
        valid_to=patch.valid_to,
        curation_weight=patch.curation_weight,
        trigger_condition=dict(patch.trigger_condition or {}),
        intent_backed=patch.intent_backed,
        write_reason=patch.write_reason,
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
        "normalized_content_key": normalized_memory_content_key(content),
        "evidence": evidence or existing.evidence,
        "updated_at": now,
        "expires_at": expires_at,
        "ledger_commit_id": commit_id,
        "ledger_sequence": sequence,
        "version": existing.version + 1,
        "item_revision": existing.item_revision + 1,
    }
    if patch.memory_text is not None and patch.memory_text.strip():
        updates["content_hash"] = memory_content_hash(
            content=patch.memory_text,
            evidence_ids=[item.evidence_id for item in (evidence or existing.evidence)],
        )
    if promotion_audit is not None:
        updates["promotion"] = promotion_audit
    if patch.subject_entity_id is not None:
        updates["subject_entity_id"] = patch.subject_entity_id
    if patch.predicate is not None:
        updates["predicate"] = patch.predicate
    if patch.arguments:
        updates["arguments"] = dict(patch.arguments)
    if patch.target_visibility is not None:
        updates["visibility"] = patch.target_visibility
    if patch.target_user_asserted is not None:
        updates["user_asserted"] = patch.target_user_asserted
    for ledger_key in (
        "ledger_schema_version",
        "kind",
        "subject_scope",
        "half_life_days",
        "belief_class",
        "slot",
        "body",
        "valid_from",
        "valid_to",
        "curation_weight",
        "trigger_condition",
        "intent_backed",
        "write_reason",
    ):
        if ledger_key in patch.model_fields_set:
            updates[ledger_key] = getattr(patch, ledger_key)
    if extra_updates:
        updates.update(extra_updates)
    if patch.clear_graph_assertion:
        updates.update(
            {
                "subject_entity_id": None,
                "predicate": None,
                "arguments": {},
                "graph_ready": False,
                "graph_assertion_id": None,
                "graph_plan_hash": None,
                "kg_extracted": False,
            }
        )
    return existing.model_copy(update=updates)


def _stale_operation(operation: MemoryOperation) -> MemoryOperation:
    data = operation.model_dump(mode="python")
    data.update({"status": MemoryOperationStatus.stale_generation, "updated_at": datetime.now(timezone.utc)})
    return MemoryOperation(**data)


def _operation_digest_for_patch(
    patch: DurableMemoryPatch,
    operation: MemoryOperation,
    *,
    mutation_identity: Dict[str, Any],
) -> str:
    logical_payload: Dict[str, Any] = {
        "decision": patch.decision.value,
        "memory_text": patch.memory_text,
        "target_memory_id": patch.target_memory_id,
        "result_status": patch.result_status.value,
        "supersedes": patch.supersedes,
        "arguments": patch.arguments,
    }
    if operation.logical_payload.subject_entity_id is not None:
        logical_payload["subject_entity_id"] = patch.subject_entity_id
    if operation.logical_payload.predicate is not None:
        logical_payload["predicate"] = patch.predicate
    if operation.logical_payload.target_tier is not None:
        logical_payload["target_tier"] = patch.target_tier.value if patch.target_tier is not None else None
    if operation.logical_payload.target_visibility is not None:
        logical_payload["target_visibility"] = patch.target_visibility
    if operation.logical_payload.target_user_asserted is not None:
        logical_payload["target_user_asserted"] = patch.target_user_asserted
    if operation.logical_payload.clear_graph_assertion is not None:
        logical_payload["clear_graph_assertion"] = patch.clear_graph_assertion
    if operation.logical_payload.mutation_metadata is not None:
        logical_payload["mutation_metadata"] = mutation_identity
    return logical_payload_digest(logical_payload)


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
    *,
    control_state: MemoryControlState,
    operation: MemoryOperation,
    patch_payload: Dict[str, Any],
    allow_trigger_feedback_arguments: bool = False,
) -> ApplyResult:
    """Pure transaction skeleton for Milestone 3.

    Production Firestore integration must perform these reads/writes atomically:
    control head/generations, operation journal status, memory item mutation, and outbox append.
    """
    raw = dict(patch_payload)
    mutation_identity = build_patch_mutation_identity(raw)
    existing_item_raw = raw.pop("existing_item", None)
    superseded_items_raw = raw.pop("superseded_items", None)
    promotion_audit = raw.pop("promotion_audit", None)
    promotion_metadata = raw.pop("promotion", None)
    expected_item_revision = raw.pop("expected_item_revision", None)
    expected_content_hash = raw.pop("expected_content_hash", None)
    extra_item_updates: Dict[str, Any] = {}
    for optional_key in (
        "corroboration_count",
        "last_corroborated_at",
        "half_life_days",
        "belief_class",
        "captured_at",
        "updated_at",
        "expires_at",
        "superseded_by",
        "kg_extracted",
        "confidence",
        "sensitivity_labels",
        "capture_device_ids",
        "primary_capture_device",
    ):
        if optional_key in raw:
            extra_item_updates[optional_key] = raw.pop(optional_key)
    for timestamp_key in (
        "last_corroborated_at",
        "captured_at",
        "updated_at",
        "expires_at",
    ):
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
    if patch.evidence_ids != operation.evidence_ids:
        return ApplyResult(
            status=ApplyStatus.payload_mismatch,
            control_state=control_state,
            operation=operation,
            reason="patch evidence_ids do not match operation evidence_ids",
        )
    if (
        patch.ledger_schema_version == "knowledge_ledger.v1"
        and operation.operation_type != MemoryOperationType.ledger_mutation
    ):
        return ApplyResult(
            status=ApplyStatus.invalid_patch,
            control_state=control_state,
            operation=operation,
            reason="knowledge ledger writes require ledger_mutation authority",
        )
    if (
        _operation_digest_for_patch(
            patch,
            operation,
            mutation_identity=mutation_identity,
        )
        != operation.logical_payload_digest
    ):
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
        rebased_operation = operation.model_copy(
            update={
                "observed_head_commit_id": control_state.head_commit_id,
                "attempt_count": operation.attempt_count + 1,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return ApplyResult(
            status=ApplyStatus.retryable_head_mismatch,
            control_state=control_state,
            operation=rebased_operation,
            reason="observed head does not match current head",
        )

    if (
        operation.operation_type == MemoryOperationType.graph_enrichment
        and patch.decision != DurablePatchDecision.update
    ):
        return ApplyResult(
            status=ApplyStatus.invalid_patch,
            control_state=control_state,
            operation=operation,
            reason="graph enrichment requires an update decision",
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
    transitioning_to_long_term = False
    graph_enrichment = False
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
        graph_enrichment = operation.operation_type == MemoryOperationType.graph_enrichment
        if graph_enrichment:
            raw_graph_plan = promotion_audit.get("graph_plan") if isinstance(promotion_audit, dict) else None
            raw_receipt = promotion_audit.get("graph_enrichment_receipt") if isinstance(promotion_audit, dict) else None
            try:
                graph_plan = PromotionGraphPlan(**raw_graph_plan) if isinstance(raw_graph_plan, dict) else None
            except Exception:
                graph_plan = None
            required_receipt_valid = not (existing_item.promotion or {}).get(
                "required"
            ) or valid_required_processing_receipt(
                content=existing_item.content or "",
                item_revision=existing_item.item_revision,
                promotion=existing_item.promotion or {},
            )
            replan = existing_item.graph_ready and bool((existing_item.promotion or {}).get("graph_enrichment"))
            if not (
                existing_item.status == MemoryItemStatus.active
                and existing_item.tier == MemoryTier.long_term
                and existing_item.processing_state == ProcessingState.processed
                and (not existing_item.graph_ready or replan)
                and graph_plan is not None
                and _valid_graph_enrichment_receipt(
                    raw_receipt,
                    operation=operation,
                    existing_item=existing_item,
                    control_state=control_state,
                    graph_plan=graph_plan,
                )
                and required_receipt_valid
                and not set(existing_item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS)
                and (existing_item.promotion or {}).get("user_review") is not False
                and patch.target_tier is None
                and patch.memory_text is None
                and patch.target_visibility is None
                and patch.target_user_asserted is None
                and not patch.clear_graph_assertion
                and not extra_item_updates
                and promotion_metadata is None
                and patch.result_status == LifecycleState.active
                and not patch.supersedes
                and patch.subject_entity_id == graph_plan.subject_entity_id
                and (
                    replan
                    or not existing_item.subject_entity_id
                    or graph_plan.subject_entity_id == existing_item.subject_entity_id
                )
                and patch.predicate == graph_plan.predicate
                and (replan or not existing_item.predicate or graph_plan.predicate == existing_item.predicate)
                and bool(_GRAPH_PREDICATE_RE.fullmatch(graph_plan.predicate))
                and patch.arguments == graph_plan.arguments
                and (replan or not existing_item.arguments or graph_plan.arguments == existing_item.arguments)
                and sorted(record.evidence_id for record in evidence)
                == sorted(record.evidence_id for record in existing_item.evidence)
            ):
                return ApplyResult(
                    status=ApplyStatus.invalid_patch,
                    control_state=control_state,
                    operation=operation,
                    reason="graph enrichment must attach one validated plan without changing Long-term semantics",
                )
        if existing_item.tier == MemoryTier.long_term and existing_item.status == MemoryItemStatus.active:
            proposed_evidence = evidence or existing_item.evidence
            semantic_change = any(
                (
                    _resolved_update_content(existing_item, patch) != existing_item.content,
                    [item.evidence_id for item in proposed_evidence]
                    != [item.evidence_id for item in existing_item.evidence],
                    (patch.subject_entity_id or existing_item.subject_entity_id) != existing_item.subject_entity_id,
                    (patch.predicate or existing_item.predicate) != existing_item.predicate,
                    (patch.arguments or existing_item.arguments) != existing_item.arguments,
                )
            )
            explicit_short_term_demotion = patch.target_tier == MemoryTier.short_term and patch.clear_graph_assertion
            if (
                semantic_change
                and not explicit_short_term_demotion
                and not graph_enrichment
                and not allow_trigger_feedback_arguments
            ):
                return ApplyResult(
                    status=ApplyStatus.invalid_patch,
                    control_state=control_state,
                    operation=operation,
                    reason="Long-term semantics are immutable; promote a new Short-term item and supersede this one",
                )
        transitioning_to_long_term = (
            existing_item.tier != MemoryTier.long_term and patch.target_tier == MemoryTier.long_term
        )
        if transitioning_to_long_term:
            admission_metadata = promotion_audit if isinstance(promotion_audit, dict) else {}
            proposed_content = _resolved_update_content(existing_item, patch) or ""
            proposed_evidence = evidence or existing_item.evidence
            proposed_evidence_ids = [item.evidence_id for item in proposed_evidence]
            proposed_content_hash = memory_content_hash(
                content=proposed_content,
                evidence_ids=proposed_evidence_ids,
            )
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
            if (
                not valid_promotion_admission(
                    memory_id=existing_item.memory_id,
                    source_item_revision=existing_item.item_revision,
                    output_content_hash=proposed_content_hash,
                    evidence_ids=proposed_evidence_ids,
                    subject_entity_id=patch.subject_entity_id or existing_item.subject_entity_id,
                    predicate=patch.predicate or existing_item.predicate,
                    arguments=patch.arguments or existing_item.arguments,
                    supersedes=patch.supersedes,
                    promotion=admission_metadata,
                )
                or operation.operation_type != MemoryOperationType.synthesis
            ):
                return ApplyResult(
                    status=ApplyStatus.invalid_patch,
                    control_state=control_state,
                    operation=operation,
                    reason="Short-term to Long-term transition requires a current promotion admission and graph plan",
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
            memory_item = MemoryItem(**{**memory_item.model_dump(), **extra_item_updates})

    memory_items = [memory_item]
    graph_assertions: List[MemoryGraphAssertion] = []
    refresh_graph_assertion = (
        transitioning_to_long_term
        or graph_enrichment
        or (
            memory_item.tier == MemoryTier.long_term
            and memory_item.status == MemoryItemStatus.active
            and memory_item.graph_ready
            and not patch.clear_graph_assertion
        )
    )
    if refresh_graph_assertion:
        admission_metadata = memory_item.promotion or {}
        raw_graph_plan = admission_metadata.get("graph_plan")
        if not isinstance(raw_graph_plan, dict):
            return ApplyResult(
                status=ApplyStatus.invalid_patch,
                control_state=control_state,
                operation=operation,
                reason="active graph-backed Long-term update requires its stored graph plan",
            )
        try:
            graph_plan = PromotionGraphPlan(**raw_graph_plan)
        except Exception:
            return ApplyResult(
                status=ApplyStatus.invalid_patch,
                control_state=control_state,
                operation=operation,
                reason="active graph-backed Long-term update has an invalid stored graph plan",
            )
        assertion = build_memory_graph_assertion(
            uid=operation.uid,
            memory_id=memory_item.memory_id,
            item_revision=memory_item.item_revision,
            content_hash=memory_item.content_hash or "",
            evidence_ids=[item.evidence_id for item in memory_item.evidence],
            graph_plan=graph_plan,
            commit_id=commit_id,
            commit_sequence=next_control.commit_sequence,
            created_at=memory_item.updated_at,
        )
        memory_item = memory_item.model_copy(
            update={
                "graph_ready": True,
                "graph_assertion_id": assertion.assertion_id,
                "graph_plan_hash": graph_plan.plan_hash,
                "kg_extracted": True,
            }
        )
        memory_items = [memory_item]
        graph_assertions = [assertion]

    if patch.supersedes:
        if not isinstance(superseded_items_raw, list):
            return ApplyResult(
                status=ApplyStatus.invalid_patch,
                control_state=control_state,
                operation=operation,
                reason="superseding promotion requires authoritative superseded_items",
            )
        superseded_by_id = {
            item.memory_id: item
            for raw_item in superseded_items_raw
            for item in [raw_item if isinstance(raw_item, MemoryItem) else MemoryItem(**raw_item)]
        }
        if set(superseded_by_id) != set(patch.supersedes):
            return ApplyResult(
                status=ApplyStatus.invalid_patch,
                control_state=control_state,
                operation=operation,
                reason="superseded_items do not match patch supersedes",
            )
        for superseded_id in patch.supersedes:
            existing_superseded = superseded_by_id[superseded_id]
            if existing_superseded.status != MemoryItemStatus.active:
                return ApplyResult(
                    status=ApplyStatus.target_not_active,
                    control_state=control_state,
                    operation=operation,
                    reason=f"superseded target is not active: {superseded_id}",
                )
            if patch.ledger_schema_version == "knowledge_ledger.v1":
                if existing_superseded.ledger_schema_version != "knowledge_ledger.v1":
                    return ApplyResult(
                        status=ApplyStatus.invalid_patch,
                        control_state=control_state,
                        operation=operation,
                        reason="knowledge ledger amendment may supersede only ledger rows",
                    )
                if (
                    existing_superseded.kind != patch.kind
                    or existing_superseded.subject_scope != patch.subject_scope
                    or existing_superseded.subject_entity_id != patch.subject_entity_id
                ):
                    return ApplyResult(
                        status=ApplyStatus.invalid_patch,
                        control_state=control_state,
                        operation=operation,
                        reason="knowledge ledger amendment must preserve kind and subject identity",
                    )
            superseded_at = max(datetime.now(timezone.utc), existing_superseded.updated_at)
            if patch.ledger_schema_version == "knowledge_ledger.v1":
                superseded_at = max(
                    superseded_at,
                    memory_item.valid_from or memory_item.captured_at,
                    existing_superseded.valid_from or existing_superseded.captured_at,
                )
            superseded_item = existing_superseded.model_copy(
                update={
                    "canonical_memory_id": memory_item.memory_id,
                    "status": MemoryItemStatus.superseded,
                    "superseded_by": memory_item.memory_id,
                    "updated_at": superseded_at,
                    "valid_to": (
                        superseded_at
                        if patch.ledger_schema_version == "knowledge_ledger.v1"
                        else existing_superseded.valid_to
                    ),
                    "ledger_commit_id": commit_id,
                    "ledger_sequence": next_control.commit_sequence,
                    "version": existing_superseded.version + 1,
                    "item_revision": existing_superseded.item_revision + 1,
                    "graph_ready": False,
                    "graph_assertion_id": None,
                    "graph_plan_hash": None,
                    "kg_extracted": False,
                }
            )
            memory_items.append(superseded_item)

    outbox_events: List[MemoryOutboxEvent] = []
    for changed_item in memory_items:
        has_restricted_sensitivity = bool(
            set(changed_item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS)
        )
        projection_eligible = (
            changed_item.status == MemoryItemStatus.active
            and changed_item.processing_state == ProcessingState.processed
            and changed_item.tier in {MemoryTier.short_term, MemoryTier.long_term}
            and (changed_item.promotion or {}).get("user_review") is not False
            and not has_restricted_sensitivity
        )
        vector_eligible = (
            changed_item.status == MemoryItemStatus.active
            and changed_item.processing_state == ProcessingState.processed
            and changed_item.tier in {MemoryTier.short_term, MemoryTier.long_term}
            and (changed_item.promotion or {}).get("user_review") is not False
            and not has_restricted_sensitivity
        )
        action_by_event_type = {
            MemoryOutboxEventType.projection_sync: "upsert" if projection_eligible else "delete",
            MemoryOutboxEventType.vector_sync: "upsert" if vector_eligible else "delete",
        }
        outbox_events.extend(
            MemoryOutboxEvent(
                event_id=_event_id(event_type, commit_id, changed_item.memory_id, operation.operation_id),
                uid=operation.uid,
                event_type=event_type,
                commit_id=commit_id,
                parent_commit_id=control_state.head_commit_id,
                commit_sequence=next_control.commit_sequence,
                memory_id=changed_item.memory_id,
                operation_id=operation.operation_id,
                account_generation=control_state.account_generation,
                source_generation=control_state.source_generation,
                payload={
                    "memory_id": changed_item.memory_id,
                    "tier": changed_item.tier.value,
                    "action": action_by_event_type[event_type],
                    "item_revision": changed_item.item_revision,
                    "content_hash": changed_item.content_hash,
                },
            )
            for event_type in [MemoryOutboxEventType.projection_sync, MemoryOutboxEventType.vector_sync]
        )
    committed_operation = operation.mark_committed(
        commit_id,
        committed_sequence=next_control.commit_sequence,
        committed_memory_item_ids=[item.memory_id for item in memory_items],
        committed_outbox_event_ids=[event.event_id for event in outbox_events],
    )
    return ApplyResult(
        status=ApplyStatus.committed,
        control_state=next_control,
        operation=committed_operation,
        memory_items=memory_items,
        graph_assertions=graph_assertions,
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
    "build_patch_mutation_identity",
    "memory_content_hash",
]
