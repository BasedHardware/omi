"""Memory routing seam — surfaces route reads/writes/search through MemoryService (WS-L)."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, cast

from fastapi import HTTPException
from pydantic import ValidationError

import database.memories as memories_db
import database.vector_db as vector_db
from database._client import db as default_db_client
from database.memory_collections import MemoryCollections
from database.vector_db import delete_memory_vector
from models.memories import MemoryDB
from models.product_memory import (
    MemoryAccessPolicy,
    MemoryConsumer,
    MemoryItemStatus,
    MemoryTier,
)
from utils.memory.canonical_memory_adapter import (
    CanonicalBatchMutationLimitError,
    CanonicalMemoryNotFoundError,
    delete_default_canonical_memories,
    delete_all_canonical_memories,
    delete_canonical_memory,
    delete_canonical_memories_batch,
    memory_item_to_memorydb,
    read_canonical_memory_item,
    read_canonical_memories,
    refine_canonical_memory,
    replace_conversation_sourced_memories,
    retract_conversation_sourced_memories,
    search_canonical_memories,
    search_result_to_memorydb,
    update_canonical_memory_content,
    update_canonical_memory_visibility,
    update_canonical_memory_product_fields,
    update_canonical_memory_review,
    write_canonical_external_memory,
)
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items
from utils.memory.required_promotion import required_processing_payload
from config.memory_rollout import MemoryRolloutMode, rollout_mode_env_value
from utils.client_device import DeviceScopeRequest
from utils.memory.device_scope_filter import memory_matches_device
from utils.memory.memory_system import MemorySystem
from utils.memory.memory_api_contract import MemoryApiExposure, memory_api_payload
from utils.metrics import (
    MEMORY_HISTORICAL_MATERIALIZATION_TOTAL,
    MEMORY_HISTORICAL_SUPPRESSION_TOTAL,
    MEMORY_UNIVERSAL_READ_ORIGIN_TOTAL,
)

logger = logging.getLogger(__name__)

MemoryPayload = Dict[str, Any]
McpSearchPayload = Dict[str, Any]


class DeviceScopeNotSupportedError(ValueError):
    """device_scope filtering is only supported on the canonical memory backend."""


@dataclass(frozen=True)
class ExternalMemoryWriteContext:
    """Released compatibility context for universal external memory mutations."""

    memory_system: MemorySystem
    legacy_write_allowed: bool = True
    legacy_write_status_code: int = 200
    legacy_write_detail: Any = None


def resolve_external_memory_write_context(
    uid: str,
    *,
    db_client: Any,
    memory_system: MemorySystem,
    consumer: str,
    operation: str,
) -> ExternalMemoryWriteContext:
    del uid, db_client, memory_system, consumer, operation
    return ExternalMemoryWriteContext(memory_system=MemorySystem.CANONICAL, legacy_write_allowed=False)


def raise_if_legacy_write_blocked(context: ExternalMemoryWriteContext) -> None:
    del context


def _truncate_locked_preview_text(content: str) -> str:
    if len(content) > 70:
        return content[:70] + "..."
    return content


def truncate_locked_memory_preview(memory: MemoryDB) -> MemoryDB:
    """Truncate locked-memory content to the legacy 70-char preview."""
    if not getattr(memory, 'is_locked', False) or not memory.content:
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
    """Fetch through the universal repository, retaining the released dict shape."""
    return MemoryService(db_client=db_client).fetch(uid, memory_id).model_dump(mode="python")


def _reject_legacy_device_scope(device_scope_request: Optional[DeviceScopeRequest]) -> None:
    scope = device_scope_request.device_scope if device_scope_request else "all"
    if scope and scope != "all":
        raise DeviceScopeNotSupportedError("device_scope filtering is unavailable for this request")


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
    # Bound list reads; do not expand first page to 5000 (prod GET 504s).
    effective_limit = max(1, min(limit if limit else 100, 500))
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
        del uid, data
        raise RuntimeError("historical memory adapter is read-only; use canonical apply")

    def review(self, uid: str, memory_id: str, value: bool) -> None:
        del uid, memory_id, value
        raise RuntimeError("historical memory adapter is read-only; use canonical apply")

    def update_product_fields(
        self,
        uid: str,
        memory_id: str,
        *,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        is_baseline: Optional[bool] = None,
    ) -> MemoryDB:
        del uid, memory_id, tags, category, is_baseline
        raise RuntimeError("historical memory adapter is read-only; use canonical apply")

    def write_batch(self, uid: str, items: List[Dict[str, Any]]) -> List[str]:
        del uid, items
        raise RuntimeError("historical memory adapter is read-only; use canonical apply")

    def update_content(self, uid: str, memory_id: str, content: str) -> MemoryDB:
        del uid, memory_id, content
        raise RuntimeError("historical memory adapter is read-only; use canonical apply")

    def update_visibility(self, uid: str, memory_id: str, visibility: str) -> None:
        del uid, memory_id, visibility
        raise RuntimeError("historical memory adapter is read-only; use canonical apply")

    def delete(self, uid: str, memory_id: str) -> None:
        del uid, memory_id
        raise RuntimeError("historical memory adapter is read-only; use canonical apply")

    def delete_all(self, uid: str) -> None:
        del uid
        raise RuntimeError("historical memory adapter is read-only; use canonical apply")

    def delete_default(self, uid: str) -> None:
        del uid
        raise RuntimeError("historical memory adapter is read-only; use canonical apply")


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
        for rank, item in enumerate(items):
            if not item.get("memory_id"):
                continue
            memory_obj = search_result_to_memorydb(uid, item)
            raw_score = item.get("score") or item.get("relevance_score")
            try:
                score = float(raw_score) if raw_score is not None else 1.0 - rank * 0.0001
            except (TypeError, ValueError):
                score = 1.0 - rank * 0.0001
            results.append(MemorySearchMatch(memory=memory_obj, score=score))
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
        is_baseline: Optional[bool] = None,
    ) -> MemoryDB:
        item = update_canonical_memory_product_fields(
            uid,
            memory_id,
            tags=tags,
            category=category,
            is_baseline=is_baseline,
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

    def delete_batch(self, uid: str, memory_ids: List[str]) -> None:
        """Atomically tombstone a bounded set of canonical identities."""
        delete_canonical_memories_batch(uid, memory_ids, db_client=self._db_client)

    def delete_all(self, uid: str) -> None:
        delete_all_canonical_memories(uid, db_client=self._db_client)

    def delete_default(self, uid: str) -> None:
        delete_default_canonical_memories(uid, db_client=self._db_client)


@dataclass(frozen=True)
class MemoryLocator:
    """Origin-qualified physical location for a released public memory id."""

    uid: str
    origin: str
    physical_id: str


@dataclass(frozen=True)
class HistoricalMemoryRecord:
    """Read-only adaptation of one ``users/{uid}/memories`` document."""

    memory: MemoryDB
    locator: MemoryLocator
    lifecycle: str = "grandfathered_long_term"


class HistoricalMemoryAdapter:
    """Bounded, protected, read-only reader for historical memory documents.

    This class deliberately has no create/update/delete methods.  Physical
    deletion is exposed only through ``cleanup`` and is called after a
    canonical mutation has committed.
    """

    MAX_PAGE_SIZE = 500
    MAX_COMPATIBILITY_WINDOW = 5000

    def __init__(self, *, db_client: Any = None):
        self._db_client = db_client

    def _firestore_kwargs(self) -> Dict[str, Any]:
        return {"firestore_client": self._db_client} if self._db_client is not None else {}

    @staticmethod
    def _timestamp(memory: MemoryDB) -> datetime:
        value = memory.updated_at or memory.created_at
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _historical_memory(raw: MemoryPayload, *, include_locked_content: bool = False) -> MemoryDB:
        # Missing visibility is a compatibility case.  Public is the released
        # legacy default and is therefore retained for old documents.
        payload = memory_api_payload(raw, MemoryApiExposure.LEGACY)
        payload.setdefault("visibility", "public")
        # A few early historical documents predate ``updated_at``.  Keep those
        # rows readable and let every sort surface use the same creation-time
        # fallback instead of dropping the row during Pydantic validation.
        if payload.get("updated_at") is None and payload.get("created_at") is not None:
            payload["updated_at"] = payload["created_at"]
        if not include_locked_content and payload.get("is_locked") and isinstance(payload.get("content"), str):
            payload["content"] = _truncate_locked_preview_text(payload["content"])
        memory = MemoryDB.model_validate(payload)
        # Historical rows are logically grandfathered Long-term records.  This
        # adapter classification is deliberately not a fabricated promotion
        # receipt; it only preserves the released lifecycle response shape.
        return memory.model_copy(update={"memory_tier": MemoryTier.long_term})

    @classmethod
    def _adapt(
        cls,
        uid: str,
        raw: MemoryPayload,
        *,
        include_locked_content: bool = False,
    ) -> Optional[HistoricalMemoryRecord]:
        memory_id = raw.get("id")
        if not isinstance(memory_id, str) or not memory_id.strip():
            return None
        try:
            memory = cls._historical_memory(raw, include_locked_content=include_locked_content)
        except (ValidationError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed historical memory uid=%s memory_id=%s: %s", uid, memory_id, exc)
            return None
        if memory.visibility not in {"private", "public", "shared"}:
            logger.warning("Skipping historical memory with unknown visibility uid=%s memory_id=%s", uid, memory_id)
            return None
        return HistoricalMemoryRecord(
            memory=memory,
            locator=MemoryLocator(uid=uid, origin="legacy", physical_id=memory.id),
        )

    @staticmethod
    def matches_device(record: HistoricalMemoryRecord, request: Optional[DeviceScopeRequest]) -> bool:
        if request is None or request.device_scope == "all":
            return True
        if not request.client_device_id:
            return False
        # A historical record has no capture-device provenance.  It is
        # device-neutral and remains visible under a scoped request.  Records
        # that do carry provenance use the same matcher as canonical rows.
        memory = record.memory
        known_devices = set(memory.capture_device_ids or [])
        known_devices.update(
            client_device_id
            for evidence in memory.evidence
            if (client_device_id := evidence.client_device_id) is not None
        )
        return not known_devices or request.client_device_id in known_devices

    def read(
        self,
        uid: str,
        *,
        limit: int = 100,
        offset: int = 0,
        device_scope_request: Optional[DeviceScopeRequest] = None,
    ) -> List[HistoricalMemoryRecord]:
        bounded_limit = max(1, min(int(limit or 100), self.MAX_COMPATIBILITY_WINDOW))
        bounded_offset = max(0, int(offset or 0))
        # Read one bounded prefix and merge/order it in the universal service;
        # never scan the historical collection for a normal page.
        fetch_limit = bounded_offset + bounded_limit
        if fetch_limit > self.MAX_COMPATIBILITY_WINDOW:
            raise HTTPException(status_code=413, detail="Historical memory pagination window exceeded")
        try:
            raw_rows = memories_db.get_memories(
                uid,
                fetch_limit,
                0,
                sort="updated_or_created_desc",
                **self._firestore_kwargs(),
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Historical memory unavailable") from exc
        records = [record for raw in raw_rows for record in [self._adapt(uid, raw)] if record is not None]
        records = [record for record in records if self.matches_device(record, device_scope_request)]
        records.sort(key=lambda record: (-self._timestamp(record.memory).timestamp(), record.memory.id))
        return records

    def get(self, uid: str, memory_id: str) -> Optional[HistoricalMemoryRecord]:
        try:
            raw = memories_db.get_memory(uid, memory_id, **self._firestore_kwargs())
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Historical memory unavailable") from exc
        if not raw:
            return None
        return self._adapt(uid, raw)

    def search(
        self,
        uid: str,
        query: str,
        *,
        limit: int = 5,
        device_scope_request: Optional[DeviceScopeRequest] = None,
    ) -> List[MemorySearchMatch]:
        capped = max(1, min(int(limit or 5), 20))
        try:
            matches = vector_db.find_similar_memories(uid, query, threshold=0.0, limit=min(capped * 3, 60))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Historical memory search unavailable") from exc
        ids, scores = _memory_ids_and_scores(matches or [])
        if not ids:
            return []
        try:
            rows = memories_db.get_memories_by_ids(uid, ids, **self._firestore_kwargs())
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Historical memory unavailable") from exc
        by_id: Dict[str, HistoricalMemoryRecord] = {}
        for raw in rows:
            record = self._adapt(uid, raw)
            if record is None or not self.matches_device(record, device_scope_request):
                continue
            if record.memory.is_locked or record.memory.user_review is False or record.memory.invalid_at is not None:
                continue
            by_id.setdefault(record.memory.id, record)
        return [
            MemorySearchMatch(memory=by_id[memory_id].memory, score=scores.get(memory_id, 0.0))
            for memory_id in ids
            if memory_id in by_id
        ][:capped]

    @staticmethod
    def cleanup(uid: str, memory_id: str, *, delete_vector: bool = True, db_client: Any = None) -> None:
        """Best-effort physical cleanup after canonical authority commits."""
        try:
            kwargs = {"firestore_client": db_client} if db_client is not None else {}
            memories_db.delete_memory(uid, memory_id, **kwargs)
        except Exception:
            logger.exception("historical memory cleanup failed uid=%s memory_id=%s", uid, memory_id)
        if delete_vector:
            try:
                delete_memory_vector(uid, memory_id)
            except Exception:
                logger.exception("historical vector cleanup failed uid=%s memory_id=%s", uid, memory_id)

    def all_live(self, uid: str, *, page_size: int = 500) -> List[HistoricalMemoryRecord]:
        """Enumerate historical live rows in bounded pages for explicit export only."""
        page_size = max(1, min(int(page_size or 500), self.MAX_PAGE_SIZE))
        records: List[HistoricalMemoryRecord] = []
        offset = 0
        while True:
            try:
                raw_rows = memories_db.get_memories(
                    uid,
                    page_size,
                    offset,
                    **self._firestore_kwargs(),
                )
            except Exception as exc:
                raise HTTPException(status_code=503, detail="Historical memory unavailable") from exc
            if not raw_rows:
                break
            for raw in raw_rows:
                record = self._adapt(uid, raw, include_locked_content=True)
                if record is not None:
                    records.append(record)
            offset += len(raw_rows)
            if len(raw_rows) < page_size:
                break
        records.sort(key=lambda record: (-self._timestamp(record.memory).timestamp(), record.memory.id))
        return records

    @staticmethod
    def ids(uid: str, *, limit: Optional[int] = None, offset: int = 0, db_client: Any = None) -> List[str]:
        """Return physical IDs without decrypting historical content.

        Ordinary reads never call this seam. Explicit privacy operations may
        request the complete ID inventory so delete-all/account deletion cannot
        silently stop at an arbitrary compatibility cap.
        """
        try:
            ids = memories_db.get_memory_ids(uid, **({"firestore_client": db_client} if db_client is not None else {}))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Historical memory unavailable") from exc
        start = max(0, offset)
        selected = ids[start:] if limit is None else ids[start : start + max(1, limit)]
        return [memory_id for memory_id in selected if memory_id]

    @classmethod
    def cleanup_all(cls, uid: str, *, db_client: Any = None) -> None:
        """Best-effort physical cleanup after a canonical delete-all."""
        try:
            ids = cls.ids(uid, db_client=db_client)
        except Exception:
            logger.exception("historical delete-all id scan failed uid=%s", uid)
            return
        for memory_id in ids:
            cls.cleanup(uid, memory_id, db_client=db_client)


class MemoryService:
    """Universal memory authority for every authenticated UID.

    ``memory_system`` arguments remain on compatibility methods because released
    callers still send them, but they are intentionally ignored.  Canonical
    apply is the sole write authority; historical documents are a bounded,
    protected read adapter and only a cleanup target after canonical commit.
    """

    def __init__(self, *, db_client: Any = None):
        self._db_client = db_client
        self._history = HistoricalMemoryAdapter(db_client=db_client)
        # Keep these attributes for callers/tests that inspect the old seam.
        self._legacy = self._history
        self._canonical = CanonicalMemoryBackend(db_client=db_client)

    def ensure_canonical_mutation_ready(self, uid: str) -> None:
        """Enforce the deployment-wide intake fence without selecting users.

        Reads and privacy deletes remain universal in every mode. ``off`` and
        ``shadow`` stop product-visible writes so operators can deploy the
        dual-format reader to every instance before enabling canonical intake.
        """
        if not uid:
            raise HTTPException(status_code=401, detail="Authenticated user required")
        try:
            mode = MemoryRolloutMode(rollout_mode_env_value())
        except ValueError as exc:
            raise HTTPException(status_code=503, detail="Memory write control is invalid") from exc
        if mode not in {MemoryRolloutMode.write, MemoryRolloutMode.read}:
            raise HTTPException(status_code=503, detail="Memory writes are globally paused")

    def _canonical_status(self, uid: str, memory_id: str) -> Optional[MemoryItemStatus]:
        """Read one canonical status to suppress historical identity collisions."""
        client = self._db_client if self._db_client is not None else default_db_client
        try:
            from database.memory_collections import MemoryCollections
            from models.product_memory import MemoryItem

            snapshot = client.document(f"{MemoryCollections(uid=uid).memory_items}/{memory_id}").get()
            if getattr(snapshot, "exists", False) is not True:
                override = client.document(
                    f"{MemoryCollections(uid=uid).memory_historical_overrides}/{memory_id}"
                ).get()
                if getattr(override, "exists", False) is True:
                    override_payload = override.to_dict()
                    if isinstance(override_payload, dict):
                        raw_status = override_payload.get("status") or override_payload.get("suppression")
                        if isinstance(raw_status, MemoryItemStatus):
                            return raw_status
                        if isinstance(raw_status, str):
                            return MemoryItemStatus(raw_status)
                return None
            payload = snapshot.to_dict()
            if not isinstance(payload, dict):
                return None
            raw_status = payload.get("status")
            if isinstance(raw_status, MemoryItemStatus):
                return raw_status
            if isinstance(raw_status, str) and raw_status in {status.value for status in MemoryItemStatus}:
                return MemoryItemStatus(raw_status)
            item = MemoryItem.model_validate(payload)
            return item.status
        except Exception as exc:
            # A materialization may use a compact override/suppression record
            # before a full canonical item exists.  It is still canonical
            # authority and must suppress the historical public ID.
            try:
                from database.memory_collections import MemoryCollections

                override = client.document(
                    f"{MemoryCollections(uid=uid).memory_historical_overrides}/{memory_id}"
                ).get()
                if getattr(override, "exists", False) is not True:
                    raise exc
                override_payload = override.to_dict()
                if not isinstance(override_payload, dict):
                    raise exc
                raw_status = override_payload.get("status") or override_payload.get("suppression")
                if isinstance(raw_status, MemoryItemStatus):
                    return raw_status
                if isinstance(raw_status, str):
                    return MemoryItemStatus(raw_status)
            except Exception:
                pass
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc

    @staticmethod
    def _status_from_snapshot(snapshot: Any) -> Optional[MemoryItemStatus]:
        if getattr(snapshot, "exists", False) is not True:
            return None
        payload = snapshot.to_dict()
        if not isinstance(payload, dict):
            return None
        raw_status = payload.get("status") or payload.get("suppression")
        if isinstance(raw_status, MemoryItemStatus):
            return raw_status
        if isinstance(raw_status, str):
            try:
                return MemoryItemStatus(raw_status)
            except ValueError:
                return None
        return None

    def _canonical_statuses(self, uid: str, memory_ids: List[str]) -> Dict[str, MemoryItemStatus]:
        """Read canonical identity/suppression status in bounded batches.

        Firestore's ``get_all`` gives mixed reads a bounded read surface instead
        of one document RPC per historical row.  Small injected fakes used by
        unit tests (and older Firestore clients without ``get_all``) retain the
        single-ID fallback through ``_canonical_status``.
        """
        normalized_ids = list(dict.fromkeys(memory_id for memory_id in memory_ids if memory_id))
        if not normalized_ids:
            return {}
        client = self._db_client if self._db_client is not None else default_db_client
        get_all = getattr(client, "get_all", None)
        if callable(get_all):
            batch_get = cast(Callable[[List[Any]], Iterable[Any]], get_all)
            collections = MemoryCollections(uid=uid)
            statuses: Dict[str, MemoryItemStatus] = {}
            # Keep each request comfortably below Firestore's practical batch
            # read limits while covering both the item and override documents.
            for start in range(0, len(normalized_ids), 100):
                chunk = normalized_ids[start : start + 100]
                item_refs = [client.document(f"{collections.memory_items}/{memory_id}") for memory_id in chunk]
                override_refs = [
                    client.document(f"{collections.memory_historical_overrides}/{memory_id}") for memory_id in chunk
                ]
                refs = item_refs + override_refs
                try:
                    snapshots = list(batch_get(refs))
                except Exception as exc:
                    raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
                snapshots_by_path: Dict[str, Any] = {}
                for snapshot in snapshots:
                    snapshot_path = getattr(getattr(snapshot, "reference", None), "path", None)
                    if not isinstance(snapshot_path, str) or snapshot_path in snapshots_by_path:
                        # Firestore does not promise result ordering and may
                        # omit missing documents. A client that also omits
                        # reference identity cannot be mapped safely.
                        snapshots_by_path = {}
                        break
                    snapshots_by_path[snapshot_path] = snapshot
                if snapshots and not snapshots_by_path:
                    return {
                        memory_id: status
                        for memory_id in normalized_ids
                        if (status := self._canonical_status(uid, memory_id))
                    }
                for index, memory_id in enumerate(chunk):
                    item_snapshot = snapshots_by_path.get(item_refs[index].path)
                    override_snapshot = snapshots_by_path.get(override_refs[index].path)
                    status = self._status_from_snapshot(item_snapshot)
                    if status is None:
                        status = self._status_from_snapshot(override_snapshot)
                    if status is None and (
                        getattr(item_snapshot, "exists", False) is True
                        or getattr(override_snapshot, "exists", False) is True
                    ):
                        # A present canonical authority record with no valid
                        # status must never admit its historical duplicate.
                        # Reuse the strict single-record parser so a valid
                        # override can still suppress a malformed item.
                        status = self._canonical_status(uid, memory_id)
                        if status is None:
                            raise HTTPException(status_code=503, detail="Canonical memory unavailable")
                    if status is not None:
                        statuses[memory_id] = status
            return statuses
        return {memory_id: status for memory_id in normalized_ids if (status := self._canonical_status(uid, memory_id))}

    def _write_historical_override(self, uid: str, memory_id: str, status: MemoryItemStatus) -> None:
        """Persist one idempotent canonical suppression/ownership record."""
        client = self._db_client if self._db_client is not None else default_db_client
        path = f"{MemoryCollections(uid=uid).memory_historical_overrides}/{memory_id}"
        payload = {
            "uid": uid,
            "memory_id": memory_id,
            "public_id": memory_id,
            "origin": "legacy",
            "status": status.value,
            "updated_at": datetime.now(timezone.utc),
        }
        try:
            ref = client.document(path)
            try:
                ref.set(payload, merge=True)
            except TypeError:
                ref.set(payload)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory suppression unavailable") from exc

    def _write_historical_overrides(
        self,
        uid: str,
        memory_ids: List[str],
        status: MemoryItemStatus,
        *,
        batch_size: int = 100,
    ) -> None:
        """Commit bounded idempotent override batches before legacy cleanup."""
        normalized = list(dict.fromkeys(memory_id for memory_id in memory_ids if memory_id))
        bounded_batch_size = max(1, min(int(batch_size or 100), 500))
        client = self._db_client if self._db_client is not None else default_db_client
        for start in range(0, len(normalized), bounded_batch_size):
            chunk = normalized[start : start + bounded_batch_size]
            batch_factory = getattr(client, "batch", None)
            if not callable(batch_factory):
                for memory_id in chunk:
                    self._write_historical_override(uid, memory_id, status)
                continue
            try:
                batch = cast(Any, batch_factory())
                for memory_id in chunk:
                    path = f"{MemoryCollections(uid=uid).memory_historical_overrides}/{memory_id}"
                    payload = {
                        "uid": uid,
                        "memory_id": memory_id,
                        "public_id": memory_id,
                        "origin": "legacy",
                        "status": status.value,
                        "updated_at": datetime.now(timezone.utc),
                    }
                    ref = client.document(path)
                    try:
                        batch.set(ref, payload, merge=True)
                    except TypeError:
                        batch.set(ref, payload)
                batch.commit()
            except Exception as exc:
                raise HTTPException(status_code=503, detail="Canonical memory suppression unavailable") from exc

    def _canonical_read(
        self,
        uid: str,
        *,
        limit: int,
        offset: int,
        device_scope_request: Optional[DeviceScopeRequest],
        include_pending_processing: bool,
        now: Optional[datetime],
    ) -> List[MemoryDB]:
        try:
            window = limit + offset
            if window > HistoricalMemoryAdapter.MAX_COMPATIBILITY_WINDOW:
                raise HTTPException(status_code=413, detail="Memory pagination window exceeded")
            return self._canonical.read(
                uid,
                limit=max(1, window),
                offset=0,
                device_scope_request=device_scope_request,
                include_pending_processing=include_pending_processing,
                now=now,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc

    @staticmethod
    def _sort_memories(memories: List[MemoryDB]) -> None:
        def timestamp(memory: MemoryDB) -> float:
            value = getattr(memory, "updated_at", None) or getattr(memory, "created_at", None)
            if value is None:
                return float("-inf")
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.timestamp()

        memories.sort(
            key=lambda memory: (
                -timestamp(memory),
                memory.id,
            )
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
        bounded_limit = max(1, min(int(limit or 100), HistoricalMemoryAdapter.MAX_COMPATIBILITY_WINDOW))
        bounded_offset = max(0, int(offset or 0))
        window = bounded_offset + bounded_limit
        if window > HistoricalMemoryAdapter.MAX_COMPATIBILITY_WINDOW:
            raise HTTPException(status_code=413, detail="Memory pagination window exceeded")
        canonical = self._canonical_read(
            uid,
            limit=window,
            offset=0,
            device_scope_request=device_scope_request,
            include_pending_processing=include_pending_processing,
            now=now,
        )
        historical = self._history.read(
            uid,
            limit=window,
            offset=0,
            device_scope_request=device_scope_request,
        )
        MEMORY_UNIVERSAL_READ_ORIGIN_TOTAL.labels(origin="canonical").inc(len(canonical))
        MEMORY_UNIVERSAL_READ_ORIGIN_TOTAL.labels(origin="historical").inc(len(historical))
        canonical_ids = {memory.id for memory in canonical}
        merged = list(canonical)
        historical_statuses = self._canonical_statuses(uid, [record.memory.id for record in historical])
        for record in historical:
            if record.memory.id in canonical_ids:
                MEMORY_HISTORICAL_SUPPRESSION_TOTAL.labels(reason="canonical_identity").inc()
                continue
            status = historical_statuses.get(record.memory.id)
            if status in {
                MemoryItemStatus.active,
                MemoryItemStatus.tombstoned,
                MemoryItemStatus.hidden,
                MemoryItemStatus.superseded,
            }:
                # Active canonical rows are authoritative even if a bounded
                # canonical page did not contain the ID; non-active rows are
                # durable suppressions of the historical identity.
                MEMORY_HISTORICAL_SUPPRESSION_TOTAL.labels(reason="canonical_state").inc()
                continue
            merged.append(record.memory)
        self._sort_memories(merged)
        return merged[bounded_offset : bounded_offset + bounded_limit]

    def read_pinned(
        self,
        uid: str,
        memory_system: MemorySystem,
        limit: int = 100,
        offset: int = 0,
        *,
        device_scope_request: Optional[DeviceScopeRequest] = None,
        include_pending_processing: bool = False,
        now: Optional[datetime] = None,
    ) -> List[MemoryDB]:
        # The pin is a released compatibility argument, never a product selector.
        del memory_system
        return self.read(
            uid,
            limit=limit,
            offset=offset,
            device_scope_request=device_scope_request,
            include_pending_processing=include_pending_processing,
            now=now,
        )

    def fetch(self, uid: str, memory_id: str, *, device_scope_request: Optional[DeviceScopeRequest] = None) -> MemoryDB:
        try:
            item = read_canonical_memory_item(uid, memory_id, db_client=self._db_client)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
        if item is not None:
            if (
                device_scope_request is not None
                and device_scope_request.device_scope in {"current", "explicit"}
                and not memory_matches_device(item, device_scope_request.client_device_id or "")
            ):
                raise HTTPException(status_code=404, detail="Memory not found")
            return memory_item_to_memorydb(item)
        status = self._canonical_status(uid, memory_id)
        if status is not None:
            raise HTTPException(status_code=404, detail="Memory not found")
        record = self._history.get(uid, memory_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        if record.memory.is_locked:
            raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
        if not HistoricalMemoryAdapter.matches_device(record, device_scope_request):
            raise HTTPException(status_code=404, detail="Memory not found")
        return record.memory

    def search(
        self,
        uid: str,
        query: str,
        *,
        limit: int = 5,
        device_scope_request: Optional[DeviceScopeRequest] = None,
    ) -> List[MemorySearchMatch]:
        capped = max(1, min(int(limit or 5), 20))
        try:
            canonical = self._canonical.search(
                uid, query, limit=min(capped * 3, 60), device_scope_request=device_scope_request
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory search unavailable") from exc
        historical = self._history.search(
            uid, query, limit=min(capped * 3, 60), device_scope_request=device_scope_request
        )
        by_id: Dict[str, MemorySearchMatch] = {}
        for match in canonical:
            by_id[match.memory.id] = match
        for match in historical:
            if match.memory.id in by_id:
                continue
            status = self._canonical_status(uid, match.memory.id)
            if status is not None:
                continue
            by_id[match.memory.id] = match
        results = list(by_id.values())

        def timestamp(match: MemorySearchMatch) -> float:
            value = getattr(match.memory, "updated_at", None) or getattr(match.memory, "created_at", None)
            if value is None:
                return float("-inf")
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.timestamp()

        results.sort(key=lambda match: (-float(match.score), -timestamp(match), match.memory.id))
        return results[:capped]

    def search_mcp(self, uid: str, query: str, *, limit: int = 5) -> List[McpSearchPayload]:
        return [
            {
                "id": match.memory.id,
                "content": match.memory.content,
                "category": match.memory.category.value,
                "relevance_score": round(float(match.score), 4),
            }
            for match in self.search(uid, query, limit=limit)
        ]

    def default_product_search(
        self,
        uid: str,
        query: str,
        *,
        policy: MemoryAccessPolicy,
        now: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Return one default-memory product view across both physical origins.

        This is the shared chat/developer/MCP read boundary.  Historical rows
        are adapted in memory only; the read performs no materialization,
        embedding, graph admission, or legacy mutation.  Canonical visibility,
        lifecycle, processing, lineage, and tombstone rules are applied by
        :meth:`read` before historical rows can join the result.
        """
        bounded_limit = max(1, min(int(limit or 100), 500))
        bounded_offset = max(0, int(offset or 0))
        if (
            policy.consumer
            in {
                MemoryConsumer.third_party,
                MemoryConsumer.developer_api,
                MemoryConsumer.mcp,
            }
            and not policy.app_has_default_memory_grant
        ):
            return self._default_product_search_response(uid, query, [], limit=bounded_limit, offset=bounded_offset)
        # Read one bounded merged window. Calling ``read`` once avoids the
        # previous page-by-page prefix reread, which grew to O(N²) Firestore
        # reads as the compatibility offset advanced.
        rows = self.read(
            uid,
            limit=HistoricalMemoryAdapter.MAX_COMPATIBILITY_WINDOW,
            offset=0,
            include_pending_processing=False,
            now=now,
        )

        query_tokens = {
            token.lower() for token in (query or "").replace(".", " ").replace(",", " ").split() if len(token) > 2
        }
        items: List[Dict[str, Any]] = []
        for memory in rows:
            # archive_requires_explicit_query: this default product search never
            # admits Archive, regardless of physical origin.
            if memory.memory_tier == MemoryTier.archive:
                continue
            if memory.invalid_at is not None or memory.user_review is False or memory.is_locked:
                continue
            content = memory.content or ""
            content_lower = content.lower()
            if query_tokens and not any(token in content_lower for token in query_tokens):
                continue
            tier = memory.memory_tier or MemoryTier.long_term
            source = memory.evidence[0].source_id if memory.evidence else None
            items.append(
                {
                    "memory_id": memory.id,
                    "memory_layer": "product_memory",
                    "tier": tier.value,
                    "content": content,
                    "lifecycle_status": "active",
                    "processing_state": "processed",
                    "confidence": None,
                    "visibility": memory.visibility,
                    "visibility_source": "universal_memory_service",
                    "source": source,
                    "date": (memory.updated_at or memory.created_at).isoformat(),
                    "evidence": [evidence.model_dump(mode="json") for evidence in memory.evidence],
                    "agent_use": "default_access_memory",
                    "access_reason": "default_memory_allowed",
                    "superseded_by": None,
                }
            )

        total_count = len(items)
        paged = items[bounded_offset : bounded_offset + bounded_limit]
        return self._default_product_search_response(
            uid,
            query,
            paged,
            limit=bounded_limit,
            offset=bounded_offset,
            total_count=total_count,
        )

    @staticmethod
    def _default_product_search_response(
        uid: str,
        query: str,
        items: List[Dict[str, Any]],
        *,
        limit: int,
        offset: int,
        total_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        return {
            "uid": uid,
            "query": query,
            "items": items,
            "total_count": len(items) if total_count is None else total_count,
            "returned_count": len(items),
            "limit": limit,
            "offset": offset,
            "archive_default_visible": False,
        }

    def export_memories(
        self,
        uid: str,
        *,
        include_archive: bool = True,
        page_size: int = 500,
    ) -> List[MemoryDB]:
        """Return each live logical memory once for account export.

        Export is an explicit capability, so it reads active canonical Archive
        rows as well as default layers when ``include_archive`` is true.  A
        historical row is omitted whenever canonical state (active or
        tombstoned) owns the same stable public ID.  No export read performs
        materialization, LLM work, embedding, or graph admission.
        """
        archive_explicit = include_archive
        page_size = max(1, min(int(page_size or 500), 500))
        client = self._db_client if self._db_client is not None else default_db_client
        try:
            canonical_items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc

        canonical_rows: List[MemoryDB] = []
        canonical_ids: set[str] = set()
        for item in canonical_items:
            canonical_ids.add(item.memory_id)
            if item.status != MemoryItemStatus.active:
                continue
            if item.tier == MemoryTier.archive and not archive_explicit:
                continue
            canonical_rows.append(memory_item_to_memorydb(item))

        historical_rows = self._history.all_live(uid, page_size=page_size)
        merged = list(canonical_rows)
        historical_statuses = self._canonical_statuses(uid, [record.memory.id for record in historical_rows])
        for record in historical_rows:
            if record.memory.id not in canonical_ids:
                # Suppression overrides are canonical authority even when the
                # canonical item itself has already been physically cleaned up.
                if historical_statuses.get(record.memory.id) is not None:
                    MEMORY_HISTORICAL_SUPPRESSION_TOTAL.labels(reason="canonical_state").inc()
                    continue
                merged.append(record.memory)
        self._sort_memories(merged)
        return merged

    def list_historical_memory_ids(self, uid: str, *, limit: Optional[int] = None, offset: int = 0) -> List[str]:
        """IDs-only compatibility seam for complete privacy operations."""
        return self._history.ids(uid, limit=limit, offset=offset, db_client=self._db_client)

    def _canonical_write(self, uid: str, data: Dict[str, Any], *, source_surface: str) -> MemoryDB:
        self.ensure_canonical_mutation_ready(uid)
        payload = required_processing_payload(data, source_surface=source_surface)
        committed_id = self._canonical.write(uid, payload)
        item = read_canonical_memory_item(uid, committed_id or str(data.get("id") or ""), db_client=self._db_client)
        if item is None:
            raise HTTPException(status_code=503, detail="Canonical memory write readback unavailable")
        return memory_item_to_memorydb(item)

    def write(self, uid: str, data: Dict[str, Any]) -> str:
        self.ensure_canonical_mutation_ready(uid)
        return self._canonical.write(uid, data)

    def write_batch(self, uid: str, items: List[Dict[str, Any]]) -> List[str]:
        self.ensure_canonical_mutation_ready(uid)
        return self._canonical.write_batch(uid, items)

    def _materialize_legacy(self, uid: str, memory_id: str) -> MemoryDB:
        status = self._canonical_status(uid, memory_id)
        if status is not None:
            raise HTTPException(status_code=404, detail="Memory not found")
        record = self._history.get(uid, memory_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        if record.memory.is_locked:
            raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
        payload = memory_api_payload(record.memory, MemoryApiExposure.LEGACY)
        payload.update(
            {
                "id": memory_id,
                "uid": uid,
                "promotion": {"historical_materialization": True, "lifecycle": "grandfathered_long_term"},
                "manually_added": bool(payload.get("manually_added")),
                "user_asserted": bool(payload.get("manually_added")),
            }
        )
        # Both writes are canonical authority: apply first, then the durable
        # historical suppression record.  If either fails, no legacy writer or
        # mirror is attempted.
        self._canonical.write(uid, payload)
        self._write_historical_override(uid, memory_id, MemoryItemStatus.active)
        return record.memory

    def _ensure_canonical_target(self, uid: str, memory_id: str) -> bool:
        try:
            if read_canonical_memory_item(uid, memory_id, db_client=self._db_client) is not None:
                MEMORY_HISTORICAL_MATERIALIZATION_TOTAL.labels(outcome="not_needed").inc()
                return False
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
        self._materialize_legacy(uid, memory_id)
        MEMORY_HISTORICAL_MATERIALIZATION_TOTAL.labels(outcome="committed").inc()
        return True

    def update_content(self, uid: str, memory_id: str, content: str) -> MemoryDB:
        self.ensure_canonical_mutation_ready(uid)
        materialized = self._ensure_canonical_target(uid, memory_id)
        try:
            updated = self._canonical.update_content(uid, memory_id, content)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Memory not found") from exc
        if materialized:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self._db_client)
        return updated

    def refine(self, uid: str, memory_id: str, arg_changes: Dict[str, Any]) -> MemoryDB:
        self.ensure_canonical_mutation_ready(uid)
        materialized = self._ensure_canonical_target(uid, memory_id)
        try:
            updated = refine_canonical_memory(uid, memory_id, arg_changes, db_client=self._db_client)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Memory not found") from exc
        if materialized:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self._db_client)
        return memory_item_to_memorydb(updated)

    def update_visibility(self, uid: str, memory_id: str, visibility: str) -> None:
        self.ensure_canonical_mutation_ready(uid)
        materialized = self._ensure_canonical_target(uid, memory_id)
        self._canonical.update_visibility(uid, memory_id, visibility)
        if materialized:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self._db_client)

    def review(self, uid: str, memory_id: str, value: bool) -> None:
        self.ensure_canonical_mutation_ready(uid)
        materialized = self._ensure_canonical_target(uid, memory_id)
        self._canonical.review(uid, memory_id, value)
        if materialized:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self._db_client)

    def update_product_fields(
        self,
        uid: str,
        memory_id: str,
        *,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        is_baseline: Optional[bool] = None,
    ) -> MemoryDB:
        self.ensure_canonical_mutation_ready(uid)
        materialized = self._ensure_canonical_target(uid, memory_id)
        updated = self._canonical.update_product_fields(
            uid,
            memory_id,
            tags=tags,
            category=category,
            is_baseline=is_baseline,
        )
        if materialized:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self._db_client)
        return updated

    def update_baseline(self, uid: str, memory_id: str, value: bool) -> MemoryDB:
        """Preserve the released baseline mutation through canonical metadata."""

        return self.update_product_fields(uid, memory_id, is_baseline=value)

    def delete(self, uid: str, memory_id: str) -> None:
        try:
            canonical_item = read_canonical_memory_item(uid, memory_id, db_client=self._db_client)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
        if canonical_item is not None:
            # Write the historical suppression first. Tombstones are privacy
            # operations, not intake, so this path stays available while the
            # global write fence is paused and a cleanup failure cannot expose
            # the old physical row again.
            self._write_historical_override(uid, memory_id, MemoryItemStatus.tombstoned)
            self._canonical.delete(uid, memory_id)
        else:
            status = self._canonical_status(uid, memory_id)
            if status is not None:
                raise HTTPException(status_code=404, detail="Memory not found")
            record = self._history.get(uid, memory_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Memory not found")
            if record.memory.is_locked:
                raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
            # A historical-only deletion does not need to manufacture an
            # active canonical item.  The durable canonical suppression record
            # is the authoritative privacy tombstone.
        self._write_historical_override(uid, memory_id, MemoryItemStatus.tombstoned)
        HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self._db_client)

    def delete_batch(self, uid: str, memory_ids: List[str]) -> None:
        """Delete canonical and historical memories with all-or-nothing validation.

        Every requested identity is resolved and its paid/locked state is checked
        before any canonical write. Canonical rows are tombstoned transactionally;
        historical-only rows receive durable canonical suppression records without
        first creating active canonical items. Physical cleanup happens last.
        """
        requested = list(dict.fromkeys(memory_id for memory_id in memory_ids if memory_id))
        if not requested:
            return

        canonical_ids: List[str] = []
        historical_ids: List[str] = []
        # Validation is intentionally a complete read-only pass.  In particular,
        # do not materialize the first historical ID before checking later IDs.
        for memory_id in requested:
            try:
                canonical_item = read_canonical_memory_item(uid, memory_id, db_client=self._db_client)
            except Exception as exc:
                raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
            if canonical_item is not None:
                canonical_ids.append(memory_id)
                continue

            status = self._canonical_status(uid, memory_id)
            if status == MemoryItemStatus.tombstoned:
                # A previous attempt may have committed the canonical tombstone
                # and failed before cleanup/ledger completion. Preserve the
                # identity in this retry so the suppression write is replayed.
                record = self._history.get(uid, memory_id)
                if record is not None:
                    historical_ids.append(memory_id)
                continue
            if status is not None:
                raise HTTPException(status_code=404, detail="Memory not found")
            record = self._history.get(uid, memory_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Memory not found")
            if record.memory.is_locked:
                raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
            historical_ids.append(memory_id)

        # Suppression is committed before the canonical tombstone and cleanup so
        # a partial attempt cannot resurrect a historical row. Canonical rows
        # also receive an override; this keeps the identity ledger explicit for
        # export and account purge, and is safe to replay.
        self._write_historical_overrides(uid, requested, MemoryItemStatus.tombstoned)

        try:
            if canonical_ids:
                self._canonical.delete_batch(uid, canonical_ids)
        except HTTPException:
            raise
        except CanonicalBatchMutationLimitError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except CanonicalMemoryNotFoundError as exc:
            # A concurrent canonical change can invalidate the prevalidation;
            # expose the same released not-found contract without per-ID fallback.
            raise HTTPException(status_code=404, detail="Memory not found") from exc

        for memory_id in historical_ids:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self._db_client)

    def delete_all(self, uid: str) -> None:
        historical_ids = self._history.ids(uid, db_client=self._db_client)
        # Commit the historical privacy fence before canonical cleanup. A retry
        # can safely repeat this idempotent batch if canonical deletion fails.
        self._write_historical_overrides(uid, historical_ids, MemoryItemStatus.tombstoned)
        self._canonical.delete_all(uid)
        # Cleanup is intentionally after canonical tombstones and is never the
        # success condition.  The protected adapter remains read-only.
        self._history.cleanup_all(uid, db_client=self._db_client)

    def delete_default(self, uid: str) -> None:
        historical_ids = self._history.ids(uid, db_client=self._db_client)
        self._write_historical_overrides(uid, historical_ids, MemoryItemStatus.tombstoned)
        self._canonical.delete_default(uid)
        self._history.cleanup_all(uid, db_client=self._db_client)

    def retract_conversation_memories(self, uid: str, conversation_id: str) -> Optional[Dict[str, Any]]:
        result = retract_conversation_sourced_memories(uid, conversation_id, db_client=self._db_client)
        historical_ids = [
            record.memory.id
            for record in self._history.all_live(uid)
            if record.memory.conversation_id == conversation_id
            or any(
                evidence.source_type == "conversation" and evidence.source_id == conversation_id
                for evidence in record.memory.evidence
            )
        ]
        retracted_ids = list(dict.fromkeys(list(result.get("retracted_memory_ids") or []) if result else []))
        all_ids = list(dict.fromkeys(retracted_ids + historical_ids))
        if all_ids:
            self._write_historical_overrides(uid, all_ids, MemoryItemStatus.tombstoned)
            for memory_id in historical_ids:
                HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self._db_client)
        return result

    def replace_conversation_memories(
        self,
        uid: str,
        conversation_id: str,
        items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        self.ensure_canonical_mutation_ready(uid)
        result = replace_conversation_sourced_memories(uid, conversation_id, items, db_client=self._db_client)
        retracted = list(result.get("retracted_memory_ids") or [])
        if retracted:
            self._write_historical_overrides(uid, retracted, MemoryItemStatus.tombstoned)
        return result

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
        del memory_system, operation, upsert_vector, require_canonical_promotion
        return self._canonical_write(uid, memory_db.model_dump(mode="python"), source_surface=consumer)

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
        del memory_system, operation, upsert_vectors, require_canonical_promotion
        self.ensure_canonical_mutation_ready(uid)
        payloads = [
            required_processing_payload(memory.model_dump(mode="python"), source_surface=consumer)
            for memory in memory_dbs
        ]
        ids = self._canonical.write_batch(uid, payloads)
        results: List[MemoryDB] = []
        for memory_id in ids:
            item = read_canonical_memory_item(uid, memory_id, db_client=self._db_client)
            if item is None:
                raise HTTPException(status_code=503, detail="Canonical memory write readback unavailable")
            results.append(memory_item_to_memorydb(item))
        self._write_historical_overrides(uid, ids, MemoryItemStatus.active)
        return results

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
        del memory_system, consumer, operation
        if delete_vector:
            self.delete(uid, memory_id)
            return

        try:
            canonical_item = read_canonical_memory_item(uid, memory_id, db_client=self._db_client)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
        if canonical_item is not None:
            self._write_historical_override(uid, memory_id, MemoryItemStatus.tombstoned)
            self._canonical.delete(uid, memory_id)
        else:
            status = self._canonical_status(uid, memory_id)
            if status is not None:
                raise HTTPException(status_code=404, detail="Memory not found")
            record = self._history.get(uid, memory_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Memory not found")
            if record.memory.is_locked:
                raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
        self._write_historical_override(uid, memory_id, MemoryItemStatus.tombstoned)
        HistoricalMemoryAdapter.cleanup(uid, memory_id, delete_vector=False, db_client=self._db_client)

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
        del memory_system, consumer, operation, upsert_vector
        self.ensure_canonical_mutation_ready(uid)
        materialized = self._ensure_canonical_target(uid, memory_id)
        try:
            updated = self._canonical.update_content(uid, memory_id, content)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Memory not found") from exc
        if materialized:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self._db_client)
        return updated
