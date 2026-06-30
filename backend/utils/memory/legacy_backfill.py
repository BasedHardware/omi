"""NON-DESTRUCTIVE legacy → canonical long-term backfill (WS-C).

Safety contract (locked directive):
- **COPY only** — reads legacy ``users/{uid}/memories`` via ``get_non_filtered_memories``
  (read-only); applies the same active-row filter as ``get_memories`` in-process. Writes canonical
  ``memory_items`` via ``apply_long_term_patch_firestore``. Legacy rows are **never** deleted,
  updated, or invalidated by this module.
- **Idempotent (Q4)** — deterministic canonical ``memory_id`` per legacy row (hash of uid + legacy id).
- **Resumable** — per-user checkpoint on ``memory_state/apply_control`` (``legacy_backfill_*`` fields).
- **Dry-run** — reports intended writes without touching canonical or legacy stores.
- **Count-verified** — reconciles active legacy source count vs backfilled long_term destination ids.

Admin-only: invoke explicitly per uid; no cron, no auto-run.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence

from database._client import db as default_db_client
from database.memories import get_non_filtered_memories
from database.memory_collections import MemoryCollections
from database.memory_apply_store import apply_long_term_patch_firestore
from models.memory_domain import (
    MemoryLayer as DomainMemoryLayer,
    MemoryProcessingState,
    assert_legal_state,
    physical_status_to_record_status,
)
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_apply import ApplyStatus, MemoryControlState
from models.memory_contracts import DurablePatchDecision, LifecycleState, deterministic_contract_id
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.product_memory import MemoryItemStatus, MemoryLayer, ProcessingState, MemoryItem
from utils.memory.atom_keyword_index import sync_atom_keyword_index_for_item
from utils.memory.canonical_memory_adapter import extraction_memory_id
from utils.memory.canonical_vector_sync import sync_canonical_memory_vector
from utils.memory.memory_system import MemorySystem, resolve_memory_system
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 50
LEGACY_SCAN_PAGE_SIZE = 500
COHORT_GATE_REASON = "cohort_gate: uid not in CANONICAL_MEMORY_USERS (use allow_admin_override=True to bypass)"
COHORT_OVERRIDE_ACK_REQUIRED_REASON = (
    "cohort_gate: allow_admin_override requires acknowledge_non_canonical_uid=True "
    "(CLI: --i-understand-uid-not-whitelisted)"
)


class BackfillCohortGateError(ValueError):
    """Raised when backfill is invoked for a uid outside the canonical cohort."""


class LegacyBackfillBucket(str, Enum):
    reviewed_long_term = "reviewed_long_term"
    manual_required_promotion = "manual_required_promotion"
    profile_required_promotion = "profile_required_promotion"
    archive_review = "archive_review"
    hold_noise = "hold_noise"
    hold_sensitive = "hold_sensitive"


WRITABLE_LEGACY_BACKFILL_BUCKETS = {
    LegacyBackfillBucket.reviewed_long_term,
    LegacyBackfillBucket.manual_required_promotion,
    LegacyBackfillBucket.profile_required_promotion,
}

_DOWNLOADS_PATTERN = re.compile(
    r"(?:\blocal downloads include\b|\bdownloads include\b|~/downloads\b|/downloads/)", re.I
)
_FOCUS_PATTERN = re.compile(r"^\s*focused on\b", re.I)
_IMPERATIVE_PATTERN = re.compile(
    r"^\s*(address|review|persist|seed|run|make|add|fix|check|confirm|use|build|deploy|merge|push)\b",
    re.I,
)
_SENSITIVE_PATTERN = re.compile(
    r"\b(api[-_ ]?key|secret|token|password|credential|private key|access key|bearer|oauth|session cookie)\b",
    re.I,
)
_PROFILE_PATTERN = re.compile(
    r"\b(user|david|david zhang|the user)\b.*\b("
    r"prefers|uses|wants|does not want|avoids|follows|works|is|has|operates|trusts|"
    r"primarily|company|team|project|building|likes|dislikes"
    r")\b",
    re.I,
)


@dataclass(frozen=True)
class BackfillReport:
    uid: str
    dry_run: bool
    source_count: int
    intended_count: int
    written_count: int
    skipped_already_present: int
    skipped_both_store_duplicate: int
    skipped_semantic_duplicate: int
    destination_count: int
    verified: bool
    discrepancy: Optional[str] = None
    resumed_from_index: int = 0
    completed: bool = False
    legacy_rows_touched: int = 0
    vector_sync_failures: int = 0
    cohort_gated: bool = False
    errors: List[str] = field(default_factory=list)
    selected_bucket: Optional[str] = None
    bucket_counts: Dict[str, int] = field(default_factory=dict)
    bucket_samples: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    skipped_bucket_not_selected: int = 0
    skipped_bucket_not_writable: int = 0


def legacy_backfill_memory_id(*, uid: str, legacy_memory_id: str) -> str:
    """Q4 hash-derived neutral canonical id for one legacy row."""
    return (
        "mem_"
        + deterministic_contract_id(
            "legacy-backfill-memory",
            {"uid": uid, "legacy_memory_id": legacy_memory_id},
        )[:32]
    )


def legacy_backfill_idempotency_key(*, uid: str, legacy_memory_id: str) -> str:
    return deterministic_contract_id(
        "legacy-backfill-idempotency",
        {"uid": uid, "legacy_memory_id": legacy_memory_id},
    )


def legacy_source_fingerprint(legacy_rows: Sequence[Dict[str, Any]]) -> str:
    legacy_ids = sorted(row.get("id") or "" for row in legacy_rows)
    return deterministic_contract_id("legacy-backfill-source-set", {"legacy_ids": legacy_ids})


def assert_canonical_cohort_for_backfill(
    uid: str,
    *,
    allow_admin_override: bool = False,
    acknowledge_non_canonical_uid: bool = False,
    operator_context: Optional[str] = None,
    db_client=None,
) -> None:
    """Require ``uid`` to be in the canonical whitelist before backfill runs."""
    if allow_admin_override:
        if not acknowledge_non_canonical_uid:
            raise BackfillCohortGateError(COHORT_OVERRIDE_ACK_REQUIRED_REASON)
        memory_system = resolve_memory_system(uid, db_client=db_client)
        if memory_system != MemorySystem.CANONICAL:
            logger.warning(
                "legacy backfill cohort override",
                extra={
                    "event": "legacy_backfill_cohort_override",
                    "uid": uid,
                    "memory_system": memory_system.value,
                    "operator_context": sanitize(operator_context or "unspecified"),
                },
            )
        return
    if resolve_memory_system(uid, db_client=db_client) != MemorySystem.CANONICAL:
        raise BackfillCohortGateError(COHORT_GATE_REASON)


def live_extraction_memory_id_for_legacy_row(*, uid: str, legacy_row: dict) -> Optional[str]:
    """Canonical id used by live extraction for the same conversation content, if derivable."""
    content = (legacy_row.get("content") or "").strip()
    if not content:
        return None
    source_id = legacy_row.get("conversation_id") or legacy_row.get("memory_id") or legacy_row.get("id")
    if not source_id:
        return None
    return extraction_memory_id(uid=uid, source_id=source_id, content=content)


def semantic_materialization_key(*, uid: str, legacy_row: dict) -> Optional[str]:
    """In-run dedup key: live extraction id when derivable, else normalized (source_id, content)."""
    content = (legacy_row.get("content") or "").strip()
    if not content:
        return None
    live_id = live_extraction_memory_id_for_legacy_row(uid=uid, legacy_row=legacy_row)
    if live_id is not None:
        return f"live:{live_id}"
    source_id = legacy_row.get("conversation_id") or legacy_row.get("memory_id") or legacy_row.get("id")
    if not source_id:
        return None
    return f"semantic:{source_id}:{content}"


def _load_canonical_item(uid: str, memory_id: str, *, db_client) -> Optional[MemoryItem]:
    path = f"{MemoryCollections(uid=uid).memory_items}/{memory_id}"
    snapshot = db_client.document(path).get()
    if not getattr(snapshot, "exists", False):
        return None
    return MemoryItem.model_validate(snapshot.to_dict() or {})


def _is_active_processed_canonical_item(item: MemoryItem) -> bool:
    return item.status == MemoryItemStatus.active and item.processing_state == ProcessingState.processed


def _is_active_processed_backfill_destination(item: MemoryItem) -> bool:
    return _is_active_processed_canonical_item(item) and item.tier == MemoryLayer.long_term


def both_store_canonical_duplicate_exists(*, uid: str, legacy_row: dict, db_client) -> bool:
    """True when a live canonical write already materialized this legacy row under a different id."""
    live_id = live_extraction_memory_id_for_legacy_row(uid=uid, legacy_row=legacy_row)
    if live_id is None:
        return False
    existing = _load_canonical_item(uid, live_id, db_client=db_client)
    return existing is not None and _is_active_processed_canonical_item(existing)


def _coerce_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_optional_legacy_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _coerce_aware_utc(value)
    if isinstance(value, str):
        try:
            return _coerce_aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def is_active_legacy_row(row: dict) -> bool:
    """Mirror ``get_memories`` default semantics: active, non-user-rejected rows only."""
    return row.get("user_review") is not False and row.get("invalid_at") is None


def classify_legacy_backfill_bucket(row: dict) -> LegacyBackfillBucket:
    """Route a legacy memory into the safest first-pass migration bucket."""
    content = (row.get("content") or "").strip()
    if not content:
        return LegacyBackfillBucket.hold_noise
    if _SENSITIVE_PATTERN.search(content):
        return LegacyBackfillBucket.hold_sensitive
    if _DOWNLOADS_PATTERN.search(content) or _FOCUS_PATTERN.search(content) or _IMPERATIVE_PATTERN.search(content):
        return LegacyBackfillBucket.hold_noise
    if row.get("manually_added") is True or row.get("category") == "manual":
        return LegacyBackfillBucket.manual_required_promotion
    if _PROFILE_PATTERN.search(content):
        if row.get("user_review") is True:
            return LegacyBackfillBucket.reviewed_long_term
        return LegacyBackfillBucket.profile_required_promotion
    return LegacyBackfillBucket.archive_review


def _legacy_bucket_sample(row: dict) -> Dict[str, Any]:
    content = " ".join((row.get("content") or "").strip().split())
    if len(content) > 160:
        content = f"{content[:157]}..."
    return {
        "id": row.get("id"),
        "category": row.get("category"),
        "manually_added": row.get("manually_added"),
        "user_review": row.get("user_review"),
        "created_at": _coerce_optional_legacy_datetime(row.get("created_at")),
        "content": content,
    }


def _bucket_counts_and_samples(
    rows: Sequence[dict],
    *,
    sample_size: int = 5,
) -> tuple[Dict[str, int], Dict[str, List[Dict[str, Any]]]]:
    counts = {bucket.value: 0 for bucket in LegacyBackfillBucket}
    samples: Dict[str, List[Dict[str, Any]]] = {bucket.value: [] for bucket in LegacyBackfillBucket}
    for row in rows:
        bucket = classify_legacy_backfill_bucket(row)
        counts[bucket.value] += 1
        if len(samples[bucket.value]) < sample_size:
            samples[bucket.value].append(_legacy_bucket_sample(row))
    return counts, {bucket: sample_rows for bucket, sample_rows in samples.items() if sample_rows}


def _fetch_active_legacy_memories(
    uid: str,
    *,
    get_non_filtered_memories_fn: Callable[..., List[dict]],
    scan_page_size: int = LEGACY_SCAN_PAGE_SIZE,
) -> List[dict]:
    """Read-only scan of active legacy memories (never writes).

    Paginates over the raw Firestore page from ``get_non_filtered_memories`` so
    ``len(page) < page_size`` reliably signals end-of-data even when many rows in
    a page are inactive and filtered out here.
    """
    all_rows: List[dict] = []
    offset = 0
    page_size = scan_page_size
    while True:
        page = get_non_filtered_memories_fn(uid, limit=page_size, offset=offset)
        if not page:
            break
        for row in page:
            if is_active_legacy_row(row):
                all_rows.append(row)
        if len(page) < page_size:
            break
        offset += page_size
    return sorted(all_rows, key=lambda row: row.get("id") or "")


def _read_control_state(uid: str, *, db_client, create_if_missing: bool = True) -> MemoryControlState:
    collections = MemoryCollections(uid=uid)
    ref = db_client.document(collections.memory_apply_control_state)
    snapshot = ref.get()
    if getattr(snapshot, "exists", False):
        return MemoryControlState(**(snapshot.to_dict() or {}))
    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    if create_if_missing:
        ref.set(control.model_dump(mode="json"))
    return control


def _persist_control_state(control: MemoryControlState, *, db_client) -> None:
    db_client.document(MemoryCollections(uid=control.uid).memory_apply_control_state).set(
        control.model_dump(mode="json")
    )


def _legacy_evidence_id(*, uid: str, legacy_memory_id: str, index: int) -> str:
    return (
        "ev_lb_"
        + deterministic_contract_id(
            "legacy-backfill-evidence",
            {"uid": uid, "legacy_memory_id": legacy_memory_id, "index": index},
        )[:28]
    )


def _build_backfill_evidence(
    *,
    uid: str,
    legacy_row: dict,
    index: int,
) -> MemoryEvidence:
    legacy_id = legacy_row.get("id") or f"legacy_{index}"
    conversation_id = legacy_row.get("conversation_id") or legacy_row.get("memory_id")
    raw_evidence = legacy_row.get("evidence") or []
    if raw_evidence and isinstance(raw_evidence[0], dict) and raw_evidence[0].get("evidence_id"):
        first = raw_evidence[0]
        source_id = first.get("source_id") or conversation_id or legacy_id
        source_type = first.get("source_type") or ("conversation" if conversation_id else "legacy_memory")
        return MemoryEvidence(
            evidence_id=first["evidence_id"],
            source_type=source_type,
            source_id=source_id,
            source_version="v1",
            conversation_id=conversation_id if source_type == "conversation" else None,
            artifact_preservation=ArtifactPreservationState.preserved,
        )

    source_id = conversation_id or legacy_id
    source_type = "conversation" if conversation_id else "legacy_memory"
    return MemoryEvidence(
        evidence_id=_legacy_evidence_id(uid=uid, legacy_memory_id=legacy_id, index=index),
        source_type=source_type,
        source_id=source_id,
        source_version="v1",
        conversation_id=conversation_id if source_type == "conversation" else None,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _persist_evidence(uid: str, evidence: MemoryEvidence, *, db_client) -> None:
    collections = MemoryCollections(uid=uid)
    path = f"{collections.memory_evidence}/{evidence.evidence_id}"
    ref = db_client.document(path)
    if not ref.get().exists:
        ref.set(evidence.model_dump(mode="json"))


def _ensure_backfill_operation(
    *,
    uid: str,
    legacy_row: dict,
    canonical_memory_id: str,
    control: MemoryControlState,
    run_id: str,
    evidence_ids: List[str],
    db_client,
    bucket: Optional[LegacyBackfillBucket] = None,
) -> MemoryOperation:
    legacy_id = legacy_row.get("id") or canonical_memory_id
    content = (legacy_row.get("content") or "").strip()
    source_packet_id = f"legacy_backfill_{legacy_id}"
    if bucket is not None:
        source_packet_id = f"legacy_backfill_{bucket.value}_{legacy_id}"
    logical_payload = {
        "decision": DurablePatchDecision.add.value,
        "memory_text": content,
        "result_status": LifecycleState.active.value,
    }
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id=source_packet_id,
        target_memory_id=None,
        evidence_ids=evidence_ids,
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    op_path = f"{MemoryCollections(uid=uid).memory_operations}/{operation.operation_id}"
    op_ref = db_client.document(op_path)
    if not op_ref.get().exists:
        op_ref.set(operation.model_dump(mode="json"))
    return operation


def _apply_one_legacy_row(
    *,
    uid: str,
    legacy_row: dict,
    index: int,
    control: MemoryControlState,
    run_id: str,
    db_client,
    bucket: Optional[LegacyBackfillBucket] = None,
) -> tuple[MemoryControlState, bool, Optional[str], bool]:
    """Write one canonical item. Returns (control, written, skip_reason, vector_sync_failed)."""
    legacy_id = legacy_row.get("id") or f"legacy_{index}"
    content = (legacy_row.get("content") or "").strip()
    if not content:
        return control, False, "empty_content", False
    if bucket is not None and bucket not in WRITABLE_LEGACY_BACKFILL_BUCKETS:
        return control, False, "bucket_not_writable", False

    canonical_memory_id = legacy_backfill_memory_id(uid=uid, legacy_memory_id=legacy_id)
    existing = _load_canonical_item(uid, canonical_memory_id, db_client=db_client)
    if existing is not None and _is_active_processed_canonical_item(existing):
        return control, False, "already_present", False

    if both_store_canonical_duplicate_exists(uid=uid, legacy_row=legacy_row, db_client=db_client):
        return control, False, "both_store_duplicate", False

    evidence = _build_backfill_evidence(uid=uid, legacy_row=legacy_row, index=index)
    _persist_evidence(uid, evidence, db_client=db_client)

    operation = _ensure_backfill_operation(
        uid=uid,
        legacy_row=legacy_row,
        canonical_memory_id=canonical_memory_id,
        control=control,
        run_id=run_id,
        evidence_ids=[evidence.evidence_id],
        db_client=db_client,
        bucket=bucket,
    )

    idempotency_key = legacy_backfill_idempotency_key(uid=uid, legacy_memory_id=legacy_id)
    initial_tier = MemoryLayer.long_term
    user_asserted = False
    promotion = None
    captured_at = None
    updated_at = None
    expires_at = None
    if bucket is not None:
        initial_tier = (
            MemoryLayer.long_term if bucket == LegacyBackfillBucket.reviewed_long_term else MemoryLayer.short_term
        )
        user_asserted = bucket == LegacyBackfillBucket.manual_required_promotion
        now = datetime.now(timezone.utc)
        captured_at = _coerce_optional_legacy_datetime(legacy_row.get("created_at")) or now
        updated_at = _coerce_optional_legacy_datetime(legacy_row.get("updated_at")) or captured_at
        if updated_at < captured_at:
            updated_at = captured_at
        expires_at = now + timedelta(days=30) if initial_tier == MemoryLayer.short_term else None
        promotion = {
            "source_surface": "legacy_backfill",
            "migration_strategy": "bucketed_legacy_backfill",
            "bucket": bucket.value,
            "legacy_memory_id": legacy_id,
            "legacy_created_at": captured_at.isoformat(),
            "legacy_updated_at": updated_at.isoformat(),
        }
        if initial_tier == MemoryLayer.short_term:
            promotion.update(
                {
                    "required": True,
                    "status": "pending",
                    "reason": "legacy_migration",
                    "attempt_count": 0,
                }
            )

    patch_payload = {
        "patch_id": f"patch_lb_{idempotency_key[:24]}",
        "packet_id": (
            f"legacy_backfill_{bucket.value}_{legacy_id}" if bucket is not None else f"legacy_backfill_{legacy_id}"
        ),
        "run_id": run_id,
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        "decision": DurablePatchDecision.add.value,
        "result_status": LifecycleState.active.value,
        "evidence_ids": [evidence.evidence_id],
        "new_memory_id": canonical_memory_id,
        "memory_text": content,
        "confidence": "medium",
        "relationship_to_user": "self",
        "initial_tier": initial_tier.value,
        "user_asserted": user_asserted,
    }
    if promotion is not None:
        patch_payload["promotion"] = promotion
        patch_payload["captured_at"] = captured_at.isoformat() if captured_at else None
        patch_payload["updated_at"] = updated_at.isoformat() if updated_at else None
        if expires_at is not None:
            patch_payload["expires_at"] = expires_at.isoformat()

    result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        patch_payload=patch_payload,
        db_client=db_client,
    )
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(f"legacy backfill apply failed for {legacy_id}: {result.status} ({result.reason})")

    item = result.memory_items[0] if result.memory_items else None
    if item is None and result.status == ApplyStatus.idempotent_skip:
        snapshot = db_client.document(f"{MemoryCollections(uid=uid).memory_items}/{canonical_memory_id}").get()
        if getattr(snapshot, "exists", False):
            item = MemoryItem(**(snapshot.to_dict() or {}))

    vector_sync_failed = False

    def _record_vector_sync_failure() -> None:
        nonlocal vector_sync_failed
        vector_sync_failed = True

    if item is not None:
        assert_legal_state(
            DomainMemoryLayer(item.tier.value),
            physical_status_to_record_status(item.status.value),
            MemoryProcessingState(item.processing_state.value),
        )
        sync_atom_keyword_index_for_item(item, db_client=db_client)
        sync_canonical_memory_vector(item, on_hard_failure=_record_vector_sync_failure)

    written = result.status == ApplyStatus.committed
    return result.control_state, written, None if written else "idempotent_skip", vector_sync_failed


def _legacy_row_has_canonical_destination(
    *,
    uid: str,
    legacy_row: dict,
    items_by_id: Dict[str, MemoryItem],
) -> bool:
    legacy_id = legacy_row.get("id") or ""
    content = (legacy_row.get("content") or "").strip()
    if not content:
        return False

    backfill_id = legacy_backfill_memory_id(uid=uid, legacy_memory_id=legacy_id)
    backfill_item = items_by_id.get(backfill_id)
    if backfill_item is not None and _is_active_processed_backfill_destination(backfill_item):
        return True

    live_id = live_extraction_memory_id_for_legacy_row(uid=uid, legacy_row=legacy_row)
    if live_id is None:
        return False
    live_item = items_by_id.get(live_id)
    return live_item is not None and _is_active_processed_canonical_item(live_item)


def _legacy_row_has_any_canonical_destination(
    *,
    uid: str,
    legacy_row: dict,
    items_by_id: Dict[str, MemoryItem],
) -> bool:
    legacy_id = legacy_row.get("id") or ""
    content = (legacy_row.get("content") or "").strip()
    if not content:
        return False

    backfill_id = legacy_backfill_memory_id(uid=uid, legacy_memory_id=legacy_id)
    backfill_item = items_by_id.get(backfill_id)
    if backfill_item is not None and _is_active_processed_canonical_item(backfill_item):
        return True

    live_id = live_extraction_memory_id_for_legacy_row(uid=uid, legacy_row=legacy_row)
    if live_id is None:
        return False
    live_item = items_by_id.get(live_id)
    return live_item is not None and _is_active_processed_canonical_item(live_item)


def _count_any_destination_backfill_items(
    uid: str,
    legacy_rows: Sequence[dict],
    *,
    db_client,
) -> int:
    if not legacy_rows:
        return 0
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=db_client)
    items_by_id = {item.memory_id: item for item in items}
    return sum(
        1
        for row in legacy_rows
        if _legacy_row_has_any_canonical_destination(uid=uid, legacy_row=row, items_by_id=items_by_id)
    )


def _count_destination_backfill_items(
    uid: str,
    legacy_rows: Sequence[dict],
    *,
    db_client,
) -> int:
    if not legacy_rows:
        return 0
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=db_client)
    items_by_id = {item.memory_id: item for item in items}
    count = 0
    for row in legacy_rows:
        if _legacy_row_has_canonical_destination(uid=uid, legacy_row=row, items_by_id=items_by_id):
            count += 1
    return count


def reconcile_backfill_counts(
    uid: str,
    legacy_rows: Sequence[dict],
    *,
    db_client=None,
) -> tuple[int, int, bool, Optional[str]]:
    """Return (source_count, destination_count, verified, discrepancy)."""
    client = db_client if db_client is not None else default_db_client
    eligible_rows = [row for row in legacy_rows if (row.get("content") or "").strip()]
    source_count = len(eligible_rows)
    destination_count = _count_destination_backfill_items(uid, eligible_rows, db_client=client)
    verified = source_count == destination_count
    discrepancy = None
    if not verified:
        discrepancy = f"source={source_count} destination={destination_count}"
    return source_count, destination_count, verified, discrepancy


def _coerce_legacy_backfill_bucket(value: LegacyBackfillBucket | str | None) -> Optional[LegacyBackfillBucket]:
    if value is None or isinstance(value, LegacyBackfillBucket):
        return value
    return LegacyBackfillBucket(value)


def _cohort_gated_report(uid: str, *, dry_run: bool, reason: str = COHORT_GATE_REASON) -> BackfillReport:
    return BackfillReport(
        uid=uid,
        dry_run=dry_run,
        source_count=0,
        intended_count=0,
        written_count=0,
        skipped_already_present=0,
        skipped_both_store_duplicate=0,
        skipped_semantic_duplicate=0,
        destination_count=0,
        verified=False,
        cohort_gated=True,
        errors=[reason],
    )


def backfill_user_bucketed(
    uid: str,
    *,
    bucket: LegacyBackfillBucket | str | None = None,
    dry_run: bool = True,
    allow_admin_override: bool = False,
    acknowledge_non_canonical_uid: bool = False,
    operator_context: Optional[str] = None,
    db_client=None,
    get_non_filtered_memories_fn: Callable[..., List[dict]] = get_non_filtered_memories,
    run_id: Optional[str] = None,
) -> BackfillReport:
    """Bucket legacy rows and optionally apply one reviewed bucket.

    ``bucket=None`` is inventory-only. Real writes must name one bucket, and only
    buckets in ``WRITABLE_LEGACY_BACKFILL_BUCKETS`` are accepted.
    """
    selected_bucket = _coerce_legacy_backfill_bucket(bucket)
    client = db_client if db_client is not None else default_db_client
    try:
        assert_canonical_cohort_for_backfill(
            uid,
            allow_admin_override=allow_admin_override,
            acknowledge_non_canonical_uid=acknowledge_non_canonical_uid,
            operator_context=operator_context,
            db_client=client,
        )
    except BackfillCohortGateError as exc:
        report = _cohort_gated_report(uid, dry_run=dry_run, reason=str(exc))
        return report

    effective_run_id = run_id or f"legacy_bucket_backfill_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    legacy_rows = _fetch_active_legacy_memories(uid, get_non_filtered_memories_fn=get_non_filtered_memories_fn)
    eligible_rows = [row for row in legacy_rows if (row.get("content") or "").strip()]
    bucket_counts, bucket_samples = _bucket_counts_and_samples(eligible_rows)

    selected_rows = [
        row
        for row in eligible_rows
        if selected_bucket is not None and classify_legacy_backfill_bucket(row) == selected_bucket
    ]
    skipped_bucket_not_selected = len(eligible_rows) - len(selected_rows) if selected_bucket is not None else 0
    selected_bucket_value = selected_bucket.value if selected_bucket is not None else None

    if selected_bucket is None:
        return BackfillReport(
            uid=uid,
            dry_run=True,
            source_count=len(eligible_rows),
            intended_count=sum(bucket_counts[bucket.value] for bucket in WRITABLE_LEGACY_BACKFILL_BUCKETS),
            written_count=0,
            skipped_already_present=0,
            skipped_both_store_duplicate=0,
            skipped_semantic_duplicate=0,
            destination_count=0,
            verified=False,
            completed=False,
            bucket_counts=bucket_counts,
            bucket_samples=bucket_samples,
        )

    if selected_bucket not in WRITABLE_LEGACY_BACKFILL_BUCKETS:
        return BackfillReport(
            uid=uid,
            dry_run=dry_run,
            source_count=len(eligible_rows),
            intended_count=0,
            written_count=0,
            skipped_already_present=0,
            skipped_both_store_duplicate=0,
            skipped_semantic_duplicate=0,
            destination_count=0,
            verified=True,
            completed=True,
            selected_bucket=selected_bucket_value,
            bucket_counts=bucket_counts,
            bucket_samples=bucket_samples,
            skipped_bucket_not_selected=skipped_bucket_not_selected,
            skipped_bucket_not_writable=len(selected_rows),
        )

    destination_count = _count_any_destination_backfill_items(uid, selected_rows, db_client=client)
    if dry_run:
        return BackfillReport(
            uid=uid,
            dry_run=True,
            source_count=len(eligible_rows),
            intended_count=max(0, len(selected_rows) - destination_count),
            written_count=0,
            skipped_already_present=0,
            skipped_both_store_duplicate=0,
            skipped_semantic_duplicate=0,
            destination_count=destination_count,
            verified=destination_count == len(selected_rows),
            discrepancy=(
                None
                if destination_count == len(selected_rows)
                else f"source={len(selected_rows)} destination={destination_count}"
            ),
            completed=False,
            selected_bucket=selected_bucket_value,
            bucket_counts=bucket_counts,
            bucket_samples=bucket_samples,
            skipped_bucket_not_selected=skipped_bucket_not_selected,
        )

    control = _read_control_state(uid, db_client=client)
    written_count = 0
    skipped_already_present = 0
    skipped_both_store_duplicate = 0
    skipped_semantic_duplicate = 0
    vector_sync_failures = 0
    errors: List[str] = []
    materialized_semantic_keys: set[str] = set()

    for index, legacy_row in enumerate(selected_rows):
        semantic_key = semantic_materialization_key(uid=uid, legacy_row=legacy_row)
        if semantic_key is not None and semantic_key in materialized_semantic_keys:
            skipped_semantic_duplicate += 1
            continue
        try:
            control, written, skip_reason, row_vector_sync_failed = _apply_one_legacy_row(
                uid=uid,
                legacy_row=legacy_row,
                index=index,
                control=control,
                run_id=effective_run_id,
                db_client=client,
                bucket=selected_bucket,
            )
            if written:
                written_count += 1
            elif skip_reason == "both_store_duplicate":
                skipped_both_store_duplicate += 1
            elif skip_reason in {"already_present", "idempotent_skip"}:
                skipped_already_present += 1
            if semantic_key is not None and skip_reason not in {"empty_content"}:
                materialized_semantic_keys.add(semantic_key)
            if row_vector_sync_failed:
                vector_sync_failures += 1
        except Exception as exc:
            logger.exception("bucketed legacy backfill failed for %s row %s", uid, legacy_row.get("id"))
            errors.append(f"{legacy_row.get('id')}: {exc}")
            break

    destination_count = _count_any_destination_backfill_items(uid, selected_rows, db_client=client)
    verified = destination_count == len(selected_rows)
    return BackfillReport(
        uid=uid,
        dry_run=False,
        source_count=len(eligible_rows),
        intended_count=len(selected_rows),
        written_count=written_count,
        skipped_already_present=skipped_already_present,
        skipped_both_store_duplicate=skipped_both_store_duplicate,
        skipped_semantic_duplicate=skipped_semantic_duplicate,
        destination_count=destination_count,
        verified=verified,
        discrepancy=None if verified else f"source={len(selected_rows)} destination={destination_count}",
        completed=not errors,
        legacy_rows_touched=len(selected_rows),
        vector_sync_failures=vector_sync_failures,
        errors=errors,
        selected_bucket=selected_bucket_value,
        bucket_counts=bucket_counts,
        bucket_samples=bucket_samples,
        skipped_bucket_not_selected=skipped_bucket_not_selected,
    )


def backfill_user(
    uid: str,
    *,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    resume: bool = True,
    allow_admin_override: bool = False,
    acknowledge_non_canonical_uid: bool = False,
    operator_context: Optional[str] = None,
    db_client=None,
    get_non_filtered_memories_fn: Callable[..., List[dict]] = get_non_filtered_memories,
    run_id: Optional[str] = None,
) -> BackfillReport:
    """Copy active legacy memories into canonical long_term items.

      **Does not modify or delete legacy data** — read-only on ``database.memories``.
      Requires ``uid`` in ``CANONICAL_MEMORY_USERS`` unless ``allow_admin_override=True``
    and ``acknowledge_non_canonical_uid=True``.
    """
    client = db_client if db_client is not None else default_db_client
    try:
        assert_canonical_cohort_for_backfill(
            uid,
            allow_admin_override=allow_admin_override,
            acknowledge_non_canonical_uid=acknowledge_non_canonical_uid,
            operator_context=operator_context,
            db_client=client,
        )
    except BackfillCohortGateError as exc:
        return _cohort_gated_report(uid, dry_run=dry_run, reason=str(exc))

    effective_run_id = run_id or f"legacy_backfill_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    legacy_rows = _fetch_active_legacy_memories(uid, get_non_filtered_memories_fn=get_non_filtered_memories_fn)
    fingerprint = legacy_source_fingerprint(legacy_rows)
    eligible_rows = [row for row in legacy_rows if (row.get("content") or "").strip()]
    source_count = len(eligible_rows)

    if dry_run:
        control = _read_control_state(uid, db_client=client, create_if_missing=False)
        start_index = 0
        if resume and control.legacy_backfill_source_fingerprint == fingerprint:
            start_index = min(control.legacy_backfill_processed_count, source_count)
        intended_count = max(0, source_count - start_index)
        _, destination_count, verified, discrepancy = reconcile_backfill_counts(uid, eligible_rows, db_client=client)
        return BackfillReport(
            uid=uid,
            dry_run=True,
            source_count=source_count,
            intended_count=intended_count,
            written_count=0,
            skipped_already_present=0,
            skipped_both_store_duplicate=0,
            skipped_semantic_duplicate=0,
            destination_count=destination_count,
            verified=verified,
            discrepancy=discrepancy,
            resumed_from_index=start_index,
            completed=False,
            legacy_rows_touched=0,
        )

    control = _read_control_state(uid, db_client=client)
    start_index = 0
    if resume and control.legacy_backfill_source_fingerprint == fingerprint:
        start_index = min(control.legacy_backfill_processed_count, source_count)
    elif (
        resume and control.legacy_backfill_processed_count and control.legacy_backfill_source_fingerprint != fingerprint
    ):
        logger.warning(
            "legacy backfill source set changed for %s (fingerprint mismatch); restarting from 0",
            uid,
        )
        start_index = 0

    intended_count = max(0, source_count - start_index)
    written_count = 0
    skipped_already_present = 0
    skipped_both_store_duplicate = 0
    skipped_semantic_duplicate = 0
    vector_sync_failures = 0
    errors: List[str] = []
    materialized_semantic_keys: set[str] = set()

    processed_index = start_index
    while processed_index < source_count:
        legacy_row = eligible_rows[processed_index]
        semantic_key = semantic_materialization_key(uid=uid, legacy_row=legacy_row)
        if semantic_key is not None and semantic_key in materialized_semantic_keys:
            skipped_semantic_duplicate += 1
            processed_index += 1
            control = control.model_copy(
                update={
                    "legacy_backfill_processed_count": processed_index,
                    "legacy_backfill_source_fingerprint": fingerprint,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            _persist_control_state(control, db_client=client)
            continue
        try:
            control, written, skip_reason, row_vector_sync_failed = _apply_one_legacy_row(
                uid=uid,
                legacy_row=legacy_row,
                index=processed_index,
                control=control,
                run_id=effective_run_id,
                db_client=client,
            )
            if written:
                written_count += 1
            elif skip_reason == "both_store_duplicate":
                skipped_both_store_duplicate += 1
            elif skip_reason in {"already_present", "idempotent_skip"}:
                skipped_already_present += 1
            if semantic_key is not None and skip_reason not in {"empty_content"}:
                materialized_semantic_keys.add(semantic_key)
            if row_vector_sync_failed:
                vector_sync_failures += 1
        except Exception as exc:
            logger.exception("legacy backfill failed for %s row %s", uid, legacy_row.get("id"))
            errors.append(f"{legacy_row.get('id')}: {exc}")
            break

        processed_index += 1
        control = control.model_copy(
            update={
                "legacy_backfill_processed_count": processed_index,
                "legacy_backfill_source_fingerprint": fingerprint,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        _persist_control_state(control, db_client=client)

        if batch_size > 0 and (processed_index - start_index) % max(1, batch_size) == 0:
            logger.debug("legacy backfill checkpoint for %s at %s/%s", uid, processed_index, source_count)

    completed = processed_index >= source_count and not errors
    if completed:
        control = control.model_copy(
            update={
                "legacy_backfill_processed_count": source_count,
                "legacy_backfill_source_fingerprint": fingerprint,
                "legacy_backfill_completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        _persist_control_state(control, db_client=client)

    _, destination_count, verified, discrepancy = reconcile_backfill_counts(uid, eligible_rows, db_client=client)

    return BackfillReport(
        uid=uid,
        dry_run=False,
        source_count=source_count,
        intended_count=intended_count,
        written_count=written_count,
        skipped_already_present=skipped_already_present,
        skipped_both_store_duplicate=skipped_both_store_duplicate,
        skipped_semantic_duplicate=skipped_semantic_duplicate,
        destination_count=destination_count,
        verified=verified,
        discrepancy=discrepancy,
        resumed_from_index=start_index,
        completed=completed,
        legacy_rows_touched=0,
        vector_sync_failures=vector_sync_failures,
        errors=errors,
    )
