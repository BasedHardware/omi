"""WS-L surface cohort pinning — resolve once per request, route canonical through MemoryService."""

from __future__ import annotations

from typing import List

from models.memories import MemoryDB
from utils.memory.memory_service import truncate_locked_memory_preview
from utils.memory.memory_system_pin import pin_memory_system

__all__ = [
    "memorydb_list_with_locked_preview",
    "pin_memory_system",
    "truncate_locked_memory_content",
]


def truncate_locked_memory_content(memory: MemoryDB) -> MemoryDB:
    """Mirror legacy locked-memory preview truncation."""
    return truncate_locked_memory_preview(memory)


def memorydb_list_with_locked_preview(memories: List[MemoryDB]) -> List[MemoryDB]:
    return [truncate_locked_memory_content(memory) for memory in memories]
