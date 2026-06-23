from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

try:
    from google.cloud.firestore_v1 import transactional
except ImportError:  # pragma: no cover - local unit tests mock Firestore.

    def transactional(func):
        def wrapper(transaction, *args, **kwargs):
            if hasattr(transaction, "_begin"):
                transaction._begin()
            try:
                result = func(transaction, *args, **kwargs)
                if hasattr(transaction, "_commit"):
                    transaction._commit()
                return result
            except Exception:
                if hasattr(transaction, "_rollback"):
                    transaction._rollback()
                raise
            finally:
                if hasattr(transaction, "_clean_up"):
                    transaction._clean_up()

        return wrapper


from pydantic import BaseModel

from database._client import db
from database.v17_collections import V17Collections
from models.memory_evidence import MemoryEvidence
from models.v17_memory_contracts import DurablePatchDecision
from models.v17_memory_apply import (
    ApplyResult,
    ApplyStatus,
    MemoryControlState,
    apply_long_term_patch_transaction,
)
from models.v17_memory_operations import MemoryOperation
from models.v17_product_memory import MemoryItemStatus, V17MemoryItem
from utils.memory.v17_v3_account_generation_source import (
    V17_V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION,
    V17_V3_TRUSTED_ACCOUNT_GENERATION_SOURCE,
)


class V17FirestoreApplyError(Exception):
    pass


class MissingV17Document(V17FirestoreApplyError):
    pass


def apply_long_term_patch_firestore(
    *,
    uid: str,
    operation_id: str,
    patch_payload: Dict[str, Any],
    db_client=db,
) -> ApplyResult:
    """Apply a V17 Long-term patch through the Firestore transaction boundary.

    The pure contract in `models.v17_memory_apply` stays dependency-free. This
    adapter owns authoritative Firestore reads/writes and never trusts caller
    snapshots for control state, operation state, or evidence/source state.
    """
    transaction = db_client.transaction()
    return _apply_long_term_patch_firestore_transaction(
        transaction,
        db_client,
        uid,
        operation_id,
        patch_payload,
    )


@transactional
def _apply_long_term_patch_firestore_transaction(
    transaction,
    db_client,
    uid: str,
    operation_id: str,
    patch_payload: Dict[str, Any],
) -> ApplyResult:
    collections = V17Collections(uid=uid)
    control_ref = db_client.document(collections.memory_control_state)
    operation_ref = db_client.document(f"{collections.memory_operations}/{operation_id}")

    control_state = _required_model(
        ref=control_ref,
        transaction=transaction,
        model=MemoryControlState,
        label="memory control state",
    )
    operation = _required_model(
        ref=operation_ref,
        transaction=transaction,
        model=MemoryOperation,
        label="memory operation",
    )
    if operation.uid != uid:
        raise V17FirestoreApplyError("operation uid does not match requested uid")
    if operation.operation_id != operation_id:
        raise V17FirestoreApplyError("operation_id does not match requested operation document")

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
        db_client=db_client,
        transaction=transaction,
        collections=collections,
        evidence_ids=operation.evidence_ids,
    )
    target_validation = _validate_authoritative_targets(
        db_client=db_client,
        transaction=transaction,
        collections=collections,
        operation=operation,
        control_state=control_state,
    )
    if target_validation is not None:
        _write_apply_result(
            transaction=transaction,
            db_client=db_client,
            collections=collections,
            operation_ref=operation_ref,
            result=target_validation,
        )
        return target_validation

    authoritative_payload = dict(patch_payload)
    authoritative_payload["evidence"] = evidence_items
    existing_item = _read_authoritative_target_item(
        db_client=db_client,
        transaction=transaction,
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
        transaction=transaction,
        db_client=db_client,
        collections=collections,
        operation_ref=operation_ref,
        result=result,
    )
    return result


def _read_authoritative_evidence(
    *,
    db_client,
    transaction,
    collections: V17Collections,
    evidence_ids: Iterable[str],
) -> List[MemoryEvidence]:
    evidence_items: List[MemoryEvidence] = []
    for evidence_id in evidence_ids:
        evidence_ref = db_client.document(f"{collections.memory_evidence}/{evidence_id}")
        evidence = _required_model(
            ref=evidence_ref,
            transaction=transaction,
            model=MemoryEvidence,
            label="memory evidence",
        )
        evidence_items.append(evidence)
    return evidence_items


def _read_authoritative_target_item(
    *,
    db_client,
    transaction,
    collections: V17Collections,
    operation: MemoryOperation,
) -> Optional[V17MemoryItem]:
    if operation.logical_payload.decision != DurablePatchDecision.update.value:
        return None
    target_id = operation.logical_payload.target_memory_id or operation.target_memory_id
    if not target_id:
        return None
    target_ref = db_client.document(f"{collections.memory_items}/{target_id}")
    snapshot = target_ref.get(transaction=transaction)
    if not snapshot.exists:
        return None
    return V17MemoryItem(**(snapshot.to_dict() or {}))


def _validate_authoritative_targets(
    *,
    db_client,
    transaction,
    collections: V17Collections,
    operation: MemoryOperation,
    control_state: MemoryControlState,
) -> Optional[ApplyResult]:
    target_ids = _operation_target_ids(operation)
    for target_id in target_ids:
        target_ref = db_client.document(f"{collections.memory_items}/{target_id}")
        snapshot = target_ref.get(transaction=transaction)
        if not snapshot.exists:
            return _target_not_active(control_state, operation, f"missing target memory item: {target_id}")
        target = V17MemoryItem(**(snapshot.to_dict() or {}))
        if target.uid != operation.uid:
            return _target_not_active(control_state, operation, "target memory uid mismatch")
        if target.account_generation != control_state.account_generation:
            return _target_not_active(control_state, operation, "target memory generation mismatch")
        if target.status != MemoryItemStatus.active:
            return _target_not_active(control_state, operation, "target memory is not active")
    return None


def _operation_target_ids(operation: MemoryOperation) -> List[str]:
    target_ids = []
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
    transaction,
    db_client,
    collections: V17Collections,
    operation_ref,
    result: ApplyResult,
) -> None:
    transaction.set(operation_ref, _firestore_data(result.operation))
    if result.status != ApplyStatus.committed:
        return

    control_ref = db_client.document(collections.memory_control_state)
    commit_ref = db_client.document(f"{collections.memory_commits}/{result.control_state.head_commit_id}")
    state_head_ref = db_client.document(collections.memory_state_head)
    transaction.set(control_ref, _firestore_data(result.control_state))
    transaction.set(state_head_ref, _firestore_data(_memory_state_head_from_control(result.control_state)))
    transaction.set(
        commit_ref,
        _firestore_data(
            {
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
        ),
    )
    for item in result.memory_items:
        item_ref = db_client.document(f"{collections.memory_items}/{item.memory_id}")
        transaction.set(item_ref, _firestore_data(item))
    for event in result.outbox_events:
        event_ref = db_client.document(f"{collections.memory_outbox}/{event.event_id}")
        transaction.set(event_ref, _firestore_data(event))


def _memory_state_head_from_control(control_state: MemoryControlState) -> Dict[str, Any]:
    return {
        "schema_version": V17_V3_TRUSTED_ACCOUNT_GENERATION_SCHEMA_VERSION,
        "uid": control_state.uid,
        "source": V17_V3_TRUSTED_ACCOUNT_GENERATION_SOURCE,
        "account_generation": control_state.account_generation,
        "head_commit_id": control_state.head_commit_id,
        "commit_sequence": control_state.commit_sequence,
        "updated_at": control_state.updated_at,
    }


def _required_model(*, ref, transaction, model, label: str):
    snapshot = ref.get(transaction=transaction)
    if not snapshot.exists:
        raise MissingV17Document(f"missing {label}: {ref.path}")
    data = snapshot.to_dict() or {}
    return model(**data)


def _firestore_data(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _firestore_data(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_firestore_data(item) for item in value]
    if isinstance(value, tuple):
        return [_firestore_data(item) for item in value]
    if isinstance(value, dict):
        return {key: _firestore_data(item) for key, item in value.items()}
    return value
