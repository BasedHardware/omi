"""Universal memory-system identity and apply-state provisioning helpers.

The enum is retained as a compatibility type for older call sites, but product
authority is no longer selected by a UID cohort.  Every authenticated, nonblank
UID resolves to the canonical system.  Invalid identity input is rejected by
callers before a Firestore path is constructed; it is never treated as an
entitled or legacy account.
"""

from __future__ import annotations

from typing import Any

from google.api_core.exceptions import AlreadyExists, Conflict

from database.account_deletion_projection_fence import (
    read_account_deletion_projection_fence,
)
from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState
from utils.memory.memory_authority import (
    MemorySystem,
    resolve_memory_system,
    validate_uid_for_memory_path,
)

MEMORY_SYSTEM_FIELD = "memory_system"

CANONICAL_MEMORY_MAINTENANCE_REGISTRY_COLLECTION = "canonical_memory_maintenance_registry"
CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH = "canonical_memory_maintenance_control/cursor"
CANONICAL_MEMORY_MAINTENANCE_REGISTRY_SCHEMA_VERSION = 1


class CanonicalApplyStateUnavailable(RuntimeError):
    """The canonical apply-control state cannot be safely read or provisioned."""


def ensure_canonical_apply_control_state(uid: str, *, db_client: Any) -> MemoryControlState:
    """Read or atomically self-provision the canonical apply control state.

    A missing state is the normal first-write path.  An existing malformed,
    cross-UID, or unreadable state fails closed so a producer cannot create a
    second ledger or fall back to historical writes.
    """
    validate_uid_for_memory_path(uid)
    if db_client is None:
        raise CanonicalApplyStateUnavailable("canonical apply control state requires a database client")

    # Account deletion (or a completed wipe marker) must not re-enroll maintenance
    # or recreate apply control under a fresh account_generation=1.
    try:
        deletion_fence = read_account_deletion_projection_fence(uid, db_client=db_client)
    except Exception as exc:
        raise CanonicalApplyStateUnavailable("canonical apply control state is unreadable") from exc
    if deletion_fence.blocks_projection_writes:
        raise CanonicalApplyStateUnavailable("canonical apply control refused during account deletion")

    ref = db_client.document(MemoryCollections(uid=uid).memory_apply_control_state)

    def _read_snapshot(target_ref: Any, *, unavailable_message: str) -> Any:
        try:
            return target_ref.get()
        except Exception as exc:
            raise CanonicalApplyStateUnavailable(unavailable_message) from exc

    def _read_existing() -> MemoryControlState:
        snapshot = _read_snapshot(
            ref,
            unavailable_message="canonical apply control state is unreadable",
        )
        if not getattr(snapshot, "exists", False):
            raise CanonicalApplyStateUnavailable("canonical apply control state disappeared during provisioning")
        try:
            payload = snapshot.to_dict()
            if not isinstance(payload, dict):
                raise ValueError("control payload must be an object")
            control = MemoryControlState.model_validate(payload)
        except Exception as exc:
            raise CanonicalApplyStateUnavailable("canonical apply control state is malformed") from exc
        if control.uid != uid:
            raise CanonicalApplyStateUnavailable("canonical apply control state uid mismatch")
        return control

    snapshot = _read_snapshot(
        ref,
        unavailable_message="canonical apply control state is unreadable",
    )
    if getattr(snapshot, "exists", False):
        control = _read_existing()
        _ensure_maintenance_registry_entry(uid, db_client=db_client)
        return control

    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    payload = control.model_dump(mode="json")
    try:
        create = getattr(ref, "create", None)
        if callable(create):
            create(payload)
        else:
            # Lightweight fakes often expose only set(); production Firestore
            # uses create() so a concurrent writer cannot be overwritten.
            ref.set(payload)
    except (AlreadyExists, Conflict):
        raced_control = _read_existing()
        _ensure_maintenance_registry_entry(uid, db_client=db_client)
        return raced_control
    _ensure_maintenance_registry_entry(uid, db_client=db_client)
    return control


def canonical_memory_maintenance_registry_path(uid: str) -> str:
    validate_uid_for_memory_path(uid)
    return f"{CANONICAL_MEMORY_MAINTENANCE_REGISTRY_COLLECTION}/{uid}"


def _ensure_maintenance_registry_entry(uid: str, *, db_client: Any) -> None:
    """Register a UID without storing content or entitlement metadata."""
    ref = db_client.document(canonical_memory_maintenance_registry_path(uid))
    try:
        snapshot = ref.get()
    except Exception as exc:
        raise CanonicalApplyStateUnavailable("canonical maintenance registry entry is unreadable") from exc
    expected = {
        "uid": uid,
        "schema_version": CANONICAL_MEMORY_MAINTENANCE_REGISTRY_SCHEMA_VERSION,
    }
    if getattr(snapshot, "exists", False):
        try:
            payload = snapshot.to_dict()
        except Exception as exc:
            raise CanonicalApplyStateUnavailable("canonical maintenance registry entry is unreadable") from exc
        if payload != expected:
            raise CanonicalApplyStateUnavailable("canonical maintenance registry entry is malformed")
        return
    try:
        create = getattr(ref, "create", None)
        if callable(create):
            create(expected)
        else:
            ref.set(expected)
    except (AlreadyExists, Conflict):
        try:
            snapshot = ref.get()
            payload = snapshot.to_dict() if getattr(snapshot, "exists", False) else None
        except Exception as exc:
            raise CanonicalApplyStateUnavailable("canonical maintenance registry entry is unreadable") from exc
        if payload != expected:
            raise CanonicalApplyStateUnavailable("canonical maintenance registry entry is malformed")


def delete_canonical_memory_maintenance_registry_entry(uid: str, *, db_client: Any) -> None:
    """Delete the content-free inventory marker during account wipe."""
    validate_uid_for_memory_path(uid)
    db_client.document(canonical_memory_maintenance_registry_path(uid)).delete()


__all__ = [
    "CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH",
    "CANONICAL_MEMORY_MAINTENANCE_REGISTRY_COLLECTION",
    "CANONICAL_MEMORY_MAINTENANCE_REGISTRY_SCHEMA_VERSION",
    "CanonicalApplyStateUnavailable",
    "MemorySystem",
    "ensure_canonical_apply_control_state",
    "canonical_memory_maintenance_registry_path",
    "delete_canonical_memory_maintenance_registry_entry",
    "resolve_memory_system",
]
