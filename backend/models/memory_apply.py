"""Canonical alias module for ``models.v17_memory_apply`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from models.v17_memory_apply import (
    ApplyResult,
    ApplyStatus,
    MemoryControlState,
    MemoryOutboxEvent,
    MemoryOutboxEventType,
    MemoryOutboxStatus,
    apply_long_term_patch_transaction,
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
