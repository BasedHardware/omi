"""Memory routing seam — WS-L will rewire callers to use MemoryService."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

import database.memories as memories_db
import database.vector_db as vector_db
from models.memories import MemoryDB
from utils.memory.memory_system import MemorySystem, resolve_memory_system

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemorySearchMatch:
    memory: MemoryDB
    score: float


def _validate_memory_list(memories: List[dict]) -> List[MemoryDB]:
    valid_memories: List[MemoryDB] = []
    for memory in memories:
        if memory.get("is_locked", False):
            content = memory.get("content", "")
            memory = dict(memory)
            memory["content"] = (content[:70] + "...") if len(content) > 70 else content
        try:
            valid_memories.append(MemoryDB.model_validate(memory))
        except ValidationError as exc:
            missing_fields = [err["loc"][0] for err in exc.errors() if err.get("loc")]
            logger.warning(
                "Skipping invalid memory doc %s: missing/invalid fields %s",
                memory.get("id", "unknown"),
                missing_fields,
            )
    return valid_memories


def _legacy_read_memories(uid: str, *, limit: int = 100, offset: int = 0) -> List[MemoryDB]:
    effective_limit = 5000 if offset == 0 else limit
    memories = memories_db.get_memories(uid, effective_limit, offset)
    return _validate_memory_list(memories)


def _legacy_search_memories(uid: str, query: str, *, limit: int = 5) -> List[MemorySearchMatch]:
    capped_limit = max(1, min(limit, 20))
    matches = vector_db.find_similar_memories(uid, query, threshold=0.0, limit=capped_limit)
    if not matches:
        return []

    memory_ids = [match.get("memory_id") for match in matches if match.get("memory_id")]
    scores_by_id = {match.get("memory_id"): float(match.get("score", 0) or 0) for match in matches}
    if not memory_ids:
        return []

    memories_data = memories_db.get_memories_by_ids(uid, memory_ids)
    memories_data = [memory for memory in memories_data if not memory.get("is_locked", False)]

    results: List[MemorySearchMatch] = []
    for memory_data in memories_data:
        memory_id = memory_data.get("id")
        try:
            memory_obj = MemoryDB.model_validate(memory_data)
        except ValidationError:
            continue
        results.append(MemorySearchMatch(memory=memory_obj, score=scores_by_id.get(memory_id, 0.0)))
    return results


class LegacyMemoryBackend:
    def read(self, uid: str, *, limit: int = 100, offset: int = 0) -> List[MemoryDB]:
        return _legacy_read_memories(uid, limit=limit, offset=offset)

    def search(self, uid: str, query: str, *, limit: int = 5) -> List[MemorySearchMatch]:
        return _legacy_search_memories(uid, query, limit=limit)

    def write(self, uid: str, data: Dict[str, Any]) -> None:
        memories_db.create_memory(uid, data)

    def delete(self, uid: str, memory_id: str) -> None:
        memories_db.delete_memory(uid, memory_id)

    def delete_all(self, uid: str) -> None:
        memories_db.delete_all_memories(uid)


class CanonicalMemoryBackend:
    _NOT_IMPLEMENTED = "canonical backend lands in WS-B/WS-C/WS-I"

    def read(self, uid: str, *, limit: int = 100, offset: int = 0) -> List[MemoryDB]:
        raise NotImplementedError(self._NOT_IMPLEMENTED)

    def search(self, uid: str, query: str, *, limit: int = 5) -> List[MemorySearchMatch]:
        raise NotImplementedError(self._NOT_IMPLEMENTED)

    def write(self, uid: str, data: Dict[str, Any]) -> None:
        raise NotImplementedError(self._NOT_IMPLEMENTED)

    def delete(self, uid: str, memory_id: str) -> None:
        raise NotImplementedError(self._NOT_IMPLEMENTED)

    def delete_all(self, uid: str) -> None:
        raise NotImplementedError(self._NOT_IMPLEMENTED)


class MemoryService:
    def __init__(self, *, db_client=None):
        self._db_client = db_client
        self._legacy = LegacyMemoryBackend()
        self._canonical = CanonicalMemoryBackend()

    def _resolve_backend(self, uid: str):
        system = resolve_memory_system(uid, db_client=self._db_client)
        if system == MemorySystem.CANONICAL:
            return self._canonical
        return self._legacy

    def read(self, uid: str, *, limit: int = 100, offset: int = 0) -> List[MemoryDB]:
        return self._resolve_backend(uid).read(uid, limit=limit, offset=offset)

    def search(self, uid: str, query: str, *, limit: int = 5) -> List[MemorySearchMatch]:
        return self._resolve_backend(uid).search(uid, query, limit=limit)

    def write(self, uid: str, data: Dict[str, Any]) -> None:
        self._resolve_backend(uid).write(uid, data)

    def delete(self, uid: str, memory_id: str) -> None:
        self._resolve_backend(uid).delete(uid, memory_id)

    def delete_all(self, uid: str) -> None:
        self._resolve_backend(uid).delete_all(uid)
