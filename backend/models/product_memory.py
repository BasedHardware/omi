"""Canonical alias module for ``models.v17_product_memory`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from models.v17_product_memory import (
    AccessDecision,
    MemoryAccessPolicy,
    MemoryConsumer,
    MemoryItemStatus,
    MemoryLayer,
    MemoryTier,
    ProcessingState,
    V17MemoryItem,
    V17MemoryItemAlias,
    is_archive_access_eligible,
    new_memory_id,
)

__all__ = [
    "AccessDecision",
    "MemoryAccessPolicy",
    "MemoryConsumer",
    "MemoryItemStatus",
    "MemoryLayer",
    "MemoryTier",
    "ProcessingState",
    "V17MemoryItem",
    "V17MemoryItemAlias",
    "is_archive_access_eligible",
    "new_memory_id",
]
