"""Memory routing seam — surfaces route reads/writes/search through MemoryService (WS-L)."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from fastapi import HTTPException
from pydantic import ValidationError

import database.memories as memories_db
import database.vector_db as vector_db
from database.vector_db import delete_memory_vector, upsert_memory_vector, upsert_memory_vectors_batch
from models.memories import MemoryDB
from utils.memory.canonical_memory_adapter import (
    delete_all_canonical_memories,
    delete_canonical_memory,
    memory_item_to_memorydb,
    read_canonical_memory_item,
    read_canonical_memories,
    retract_conversation_sourced_memories,
    search_canonical_memories,
    search_result_to_memorydb,
    update_canonical_memory_content,
    update_canonical_memory_visibility,
    update_canonical_memory_product_fields,
    update_canonical_memory_review,
    write_canonical_external_memory,
)
from utils.memory.required_promotion import required_processing_payload
from utils.client_device import DeviceScopeRequest
from utils.memory.canonical_activation import canonical_read_enabled, canonical_write_decision
from utils.memory.memory_system import MemorySystem
from utils.memory.default_read_rollout import guard_legacy_memory_write
from utils.memory.memory_api_contract import MemoryApiExposure, memory_api_payload, memory_write_payload
from utils.retrieval.hybrid import rrf_rerank

logger = logging.getLogger(__name__)

MemoryPayload = Dict[str, Any]
McpSearchPayload = Dict[str, Any]


class DeviceScopeNotSupportedError(ValueError):
    """device_scope filtering is only supported on the canonical memory backend."""


@dataclass(frozen=True)
class ExternalMemoryWriteContext:
    """Resolved cohort + legacy-write guard context for external memory mutations."""

    memory_system: MemorySystem
    legacy_write_allowed: bool = True
    legacy_write_status_code: int = 200
    legacy_write_detail: Any = None


def _require_legacy_write_guard(uid: str, db_client: Any, *, consumer: str, operation: str) -> None:
    write_guard = guard_legacy_memory_write(uid, db_client, consumer=consumer, operation=operation)
    if not write_guard.allowed:
        raise HTTPException(status_code=write_guard.status_code, detail=write_guard.detail)


def _canonical_external_write_enabled_or_fail_closed(uid: str, db_client: Any) -> bool:
    decision = canonical_write_decision(uid, db_client=db_client)
    if decision.enabled:
        return True
    if decision.fail_closed:
        raise HTTPException(status_code=503, detail={"reason": decision.reason, "memory_system": "canonical"})
    return False


def resolve_external_memory_write_context(
    uid: str,
    *,
    db_client: Any,
    memory_system: MemorySystem,
    consumer: str,
    operation: str,
) -> ExternalMemoryWriteContext:
    if memory_system == MemorySystem.CANONICAL and _canonical_external_write_enabled_or_fail_closed(uid, db_client):
        return ExternalMemoryWriteContext(memory_system=memory_system)
    write_guard = guard_legacy_memory_write(uid, db_client, consumer=consumer, operation=operation)
    return ExternalMemoryWriteContext(
        memory_system=MemorySystem.LEGACY,
        legacy_write_allowed=write_guard.allowed,
        legacy_write_status_code=write_guard.status_code,
        legacy_write_detail=write_guard.detail,
    )


def raise_if_legacy_write_blocked(context: ExternalMemoryWriteContext) -> None:
    if not context.legacy_write_allowed:
        raise HTTPException(status_code=context.legacy_write_status_code, detail=context.legacy_write_detail)


def _truncate_locked_preview_text(content: str) -> str:
    if len(content) > 70:
        return content[:70] + "..."
    return content


def truncate_locked_memory_preview(memory: MemoryDB) -> MemoryDB:
    """Truncate locked-memory content to the legacy 70-char preview."""
    if not memory.content:
        return memory
    truncated = _truncate_locked_preview_text(memory.content)
    if truncated == memory.content:
        return memory
    return memory.model_copy(update={"content": truncated})


def _legacy_memorydb(value: MemoryDB | Dict[str, Any]) -> MemoryDB:
    """Normalize one legacy memory object so direct route serialization stays untiered."""
    if isinstance(value, MemoryDB):
        return value.model_copy(update={"memory_tier": None})
    payload = memory_api_payload(value, MemoryApiExposure.LEGACY)
    memory = MemoryDB.model_validate(payload)
    return memory.model_copy(update={"memory_tier": None})


def fetch_memory_dict(uid: str, memory_id: str, *, db_client: Any) -> MemoryPayload:
    """Fetch one memory by id with canonical/legacy routing and locked-memory paywall."""
    if canonical_read_enabled(uid, db_client=db_client):
        item = read_canonical_memory_item(uid, memory_id, db_client=db_client)
        if item is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return memory_item_to_memorydb(item).dict()

    memory = memories_db.get_memory(uid, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    if memory.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")

    return memory_api_payload(memory, MemoryApiExposure.LEGACY)


def _reject_legacy_device_scope(device_scope_request: Optional[DeviceScopeRequest]) -> None:
    scope = device_scope_request.device_scope if device_scope_request else "all"
    if scope and scope != "all":
        raise DeviceScopeNotSupportedError("device_scope filtering is only supported for canonical memory users")


@dataclass(frozen=True)
class MemorySearchMatch:
    memory: MemoryDB
    score: float


def _validate_memory_list(memories: List[MemoryPayload]) -> List[MemoryDB]:
    valid_memories: List[MemoryDB] = []
    for memory in memories:
        memory = memory_api_payload(memory, MemoryApiExposure.LEGACY)
        if memory.get("is_locked", False):
            content = memory.get("content", "")
            memory = dict(memory)
            memory["content"] = _truncate_locked_preview_text(content)
        try:
            valid_memories.append(_legacy_memorydb(memory))
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


def _memory_ids_and_scores(matches: List[MemoryPayload]) -> tuple[List[str], Dict[str, float]]:
    memory_ids: List[str] = []
    scores_by_id: Dict[str, float] = {}
    for match in matches:
        memory_id = match.get("memory_id")
        if not isinstance(memory_id, str) or not memory_id:
            continue
        memory_ids.append(memory_id)
        scores_by_id[memory_id] = float(match.get("score") or 0)
    return memory_ids, scores_by_id


def _legacy_search_memories(uid: str, query: str, *, limit: int = 5) -> List[MemorySearchMatch]:
    capped_limit = max(1, min(limit, 20))
    matches = vector_db.find_similar_memories(uid, query, threshold=0.0, limit=capped_limit)
    if not matches:
        return []

    memory_ids, scores_by_id = _memory_ids_and_scores(matches)
    if not memory_ids:
        return []

    memories_data = memories_db.get_memories_by_ids(uid, memory_ids)
    memories_data = [
        memory_api_payload(memory, MemoryApiExposure.LEGACY)
        for memory in memories_data
        if not memory.get("is_locked", False)
    ]

    results: List[MemorySearchMatch] = []
    for memory_data in memories_data:
        memory_id = memory_data.get("id")
        if not isinstance(memory_id, str):
            continue
        try:
            memory_obj = _legacy_memorydb(memory_data)
        except ValidationError:
            continue
        results.append(MemorySearchMatch(memory=memory_obj, score=scores_by_id.get(memory_id, 0.0)))
    return results


def _legacy_search_memories_mcp(uid: str, query: str, *, limit: int = 5) -> List[McpSearchPayload]:
    """Legacy MCP search path: over-fetch, filter, RRF rerank (Wave 2 cf#1 parity)."""
    capped_limit = max(1, min(limit, 20))
    fetch_limit = min(capped_limit * 3, 60)
    matches = vector_db.find_similar_memories(uid, query, threshold=0.0, limit=fetch_limit)
    if not matches:
        return []

    memory_ids, scores = _memory_ids_and_scores(matches)
    if not memory_ids:
        return []

    docs: Dict[str, MemoryPayload] = {}
    for memory in memories_db.get_memories_by_ids(uid, memory_ids):
        memory_id = memory.get("id")
        if isinstance(memory_id, str) and memory_id:
            docs[memory_id] = memory

    candidates: List[McpSearchPayload] = []
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


def _canonical_search_memories_mcp(
    uid: str, query: str, *, limit: int = 5, db_client: Any = None
) -> List[McpSearchPayload]:
    capped_limit = max(1, min(limit, 20))
    items = search_canonical_memories(uid, query, limit=capped_limit, db_client=db_client)
    formatted: List[McpSearchPayload] = []
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
        device_scope_request: Optional[DeviceScopeRequest] = None,
        include_pending_processing: bool = False,
        now: Optional[datetime] = None,
    ) -> List[MemoryDB]:
        _reject_legacy_device_scope(device_scope_request)
        return _legacy_read_memories(uid, limit=limit, offset=offset)

    def search(
        self,
        uid: str,
        query: str,
        *,
        limit: int = 5,
        device_scope_request: Optional[DeviceScopeRequest] = None,
    ) -> List[MemorySearchMatch]:
        _reject_legacy_device_scope(device_scope_request)
        return _legacy_search_memories(uid, query, limit=limit)

    def write(self, uid: str, data: Dict[str, Any]) -> str:
        memories_db.create_memory(uid, memory_write_payload(data, MemoryApiExposure.LEGACY))
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
        return _legacy_memorydb(cast(MemoryPayload, memories_db.get_memory(uid, memory_id)))

    def write_batch(self, uid: str, items: List[Dict[str, Any]]) -> List[str]:
        memories_db.save_memories(uid, [memory_write_payload(item, MemoryApiExposure.LEGACY) for item in items])
        return [str(item.get("id") or "") for item in items]

    def update_content(self, uid: str, memory_id: str, content: str) -> MemoryDB:
        memories_db.edit_memory(uid, memory_id, content)
        return _legacy_memorydb(cast(MemoryPayload, memories_db.get_memory(uid, memory_id)))

    def update_visibility(self, uid: str, memory_id: str, visibility: str) -> None:
        memories_db.change_memory_visibility(uid, memory_id, visibility)

    def delete(self, uid: str, memory_id: str) -> None:
        memories_db.delete_memory(uid, memory_id)

    def delete_all(self, uid: str) -> None:
        memories_db.delete_all_memories(uid)


class CanonicalMemoryBackend:
    def __init__(self, *, db_client: Any = None):
        self._db_client = db_client

    def read(
        self,
        uid: str,
        *,
        limit: int = 100,
        offset: int = 0,
        device_scope_request: Optional[DeviceScopeRequest] = None,
        include_pending_processing: bool = False,
        now: Optional[datetime] = None,
    ) -> List[MemoryDB]:
        return read_canonical_memories(
            uid,
            limit=limit,
            offset=offset,
            db_client=self._db_client,
            device_scope_request=device_scope_request,
            include_pending_processing=include_pending_processing,
            now=now,
        )

    def search(
        self, uid: str, query: str, *, limit: int = 5, device_scope_request: Optional[DeviceScopeRequest] = None
    ) -> List[MemorySearchMatch]:
        items = search_canonical_memories(
            uid,
            query,
            limit=limit,
            db_client=self._db_client,
            device_scope_request=device_scope_request,
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
    def __init__(self, *, db_client: Any = None):
        self._db_client = db_client
        self._legacy = LegacyMemoryBackend()
        self._canonical = CanonicalMemoryBackend(db_client=db_client)

    def _resolve_mutation_backend(self, uid: str):
        """Return the only store a mutation may affect for this account.

        Canonical selection is sticky for mutations: a temporarily unavailable
        canonical control/write gate is retryable, not permission to create or
        modify a legacy row. Legacy accounts retain their existing behavior.
        """

        decision = canonical_write_decision(uid, db_client=self._db_client)
        if decision.memory_system != MemorySystem.CANONICAL:
            return self._legacy
        if decision.enabled:
            return self._canonical
        raise HTTPException(status_code=503, detail={"reason": decision.reason, "memory_system": "canonical"})

    def ensure_canonical_mutation_ready(self, uid: str) -> None:
        """Fail closed when a canonical-selected background writer cannot mutate."""

        backend = self._resolve_mutation_backend(uid)
        if backend is not self._canonical:
            raise HTTPException(
                status_code=503,
                detail={"reason": "canonical_selection_changed", "memory_system": "canonical"},
            )

    def read(
        self,
        uid: str,
        *,
        limit: int = 100,
        offset: int = 0,
        device_scope_request: Optional[DeviceScopeRequest] = None,
        include_pending_processing: bool = False,
        now: Optional[datetime] = None,
    ) -> List[MemoryDB]:
        backend = self._canonical if canonical_read_enabled(uid, db_client=self._db_client) else self._legacy
        return backend.read(
            uid,
            limit=limit,
            offset=offset,
            device_scope_request=device_scope_request,
            include_pending_processing=include_pending_processing,
            now=now,
        )

    def search(
        self,
        uid: str,
        query: str,
        *,
        limit: int = 5,
        device_scope_request: Optional[DeviceScopeRequest] = None,
    ) -> List[MemorySearchMatch]:
        backend = self._canonical if canonical_read_enabled(uid, db_client=self._db_client) else self._legacy
        return backend.search(
            uid,
            query,
            limit=limit,
            device_scope_request=device_scope_request,
        )

    def search_mcp(self, uid: str, query: str, *, limit: int = 5) -> List[McpSearchPayload]:
        """MCP-shaped search results (legacy parity filters + RRF, or canonical keyword)."""
        if canonical_read_enabled(uid, db_client=self._db_client):
            return _canonical_search_memories_mcp(uid, query, limit=limit, db_client=self._db_client)
        return _legacy_search_memories_mcp(uid, query, limit=limit)

    def write(self, uid: str, data: Dict[str, Any]) -> str:
        return self._resolve_mutation_backend(uid).write(uid, data)

    def write_batch(self, uid: str, items: List[Dict[str, Any]]) -> List[str]:
        return self._resolve_mutation_backend(uid).write_batch(uid, items)

    def update_content(self, uid: str, memory_id: str, content: str) -> MemoryDB:
        return self._resolve_mutation_backend(uid).update_content(uid, memory_id, content)

    def update_visibility(self, uid: str, memory_id: str, visibility: str) -> None:
        self._resolve_mutation_backend(uid).update_visibility(uid, memory_id, visibility)

    def review(self, uid: str, memory_id: str, value: bool) -> None:
        self._resolve_mutation_backend(uid).review(uid, memory_id, value)

    def update_product_fields(
        self,
        uid: str,
        memory_id: str,
        *,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
    ) -> MemoryDB:
        return self._resolve_mutation_backend(uid).update_product_fields(
            uid,
            memory_id,
            tags=tags,
            category=category,
        )

    def delete(self, uid: str, memory_id: str) -> None:
        self._resolve_mutation_backend(uid).delete(uid, memory_id)

    def delete_all(self, uid: str) -> None:
        self._resolve_mutation_backend(uid).delete_all(uid)

    def retract_conversation_memories(self, uid: str, conversation_id: str) -> Optional[Dict[str, Any]]:
        backend = self._resolve_mutation_backend(uid)
        if backend is self._legacy:
            return None
        return retract_conversation_sourced_memories(uid, conversation_id, db_client=self._db_client)

    def create_external_memory(
        self,
        uid: str,
        memory_db: MemoryDB,
        *,
        memory_system: MemorySystem,
        consumer: str,
        operation: str,
        upsert_vector: bool = True,
        require_canonical_promotion: bool = True,
    ) -> MemoryDB:
        """Create one external memory without changing the caller-facing API.

        ``require_canonical_promotion`` remains accepted for compatibility, but
        canonical external writes are always processed before durable admission.
        """
        if memory_system == MemorySystem.CANONICAL and _canonical_external_write_enabled_or_fail_closed(
            uid, self._db_client
        ):
            payload = required_processing_payload(memory_db.model_dump(mode="python"), source_surface=consumer)
            committed_id = self._canonical.write(uid, payload)
            item = read_canonical_memory_item(uid, committed_id or memory_db.id, db_client=self._db_client)
            if item is not None:
                return memory_item_to_memorydb(item)
            logger.error(
                "canonical external memory readback missing uid=%s memory_id=%s",
                uid,
                committed_id or memory_db.id,
            )
            raise HTTPException(status_code=503, detail="Service temporarily unavailable")

        _require_legacy_write_guard(uid, self._db_client, consumer=consumer, operation=operation)
        memories_db.create_memory(uid, memory_write_payload(memory_db, MemoryApiExposure.LEGACY))
        if upsert_vector:
            try:
                upsert_memory_vector(
                    uid,
                    memory_db.id,
                    memory_db.content,
                    memory_db.category.value,
                    subject_entity_id=memory_db.subject_entity_id,
                )
            except Exception:
                logger.exception(
                    "Vector upsert failed uid=%s memory_id=%s (memory saved, vector missing)",
                    uid,
                    memory_db.id,
                )
        return _legacy_memorydb(memory_db)

    def create_external_memory_batch(
        self,
        uid: str,
        memory_dbs: List[MemoryDB],
        *,
        memory_system: MemorySystem,
        consumer: str,
        operation: str,
        upsert_vectors: bool = True,
        require_canonical_promotion: bool = True,
    ) -> List[MemoryDB]:
        """Batch-create external memories with legacy vector upsert when applicable."""
        if memory_system == MemorySystem.CANONICAL and _canonical_external_write_enabled_or_fail_closed(
            uid, self._db_client
        ):
            payloads = [
                required_processing_payload(memory.model_dump(mode="python"), source_surface=consumer)
                for memory in memory_dbs
            ]
            committed_ids = self._canonical.write_batch(uid, payloads)
            results: List[MemoryDB] = []
            for memory_id in committed_ids:
                item = read_canonical_memory_item(uid, memory_id, db_client=self._db_client)
                if item is not None:
                    results.append(memory_item_to_memorydb(item))
                else:
                    logger.error("canonical external batch readback missing uid=%s memory_id=%s", uid, memory_id)
                    raise HTTPException(status_code=503, detail="Service temporarily unavailable")
            return results

        _require_legacy_write_guard(uid, self._db_client, consumer=consumer, operation=operation)
        memories_db.save_memories(
            uid,
            [memory_write_payload(memory, MemoryApiExposure.LEGACY) for memory in memory_dbs],
        )
        if upsert_vectors:
            try:
                upsert_memory_vectors_batch(
                    uid,
                    [
                        {
                            "memory_id": memory.id,
                            "content": memory.content,
                            "category": memory.category.value,
                            "subject_entity_id": memory.subject_entity_id,
                        }
                        for memory in memory_dbs
                    ],
                )
            except Exception:
                logger.exception("Vector batch upsert failed uid=%s (memories saved, vectors missing)", uid)
        return [_legacy_memorydb(memory) for memory in memory_dbs]

    def delete_external_memory(
        self,
        uid: str,
        memory_id: str,
        *,
        memory_system: MemorySystem,
        consumer: str,
        operation: str,
        delete_vector: bool = True,
    ) -> None:
        """Delete external memory with legacy vector cleanup when applicable."""
        if memory_system == MemorySystem.CANONICAL and _canonical_external_write_enabled_or_fail_closed(
            uid, self._db_client
        ):
            try:
                self._canonical.delete(uid, memory_id)
            except ValueError:
                raise HTTPException(status_code=404, detail="Memory not found")
            return

        _require_legacy_write_guard(uid, self._db_client, consumer=consumer, operation=operation)
        memory = memories_db.get_memory(uid, memory_id)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        if memory.get('is_locked', False):
            raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
        memories_db.delete_memory(uid, memory_id)
        if delete_vector:
            try:
                delete_memory_vector(uid, memory_id)
            except Exception:
                logger.exception("Vector delete failed uid=%s memory_id=%s (Firestore deleted)", uid, memory_id)

    def update_external_memory_content(
        self,
        uid: str,
        memory_id: str,
        content: str,
        *,
        memory_system: MemorySystem,
        consumer: str,
        operation: str,
        upsert_vector: bool = True,
    ) -> MemoryDB:
        """Update external memory content with legacy vector upsert when applicable."""
        if memory_system == MemorySystem.CANONICAL and _canonical_external_write_enabled_or_fail_closed(
            uid, self._db_client
        ):
            try:
                return self._canonical.update_content(uid, memory_id, content)
            except ValueError:
                raise HTTPException(status_code=404, detail="Memory not found")

        _require_legacy_write_guard(uid, self._db_client, consumer=consumer, operation=operation)
        memory = memories_db.get_memory(uid, memory_id)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        if memory.get('is_locked', False):
            raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
        memories_db.edit_memory(uid, memory_id, content)
        if upsert_vector:
            try:
                upsert_memory_vector(
                    uid,
                    memory_id,
                    content,
                    memory.get('category', 'other'),
                    subject_entity_id=memory.get('subject_entity_id'),
                )
            except Exception:
                logger.exception(
                    "Vector upsert failed uid=%s memory_id=%s (memory edited, vector stale)",
                    uid,
                    memory_id,
                )
        return _legacy_memorydb(cast(MemoryPayload, memories_db.get_memory(uid, memory_id)))
