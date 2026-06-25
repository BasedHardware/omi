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
    memory_item_to_memorydb,
    read_canonical_memories,
    retract_conversation_sourced_memories,
    search_canonical_memories,
    search_result_to_memorydb,
    update_canonical_memory_content,
    update_canonical_memory_visibility,
    update_canonical_memory_product_fields,
    update_canonical_memory_review,
    write_canonical_extraction_memory,
    write_canonical_external_memory,
)
from utils.memory.memory_system import MemorySystem
from utils.memory.memory_system_pin import resolve_pinned_memory_system
from utils.retrieval.hybrid import rrf_rerank

logger = logging.getLogger(__name__)


class DeviceScopeNotSupportedError(ValueError):
    """device_scope filtering is only supported on the canonical memory backend."""


def _reject_legacy_device_scope(device_scope: str) -> None:
    if device_scope and device_scope != "all":
        raise DeviceScopeNotSupportedError("device_scope filtering is only supported for canonical memory users")


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
    def read(
        self,
        uid: str,
        *,
        limit: int = 100,
        offset: int = 0,
        device_scope: str = "all",
        client_device_id: Optional[str] = None,
    ) -> List[MemoryDB]:
        _reject_legacy_device_scope(device_scope)
        return _legacy_read_memories(uid, limit=limit, offset=offset)

    def search(
        self,
        uid: str,
        query: str,
        *,
        limit: int = 5,
        device_scope: str = "all",
        client_device_id: Optional[str] = None,
    ) -> List[MemorySearchMatch]:
        _reject_legacy_device_scope(device_scope)
        return _legacy_search_memories(uid, query, limit=limit)

    def write(self, uid: str, data: Dict[str, Any]) -> str:
        memories_db.create_memory(uid, data)
        return str(data.get("id") or "")

    def review(self, uid: str, memory_id: str, value: bool) -> None:
        memories_db.review_memory(uid, memory_id, value)

    def update_product_fields(
        self,
        uid: str,
        memory_id: str,
        *,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
    ) -> MemoryDB:
        update_data: Dict[str, Any] = {}
        if tags is not None:
            update_data["tags"] = tags
        if category is not None:
            update_data["category"] = category
        if update_data:
            memories_db.update_memory_fields(uid, memory_id, update_data)
        memory = memories_db.get_memory(uid, memory_id)
        return MemoryDB.model_validate(memory)

    def write_batch(self, uid: str, items: List[Dict[str, Any]]) -> List[str]:
        memories_db.save_memories(uid, items)
        return [str(item.get("id") or "") for item in items]

    def update_content(self, uid: str, memory_id: str, content: str) -> MemoryDB:
        memories_db.edit_memory(uid, memory_id, content)
        memory = memories_db.get_memory(uid, memory_id)
        return MemoryDB.model_validate(memory)

    def update_visibility(self, uid: str, memory_id: str, visibility: str) -> None:
        memories_db.change_memory_visibility(uid, memory_id, visibility)

    def delete(self, uid: str, memory_id: str) -> None:
        memories_db.delete_memory(uid, memory_id)

    def delete_all(self, uid: str) -> None:
        memories_db.delete_all_memories(uid)


class CanonicalMemoryBackend:
    def __init__(self, *, db_client=None):
        self._db_client = db_client

    def read(
        self,
        uid: str,
        *,
        limit: int = 100,
        offset: int = 0,
        device_scope: str = "all",
        client_device_id: Optional[str] = None,
    ) -> List[MemoryDB]:
        return read_canonical_memories(
            uid,
            limit=limit,
            offset=offset,
            db_client=self._db_client,
            device_scope=device_scope,
            client_device_id=client_device_id,
        )

    def search(
        self, uid: str, query: str, *, limit: int = 5, device_scope: str = "all", client_device_id: Optional[str] = None
    ) -> List[MemorySearchMatch]:
        items = search_canonical_memories(
            uid,
            query,
            limit=limit,
            db_client=self._db_client,
            device_scope=device_scope,
            client_device_id=client_device_id,
        )
        results: List[MemorySearchMatch] = []
        for item in items:
            if not item.get("memory_id"):
                continue
            memory_obj = search_result_to_memorydb(uid, item)
            results.append(MemorySearchMatch(memory=memory_obj, score=1.0))
        return results

    def write(self, uid: str, data: Dict[str, Any]) -> str:
        return write_canonical_external_memory(uid, data, db_client=self._db_client)

    def review(self, uid: str, memory_id: str, value: bool) -> None:
        update_canonical_memory_review(uid, memory_id, value, db_client=self._db_client)

    def update_product_fields(
        self,
        uid: str,
        memory_id: str,
        *,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
    ) -> MemoryDB:
        item = update_canonical_memory_product_fields(
            uid,
            memory_id,
            tags=tags,
            category=category,
            db_client=self._db_client,
        )
        return memory_item_to_memorydb(item)

    def write_batch(self, uid: str, items: List[Dict[str, Any]]) -> List[str]:
        return [self.write(uid, item) for item in items]

    def update_content(self, uid: str, memory_id: str, content: str) -> MemoryDB:
        item = update_canonical_memory_content(uid, memory_id, content, db_client=self._db_client)
        return memory_item_to_memorydb(item)

    def update_visibility(self, uid: str, memory_id: str, visibility: str) -> None:
        update_canonical_memory_visibility(uid, memory_id, visibility, db_client=self._db_client)

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
        system = resolve_pinned_memory_system(uid, db_client=self._db_client)
        if system == MemorySystem.CANONICAL:
            return self._canonical
        return self._legacy

    def read(
        self,
        uid: str,
        *,
        limit: int = 100,
        offset: int = 0,
        device_scope: str = "all",
        client_device_id: Optional[str] = None,
    ) -> List[MemoryDB]:
        return self._resolve_backend(uid).read(
            uid,
            limit=limit,
            offset=offset,
            device_scope=device_scope,
            client_device_id=client_device_id,
        )

    def search(
        self,
        uid: str,
        query: str,
        *,
        limit: int = 5,
        device_scope: str = "all",
        client_device_id: Optional[str] = None,
    ) -> List[MemorySearchMatch]:
        return self._resolve_backend(uid).search(
            uid,
            query,
            limit=limit,
            device_scope=device_scope,
            client_device_id=client_device_id,
        )

    def search_mcp(self, uid: str, query: str, *, limit: int = 5) -> List[dict]:
        """MCP-shaped search results (legacy parity filters + RRF, or canonical keyword)."""
        if resolve_pinned_memory_system(uid, db_client=self._db_client) == MemorySystem.CANONICAL:
            return _canonical_search_memories_mcp(uid, query, limit=limit, db_client=self._db_client)
        return _legacy_search_memories_mcp(uid, query, limit=limit)

    def write(self, uid: str, data: Dict[str, Any]) -> str:
        return self._resolve_backend(uid).write(uid, data)

    def write_batch(self, uid: str, items: List[Dict[str, Any]]) -> List[str]:
        return self._resolve_backend(uid).write_batch(uid, items)

    def update_content(self, uid: str, memory_id: str, content: str) -> MemoryDB:
        return self._resolve_backend(uid).update_content(uid, memory_id, content)

    def update_visibility(self, uid: str, memory_id: str, visibility: str) -> None:
        self._resolve_backend(uid).update_visibility(uid, memory_id, visibility)

    def review(self, uid: str, memory_id: str, value: bool) -> None:
        self._resolve_backend(uid).review(uid, memory_id, value)

    def update_product_fields(
        self,
        uid: str,
        memory_id: str,
        *,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
    ) -> MemoryDB:
        return self._resolve_backend(uid).update_product_fields(uid, memory_id, tags=tags, category=category)

    def delete(self, uid: str, memory_id: str) -> None:
        self._resolve_backend(uid).delete(uid, memory_id)

    def delete_all(self, uid: str) -> None:
        self._resolve_backend(uid).delete_all(uid)

    def retract_conversation_memories(self, uid: str, conversation_id: str) -> Optional[Dict[str, Any]]:
        if resolve_pinned_memory_system(uid, db_client=self._db_client) != MemorySystem.CANONICAL:
            return None
        return retract_conversation_sourced_memories(uid, conversation_id, db_client=self._db_client)
