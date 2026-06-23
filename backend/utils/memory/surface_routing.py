"""WS-L surface cohort pinning — resolve once per request, route canonical through MemoryService."""

from __future__ import annotations

from typing import List

from models.memories import MemoryDB
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.memory_system_pin import (
    clear_memory_system_pin,
    get_pinned_memory_system,
    memory_system_request_scope,
    pin_memory_system,
    resolve_pinned_memory_system,
)

__all__ = [
    "MemorySystem",
    "clear_memory_system_pin",
    "get_memory_service",
    "get_pinned_memory_system",
    "is_canonical_cohort",
    "memory_system_request_scope",
    "memorydb_list_with_locked_preview",
    "pin_memory_system",
    "resolve_pinned_memory_system",
    "truncate_locked_memory_content",
]


def is_canonical_cohort(uid: str, *, db_client=None) -> bool:
    return resolve_pinned_memory_system(uid, db_client=db_client) == MemorySystem.CANONICAL


def get_memory_service(*, db_client=None) -> MemoryService:
    return MemoryService(db_client=db_client)


def truncate_locked_memory_content(memory: MemoryDB) -> MemoryDB:
    """Mirror legacy locked-memory preview truncation."""
    if not memory.content:
        return memory
    content = memory.content
    if len(content) > 70:
        return memory.model_copy(update={"content": content[:70] + "..."})
    return memory


def memorydb_list_with_locked_preview(memories: List[MemoryDB]) -> List[MemoryDB]:
    return [truncate_locked_memory_content(memory) for memory in memories]
