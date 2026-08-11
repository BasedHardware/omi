"""Universal memory-system identity and apply-state provisioning helpers.

The enum is retained as a compatibility type for older call sites, but product
authority is no longer selected by a UID cohort.  Every authenticated, nonblank
UID resolves to the canonical system.  Invalid identity input is rejected by
callers before a Firestore path is constructed; it is never treated as an
entitled or legacy account.
"""

from enum import Enum
from typing import Any

from google.api_core.exceptions import AlreadyExists, Conflict

from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState

MEMORY_SYSTEM_FIELD = "memory_system"

CANONICAL_MEMORY_MAINTENANCE_REGISTRY_COLLECTION = "canonical_memory_maintenance_registry"
CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH = "canonical_memory_maintenance_control/cursor"
CANONICAL_MEMORY_MAINTENANCE_REGISTRY_SCHEMA_VERSION = 1


class MemorySystem(str, Enum):
    LEGACY = "legacy"
    CANONICAL = "canonical"


def resolve_memory_system(uid: object, *, db_client: Any = None) -> MemorySystem:
    """Return canonical authority for every valid authenticated UID.

    ``db_client`` remains accepted so request-scoped callers do not need a
    compatibility migration.  Control/readiness and integrity failures belong
    to the operation that touches state; they must not silently route an
    account to a legacy writer.
    """
    del db_client
    if isinstance(uid, str) and uid.strip():
        return MemorySystem.CANONICAL
    # Invalid identity is not a legacy account.  The legacy enum value is kept
    # only as a sentinel for callers that already reject malformed identities.
    return MemorySystem.LEGACY


def ensure_canonical_apply_control_state(uid: str, *, db_client: Any) -> MemoryControlState:
    """Read or atomically self-provision the canonical apply control state.

    A missing state is the normal first-write path.  An existing malformed,
    cross-UID, or unreadable state fails closed so a producer cannot create a
    second ledger or fall back to historical writes.
    """
    if not uid.strip():
        raise ValueError("uid must be a nonblank authenticated identifier")
    if db_client is None:
        raise RuntimeError("canonical apply control state requires a database client")

    ref = db_client.document(MemoryCollections(uid=uid).memory_apply_control_state)

    def _read_existing() -> MemoryControlState:
        snapshot = ref.get()
        if not getattr(snapshot, "exists", False):
            raise RuntimeError("canonical apply control state disappeared during provisioning")
        try:
            payload = snapshot.to_dict()
            if not isinstance(payload, dict):
                raise ValueError("control payload must be an object")
            control = MemoryControlState.model_validate(payload)
        except Exception as exc:
            raise RuntimeError("canonical apply control state is malformed") from exc
        if control.uid != uid:
            raise RuntimeError("canonical apply control state uid mismatch")
        return control

    snapshot = ref.get()
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
    if not uid.strip() or "/" in uid:
        raise ValueError("uid must be a nonblank path-safe identifier")
    return f"{CANONICAL_MEMORY_MAINTENANCE_REGISTRY_COLLECTION}/{uid}"


def _ensure_maintenance_registry_entry(uid: str, *, db_client: Any) -> None:
    """Register a UID without storing content or entitlement metadata."""
    ref = db_client.document(canonical_memory_maintenance_registry_path(uid))
    snapshot = ref.get()
    expected = {
        "uid": uid,
        "schema_version": CANONICAL_MEMORY_MAINTENANCE_REGISTRY_SCHEMA_VERSION,
    }
    if getattr(snapshot, "exists", False):
        try:
            payload = snapshot.to_dict()
        except Exception as exc:
            raise RuntimeError("canonical maintenance registry entry is unreadable") from exc
        if payload != expected:
            raise RuntimeError("canonical maintenance registry entry is malformed")
        return
    try:
        create = getattr(ref, "create", None)
        if callable(create):
            create(expected)
        else:
            ref.set(expected)
    except (AlreadyExists, Conflict):
        snapshot = ref.get()
        if not getattr(snapshot, "exists", False) or snapshot.to_dict() != expected:
            raise RuntimeError("canonical maintenance registry entry is malformed")


def delete_canonical_memory_maintenance_registry_entry(uid: str, *, db_client: Any) -> None:
    """Delete the content-free inventory marker during account wipe."""
    if not uid.strip() or "/" in uid:
        raise ValueError("uid must be a nonblank path-safe identifier")
    db_client.document(canonical_memory_maintenance_registry_path(uid)).delete()


__all__ = [
    "CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH",
    "CANONICAL_MEMORY_MAINTENANCE_REGISTRY_COLLECTION",
    "CANONICAL_MEMORY_MAINTENANCE_REGISTRY_SCHEMA_VERSION",
    "MemorySystem",
    "ensure_canonical_apply_control_state",
    "canonical_memory_maintenance_registry_path",
    "delete_canonical_memory_maintenance_registry_entry",
    "resolve_memory_system",
]
