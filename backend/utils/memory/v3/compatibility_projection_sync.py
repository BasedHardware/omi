"""Normal-outbox writer for the enrolled ``/v3`` compatibility projection.

The projection state document is an enrollment/account-generation fence.  A
normal ``projection_sync`` delivery reuses those stable fences for one item
row, so updating one memory does not invalidate every other projected row.
Missing or malformed state fails closed for upserts; deletes remain safe and
idempotent even when the state document is unavailable.
"""

# LIFECYCLE: permanent

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, cast

from google.cloud.firestore_v1 import transactional as _firestore_transactional  # type: ignore[reportAssignmentType,reportUnknownMemberType]

from database.memory_collections import MemoryCollections
from models.product_memory import MemoryItem, RESTRICTED_SENSITIVITY_LABELS
from utils.memory.canonical_memory_adapter import memory_item_to_memorydb
from utils.memory.v3.projection_reader_contract import (
    V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
    V3_COMPATIBILITY_PROJECTION_SOURCE,
    V3_COMPATIBILITY_PROJECTION_VERSION,
)

ProjectionPayload = Dict[str, Any]


class CompatibilityProjectionSyncError(RuntimeError):
    """A sanitized retryable projection-state or write failure."""


def _snapshot_payload(snapshot: Any) -> Optional[ProjectionPayload]:
    if snapshot is None or getattr(snapshot, "exists", False) is False:
        return None
    raw: object = snapshot.to_dict()
    if not isinstance(raw, dict):
        raise CompatibilityProjectionSyncError("malformed_compatibility_projection_state")
    return cast(ProjectionPayload, raw)


def _required_nonnegative_int(payload: ProjectionPayload, field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CompatibilityProjectionSyncError("malformed_compatibility_projection_state")
    return value


def _required_nonblank_str(payload: ProjectionPayload, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CompatibilityProjectionSyncError("malformed_compatibility_projection_state")
    return value


def _validated_projection_fences(
    *,
    uid: str,
    account_generation: int,
    state: Optional[ProjectionPayload],
) -> ProjectionPayload:
    if state is None:
        raise CompatibilityProjectionSyncError("missing_compatibility_projection_state")
    if (
        state.get("uid") != uid
        or state.get("schema_version") != V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION
        or state.get("source") != V3_COMPATIBILITY_PROJECTION_SOURCE
        or state.get("ready") is not True
        or state.get("projection_version") != V3_COMPATIBILITY_PROJECTION_VERSION
    ):
        raise CompatibilityProjectionSyncError("malformed_compatibility_projection_state")

    stored_generation = _required_nonnegative_int(state, "account_generation")
    projection_generation = _required_nonnegative_int(state, "projection_generation")
    freshness_generation = _required_nonnegative_int(state, "freshness_fence_generation")
    tombstone_generation = _required_nonnegative_int(state, "tombstone_fence_generation")
    vector_cleanup_generation = _required_nonnegative_int(state, "vector_cleanup_fence_generation")
    if (
        stored_generation != account_generation
        or projection_generation != account_generation
        or freshness_generation != projection_generation
        or tombstone_generation != projection_generation
        or vector_cleanup_generation != projection_generation
    ):
        raise CompatibilityProjectionSyncError("compatibility_projection_generation_mismatch")

    source_commit_id = _required_nonblank_str(state, "source_commit_id")
    projection_commit_id = _required_nonblank_str(state, "projection_commit_id")
    projection_evidence_fence = _required_nonblank_str(state, "projection_evidence_fence")
    if not projection_commit_id.startswith("commit-"):
        raise CompatibilityProjectionSyncError("malformed_compatibility_projection_state")
    if _required_nonblank_str(state, "source_evidence_fence") != projection_evidence_fence:
        raise CompatibilityProjectionSyncError("malformed_compatibility_projection_state")
    if (
        state.get("write_convergence_complete") is not True
        or state.get("delete_convergence_complete") is not True
        or state.get("tombstone_convergence_complete") is not True
    ):
        raise CompatibilityProjectionSyncError("incomplete_compatibility_projection_state")
    _required_nonblank_str(state, "source_version")

    return {
        "account_generation": stored_generation,
        "projection_generation": projection_generation,
        "source_commit_id": source_commit_id,
        "projection_commit_id": projection_commit_id,
        "projection_evidence_fence": projection_evidence_fence,
        "freshness_fence_generation": freshness_generation,
        "tombstone_fence_generation": tombstone_generation,
    }


def _memorydb_projection_payload(item: MemoryItem) -> ProjectionPayload:
    memory = memory_item_to_memorydb(item)
    return {
        "id": memory.id,
        "uid": memory.uid,
        "content": memory.content,
        "category": memory.category.value,
        "visibility": memory.visibility or "private",
        "tags": list(memory.tags),
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
        "reviewed": memory.reviewed,
        "user_review": memory.user_review,
        "manually_added": memory.manually_added,
        "edited": memory.edited,
        "conversation_id": memory.conversation_id,
        "data_protection_level": memory.data_protection_level or "standard",
        "memory_tier": item.tier.value,
    }


def _projection_item_payload(item: MemoryItem, *, fences: ProjectionPayload) -> ProjectionPayload:
    return {
        "uid": item.uid,
        "memory_id": item.memory_id,
        "schema_version": V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
        "source": V3_COMPATIBILITY_PROJECTION_SOURCE,
        **fences,
        "write_convergence_complete": True,
        "delete_convergence_complete": True,
        "tombstone_convergence_complete": True,
        "created_at": item.captured_at,
        "memorydb": _memorydb_projection_payload(item),
    }


def _item_path(uid: str, memory_id: str) -> str:
    return f"{MemoryCollections(uid=uid).v3_compatibility_projection_items}/{memory_id}"


def _has_restricted_sensitivity(item: MemoryItem) -> bool:
    return bool(set(item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS))


def _run_transaction(db_client: Any, callback: Callable[..., bool], *args: Any) -> bool:
    transaction = db_client.transaction()
    if transaction.__class__.__module__.startswith("google.cloud.firestore"):
        wrapped = cast(Callable[..., bool], _firestore_transactional(callback))
        return wrapped(transaction, *args)

    if hasattr(transaction, "_begin"):
        transaction._begin()
    try:
        result = callback(transaction, *args)
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


def _upsert_projection_transaction(
    transaction: Any,
    db_client: Any,
    item: MemoryItem,
    expected_account_generation: int,
) -> bool:
    if item.account_generation != expected_account_generation:
        raise CompatibilityProjectionSyncError("compatibility_projection_generation_mismatch")
    paths = MemoryCollections(uid=item.uid)
    state_ref = db_client.document(paths.v3_compatibility_projection_state)
    state = _snapshot_payload(state_ref.get(transaction=transaction))
    fences = _validated_projection_fences(
        uid=item.uid,
        account_generation=expected_account_generation,
        state=state,
    )
    payload = _projection_item_payload(item, fences=fences)
    transaction.set(db_client.document(_item_path(item.uid, item.memory_id)), payload)
    return True


def upsert_v3_compatibility_projection_item(
    item: MemoryItem,
    *,
    expected_account_generation: int,
    db_client: Any,
) -> bool:
    """Idempotently project one authoritative, privacy-eligible memory item."""
    if _has_restricted_sensitivity(item):
        return delete_v3_compatibility_projection_item(
            item.uid,
            item.memory_id,
            expected_account_generation=expected_account_generation,
            db_client=db_client,
        )
    return _run_transaction(
        db_client,
        _upsert_projection_transaction,
        db_client,
        item,
        expected_account_generation,
    )


def _delete_projection_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
    memory_id: str,
    expected_account_generation: int,
) -> bool:
    paths = MemoryCollections(uid=uid)
    state_ref = db_client.document(paths.v3_compatibility_projection_state)
    state = _snapshot_payload(state_ref.get(transaction=transaction))
    if state is not None:
        _validated_projection_fences(
            uid=uid,
            account_generation=expected_account_generation,
            state=state,
        )
    transaction.delete(db_client.document(_item_path(uid, memory_id)))
    return True


def delete_v3_compatibility_projection_item(
    uid: str,
    memory_id: str,
    *,
    expected_account_generation: int,
    db_client: Any,
) -> bool:
    """Idempotently remove one compatibility row, including on privacy paths."""
    if not uid.strip() or not memory_id.strip():
        raise CompatibilityProjectionSyncError("compatibility_projection_identity_missing")
    return _run_transaction(
        db_client,
        _delete_projection_transaction,
        db_client,
        uid,
        memory_id,
        expected_account_generation,
    )


__all__ = [
    "CompatibilityProjectionSyncError",
    "delete_v3_compatibility_projection_item",
    "upsert_v3_compatibility_projection_item",
]
