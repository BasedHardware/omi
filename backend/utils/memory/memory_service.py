"""Memory routing seam — surfaces route reads/writes/search through MemoryService (WS-L)."""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Collection, Dict, Iterator, List, Literal, NoReturn, Optional, Set, Tuple, cast
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError

import database.memories as memories_db
import database.vector_db as vector_db
from database._client import db as default_db_client
from database.memory_collections import MemoryCollections
from database.memory_apply_store import privacy_deletion_receipt_id
from database.memory_ledger import purge_source_replacement_receipts_for_memories
from database.legal_holds import destructive_operation_gate
from database.review_queue import purge_stale_review_conflicts_for_memories
from database.vector_db import delete_memory_vector
from models.memories import MemoryDB
from models.knowledge_ledger_search import (
    LedgerSearchSurface as LedgerSearchSurface,
    is_ledger_row_admissible as is_ledger_row_admissible,
    ledger_row_is_rejected,
)
from models.memory_apply import WriterMode
from models.product_memory import (
    MemoryAccessPolicy,
    MemoryConsumer,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemorySubjectScope,
    LedgerWriteReason,
    MemoryTier,
    ProcessingState,
    RESTRICTED_SENSITIVITY_LABELS,
    SourceState,
)
from utils.log_sanitizer import sanitize_validation_error
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted, budgeted_get_all
from utils.memory.canonical_memory_adapter import (
    CanonicalBatchMutationLimitError,
    CanonicalMemoryNotFoundError,
    CanonicalScanCursor,
    canonical_memory_lineage_ids,
    delete_default_canonical_memories,
    delete_all_canonical_memories,
    delete_canonical_memory,
    delete_canonical_memories_batch,
    memory_item_to_memorydb,
    purge_canonical_memory_projections,
    read_canonical_memory_item,
    read_canonical_memories,
    read_canonical_scan_page,
    refine_canonical_memory,
    replace_conversation_sourced_memories,
    retract_conversation_sourced_memories,
    search_canonical_memories,
    search_result_to_memorydb,
    update_canonical_memory_content,
    update_canonical_memory_visibility,
    update_canonical_memory_product_fields,
    update_canonical_memory_review,
    is_direct_user_write_authority,
    write_canonical_external_memory,
)
from utils.memory.product_memory_read_service import (
    iter_authoritative_product_memory_items,
    iter_authoritative_product_memory_items_newest_first,
)
from utils.memory.knowledge_ledger import (
    LEDGER_SCHEMA_VERSION,
    LedgerProvenance,
    LedgerWrite,
    amend_user_fact as amend_fact,
    evidence_id_for_ledger_provenance,
    reopen_standalone_fact,
    save_fact,
)
from utils.memory.ledger_history_policy import is_ledger_history_item
from utils.memory.rejected_memory_feedback import clear_rejected_memory_feedback_cache
from utils.memory.required_promotion import required_processing_payload
from config.memory_rollout import MemoryRolloutMode, rollout_mode_env_value
from utils.client_device import DeviceScopeRequest
from utils.memory.device_scope_filter import memory_matches_device
from utils.memory.memory_system import MemorySystem
from utils.memory.memory_system import ensure_canonical_apply_control_state
from utils.jit_rollout import JITDecisionStage, resolve_jit_rollout_sync
from utils.memory.memory_api_contract import MemoryApiExposure, memory_api_payload
from utils.memory.belief_model import public_belief_overlay_json
from utils.memory.universal_list_cursor import (
    StreamKeyset,
    UniversalListCursorError,
    UniversalListCursorState,
    cursor_secret,
    decode_universal_list_cursor,
    encode_universal_list_cursor,
)
from utils.metrics import (
    MEMORY_HISTORICAL_MATERIALIZATION_TOTAL,
    MEMORY_HISTORICAL_SUPPRESSION_TOTAL,
    MEMORY_UNIVERSAL_READ_ORIGIN_TOTAL,
)

logger = logging.getLogger(__name__)

MemoryBackingStoreStream = Literal['canonical', 'historical', 'cursor']


class MemoryBackingStoreUnavailable(HTTPException):
    """Recoverable backing-store failure for mixed-list reads.

    Subclasses ``HTTPException`` so existing callers keep the same 503 body.
    ``GET /v3/memories`` first-page fallback catches this type instead of
    matching ``detail`` strings — a renamed or newly added unavailable
    message must not escape to clients as a hard 503.
    """

    def __init__(self, detail: str, *, stream: MemoryBackingStoreStream) -> None:
        super().__init__(status_code=503, detail=detail)
        self.stream = stream


MemoryPayload = Dict[str, Any]
McpSearchPayload = Dict[str, Any]

MAX_LEDGER_HISTORY_PROVIDER_WINDOW = 500
MAX_LEDGER_REVERT_CHAIN_LENGTH = 64
_LEDGER_QUERY_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9']{1,63}")


def _legal_hold_gated_deletion(method: Callable[..., Any]) -> Callable[..., Any]:
    """Hold one server-owned deletion gate across legacy and canonical layers."""

    @wraps(method)
    def wrapped(self: Any, uid: str, *args: Any, **kwargs: Any) -> Any:
        with destructive_operation_gate(
            uid,
            kind="explicit_memory_deletion",
            firestore_client=self.db_client,
        ):
            return method(self, uid, *args, **kwargs)

    return wrapped


def _returned_lineage_ids(result: object, fallback: List[str]) -> List[str]:
    """Normalize the internal canonical deletion receipt for legacy test seams."""

    if isinstance(result, list):
        ids = [memory_id for memory_id in result if isinstance(memory_id, str) and memory_id]
        if ids:
            return list(dict.fromkeys(ids))
    return list(dict.fromkeys(fallback))


def _purge_required_canonical_projections(
    uid: str,
    memory_ids: List[str],
    *,
    db_client: Any,
    reason: str,
    preserve_source_replacement_receipts: bool = False,
) -> None:
    """Map provider failures to the released fail-closed deletion contract."""

    try:
        purge_canonical_memory_projections(
            uid,
            memory_ids,
            db_client=db_client,
            reason=reason,
            include_review_queue=False,
            preserve_source_replacement_receipts=preserve_source_replacement_receipts,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Canonical memory projection privacy cleanup unavailable",
        ) from exc


def _delete_historical_privacy_overrides(uid: str, memory_ids: List[str], *, db_client: Any) -> None:
    """Remove content-derived override paths after physical legacy cleanup."""

    client = db_client if db_client is not None else default_db_client
    collections = MemoryCollections(uid=uid)
    for memory_id in dict.fromkeys(memory_id for memory_id in memory_ids if memory_id):
        client.document(f"{collections.memory_historical_overrides}/{memory_id}").delete()


class DeviceScopeNotSupportedError(ValueError):
    """device_scope filtering is only supported on the canonical memory backend."""


@dataclass(frozen=True)
class ExternalMemoryWriteContext:
    """Released compatibility context for universal external memory mutations."""

    memory_system: MemorySystem
    legacy_write_allowed: bool = True
    legacy_write_status_code: int = 200
    legacy_write_detail: Any = None


@dataclass(frozen=True)
class UniversalMemoryListPage:
    """One mixed-view page plus an opaque continuation cursor.

    ``truncated`` is True only when the request's list-read budget ended the
    scan early (#11831); a truncated page carries no continuation cursor
    because its cursor state would not cover every consumed scan position.
    """

    memories: List[MemoryDB]
    next_cursor: Optional[str]
    truncated: bool = False


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


def _reject_legacy_device_scope(
    device_scope_request: Optional[DeviceScopeRequest],
) -> None:
    scope = device_scope_request.device_scope if device_scope_request else "all"
    if scope and scope != "all":
        raise DeviceScopeNotSupportedError("device_scope filtering is unavailable for this request")


@dataclass(frozen=True)
class MemorySearchMatch:
    memory: MemoryDB
    score: float


@dataclass(frozen=True)
class LedgerHistoryPage:
    """Bounded canonical ledger history with an honest provider-window signal."""

    memories: Tuple[MemoryDB, ...]
    truncated: bool
    scanned_count: int


@dataclass(frozen=True)
class LedgerHistorySearchPage:
    """Historical query results plus whether the canonical provider window ended."""

    matches: Tuple[MemorySearchMatch, ...]
    truncated: bool
    scanned_count: int
    next_offset: Optional[int] = None


@dataclass(frozen=True)
class LedgerRevertIdentity:
    """Canonical fact identity that every row in a revert chain must share."""

    kind: MemoryKind
    slot: Optional[str]
    subject_scope: Optional[MemorySubjectScope]
    subject_entity_id: Optional[str]


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


def _memory_ids_and_scores(
    matches: List[MemoryPayload],
) -> tuple[List[str], Dict[str, float]]:
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
        include_archive: bool = False,
        now: Optional[datetime] = None,
    ) -> List[MemoryDB]:
        _reject_legacy_device_scope(device_scope_request)
        del include_pending_processing, include_archive, now
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
        is_read: Optional[bool] = None,
        is_dismissed: Optional[bool] = None,
    ) -> MemoryDB:
        del uid, memory_id, tags, category, is_baseline, is_read, is_dismissed
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
        include_archive: bool = False,
        now: Optional[datetime] = None,
        budget: Optional[ListReadBudget] = None,
    ) -> List[MemoryDB]:
        return [
            truncate_locked_memory_preview(memory)
            for memory in read_canonical_memories(
                uid,
                limit=limit,
                offset=offset,
                db_client=self._db_client,
                device_scope_request=device_scope_request,
                include_pending_processing=include_pending_processing,
                include_archive=include_archive,
                now=now,
                budget=budget,
            )
        ]

    def search(
        self,
        uid: str,
        query: str,
        *,
        limit: int = 5,
        device_scope_request: Optional[DeviceScopeRequest] = None,
        item_filter: Optional[Callable[[MemoryItem], bool]] = None,
        ledger_kinds: Optional[Collection[str]] = None,
    ) -> List[MemorySearchMatch]:
        search_kwargs: Dict[str, Any] = {
            "limit": limit,
            "db_client": self._db_client,
            "device_scope_request": device_scope_request,
            "item_filter": item_filter,
        }
        if ledger_kinds is not None:
            search_kwargs["ledger_kinds"] = ledger_kinds
        items = search_canonical_memories(
            uid,
            query,
            **search_kwargs,
        )
        results: List[MemorySearchMatch] = []
        for rank, item in enumerate(items):
            if not item.get("memory_id"):
                continue
            memory_obj = search_result_to_memorydb(uid, item)
            if memory_obj.is_locked or memory_obj.user_review is False or memory_obj.invalid_at is not None:
                continue
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
        is_read: Optional[bool] = None,
        is_dismissed: Optional[bool] = None,
    ) -> MemoryDB:
        item = update_canonical_memory_product_fields(
            uid,
            memory_id,
            tags=tags,
            category=category,
            is_baseline=is_baseline,
            is_read=is_read,
            is_dismissed=is_dismissed,
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

    def delete(self, uid: str, memory_id: str) -> List[str]:
        return delete_canonical_memory(uid, memory_id, db_client=self._db_client)

    def delete_batch(self, uid: str, memory_ids: List[str]) -> List[str]:
        """Atomically tombstone a bounded set of canonical identities."""
        return delete_canonical_memories_batch(uid, memory_ids, db_client=self._db_client)

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
    # False when the row is an index stub (id + sort timestamps only). Merge
    # and suppression use stubs; the mixed list hydrates only the emitted page.
    hydrated: bool = True


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
    def _historical_memory(
        raw: MemoryPayload,
        *,
        include_locked_content: bool = False,
        uid: Optional[str] = None,
    ) -> MemoryDB:
        # Missing visibility is a compatibility case.  Public is the released
        # legacy default and is therefore retained for old documents.
        payload = memory_api_payload(raw, MemoryApiExposure.LEGACY)
        payload.setdefault("visibility", "public")
        # Historical rows live under ``users/{uid}/memories/{id}`` and a legacy
        # cohort never stored the redundant ``uid`` field, which ``MemoryDB``
        # requires.  The owning path is the authority for it, so fall back to
        # it instead of dropping the row during Pydantic validation.
        if uid is not None:
            payload.setdefault("uid", uid)
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
            memory = cls._historical_memory(raw, include_locked_content=include_locked_content, uid=uid)
        except ValidationError as exc:
            # Never log ValidationError.__str__ — it embeds input_value (memory content).
            logger.warning(
                "Skipping malformed historical memory uid=%s memory_id=%s: %s",
                uid,
                memory_id,
                sanitize_validation_error(exc),
            )
            return None
        except (TypeError, ValueError):
            logger.warning(
                "Skipping malformed historical memory uid=%s memory_id=%s type=adapt_error",
                uid,
                memory_id,
            )
            return None
        if memory.visibility not in {"private", "public", "shared"}:
            logger.warning(
                "Skipping historical memory with unknown visibility uid=%s memory_id=%s",
                uid,
                memory_id,
            )
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

    def _stub_from_index(self, uid: str, raw: Dict[str, Any]) -> Optional[HistoricalMemoryRecord]:
        memory_id = raw.get("id")
        if not isinstance(memory_id, str) or not memory_id.strip():
            return None

        def _as_datetime(value: Any) -> Optional[datetime]:
            if isinstance(value, datetime):
                return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
            if isinstance(value, str):
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return None
                return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
            return None

        created_at = _as_datetime(raw.get("created_at"))
        updated_at = _as_datetime(raw.get("updated_at")) or created_at
        if created_at is None and updated_at is None:
            return None
        created_value = created_at or updated_at
        updated_value = updated_at or created_value
        assert created_value is not None and updated_value is not None
        visibility = raw.get("visibility")
        if visibility is None or visibility == "":
            # Missing visibility is the released legacy default, same as _adapt.
            visibility = "public"
        elif visibility not in {"private", "public", "shared"}:
            return None
        capture_ids = raw.get("capture_device_ids") or []
        if not isinstance(capture_ids, list):
            capture_ids = []
        capture_ids = [device_id for device_id in capture_ids if isinstance(device_id, str) and device_id]
        try:
            memory = MemoryDB.model_validate(
                {
                    "id": memory_id,
                    "uid": uid,
                    "content": "",
                    "category": "interesting",
                    "created_at": created_value,
                    "updated_at": updated_value,
                    "visibility": visibility,
                    "capture_device_ids": capture_ids,
                }
            )
        except (ValidationError, TypeError, ValueError):
            return None
        memory = memory.model_copy(update={"memory_tier": MemoryTier.long_term})
        return HistoricalMemoryRecord(
            memory=memory,
            locator=MemoryLocator(uid=uid, origin="legacy", physical_id=memory.id),
            hydrated=False,
        )

    def hydrate_records(
        self,
        uid: str,
        records: List[HistoricalMemoryRecord],
        *,
        budget: Optional[ListReadBudget] = None,
    ) -> List[HistoricalMemoryRecord]:
        memory_ids = [record.memory.id for record in records if not record.hydrated]
        if not memory_ids:
            return records
        try:
            raw_rows = memories_db.get_memories_by_ids(uid, memory_ids, budget=budget, **self._firestore_kwargs())
        except ListReadBudgetExhausted:
            raise
        except Exception as exc:
            raise MemoryBackingStoreUnavailable("Historical memory unavailable", stream="historical") from exc
        adapted: Dict[str, HistoricalMemoryRecord] = {}
        for raw in raw_rows:
            record = self._adapt(uid, raw)
            if record is None:
                continue
            adapted[record.memory.id] = record
        hydrated: List[HistoricalMemoryRecord] = []
        for record in records:
            if record.hydrated:
                hydrated.append(record)
                continue
            replacement = adapted.get(record.memory.id)
            if replacement is not None:
                hydrated.append(replacement)
        return hydrated

    def read(
        self,
        uid: str,
        *,
        limit: int = 100,
        offset: int = 0,
        device_scope_request: Optional[DeviceScopeRequest] = None,
        hydrate: bool = True,
        budget: Optional[ListReadBudget] = None,
    ) -> List[HistoricalMemoryRecord]:
        bounded_limit = max(1, min(int(limit or 100), self.MAX_COMPATIBILITY_WINDOW))
        bounded_offset = max(0, int(offset or 0))
        needed = bounded_offset + bounded_limit
        if needed > self.MAX_COMPATIBILITY_WINDOW:
            raise HTTPException(status_code=413, detail="Historical memory pagination window exceeded")
        # Index the whole prefix in one dual-window metadata query, then hydrate
        # only the returned page. ``updated_or_created_desc`` has no single index,
        # so the helper streams two candidate windows of ``limit + offset``
        # documents. Hydrating that prefix (and decrypting it) is what took
        # GET /v3/memories past the 30s edge timeout on 2026-08-18 once first
        # pages fell back here. Mixed-list expansion needs prefix ids and
        # timestamps, not content — pass hydrate=False for that caller.
        # Grow the indexed prefix when adapt/device filters skip rows so a page
        # of N valid memories is not silently shortened by malformed documents.
        # With a ``budget`` both windows of every expansion round charge their
        # fetched rows and each stream runs under the per-RPC timeout (#11831).
        index_limit = needed
        records: List[HistoricalMemoryRecord] = []
        try:
            while True:
                index_rows = memories_db.list_memory_updated_or_created_index(
                    uid,
                    index_limit,
                    0,
                    budget=budget,
                    **self._firestore_kwargs(),
                )
                records = []
                for raw in index_rows:
                    record = self._stub_from_index(uid, raw)
                    if record is None or not self.matches_device(record, device_scope_request):
                        continue
                    records.append(record)
                    if len(records) >= needed:
                        break
                if len(records) >= needed or len(index_rows) < index_limit:
                    break
                if index_limit >= self.MAX_COMPATIBILITY_WINDOW:
                    break
                index_limit = min(
                    self.MAX_COMPATIBILITY_WINDOW,
                    max(index_limit + bounded_limit, index_limit * 2),
                )
        except ListReadBudgetExhausted:
            # The request budget ended this read: return the rows already known
            # so the caller can serve an explicitly truncated prefix instead of
            # converting the typed exhaustion into a 503.
            records.sort(
                key=lambda record: (
                    -self._timestamp(record.memory).timestamp(),
                    record.memory.id,
                )
            )
            return records[bounded_offset : bounded_offset + bounded_limit]
        except Exception as exc:
            raise MemoryBackingStoreUnavailable("Historical memory unavailable", stream="historical") from exc
        records.sort(
            key=lambda record: (
                -self._timestamp(record.memory).timestamp(),
                record.memory.id,
            )
        )
        page = records[bounded_offset : bounded_offset + bounded_limit]
        if not hydrate or not page:
            return page
        return self.hydrate_records(uid, page, budget=budget)

    def read_scan_page(
        self,
        uid: str,
        *,
        limit: int = 100,
        scan_offset: int = 0,
        device_scope_request: Optional[DeviceScopeRequest] = None,
    ) -> NoReturn:
        """Retired offset scan — cursor paging must use dual keyset streams.

        Kept only so accidental callers fail loudly instead of silently
        reintroducing the 5000/source-window offset race.
        """
        del uid, limit, scan_offset, device_scope_request
        raise RuntimeError("historical offset scan is retired; use read_updated_scan_page / read_created_scan_page")

    def _adapt_scan_payloads(
        self,
        uid: str,
        payloads: List[Dict[str, Any]],
        cursors: List[Tuple[datetime, str]],
        *,
        device_scope_request: Optional[DeviceScopeRequest],
        drop_updated_at_present: bool = False,
        include_locked_content: bool = False,
    ) -> List[Tuple[Optional[HistoricalMemoryRecord], Tuple[datetime, str]]]:
        slots: List[Tuple[Optional[HistoricalMemoryRecord], Tuple[datetime, str]]] = []
        for raw, scan_cursor in zip(payloads, cursors):
            if drop_updated_at_present and raw.get('updated_at') is not None:
                # Owned by the updated_at stream — advance created cursor only.
                slots.append((None, scan_cursor))
                continue
            if raw.get('user_review') is False or raw.get('invalid_at') is not None:
                slots.append((None, scan_cursor))
                continue
            decrypted = memories_db.prepare_memory_for_read(raw, uid) or raw
            decrypted = dict(decrypted)
            decrypted['id'] = raw.get('id')
            record = self._adapt(uid, decrypted, include_locked_content=include_locked_content)
            if record is None or not self.matches_device(record, device_scope_request):
                slots.append((None, scan_cursor))
            else:
                slots.append((record, scan_cursor))
        return slots

    def read_updated_scan_page(
        self,
        uid: str,
        *,
        limit: int = 100,
        start_after: Optional[Tuple[datetime, str]] = None,
        device_scope_request: Optional[DeviceScopeRequest] = None,
        include_locked_content: bool = False,
        budget: Optional[ListReadBudget] = None,
    ) -> Tuple[List[Tuple[Optional[HistoricalMemoryRecord], Tuple[datetime, str]]], bool]:
        """Bounded updated_at-present historical keyset page."""
        bounded_limit = max(1, min(int(limit or 100), self.MAX_PAGE_SIZE))
        try:
            payloads, cursors, exhausted = memories_db.scan_memories_updated_at_page(
                uid,
                limit=bounded_limit,
                start_after=start_after,
                budget=budget,
                **self._firestore_kwargs(),
            )
        except (HTTPException, ListReadBudgetExhausted):
            raise
        except Exception as exc:
            raise MemoryBackingStoreUnavailable("Historical memory unavailable", stream="historical") from exc
        slots = self._adapt_scan_payloads(
            uid,
            payloads,
            cursors,
            device_scope_request=device_scope_request,
            drop_updated_at_present=False,
            include_locked_content=include_locked_content,
        )
        return slots, exhausted

    def read_created_scan_page(
        self,
        uid: str,
        *,
        limit: int = 100,
        start_after: Optional[Tuple[datetime, str]] = None,
        device_scope_request: Optional[DeviceScopeRequest] = None,
        include_locked_content: bool = False,
        budget: Optional[ListReadBudget] = None,
    ) -> Tuple[List[Tuple[Optional[HistoricalMemoryRecord], Tuple[datetime, str]]], bool]:
        """Bounded created_at historical keyset page with updated_at-present filtered out."""
        bounded_limit = max(1, min(int(limit or 100), self.MAX_PAGE_SIZE))
        try:
            payloads, cursors, exhausted = memories_db.scan_memories_created_at_page(
                uid,
                limit=bounded_limit,
                start_after=start_after,
                budget=budget,
                **self._firestore_kwargs(),
            )
        except (HTTPException, ListReadBudgetExhausted):
            raise
        except Exception as exc:
            raise MemoryBackingStoreUnavailable("Historical memory unavailable", stream="historical") from exc
        slots = self._adapt_scan_payloads(
            uid,
            payloads,
            cursors,
            device_scope_request=device_scope_request,
            drop_updated_at_present=True,
            include_locked_content=include_locked_content,
        )
        return slots, exhausted

    def get(self, uid: str, memory_id: str) -> Optional[HistoricalMemoryRecord]:
        try:
            raw = memories_db.get_memory(uid, memory_id, **self._firestore_kwargs())
        except Exception as exc:
            raise MemoryBackingStoreUnavailable("Historical memory unavailable", stream="historical") from exc
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
            raise MemoryBackingStoreUnavailable("Historical memory unavailable", stream="historical") from exc
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
    def cleanup(
        uid: str,
        memory_id: str,
        *,
        delete_vector: bool = True,
        db_client: Any = None,
        required: bool = False,
    ) -> None:
        """Physically clean one historical row after canonical authority commits.

        Explicit privacy deletion sets ``required``. It deletes the rebuildable
        vector first so a later Firestore failure leaves the content row (and
        therefore its retry identity) intact. Suppression/tombstones prevent
        resurrection while the caller retries the failed request.
        """
        failures: List[str] = []
        if delete_vector:
            if required and getattr(vector_db, "index", None) is None:
                raise HTTPException(status_code=503, detail="Historical memory privacy cleanup unavailable")
            try:
                delete_memory_vector(uid, memory_id)
            except Exception:
                failures.append("vector")
                logger.exception(
                    "historical vector cleanup failed uid=%s memory_id=%s",
                    uid,
                    memory_id,
                )
        if required and failures:
            # Keep the content row as a durable retry identity until its vector
            # has definitely been removed.
            raise HTTPException(status_code=503, detail="Historical memory privacy cleanup incomplete")
        try:
            kwargs = {"firestore_client": db_client} if db_client is not None else {}
            memories_db.delete_memory(uid, memory_id, **kwargs)
        except Exception:
            failures.append("content")
            logger.exception("historical memory cleanup failed uid=%s memory_id=%s", uid, memory_id)
        if required and failures:
            raise HTTPException(status_code=503, detail="Historical memory privacy cleanup incomplete")

    def iter_all_live(
        self,
        uid: str,
        *,
        page_size: int = 500,
        device_scope_request: Optional[DeviceScopeRequest] = None,
        include_locked_content: bool = True,
    ) -> Iterator[HistoricalMemoryRecord]:
        """Stream every historical live row through stable dual-keyset scans."""
        page_size = max(1, min(int(page_size or 500), self.MAX_PAGE_SIZE))

        def records(kind: str) -> Iterator[HistoricalMemoryRecord]:
            cursor: Optional[Tuple[datetime, str]] = None
            exhausted = False
            while not exhausted:
                reader = self.read_updated_scan_page if kind == "updated" else self.read_created_scan_page
                slots, exhausted = reader(
                    uid,
                    limit=page_size,
                    start_after=cursor,
                    device_scope_request=device_scope_request,
                    include_locked_content=include_locked_content,
                )
                if not slots and not exhausted:
                    raise HTTPException(status_code=503, detail="Historical memory scan made no progress")
                for record, cursor in slots:
                    if record is None:
                        continue
                    yield record

        updated = records("updated")
        created = records("created")
        updated_record = next(updated, None)
        created_record = next(created, None)
        while updated_record is not None or created_record is not None:
            take_updated = created_record is None or (
                updated_record is not None
                and self._timestamp(updated_record.memory) >= self._timestamp(created_record.memory)
            )
            if take_updated:
                assert updated_record is not None
                yield updated_record
                updated_record = next(updated, None)
            else:
                assert created_record is not None
                yield created_record
                created_record = next(created, None)

    def all_live(self, uid: str, *, page_size: int = 500) -> List[HistoricalMemoryRecord]:
        """Enumerate historical live rows in bounded pages for explicit export only."""
        records = list(self.iter_all_live(uid, page_size=page_size))
        records.sort(
            key=lambda record: (
                -self._timestamp(record.memory).timestamp(),
                record.memory.id,
            )
        )
        return records

    @staticmethod
    def ids(uid: str, *, limit: Optional[int] = None, offset: int = 0, db_client: Any = None) -> List[str]:
        """Return physical IDs without decrypting historical content.

        Ordinary reads never call this seam. Explicit privacy operations may
        request the complete ID inventory so delete-all/account deletion cannot
        silently stop at an arbitrary compatibility cap.
        """
        try:
            ids = memories_db.get_memory_ids(
                uid,
                **({"firestore_client": db_client} if db_client is not None else {}),
            )
        except Exception as exc:
            raise MemoryBackingStoreUnavailable("Historical memory unavailable", stream="historical") from exc
        start = max(0, offset)
        selected = ids[start:] if limit is None else ids[start : start + max(1, limit)]
        return [memory_id for memory_id in selected if memory_id]

    @classmethod
    def cleanup_all(cls, uid: str, *, db_client: Any = None, required: bool = False) -> None:
        """Physically clean all historical rows after a canonical delete-all."""
        try:
            ids = cls.ids(uid, db_client=db_client)
        except Exception as exc:
            logger.exception("historical delete-all id scan failed uid=%s", uid)
            if required:
                if isinstance(exc, HTTPException):
                    raise
                raise HTTPException(status_code=503, detail="Historical memory privacy cleanup unavailable") from exc
            return
        for memory_id in ids:
            cls.cleanup(uid, memory_id, db_client=db_client, required=required)


# A page walks past rows it must not emit (canonical-suppressed historical rows,
# lineage-filtered canonical rows) before it can fill `limit`. That walk is
# proportional to the account's skipped prefix, not to the page size: an account
# whose whole historical set is suppressed by canonical scans every historical
# document for a `limit=8` first page. In prod on 2026-08-18 that walk ran past
# the 30s edge timeout and GET /v3/memories 504'd (~100/h, first pages only,
# offset=0) once the `memories` composite indexes went READY and the keyset scans
# actually started serving. Bound the skipped work per request so a page either
# lands or fails fast into the route's offset-read fallback.
MEMORY_LIST_SCAN_ROW_BUDGET = 4000
# The row budget alone does not bound the wall clock: 4000 skipped rows is ~80
# sequential Firestore round trips, which at prod latency still lands near the
# 30s edge timeout — and the offset-read fallback the budget exists to reach
# then has no time left to answer. First pages kept 504ing after the row budget
# shipped (~40/h on 2026-08-18T08:09Z+, offset=0 only) for exactly that reason.
# Bound the skipped walk in seconds too, leaving the bulk of the request budget
# for the fallback read.
MEMORY_LIST_SCAN_DEADLINE_SECONDS = 6.0
MEMORY_LIST_SCAN_BUDGET_DETAIL = "Memory scan budget exceeded"
# First-page 504s on 2026-08-18 still spent 17s+ inside ``read_page`` before
# ``get_memories`` ran: ``max(page_limit, 50)`` fetched 500-doc chunks and
# decrypted them before ``charge()`` could see the 6s deadline. Cap each
# keyset fetch so the deadline is checked between small pages.
MEMORY_LIST_SCAN_CHUNK_SIZE = 50


class _ScanRowBudget:
    """Bounds the rows and the seconds one ``read_page`` call may skip without emitting.

    With a request ``parent`` (:class:`ListReadBudget`, #11831) every charged
    row also charges the request budget and the walk sub-deadline never extends
    past the request deadline. Sub-budget exhaustion keeps its historical
    meaning — 503 ``MEMORY_LIST_SCAN_BUDGET_DETAIL`` so the route's offset-read
    fallback can serve the page — while parent exhaustion raises the typed
    ``ListReadBudgetExhausted`` that maps to a truncated response.
    """

    def __init__(
        self,
        limit: Optional[int] = None,
        *,
        deadline_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
        parent: Optional[ListReadBudget] = None,
    ) -> None:
        # Read the module constants at construction, not as default arguments,
        # so the bounds stay tunable in one place.
        self._parent = parent
        if parent is not None:
            rows = MEMORY_LIST_SCAN_ROW_BUDGET if limit is None else limit
            self._remaining = max(1, min(int(rows), parent.remaining_documents))
            seconds = MEMORY_LIST_SCAN_DEADLINE_SECONDS if deadline_seconds is None else deadline_seconds
            # The walk sub-deadline starts now but must stop at the request deadline.
            self._deadline = min(clock() + max(0.0, float(seconds)), clock() + max(0.0, parent.remaining_seconds))
        else:
            self._remaining = max(1, int(MEMORY_LIST_SCAN_ROW_BUDGET if limit is None else limit))
            seconds = MEMORY_LIST_SCAN_DEADLINE_SECONDS if deadline_seconds is None else deadline_seconds
            self._deadline = clock() + max(0.0, float(seconds))
        self._clock = clock

    def check(self, stream: MemoryBackingStoreStream = "historical") -> None:
        # Parent exhaustion is checked first and wins: a request out of time
        # must truncate, not fall back into another read.
        if self._parent is not None:
            self._parent.check()
        if self._remaining < 0 or self._clock() >= self._deadline:
            raise MemoryBackingStoreUnavailable(MEMORY_LIST_SCAN_BUDGET_DETAIL, stream=stream)

    def charge(self, stream: MemoryBackingStoreStream = "historical") -> None:
        self._remaining -= 1
        if self._parent is not None:
            # Rows the scan walks past still crossed the wire for this request.
            self._parent.charge(1)
        self.check(stream=stream)


class _HistoricalRawStream:
    """Peekable keyset stream over one historical Firestore order field."""

    def __init__(
        self,
        *,
        service: "MemoryService",
        uid: str,
        kind: str,
        scan: Optional[StreamKeyset],
        exhausted: bool,
        device_scope_request: Optional[DeviceScopeRequest],
        page_limit: int,
        budget: Optional[_ScanRowBudget] = None,
        rpc_budget: Optional[ListReadBudget] = None,
    ) -> None:
        self._service = service
        self._uid = uid
        self._kind = kind
        self.scan_keyset = scan
        self.exhausted = bool(exhausted)
        self._budget = budget or _ScanRowBudget()
        self._rpc_budget = rpc_budget
        self._device_scope_request = device_scope_request
        self._page_limit = max(1, int(page_limit or 100))
        self._peek: Optional[MemoryDB] = None
        self._peek_keyset: Optional[StreamKeyset] = None
        self._peek_scan: Optional[StreamKeyset] = None
        self._slots: List[Tuple[Optional[HistoricalMemoryRecord], StreamKeyset]] = []
        self._slot_index = 0
        self._slots_exhausted = self.exhausted
        self._chunk_statuses: Dict[str, MemoryItemStatus] = {}
        self.identity_suppressed = 0
        self.state_suppressed = 0

    def _ensure_slots(self) -> None:
        if self._slot_index < len(self._slots) or self.exhausted:
            return
        self._budget.check()
        start_after: Optional[Tuple[datetime, str]] = None
        if self.scan_keyset is not None:
            start_after = self._service.stream_keyset_to_scan_cursor(self.scan_keyset)
        reader = (
            self._service.history.read_updated_scan_page
            if self._kind == "updated"
            else self._service.history.read_created_scan_page
        )
        try:
            raw_slots, stream_exhausted = reader(
                self._uid,
                limit=MEMORY_LIST_SCAN_CHUNK_SIZE,
                start_after=start_after,
                device_scope_request=self._device_scope_request,
                budget=self._rpc_budget,
            )
        except (HTTPException, ListReadBudgetExhausted):
            raise
        except Exception as exc:
            raise MemoryBackingStoreUnavailable("Historical memory unavailable", stream="historical") from exc
        self._slots = [
            (
                record,
                self._service.scan_cursor_to_stream_keyset(scan_cursor),
            )
            for record, scan_cursor in raw_slots
        ]
        self._slot_index = 0
        self._slots_exhausted = stream_exhausted
        # Batch canonical status suppression once per chunk, never per row.
        visible_ids = [record.memory.id for record, _ in self._slots if record is not None]
        self._chunk_statuses = (
            self._service.canonical_statuses(self._uid, visible_ids, budget=self._rpc_budget) if visible_ids else {}
        )
        if not self._slots:
            self.exhausted = True

    def peek(self) -> Optional[MemoryDB]:
        if self._peek is not None:
            return self._peek
        while True:
            self._ensure_slots()
            if self._slot_index >= len(self._slots):
                self.exhausted = True
                return None
            record, scan_keyset = self._slots[self._slot_index]
            if record is None:
                self._budget.charge()
                self.scan_keyset = scan_keyset
                self._advance_raw_slot()
                continue
            memory = truncate_locked_memory_preview(record.memory)
            reason = self._service.historical_suppression_reason(
                memory.id,
                statuses=self._chunk_statuses,
            )
            if reason == "canonical_identity":
                self.identity_suppressed += 1
                self._budget.charge()
                self.scan_keyset = scan_keyset
                self._advance_raw_slot()
                continue
            if reason == "canonical_state":
                self.state_suppressed += 1
                self._budget.charge()
                self.scan_keyset = scan_keyset
                self._advance_raw_slot()
                continue
            self._peek = memory
            self._peek_keyset = self._service.memory_keyset(memory)
            self._peek_scan = scan_keyset
            return memory

    def _advance_raw_slot(self) -> None:
        self._slot_index += 1
        if self._slot_index >= len(self._slots):
            self.exhausted = self._slots_exhausted
            self._slots = []
            self._slot_index = 0
            self._chunk_statuses = {}

    def consume(self) -> None:
        if self._peek is None or self._peek_keyset is None or self._peek_scan is None:
            raise RuntimeError("historical raw stream consume without peek")
        self.scan_keyset = self._peek_scan
        self._peek = None
        self._peek_keyset = None
        self._peek_scan = None
        self._advance_raw_slot()

    @property
    def peek_keyset(self) -> Optional[StreamKeyset]:
        return self._peek_keyset


class _HistoricalCursorStream:
    """Merge updated_at-present and created_at-only historical keyset streams."""

    def __init__(
        self,
        *,
        service: "MemoryService",
        uid: str,
        after: Optional[StreamKeyset],
        updated_scan: Optional[StreamKeyset],
        created_scan: Optional[StreamKeyset],
        updated_exhausted: bool,
        created_exhausted: bool,
        device_scope_request: Optional[DeviceScopeRequest],
        page_limit: int,
        budget: Optional[_ScanRowBudget] = None,
        rpc_budget: Optional[ListReadBudget] = None,
    ) -> None:
        self._service = service
        self.consumed_keyset = after
        budget = budget or _ScanRowBudget()
        self._updated = _HistoricalRawStream(
            service=service,
            uid=uid,
            kind="updated",
            scan=updated_scan,
            exhausted=updated_exhausted,
            device_scope_request=device_scope_request,
            page_limit=page_limit,
            budget=budget,
            rpc_budget=rpc_budget,
        )
        self._created = _HistoricalRawStream(
            service=service,
            uid=uid,
            kind="created",
            scan=created_scan,
            exhausted=created_exhausted,
            device_scope_request=device_scope_request,
            page_limit=page_limit,
            budget=budget,
            rpc_budget=rpc_budget,
        )
        self._peek_source: Optional[str] = None

    @property
    def updated_scan_keyset(self) -> Optional[StreamKeyset]:
        return self._updated.scan_keyset

    @property
    def created_scan_keyset(self) -> Optional[StreamKeyset]:
        return self._created.scan_keyset

    @property
    def updated_exhausted(self) -> bool:
        return self._updated.exhausted and self._updated.peek() is None

    @property
    def created_exhausted(self) -> bool:
        return self._created.exhausted and self._created.peek() is None

    @property
    def exhausted(self) -> bool:
        return self.updated_exhausted and self.created_exhausted

    @property
    def identity_suppressed(self) -> int:
        return self._updated.identity_suppressed + self._created.identity_suppressed

    @property
    def state_suppressed(self) -> int:
        return self._updated.state_suppressed + self._created.state_suppressed

    def peek(self) -> Optional[MemoryDB]:
        updated_memory = self._updated.peek()
        created_memory = self._created.peek()
        if updated_memory is None and created_memory is None:
            self._peek_source = None
            return None
        take_updated = created_memory is None or (
            updated_memory is not None
            and self._service.memory_cursor_sort_key(updated_memory)
            <= self._service.memory_cursor_sort_key(created_memory)
        )
        if take_updated:
            self._peek_source = "updated"
            return updated_memory
        self._peek_source = "created"
        return created_memory

    def consume(self) -> None:
        if self._peek_source == "updated":
            memory = self._updated.peek()
            if memory is not None:
                self.consumed_keyset = self._service.memory_keyset(memory)
            self._updated.consume()
        elif self._peek_source == "created":
            memory = self._created.peek()
            if memory is not None:
                self.consumed_keyset = self._service.memory_keyset(memory)
            self._created.consume()
        else:
            raise RuntimeError("historical cursor stream consume without peek")
        self._peek_source = None


class _CanonicalCursorStream:
    """Peekable canonical stream over bounded Firestore keyset scan pages."""

    def __init__(
        self,
        *,
        service: "MemoryService",
        uid: str,
        emitted: Optional[StreamKeyset],
        scan: Optional[StreamKeyset],
        exhausted: bool,
        device_scope_request: Optional[DeviceScopeRequest],
        include_pending_processing: bool,
        include_archive: bool,
        now: Optional[datetime],
        page_limit: int,
        budget: Optional[_ScanRowBudget] = None,
        rpc_budget: Optional[ListReadBudget] = None,
    ) -> None:
        self._service = service
        self._uid = uid
        self.emitted_keyset = emitted
        self.scan_keyset = scan
        self.exhausted = bool(exhausted)
        self._budget = budget or _ScanRowBudget()
        self._rpc_budget = rpc_budget
        self._device_scope_request = device_scope_request
        self._include_pending_processing = include_pending_processing
        self._include_archive = include_archive
        self._now = now
        self._page_limit = max(1, int(page_limit or 100))
        self._peek: Optional[MemoryDB] = None
        self._peek_keyset: Optional[StreamKeyset] = None
        self._peek_scan: Optional[StreamKeyset] = None
        self._slots: List[Tuple[Optional[MemoryDB], StreamKeyset]] = []
        self._slot_index = 0
        self._slots_exhausted = self.exhausted

    def _ensure_slots(self) -> None:
        if self._slot_index < len(self._slots) or self.exhausted:
            return
        self._budget.check(stream="canonical")
        start_after: Optional[CanonicalScanCursor] = None
        if self.scan_keyset is not None:
            start_after = self._service.stream_keyset_to_scan_cursor(self.scan_keyset)
        try:
            raw_slots, stream_exhausted = read_canonical_scan_page(
                self._uid,
                limit=MEMORY_LIST_SCAN_CHUNK_SIZE,
                start_after=start_after,
                db_client=self._service.db_client,
                device_scope_request=self._device_scope_request,
                include_pending_processing=self._include_pending_processing,
                now=self._now,
                budget=self._rpc_budget,
            )
        except (HTTPException, ListReadBudgetExhausted):
            raise
        except Exception as exc:
            # Surface the underlying failure class/message so a Firestore
            # FAILED_PRECONDITION (missing composite) is distinguishable from a
            # uid/cursor ValueError in logs. No uid or memory content here.
            logger.exception(
                "canonical list scan page failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            raise MemoryBackingStoreUnavailable("Canonical memory unavailable", stream="canonical") from exc
        self._slots = [
            (
                truncate_locked_memory_preview(memory) if memory is not None else None,
                self._service.scan_cursor_to_stream_keyset(scan_cursor),
            )
            for memory, scan_cursor in raw_slots
        ]
        self._slot_index = 0
        self._slots_exhausted = stream_exhausted
        if not self._slots:
            self.exhausted = True

    def peek(self) -> Optional[MemoryDB]:
        if self._peek is not None:
            return self._peek
        while True:
            self._ensure_slots()
            if self._slot_index >= len(self._slots):
                self.exhausted = True
                return None
            memory, scan_keyset = self._slots[self._slot_index]
            # Raw scan position advances for filtered rows too.
            if memory is None:
                self._budget.charge(stream="canonical")
                self.scan_keyset = scan_keyset
                self._advance_raw_slot()
                continue
            if self.emitted_keyset is not None and self._service.memory_cursor_sort_key(memory) <= (
                self._service.keyset_sort_key(self.emitted_keyset)
            ):
                self._budget.charge(stream="canonical")
                self.scan_keyset = scan_keyset
                self._advance_raw_slot()
                continue
            self._peek = memory
            self._peek_keyset = self._service.memory_keyset(memory)
            self._peek_scan = scan_keyset
            return memory

    def _advance_raw_slot(self) -> None:
        self._slot_index += 1
        if self._slot_index >= len(self._slots):
            self.exhausted = self._slots_exhausted
            self._slots = []
            self._slot_index = 0

    def consume(self) -> None:
        if self._peek is None or self._peek_keyset is None or self._peek_scan is None:
            raise RuntimeError("canonical cursor stream consume without peek")
        self.emitted_keyset = self._peek_keyset
        self.scan_keyset = self._peek_scan
        self._peek = None
        self._peek_keyset = None
        self._peek_scan = None
        self._advance_raw_slot()


class MemoryService:
    """Universal memory authority for every authenticated UID.

    ``memory_system`` arguments remain on compatibility methods because released
    callers still send them, but they are intentionally ignored.  Canonical
    apply is the sole write authority; historical documents are a bounded,
    protected read adapter and only a cleanup target after canonical commit.
    """

    def _invalidate_prompt_cache(self, uid: str) -> None:
        clear_rejected_memory_feedback_cache(uid)
        try:
            from utils.llms.memory import clear_prompt_data_cache
        except ImportError:
            return
        clear_prompt_data_cache(uid)

    def __init__(self, *, db_client: Any = None):
        self.db_client = db_client
        self.history = HistoricalMemoryAdapter(db_client=db_client)
        # Keep these attributes for callers/tests that inspect the old seam.
        self._legacy = self.history
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
        client = self.db_client if self.db_client is not None else default_db_client
        try:
            from database.memory_collections import MemoryCollections
            from models.product_memory import MemoryItem

            snapshot = client.document(f"{MemoryCollections(uid=uid).memory_items}/{memory_id}").get()
            if getattr(snapshot, "exists", False) is not True:
                receipt_id = privacy_deletion_receipt_id(uid, memory_id)
                receipt = client.document(f"{MemoryCollections(uid=uid).memory_deletion_receipts}/{receipt_id}").get()
                if getattr(receipt, "exists", False) is True:
                    receipt_payload = receipt.to_dict()
                    if (
                        isinstance(receipt_payload, dict)
                        and receipt_payload.get("schema_version") == "memory_deletion_receipt.v2"
                        and receipt_payload.get("uid") == uid
                        and receipt_payload.get("receipt_id") == receipt_id
                    ):
                        return MemoryItemStatus.tombstoned
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

    def _canonical_item_for_lineage(self, uid: str, memory_id: str) -> Optional[MemoryItem]:
        """Read one identity-checked canonical row, including closed history."""
        client = self.db_client if self.db_client is not None else default_db_client
        try:
            snapshot = client.document(f"{MemoryCollections(uid=uid).memory_items}/{memory_id}").get()
            if getattr(snapshot, "exists", False) is not True:
                return None
            payload = snapshot.to_dict()
            if not isinstance(payload, dict):
                raise ValueError("canonical memory payload is malformed")
            item = MemoryItem.model_validate(payload)
            if item.uid != uid or item.memory_id != memory_id or str(getattr(snapshot, "id", memory_id)) != memory_id:
                raise ValueError("canonical memory identity mismatch")
            return item
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc

    @staticmethod
    def _ledger_correction_action_id(item: MemoryItem, content: str) -> str:
        identity = f"{item.memory_id}\0{item.item_revision}\0{content}".encode("utf-8")
        return f"memory_ui_correction:{hashlib.sha256(identity).hexdigest()}"

    def _retry_ledger_fact_correction(
        self,
        uid: str,
        prior: MemoryItem,
        content: str,
    ) -> Optional[MemoryDB]:
        """Return the exact prior correction on an HTTP retry, without rewriting history."""
        replacement_id = (prior.superseded_by or "").strip()
        if prior.status != MemoryItemStatus.superseded or not replacement_id:
            return None
        replacement = self._canonical_item_for_lineage(uid, replacement_id)
        if replacement is None:
            return None
        if not self._is_exact_ledger_fact_correction(prior, replacement, content):
            return None
        return memory_item_to_memorydb(replacement)

    @staticmethod
    def _is_exact_ledger_fact_correction(prior: MemoryItem, replacement: MemoryItem, content: str) -> bool:
        # The atomic supersession commit advances the closed source row by one
        # revision.  Its correction evidence intentionally names the revision
        # that was active when the user edited it, which remains the current
        # revision on immediate readback and is ``closed_revision - 1`` on an
        # HTTP retry after the commit succeeded.
        source_revision = prior.item_revision
        if prior.status == MemoryItemStatus.superseded:
            source_revision -= 1
        if source_revision < 1:
            return False
        expected_source_version = f"item_revision:{source_revision}"
        has_correction_evidence = any(
            evidence.source_type == "explicit_user_correction"
            and evidence.source_id == prior.memory_id
            and evidence.source_version == expected_source_version
            for evidence in replacement.evidence
        )
        return not (
            replacement.status != MemoryItemStatus.active
            or replacement.ledger_schema_version != LEDGER_SCHEMA_VERSION
            or replacement.kind != MemoryKind.fact
            or replacement.valid_to is not None
            or bool((replacement.superseded_by or "").strip())
            or not replacement.intent_backed
            or replacement.write_reason != LedgerWriteReason.direct_user_statement
            or not replacement.user_asserted
            or (replacement.content or "").strip() != content
            or replacement.slot != prior.slot
            or replacement.subject_scope != prior.subject_scope
            or replacement.subject_entity_id != prior.subject_entity_id
            or replacement.curation_weight != prior.curation_weight
            or replacement.visibility != prior.visibility
            or not has_correction_evidence
        )

    def _correct_ledger_fact(self, uid: str, prior: MemoryItem, content: str) -> MemoryDB:
        normalized = (content or "").strip()
        if not normalized:
            raise HTTPException(status_code=422, detail="Memory correction must not be blank")
        if prior.ledger_schema_version != LEDGER_SCHEMA_VERSION or prior.kind != MemoryKind.fact:
            raise HTTPException(status_code=409, detail="Only knowledge ledger facts may be corrected")
        if memory_item_to_memorydb(prior).is_locked:
            raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
        if prior.visibility not in {"private", "public", "shared"}:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable")
        if prior.status != MemoryItemStatus.active or prior.valid_to is not None or prior.superseded_by:
            retried = self._retry_ledger_fact_correction(uid, prior, normalized)
            if retried is not None:
                self._invalidate_prompt_cache(uid)
                return retried
            raise HTTPException(status_code=409, detail="Historical knowledge ledger rows are read-only")

        provenance = LedgerProvenance(
            source_id=prior.memory_id,
            source_type="explicit_user_correction",
            source_version=f"item_revision:{prior.item_revision}",
            action_id=self._ledger_correction_action_id(prior, normalized),
            artifact_ref={"surface": "memory_edit_api"},
        )
        try:
            replacement_id = amend_fact(
                uid,
                prior.memory_id,
                normalized,
                provenance=provenance,
                write_reason=LedgerWriteReason.direct_user_statement,
                slot=prior.slot,
                subject_scope=prior.subject_scope or MemorySubjectScope.primary_user,
                subject_entity_id=prior.subject_entity_id,
                curation_weight=prior.curation_weight,
                visibility=cast(Literal["private", "public", "shared"], prior.visibility),
                db_client=self.db_client,
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="Knowledge ledger correction conflicted") from exc
        # The append/supersede transaction is already durable once amend_fact
        # returns. Invalidate before readback so a transient readback failure
        # cannot leave a successfully corrected fact in a stale prompt cache.
        self._invalidate_prompt_cache(uid)
        replacement = self._canonical_item_for_lineage(uid, replacement_id)
        if replacement is None or not self._is_exact_ledger_fact_correction(prior, replacement, normalized):
            raise HTTPException(status_code=503, detail="Knowledge ledger correction readback unavailable")
        return memory_item_to_memorydb(replacement)

    @staticmethod
    def _normalized_revert_operation_id(operation_id: str) -> str:
        try:
            normalized = str(UUID(str(operation_id or "").strip()))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Invalid memory revert operation id") from exc
        return normalized

    @staticmethod
    def _ledger_revert_identity(
        item: MemoryItem,
    ) -> LedgerRevertIdentity:
        return LedgerRevertIdentity(
            kind=item.kind,
            slot=item.slot,
            subject_scope=item.subject_scope,
            subject_entity_id=item.subject_entity_id,
        )

    @staticmethod
    def _validate_ledger_revert_item(item: MemoryItem, *, identity: LedgerRevertIdentity) -> None:
        if (
            item.ledger_schema_version != LEDGER_SCHEMA_VERSION
            or item.kind != MemoryKind.fact
            or not item.intent_backed
            or item.processing_state != ProcessingState.processed
            or item.source_state != SourceState.active
            or set(item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS)
            or MemoryService._ledger_revert_identity(item) != identity
        ):
            raise HTTPException(status_code=409, detail="Knowledge ledger history cannot be restored")

    @staticmethod
    def _is_standalone_closed_ledger_fact(item: MemoryItem) -> bool:
        return (
            item.ledger_schema_version == LEDGER_SCHEMA_VERSION
            and item.kind == MemoryKind.fact
            and item.intent_backed
            and item.status == MemoryItemStatus.superseded
            and item.valid_to is not None
            and not (item.superseded_by or "").strip()
            and not (item.canonical_memory_id or "").strip()
        )

    @staticmethod
    def _is_exact_standalone_ledger_reopen(
        selected: MemoryItem,
        replacement: MemoryItem,
        *,
        evidence_id: str,
    ) -> bool:
        has_reopen_evidence = any(
            evidence.evidence_id == evidence_id
            and evidence.source_type == "explicit_user_reopen"
            and evidence.source_id == selected.memory_id
            and evidence.source_version == f"item_revision:{selected.item_revision}"
            for evidence in replacement.evidence
        )
        return not (
            replacement.uid != selected.uid
            or replacement.status != MemoryItemStatus.active
            or replacement.valid_to is not None
            or (replacement.superseded_by or "").strip()
            or (replacement.canonical_memory_id or "").strip()
            or replacement.ledger_schema_version != LEDGER_SCHEMA_VERSION
            or replacement.kind != MemoryKind.fact
            or not replacement.intent_backed
            or replacement.write_reason != LedgerWriteReason.direct_user_statement
            or not replacement.user_asserted
            or replacement.processing_state != ProcessingState.processed
            or replacement.source_state != SourceState.active
            or (replacement.content or "").strip() != (selected.content or "").strip()
            or replacement.visibility != selected.visibility
            or replacement.slot != selected.slot
            or replacement.subject_scope != selected.subject_scope
            or replacement.subject_entity_id != selected.subject_entity_id
            or replacement.curation_weight != selected.curation_weight
            or replacement.predicate != selected.predicate
            or replacement.arguments != selected.arguments
            or replacement.sensitivity_labels != selected.sensitivity_labels
            or memory_item_to_memorydb(replacement).user_review is False
            or not has_reopen_evidence
        )

    def reopen_standalone_closed_ledger_fact(
        self,
        uid: str,
        memory_id: str,
        operation_id: str,
    ) -> MemoryDB:
        """Append one current tail from a standalone closed ledger fact."""

        self.ensure_canonical_mutation_ready(uid)
        normalized_operation_id = self._normalized_revert_operation_id(operation_id)
        selected = self._canonical_item_for_lineage(uid, memory_id)
        if selected is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        if not self._is_standalone_closed_ledger_fact(selected):
            raise HTTPException(status_code=409, detail="Only standalone closed knowledge ledger facts may be reopened")
        if (
            selected.source_state != SourceState.active
            or selected.processing_state != ProcessingState.processed
            or set(selected.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS)
            or memory_item_to_memorydb(selected).user_review is False
        ):
            raise HTTPException(status_code=409, detail="Knowledge ledger history cannot be reopened")
        if memory_item_to_memorydb(selected).is_locked:
            raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
        if not (selected.content or "").strip() or selected.visibility not in {"private", "public", "shared"}:
            raise HTTPException(status_code=409, detail="Knowledge ledger history cannot be reopened")

        provenance = LedgerProvenance(
            source_id=selected.memory_id,
            source_type="explicit_user_reopen",
            source_version=f"item_revision:{selected.item_revision}",
            action_id=f"memory_ui_reopen:{normalized_operation_id}",
            artifact_ref={
                "artifact_id": f"memory-history-reopen:{normalized_operation_id}",
                "preservation": "preserved",
            },
        )
        expected_evidence_id = evidence_id_for_ledger_provenance(uid, provenance)
        try:
            replacement_id = reopen_standalone_fact(
                uid,
                selected,
                operation_id=normalized_operation_id,
                provenance=provenance,
                db_client=self.db_client,
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="Knowledge ledger reopen conflicted") from exc

        replacement = self._canonical_item_for_lineage(uid, replacement_id)
        if replacement is None or not self._is_exact_standalone_ledger_reopen(
            selected,
            replacement,
            evidence_id=expected_evidence_id,
        ):
            raise HTTPException(status_code=503, detail="Knowledge ledger reopen readback unavailable")
        self._invalidate_prompt_cache(uid)
        return memory_item_to_memorydb(replacement)

    @staticmethod
    def _is_exact_ledger_fact_revert(
        selected: MemoryItem,
        prior_tail: MemoryItem,
        replacement: MemoryItem,
        *,
        evidence_id: str,
    ) -> bool:
        expected_source_version = f"item_revision:{selected.item_revision}"
        has_revert_evidence = any(
            evidence.evidence_id == evidence_id
            and evidence.source_type == "explicit_user_revert"
            and evidence.source_id == selected.memory_id
            and evidence.source_version == expected_source_version
            for evidence in replacement.evidence
        )
        return not (
            replacement.ledger_schema_version != LEDGER_SCHEMA_VERSION
            or replacement.kind != MemoryKind.fact
            or not replacement.intent_backed
            or replacement.write_reason != LedgerWriteReason.direct_user_statement
            or not replacement.user_asserted
            or (replacement.content or "").strip() != (selected.content or "").strip()
            or replacement.slot != selected.slot
            or replacement.subject_scope != selected.subject_scope
            or replacement.subject_entity_id != selected.subject_entity_id
            or replacement.curation_weight != selected.curation_weight
            or replacement.visibility != prior_tail.visibility
            or not has_revert_evidence
        )

    def revert_superseded_ledger_fact(
        self,
        uid: str,
        memory_id: str,
        operation_id: str,
    ) -> MemoryDB:
        """Restore a superseded fact by appending a fresh authoritative tail.

        Historical rows remain immutable. The selected row must lead through a
        single well-formed v1 fact chain to one current tail. A retry with the
        same operation id returns its still-current append; it never creates a
        second restore.
        """

        self.ensure_canonical_mutation_ready(uid)
        normalized_operation_id = self._normalized_revert_operation_id(operation_id)
        selected = self._canonical_item_for_lineage(uid, memory_id)
        if selected is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        if self._is_standalone_closed_ledger_fact(selected):
            return self.reopen_standalone_closed_ledger_fact(uid, memory_id, normalized_operation_id)
        identity = self._ledger_revert_identity(selected)
        self._validate_ledger_revert_item(selected, identity=identity)
        if (
            selected.status != MemoryItemStatus.superseded
            or selected.valid_to is None
            or not (selected.superseded_by or "").strip()
        ):
            raise HTTPException(status_code=409, detail="Only superseded knowledge ledger facts may be restored")
        if memory_item_to_memorydb(selected).is_locked:
            raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
        if not (selected.content or "").strip():
            raise HTTPException(status_code=409, detail="Knowledge ledger history cannot be restored")

        provenance = LedgerProvenance(
            source_id=selected.memory_id,
            source_type="explicit_user_revert",
            source_version=f"item_revision:{selected.item_revision}",
            action_id=f"memory_ui_revert:{normalized_operation_id}",
            artifact_ref={
                "artifact_id": f"memory-history-revert:{normalized_operation_id}",
                "preservation": "preserved",
            },
        )
        expected_evidence_id = evidence_id_for_ledger_provenance(uid, provenance)

        seen = {selected.memory_id}
        prior = selected
        for _ in range(MAX_LEDGER_REVERT_CHAIN_LENGTH):
            successor_id = (prior.superseded_by or "").strip()
            if not successor_id:
                break
            if (
                prior.status != MemoryItemStatus.superseded
                or prior.valid_to is None
                or (prior.canonical_memory_id or "").strip() != successor_id
                or successor_id in seen
            ):
                raise HTTPException(status_code=409, detail="Knowledge ledger history cannot be restored")
            successor = self._canonical_item_for_lineage(uid, successor_id)
            if successor is None:
                raise HTTPException(status_code=409, detail="Knowledge ledger history cannot be restored")
            self._validate_ledger_revert_item(successor, identity=identity)
            if any(evidence.evidence_id == expected_evidence_id for evidence in successor.evidence):
                if (
                    successor.status == MemoryItemStatus.active
                    and successor.valid_to is None
                    and not (successor.superseded_by or "").strip()
                    and not (successor.canonical_memory_id or "").strip()
                    and self._is_exact_ledger_fact_revert(
                        selected,
                        prior,
                        successor,
                        evidence_id=expected_evidence_id,
                    )
                ):
                    if memory_item_to_memorydb(successor).is_locked:
                        raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
                    self._invalidate_prompt_cache(uid)
                    return memory_item_to_memorydb(successor)
                raise HTTPException(status_code=409, detail="Memory revert operation is no longer current")
            seen.add(successor_id)
            prior = successor
        else:
            raise HTTPException(status_code=409, detail="Knowledge ledger history chain is too long")

        tail = prior
        if (
            tail.status != MemoryItemStatus.active
            or tail.valid_to is not None
            or tail.superseded_by
            or tail.canonical_memory_id
        ):
            raise HTTPException(status_code=409, detail="Knowledge ledger history has no current fact")
        if memory_item_to_memorydb(tail).is_locked:
            raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
        if tail.visibility not in {"private", "public", "shared"}:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable")
        if (tail.content or "").strip() == (selected.content or "").strip():
            raise HTTPException(status_code=409, detail="Knowledge ledger fact is already current")

        try:
            replacement_id = amend_fact(
                uid,
                tail.memory_id,
                (selected.content or "").strip(),
                provenance=provenance,
                write_reason=LedgerWriteReason.direct_user_statement,
                slot=selected.slot,
                subject_scope=selected.subject_scope or MemorySubjectScope.primary_user,
                subject_entity_id=selected.subject_entity_id,
                curation_weight=selected.curation_weight,
                visibility=cast(Literal["private", "public", "shared"], tail.visibility),
                db_client=self.db_client,
                required_source_item=selected,
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="Knowledge ledger restore conflicted") from exc

        self._invalidate_prompt_cache(uid)
        replacement = self._canonical_item_for_lineage(uid, replacement_id)
        closed_tail = self._canonical_item_for_lineage(uid, tail.memory_id)
        if (
            replacement is None
            or closed_tail is None
            or closed_tail.status != MemoryItemStatus.superseded
            or closed_tail.superseded_by != replacement_id
            or not self._is_exact_ledger_fact_revert(
                selected,
                tail,
                replacement,
                evidence_id=expected_evidence_id,
            )
            or replacement.status != MemoryItemStatus.active
            or replacement.valid_to is not None
            or replacement.superseded_by
        ):
            raise HTTPException(status_code=503, detail="Knowledge ledger restore readback unavailable")
        return memory_item_to_memorydb(replacement)

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

    def canonical_statuses(
        self,
        uid: str,
        memory_ids: List[str],
        *,
        budget: Optional[ListReadBudget] = None,
    ) -> Dict[str, MemoryItemStatus]:
        """Read canonical identity/suppression status in bounded batches.

        Firestore's ``get_all`` gives mixed reads a bounded read surface instead
        of one document RPC per historical row.  Small injected fakes used by
        unit tests (and older Firestore clients without ``get_all``) retain the
        single-ID fallback through ``_canonical_status``.
        """
        normalized_ids = list(dict.fromkeys(memory_id for memory_id in memory_ids if memory_id))
        if not normalized_ids:
            return {}
        client = self.db_client if self.db_client is not None else default_db_client
        get_all = getattr(client, "get_all", None)
        if callable(get_all):
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
                    snapshots = budgeted_get_all(client, refs, budget)
                except ListReadBudgetExhausted:
                    raise
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
        client = self.db_client if self.db_client is not None else default_db_client
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
        client = self.db_client if self.db_client is not None else default_db_client
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
        include_archive: bool,
        now: Optional[datetime],
        budget: Optional[ListReadBudget] = None,
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
                include_archive=include_archive,
                now=now,
                budget=budget,
            )
        except (HTTPException, ListReadBudgetExhausted):
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc

    @staticmethod
    def _memory_sort_key(memory: MemoryDB) -> tuple[float, str]:
        value = getattr(memory, "updated_at", None) or getattr(memory, "created_at", None)
        if value is None:
            timestamp = float("-inf")
        else:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            timestamp = value.timestamp()
        return (-timestamp, memory.id)

    @classmethod
    def _sort_memories(cls, memories: List[MemoryDB]) -> None:
        memories.sort(key=cls._memory_sort_key)

    @staticmethod
    def _next_historical_scan_limit(current: int, *, step: int) -> int:
        """Grow the adaptive historical scan at least geometrically.

        Every expansion round re-reads the whole newest-first prefix from the
        start, so a linear step makes one page cost O(rounds x prefix): a fully
        suppressed account at window=500 stepped 500, 1000, ... 5000 and read
        27,500 documents over 55 queries for a single page. Doubling keeps the
        light case identical (the first expansion is still ``current + step``)
        and bounds the heavy case to a logarithmic number of rescans.
        """
        grown = max(current + max(1, int(step)), current * 2)
        return min(HistoricalMemoryAdapter.MAX_COMPATIBILITY_WINDOW, grown)

    def read(
        self,
        uid: str,
        *,
        limit: int = 100,
        offset: int = 0,
        device_scope_request: Optional[DeviceScopeRequest] = None,
        include_pending_processing: bool = False,
        include_archive: bool = False,
        now: Optional[datetime] = None,
        budget: Optional[ListReadBudget] = None,
    ) -> List[MemoryDB]:
        bounded_limit = max(1, min(int(limit or 100), HistoricalMemoryAdapter.MAX_COMPATIBILITY_WINDOW))
        bounded_offset = max(0, int(offset or 0))
        window = bounded_offset + bounded_limit
        if window > HistoricalMemoryAdapter.MAX_COMPATIBILITY_WINDOW:
            raise HTTPException(status_code=413, detail="Memory pagination window exceeded")
        truncated = False
        try:
            canonical = self._canonical_read(
                uid,
                limit=window,
                offset=0,
                device_scope_request=device_scope_request,
                include_pending_processing=include_pending_processing,
                include_archive=include_archive,
                now=now,
                budget=budget,
            )
        except ListReadBudgetExhausted:
            # Out of budget before the canonical stream finished: serve an
            # explicitly empty prefix — the budget is already flagged truncated
            # so the route marks the response (#11831).
            return []
        canonical_ids = {memory.id for memory in canonical}
        # Adaptive historical scan: a suppressed newest-first prefix must not
        # hide later visible historical rows that belong in this merged page.
        historical_limit = window
        historical: List[HistoricalMemoryRecord] = []
        merged: List[MemoryDB] = list(canonical)
        identity_suppressed = 0
        state_suppressed = 0
        historical_kept = 0
        # Each expansion round rescans the same newest-first prefix with a
        # larger limit, so an uncached status lookup pays for every earlier
        # round again: a fully suppressed account at window=500 issued 275
        # batch gets over 55,000 documents for one page and took the request
        # past the 30s edge timeout. Canonical status is a stable read within
        # one request, so ask for each memory id exactly once.
        statuses: Dict[str, MemoryItemStatus] = {}
        status_ids_read: Set[str] = set()
        kept_stub_ids: Set[str] = set()
        try:
            while True:
                historical = self.history.read(
                    uid,
                    limit=historical_limit,
                    offset=0,
                    device_scope_request=device_scope_request,
                    hydrate=False,
                    budget=budget,
                )
                merged = list(canonical)
                identity_suppressed = 0
                state_suppressed = 0
                historical_kept = 0
                kept_stub_ids = set()
                unread_ids = [
                    record.memory.id
                    for record in historical
                    if record.memory.id and record.memory.id not in status_ids_read
                ]
                if unread_ids:
                    statuses.update(self.canonical_statuses(uid, unread_ids, budget=budget))
                    status_ids_read.update(unread_ids)
                for record in historical:
                    if record.memory.id in canonical_ids:
                        identity_suppressed += 1
                        continue
                    if statuses.get(record.memory.id) in {
                        MemoryItemStatus.active,
                        MemoryItemStatus.tombstoned,
                        MemoryItemStatus.hidden,
                        MemoryItemStatus.superseded,
                    }:
                        state_suppressed += 1
                        continue
                    merged.append(record.memory)
                    historical_kept += 1
                    if not record.hydrated:
                        kept_stub_ids.add(record.memory.id)
                self._sort_memories(merged)

                historical_exhausted = len(historical) < historical_limit
                at_max_window = historical_limit >= HistoricalMemoryAdapter.MAX_COMPATIBILITY_WINDOW
                if historical_exhausted or at_max_window:
                    break

                if len(merged) < window:
                    missing = window - len(merged)
                    historical_limit = self._next_historical_scan_limit(
                        historical_limit,
                        step=max(missing, bounded_limit),
                    )
                    continue

                # Page is full, but the oldest scanned historical row may still be
                # newer than the cutoff. Further visible rows could then belong in
                # the page, so keep expanding within the compatibility window.
                cutoff = merged[window - 1]
                oldest_scanned = historical[-1].memory
                if self._memory_sort_key(oldest_scanned) >= self._memory_sort_key(cutoff):
                    break
                historical_limit = self._next_historical_scan_limit(
                    historical_limit,
                    step=max(bounded_limit, window),
                )
        except ListReadBudgetExhausted:
            # The shared request budget ended this read mid-merge. ``merged``
            # holds the last fully assembled round; keep the merged view from
            # the last completed round so the page stays an honest prefix.
            truncated = True

        # Emit telemetry once for the final scan only — retries must not
        # double-count origin or suppression counters.
        MEMORY_UNIVERSAL_READ_ORIGIN_TOTAL.labels(origin="canonical").inc(len(canonical))
        MEMORY_UNIVERSAL_READ_ORIGIN_TOTAL.labels(origin="historical").inc(historical_kept)
        if identity_suppressed:
            MEMORY_HISTORICAL_SUPPRESSION_TOTAL.labels(reason="canonical_identity").inc(identity_suppressed)
        if state_suppressed:
            MEMORY_HISTORICAL_SUPPRESSION_TOTAL.labels(reason="canonical_state").inc(state_suppressed)
        page = merged[bounded_offset : bounded_offset + bounded_limit]
        if truncated:
            # An unhydrated stub ships empty content; a truncated page must
            # stay an honest prefix of fully-known rows instead.
            page = [memory for memory in page if memory.id not in kept_stub_ids]
        elif kept_stub_ids:
            page = self._hydrate_merged_historical_stubs(uid, page, kept_stub_ids, budget=budget)
        return page

    def _hydrate_merged_historical_stubs(
        self,
        uid: str,
        page: List[MemoryDB],
        stub_ids: Set[str],
        budget: Optional[ListReadBudget] = None,
    ) -> List[MemoryDB]:
        """Replace mixed-list historical stubs with decrypted documents.

        ``stub_ids`` must be ids that were actually appended from historical,
        not the suppressed prefix. Migrated memories share ids across stores;
        hydrating every historical stub id would replace (or drop) the
        canonical row that already won identity suppression.
        """
        page_stub_ids = [memory.id for memory in page if memory.id in stub_ids]
        if not page_stub_ids:
            return page
        hydrated_records = self.history.hydrate_records(
            uid,
            [
                HistoricalMemoryRecord(
                    memory=memory,
                    locator=MemoryLocator(uid=uid, origin="legacy", physical_id=memory.id),
                    hydrated=False,
                )
                for memory in page
                if memory.id in stub_ids
            ],
            budget=budget,
        )
        by_id = {record.memory.id: record.memory for record in hydrated_records}
        hydrated_page: List[MemoryDB] = []
        for memory in page:
            if memory.id not in stub_ids:
                hydrated_page.append(memory)
                continue
            replacement = by_id.get(memory.id)
            if replacement is not None:
                hydrated_page.append(replacement)
        return hydrated_page

    @classmethod
    def _datetime_to_us(cls, value: datetime) -> int:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        # Exact UTC microsecond key — avoid float timestamp truncation.
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        delta = value - epoch
        return delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds

    @classmethod
    def _us_to_datetime(cls, updated_at_us: int) -> datetime:
        seconds, micro = divmod(max(0, int(updated_at_us)), 1_000_000)
        return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=micro)

    @classmethod
    def memory_keyset(cls, memory: MemoryDB) -> StreamKeyset:
        value = getattr(memory, "updated_at", None) or getattr(memory, "created_at", None)
        if value is None:
            updated_at_us = 0
        else:
            updated_at_us = max(0, cls._datetime_to_us(value))
        return StreamKeyset(updated_at_us=updated_at_us, memory_id=memory.id)

    @classmethod
    def scan_cursor_to_stream_keyset(cls, scan_cursor: CanonicalScanCursor) -> StreamKeyset:
        updated_at, memory_id = scan_cursor
        return StreamKeyset(
            updated_at_us=max(0, cls._datetime_to_us(updated_at)),
            memory_id=memory_id,
        )

    @classmethod
    def stream_keyset_to_scan_cursor(cls, keyset: StreamKeyset) -> CanonicalScanCursor:
        return (
            cls._us_to_datetime(keyset.updated_at_us),
            keyset.memory_id,
        )

    @classmethod
    def keyset_sort_key(cls, keyset: StreamKeyset) -> Tuple[int, str]:
        # Newest-first public order mirrored as (-updated_at_us, memory_id).
        return (-keyset.updated_at_us, keyset.memory_id)

    @classmethod
    def memory_cursor_sort_key(cls, memory: MemoryDB) -> Tuple[int, str]:
        return cls.keyset_sort_key(cls.memory_keyset(memory))

    def historical_suppression_reason(
        self,
        memory_id: str,
        *,
        statuses: Dict[str, MemoryItemStatus],
    ) -> Optional[str]:
        """Classify historical suppression from batched canonical status alone.

        Active canonical authority is ``canonical_identity``; terminal/hidden
        ownership states are ``canonical_state``. A full visible-ID set is not
        required — ``canonical_statuses`` already distinguishes identity.
        """
        status = statuses.get(memory_id)
        if status == MemoryItemStatus.active:
            return "canonical_identity"
        if status in {
            MemoryItemStatus.tombstoned,
            MemoryItemStatus.hidden,
            MemoryItemStatus.superseded,
        }:
            return "canonical_state"
        return None

    def read_page(
        self,
        uid: str,
        *,
        limit: int = 100,
        cursor: Optional[str] = None,
        device_scope_request: Optional[DeviceScopeRequest] = None,
        include_pending_processing: bool = False,
        include_archive: bool = False,
        now: Optional[datetime] = None,
        request_budget: Optional[ListReadBudget] = None,
    ) -> UniversalMemoryListPage:
        """Page the mixed newest-first view with an opaque composite cursor.

        Legacy offset paging remains on ``read``. This path advances independent
        canonical and historical positions, walks through suppressed historical
        rows without emitting them, and refuses scope/archive authority changes
        midstream via the signed cursor claims. Canonical continuation uses a
        bounded Firestore keyset scan — never a full-set reload.
        """
        bounded_limit = max(1, min(int(limit or 100), HistoricalMemoryAdapter.MAX_PAGE_SIZE))
        device_scope = device_scope_request.device_scope if device_scope_request is not None else "all"
        client_device_id = device_scope_request.client_device_id if device_scope_request is not None else None
        if cursor:
            cursor_parts = cursor.split('.')
            if len(cursor_parts) != 3 or cursor_parts[0] != 'uml':
                raise HTTPException(status_code=400, detail="invalid_or_stale_cursor:malformed_cursor")
        try:
            secret = cursor_secret()
        except UniversalListCursorError as exc:
            raise MemoryBackingStoreUnavailable("Memory cursor unavailable", stream="cursor") from exc

        if cursor:
            try:
                claims = decode_universal_list_cursor(
                    cursor,
                    uid=uid,
                    include_archive=include_archive,
                    include_pending_processing=include_pending_processing,
                    device_scope=device_scope,
                    client_device_id=client_device_id,
                    secret=secret,
                )
            except UniversalListCursorError as exc:
                raise HTTPException(status_code=400, detail=f"invalid_or_stale_cursor:{exc.reason}") from exc
            state = claims.state
        else:
            state = UniversalListCursorState(
                uid=uid,
                include_archive=bool(include_archive),
                include_pending_processing=bool(include_pending_processing),
                device_scope=device_scope,
                client_device_id=client_device_id,
                canonical=None,
                canonical_scan=None,
                historical=None,
                historical_updated_scan=None,
                historical_created_scan=None,
                canonical_exhausted=False,
                historical_updated_exhausted=False,
                historical_created_exhausted=False,
            )
        # One budget per request, shared by both streams: the cost that has to
        # stay bounded is the total skipped-row walk behind a single page. When
        # the route shares a request ListReadBudget (#11831), the walk charges
        # that budget too, every chunk RPC runs under its per-RPC timeout, and
        # parent exhaustion truncates the page instead of 503-ing.
        budget = _ScanRowBudget(parent=request_budget)
        canonical = _CanonicalCursorStream(
            service=self,
            uid=uid,
            emitted=state.canonical,
            scan=state.canonical_scan,
            exhausted=state.canonical_exhausted,
            device_scope_request=device_scope_request,
            include_pending_processing=include_pending_processing,
            include_archive=include_archive,
            now=now,
            page_limit=bounded_limit,
            budget=budget,
            rpc_budget=request_budget,
        )
        historical = _HistoricalCursorStream(
            service=self,
            uid=uid,
            after=state.historical,
            updated_scan=state.historical_updated_scan,
            created_scan=state.historical_created_scan,
            updated_exhausted=state.historical_updated_exhausted,
            created_exhausted=state.historical_created_exhausted,
            device_scope_request=device_scope_request,
            page_limit=bounded_limit,
            budget=budget,
            rpc_budget=request_budget,
        )

        page: List[MemoryDB] = []
        canonical_kept = 0
        historical_kept = 0
        truncated = False

        try:
            while len(page) < bounded_limit:
                canonical_memory = canonical.peek()
                historical_memory = historical.peek()
                if canonical_memory is None and historical_memory is None:
                    break
                take_canonical = historical_memory is None or (
                    canonical_memory is not None
                    and self.memory_cursor_sort_key(canonical_memory) <= self.memory_cursor_sort_key(historical_memory)
                )
                if take_canonical:
                    assert canonical_memory is not None
                    page.append(canonical_memory)
                    canonical.consume()
                    canonical_kept += 1
                    continue
                assert historical_memory is not None
                page.append(historical_memory)
                historical.consume()
                historical_kept += 1
        except ListReadBudgetExhausted:
            # The request budget ended the scan mid-merge. Items already merged
            # are an honest newest-first prefix, but the cursor state does not
            # cover every consumed scan position — no continuation cursor.
            truncated = True

        MEMORY_UNIVERSAL_READ_ORIGIN_TOTAL.labels(origin="canonical").inc(canonical_kept)
        MEMORY_UNIVERSAL_READ_ORIGIN_TOTAL.labels(origin="historical").inc(historical_kept)
        if historical.identity_suppressed:
            MEMORY_HISTORICAL_SUPPRESSION_TOTAL.labels(reason="canonical_identity").inc(historical.identity_suppressed)
        if historical.state_suppressed:
            MEMORY_HISTORICAL_SUPPRESSION_TOTAL.labels(reason="canonical_state").inc(historical.state_suppressed)

        has_more = (not truncated) and (canonical.peek() is not None or historical.peek() is not None)
        next_cursor = None
        if has_more:
            next_state = UniversalListCursorState(
                uid=uid,
                include_archive=bool(include_archive),
                include_pending_processing=bool(include_pending_processing),
                device_scope=device_scope,
                client_device_id=client_device_id,
                canonical=canonical.emitted_keyset,
                canonical_scan=canonical.scan_keyset,
                historical=historical.consumed_keyset,
                historical_updated_scan=historical.updated_scan_keyset,
                historical_created_scan=historical.created_scan_keyset,
                canonical_exhausted=canonical.exhausted and canonical.peek() is None,
                historical_updated_exhausted=historical.updated_exhausted,
                historical_created_exhausted=historical.created_exhausted,
            )
            next_cursor = encode_universal_list_cursor(next_state, secret=secret)
        return UniversalMemoryListPage(memories=page, next_cursor=next_cursor, truncated=truncated)

    def read_pinned(
        self,
        uid: str,
        memory_system: MemorySystem,
        limit: int = 100,
        offset: int = 0,
        *,
        device_scope_request: Optional[DeviceScopeRequest] = None,
        include_pending_processing: bool = False,
        include_archive: bool = False,
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
            include_archive=include_archive,
            now=now,
        )

    def fetch(
        self,
        uid: str,
        memory_id: str,
        *,
        device_scope_request: Optional[DeviceScopeRequest] = None,
    ) -> MemoryDB:
        try:
            item = read_canonical_memory_item(uid, memory_id, db_client=self.db_client)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
        if item is not None:
            if (
                device_scope_request is not None
                and device_scope_request.device_scope in {"current", "explicit"}
                and not memory_matches_device(item, device_scope_request.client_device_id or "")
            ):
                raise HTTPException(status_code=404, detail="Memory not found")
            memory = memory_item_to_memorydb(item)
            if memory.is_locked:
                raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
            return memory
        status = self._canonical_status(uid, memory_id)
        if status is not None:
            raise HTTPException(status_code=404, detail="Memory not found")
        record = self.history.get(uid, memory_id)
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
        candidate_limit: Optional[int] = None,
        device_scope_request: Optional[DeviceScopeRequest] = None,
        canonical_item_filter: Optional[Callable[[MemoryItem], bool]] = None,
        result_filter: Optional[Callable[[MemoryDB], bool]] = None,
        ledger_kinds: Optional[Collection[str]] = None,
    ) -> List[MemorySearchMatch]:
        capped = max(1, min(int(limit or 5), 20))
        # Default 3× oversample so dedup/canonical suppression still yields `limit` hits.
        # Callers that already over-fetch (e.g. timeframe-scoped chat) pass candidate_limit.
        candidate_cap = max(
            capped,
            min(int(candidate_limit if candidate_limit is not None else capped * 3), 60),
        )
        try:
            canonical_kwargs: Dict[str, Any] = {
                "limit": candidate_cap,
                "device_scope_request": device_scope_request,
                "item_filter": canonical_item_filter,
            }
            if ledger_kinds is not None:
                canonical_kwargs["ledger_kinds"] = ledger_kinds
            canonical = self._canonical.search(
                uid,
                query,
                **canonical_kwargs,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory search unavailable") from exc
        if ledger_kinds is not None:
            # The ledger agent surface is explicitly canonical-only. Legacy
            # vector/storage search is a separate historical tool and must not
            # be merged here: aside from leaking stamped compatibility rows,
            # its provider outage would make current ledger search unavailable.
            historical: List[MemorySearchMatch] = []
        else:
            historical = self.history.search(
                uid,
                query,
                limit=candidate_cap,
                device_scope_request=device_scope_request,
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
        results = [match for match in by_id.values() if result_filter is None or result_filter(match.memory)]

        def timestamp(match: MemorySearchMatch) -> float:
            value = getattr(match.memory, "updated_at", None) or getattr(match.memory, "created_at", None)
            if value is None:
                return float("-inf")
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.timestamp()

        results.sort(key=lambda match: (-float(match.score), -timestamp(match), match.memory.id))
        return results[:capped]

    @staticmethod
    def _is_ledger_history_item(item: MemoryItem, row: MemoryDB) -> bool:
        """Compatibility wrapper for callers that patch the legacy seam."""

        return is_ledger_history_item(item, row)

    def read_ledger_history_page(
        self,
        uid: str,
        *,
        limit: int = 100,
        offset: int = 0,
        budget: Optional[ListReadBudget] = None,
    ) -> LedgerHistoryPage:
        """Read a bounded canonical history window with truncation truth.

        This is deliberately separate from ``read``: default product reads
        must continue to hide rejected and closed facts.  The history seam is
        for a user's review/history surfaces and admits only canonical ledger
        rows that are explicitly rejected, no longer current, or preserved
        with ``legacy_migration`` provenance. It never exposes arbitrary
        passive rows, tombstoned/hidden rows, or the legacy
        ``users/{uid}/memories`` collection.
        """

        bounded_limit = max(1, min(int(limit or 100), 500))
        bounded_offset = max(0, int(offset or 0))
        window = bounded_offset + bounded_limit
        if window > HistoricalMemoryAdapter.MAX_COMPATIBILITY_WINDOW:
            raise HTTPException(status_code=413, detail="Ledger history pagination window exceeded")
        projected_items: List[Tuple[MemoryItem, MemoryDB]] = []
        scanned_count = 0
        truncated = False
        scan_limit = MAX_LEDGER_HISTORY_PROVIDER_WINDOW + 1
        try:
            for item in iter_authoritative_product_memory_items_newest_first(
                uid,
                db_client=self.db_client,
                limit=scan_limit,
                budget=budget,
            ):
                scanned_count += 1
                row = memory_item_to_memorydb(item)
                if self._is_ledger_history_item(item, row):
                    projected_items.append((item, row))
        except ListReadBudgetExhausted:
            truncated = True
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc

        # The extra provider row is a sentinel. A full window is conservatively
        # partial even when it happens to contain exactly 501 rows.
        truncated = truncated or scanned_count >= scan_limit
        projected_items.sort(key=lambda pair: (-pair[0].updated_at.timestamp(), pair[0].memory_id))
        return LedgerHistoryPage(
            memories=tuple(row for _, row in projected_items[bounded_offset : bounded_offset + bounded_limit]),
            truncated=truncated,
            scanned_count=scanned_count,
        )

    def read_ledger_history(
        self,
        uid: str,
        *,
        limit: int = 100,
        offset: int = 0,
        budget: Optional[ListReadBudget] = None,
    ) -> List[MemoryDB]:
        """Compatibility list wrapper over :meth:`read_ledger_history_page`."""

        return list(self.read_ledger_history_page(uid, limit=limit, offset=offset, budget=budget).memories)

    def search_ledger_history_page(
        self,
        uid: str,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
        include_rejected: bool = False,
        budget: Optional[ListReadBudget] = None,
    ) -> LedgerHistorySearchPage:
        """Search one bounded canonical history provider window.

        This is intentionally a deterministic local ranking over the
        authoritative canonical window. It does not consult legacy vectors or
        claim exhaustive historical retrieval; callers must surface
        ``truncated`` when the provider window or request budget is incomplete.
        Offset pagination is deterministic for one live provider snapshot, but
        concurrent history changes may shift later offsets and must be disclosed
        by interactive callers.
        """

        normalized_query = " ".join((query or "").split()).casefold()
        terms = tuple(dict.fromkeys(_LEDGER_QUERY_TOKEN_RE.findall(normalized_query)))
        if not terms:
            raise ValueError("historical ledger query must contain a searchable token")
        bounded_limit = max(1, min(int(limit or 20), 20))
        bounded_offset = max(0, int(offset or 0))
        if bounded_offset + bounded_limit > MAX_LEDGER_HISTORY_PROVIDER_WINDOW:
            raise HTTPException(status_code=413, detail="Ledger history search pagination window exceeded")
        page = self.read_ledger_history_page(
            uid,
            limit=MAX_LEDGER_HISTORY_PROVIDER_WINDOW,
            offset=0,
            budget=budget,
        )
        matches: List[MemorySearchMatch] = []
        for memory in page.memories:
            if memory.kind != MemoryKind.fact:
                continue
            if memory.user_review is False and not include_rejected:
                continue
            try:
                arguments_text = json.dumps(memory.arguments, sort_keys=True, default=str)[:4000]
            except (TypeError, ValueError):
                arguments_text = ""
            searchable = " ".join(
                value
                for value in (memory.content, memory.body, memory.slot, memory.subject_entity_id, arguments_text)
                if isinstance(value, str) and value.strip()
            ).casefold()
            tokens = set(_LEDGER_QUERY_TOKEN_RE.findall(searchable))
            matched = sum(term in tokens for term in terms)
            if not matched:
                continue
            matches.append(MemorySearchMatch(memory=memory, score=matched / len(terms)))

        def sort_key(match: MemorySearchMatch) -> Tuple[float, float, str]:
            value = match.memory.updated_at or match.memory.created_at
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return (-match.score, -value.timestamp(), match.memory.id)

        matches.sort(key=sort_key)
        page_end = bounded_offset + bounded_limit
        selected = matches[bounded_offset:page_end]
        next_offset = page_end if page_end < len(matches) else None
        return LedgerHistorySearchPage(
            matches=tuple(selected),
            truncated=page.truncated or next_offset is not None,
            scanned_count=page.scanned_count,
            next_offset=next_offset,
        )

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
                    **public_belief_overlay_json(memory, now=now or datetime.now(timezone.utc)),
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

    def iter_export_memories(
        self,
        uid: str,
        *,
        include_archive: bool = True,
        page_size: int = 500,
    ) -> Iterator[MemoryDB]:
        """Stream each live logical memory once for compatibility consumers.

        Yields without building one giant merged list. Canonical active rows are
        emitted first; historical pages follow with per-page suppression checks.
        No export read performs materialization, LLM work, embedding, or graph
        admission.
        """
        yield from self._iter_export_memories(
            uid,
            include_archive=include_archive,
            page_size=page_size,
            include_ledger_history=False,
        )

    def iter_portability_export_memories(
        self,
        uid: str,
        *,
        include_archive: bool = True,
        page_size: int = 500,
    ) -> Iterator[MemoryDB]:
        """Stream owner-portable memories, including representable ledger history.

        Compatibility readers and migration planning intentionally consume only
        live rows through :meth:`iter_export_memories`. A user's data export has
        a stronger preservation contract: superseded ledger rows and closed
        ``legacy_migration`` history and explicitly rejected/hidden audit rows
        remain portable without becoming current prompt authority. Privacy
        tombstones and source-purged content stay excluded, while owner-visible
        locked or sensitive history is preserved.
        """
        yield from self._iter_export_memories(
            uid,
            include_archive=include_archive,
            page_size=page_size,
            include_ledger_history=True,
        )

    @staticmethod
    def _is_portability_ledger_history(item: MemoryItem, row: MemoryDB) -> bool:
        if item.ledger_schema_version != LEDGER_SCHEMA_VERSION:
            return False
        if item.status not in {MemoryItemStatus.superseded, MemoryItemStatus.hidden}:
            return False
        if item.source_state in {SourceState.tombstoned, SourceState.purged}:
            return False
        # MemoryDB has no generic physical-status field. Admit only closure
        # states represented honestly on the released wire shape.
        return item.status == MemoryItemStatus.hidden or row.invalid_at is not None or row.superseded_by is not None

    def _iter_export_memories(
        self,
        uid: str,
        *,
        include_archive: bool,
        page_size: int,
        include_ledger_history: bool,
    ) -> Iterator[MemoryDB]:
        archive_explicit = include_archive
        page_size = max(1, min(int(page_size or 500), 500))
        client = self.db_client if self.db_client is not None else default_db_client
        try:
            canonical_items = iter_authoritative_product_memory_items(uid=uid, db_client=client)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc

        canonical_ids: set[str] = set()
        while True:
            try:
                item = next(canonical_items)
            except StopIteration:
                break
            except Exception as exc:
                raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
            canonical_ids.add(item.memory_id)
            if item.source_state in {SourceState.tombstoned, SourceState.purged}:
                continue
            if item.tier == MemoryTier.archive and not archive_explicit:
                continue
            row = memory_item_to_memorydb(item)
            if item.status == MemoryItemStatus.active:
                if not include_ledger_history and ledger_row_is_rejected(item):
                    continue
                yield row
                continue
            if include_ledger_history and self._is_portability_ledger_history(item, row):
                yield row

        pending_historical: List[HistoricalMemoryRecord] = []
        for record in self.history.iter_all_live(uid, page_size=page_size):
            if record.memory.id in canonical_ids:
                continue
            pending_historical.append(record)
            if len(pending_historical) < page_size:
                continue
            yield from self._export_unsuppressed_historical(uid, pending_historical)
            pending_historical = []
        if pending_historical:
            yield from self._export_unsuppressed_historical(uid, pending_historical)

    def _export_unsuppressed_historical(
        self,
        uid: str,
        records: List[HistoricalMemoryRecord],
    ) -> Iterator[MemoryDB]:
        historical_statuses = self.canonical_statuses(uid, [record.memory.id for record in records])
        for record in records:
            # Suppression overrides are canonical authority even when the
            # canonical item itself has already been physically cleaned up.
            if historical_statuses.get(record.memory.id) is not None:
                MEMORY_HISTORICAL_SUPPRESSION_TOTAL.labels(reason="canonical_state").inc()
                continue
            yield record.memory

    def export_memories(
        self,
        uid: str,
        *,
        include_archive: bool = True,
        page_size: int = 500,
    ) -> List[MemoryDB]:
        """Return each live logical memory once for account export.

        Prefer ``iter_export_memories`` for large accounts so the response path
        can stream. This list helper remains for callers that need a snapshot.
        """
        merged = list(self.iter_export_memories(uid, include_archive=include_archive, page_size=page_size))
        self._sort_memories(merged)
        return merged

    def list_historical_memory_ids(self, uid: str, *, limit: Optional[int] = None, offset: int = 0) -> List[str]:
        """IDs-only compatibility seam for complete privacy operations."""
        return self.history.ids(uid, limit=limit, offset=offset, db_client=self.db_client)

    def _canonical_write(self, uid: str, data: Dict[str, Any], *, source_surface: str) -> MemoryDB:
        self.ensure_canonical_mutation_ready(uid)
        payload = required_processing_payload(data, source_surface=source_surface)
        committed_id = self._canonical.write(uid, payload)
        item = read_canonical_memory_item(uid, committed_id or str(data.get("id") or ""), db_client=self.db_client)
        if item is None:
            raise HTTPException(status_code=503, detail="Canonical memory write readback unavailable")
        return memory_item_to_memorydb(item)

    def _direct_user_ledger_admitted(self, uid: str, authority: object | None) -> bool:
        """Require route authority, fresh JIT ingress, and stable ledger mode."""
        if not is_direct_user_write_authority(authority):
            return False
        decision = resolve_jit_rollout_sync(
            uid,
            stage=JITDecisionStage.INGRESS,
            force_refresh=True,
        )
        if not decision.permits_work:
            return False
        control = ensure_canonical_apply_control_state(uid, db_client=self.db_client)
        return control.writer_mode == WriterMode.ledger

    def _write_direct_user_fact(
        self,
        uid: str,
        memory_db: MemoryDB,
        *,
        consumer: str,
        authority: object,
    ) -> MemoryDB:
        """Persist one explicitly typed memory through the ledger fact seam."""
        provenance = self._direct_user_fact_provenance(memory_db, consumer=consumer)
        memory_id = save_fact(
            uid,
            memory_db.content,
            provenance=provenance,
            write_reason=LedgerWriteReason.direct_user_statement,
            subject_scope=memory_db.subject_scope or MemorySubjectScope.primary_user,
            subject_entity_id=memory_db.subject_entity_id,
            predicate=memory_db.predicate,
            arguments=memory_db.arguments,
            valid_from=memory_db.valid_at,
            visibility=cast(Literal["private", "public", "shared"], memory_db.visibility or "private"),
            db_client=self.db_client,
            _direct_user_authority=authority,
        )
        item = read_canonical_memory_item(uid, memory_id, db_client=self.db_client)
        if item is None:
            raise HTTPException(status_code=503, detail="Canonical memory write readback unavailable")
        return memory_item_to_memorydb(item)

    @staticmethod
    def _direct_user_fact_provenance(memory_db: MemoryDB, *, consumer: str) -> LedgerProvenance:
        return LedgerProvenance(
            source_id=f"{consumer}:{memory_db.id}",
            source_type="explicit_user_statement",
            source_version="v3_memory_create.v1",
            action_id=f"{consumer}:memory:{memory_db.id}",
            artifact_ref={"memory_id": memory_db.id},
        )

    def _validate_direct_user_fact(self, memory_db: MemoryDB, *, consumer: str) -> None:
        """Run the same semantic model validation as save_fact without I/O."""
        LedgerWrite(
            kind=MemoryKind.fact,
            content=memory_db.content,
            provenance=self._direct_user_fact_provenance(memory_db, consumer=consumer),
            write_reason=LedgerWriteReason.direct_user_statement,
            subject_scope=memory_db.subject_scope or MemorySubjectScope.primary_user,
            subject_entity_id=memory_db.subject_entity_id,
            predicate=memory_db.predicate,
            arguments=memory_db.arguments,
            valid_from=memory_db.valid_at,
            visibility=cast(Literal["private", "public", "shared"], memory_db.visibility or "private"),
        )

    def write(self, uid: str, data: Dict[str, Any]) -> str:
        self.ensure_canonical_mutation_ready(uid)
        result = self._canonical.write(uid, data)
        self._invalidate_prompt_cache(uid)
        return result

    def write_batch(self, uid: str, items: List[Dict[str, Any]]) -> List[str]:
        self.ensure_canonical_mutation_ready(uid)
        result = self._canonical.write_batch(uid, items)
        self._invalidate_prompt_cache(uid)
        return result

    def _materialize_legacy(self, uid: str, memory_id: str) -> MemoryDB:
        status = self._canonical_status(uid, memory_id)
        if status is not None:
            raise HTTPException(status_code=404, detail="Memory not found")
        record = self.history.get(uid, memory_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        # Closed historical rows are read-only history, never migration input.
        # Without this guard, the compatibility mutation path could turn an
        # invalidated or superseded legacy row back into an active canonical
        # item (and the superseded_by marker is not part of the legacy write
        # payload).  Current canonical rows are still reviewable, including
        # an explicit re-accept of a previously rejected active row.
        if record.memory.invalid_at is not None or (record.memory.superseded_by or "").strip():
            raise HTTPException(status_code=404, detail="Memory not found")
        if record.memory.is_locked:
            raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
        payload = memory_api_payload(record.memory, MemoryApiExposure.LEGACY)
        payload.update(
            {
                "id": memory_id,
                "uid": uid,
                "promotion": {
                    "historical_materialization": True,
                    "lifecycle": "grandfathered_long_term",
                },
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
            canonical_item = read_canonical_memory_item(uid, memory_id, db_client=self.db_client)
            if canonical_item is not None:
                if memory_item_to_memorydb(canonical_item).is_locked:
                    raise HTTPException(
                        status_code=402,
                        detail="A paid plan is required to access this memory.",
                    )
                MEMORY_HISTORICAL_MATERIALIZATION_TOTAL.labels(outcome="not_needed").inc()
                return False
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
        self._materialize_legacy(uid, memory_id)
        MEMORY_HISTORICAL_MATERIALIZATION_TOTAL.labels(outcome="committed").inc()
        return True

    def materialize_legacy_for_ledger_migration(self, uid: str, memory_id: str) -> MemoryItem:
        """Adopt one live historical row through the existing canonical seam.

        The physical legacy row is preserved. A canonical active ownership
        record suppresses it from default compatibility reads while explicit
        historical export/query remains available; the migration sweep then
        adapts that canonical item in place to the ledger schema.
        """
        self.ensure_canonical_mutation_ready(uid)
        self._ensure_canonical_target(uid, memory_id)
        item = read_canonical_memory_item(uid, memory_id, db_client=self.db_client)
        if item is None:
            raise RuntimeError("legacy materialization did not produce canonical authority")
        return item

    def update_content(self, uid: str, memory_id: str, content: str) -> MemoryDB:
        self.ensure_canonical_mutation_ready(uid)
        canonical_item = self._canonical_item_for_lineage(uid, memory_id)
        if canonical_item is not None and canonical_item.ledger_schema_version == LEDGER_SCHEMA_VERSION:
            return self._correct_ledger_fact(uid, canonical_item, content)
        materialized = self._ensure_canonical_target(uid, memory_id)
        try:
            updated = self._canonical.update_content(uid, memory_id, content)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Memory not found") from exc
        if materialized:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self.db_client)
        self._invalidate_prompt_cache(uid)
        return updated

    def refine(self, uid: str, memory_id: str, arg_changes: Dict[str, Any]) -> MemoryDB:
        self.ensure_canonical_mutation_ready(uid)
        materialized = self._ensure_canonical_target(uid, memory_id)
        try:
            updated = refine_canonical_memory(uid, memory_id, arg_changes, db_client=self.db_client)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Memory not found") from exc
        if materialized:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self.db_client)
        self._invalidate_prompt_cache(uid)
        return memory_item_to_memorydb(updated)

    def update_visibility(self, uid: str, memory_id: str, visibility: str) -> None:
        self.ensure_canonical_mutation_ready(uid)
        materialized = self._ensure_canonical_target(uid, memory_id)
        self._canonical.update_visibility(uid, memory_id, visibility)
        if materialized:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self.db_client)
        self._invalidate_prompt_cache(uid)

    def review(self, uid: str, memory_id: str, value: bool) -> None:
        self.ensure_canonical_mutation_ready(uid)
        materialized = self._ensure_canonical_target(uid, memory_id)
        self._canonical.review(uid, memory_id, value)
        if materialized:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self.db_client)
        self._invalidate_prompt_cache(uid)

    def update_product_fields(
        self,
        uid: str,
        memory_id: str,
        *,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        is_baseline: Optional[bool] = None,
        is_read: Optional[bool] = None,
        is_dismissed: Optional[bool] = None,
    ) -> MemoryDB:
        self.ensure_canonical_mutation_ready(uid)
        materialized = self._ensure_canonical_target(uid, memory_id)
        updated = self._canonical.update_product_fields(
            uid,
            memory_id,
            tags=tags,
            category=category,
            is_baseline=is_baseline,
            is_read=is_read,
            is_dismissed=is_dismissed,
        )
        if materialized:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self.db_client)
        self._invalidate_prompt_cache(uid)
        return updated

    def update_read_status(
        self,
        uid: str,
        memory_id: str,
        *,
        is_read: Optional[bool] = None,
        is_dismissed: Optional[bool] = None,
    ) -> MemoryDB:
        """Persist durable UI read/dismiss state through canonical product metadata."""

        if is_read is None and is_dismissed is None:
            raise HTTPException(status_code=422, detail="Missing memory read mutation value")
        return self.update_product_fields(uid, memory_id, is_read=is_read, is_dismissed=is_dismissed)

    def update_baseline(self, uid: str, memory_id: str, value: bool) -> MemoryDB:
        """Preserve the released baseline mutation through canonical metadata."""

        return self.update_product_fields(uid, memory_id, is_baseline=value)

    @_legal_hold_gated_deletion
    def delete(self, uid: str, memory_id: str) -> None:
        try:
            canonical_item = read_canonical_memory_item(uid, memory_id, db_client=self.db_client)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
        if canonical_item is not None:
            if getattr(canonical_item, "status", None) == MemoryItemStatus.tombstoned:
                try:
                    lineage_ids = canonical_memory_lineage_ids(
                        uid,
                        [memory_id],
                        db_client=self.db_client,
                    )
                except Exception as exc:
                    raise HTTPException(status_code=503, detail="Canonical memory privacy cleanup unavailable") from exc
                self._write_historical_override(uid, memory_id, MemoryItemStatus.tombstoned)
                _purge_required_canonical_projections(
                    uid,
                    lineage_ids,
                    db_client=self.db_client,
                    reason="canonical_memory_delete_retry",
                )
                try:
                    purge_stale_review_conflicts_for_memories(
                        uid,
                        lineage_ids,
                        reason="canonical_memory_delete_retry",
                        db_client=self.db_client,
                        include_legacy_commits=True,
                    )
                except Exception as exc:
                    raise HTTPException(
                        status_code=503,
                        detail="Canonical memory review privacy cleanup unavailable",
                    ) from exc
                for lineage_memory_id in lineage_ids:
                    HistoricalMemoryAdapter.cleanup(
                        uid,
                        lineage_memory_id,
                        db_client=self.db_client,
                        required=True,
                    )
                _delete_historical_privacy_overrides(uid, lineage_ids, db_client=self.db_client)
                self._invalidate_prompt_cache(uid)
                return
            if memory_item_to_memorydb(canonical_item).is_locked:
                raise HTTPException(
                    status_code=402,
                    detail="A paid plan is required to access this memory.",
                )
            # Write the historical suppression first. Tombstones are privacy
            # operations, not intake, so this path stays available while the
            # global write fence is paused and a cleanup failure cannot expose
            # the old physical row again.
            self._write_historical_override(uid, memory_id, MemoryItemStatus.tombstoned)
            lineage_ids = _returned_lineage_ids(self._canonical.delete(uid, memory_id), [memory_id])
        else:
            status = self._canonical_status(uid, memory_id)
            if status == MemoryItemStatus.tombstoned:
                lineage_ids = [memory_id]
            elif status is not None:
                raise HTTPException(status_code=404, detail="Memory not found")
            else:
                record = self.history.get(uid, memory_id)
                if record is None:
                    raise HTTPException(status_code=404, detail="Memory not found")
                if record.memory.is_locked:
                    raise HTTPException(
                        status_code=402,
                        detail="A paid plan is required to access this memory.",
                    )
                # A historical-only deletion does not need to manufacture an
                # active canonical item.  The durable canonical suppression record
                # is the authoritative privacy tombstone.
                lineage_ids = [memory_id]
        self._write_historical_override(uid, memory_id, MemoryItemStatus.tombstoned)
        try:
            purge_stale_review_conflicts_for_memories(
                uid,
                lineage_ids,
                reason="explicit_memory_delete",
                db_client=self.db_client,
                include_legacy_commits=True,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Memory review privacy cleanup unavailable",
            ) from exc
        for lineage_memory_id in lineage_ids:
            HistoricalMemoryAdapter.cleanup(
                uid,
                lineage_memory_id,
                db_client=self.db_client,
                required=True,
            )
        _delete_historical_privacy_overrides(uid, lineage_ids, db_client=self.db_client)
        self._invalidate_prompt_cache(uid)

    @_legal_hold_gated_deletion
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
                canonical_item = read_canonical_memory_item(uid, memory_id, db_client=self.db_client)
            except Exception as exc:
                raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
            if canonical_item is not None:
                if getattr(canonical_item, "status", None) == MemoryItemStatus.tombstoned:
                    try:
                        historical_ids.extend(canonical_memory_lineage_ids(uid, [memory_id], db_client=self.db_client))
                    except Exception as exc:
                        raise HTTPException(
                            status_code=503,
                            detail="Canonical memory privacy cleanup unavailable",
                        ) from exc
                    continue
                if memory_item_to_memorydb(canonical_item).is_locked:
                    raise HTTPException(
                        status_code=402,
                        detail="A paid plan is required to access this memory.",
                    )
                canonical_ids.append(memory_id)
                continue

            status = self._canonical_status(uid, memory_id)
            if status == MemoryItemStatus.tombstoned:
                # A previous attempt may have committed the canonical tombstone
                # and completed its opaque finalization. The keyed receipt
                # proves this requested identity remains suppressed; raw alias
                # IDs have already been scrubbed and must not be reconstructed.
                historical_ids.append(memory_id)
                continue
            if status is not None:
                raise HTTPException(status_code=404, detail="Memory not found")
            record = self.history.get(uid, memory_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Memory not found")
            if record.memory.is_locked:
                raise HTTPException(
                    status_code=402,
                    detail="A paid plan is required to access this memory.",
                )
            historical_ids.append(memory_id)

        # Suppression is committed before the canonical tombstone and cleanup so
        # a partial attempt cannot resurrect a historical row. Canonical rows
        # also receive an override; this keeps the identity ledger explicit for
        # export and account purge, and is safe to replay.
        self._write_historical_overrides(uid, requested, MemoryItemStatus.tombstoned)

        try:
            canonical_lineage_ids = (
                _returned_lineage_ids(self._canonical.delete_batch(uid, canonical_ids), canonical_ids)
                if canonical_ids
                else []
            )
        except HTTPException:
            raise
        except CanonicalBatchMutationLimitError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except CanonicalMemoryNotFoundError as exc:
            # A concurrent canonical change can invalidate the prevalidation;
            # expose the same released not-found contract without per-ID fallback.
            raise HTTPException(status_code=404, detail="Memory not found") from exc

        cleanup_ids = list(dict.fromkeys(canonical_lineage_ids + historical_ids))
        _purge_required_canonical_projections(
            uid,
            cleanup_ids,
            db_client=self.db_client,
            reason="canonical_memory_delete_batch_retry",
        )
        try:
            purge_stale_review_conflicts_for_memories(
                uid,
                cleanup_ids,
                reason="canonical_memory_delete_batch_retry",
                db_client=self.db_client,
                include_legacy_commits=True,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Canonical memory review privacy cleanup unavailable",
            ) from exc

        for memory_id in cleanup_ids:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self.db_client, required=True)

        _delete_historical_privacy_overrides(uid, cleanup_ids, db_client=self.db_client)

        self._invalidate_prompt_cache(uid)

    @_legal_hold_gated_deletion
    def delete_all(self, uid: str) -> None:
        historical_ids = self.history.ids(uid, db_client=self.db_client)
        try:
            canonical_ids = [
                item.memory_id for item in iter_authoritative_product_memory_items(uid, db_client=self.db_client)
            ]
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
        # Commit the historical privacy fence before canonical cleanup. A retry
        # can safely repeat this idempotent batch if canonical deletion fails.
        self._write_historical_overrides(uid, historical_ids, MemoryItemStatus.tombstoned)
        self._canonical.delete_all(uid)
        try:
            purge_stale_review_conflicts_for_memories(
                uid,
                list(dict.fromkeys(canonical_ids + historical_ids)),
                reason="canonical_memory_delete_all_retry",
                db_client=self.db_client,
                include_legacy_commits=True,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Canonical memory review privacy cleanup unavailable",
            ) from exc
        self.history.cleanup_all(uid, db_client=self.db_client, required=True)
        _delete_historical_privacy_overrides(
            uid,
            list(dict.fromkeys(canonical_ids + historical_ids)),
            db_client=self.db_client,
        )
        self._invalidate_prompt_cache(uid)

    @_legal_hold_gated_deletion
    def delete_default(self, uid: str) -> None:
        historical_ids = self.history.ids(uid, db_client=self.db_client)
        try:
            canonical_ids = [
                item.memory_id
                for item in iter_authoritative_product_memory_items(uid, db_client=self.db_client)
                # not_archive: this is explicit default-tier deletion scope,
                # not a released default-read visibility predicate.
                if item.tier != MemoryTier.archive
            ]
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Canonical memory unavailable") from exc
        self._write_historical_overrides(uid, historical_ids, MemoryItemStatus.tombstoned)
        self._canonical.delete_default(uid)
        try:
            purge_stale_review_conflicts_for_memories(
                uid,
                list(dict.fromkeys(canonical_ids + historical_ids)),
                reason="canonical_memory_delete_default_retry",
                db_client=self.db_client,
                include_legacy_commits=True,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Canonical memory review privacy cleanup unavailable",
            ) from exc
        self.history.cleanup_all(uid, db_client=self.db_client, required=True)
        _delete_historical_privacy_overrides(
            uid,
            list(dict.fromkeys(canonical_ids + historical_ids)),
            db_client=self.db_client,
        )
        self._invalidate_prompt_cache(uid)

    @_legal_hold_gated_deletion
    def retract_conversation_memories(
        self,
        uid: str,
        conversation_id: str,
        *,
        on_authoritative_commit: Optional[Callable[[], None]] = None,
    ) -> Optional[Dict[str, Any]]:
        result = retract_conversation_sourced_memories(uid, conversation_id, db_client=self.db_client)
        # Canonical retraction is irreversible even if the historical scan or
        # suppression write below fails. Advance the merge compensation fence
        # immediately so failure handling preserves the already-built merged
        # target instead of deleting both source and target memories.
        if on_authoritative_commit is not None:
            on_authoritative_commit()
        historical_ids = [
            record.memory.id
            for record in self.history.all_live(uid)
            if record.memory.conversation_id == conversation_id
            or any(
                evidence.source_type == "conversation" and evidence.source_id == conversation_id
                for evidence in record.memory.evidence
            )
        ]
        retracted_ids = list(dict.fromkeys(list(result.get("retracted_memory_ids") or []) if result else []))
        all_ids = list(dict.fromkeys(retracted_ids + historical_ids))
        if all_ids:
            # Historical suppression must commit before the authoritative fence
            # advances. A suppression failure leaves the callback unfired so
            # merge source-deletion does not proceed on a partial retract.
            self._write_historical_overrides(uid, all_ids, MemoryItemStatus.tombstoned)
            _purge_required_canonical_projections(
                uid,
                all_ids,
                db_client=self.db_client,
                reason="conversation_memory_retraction",
                preserve_source_replacement_receipts=True,
            )
            try:
                purge_stale_review_conflicts_for_memories(
                    uid,
                    all_ids,
                    reason="conversation_memory_retraction",
                    db_client=self.db_client,
                    include_legacy_commits=True,
                    preserve_source_replacement_receipts=True,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail="Conversation memory review privacy cleanup unavailable",
                ) from exc
        for memory_id in historical_ids:
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self.db_client, required=True)
        _delete_historical_privacy_overrides(uid, all_ids, db_client=self.db_client)
        if retracted_ids:
            try:
                purge_source_replacement_receipts_for_memories(
                    uid,
                    retracted_ids,
                    firestore_client=self.db_client,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail="Conversation memory replacement receipt cleanup unavailable",
                ) from exc
        return result

    def replace_conversation_memories(
        self,
        uid: str,
        conversation_id: str,
        items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        self.ensure_canonical_mutation_ready(uid)
        # This wrapper is the conversation-extraction entry (finalize and
        # reprocess). An empty extraction here is model variance, not deletion
        # intent, so it keeps any existing rows instead of demanding the
        # destructive gate the extraction path never holds.
        result = replace_conversation_sourced_memories(
            uid,
            conversation_id,
            items,
            db_client=self.db_client,
            empty_set_intent="extraction",
        )
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
        direct_user_authority: object | None = None,
    ) -> MemoryDB:
        del memory_system, operation, upsert_vector, require_canonical_promotion
        if memory_db.manually_added and self._direct_user_ledger_admitted(uid, direct_user_authority):
            assert direct_user_authority is not None
            result = self._write_direct_user_fact(
                uid,
                memory_db,
                consumer=consumer,
                authority=direct_user_authority,
            )
        else:
            result = self._canonical_write(uid, memory_db.model_dump(mode="python"), source_surface=consumer)
        self._invalidate_prompt_cache(uid)
        return result

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
        direct_user_authority: object | None = None,
    ) -> List[MemoryDB]:
        del memory_system, operation, upsert_vectors, require_canonical_promotion
        self.ensure_canonical_mutation_ready(uid)
        if direct_user_authority is not None and any(memory.manually_added for memory in memory_dbs):
            if self._direct_user_ledger_admitted(uid, direct_user_authority):
                assert direct_user_authority is not None
                if not all(memory.manually_added for memory in memory_dbs):
                    raise HTTPException(
                        status_code=503,
                        detail="Mixed explicit-user and external memory batch is not admitted in ledger mode",
                    )
                for memory in memory_dbs:
                    self._validate_direct_user_fact(memory, consumer=consumer)
                results = [
                    self._write_direct_user_fact(
                        uid,
                        memory,
                        consumer=consumer,
                        authority=direct_user_authority,
                    )
                    for memory in memory_dbs
                ]
                self._invalidate_prompt_cache(uid)
                return results
        payloads = [
            required_processing_payload(memory.model_dump(mode="python"), source_surface=consumer)
            for memory in memory_dbs
        ]
        ids = self._canonical.write_batch(uid, payloads)
        results: List[MemoryDB] = []
        for memory_id in ids:
            item = read_canonical_memory_item(uid, memory_id, db_client=self.db_client)
            if item is None:
                raise HTTPException(
                    status_code=503,
                    detail="Canonical memory write readback unavailable",
                )
            results.append(memory_item_to_memorydb(item))
        self._write_historical_overrides(uid, ids, MemoryItemStatus.active)
        self._invalidate_prompt_cache(uid)
        return results

    @_legal_hold_gated_deletion
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
        # External callers do not get a weaker privacy mode. The legacy
        # ``delete_vector`` argument is accepted for wire compatibility only;
        # explicit deletion always purges canonical and legacy vectors/content.
        del memory_system, consumer, operation, delete_vector
        self.delete(uid, memory_id)

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
            HistoricalMemoryAdapter.cleanup(uid, memory_id, db_client=self.db_client)
        self._invalidate_prompt_cache(uid)
        return updated
