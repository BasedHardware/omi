"""Backward-compatible shim — canonical definitions live in ``models.product_memory`` (WS-G G6)."""

from models.product_memory import (
    AccessDecision,
    MemoryAccessPolicy,
    MemoryConsumer,
    MemoryItem,
    MemoryItemAlias,
    MemoryItemStatus,
    MemoryLayer,
    MemoryTier,
    ProcessingState,
    V17MemoryItem,
    V17MemoryItemAlias,
    derived_default_access_allowed,
    is_archive_access_eligible,
    is_default_access_eligible,
    new_memory_id,
)

__all__ = [
    "AccessDecision",
    "MemoryAccessPolicy",
    "MemoryConsumer",
    "MemoryItem",
    "MemoryItemAlias",
    "MemoryItemStatus",
    "MemoryLayer",
    "MemoryTier",
    "ProcessingState",
    "V17MemoryItem",
    "V17MemoryItemAlias",
    "derived_default_access_allowed",
    "is_archive_access_eligible",
    "is_default_access_eligible",
    "new_memory_id",
]
