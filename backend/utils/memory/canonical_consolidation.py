"""Canonical batched short-term consolidation (WS-O).

Deterministic code retrieves candidates, hydrates active memory_items, and assembles
LLM context. A single batched LLM agent is the sole decider of consolidation outcomes;
decisions are applied via ``apply_long_term_patch_firestore``.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Literal, Optional, Set, cast

from google.cloud.firestore_v1 import FieldFilter, transactional
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field, model_validator

from database._client import db as default_db_client
from database.firestore_index_registry import CANONICAL_CONSOLIDATION_QUERY
from database.memory_apply_store import (
    MissingMemoryDocument,
    apply_long_term_patch_firestore,
)
from database.memory_collections import MemoryCollections
from database.vector_db import query_memory_vector_candidates
from models.memory_evidence import SourceState
from models.memory_apply import (
    ApplyStatus,
    MemoryControlState,
    build_patch_mutation_identity,
    memory_content_hash,
)
from models.memory_contracts import (
    DurablePatchDecision,
    LifecycleState,
    deterministic_contract_id,
)
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.memory_promotion import (
    PromotionGraphPlan,
    build_promotion_admission_receipt,
)
from models.memory_search_gateway import SearchMode
from models.memory_recurrence import CanonicalRecurrenceSignal
from models.product_memory import (
    RESTRICTED_SENSITIVITY_LABELS,
    MemoryItem,
    MemoryItemStatus,
    MemoryLayer,
    ProcessingState,
    effective_short_term_expiry,
)
from langchain_core.messages import HumanMessage, SystemMessage

from utils.executors import llm_executor, submit_with_context
from utils.llm.clients import get_llm
from utils.llm.prompt_cache import EXPLICIT_CACHE_OPTIONS, has_cacheable_prefix
from utils.log_sanitizer import sanitize_pii
from utils.memory.memory_system import (
    MemorySystem as MemorySystem,  # compatibility export for older test doubles; never used for routing
    ensure_canonical_apply_control_state,
    resolve_memory_system as resolve_memory_system,  # compatibility export; universal routing does not call it
)
from utils.memory.canonical_required_processing import (
    ProcessedRequiredMemory,
    commit_required_processing,
    is_pending_required_processing,
    list_pending_required_processing_items,
)
from utils.memory.promotion_flex import (
    PromotionFlexControlChanged,
    PromotionFlexDeferred,
)
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

CONSOLIDATION_BY = "canonical_batched_consolidation"
DEFAULT_CONSOLIDATION_BATCH_THRESHOLD = 20
DEFAULT_CANDIDATES_PER_ITEM = 8
DEFAULT_CONSOLIDATION_QUERY_LIMIT = 250
MAX_CONSOLIDATION_QUERY_LIMIT = 500
MAX_CONSOLIDATION_FAILURE_ATTEMPTS = 3
CONSOLIDATION_ATTEMPT_LEASE_SECONDS = 600
CONSOLIDATION_RETRY_STATE_SCHEMA_VERSION = "canonical_consolidation_retry.v1"
CONSOLIDATION_CONTEXT_MEMORY_CONTENT_MAX_CHARS = 2_000
CONSOLIDATION_CONTEXT_CANDIDATE_CONTENT_MAX_CHARS = 1_000
CONSOLIDATION_CONTEXT_EVIDENCE_QUOTES_MAX_COUNT = 4
CONSOLIDATION_CONTEXT_EVIDENCE_QUOTE_MAX_CHARS = 500
CONSOLIDATION_CONTEXT_EVIDENCE_IDS_MAX_COUNT = 32
CONSOLIDATION_CONTEXT_EVIDENCE_SOURCE_IDS_MAX_COUNT = 16
CONSOLIDATION_CONTEXT_QUOTE_FIELDS_MAX_COUNT = 8
CONSOLIDATION_CONTEXT_QUOTE_COLLECTION_MAX_COUNT = 8
CONSOLIDATION_CONTEXT_QUOTE_MAX_DEPTH = 3
CONSOLIDATION_CONTEXT_ARGUMENTS_MAX_CHARS = 2_000
CONSOLIDATION_CONTEXT_PROMOTION_MAX_CHARS = 1_000
CONSOLIDATION_CONTEXT_METADATA_TEXT_MAX_CHARS = 500
CONSOLIDATION_CONTEXT_METADATA_COLLECTION_MAX_COUNT = 16
CONSOLIDATION_CONTEXT_METADATA_MAX_DEPTH = 3
CONSOLIDATION_CONTEXT_CANDIDATES_PER_ANCHOR_MAX_COUNT = 20
CONSOLIDATION_CONTEXT_REDACTED_TEXT = "[REDACTED: restricted sensitivity]"
CONSOLIDATION_CONTEXT_TRUNCATION_SUFFIX = "...[truncated]"

MEMORY_CANONICAL_CONSOLIDATION_ENABLED_ENV = "MEMORY_CANONICAL_CONSOLIDATION_ENABLED"
Payload = Dict[str, Any]


def _empty_candidate_map() -> Dict[str, List["ConsolidationCandidate"]]:
    return {}


def _empty_str_list() -> List[str]:
    return []


def _empty_consolidation_decisions() -> List["ConsolidationAgentDecision"]:
    return []


def _empty_recurrence_signals() -> List[CanonicalRecurrenceSignal]:
    return []


class ConsolidationRetryState(BaseModel):
    """Non-content operational state for one exact Short-term revision."""

    schema_version: str = CONSOLIDATION_RETRY_STATE_SCHEMA_VERSION
    uid: str
    memory_id: str
    source_item_revision: int = Field(ge=1)
    source_content_hash: Optional[str] = None
    attempt_count: int = Field(default=0, ge=0)
    status: Literal["retryable", "in_progress", "quarantined", "terminal_review"] = "retryable"
    last_error_code: str
    last_attempt_at: datetime
    lease_owner: Optional[str] = None
    lease_expires_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_identity(self):
        if not self.uid.strip() or not self.memory_id.strip() or not self.last_error_code.strip():
            raise ValueError("consolidation retry state identity must not be blank")
        _coerce_aware_utc(self.last_attempt_at)
        if self.lease_expires_at is not None:
            _coerce_aware_utc(self.lease_expires_at)
        if self.status == "in_progress" and (not self.lease_owner or self.lease_expires_at is None):
            raise ValueError("in-progress consolidation retry state requires a lease")
        return self


class ConsolidationScanCursor(BaseModel):
    """Durable fair-scan cursor used only while an earlier page is blocked."""

    schema_version: str = "canonical_consolidation_scan_cursor.v1"
    uid: str
    captured_at: datetime
    memory_id: str
    updated_at: datetime

    @model_validator(mode="after")
    def validate_cursor(self):
        if not self.uid.strip() or not self.memory_id.strip():
            raise ValueError("consolidation scan cursor identity must not be blank")
        _coerce_aware_utc(self.captured_at)
        _coerce_aware_utc(self.updated_at)
        return self


def _snapshot_payload(snapshot: Any) -> Payload:
    if not getattr(snapshot, "exists", False):
        return {}
    raw = snapshot.to_dict()
    return cast(Payload, raw) if isinstance(raw, dict) else {}


def _coerce_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _read_control_state(uid: str, *, db_client: Any) -> MemoryControlState:
    return ensure_canonical_apply_control_state(uid, db_client=db_client)


def _persist_control_state(control: MemoryControlState, *, db_client: Any) -> None:
    db_client.document(MemoryCollections(uid=control.uid).memory_apply_control_state).set(
        {
            "last_consolidation_run_at": (
                control.last_consolidation_run_at.isoformat() if control.last_consolidation_run_at is not None else None
            ),
            "updated_at": control.updated_at.isoformat(),
        },
        merge=True,
    )


def _retry_state_document_path(uid: str, item: MemoryItem) -> str:
    state_id = deterministic_contract_id(
        "canonical-consolidation-retry-state",
        {
            "uid": uid,
            "memory_id": item.memory_id,
            "source_item_revision": item.item_revision,
            "source_content_hash": item.content_hash,
        },
    )
    return f"{MemoryCollections(uid=uid).memory_runs}/consolidation_retry_{state_id[:32]}"


def _scan_cursor_document_path(uid: str) -> str:
    return f"{MemoryCollections(uid=uid).memory_runs}/canonical_consolidation_scan_cursor"


def _read_scan_cursor(uid: str, *, db_client: Any) -> Optional[ConsolidationScanCursor]:
    payload = _snapshot_payload(db_client.document(_scan_cursor_document_path(uid)).get())
    if not payload:
        return None
    cursor = ConsolidationScanCursor.model_validate(payload)
    if cursor.uid != uid:
        raise ValueError("consolidation scan cursor uid mismatch")
    return cursor


def _persist_scan_cursor(uid: str, item: MemoryItem, *, now: datetime, db_client: Any) -> None:
    cursor = ConsolidationScanCursor(
        uid=uid,
        captured_at=item.captured_at,
        memory_id=item.memory_id,
        updated_at=now,
    )
    db_client.document(_scan_cursor_document_path(uid)).set(cursor.model_dump(mode="python"))


def _clear_scan_cursor(uid: str, *, db_client: Any) -> None:
    db_client.document(_scan_cursor_document_path(uid)).delete()


def _read_retry_state(uid: str, item: MemoryItem, *, db_client: Any) -> Optional[ConsolidationRetryState]:
    snapshot = db_client.document(_retry_state_document_path(uid, item)).get()
    payload = _snapshot_payload(snapshot)
    if not payload:
        return None
    state = ConsolidationRetryState.model_validate(payload)
    if (
        state.uid != uid
        or state.memory_id != item.memory_id
        or state.source_item_revision != item.item_revision
        or state.source_content_hash != item.content_hash
    ):
        raise ValueError("consolidation retry state identity mismatch")
    return state


@transactional
def _claim_retry_state_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
    item: MemoryItem,
    lease_owner: str,
    now: datetime,
    lease_seconds: int,
) -> tuple[ConsolidationRetryState, bool]:
    ref = db_client.document(_retry_state_document_path(uid, item))
    snapshot = ref.get(transaction=transaction)
    payload = _snapshot_payload(snapshot)
    prior = ConsolidationRetryState.model_validate(payload) if payload else None
    if prior is not None and (
        prior.uid != uid
        or prior.memory_id != item.memory_id
        or prior.source_item_revision != item.item_revision
        or prior.source_content_hash != item.content_hash
    ):
        raise ValueError("consolidation retry state identity mismatch")
    if prior is not None:
        if prior.status in {"quarantined", "terminal_review"}:
            return prior, False
        if prior.attempt_count >= MAX_CONSOLIDATION_FAILURE_ATTEMPTS:
            return prior, False
        if (
            prior.status == "in_progress"
            and prior.lease_owner != lease_owner
            and prior.lease_expires_at is not None
            and prior.lease_expires_at > now
        ):
            return prior, False
        if prior.status == "in_progress" and prior.lease_owner == lease_owner:
            return prior, True
    state = ConsolidationRetryState(
        uid=uid,
        memory_id=item.memory_id,
        source_item_revision=item.item_revision,
        source_content_hash=item.content_hash,
        attempt_count=(prior.attempt_count if prior is not None else 0) + 1,
        status="in_progress",
        last_error_code=prior.last_error_code if prior is not None else "attempt_claimed",
        last_attempt_at=now,
        lease_owner=lease_owner,
        lease_expires_at=now + timedelta(seconds=lease_seconds),
    )
    transaction.set(ref, state.model_dump(mode="python"))
    return state, True


def _claim_retry_state(
    uid: str,
    item: MemoryItem,
    *,
    lease_owner: str,
    now: datetime,
    db_client: Any,
    lease_seconds: int = CONSOLIDATION_ATTEMPT_LEASE_SECONDS,
) -> tuple[ConsolidationRetryState, bool]:
    transaction = db_client.transaction()
    return _claim_retry_state_transaction(transaction, db_client, uid, item, lease_owner, now, lease_seconds)


@transactional
def _transition_retry_state_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
    item: MemoryItem,
    status: Literal["retryable", "quarantined", "terminal_review"],
    error_code: str,
    now: datetime,
    expected_lease_owner: Optional[str],
) -> ConsolidationRetryState:
    ref = db_client.document(_retry_state_document_path(uid, item))
    snapshot = ref.get(transaction=transaction)
    payload = _snapshot_payload(snapshot)
    if not payload:
        raise ValueError("consolidation retry state is missing")
    prior = ConsolidationRetryState.model_validate(payload)
    if (
        prior.uid != uid
        or prior.memory_id != item.memory_id
        or prior.source_item_revision != item.item_revision
        or prior.source_content_hash != item.content_hash
    ):
        raise ValueError("consolidation retry state identity mismatch")
    if expected_lease_owner is not None and prior.lease_owner != expected_lease_owner:
        raise ValueError("consolidation retry lease ownership changed")
    if prior.status in {"quarantined", "terminal_review"}:
        return prior
    state = prior.model_copy(
        update={
            "status": status,
            "last_error_code": error_code,
            "last_attempt_at": now,
            "lease_owner": None,
            "lease_expires_at": None,
        }
    )
    transaction.set(ref, state.model_dump(mode="python"))
    return state


def _transition_retry_state(
    uid: str,
    item: MemoryItem,
    *,
    status: Literal["retryable", "quarantined", "terminal_review"],
    error_code: str,
    now: datetime,
    db_client: Any,
    expected_lease_owner: Optional[str] = None,
) -> ConsolidationRetryState:
    transaction = db_client.transaction()
    return _transition_retry_state_transaction(
        transaction,
        db_client,
        uid,
        item,
        status,
        error_code,
        now,
        expected_lease_owner,
    )


@transactional
def _delete_retry_state_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
    item: MemoryItem,
    expected_lease_owner: str,
) -> None:
    ref = db_client.document(_retry_state_document_path(uid, item))
    snapshot = ref.get(transaction=transaction)
    payload = _snapshot_payload(snapshot)
    if not payload:
        return
    state = ConsolidationRetryState.model_validate(payload)
    if (
        state.uid != uid
        or state.memory_id != item.memory_id
        or state.source_item_revision != item.item_revision
        or state.source_content_hash != item.content_hash
    ):
        raise ValueError("consolidation retry state identity mismatch")
    if state.lease_owner != expected_lease_owner:
        raise ValueError("consolidation retry lease ownership changed")
    transaction.delete(ref)


def _delete_retry_state(
    uid: str,
    item: MemoryItem,
    *,
    expected_lease_owner: str,
    db_client: Any,
) -> None:
    transaction = db_client.transaction()
    _delete_retry_state_transaction(
        transaction,
        db_client,
        uid,
        item,
        expected_lease_owner,
    )


def _is_promotable_for_consolidation(item: MemoryItem, *, now: datetime) -> bool:
    current_time = _coerce_aware_utc(now)
    if item.tier != MemoryLayer.short_term:
        return False
    if item.status != MemoryItemStatus.active:
        return False
    if item.source_state != SourceState.active:
        return False
    if is_pending_required_processing(item):
        # Explicit submissions must still reach the planner. Conversation STM
        # expires at 48h; required rows stay eligible until they get a route.
        return True
    if item.processing_state != ProcessingState.processed:
        return False
    return effective_short_term_expiry(item) > current_time


def consolidation_enabled() -> bool:
    raw = os.getenv(MEMORY_CANONICAL_CONSOLIDATION_ENABLED_ENV, "true")
    return raw.lower() == "true"


def consolidation_batch_threshold() -> int:
    raw = os.getenv(
        "MEMORY_CANONICAL_CONSOLIDATION_BATCH_THRESHOLD",
        str(DEFAULT_CONSOLIDATION_BATCH_THRESHOLD),
    )
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_CONSOLIDATION_BATCH_THRESHOLD


def consolidation_batch_cap() -> int:
    """Max pending items per consolidation LLM call (defaults to batch threshold)."""
    default = str(consolidation_batch_threshold())
    raw = os.getenv("MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP", default)
    try:
        return max(1, int(raw))
    except ValueError:
        return consolidation_batch_threshold()


def max_consolidation_batches_per_pass() -> int:
    """Upper bound on LLM consolidation calls per maintenance pass.

    Default 25 * batch cap 20 drains 500 pending Short-term rows, which is the
    consolidation query window ceiling. Flex job-budget deferral still
    stops the loop before the Cloud Run hour expires.
    """
    raw = os.getenv("MEMORY_CANONICAL_CONSOLIDATION_MAX_BATCHES_PER_PASS", "25")
    try:
        return max(1, int(raw))
    except ValueError:
        return 25


def candidates_per_item_limit() -> int:
    raw = os.getenv(
        "MEMORY_CANONICAL_CONSOLIDATION_CANDIDATES_PER_ITEM",
        str(DEFAULT_CANDIDATES_PER_ITEM),
    )
    try:
        return max(1, min(20, int(raw)))
    except ValueError:
        return DEFAULT_CANDIDATES_PER_ITEM


def _is_active_consolidation_item(item: MemoryItem) -> bool:
    if item.status != MemoryItemStatus.active:
        return False
    if item.processing_state == ProcessingState.processed:
        return True
    return is_pending_required_processing(item)


def list_pending_consolidation_items(
    uid: str,
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    limit: int = DEFAULT_CONSOLIDATION_QUERY_LIMIT,
    start_after: Optional[tuple[datetime, str]] = None,
) -> List[MemoryItem]:
    """Fetch a bounded, oldest-first set of consolidation-eligible items."""
    client: Any = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))
    if limit <= 0:
        raise ValueError("consolidation query limit must be positive")
    effective_limit = min(limit, MAX_CONSOLIDATION_QUERY_LIMIT)
    required_items = list_pending_required_processing_items(
        uid,
        db_client=client,
        limit=min(effective_limit, 100),
    )
    query = CANONICAL_CONSOLIDATION_QUERY.build(
        client.collection(MemoryCollections(uid=uid).memory_items),
        {
            "tier": MemoryLayer.short_term.value,
            "status": MemoryItemStatus.active.value,
            "processing_state": ProcessingState.processed.value,
            "source_state": SourceState.active.value,
        },
        field_filter_factory=FieldFilter,
    )
    query = query.order_by("captured_at").order_by("memory_id")
    if start_after is not None:
        cursor_time, cursor_memory_id = start_after
        if not cursor_memory_id.strip():
            raise ValueError("consolidation query cursor memory_id must not be blank")
        query = query.start_after(
            {
                "captured_at": _coerce_aware_utc(cursor_time),
                "memory_id": cursor_memory_id,
            }
        )
    snapshots = query.limit(effective_limit).stream()
    items = [MemoryItem(**_snapshot_payload(snapshot)) for snapshot in snapshots]
    for item in items:
        if item.uid != uid:
            raise ValueError(f"consolidation query uid mismatch for {item.memory_id}")
    if start_after is not None:
        cursor_time, cursor_memory_id = start_after
        cursor_time = _coerce_aware_utc(cursor_time)
        required_items = [
            item for item in required_items if (item.captured_at, item.memory_id) > (cursor_time, cursor_memory_id)
        ]
    merged: Dict[str, MemoryItem] = {item.memory_id: item for item in required_items}
    merged.update({item.memory_id: item for item in items})
    pending = [
        item
        for item in merged.values()
        if item.uid == uid
        and _is_active_consolidation_item(item)
        and _is_promotable_for_consolidation(item, now=current_time)
    ]
    return sorted(pending, key=lambda item: (item.captured_at, item.memory_id))[:effective_limit]


def consolidation_trigger_reason(
    *,
    pending_count: int,
) -> Optional[str]:
    if pending_count <= 0:
        return None
    return "pending_items"


@dataclass(frozen=True)
class ConsolidationCandidate:
    anchor_memory_id: str
    memory_id: str
    content: str
    score: float
    tier: str
    captured_at: str
    sensitivity_labels: tuple[str, ...] = ()


@dataclass
class ConsolidationContext:
    uid: str
    pending_items: List[MemoryItem]
    candidates_by_anchor: Dict[str, List[ConsolidationCandidate]] = field(default_factory=_empty_candidate_map)

    @property
    def hydrated_memory_ids(self) -> Set[str]:
        ids: Set[str] = {item.memory_id for item in self.pending_items}
        for candidates in self.candidates_by_anchor.values():
            for candidate in candidates:
                ids.add(candidate.memory_id)
        return ids


def _hydrate_memory_item(
    uid: str, memory_id: str, *, db_client: Any, cache: Dict[str, Optional[MemoryItem]]
) -> Optional[MemoryItem]:
    if memory_id in cache:
        return cache[memory_id]
    path = f"{MemoryCollections(uid=uid).memory_items}/{memory_id}"
    payload = _snapshot_payload(db_client.document(path).get())
    if not payload:
        cache[memory_id] = None
        return None
    item = MemoryItem(**payload)
    if not _is_active_consolidation_item(item):
        cache[memory_id] = None
        return None
    cache[memory_id] = item
    return item


def gather_consolidation_candidates(
    uid: str,
    pending_items: List[MemoryItem],
    *,
    db_client: Any = None,
    candidate_limit: Optional[int] = None,
) -> ConsolidationContext:
    """Vector-search similar memories and hydrate active items (deterministic only)."""
    client: Any = db_client if db_client is not None else default_db_client
    per_item = candidate_limit if candidate_limit is not None else candidates_per_item_limit()
    context = ConsolidationContext(uid=uid, pending_items=list(pending_items))
    cache: Dict[str, Optional[MemoryItem]] = {item.memory_id: item for item in pending_items}

    for anchor in pending_items:
        content = (anchor.content or "").strip()
        if not content or _has_restricted_sensitivity(anchor.sensitivity_labels):
            context.candidates_by_anchor[anchor.memory_id] = []
            continue
        query_result = query_memory_vector_candidates(uid, content, mode=SearchMode.default, limit=per_item + 1)
        candidates: List[ConsolidationCandidate] = []
        seen: Set[str] = set()
        for hit in query_result.hits:
            if hit.memory_id == anchor.memory_id or hit.memory_id in seen:
                continue
            item = _hydrate_memory_item(uid, hit.memory_id, db_client=client, cache=cache)
            if item is None:
                continue
            seen.add(hit.memory_id)
            candidates.append(
                ConsolidationCandidate(
                    anchor_memory_id=anchor.memory_id,
                    memory_id=item.memory_id,
                    content=item.content or "",
                    score=hit.score,
                    tier=item.tier.value,
                    captured_at=item.captured_at.isoformat(),
                    sensitivity_labels=tuple(item.sensitivity_labels),
                )
            )
            if len(candidates) >= per_item:
                break
        context.candidates_by_anchor[anchor.memory_id] = candidates
    return context


def _has_restricted_sensitivity(labels: List[str] | tuple[str, ...]) -> bool:
    normalized = {label.strip().lower() for label in labels if label and label.strip()}
    return bool(normalized.intersection(RESTRICTED_SENSITIVITY_LABELS))


def _truncate_context_text(value: str, *, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    if max_chars <= len(CONSOLIDATION_CONTEXT_TRUNCATION_SUFFIX):
        return CONSOLIDATION_CONTEXT_TRUNCATION_SUFFIX[:max_chars]
    prefix_length = max_chars - len(CONSOLIDATION_CONTEXT_TRUNCATION_SUFFIX)
    return value[:prefix_length] + CONSOLIDATION_CONTEXT_TRUNCATION_SUFFIX


def _bounded_json_value(
    value: Any,
    *,
    text_max_chars: int,
    mapping_max_count: int,
    sequence_max_count: int,
    max_depth: int,
    depth: int = 0,
) -> Any:
    """Bound arbitrary JSON-like data without changing ordinary in-budget values."""
    if isinstance(value, str):
        return _truncate_context_text(value, max_chars=text_max_chars)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if depth >= max_depth:
        return CONSOLIDATION_CONTEXT_TRUNCATION_SUFFIX
    if isinstance(value, dict):
        keys = sorted(value, key=str)[:mapping_max_count]
        return {
            _truncate_context_text(str(key), max_chars=text_max_chars): _bounded_json_value(
                value[key],
                text_max_chars=text_max_chars,
                mapping_max_count=mapping_max_count,
                sequence_max_count=sequence_max_count,
                max_depth=max_depth,
                depth=depth + 1,
            )
            for key in keys
        }
    if isinstance(value, (list, tuple)):
        return [
            _bounded_json_value(
                entry,
                text_max_chars=text_max_chars,
                mapping_max_count=mapping_max_count,
                sequence_max_count=sequence_max_count,
                max_depth=max_depth,
                depth=depth + 1,
            )
            for entry in value[:sequence_max_count]
        ]
    return _truncate_context_text(str(value), max_chars=text_max_chars)


def _bounded_quote_value(value: Any) -> Any:
    return _bounded_json_value(
        value,
        text_max_chars=CONSOLIDATION_CONTEXT_EVIDENCE_QUOTE_MAX_CHARS,
        mapping_max_count=CONSOLIDATION_CONTEXT_QUOTE_FIELDS_MAX_COUNT,
        sequence_max_count=CONSOLIDATION_CONTEXT_QUOTE_COLLECTION_MAX_COUNT,
        max_depth=CONSOLIDATION_CONTEXT_QUOTE_MAX_DEPTH,
    )


def _bounded_metadata(value: Payload, *, max_chars: int) -> Any:
    bounded = _bounded_json_value(
        value,
        text_max_chars=CONSOLIDATION_CONTEXT_METADATA_TEXT_MAX_CHARS,
        mapping_max_count=CONSOLIDATION_CONTEXT_METADATA_COLLECTION_MAX_COUNT,
        sequence_max_count=CONSOLIDATION_CONTEXT_METADATA_COLLECTION_MAX_COUNT,
        max_depth=CONSOLIDATION_CONTEXT_METADATA_MAX_DEPTH,
    )
    serialized = json.dumps(bounded, sort_keys=True, separators=(",", ":"))
    if len(serialized) <= max_chars:
        return bounded
    return {"truncated": True}


def _bounded_evidence_quotes(item: MemoryItem, *, restricted: bool) -> List[Payload]:
    if restricted:
        return []
    quotes: List[Payload] = []
    for evidence in item.evidence[:CONSOLIDATION_CONTEXT_EVIDENCE_IDS_MAX_COUNT]:
        for quote_ref in evidence.quote_refs:
            quotes.append(cast(Payload, _bounded_quote_value(quote_ref)))
            if len(quotes) >= CONSOLIDATION_CONTEXT_EVIDENCE_QUOTES_MAX_COUNT:
                return quotes
    return quotes


def _source_attribution_metadata(item: MemoryItem) -> Payload:
    raw = (item.promotion or {}).get("source_attribution")
    if not isinstance(raw, dict):
        return {}
    attribution = raw.get("subject_attribution")
    subject_entity_id = raw.get("subject_entity_id")
    subject_kind = raw.get("subject_kind")
    return {
        "subject_attribution": attribution if isinstance(attribution, str) else None,
        "subject_entity_id": subject_entity_id if isinstance(subject_entity_id, str) else None,
        "subject_kind": subject_kind if isinstance(subject_kind, str) else None,
    }


def format_consolidation_llm_context(context: ConsolidationContext) -> str:
    """Serialize a bounded, sensitivity-aware batch for the consolidation agent."""
    memories: List[Payload] = []
    candidate_groups: List[Payload] = []
    payload: Payload = {"memories": memories, "candidate_groups": candidate_groups}
    for item in context.pending_items:
        restricted = _has_restricted_sensitivity(item.sensitivity_labels)
        content = item.content or ""
        memories.append(
            {
                "memory_id": item.memory_id,
                "content": (
                    CONSOLIDATION_CONTEXT_REDACTED_TEXT
                    if restricted
                    else _truncate_context_text(
                        content,
                        max_chars=CONSOLIDATION_CONTEXT_MEMORY_CONTENT_MAX_CHARS,
                    )
                ),
                "tier": item.tier.value,
                "captured_at": item.captured_at.isoformat(),
                "evidence_source_ids": sorted({ev.source_id for ev in item.evidence if ev.source_id})[
                    :CONSOLIDATION_CONTEXT_EVIDENCE_SOURCE_IDS_MAX_COUNT
                ],
                "evidence_ids": [ev.evidence_id for ev in item.evidence[:CONSOLIDATION_CONTEXT_EVIDENCE_IDS_MAX_COUNT]],
                "evidence_quotes": _bounded_evidence_quotes(item, restricted=restricted),
                "corroboration_count": getattr(item, "corroboration_count", 0) or 0,
                "subject_entity_id": getattr(item, "subject_entity_id", None),
                "source_attribution": _source_attribution_metadata(item),
                "predicate": getattr(item, "predicate", None),
                "arguments": (
                    {}
                    if restricted
                    else _bounded_metadata(
                        getattr(item, "arguments", {}),
                        max_chars=CONSOLIDATION_CONTEXT_ARGUMENTS_MAX_CHARS,
                    )
                ),
                "promotion": (
                    {"redacted": True}
                    if restricted
                    else _bounded_metadata(
                        item.promotion or {},
                        max_chars=CONSOLIDATION_CONTEXT_PROMOTION_MAX_CHARS,
                    )
                ),
                "sensitivity_labels": item.sensitivity_labels,
                "requires_normalization": is_pending_required_processing(item),
            }
        )
    for anchor_id, candidates in context.candidates_by_anchor.items():
        if not candidates:
            continue
        candidate_groups.append(
            {
                "anchor_memory_id": anchor_id,
                "candidates": [
                    {
                        "memory_id": c.memory_id,
                        "content": (
                            CONSOLIDATION_CONTEXT_REDACTED_TEXT
                            if _has_restricted_sensitivity(c.sensitivity_labels)
                            else _truncate_context_text(
                                c.content,
                                max_chars=CONSOLIDATION_CONTEXT_CANDIDATE_CONTENT_MAX_CHARS,
                            )
                        ),
                        "score": round(c.score, 4),
                        "tier": c.tier,
                        "captured_at": c.captured_at,
                        "sensitivity_labels": list(c.sensitivity_labels),
                    }
                    for c in candidates[:CONSOLIDATION_CONTEXT_CANDIDATES_PER_ANCHOR_MAX_COUNT]
                ],
            }
        )
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class ConsolidationAgentDecision(BaseModel):
    """One total, item-addressed L2 route for a pending Short-term memory."""

    source_memory_id: str = Field(description="Pending memory_id this decision settles")
    route: Literal["promote", "archive", "review", "reject"]
    reconciliation: Literal["create", "replace", "merge", "duplicate", "keep_both"] = "create"
    target_memory_id: Optional[str] = Field(
        default=None,
        description="Existing memory used for duplicate/replace/merge reasoning",
    )
    supersedes: List[str] = Field(default_factory=list, description="Active memory_ids replaced by this source")
    memory_text: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    subject_entity_id: Optional[str] = None
    predicate: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    relationship_to_user: Literal[
        "self",
        "owned_work",
        "adopted",
        "asking_about",
        "encountered",
        "other_speaker",
        "unclear",
    ] = "unclear"
    aboutness: Literal[
        "primary_user",
        "user_owned_project",
        "user_relationship",
        "third_party",
        "unclear",
    ] = "unclear"
    basis_for_memory: Literal["explicit", "recurring", "inferred_pattern", "weak_or_none"] = "weak_or_none"
    confidence: Literal["high", "medium", "low"] = "medium"
    rationale: str = ""

    @model_validator(mode="after")
    def validate_route(self):
        if not self.source_memory_id.strip():
            raise ValueError("source_memory_id is required")
        self.supersedes = sorted({value.strip() for value in self.supersedes if value and value.strip()})
        if self.source_memory_id in self.supersedes:
            raise ValueError("a promotion cannot supersede its source item")
        if self.target_memory_id == self.source_memory_id:
            raise ValueError("target_memory_id cannot point to the source item")
        if self.reconciliation in {"replace", "merge", "duplicate"} and not self.target_memory_id:
            raise ValueError("replace/merge/duplicate requires target_memory_id")
        if self.route == "promote":
            if not (self.memory_text or "").strip():
                raise ValueError("promote requires memory_text")
            if not self.evidence_ids:
                raise ValueError("promote requires exact evidence_ids")
            PromotionGraphPlan(
                subject_entity_id=self.subject_entity_id or "",
                predicate=self.predicate or "",
                arguments=self.arguments,
            )
            if self.basis_for_memory == "weak_or_none":
                raise ValueError("promote requires a defensible relationship-to-user basis")
            if self.reconciliation == "duplicate":
                raise ValueError("duplicate observations must not be promoted")
            if self.reconciliation in {"replace", "merge"} and self.target_memory_id not in self.supersedes:
                raise ValueError("replace/merge promotion must supersede its target_memory_id")
            if self.reconciliation in {"create", "keep_both"} and self.supersedes:
                raise ValueError("create/keep_both promotion cannot supersede existing memories")
        elif self.supersedes:
            raise ValueError("only promote routes may supersede active memories")
        return self


class ConsolidationAgentBatch(BaseModel):
    decisions: List[ConsolidationAgentDecision] = Field(default_factory=_empty_consolidation_decisions)
    recurrence_signals: List[CanonicalRecurrenceSignal] = Field(default_factory=_empty_recurrence_signals)
    reasoning: str = ""


CONSOLIDATION_AGENT_PROMPT = """You are Omi's canonical Long-term memory promotion planner.

You receive a BATCH of evidence-backed Short-term candidates plus authoritative
vector-similar memories. Return EXACTLY ONE decision for EVERY pending memory_id.
Never omit an input and never invent an id.

Routes:
- promote: future-useful, evidence-grounded memory with a defensible relationship to this user.
- archive: source-backed context worth retaining, but not stable profile truth.
- review: potentially useful but attribution/conflict is too uncertain for automatic promotion.
- reject: ephemeral, unsupported, unsafe, or not useful enough to retain as a memory.

Rules:
- L1 was intentionally broad. You own durable memory-worthiness, subject safety,
  deduplication, conflict resolution, and clean standalone synthesis.
- source_attribution and the source subject_entity_id are authoritative. Never
  rewrite a non-user or unknown source subject into the primary user, and never
  change a known source subject_entity_id during promotion.
- A topic is not enough. Durable memory needs a defensible relationship_to_user
  (self, owned_work, adopted, or genuinely recurring relationship context).
- Merely encountered or ambient media dialogue, quoted characters, and topics
  discussed are not user facts. Route archive/reject unless evidence establishes
  an adopted user preference or commitment.
- For promote, emit concise memory_text plus a structured assertion:
  subject_entity_id, snake_case predicate, and at least one named argument.
- Items with requires_normalization=true are raw explicit submissions. Normalize
  them into memory_text, snake_case predicate, and arguments as part of this
  same decision. Archive/reject remain valid terminal routes; do not leave them
  without a durable outcome.
- Use supersedes only when older active facts are outdated/false or when this
  synthesized item intentionally replaces/merges them.
- Duplicate candidates route archive or reject; do not promote another copy.
- Compatible facts use reconciliation=keep_both and supersedes=[].
- evidence_ids must be a subset of the source item's evidence IDs.
- review/archive/reject are terminal outcomes and must never silently promote.
- sensitivity_labels are authoritative. A source with any restricted label
  ({restricted_sensitivity_labels}) MUST NOT route promote.
- aboutness=third_party or unclear MUST NOT route promote.
- relationship_to_user asking_about, encountered, or unclear MUST NOT route
  promote. other_speaker is promotable only for recurring user_relationship
  context; otherwise route archive/review/reject.
- A non-promote decision may target another pending source only when that target
  routes promote in this batch. Never supersede a pending source.

Reference conflict-resolution patterns (adapt for batch reasoning):
- Preference flip (loves→hates): promote source, reconciliation=replace, supersede old.
- Location change (NYC→LA): promote source, reconciliation=replace, supersede old.
- Duplicate text: archive/reject source, reconciliation=duplicate, target=existing.
- Compatible preferences (tennis + basketball): promote source, reconciliation=keep_both.
- Cross-source richer fact: promote source, reconciliation=merge, supersede old.
- recurrence_signals are only for the same unresolved open loop appearing on at
  least two distinct days. One-off mentions never qualify. Cite only canonical
  memory_item/conversation EvidenceRefs; do not include raw source content.
  EvidenceRefs MUST be oldest-first, retaining the original first-seen evidence
  anchor when later batches add evidence or refine wording. signal_id identifies
  this observation; workflow derives enduring loop identity from canonical time
  and that first evidence anchor rather than trusting model-authored identity.

{format_instructions}
"""

CONSOLIDATION_CACHE_KEY = "omi-canonical-consolidation-v1"


def build_consolidation_llm_messages(context: ConsolidationContext) -> list[Any]:
    """Stable cached prefix + volatile batch JSON on a message boundary.

    GPT-5.6 only serves a cache read when the stable text ends on an explicit
    breakpoint. Putting Batch JSON in the same message as the planner rules
    would force a unique write on every 20-item call.
    """
    parser = PydanticOutputParser(pydantic_object=ConsolidationAgentBatch)
    prefix = CONSOLIDATION_AGENT_PROMPT.format(
        format_instructions=parser.get_format_instructions(),
        restricted_sensitivity_labels=", ".join(sorted(RESTRICTED_SENSITIVITY_LABELS)),
    )
    suffix = f"Batch JSON:\n{format_consolidation_llm_context(context)}"
    block: Dict[str, Any] = {"type": "text", "text": prefix}
    if has_cacheable_prefix(prefix):
        block["prompt_cache_breakpoint"] = {"mode": "explicit"}
    return [SystemMessage(content=[block]), HumanMessage(content=suffix)]


def _invoke_consolidation_llm(messages: list[Any]) -> str:
    cache_enabled = False
    if messages:
        content = getattr(messages[0], "content", None)
        if isinstance(content, list) and content:
            first = content[0]
            cache_enabled = isinstance(first, dict) and "prompt_cache_breakpoint" in first
    llm = get_llm(
        "memory_conflict",
        cache_key=CONSOLIDATION_CACHE_KEY if cache_enabled else None,
        prompt_cache_options=EXPLICIT_CACHE_OPTIONS if cache_enabled else None,
    )
    response = llm.invoke(messages)
    return cast(str, getattr(response, "content", str(response)))


def invoke_consolidation_agent(
    context: ConsolidationContext,
    *,
    llm_invoke: Optional[Callable[[Any], str]] = None,
) -> ConsolidationAgentBatch:
    """Single batched LLM call — sole decider for consolidation outcomes."""
    parser = PydanticOutputParser(pydantic_object=ConsolidationAgentBatch)
    messages = build_consolidation_llm_messages(context)
    try:
        if llm_invoke is not None:
            raw = llm_invoke(messages)
        else:
            raw = submit_with_context(llm_executor, _invoke_consolidation_llm, messages).result()
    except (PromotionFlexControlChanged, PromotionFlexDeferred):
        raise
    except Exception as exc:
        logger.warning(
            "consolidation_agent_invoke_failed uid=%s error=%s",
            context.uid,
            type(exc).__name__,
        )
        return ConsolidationAgentBatch(decisions=[], reasoning=f"invoke_failed:{type(exc).__name__}")
    try:
        return parser.parse(raw)
    except Exception as exc:
        logger.warning(
            "consolidation_agent_parse_failed uid=%s error=%s",
            context.uid,
            type(exc).__name__,
        )
        return ConsolidationAgentBatch(decisions=[], reasoning=f"parse_failed:{type(exc).__name__}")


class ConsolidationApplySkipped(Exception):
    """A route could not be safely validated or committed."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _agent_batch_blocks_watermark(agent_batch: ConsolidationAgentBatch) -> bool:
    """True when agent output is unusable (invoke/parse failure)."""
    return agent_batch.reasoning.startswith(("parse_failed:", "invoke_failed:", "output_invalid:"))


def _consolidation_decision_identity(
    *,
    uid: str,
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
    quarantine: bool = False,
) -> Payload:
    """Stable consolidation identity for idempotency across maintenance passes."""
    return {
        "uid": uid,
        "source_memory_id": source.memory_id,
        "source_item_revision": source.item_revision,
        "source_content_hash": source.content_hash,
        "decision": decision.model_dump(mode="json"),
        "quarantine": quarantine,
    }


def _validate_agent_batch(
    context: ConsolidationContext,
    agent_batch: ConsolidationAgentBatch,
) -> Optional[str]:
    """Enforce conservation and reference allowlists before the first mutation."""
    if _agent_batch_blocks_watermark(agent_batch):
        return agent_batch.reasoning

    pending_by_id = {item.memory_id: item for item in context.pending_items}
    expected_ids = set(pending_by_id)
    actual_ids = [decision.source_memory_id for decision in agent_batch.decisions]
    if len(actual_ids) != len(set(actual_ids)):
        return "output_invalid:duplicate_source_memory_id"
    if set(actual_ids) != expected_ids:
        missing = sorted(expected_ids - set(actual_ids))
        unknown = sorted(set(actual_ids) - expected_ids)
        return f"output_invalid:partition_mismatch:missing={len(missing)}:unknown={len(unknown)}"

    candidate_by_id = {
        candidate.memory_id: candidate
        for candidates in context.candidates_by_anchor.values()
        for candidate in candidates
    }
    decision_by_source_id = {decision.source_memory_id: decision for decision in agent_batch.decisions}
    allowed_reference_ids = context.hydrated_memory_ids
    for decision in agent_batch.decisions:
        source = pending_by_id[decision.source_memory_id]
        if decision.route == "promote":
            if set(source.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS):
                return f"output_invalid:restricted_sensitivity_promotion:{source.memory_id}"
            if decision.aboutness in {"third_party", "unclear"}:
                return f"output_invalid:unsafe_aboutness_promotion:{source.memory_id}"
            relationship_is_durable = decision.relationship_to_user in {
                "self",
                "owned_work",
                "adopted",
            } or (
                decision.relationship_to_user == "other_speaker"
                and decision.aboutness == "user_relationship"
                and decision.basis_for_memory == "recurring"
            )
            if not relationship_is_durable:
                return f"output_invalid:weak_relationship_promotion:{source.memory_id}"
            source_attribution = _source_attribution_metadata(source)
            if not source_attribution:
                if not source.user_asserted:
                    return f"output_invalid:missing_source_attribution:{source.memory_id}"
            else:
                attribution = source_attribution.get("subject_attribution")
                source_subject_id = source_attribution.get("subject_entity_id")
                subject_kind = source_attribution.get("subject_kind")
                if source_subject_id and source_subject_id != source.subject_entity_id:
                    return f"output_invalid:source_attribution_mismatch:{source.memory_id}"
                attribution_is_unknown = attribution in {"unknown", "legacy_assumed"} or not source_subject_id
                if attribution_is_unknown and not source.user_asserted:
                    return f"output_invalid:unknown_source_subject_promotion:{source.memory_id}"
                if attribution not in {
                    "user",
                    "third_party",
                    "unknown",
                    "legacy_assumed",
                }:
                    return f"output_invalid:unknown_source_subject_promotion:{source.memory_id}"
                if source_subject_id and decision.subject_entity_id != source_subject_id:
                    return f"output_invalid:source_subject_contradiction:{source.memory_id}"
                if attribution == "user" and not (
                    (decision.relationship_to_user == "self" and decision.aboutness == "primary_user")
                    or (decision.relationship_to_user == "owned_work" and decision.aboutness == "user_owned_project")
                    or (decision.relationship_to_user == "adopted" and decision.aboutness == "user_relationship")
                ):
                    return f"output_invalid:source_subject_contradiction:{source.memory_id}"
                third_party_is_person = attribution == "third_party" and subject_kind in {
                    None,
                    "unknown",
                    "speaker",
                    "person",
                }
                if third_party_is_person and (
                    decision.relationship_to_user != "other_speaker" or decision.aboutness != "user_relationship"
                ):
                    return f"output_invalid:source_subject_contradiction:{source.memory_id}"
                if (
                    attribution == "third_party"
                    and subject_kind == "entity"
                    and not (
                        (decision.relationship_to_user == "owned_work" and decision.aboutness == "user_owned_project")
                        or (decision.relationship_to_user == "adopted" and decision.aboutness == "user_relationship")
                    )
                ):
                    return f"output_invalid:source_subject_contradiction:{source.memory_id}"
        source_evidence_ids = {evidence.evidence_id for evidence in source.evidence}
        if len(decision.evidence_ids) != len(set(decision.evidence_ids)):
            return f"output_invalid:duplicate_evidence:{source.memory_id}"
        if not set(decision.evidence_ids).issubset(source_evidence_ids):
            return f"output_invalid:evidence_not_owned_by_source:{source.memory_id}"

        referenced_ids = set(decision.supersedes)
        if decision.target_memory_id:
            referenced_ids.add(decision.target_memory_id)
        if not referenced_ids.issubset(allowed_reference_ids):
            return f"output_invalid:unknown_reference:{source.memory_id}"
        if set(decision.supersedes).intersection(expected_ids):
            return f"output_invalid:cross_pending_reference:{source.memory_id}"
        if decision.target_memory_id in expected_ids:
            target_decision = decision_by_source_id[decision.target_memory_id]
            if decision.route == "promote" or target_decision.route != "promote":
                return f"output_invalid:cross_pending_reference:{source.memory_id}"
        if any(
            candidate_by_id.get(memory_id) is None or candidate_by_id[memory_id].tier != MemoryLayer.long_term.value
            for memory_id in decision.supersedes
        ):
            return f"output_invalid:supersede_target_not_long_term:{source.memory_id}"

    # Batch-level guard: two decisions must not supersede the same Long-term
    # candidate. Per-decision validation cannot catch this — the first promotion
    # commits and marks the target superseded, so the second reaches this
    # validation with an inactive target and fails after partial apply.
    seen_supersede_targets: Dict[str, str] = {}
    for decision in agent_batch.decisions:
        for target_id in decision.supersedes:
            if target_id in seen_supersede_targets:
                return f"output_invalid:duplicate_supersede_target:{decision.source_memory_id}"
            seen_supersede_targets[target_id] = decision.source_memory_id
    return None


def _ordered_route_evidence_ids(
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
) -> List[str]:
    requested = set(decision.evidence_ids)
    if decision.route != "promote":
        requested = {evidence.evidence_id for evidence in source.evidence}
    ordered = [evidence.evidence_id for evidence in source.evidence if evidence.evidence_id in requested]
    if not ordered:
        raise ConsolidationApplySkipped(f"route has no active source evidence: {source.memory_id}")
    if set(ordered) != requested:
        raise ConsolidationApplySkipped(f"route evidence changed after planning: {source.memory_id}")
    return ordered


def _route_result_status(decision: ConsolidationAgentDecision) -> LifecycleState:
    return LifecycleState.hidden if decision.route == "reject" else LifecycleState.active


def _route_target_tier(decision: ConsolidationAgentDecision, *, quarantine: bool) -> MemoryLayer:
    # explicit_archive_memory: non-durable L2 outcomes are retained only outside default reads.
    if quarantine:
        return MemoryLayer.short_term
    return MemoryLayer.long_term if decision.route == "promote" else MemoryLayer.archive


def _route_logical_payload(
    *,
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
    quarantine: bool,
) -> Payload:
    promote = decision.route == "promote"
    return {
        "decision": DurablePatchDecision.update.value,
        "target_memory_id": source.memory_id,
        "memory_text": decision.memory_text if promote else None,
        "result_status": _route_result_status(decision).value,
        "supersedes": sorted(decision.supersedes),
        "subject_entity_id": decision.subject_entity_id if promote else None,
        "predicate": decision.predicate if promote else None,
        "arguments": decision.arguments if promote else {},
        "target_tier": _route_target_tier(decision, quarantine=quarantine).value,
    }


def _new_consolidation_operation(
    *,
    uid: str,
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
    control: MemoryControlState,
    evidence_ids: List[str],
    logical_payload: Payload,
    quarantine: bool,
) -> MemoryOperation:
    source_packet_id = deterministic_contract_id(
        "canonical-promotion-route",
        _consolidation_decision_identity(
            uid=uid,
            source=source,
            decision=decision,
            quarantine=quarantine,
        ),
    )
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.synthesis,
        source_packet_id=source_packet_id,
        target_memory_id=source.memory_id,
        evidence_ids=evidence_ids,
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    return operation


def _promotion_audit(
    *,
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
    evidence_ids: List[str],
    now: datetime,
    quarantine: bool,
) -> Payload:
    audit: Payload = {
        **(source.promotion or {}),
        "route": decision.route,
        "reconciliation": decision.reconciliation,
        "target_memory_id": decision.target_memory_id,
        "relationship_to_user": decision.relationship_to_user,
        "aboutness": decision.aboutness,
        "basis_for_memory": decision.basis_for_memory,
        "confidence": decision.confidence,
        "rationale": sanitize_pii(decision.rationale or "")[:500],
        "processing_status": "processing_blocked" if quarantine else "processed",
        "processed_at": now,
        "processed_by": CONSOLIDATION_BY,
    }
    if decision.route != "promote":
        return audit

    graph_plan = PromotionGraphPlan(
        subject_entity_id=decision.subject_entity_id or "",
        predicate=decision.predicate or "",
        arguments=decision.arguments,
    )
    output_hash = memory_content_hash(
        content=decision.memory_text,
        evidence_ids=evidence_ids,
    )
    receipt = build_promotion_admission_receipt(
        memory_id=source.memory_id,
        source_item_revision=source.item_revision,
        output_content_hash=output_hash,
        evidence_ids=evidence_ids,
        graph_plan=graph_plan,
        supersedes=decision.supersedes,
    )
    audit.update(
        {
            "from_tier": MemoryLayer.short_term.value,
            "to_tier": MemoryLayer.long_term.value,
            "promoted_at": now,
            "graph_plan": graph_plan.model_dump(mode="json"),
            "admission_receipt": receipt.model_dump(mode="json"),
        }
    )
    return audit


def _processed_from_consolidation_decision(
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
) -> ProcessedRequiredMemory:
    content = (decision.memory_text or source.content or "").strip()
    if not content:
        raise ConsolidationApplySkipped(f"required source has no normalizable content: {source.memory_id}")
    predicate = (decision.predicate or source.predicate or "remembered_fact").strip()
    subject = (decision.subject_entity_id or source.subject_entity_id or "user").strip()
    try:
        return ProcessedRequiredMemory(
            content=content[:1000],
            subject_entity_id=subject,
            predicate=predicate,
            arguments=dict(decision.arguments or source.arguments or {}),
            sensitivity_labels=list(source.sensitivity_labels or []),
            rationale=(decision.rationale or "normalized during consolidation")[:500],
        )
    except Exception as exc:
        raise ConsolidationApplySkipped(
            f"required source could not be normalized from the consolidation decision: {source.memory_id}"
        ) from exc


def _bind_required_promote_memory_text(
    source: MemoryItem,
    decision: ConsolidationAgentDecision,
) -> ConsolidationAgentDecision:
    """Keep promote text identical to L2 content so INV-MEM-4 receipt hashes match.

    L2 commit and the promote patch are separate ledger applies. After a successful
    L2 write the item is already processed with ``required=True``; a later pass or
    mixed batch must still bind ``memory_text`` to that stored content, not a
    rewritten planner string.
    """
    if decision.route != "promote":
        return decision
    if not (source.promotion or {}).get("required"):
        return decision
    return decision.model_copy(update={"memory_text": source.content})


def apply_consolidation_decision(
    uid: str,
    *,
    decision: ConsolidationAgentDecision,
    pending_by_id: Dict[str, MemoryItem],
    control: MemoryControlState,
    run_id: str,
    now: datetime,
    db_client: Any,
    quarantine: bool = False,
) -> List[str]:
    """Atomically settle one source item, including LT graph assertion/supersedes."""
    source = pending_by_id.get(decision.source_memory_id)
    if source is None:
        raise ConsolidationApplySkipped(f"missing pending source: {decision.source_memory_id}")
    if is_pending_required_processing(source):
        processed = _processed_from_consolidation_decision(source, decision)
        try:
            source = commit_required_processing(source, processed, db_client=db_client, now=now)
        except Exception as exc:
            raise ConsolidationApplySkipped(
                f"required processing apply failed for {decision.source_memory_id}"
            ) from exc
        pending_by_id[source.memory_id] = source
        control = _read_control_state(uid, db_client=db_client)
    decision = _bind_required_promote_memory_text(source, decision)
    if (
        source.tier != MemoryLayer.short_term
        or source.status != MemoryItemStatus.active
        or source.processing_state != ProcessingState.processed
        or source.source_state != SourceState.active
    ):
        raise ConsolidationApplySkipped(f"source is no longer promotable: {source.memory_id}")

    evidence_ids = _ordered_route_evidence_ids(source, decision)
    idempotency_key = deterministic_contract_id(
        "canonical-promotion-route",
        _consolidation_decision_identity(
            uid=uid,
            source=source,
            decision=decision,
            quarantine=quarantine,
        ),
    )
    logical_payload = _route_logical_payload(
        source=source,
        decision=decision,
        quarantine=quarantine,
    )
    patch_payload: Dict[str, Any] = {
        "patch_id": f"patch_cons_{idempotency_key[:24]}",
        "packet_id": f"consolidation_{run_id}",
        "run_id": run_id,
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        **logical_payload,
        "evidence_ids": evidence_ids,
        "expected_item_revision": source.item_revision,
        "expected_content_hash": source.content_hash,
        "promotion_audit": _promotion_audit(
            source=source,
            decision=decision,
            evidence_ids=evidence_ids,
            now=now,
            quarantine=quarantine,
        ),
    }
    mutation_identity = build_patch_mutation_identity(patch_payload)
    patch_payload["mutation_metadata"] = mutation_identity
    logical_payload["mutation_metadata"] = mutation_identity
    operation = _new_consolidation_operation(
        uid=uid,
        source=source,
        decision=decision,
        control=control,
        evidence_ids=evidence_ids,
        logical_payload=logical_payload,
        quarantine=quarantine,
    )

    result = None
    for _attempt in range(3):
        result = apply_long_term_patch_firestore(
            uid=uid,
            operation_id=operation.operation_id,
            patch_payload=patch_payload,
            proposed_operation=operation,
            db_client=db_client,
        )
        if result.status != ApplyStatus.retryable_head_mismatch:
            break
    assert result is not None
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise ConsolidationApplySkipped(
            f"promotion route failed for {source.memory_id}: {result.status} ({result.reason})"
        )
    return [source.memory_id, *decision.supersedes]


@dataclass
class ConsolidationReport:
    uid: str
    skipped_reason: Optional[str] = None
    trigger_reason: Optional[str] = None
    pending_count: int = 0
    decisions_applied: int = 0
    decisions_skipped: int = 0
    batched_memory_ids: List[str] = field(default_factory=_empty_str_list)
    promoted_memory_ids: List[str] = field(default_factory=_empty_str_list)
    archived_memory_ids: List[str] = field(default_factory=_empty_str_list)
    rejected_memory_ids: List[str] = field(default_factory=_empty_str_list)
    review_memory_ids: List[str] = field(default_factory=_empty_str_list)
    superseded_memory_ids: List[str] = field(default_factory=_empty_str_list)
    review_escalations: int = 0
    last_consolidation_run_at: Optional[datetime] = None
    watermark_blocked: bool = False
    recurrence_signals: List[CanonicalRecurrenceSignal] = field(default_factory=_empty_recurrence_signals)
    retryable_memory_ids: List[str] = field(default_factory=_empty_str_list)
    quarantined_memory_ids: List[str] = field(default_factory=_empty_str_list)
    errors: List[str] = field(default_factory=_empty_str_list)


def _safe_consolidation_failure_code(reason: str) -> str:
    """Return a bounded, non-content failure class safe for state and summaries."""
    segments = [segment for segment in reason.split(":") if segment]
    if not segments:
        return "consolidation_failed"
    if segments[0] in {"invoke_failed", "parse_failed"}:
        return ":".join(segments[:2])[:120]
    if segments[0] == "output_invalid":
        return ":".join(segments[:2])[:120]
    if segments[0] in {
        "candidate_hydration",
        "recurrence_handoff",
        "apply_blocked",
        "retry_state",
    }:
        return ":".join(segments[:2])[:120]
    return segments[0][:120]


def _terminal_review_decision(item: MemoryItem) -> ConsolidationAgentDecision:
    return ConsolidationAgentDecision(
        source_memory_id=item.memory_id,
        route="review",
        reconciliation="create",
        relationship_to_user="unclear",
        aboutness="unclear",
        basis_for_memory="weak_or_none",
        confidence="low",
        rationale="Automatic consolidation exhausted its bounded retry budget; manual review is required.",
    )


def _append_report_error(report: ConsolidationReport, error_code: str) -> None:
    if error_code not in report.errors:
        report.errors.append(error_code)


def _escalate_to_terminal_review(
    uid: str,
    item: MemoryItem,
    *,
    state: ConsolidationRetryState,
    report: ConsolidationReport,
    batched_ids: List[str],
    run_id: str,
    now: datetime,
    db_client: Any,
) -> None:
    """Settle an exhausted source as review, or quarantine it without promotion."""
    error_code = state.last_error_code
    _append_report_error(report, f"consolidation_retry_exhausted:{error_code}")
    decision = _terminal_review_decision(item)
    quarantine_committed = False
    try:
        control = _read_control_state(uid, db_client=db_client)
        applied_ids = apply_consolidation_decision(
            uid,
            decision=decision,
            pending_by_id={item.memory_id: item},
            control=control,
            run_id=f"{run_id}:retry-exhausted",
            now=now,
            db_client=db_client,
        )
    except Exception as review_exc:
        try:
            control = _read_control_state(uid, db_client=db_client)
            applied_ids = apply_consolidation_decision(
                uid,
                decision=decision,
                pending_by_id={item.memory_id: item},
                control=control,
                run_id=f"{run_id}:quarantine",
                now=now,
                db_client=db_client,
                quarantine=True,
            )
            quarantine_committed = bool(applied_ids)
        except Exception as quarantine_exc:
            report.decisions_skipped += 1
            if item.memory_id not in report.retryable_memory_ids:
                report.retryable_memory_ids.append(item.memory_id)
            _append_report_error(
                report,
                f"consolidation_terminal_route_failed:{type(review_exc).__name__}:{type(quarantine_exc).__name__}",
            )
            try:
                _transition_retry_state(
                    uid,
                    item,
                    status="retryable",
                    error_code=error_code,
                    now=now,
                    db_client=db_client,
                    expected_lease_owner=state.lease_owner,
                )
            except Exception as state_exc:
                _append_report_error(report, f"retry_state:transition_{type(state_exc).__name__}")
            return

    if not applied_ids:
        report.decisions_skipped += 1
        if item.memory_id not in report.retryable_memory_ids:
            report.retryable_memory_ids.append(item.memory_id)
        _append_report_error(report, "consolidation_terminal_route_failed:empty_apply")
        try:
            _transition_retry_state(
                uid,
                item,
                status="retryable",
                error_code=error_code,
                now=now,
                db_client=db_client,
                expected_lease_owner=state.lease_owner,
            )
        except Exception as state_exc:
            _append_report_error(report, f"retry_state:transition_{type(state_exc).__name__}")
        return

    report.decisions_applied += 1
    report.review_escalations += 1
    if item.memory_id not in report.review_memory_ids:
        report.review_memory_ids.append(item.memory_id)
    if item.memory_id not in batched_ids:
        batched_ids.append(item.memory_id)
    final_status: Literal["quarantined", "terminal_review"] = (
        "quarantined" if quarantine_committed else "terminal_review"
    )
    if quarantine_committed and item.memory_id not in report.quarantined_memory_ids:
        report.quarantined_memory_ids.append(item.memory_id)
    try:
        _transition_retry_state(
            uid,
            item,
            status=final_status,
            error_code=error_code,
            now=now,
            db_client=db_client,
            expected_lease_owner=state.lease_owner,
        )
    except Exception as exc:
        _append_report_error(report, f"retry_state:terminal_{type(exc).__name__}")
    record_fallback(
        component="other",
        from_mode="canonical_consolidation_retry",
        to_mode="canonical_consolidation_quarantine" if quarantine_committed else "canonical_review",
        reason="other",
        outcome="exhausted" if quarantine_committed else "recovered",
        log=logger,
    )


def _record_batch_failure(
    uid: str,
    items: List[MemoryItem],
    *,
    claimed_states: Dict[str, ConsolidationRetryState],
    error_code: str,
    report: ConsolidationReport,
    batched_ids: List[str],
    run_id: str,
    now: datetime,
    db_client: Any,
) -> None:
    safe_code = _safe_consolidation_failure_code(error_code)
    _append_report_error(report, safe_code)
    for item in items:
        state = claimed_states.get(item.memory_id)
        if state is None:
            _append_report_error(report, "retry_state:missing_claim")
            continue
        if state.attempt_count >= MAX_CONSOLIDATION_FAILURE_ATTEMPTS:
            _escalate_to_terminal_review(
                uid,
                item,
                state=state.model_copy(update={"last_error_code": safe_code}),
                report=report,
                batched_ids=batched_ids,
                run_id=run_id,
                now=now,
                db_client=db_client,
            )
            continue
        try:
            state = _transition_retry_state(
                uid,
                item,
                status="retryable",
                error_code=safe_code,
                now=now,
                db_client=db_client,
                expected_lease_owner=state.lease_owner,
            )
        except Exception as exc:
            _append_report_error(report, f"retry_state:release_{type(exc).__name__}")
            state = state.model_copy(update={"last_error_code": safe_code})
        if state.status == "quarantined":
            if item.memory_id not in report.quarantined_memory_ids:
                report.quarantined_memory_ids.append(item.memory_id)
            _append_report_error(report, f"consolidation_quarantined:{state.last_error_code}")
        elif state.status == "terminal_review":
            _append_report_error(report, f"consolidation_retry_exhausted:{state.last_error_code}")
        elif item.memory_id not in report.retryable_memory_ids:
            report.retryable_memory_ids.append(item.memory_id)
    record_fallback(
        component="other",
        from_mode="canonical_consolidation",
        to_mode="canonical_consolidation_retry",
        reason="other",
        outcome="degraded",
        log=logger,
    )


@transactional
def _release_deferred_retry_state_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
    item: MemoryItem,
    error_code: str,
    now: datetime,
    expected_lease_owner: str,
) -> ConsolidationRetryState:
    ref = db_client.document(_retry_state_document_path(uid, item))
    snapshot = ref.get(transaction=transaction)
    payload = _snapshot_payload(snapshot)
    if not payload:
        raise ValueError("consolidation retry state is missing")
    prior = ConsolidationRetryState.model_validate(payload)
    if (
        prior.uid != uid
        or prior.memory_id != item.memory_id
        or prior.source_item_revision != item.item_revision
        or prior.source_content_hash != item.content_hash
    ):
        raise ValueError("consolidation retry state identity mismatch")
    if prior.lease_owner != expected_lease_owner:
        raise ValueError("consolidation retry lease ownership changed")
    state = prior.model_copy(
        update={
            "attempt_count": max(prior.attempt_count - 1, 0),
            "status": "retryable",
            "last_error_code": error_code,
            "last_attempt_at": now,
            "lease_owner": None,
            "lease_expires_at": None,
        }
    )
    transaction.set(ref, state.model_dump(mode="python"))
    return state


def _record_deferred_batch_failure(
    uid: str,
    items: List[MemoryItem],
    *,
    claimed_states: Dict[str, ConsolidationRetryState],
    error_code: str,
    report: ConsolidationReport,
    now: datetime,
    db_client: Any,
) -> None:
    safe_code = _safe_consolidation_failure_code(error_code)
    _append_report_error(report, safe_code)
    for item in items:
        state = claimed_states.get(item.memory_id)
        if state is None or state.lease_owner is None:
            _append_report_error(report, "retry_state:missing_claim")
            continue
        try:
            transaction = db_client.transaction()
            _release_deferred_retry_state_transaction(
                transaction,
                db_client,
                uid,
                item,
                safe_code,
                now,
                state.lease_owner,
            )
        except Exception as exc:
            _append_report_error(report, f"retry_state:deferred_release_{type(exc).__name__}")
        if item.memory_id not in report.retryable_memory_ids:
            report.retryable_memory_ids.append(item.memory_id)


def run_canonical_consolidation(
    uid: str,
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    run_id: str,
    llm_invoke: Optional[Callable[[str], str]] = None,
    recurrence_signal_sink: Optional[Callable[..., int]] = None,
    attempt_lease_seconds: int = CONSOLIDATION_ATTEMPT_LEASE_SECONDS,
    result_guard: Optional[Callable[[], None]] = None,
) -> ConsolidationReport:
    """Batched consolidation entry point for one canonical user."""
    client: Any = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))

    if not consolidation_enabled():
        return ConsolidationReport(uid=uid, skipped_reason="consolidation_disabled")

    scan_cursor: Optional[ConsolidationScanCursor] = None
    try:
        scan_cursor = _read_scan_cursor(uid, db_client=client)
    except Exception as exc:
        logger.warning(
            "consolidation_scan_cursor_invalid uid=%s reason=%s",
            uid,
            type(exc).__name__,
        )
        try:
            _clear_scan_cursor(uid, db_client=client)
        except Exception:
            pass
    cursor_values = (scan_cursor.captured_at, scan_cursor.memory_id) if scan_cursor is not None else None
    pending = list_pending_consolidation_items(
        uid,
        db_client=client,
        now=current_time,
        start_after=cursor_values,
    )
    if scan_cursor is not None and not pending:
        _clear_scan_cursor(uid, db_client=client)
        scan_cursor = None
        pending = list_pending_consolidation_items(uid, db_client=client, now=current_time)
    control = _read_control_state(uid, db_client=client)
    trigger = consolidation_trigger_reason(
        pending_count=len(pending),
    )
    if trigger is None:
        return ConsolidationReport(
            uid=uid,
            skipped_reason="consolidation_not_due",
            pending_count=len(pending),
            last_consolidation_run_at=control.last_consolidation_run_at,
        )

    report = ConsolidationReport(
        uid=uid,
        trigger_reason=trigger,
        pending_count=len(pending),
        last_consolidation_run_at=control.last_consolidation_run_at,
    )
    if not pending:
        return report

    batch_cap = consolidation_batch_cap()
    max_batches = max_consolidation_batches_per_pass()
    batches_run = 0
    batched_ids: List[str] = []
    watermark_blocked = False
    offset = 0
    recurrence_signals_by_id: Dict[str, CanonicalRecurrenceSignal] = {}
    attempt_lease_owner = f"{run_id}:{uuid.uuid4().hex}"

    while offset < len(pending):
        if batches_run >= max_batches:
            break
        first_item = pending[offset]
        first_retry_state: Optional[ConsolidationRetryState] = None
        first_retry_state_read = False
        try:
            first_retry_state = _read_retry_state(uid, first_item, db_client=client)
            first_retry_state_read = True
        except Exception:
            # Isolate unreadable retry state so one malformed operational row
            # cannot make the loop skip unrelated items in the same base batch.
            pass
        effective_batch_cap = 1 if first_retry_state is not None or not first_retry_state_read else batch_cap
        pending_batch = pending[offset : offset + effective_batch_cap]
        if not pending_batch:
            break

        llm_pending_batch: List[MemoryItem] = []
        claimed_states: Dict[str, ConsolidationRetryState] = {}
        for item in pending_batch:
            try:
                retry_state = (
                    first_retry_state
                    if item.memory_id == first_item.memory_id and first_retry_state_read
                    else _read_retry_state(uid, item, db_client=client)
                )
            except Exception as exc:
                watermark_blocked = True
                _append_report_error(report, f"retry_state:read_{type(exc).__name__}")
                continue
            if retry_state is not None and retry_state.status == "terminal_review":
                watermark_blocked = True
                if item.memory_id not in report.review_memory_ids:
                    report.review_memory_ids.append(item.memory_id)
                _append_report_error(report, "consolidation_terminal_review_source_still_pending")
                continue
            if retry_state is not None and retry_state.status == "quarantined":
                watermark_blocked = True
                if item.memory_id not in report.quarantined_memory_ids:
                    report.quarantined_memory_ids.append(item.memory_id)
                _append_report_error(report, f"consolidation_quarantined:{retry_state.last_error_code}")
                continue
            if (
                retry_state is not None
                and retry_state.attempt_count >= MAX_CONSOLIDATION_FAILURE_ATTEMPTS
                and (
                    retry_state.status == "retryable"
                    or retry_state.lease_expires_at is None
                    or retry_state.lease_expires_at <= current_time
                )
            ):
                watermark_blocked = True
                _escalate_to_terminal_review(
                    uid,
                    item,
                    state=retry_state,
                    report=report,
                    batched_ids=batched_ids,
                    run_id=run_id,
                    now=current_time,
                    db_client=client,
                )
                continue
            try:
                claimed_state, claimed = _claim_retry_state(
                    uid,
                    item,
                    lease_owner=attempt_lease_owner,
                    now=current_time,
                    db_client=client,
                    lease_seconds=attempt_lease_seconds,
                )
            except Exception as exc:
                watermark_blocked = True
                _append_report_error(report, f"retry_state:claim_{type(exc).__name__}")
                continue
            if not claimed:
                watermark_blocked = True
                if claimed_state.status == "terminal_review":
                    if item.memory_id not in report.review_memory_ids:
                        report.review_memory_ids.append(item.memory_id)
                    _append_report_error(report, "consolidation_terminal_review_source_still_pending")
                elif claimed_state.status == "quarantined":
                    if item.memory_id not in report.quarantined_memory_ids:
                        report.quarantined_memory_ids.append(item.memory_id)
                    _append_report_error(
                        report,
                        f"consolidation_quarantined:{claimed_state.last_error_code}",
                    )
                elif (
                    claimed_state.status == "in_progress"
                    and claimed_state.lease_expires_at is not None
                    and claimed_state.lease_expires_at > current_time
                ):
                    if item.memory_id not in report.retryable_memory_ids:
                        report.retryable_memory_ids.append(item.memory_id)
                    _append_report_error(report, "consolidation_attempt_leased")
                elif claimed_state.attempt_count >= MAX_CONSOLIDATION_FAILURE_ATTEMPTS:
                    _escalate_to_terminal_review(
                        uid,
                        item,
                        state=claimed_state,
                        report=report,
                        batched_ids=batched_ids,
                        run_id=run_id,
                        now=current_time,
                        db_client=client,
                    )
                else:
                    if item.memory_id not in report.retryable_memory_ids:
                        report.retryable_memory_ids.append(item.memory_id)
                    _append_report_error(report, "consolidation_attempt_leased")
                continue
            claimed_states[item.memory_id] = claimed_state
            llm_pending_batch.append(item)

        if not llm_pending_batch:
            offset += effective_batch_cap
            continue

        try:
            context = gather_consolidation_candidates(uid, llm_pending_batch, db_client=client)
        except Exception as exc:
            watermark_blocked = True
            logger.warning(
                "consolidation_candidate_hydration_blocked uid=%s reason=%s",
                uid,
                type(exc).__name__,
            )
            _record_batch_failure(
                uid,
                llm_pending_batch,
                claimed_states=claimed_states,
                error_code=f"candidate_hydration:{type(exc).__name__}",
                report=report,
                batched_ids=batched_ids,
                run_id=run_id,
                now=current_time,
                db_client=client,
            )
            offset += effective_batch_cap
            continue
        try:
            agent_batch = invoke_consolidation_agent(context, llm_invoke=llm_invoke)
        except (PromotionFlexControlChanged, PromotionFlexDeferred) as exc:
            watermark_blocked = True
            _record_deferred_batch_failure(
                uid,
                llm_pending_batch,
                claimed_states=claimed_states,
                error_code=f"flex_deferred:{type(exc).__name__}",
                report=report,
                now=current_time,
                db_client=client,
            )
            offset += effective_batch_cap
            continue
        batches_run += 1
        pending_by_id = {item.memory_id: item for item in llm_pending_batch}

        output_error = _validate_agent_batch(context, agent_batch)
        if output_error is not None:
            watermark_blocked = True
            logger.warning(
                "consolidation_output_blocked uid=%s reason=%s",
                uid,
                output_error,
            )
            _record_batch_failure(
                uid,
                llm_pending_batch,
                claimed_states=claimed_states,
                error_code=output_error,
                report=report,
                batched_ids=batched_ids,
                run_id=run_id,
                now=current_time,
                db_client=client,
            )
            offset += effective_batch_cap
            continue

        if result_guard is not None:
            try:
                result_guard()
            except PromotionFlexControlChanged as exc:
                watermark_blocked = True
                _record_deferred_batch_failure(
                    uid,
                    llm_pending_batch,
                    claimed_states=claimed_states,
                    error_code=f"flex_deferred:{type(exc).__name__}",
                    report=report,
                    now=current_time,
                    db_client=client,
                )
                offset += effective_batch_cap
                continue

        for signal in agent_batch.recurrence_signals:
            recurrence_signals_by_id[signal.stable_loop_key] = signal
        if recurrence_signal_sink is not None and agent_batch.recurrence_signals:
            try:
                recurrence_signal_sink(
                    uid,
                    agent_batch.recurrence_signals,
                    firestore_client=client,
                )
            except Exception as exc:
                watermark_blocked = True
                logger.warning(
                    "consolidation_recurrence_handoff_blocked uid=%s reason=%s",
                    uid,
                    type(exc).__name__,
                )
                _record_batch_failure(
                    uid,
                    llm_pending_batch,
                    claimed_states=claimed_states,
                    error_code=f"recurrence_handoff:{type(exc).__name__}",
                    report=report,
                    batched_ids=batched_ids,
                    run_id=run_id,
                    now=current_time,
                    db_client=client,
                )
                offset += effective_batch_cap
                continue

        ordered_decisions = sorted(agent_batch.decisions, key=lambda decision: decision.route != "promote")
        batch_apply_failed = False
        for decision_index, decision in enumerate(ordered_decisions):
            control = _read_control_state(uid, db_client=client)
            try:
                applied_ids = apply_consolidation_decision(
                    uid,
                    decision=decision,
                    pending_by_id=pending_by_id,
                    control=control,
                    run_id=run_id,
                    now=current_time,
                    db_client=client,
                )
            except (ConsolidationApplySkipped, MissingMemoryDocument) as exc:
                report.decisions_skipped += 1
                watermark_blocked = True
                logger.warning(
                    "consolidation_decision_blocked uid=%s source=%s reason=%s",
                    uid,
                    sanitize_pii(decision.source_memory_id),
                    sanitize_pii(str(exc)),
                )
                unresolved_ids = {
                    pending_decision.source_memory_id for pending_decision in ordered_decisions[decision_index:]
                }
                unresolved_items = [item for item in llm_pending_batch if item.memory_id in unresolved_ids]
                _record_batch_failure(
                    uid,
                    unresolved_items,
                    claimed_states=claimed_states,
                    error_code=f"apply_blocked:{type(exc).__name__}",
                    report=report,
                    batched_ids=batched_ids,
                    run_id=run_id,
                    now=current_time,
                    db_client=client,
                )
                batch_apply_failed = True
                break
            if applied_ids:
                report.decisions_applied += 1
                if decision.source_memory_id not in batched_ids:
                    batched_ids.append(decision.source_memory_id)
                claimed_state = claimed_states[decision.source_memory_id]
                try:
                    _delete_retry_state(
                        uid,
                        pending_by_id[decision.source_memory_id],
                        expected_lease_owner=claimed_state.lease_owner or "",
                        db_client=client,
                    )
                except Exception as exc:
                    _append_report_error(report, f"retry_state:cleanup_{type(exc).__name__}")
                if decision.route == "promote":
                    report.promoted_memory_ids.append(decision.source_memory_id)
                elif decision.route == "review":
                    report.review_memory_ids.append(decision.source_memory_id)
                    report.review_escalations += 1
                elif decision.route == "reject":
                    report.rejected_memory_ids.append(decision.source_memory_id)
                else:
                    report.archived_memory_ids.append(decision.source_memory_id)
                report.superseded_memory_ids.extend(decision.supersedes)

        if batch_apply_failed:
            offset += effective_batch_cap
            continue
        offset += effective_batch_cap

    report.batched_memory_ids = list(dict.fromkeys(batched_ids))
    report.watermark_blocked = watermark_blocked
    report.recurrence_signals = list(recurrence_signals_by_id.values())

    try:
        if watermark_blocked and pending:
            _persist_scan_cursor(uid, pending[-1], now=current_time, db_client=client)
        elif scan_cursor is not None:
            _clear_scan_cursor(uid, db_client=client)
    except Exception as exc:
        _append_report_error(report, f"scan_cursor:{type(exc).__name__}")

    if batched_ids and not watermark_blocked:
        updated_control = _read_control_state(uid, db_client=client).model_copy(
            update={
                "last_consolidation_run_at": current_time,
                "updated_at": current_time,
            }
        )
        _persist_control_state(updated_control, db_client=client)
        report.last_consolidation_run_at = current_time
    else:
        report.last_consolidation_run_at = control.last_consolidation_run_at
    return report
