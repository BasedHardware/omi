"""WS-L surface cohort pinning — resolve once per request, route canonical through MemoryService."""

from __future__ import annotations

from typing import List, Optional

from models.memories import MemoryDB
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem, resolve_memory_system


def pin_memory_system(uid: str, *, db_client=None) -> MemorySystem:
    """Resolve and pin the memory cohort for one request / tool invocation."""
    return resolve_memory_system(uid, db_client=db_client)


def is_canonical_cohort(uid: str, *, db_client=None) -> bool:
    return pin_memory_system(uid, db_client=db_client) == MemorySystem.CANONICAL


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
