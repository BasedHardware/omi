"""Backward-compatible shim — canonical definitions live in ``models.memory_apply`` (WS-G G6)."""

from models.memory_apply import (
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
