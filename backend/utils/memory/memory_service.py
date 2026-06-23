"""Memory routing seam — surfaces route reads/writes/search through MemoryService (WS-L)."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

import database.memories as memories_db
import database.vector_db as vector_db
from models.memories import MemoryDB
from utils.memory.canonical_memory_adapter import (
    delete_all_canonical_memories,
    delete_canonical_memory,
    read_canonical_memories,
    retract_conversation_sourced_memories,
    search_canonical_memories,
    search_result_to_memorydb,
    write_canonical_extraction_memory,
)
from utils.memory.memory_system import MemorySystem, resolve_memory_system
from utils.retrieval.hybrid import rrf_rerank

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


def _legacy_search_memories_mcp(uid: str, query: str, *, limit: int = 5) -> List[dict]:
    """Legacy MCP search path: over-fetch, filter, RRF rerank (Wave 2 cf#1 parity)."""
    capped_limit = max(1, min(limit, 20))
    fetch_limit = min(capped_limit * 3, 60)
    matches = vector_db.find_similar_memories(uid, query, threshold=0.0, limit=fetch_limit)
    if not matches:
        return []

    memory_ids = [match.get("memory_id") for match in matches if match.get("memory_id")]
    scores = {match.get("memory_id"): float(match.get("score", 0) or 0) for match in matches}
    if not memory_ids:
        return []

    docs = {memory.get("id"): memory for memory in memories_db.get_memories_by_ids(uid, memory_ids)}

    candidates = []
    for memory_id in memory_ids:
        memory = docs.get(memory_id)
        if not memory:
            continue
        if memory.get("user_review") is False or memory.get("is_locked", False) or memory.get("invalid_at") is not None:
            continue
        candidates.append(
            {
                "id": memory.get("id", ""),
                "content": memory.get("content", ""),
                "category": memory.get("category", "other"),
                "vector_score": scores.get(memory_id, 0),
            }
        )

    candidates.sort(key=lambda candidate: candidate.get("vector_score", 0), reverse=True)
    reranked = rrf_rerank(query, candidates, capped_limit)
    return [
        {
            "id": candidate["id"],
            "content": candidate["content"],
            "category": candidate["category"],
            "relevance_score": round(candidate.get("vector_score", 0), 4),
        }
        for candidate in reranked
    ]


def _canonical_search_memories_mcp(uid: str, query: str, *, limit: int = 5, db_client=None) -> List[dict]:
    capped_limit = max(1, min(limit, 20))
    items = search_canonical_memories(uid, query, limit=capped_limit, db_client=db_client)
    formatted = []
    for rank, item in enumerate(items):
        formatted.append(
            {
                "id": item["memory_id"],
                "content": item.get("content") or "",
                "category": "other",
                "relevance_score": round(1.0 - (rank * 0.0001), 4),
            }
        )
    return formatted


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
    def __init__(self, *, db_client=None):
        self._db_client = db_client

    def read(self, uid: str, *, limit: int = 100, offset: int = 0) -> List[MemoryDB]:
        return read_canonical_memories(uid, limit=limit, offset=offset, db_client=self._db_client)

    def search(self, uid: str, query: str, *, limit: int = 5) -> List[MemorySearchMatch]:
        items = search_canonical_memories(uid, query, limit=limit, db_client=self._db_client)
        results: List[MemorySearchMatch] = []
        for item in items:
            if not item.get("memory_id"):
                continue
            memory_obj = search_result_to_memorydb(uid, item)
            results.append(MemorySearchMatch(memory=memory_obj, score=1.0))
        return results

    def write(self, uid: str, data: Dict[str, Any]) -> None:
        write_canonical_extraction_memory(uid, data, db_client=self._db_client)

    def delete(self, uid: str, memory_id: str) -> None:
        delete_canonical_memory(uid, memory_id, db_client=self._db_client)

    def delete_all(self, uid: str) -> None:
        delete_all_canonical_memories(uid, db_client=self._db_client)


class MemoryService:
    def __init__(self, *, db_client=None):
        self._db_client = db_client
        self._legacy = LegacyMemoryBackend()
        self._canonical = CanonicalMemoryBackend(db_client=db_client)

    def _resolve_backend(self, uid: str):
        system = resolve_memory_system(uid, db_client=self._db_client)
        if system == MemorySystem.CANONICAL:
            return self._canonical
        return self._legacy

    def read(self, uid: str, *, limit: int = 100, offset: int = 0) -> List[MemoryDB]:
        return self._resolve_backend(uid).read(uid, limit=limit, offset=offset)

    def search(self, uid: str, query: str, *, limit: int = 5) -> List[MemorySearchMatch]:
        return self._resolve_backend(uid).search(uid, query, limit=limit)

    def search_mcp(self, uid: str, query: str, *, limit: int = 5) -> List[dict]:
        """MCP-shaped search results (legacy parity filters + RRF, or canonical keyword)."""
        if resolve_memory_system(uid, db_client=self._db_client) == MemorySystem.CANONICAL:
            return _canonical_search_memories_mcp(uid, query, limit=limit, db_client=self._db_client)
        return _legacy_search_memories_mcp(uid, query, limit=limit)

    def write(self, uid: str, data: Dict[str, Any]) -> None:
        self._resolve_backend(uid).write(uid, data)

    def delete(self, uid: str, memory_id: str) -> None:
        self._resolve_backend(uid).delete(uid, memory_id)

    def delete_all(self, uid: str) -> None:
        self._resolve_backend(uid).delete_all(uid)

    def retract_conversation_memories(self, uid: str, conversation_id: str) -> Optional[Dict[str, Any]]:
        if resolve_memory_system(uid, db_client=self._db_client) != MemorySystem.CANONICAL:
            return None
        return retract_conversation_sourced_memories(uid, conversation_id, db_client=self._db_client)
