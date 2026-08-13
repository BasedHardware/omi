"""Dependency-free universal memory authority identity.

This module is intentionally safe for deployment/dev-harness resolvers that do
not install the backend's Firestore or Pydantic dependencies. Durable state
provisioning remains in :mod:`utils.memory.memory_system`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class MemorySystem(str, Enum):
    LEGACY = "legacy"
    CANONICAL = "canonical"


def validate_uid_for_memory_path(uid: object) -> str:
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError("uid must be a nonblank authenticated identifier")
    if "/" in uid:
        raise ValueError("uid must be a path-safe identifier")
    return uid


def resolve_memory_system(uid: object, *, db_client: Any = None) -> MemorySystem:
    """Return canonical authority for every valid authenticated UID."""
    del db_client
    if isinstance(uid, str) and uid.strip():
        return MemorySystem.CANONICAL
    # Invalid identity is not a legacy account. The legacy enum value remains
    # only as a compatibility sentinel for callers that reject malformed UIDs.
    return MemorySystem.LEGACY


__all__ = ["MemorySystem", "resolve_memory_system", "validate_uid_for_memory_path"]
