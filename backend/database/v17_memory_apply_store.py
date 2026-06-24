"""Backward-compatible shim — implementation lives in ``database.memory_apply_store`` (WS-G7)."""

from database.memory_apply_store import (
    MemoryFirestoreApplyError,
    MissingV17Document,
    V17FirestoreApplyError,
    apply_long_term_patch_firestore,
    atomic_bump_source_generation,
)

__all__ = [
    "MemoryFirestoreApplyError",
    "MissingV17Document",
    "V17FirestoreApplyError",
    "apply_long_term_patch_firestore",
    "atomic_bump_source_generation",
]
