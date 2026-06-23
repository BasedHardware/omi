"""Canonical alias module for ``database.v17_memory_apply_store`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from database.v17_memory_apply_store import (
    MissingV17Document,
    V17FirestoreApplyError,
    apply_long_term_patch_firestore,
    atomic_bump_source_generation,
)

__all__ = [
    "MissingV17Document",
    "V17FirestoreApplyError",
    "apply_long_term_patch_firestore",
    "atomic_bump_source_generation",
]
