"""Canonical Firestore apply adapter for long-term memory patches (WS-G7)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, TypeVar, TypedDict, cast

from pydantic import BaseModel

from database.store import Transaction, get_document_store
from database.memory_collections import MemoryCollections
from database.read_boundary import parse_snapshot_strict
from models.memory_evidence import MemoryEvidence
from models.memory_contracts import DurablePatchDecision
from models.memory_apply import (
    ApplyResult,
    ApplyStatus,
    MemoryControlState,
    apply_long_term_patch_transaction,
)
from models.memory_operations import MemoryOperation
from models.product_memory import MemoryItemStatus, MemoryItem
from models.memory_state_head import trusted_memory_state_head_fields


def _store():
    return get_document_store()


class MemoryFirestoreApplyError(Exception):
    pass


MemoryFirestoreApplyError = MemoryFirestoreApplyError


class MissingMemoryDocument(MemoryFirestoreApplyError):
    pass


class MemoryApplyDoc(TypedDict, total=False):
    """Firestore document contract for the memory-apply store.

    Captures the union of keys read into ``MemoryControlState``,
    ``MemoryOperation``, ``MemoryEvidence`` and ``MemoryItem`` plus the
    ``commit`` and ``state-head`` projections written back through this store.
    Every key is optional because each read uses ``**`` into a pydantic model
    that supplies defaults, and the document shape varies per collection.
    """

    # control state
    uid: str
    head_commit_id: str
    account_generation: int
    source_generation: int
    commit_sequence: int
    projection_watermark_commit_id: Optional[str]
    projection_watermark_sequence: int
    vector_watermark_commit_id: Optional[str]
    last_promotion_run_at: Optional[datetime]
    last_consolidation_run_at: Optional[datetime]
    legacy_backfill_processed_count: int
    legacy_backfill_source_fingerprint: Optional[str]
    legacy_backfill_completed_at: Optional[datetime]
    updated_at: datetime
    # operation
    operation_id: str
    operation_type: Any
    status: Any
    source_packet_id: Optional[str]
    target_memory_id: Optional[str]
    evidence_ids: List[str]
    logical_payload: Any
    logical_payload_digest: str
    observed_head_commit_id: Optional[str]
    committed_head_commit_id: Optional[str]
    committed_sequence: Optional[int]
    committed_memory_item_ids: List[str]
    committed_outbox_event_ids: List[str]
    attempt_count: int
    error_code: Optional[str]
    untrusted_proposed_operation_id: Optional[str]
    created_at: datetime
    # evidence
    evidence_id: str
    source_type: str
    source_id: Optional[str]
    source_version: Optional[str]
    conversation_id: Optional[str]
    artifact_refs: List[Dict[str, Any]]
    artifact_preservation: Any
    quote_refs: List[Dict[str, Any]]
    content_hash: Optional[str]
    lineage_id: Optional[str]
    source_state: Any
    source_state_reason: Any
    provenance_visibility: Any
    redaction_status: Any
    encryption_or_redaction_status: Any
    patch_id: Optional[str]
    commit_id: Optional[str]
    client_device_id: Optional[str]
    # memory item
    memory_id: str
    canonical_memory_id: Optional[str]
    version: int
    tier: Any
    processing_state: Any
    content: Optional[str]
    evidence: List[Dict[str, Any]]
    sensitivity_labels: List[str]
    visibility: str
    user_asserted: bool
    captured_at: datetime
    expires_at: Optional[datetime]
    ledger_commit_id: Optional[str]
    ledger_sequence: Optional[int]
    item_revision: int
    source_commit_id: Optional[str]
    source_commit_sequence: Optional[int]
    promotion: Optional[Dict[str, Any]]
    capture_device_ids: List[str]
    primary_capture_device: Optional[str]
    corroboration_count: int
    last_corroborated_at: Optional[datetime]
    confidence: Optional[float]
    superseded_by: Optional[str]
    subject_entity_id: Optional[str]
    predicate: Optional[str]
    arguments: Dict[str, Any]
    kg_extracted: bool
    # commit projection (write-only)
    memory_item_ids: List[str]
    outbox_event_ids: List[str]
    # state-head projection (write-only)
    schema_version: int
    source: str


M = TypeVar("M", bound=BaseModel)


def _typed_doc(doc: Any) -> Dict[str, Any]:
    """Typed adapter for the storage port ``StoredDocument.to_dict()`` reads."""
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def apply_long_term_patch_firestore(
    *,
    uid: str,
    operation_id: str,
    patch_payload: Dict[str, Any],
) -> ApplyResult:
    """Apply a memory Long-term patch through the storage-port transaction boundary.

    The pure contract in `models.memory_apply` stays dependency-free. This
    adapter owns authoritative store reads/writes and never trusts caller
    snapshots for control state, operation state, or evidence/source state.
    """
    return _store().run_transaction(
        lambda tx: _apply_long_term_patch_firestore_transaction(tx, uid, operation_id, patch_payload)
    )


def atomic_bump_source_generation(uid: str) -> MemoryControlState:
    """Atomically advance canonical apply ``source_generation`` (Q7 reprocess)."""
    return _store().run_transaction(lambda tx: _atomic_bump_source_generation_transaction(tx, uid))


def _atomic_bump_source_generation_transaction(
    tx: Transaction,
    uid: str,
) -> MemoryControlState:
    now = datetime.now(timezone.utc)
    collections = MemoryCollections(uid=uid)
    control_path = collections.memory_apply_control_state
    snapshot = tx.get(control_path)
    if not snapshot.exists:
        control = MemoryControlState(
            uid=uid,
            head_commit_id="head0",
            account_generation=1,
            source_generation=1,
            updated_at=now,
        )
    else:
        control = parse_snapshot_strict(MemoryControlState, snapshot, payload_from_snapshot=_typed_doc)
    bumped = control.model_copy(
        update={
            "source_generation": control.source_generation + 1,
            "updated_at": now,
        }
    )
    tx.set(control_path, _firestore_data(bumped))
    return bumped


def _apply_long_term_patch_firestore_transaction(
    tx: Transaction,
    uid: str,
    operation_id: str,
    patch_payload: Dict[str, Any],
) -> ApplyResult:
    collections = MemoryCollections(uid=uid)
    control_path = collections.memory_apply_control_state
    operation_path = f"{collections.memory_operations}/{operation_id}"

    control_state = _required_model(
        tx=tx,
        path=control_path,
        model=MemoryControlState,
        label="memory control state",
    )
    operation = _required_model(
        tx=tx,
        path=operation_path,
        model=MemoryOperation,
        label="memory operation",
    )
    if operation.uid != uid:
        raise MemoryFirestoreApplyError("operation uid does not match requested uid")
    if operation.operation_id != operation_id:
        raise MemoryFirestoreApplyError("operation_id does not match requested operation document")

    committed_replay = apply_long_term_patch_transaction(
        control_state=control_state,
        operation=operation,
        patch_payload=patch_payload,
    )
    if committed_replay.status == ApplyStatus.idempotent_skip:
        return committed_replay
    if committed_replay.status == ApplyStatus.payload_mismatch:
        return committed_replay

    evidence_items = _read_authoritative_evidence(
        tx=tx,
        collections=collections,
        evidence_ids=operation.evidence_ids,
    )
    target_validation = _validate_authoritative_targets(
        tx=tx,
        collections=collections,
        operation=operation,
        control_state=control_state,
    )
    if target_validation is not None:
        _write_apply_result(
            tx=tx,
            collections=collections,
            operation_path=operation_path,
            result=target_validation,
        )
        return target_validation

    authoritative_payload: Dict[str, Any] = dict(patch_payload)
    authoritative_payload["evidence"] = evidence_items
    existing_item = _read_authoritative_target_item(
        tx=tx,
        collections=collections,
        operation=operation,
    )
    if existing_item is not None:
        authoritative_payload["existing_item"] = existing_item.model_dump(mode="python")

    result = apply_long_term_patch_transaction(
        control_state=control_state,
        operation=operation,
        patch_payload=authoritative_payload,
    )
    _write_apply_result(
        tx=tx,
        collections=collections,
        operation_path=operation_path,
        result=result,
    )
    return result


def _read_authoritative_evidence(
    *,
    tx: Transaction,
    collections: MemoryCollections,
    evidence_ids: Iterable[str],
) -> List[MemoryEvidence]:
    evidence_items: List[MemoryEvidence] = []
    for evidence_id in evidence_ids:
        evidence = _required_model(
            tx=tx,
            path=f"{collections.memory_evidence}/{evidence_id}",
            model=MemoryEvidence,
            label="memory evidence",
        )
        evidence_items.append(evidence)
    return evidence_items


def _read_authoritative_target_item(
    *,
    tx: Transaction,
    collections: MemoryCollections,
    operation: MemoryOperation,
) -> Optional[MemoryItem]:
    if operation.logical_payload.decision != DurablePatchDecision.update.value:
        return None
    target_id = operation.logical_payload.target_memory_id or operation.target_memory_id
    if not target_id:
        return None
    snapshot = tx.get(f"{collections.memory_items}/{target_id}")
    if not snapshot.exists:
        return None
    return parse_snapshot_strict(MemoryItem, snapshot, payload_from_snapshot=_typed_doc)


def _validate_authoritative_targets(
    *,
    tx: Transaction,
    collections: MemoryCollections,
    operation: MemoryOperation,
    control_state: MemoryControlState,
) -> Optional[ApplyResult]:
    target_ids = _operation_target_ids(operation)
    for target_id in target_ids:
        snapshot = tx.get(f"{collections.memory_items}/{target_id}")
        if not snapshot.exists:
            return _target_not_active(control_state, operation, f"missing target memory item: {target_id}")
        target = parse_snapshot_strict(MemoryItem, snapshot, payload_from_snapshot=_typed_doc)
        if target.uid != operation.uid:
            return _target_not_active(control_state, operation, "target memory uid mismatch")
        if target.account_generation != control_state.account_generation:
            return _target_not_active(control_state, operation, "target memory generation mismatch")
        if target.status != MemoryItemStatus.active:
            return _target_not_active(control_state, operation, "target memory is not active")
    return None


def _operation_target_ids(operation: MemoryOperation) -> List[str]:
    target_ids: List[str] = []
    if operation.target_memory_id:
        target_ids.append(operation.target_memory_id)
    if operation.logical_payload.target_memory_id:
        target_ids.append(operation.logical_payload.target_memory_id)
    target_ids.extend(operation.logical_payload.supersedes or [])
    return sorted(set(target_ids))


def _target_not_active(control_state: MemoryControlState, operation: MemoryOperation, reason: str) -> ApplyResult:
    return ApplyResult(
        status=ApplyStatus.target_not_active,
        control_state=control_state,
        operation=operation,
        reason=reason,
    )


def _write_apply_result(
    *,
    tx: Transaction,
    collections: MemoryCollections,
    operation_path: str,
    result: ApplyResult,
) -> None:
    tx.set(operation_path, _firestore_data(result.operation))
    if result.status != ApplyStatus.committed:
        return

    control_path = collections.memory_apply_control_state
    commit_path = f"{collections.memory_commits}/{result.control_state.head_commit_id}"
    state_head_path = collections.memory_state_head
    tx.set(control_path, _firestore_data(result.control_state))
    tx.set(state_head_path, _firestore_data(_memory_state_head_from_control(result.control_state)))
    commit_doc: MemoryApplyDoc = {
        "commit_id": result.control_state.head_commit_id,
        "uid": result.control_state.uid,
        "account_generation": result.control_state.account_generation,
        "source_generation": result.control_state.source_generation,
        "commit_sequence": result.control_state.commit_sequence,
        "operation_id": result.operation.operation_id,
        "memory_item_ids": [item.memory_id for item in result.memory_items],
        "outbox_event_ids": [event.event_id for event in result.outbox_events],
        "updated_at": result.control_state.updated_at,
    }
    tx.set(commit_path, _firestore_data(commit_doc))
    for item in result.memory_items:
        tx.set(f"{collections.memory_items}/{item.memory_id}", _firestore_data(item))
    for event in result.outbox_events:
        tx.set(f"{collections.memory_outbox}/{event.event_id}", _firestore_data(event))


def _memory_state_head_from_control(control_state: MemoryControlState) -> MemoryApplyDoc:
    trusted_fields = trusted_memory_state_head_fields(
        uid=control_state.uid,
        account_generation=control_state.account_generation,
        head_commit_id=control_state.head_commit_id,
        commit_sequence=control_state.commit_sequence,
    )
    if trusted_fields is None:  # MemoryControlState has already validated this input.
        raise MemoryFirestoreApplyError("invalid memory state-head control fields")
    return cast(MemoryApplyDoc, {**trusted_fields, "updated_at": control_state.updated_at})


def _required_model(*, tx: Transaction, path: str, model: type[M], label: str) -> M:
    snapshot = tx.get(path)
    if not snapshot.exists:
        raise MissingMemoryDocument(f"missing {label}: {path}")
    return parse_snapshot_strict(model, snapshot, payload_from_snapshot=_typed_doc)


def _firestore_data(value: object) -> Any:
    if isinstance(value, BaseModel):
        return _firestore_data(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_firestore_data(item) for item in cast(List[Any], value)]
    if isinstance(value, tuple):
        return [_firestore_data(item) for item in cast(List[Any], value)]
    if isinstance(value, dict):
        mapping = cast(Dict[str, Any], value)
        return {key: _firestore_data(item) for key, item in mapping.items()}
    return value


__all__ = [
    "MemoryFirestoreApplyError",
    "MissingMemoryDocument",
    "MemoryFirestoreApplyError",
    "apply_long_term_patch_firestore",
    "atomic_bump_source_generation",
]
