"""NON-DESTRUCTIVE legacy → canonical processing backfill (WS-C).

Safety contract (locked directive):
- **COPY only** — reads legacy ``users/{uid}/memories`` via ``get_non_filtered_memories``
  (read-only); applies the same active-row filter as ``get_memories`` in-process. Writes canonical
  ``memory_items`` via ``apply_long_term_patch_firestore``. Legacy rows are **never** deleted,
  updated, or invalidated by this module.
- **Idempotent (Q4)** — deterministic canonical ``memory_id`` per legacy row (hash of uid + legacy id).
- **Resumable** — per-user checkpoint on ``memory_state/apply_control`` (``legacy_backfill_*`` fields).
- **Dry-run** — reports intended writes without touching canonical or legacy stores.
- **Count-verified** — reconciles active legacy source count vs canonical submission ids.

Admin-only: invoke explicitly per uid; no cron, no auto-run.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, cast

from database._client import db as default_db_client
from database.memories import get_non_filtered_memories
from database.memory_collections import MemoryCollections
from database.memory_apply_store import apply_long_term_patch_firestore
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence
from models.memory_apply import ApplyStatus, MemoryControlState, build_patch_mutation_identity
from models.memory_contracts import DurablePatchDecision, LifecycleState, deterministic_contract_id
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.product_memory import (
    MemoryItemStatus,
    MemoryLayer,
    ProcessingState,
    MemoryItem,
    default_short_term_expiry,
)
from utils.memory.canonical_memory_adapter import extraction_memory_id
from utils.memory.legacy_backfill_support import (
    apply_with_control_refresh,
    fetch_active_legacy_rows,
    rows_missing_canonical_destinations,
)
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items
from utils.memory.required_promotion import (
    ADMISSION_CANDIDATE_STATUS_PENDING,
    REQUIRED_PROCESSING_STATUS_FAILED_RETRYABLE,
    REQUIRED_PROCESSING_STATUS_PENDING,
    REQUIRED_PROCESSOR_ID,
    REQUIRED_PROCESSOR_VERSION,
    REQUIRED_PROMOTION_STATUS_PENDING,
)
from utils.log_sanitizer import sanitize, sanitize_pii

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 50
LEGACY_SCAN_PAGE_SIZE = 500
Payload = Dict[str, Any]
LegacyRow = Dict[str, Any]
LegacyReader = Callable[..., List[LegacyRow]]
BucketSampleMap = Dict[str, List[Payload]]


class LegacyBackfillBucket(str, Enum):
    reviewed_long_term = "reviewed_long_term"
    manual_required_promotion = "manual_required_promotion"
    profile_required_promotion = "profile_required_promotion"
    archive_review = "archive_review"
    hold_noise = "hold_noise"
    hold_sensitive = "hold_sensitive"


class LegacyBackfillRemediationAction(str, Enum):
    """Read-only recommendation for a pre-admission legacy backfill item."""

    archive = "archive"
    keep = "keep"
    review = "review"


WRITABLE_LEGACY_BACKFILL_BUCKETS = {
    LegacyBackfillBucket.reviewed_long_term,
    LegacyBackfillBucket.manual_required_promotion,
}


def _empty_str_list() -> List[str]:
    return []


def _empty_bucket_counts() -> Dict[str, int]:
    return {}


def _empty_bucket_samples() -> BucketSampleMap:
    return {}


def _snapshot_payload(snapshot: Any) -> Payload:
    if not getattr(snapshot, "exists", False):
        return {}
    raw = snapshot.to_dict()
    return cast(Payload, raw) if isinstance(raw, dict) else {}


def _row_str(row: LegacyRow, key: str, default: str = "") -> str:
    value = row.get(key)
    return value if isinstance(value, str) else default


def _row_content(row: LegacyRow) -> str:
    return _row_str(row, "content").strip()


def row_content(row: LegacyRow) -> str:
    """Public content accessor for inventory/orchestrators (no new behavior)."""
    return _row_content(row)


def _legacy_source_attribution(
    payload: Payload,
    *,
    unresolved_attribution: str,
) -> Payload:
    """Preserve a structured legacy subject without inventing a primary-user subject."""
    raw_subject_id = payload.get("subject_entity_id")
    subject_id = raw_subject_id.strip() if isinstance(raw_subject_id, str) and raw_subject_id.strip() else None
    raw_subject_kind = str(payload.get("subject_kind") or "").strip().lower()
    if subject_id == "user":
        attribution = "user"
        inferred_kind = "user"
    elif subject_id is not None:
        attribution = "third_party"
        inferred_kind = "person" if subject_id.startswith("person:") else "entity"
    else:
        attribution = unresolved_attribution
        inferred_kind = "unknown"
    return {
        "subject_entity_id": subject_id,
        "subject_attribution": attribution,
        "subject_kind": (
            raw_subject_kind
            if raw_subject_kind in {"user", "speaker", "person", "entity", "unknown"}
            else inferred_kind
        ),
    }


_DOWNLOADS_PATTERN = re.compile(
    r"(?:\blocal downloads include\b|\bdownloads include\b|~/downloads\b|/downloads/)", re.I
)
_FOCUS_PATTERN = re.compile(r"^\s*focused on\b", re.I)
_GAUNTLET_MARKER_PATTERN = re.compile(
    r"\bgauntlet\s+recall\s+page\b|\bgauntlet\s+marker\s*:\s*gauntlet[-_][a-z0-9]|\bmarker\s+gauntlet[-_][a-z0-9]",
    re.I,
)
_RAW_EMAIL_PATTERN = re.compile(r"^\s*email from\b", re.I)
_ATTENTION_TELEMETRY_PATTERN = re.compile(r"^\s*distracted on\b", re.I)
_FILE_INVENTORY_PATTERN = re.compile(r"\b\d[\d,]*\s+local files indexed\b", re.I)
_LOCAL_PROJECT_DISCOVERY_PATTERN = re.compile(r"\bworks on a local project named\b", re.I)
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
    keyword_sync_failures: int = 0
    kg_extraction_failures: int = 0
    errors: List[str] = field(default_factory=_empty_str_list)
    selected_bucket: Optional[str] = None
    bucket_counts: Dict[str, int] = field(default_factory=_empty_bucket_counts)
    bucket_samples: BucketSampleMap = field(default_factory=_empty_bucket_samples)
    skipped_bucket_not_selected: int = 0
    skipped_bucket_not_writable: int = 0
    skipped_non_admissible: int = 0
    admissible_count: int = 0


@dataclass(frozen=True)
class LegacyBackfillRowResult:
    control: MemoryControlState
    written: bool
    skip_reason: Optional[str]
    vector_sync_failed: bool = False
    keyword_sync_succeeded: bool = True
    kg_extraction_failed: bool = False


@dataclass(frozen=True)
class LegacyBackfillRemediationEntry:
    """A content-free cleanup recommendation for an existing canonical item."""

    memory_id: str
    action: LegacyBackfillRemediationAction
    reason: str
    bucket: Optional[str]
    user_asserted: bool
    captured_at: datetime
    evidence_count: int
    content_hash: Optional[str]


@dataclass(frozen=True)
class LegacyBackfillRemediationPlan:
    """Read-only plan for canonical rows written by the historical backfill."""

    uid: str
    candidate_count: int
    action_counts: Dict[str, int]
    samples: Dict[str, List[LegacyBackfillRemediationEntry]]


@dataclass(frozen=True)
class LegacyBackfillRemediationApplyReport:
    """Result of the deliberately narrow legacy-backfill archive transition."""

    uid: str
    dry_run: bool
    expected_archive_count: Optional[int]
    candidate_count: int
    archived_count: int
    idempotent_count: int
    vector_sync_failures: int
    keyword_sync_failures: int
    kg_invalidation_failures: int
    errors: List[str] = field(default_factory=_empty_str_list)


@dataclass(frozen=True)
class LegacyBackfillRemediationArchiveResult:
    """Named result for one durable archive transition and its derived repairs."""

    control: MemoryControlState
    archived: bool
    idempotent: bool
    vector_sync_failed: bool
    keyword_sync_failed: bool
    kg_invalidation_failed: bool


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


def legacy_source_fingerprint(legacy_rows: Sequence[LegacyRow]) -> str:
    legacy_ids = sorted(_row_str(row, "id") for row in legacy_rows)
    return deterministic_contract_id("legacy-backfill-source-set", {"legacy_ids": legacy_ids})


def live_extraction_memory_id_for_legacy_row(*, uid: str, legacy_row: LegacyRow) -> Optional[str]:
    """Canonical id used by live extraction for the same conversation content, if derivable."""
    content = _row_content(legacy_row)
    if not content:
        return None
    source_id = (
        _row_str(legacy_row, "conversation_id") or _row_str(legacy_row, "memory_id") or _row_str(legacy_row, "id")
    )
    if not source_id:
        return None
    return extraction_memory_id(uid=uid, source_id=source_id, content=content)


def semantic_materialization_key(*, uid: str, legacy_row: LegacyRow) -> Optional[str]:
    """In-run dedup key: live extraction id when derivable, else normalized (source_id, content)."""
    content = _row_content(legacy_row)
    if not content:
        return None
    live_id = live_extraction_memory_id_for_legacy_row(uid=uid, legacy_row=legacy_row)
    if live_id is not None:
        return f"live:{live_id}"
    source_id = (
        _row_str(legacy_row, "conversation_id") or _row_str(legacy_row, "memory_id") or _row_str(legacy_row, "id")
    )
    if not source_id:
        return None
    return f"semantic:{source_id}:{content}"


def _load_canonical_item(uid: str, memory_id: str, *, db_client: Any) -> Optional[MemoryItem]:
    path = f"{MemoryCollections(uid=uid).memory_items}/{memory_id}"
    payload = _snapshot_payload(db_client.document(path).get())
    if not payload:
        return None
    return MemoryItem.model_validate(payload)


def _is_active_processed_canonical_item(item: MemoryItem) -> bool:
    return item.status == MemoryItemStatus.active and item.processing_state == ProcessingState.processed


def _is_active_processed_backfill_destination(item: MemoryItem) -> bool:
    return _is_active_processed_canonical_item(item) and item.tier == MemoryLayer.long_term


def _is_active_backfill_destination(item: MemoryItem) -> bool:
    if item.status != MemoryItemStatus.active:
        return False
    if _is_active_processed_backfill_destination(item):
        return True
    promotion = item.promotion or {}
    if item.tier != MemoryLayer.short_term or item.processing_state != ProcessingState.pending:
        return False
    processing_status = promotion.get("processing_status")
    if promotion.get("required") is True:
        return processing_status in {
            REQUIRED_PROCESSING_STATUS_PENDING,
            REQUIRED_PROCESSING_STATUS_FAILED_RETRYABLE,
        }
    return (
        promotion.get("required") is False
        and processing_status == ADMISSION_CANDIDATE_STATUS_PENDING
        and promotion.get("source_surface") == "legacy_backfill"
    )


def both_store_canonical_duplicate_exists(*, uid: str, legacy_row: LegacyRow, db_client: Any) -> bool:
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


def is_active_legacy_row(row: LegacyRow) -> bool:
    """Mirror ``get_memories`` default semantics: active, non-user-rejected rows only."""
    return row.get("user_review") is not False and row.get("invalid_at") is None


def legacy_backfill_noise_reason(content: str) -> Optional[str]:
    """Return a stable reason when historical content must never enter admission.

    These are source artifacts or test/attention telemetry, not candidate facts.
    Keep this deterministic and conservative: ambiguous content belongs in review,
    never in this denylist.
    """

    normalized = " ".join((content or "").split())
    if not normalized:
        return "empty_content"
    if _GAUNTLET_MARKER_PATTERN.search(normalized):
        return "test_marker"
    if _RAW_EMAIL_PATTERN.search(normalized):
        return "raw_email"
    if _ATTENTION_TELEMETRY_PATTERN.search(normalized):
        return "attention_telemetry"
    if _FILE_INVENTORY_PATTERN.search(normalized):
        return "file_inventory"
    if _LOCAL_PROJECT_DISCOVERY_PATTERN.search(normalized):
        return "local_project_inventory"
    if _DOWNLOADS_PATTERN.search(normalized):
        return "downloads_inventory"
    if _FOCUS_PATTERN.search(normalized):
        return "focus_telemetry"
    if _IMPERATIVE_PATTERN.search(normalized):
        return "imperative_fragment"
    return None


def classify_legacy_backfill_bucket(row: LegacyRow) -> LegacyBackfillBucket:
    """Route a legacy memory into the safest first-pass migration bucket."""
    content = _row_content(row)
    if not content:
        return LegacyBackfillBucket.hold_noise
    if _SENSITIVE_PATTERN.search(content):
        return LegacyBackfillBucket.hold_sensitive
    if legacy_backfill_noise_reason(content) is not None:
        return LegacyBackfillBucket.hold_noise
    if row.get("manually_added") is True or row.get("category") == "manual":
        return LegacyBackfillBucket.manual_required_promotion
    if _PROFILE_PATTERN.search(content):
        if row.get("user_review") is True:
            return LegacyBackfillBucket.reviewed_long_term
        return LegacyBackfillBucket.profile_required_promotion
    return LegacyBackfillBucket.archive_review


def is_legacy_backfill_admissible(row: LegacyRow) -> bool:
    """Whether a legacy row may enter hidden canonical admission staging."""

    return classify_legacy_backfill_bucket(row) not in {
        LegacyBackfillBucket.hold_noise,
        LegacyBackfillBucket.hold_sensitive,
    }


def _is_legacy_backfill_item(item: MemoryItem) -> bool:
    return (item.promotion or {}).get("source_surface") == "legacy_backfill"


def classify_legacy_backfill_remediation(item: MemoryItem) -> LegacyBackfillRemediationEntry:
    """Classify an existing backfilled canonical item without mutating it.

    Manual assertions and explicitly reviewed historical rows are preserved.
    Known source artifacts are recommended for Archive, while all ambiguous
    historical profile rows remain review-only. This deliberately avoids an LLM
    decision so a plan is deterministic and auditable before any future apply run.
    """

    promotion = item.promotion or {}
    bucket = promotion.get("bucket")
    if item.sensitivity_labels or _SENSITIVE_PATTERN.search(item.content or ""):
        action = LegacyBackfillRemediationAction.review
        reason = "sensitive_requires_review"
    elif bool(item.user_asserted) or bucket == LegacyBackfillBucket.manual_required_promotion.value:
        action = LegacyBackfillRemediationAction.keep
        reason = "user_asserted"
    elif bucket == LegacyBackfillBucket.reviewed_long_term.value:
        action = LegacyBackfillRemediationAction.keep
        reason = "explicitly_reviewed"
    else:
        noise_reason = legacy_backfill_noise_reason(item.content or "")
        if noise_reason is not None:
            action = LegacyBackfillRemediationAction.archive
            reason = noise_reason
        else:
            action = LegacyBackfillRemediationAction.review
            reason = "historical_import_requires_adjudication"
    return LegacyBackfillRemediationEntry(
        memory_id=item.memory_id,
        action=action,
        reason=reason,
        bucket=str(bucket) if bucket else None,
        user_asserted=bool(item.user_asserted),
        captured_at=item.captured_at,
        evidence_count=len(item.evidence),
        content_hash=item.content_hash,
    )


def build_legacy_backfill_remediation_plan(
    uid: str,
    *,
    db_client: Any = None,
    sample_size: int = 5,
) -> LegacyBackfillRemediationPlan:
    """Build a metadata-only, read-only remediation plan for historical imports.

    The plan intentionally scopes itself to active canonical rows with explicit
    ``legacy_backfill`` provenance. Unattributed historical rows are excluded
    until a separate lineage audit can explain their ingress.
    """

    client: Any = db_client if db_client is not None else default_db_client
    action_counts = {action.value: 0 for action in LegacyBackfillRemediationAction}
    samples: Dict[str, List[LegacyBackfillRemediationEntry]] = {
        action.value: [] for action in LegacyBackfillRemediationAction
    }
    candidates = [
        item
        for item in fetch_authoritative_product_memory_items(uid=uid, db_client=client)
        if item.tier == MemoryLayer.long_term
        and item.status == MemoryItemStatus.active
        and _is_legacy_backfill_item(item)
    ]
    for item in candidates:
        entry = classify_legacy_backfill_remediation(item)
        action_counts[entry.action.value] += 1
        if len(samples[entry.action.value]) < max(0, sample_size):
            samples[entry.action.value].append(entry)
    return LegacyBackfillRemediationPlan(
        uid=uid,
        candidate_count=len(candidates),
        action_counts=action_counts,
        samples={action: entries for action, entries in samples.items() if entries},
    )


def _archive_remediation_candidates(uid: str, *, db_client: Any) -> List[MemoryItem]:
    """Return only active, explicitly attributed rows the deterministic planner archives."""

    return [
        item
        for item in fetch_authoritative_product_memory_items(uid=uid, db_client=db_client)
        if item.tier == MemoryLayer.long_term
        and item.status == MemoryItemStatus.active
        and _is_legacy_backfill_item(item)
        and classify_legacy_backfill_remediation(item).action == LegacyBackfillRemediationAction.archive
    ]


def _archive_legacy_backfill_item_via_apply(
    *,
    uid: str,
    item: MemoryItem,
    control: MemoryControlState,
    run_id: str,
    db_client: Any,
) -> LegacyBackfillRemediationArchiveResult:
    """Archive one planner-approved item through the canonical apply ledger.

    The expected revision and content hash turn concurrent edits into a safe failure
    rather than archiving an item whose classification may no longer be valid.
    """

    entry = classify_legacy_backfill_remediation(item)
    if entry.action != LegacyBackfillRemediationAction.archive:
        raise ValueError(f"remediation item is no longer archive-eligible: {item.memory_id}")
    evidence_ids = [evidence.evidence_id for evidence in item.evidence]
    logical_payload: Payload = {
        "decision": DurablePatchDecision.update.value,
        "target_memory_id": item.memory_id,
        "result_status": LifecycleState.active.value,
        # archive_explicit: this operator path intentionally changes default visibility.
        "target_tier": MemoryLayer.archive.value,
        "clear_graph_assertion": True,
    }
    idempotency_key = deterministic_contract_id(
        "legacy-backfill-remediation-archive",
        {
            "uid": uid,
            "memory_id": item.memory_id,
            "item_revision": item.item_revision,
            "content_hash": item.content_hash,
        },
    )
    promotion = dict(item.promotion or {})
    promotion["remediation"] = {
        "action": LegacyBackfillRemediationAction.archive.value,
        "reason": entry.reason,
        "run_id": run_id,
        "previous_tier": item.tier.value,
    }
    patch_payload: Payload = {
        "patch_id": f"patch_lb_remediate_{idempotency_key[:20]}",
        "packet_id": f"legacy_backfill_remediation_archive:{item.memory_id}",
        "run_id": run_id,
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        **logical_payload,
        "evidence_ids": evidence_ids,
        "expected_item_revision": item.item_revision,
        "expected_content_hash": item.content_hash,
        "promotion_audit": promotion,
    }
    mutation_identity = build_patch_mutation_identity(patch_payload)
    patch_payload["mutation_metadata"] = mutation_identity
    logical_payload["mutation_metadata"] = mutation_identity
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.archive_transition,
        source_packet_id=(f"legacy_backfill_remediation_archive:{item.memory_id}:" f"r{item.item_revision}"),
        target_memory_id=item.memory_id,
        evidence_ids=evidence_ids,
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        patch_payload=patch_payload,
        proposed_operation=operation,
        db_client=db_client,
    )
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(f"archive remediation failed: {result.status} ({result.reason})")

    archived = (
        result.memory_items[0]
        if result.memory_items
        else _load_canonical_item(uid, item.memory_id, db_client=db_client)
    )
    # archive_explicit postcondition: default readers must no longer see this item.
    if archived is None or archived.tier != MemoryLayer.archive:
        raise RuntimeError("archive remediation did not persist an archive-tier memory")

    return LegacyBackfillRemediationArchiveResult(
        control=result.control_state,
        archived=result.status == ApplyStatus.committed,
        idempotent=result.status == ApplyStatus.idempotent_skip,
        vector_sync_failed=False,
        keyword_sync_failed=False,
        kg_invalidation_failed=False,
    )


def apply_legacy_backfill_remediation_archives(
    uid: str,
    *,
    expected_archive_count: Optional[int] = None,
    dry_run: bool = True,
    run_id: Optional[str] = None,
    operator_context: Optional[str] = None,
    db_client: Any = None,
) -> LegacyBackfillRemediationApplyReport:
    """Archive only the deterministic planner's legacy-backfill noise recommendations.

    This is intentionally a count-locked, per-account operator action. It never
    deletes memory content or touches ambiguous, sensitive, manually asserted, or
    unattributed rows. Actual transitions use ``apply_long_term_patch_firestore``.
    """

    client: Any = db_client if db_client is not None else default_db_client
    del operator_context  # Accepted for operator-side audit plumbing; never an entitlement input.

    candidates = _archive_remediation_candidates(uid, db_client=client)
    candidate_count = len(candidates)
    if not dry_run and expected_archive_count is None:
        raise ValueError("expected_archive_count is required for an archive remediation apply")
    if expected_archive_count is not None and candidate_count != expected_archive_count:
        return LegacyBackfillRemediationApplyReport(
            uid=uid,
            dry_run=dry_run,
            expected_archive_count=expected_archive_count,
            candidate_count=candidate_count,
            archived_count=0,
            idempotent_count=0,
            vector_sync_failures=0,
            keyword_sync_failures=0,
            kg_invalidation_failures=0,
            errors=[
                f"expected_archive_count={expected_archive_count} does not match candidate_count={candidate_count}"
            ],
        )
    if dry_run:
        return LegacyBackfillRemediationApplyReport(
            uid=uid,
            dry_run=True,
            expected_archive_count=expected_archive_count,
            candidate_count=candidate_count,
            archived_count=0,
            idempotent_count=0,
            vector_sync_failures=0,
            keyword_sync_failures=0,
            kg_invalidation_failures=0,
        )

    control = _read_control_state(uid, db_client=client, create_if_missing=False)
    effective_run_id = run_id or f"legacy_backfill_remediation_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    archived_count = 0
    idempotent_count = 0
    vector_sync_failures = 0
    keyword_sync_failures = 0
    kg_invalidation_failures = 0
    errors: List[str] = []
    for item in candidates:
        try:
            result = _archive_legacy_backfill_item_via_apply(
                uid=uid,
                item=item,
                control=control,
                run_id=effective_run_id,
                db_client=client,
            )
            control = result.control
            archived_count += int(result.archived)
            idempotent_count += int(result.idempotent)
            vector_sync_failures += int(result.vector_sync_failed)
            keyword_sync_failures += int(result.keyword_sync_failed)
            kg_invalidation_failures += int(result.kg_invalidation_failed)
        except Exception as exc:
            errors.append(f"{item.memory_id}: {sanitize(str(exc))}")
            logger.exception("legacy backfill remediation archive failed uid=%s memory_id=%s", uid, item.memory_id)
    return LegacyBackfillRemediationApplyReport(
        uid=uid,
        dry_run=False,
        expected_archive_count=expected_archive_count,
        candidate_count=candidate_count,
        archived_count=archived_count,
        idempotent_count=idempotent_count,
        vector_sync_failures=vector_sync_failures,
        keyword_sync_failures=keyword_sync_failures,
        kg_invalidation_failures=kg_invalidation_failures,
        errors=errors,
    )


def _legacy_bucket_sample(row: LegacyRow, *, bucket: LegacyBackfillBucket) -> Payload:
    content = " ".join(_row_content(row).split())
    if bucket == LegacyBackfillBucket.hold_sensitive:
        content = "[redacted sensitive memory content]"
    elif len(content) > 160:
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
    rows: Sequence[LegacyRow],
    *,
    sample_size: int = 5,
) -> tuple[Dict[str, int], BucketSampleMap]:
    counts = {bucket.value: 0 for bucket in LegacyBackfillBucket}
    samples: BucketSampleMap = {bucket.value: [] for bucket in LegacyBackfillBucket}
    for row in rows:
        bucket = classify_legacy_backfill_bucket(row)
        counts[bucket.value] += 1
        if len(samples[bucket.value]) < sample_size:
            samples[bucket.value].append(_legacy_bucket_sample(row, bucket=bucket))
    return counts, {bucket: sample_rows for bucket, sample_rows in samples.items() if sample_rows}


def bucket_counts_and_samples(
    rows: Sequence[LegacyRow],
    *,
    sample_size: int = 5,
) -> tuple[Dict[str, int], BucketSampleMap]:
    """Public inventory helper; wraps the internal classifier tally."""
    return _bucket_counts_and_samples(rows, sample_size=sample_size)


def _fetch_active_legacy_memories(
    uid: str,
    *,
    db_client: Any,
    get_non_filtered_memories_fn: LegacyReader,
    scan_page_size: int = LEGACY_SCAN_PAGE_SIZE,
) -> List[LegacyRow]:
    """Read-only raw-page scan; active filtering never mutates legacy rows."""
    return fetch_active_legacy_rows(
        uid,
        db_client=db_client,
        reader=get_non_filtered_memories_fn,
        is_active=is_active_legacy_row,
        scan_page_size=scan_page_size,
    )


def fetch_active_legacy_memories(
    uid: str,
    *,
    db_client: Any,
    get_non_filtered_memories_fn: LegacyReader,
    scan_page_size: int = LEGACY_SCAN_PAGE_SIZE,
) -> List[LegacyRow]:
    """Public read-only active legacy scan for inventory/orchestrators."""
    return _fetch_active_legacy_memories(
        uid,
        db_client=db_client,
        get_non_filtered_memories_fn=get_non_filtered_memories_fn,
        scan_page_size=scan_page_size,
    )


def _read_control_state(uid: str, *, db_client: Any, create_if_missing: bool = True) -> MemoryControlState:
    collections = MemoryCollections(uid=uid)
    ref = db_client.document(collections.memory_apply_control_state)
    payload = _snapshot_payload(ref.get())
    if payload:
        return MemoryControlState(**payload)
    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    if create_if_missing:
        ref.set(control.model_dump(mode="json"))
    return control


def _persist_control_state(control: MemoryControlState, *, db_client: Any) -> None:
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
    legacy_row: LegacyRow,
    index: int,
) -> MemoryEvidence:
    legacy_id = _row_str(legacy_row, "id", f"legacy_{index}")
    conversation_id = _row_str(legacy_row, "conversation_id") or _row_str(legacy_row, "memory_id")
    raw_evidence = legacy_row.get("evidence")
    evidence_rows = cast(List[Payload], raw_evidence) if isinstance(raw_evidence, list) else []
    if evidence_rows and evidence_rows[0].get("evidence_id"):
        first = evidence_rows[0]
        source_id = cast(str, first.get("source_id") or conversation_id or legacy_id)
        source_type = cast(str, first.get("source_type") or ("conversation" if conversation_id else "legacy_memory"))
        return MemoryEvidence(
            evidence_id=cast(str, first["evidence_id"]),
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


def _persist_evidence(uid: str, evidence: MemoryEvidence, *, db_client: Any) -> None:
    collections = MemoryCollections(uid=uid)
    path = f"{collections.memory_evidence}/{evidence.evidence_id}"
    ref = db_client.document(path)
    if not ref.get().exists:
        ref.set(evidence.model_dump(mode="json"))


def _new_backfill_operation(
    *,
    uid: str,
    legacy_row: LegacyRow,
    canonical_memory_id: str,
    control: MemoryControlState,
    evidence_ids: List[str],
    logical_payload: Payload,
    bucket: Optional[LegacyBackfillBucket] = None,
) -> MemoryOperation:
    legacy_id = _row_str(legacy_row, "id", canonical_memory_id)
    source_packet_id = f"legacy_backfill_{legacy_id}"
    if bucket is not None:
        source_packet_id = f"legacy_backfill_{bucket.value}_{legacy_id}"
    return MemoryOperation.new(
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


def _upgrade_pending_admission_candidate(
    *,
    uid: str,
    item: MemoryItem,
    bucket: LegacyBackfillBucket,
    control: MemoryControlState,
    run_id: str,
    db_client: Any,
) -> LegacyBackfillRowResult:
    promotion = dict(item.promotion or {})
    submission = dict(promotion.get("submission") or {})
    submission.update(
        {
            "submission_id": submission.get("submission_id") or item.memory_id,
            "source_surface": "legacy_backfill",
            "content_hash": hashlib.sha256((item.content or "").strip().encode("utf-8")).hexdigest(),
            "submitted_at": submission.get("submitted_at") or datetime.now(timezone.utc).isoformat(),
        }
    )
    promotion.update(
        {
            "required": True,
            "status": REQUIRED_PROMOTION_STATUS_PENDING,
            "processing_status": REQUIRED_PROCESSING_STATUS_PENDING,
            "processor_id": REQUIRED_PROCESSOR_ID,
            "processor_version": REQUIRED_PROCESSOR_VERSION,
            "reason": "legacy_migration_reviewed",
            "source_surface": "legacy_backfill",
            "migration_strategy": "bucketed_legacy_backfill",
            "bucket": bucket.value,
            "attempt_count": 0,
            "submission": submission,
        }
    )
    prior_source_attribution = dict(promotion.get("source_attribution") or {})
    source_attribution = _legacy_source_attribution(
        {
            "subject_entity_id": prior_source_attribution.get("subject_entity_id") or item.subject_entity_id,
            "subject_attribution": prior_source_attribution.get("subject_attribution"),
            "subject_kind": prior_source_attribution.get("subject_kind"),
        },
        unresolved_attribution="unknown",
    )
    promotion["source_attribution"] = source_attribution
    if bucket == LegacyBackfillBucket.reviewed_long_term:
        promotion["user_review"] = True
    evidence_ids = [evidence.evidence_id for evidence in item.evidence]
    logical_payload: Payload = {
        "decision": DurablePatchDecision.update.value,
        "target_memory_id": item.memory_id,
        "result_status": LifecycleState.active.value,
    }
    source_subject_id = source_attribution.get("subject_entity_id")
    if isinstance(source_subject_id, str) and source_subject_id:
        logical_payload["subject_entity_id"] = source_subject_id
    idempotency_key = deterministic_contract_id(
        "legacy-backfill-admission-upgrade",
        {
            "uid": uid,
            "memory_id": item.memory_id,
            "item_revision": item.item_revision,
            "bucket": bucket.value,
        },
    )
    patch_payload: Payload = {
        "patch_id": f"patch_lb_upgrade_{idempotency_key[:20]}",
        "packet_id": f"legacy_admission_upgrade:{item.memory_id}",
        "run_id": run_id,
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        **logical_payload,
        "evidence_ids": evidence_ids,
        "expected_item_revision": item.item_revision,
        "expected_content_hash": item.content_hash,
        "promotion_audit": promotion,
        "expires_at": (item.expires_at or default_short_term_expiry(datetime.now(timezone.utc))).isoformat(),
    }
    if isinstance(source_subject_id, str) and source_subject_id:
        patch_payload["subject_entity_id"] = source_subject_id
    mutation_identity = build_patch_mutation_identity(patch_payload)
    patch_payload["mutation_metadata"] = mutation_identity
    logical_payload["mutation_metadata"] = mutation_identity
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id=(f"legacy_admission_upgrade:{bucket.value}:{item.memory_id}:" f"r{item.item_revision}"),
        target_memory_id=item.memory_id,
        evidence_ids=evidence_ids,
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        patch_payload=patch_payload,
        proposed_operation=operation,
        db_client=db_client,
    )
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(f"legacy admission upgrade failed: {result.status} ({result.reason})")
    return LegacyBackfillRowResult(
        control=result.control_state,
        written=result.status == ApplyStatus.committed,
        skip_reason=None if result.status == ApplyStatus.committed else "idempotent_skip",
    )


def _apply_one_legacy_row(
    *,
    uid: str,
    legacy_row: LegacyRow,
    index: int,
    control: MemoryControlState,
    run_id: str,
    db_client: Any,
    bucket: Optional[LegacyBackfillBucket] = None,
) -> LegacyBackfillRowResult:
    """Write one canonical item. Returns control, write status, and side-effect status."""
    legacy_id = _row_str(legacy_row, "id", f"legacy_{index}")
    content = _row_content(legacy_row)
    if not content:
        return LegacyBackfillRowResult(control=control, written=False, skip_reason="empty_content")
    if bucket is not None and bucket not in WRITABLE_LEGACY_BACKFILL_BUCKETS:
        return LegacyBackfillRowResult(control=control, written=False, skip_reason="bucket_not_writable")

    classified_bucket = bucket or classify_legacy_backfill_bucket(legacy_row)
    durable_required = classified_bucket in {
        LegacyBackfillBucket.manual_required_promotion,
        LegacyBackfillBucket.reviewed_long_term,
    }

    canonical_memory_id = legacy_backfill_memory_id(uid=uid, legacy_memory_id=legacy_id)
    existing = _load_canonical_item(uid, canonical_memory_id, db_client=db_client)
    if existing is not None and _is_active_backfill_destination(existing):
        existing_promotion = existing.promotion or {}
        if (
            bucket is not None
            and durable_required
            and existing_promotion.get("required") is False
            and existing_promotion.get("processing_status") == ADMISSION_CANDIDATE_STATUS_PENDING
        ):
            return _upgrade_pending_admission_candidate(
                uid=uid,
                item=existing,
                bucket=classified_bucket,
                control=control,
                run_id=run_id,
                db_client=db_client,
            )
        return LegacyBackfillRowResult(
            control=control,
            written=False,
            skip_reason="already_present",
        )

    if both_store_canonical_duplicate_exists(uid=uid, legacy_row=legacy_row, db_client=db_client):
        return LegacyBackfillRowResult(control=control, written=False, skip_reason="both_store_duplicate")

    evidence = _build_backfill_evidence(uid=uid, legacy_row=legacy_row, index=index)
    _persist_evidence(uid, evidence, db_client=db_client)

    idempotency_key = legacy_backfill_idempotency_key(uid=uid, legacy_memory_id=legacy_id)
    # A migration is provenance, not durable-memory processing. Only manual or
    # reviewed rows inherit a durable-required contract. Everything else is a
    # hidden admission candidate and cannot promote without a future decision.
    initial_tier = MemoryLayer.short_term
    user_asserted = classified_bucket == LegacyBackfillBucket.manual_required_promotion
    admission_status = REQUIRED_PROCESSING_STATUS_PENDING if durable_required else ADMISSION_CANDIDATE_STATUS_PENDING
    promotion: Payload = {
        "required": durable_required,
        "status": REQUIRED_PROMOTION_STATUS_PENDING if durable_required else ADMISSION_CANDIDATE_STATUS_PENDING,
        "processing_status": admission_status,
        "processor_id": REQUIRED_PROCESSOR_ID,
        "processor_version": REQUIRED_PROCESSOR_VERSION,
        "reason": "legacy_migration",
        "source_surface": "legacy_backfill",
        "bucket": classified_bucket.value,
        "attempt_count": 0,
        "submission": {
            "submission_id": canonical_memory_id,
            "source_surface": "legacy_backfill",
            "source_type": evidence.source_type,
            "source_id": evidence.source_id,
            "legacy_memory_id": legacy_id,
            "content_hash": hashlib.sha256(content.strip().encode("utf-8")).hexdigest(),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    captured_at = None
    updated_at = None
    expires_at = default_short_term_expiry(datetime.now(timezone.utc))
    if bucket is not None:
        now = datetime.now(timezone.utc)
        captured_at = _coerce_optional_legacy_datetime(legacy_row.get("created_at")) or now
        updated_at = _coerce_optional_legacy_datetime(legacy_row.get("updated_at")) or captured_at
        if updated_at < captured_at:
            updated_at = captured_at
        expires_at = default_short_term_expiry(now)
        promotion.update(
            {
                "migration_strategy": "bucketed_legacy_backfill",
                "bucket": classified_bucket.value,
                "legacy_memory_id": legacy_id,
                "legacy_created_at": captured_at.isoformat(),
                "legacy_updated_at": updated_at.isoformat(),
            }
        )
    source_attribution = _legacy_source_attribution(
        legacy_row,
        unresolved_attribution="unknown" if durable_required else "legacy_assumed",
    )
    promotion["source_attribution"] = source_attribution
    if classified_bucket == LegacyBackfillBucket.reviewed_long_term:
        promotion["user_review"] = True

    patch_payload: Payload = {
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
        "relationship_to_user": ("self" if source_attribution.get("subject_entity_id") == "user" else "unclear"),
        "initial_tier": initial_tier.value,
        "user_asserted": user_asserted,
    }
    source_subject_id = source_attribution.get("subject_entity_id")
    if isinstance(source_subject_id, str) and source_subject_id:
        patch_payload["subject_entity_id"] = source_subject_id
    patch_payload["promotion"] = promotion
    if captured_at is not None:
        patch_payload["captured_at"] = captured_at.isoformat()
    if updated_at is not None:
        patch_payload["updated_at"] = updated_at.isoformat()
    patch_payload["expires_at"] = expires_at.isoformat()
    mutation_identity = build_patch_mutation_identity(patch_payload)
    patch_payload["mutation_metadata"] = mutation_identity
    logical_payload: Payload = {
        "decision": DurablePatchDecision.add.value,
        "memory_text": content,
        "result_status": LifecycleState.active.value,
        "mutation_metadata": mutation_identity,
    }
    if isinstance(source_subject_id, str) and source_subject_id:
        logical_payload["subject_entity_id"] = source_subject_id
    operation = _new_backfill_operation(
        uid=uid,
        legacy_row=legacy_row,
        canonical_memory_id=canonical_memory_id,
        control=control,
        evidence_ids=[evidence.evidence_id],
        logical_payload=logical_payload,
        bucket=bucket,
    )

    result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        patch_payload=patch_payload,
        proposed_operation=operation,
        db_client=db_client,
    )
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(f"legacy backfill apply failed for {legacy_id}: {result.status} ({result.reason})")

    written = result.status == ApplyStatus.committed
    return LegacyBackfillRowResult(
        control=result.control_state,
        written=written,
        skip_reason=None if written else "idempotent_skip",
    )


def _legacy_row_has_canonical_destination(
    *,
    uid: str,
    legacy_row: LegacyRow,
    items_by_id: Dict[str, MemoryItem],
) -> bool:
    legacy_id = _row_str(legacy_row, "id")
    content = _row_content(legacy_row)
    if not content:
        return False

    backfill_id = legacy_backfill_memory_id(uid=uid, legacy_memory_id=legacy_id)
    backfill_item = items_by_id.get(backfill_id)
    if backfill_item is not None and _is_active_backfill_destination(backfill_item):
        return True

    live_id = live_extraction_memory_id_for_legacy_row(uid=uid, legacy_row=legacy_row)
    if live_id is None:
        return False
    live_item = items_by_id.get(live_id)
    return live_item is not None and _is_active_processed_canonical_item(live_item)


def _count_destination_backfill_items(
    uid: str,
    legacy_rows: Sequence[LegacyRow],
    *,
    db_client: Any,
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
    legacy_rows: Sequence[LegacyRow],
    *,
    db_client: Any = None,
) -> tuple[int, int, bool, Optional[str]]:
    """Return (source_count, destination_count, verified, discrepancy)."""
    client: Any = db_client if db_client is not None else default_db_client
    eligible_rows = [row for row in legacy_rows if _row_content(row)]
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


def backfill_user_bucketed(
    uid: str,
    *,
    bucket: LegacyBackfillBucket | str | None = None,
    dry_run: bool = True,
    operator_context: Optional[str] = None,
    db_client: Any = None,
    get_non_filtered_memories_fn: LegacyReader = get_non_filtered_memories,
    run_id: Optional[str] = None,
) -> BackfillReport:
    """Bucket legacy rows and optionally apply one reviewed bucket.

    ``bucket=None`` is inventory-only. Real writes must name one bucket, and only
    buckets in ``WRITABLE_LEGACY_BACKFILL_BUCKETS`` are accepted.
    """
    selected_bucket = _coerce_legacy_backfill_bucket(bucket)
    client: Any = db_client if db_client is not None else default_db_client
    del operator_context  # Accepted for operator-side audit plumbing; never an entitlement input.

    effective_run_id = run_id or f"legacy_bucket_backfill_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    legacy_rows = _fetch_active_legacy_memories(
        uid,
        db_client=client,
        get_non_filtered_memories_fn=get_non_filtered_memories_fn,
    )
    eligible_rows = [row for row in legacy_rows if _row_content(row)]
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

    destination_count = _count_destination_backfill_items(uid, selected_rows, db_client=client)
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
    keyword_sync_failures = 0
    kg_extraction_failures = 0
    errors: List[str] = []
    materialized_semantic_keys: set[str] = set()

    for index, legacy_row in enumerate(selected_rows):
        semantic_key = semantic_materialization_key(uid=uid, legacy_row=legacy_row)
        if semantic_key is not None and semantic_key in materialized_semantic_keys:
            skipped_semantic_duplicate += 1
            continue
        try:
            row_result = _apply_one_legacy_row(
                uid=uid,
                legacy_row=legacy_row,
                index=index,
                control=control,
                run_id=effective_run_id,
                db_client=client,
                bucket=selected_bucket,
            )
            control = row_result.control
            if row_result.written:
                written_count += 1
            elif row_result.skip_reason == "both_store_duplicate":
                skipped_both_store_duplicate += 1
            elif row_result.skip_reason in {"already_present", "idempotent_skip"}:
                skipped_already_present += 1
            if semantic_key is not None and row_result.skip_reason not in {"empty_content"}:
                materialized_semantic_keys.add(semantic_key)
            if row_result.vector_sync_failed:
                vector_sync_failures += 1
            if not row_result.keyword_sync_succeeded:
                keyword_sync_failures += 1
            if row_result.kg_extraction_failed:
                kg_extraction_failures += 1
        except Exception as exc:
            safe_uid = sanitize_pii(uid)
            safe_legacy_id = sanitize_pii(_row_str(legacy_row, "id", "unknown"))
            logger.exception("bucketed legacy backfill failed for %s row %s", safe_uid, safe_legacy_id)
            errors.append(f"{safe_legacy_id}: {sanitize(exc)}")
            break

    destination_count = _count_destination_backfill_items(uid, selected_rows, db_client=client)
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
        keyword_sync_failures=keyword_sync_failures,
        kg_extraction_failures=kg_extraction_failures,
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
    max_rows: Optional[int] = None,
    continue_on_error: bool = False,
    stop_requested: Optional[Callable[[], bool]] = None,
    operator_context: Optional[str] = None,
    db_client: Any = None,
    get_non_filtered_memories_fn: LegacyReader = get_non_filtered_memories,
    run_id: Optional[str] = None,
) -> BackfillReport:
    """Stage active legacy memories as canonical admission candidates.

    **Does not modify or delete legacy data** — read-only on ``database.memories``.
    This is an explicit, bounded, per-UID repair tool; it never discovers users.
    """
    client: Any = db_client if db_client is not None else default_db_client
    del operator_context  # Accepted for operator-side audit plumbing; never an entitlement input.

    effective_run_id = run_id or f"legacy_backfill_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    legacy_rows = _fetch_active_legacy_memories(
        uid,
        db_client=client,
        get_non_filtered_memories_fn=get_non_filtered_memories_fn,
    )
    eligible_rows = [row for row in legacy_rows if _row_content(row)]
    admissible_rows = [row for row in eligible_rows if is_legacy_backfill_admissible(row)]
    skipped_non_admissible = len(eligible_rows) - len(admissible_rows)
    fingerprint = legacy_source_fingerprint(admissible_rows)
    source_count = len(eligible_rows)

    if dry_run:
        control = _read_control_state(uid, db_client=client, create_if_missing=False)
        start_index = 0
        if resume and control.legacy_backfill_source_fingerprint == fingerprint:
            start_index = min(control.legacy_backfill_processed_count, len(admissible_rows))
        end_index = len(admissible_rows)
        if max_rows is not None:
            end_index = min(end_index, start_index + max(0, max_rows))
        intended_count = max(0, end_index - start_index)
        _, destination_count, verified, discrepancy = reconcile_backfill_counts(uid, admissible_rows, db_client=client)
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
            skipped_non_admissible=skipped_non_admissible,
            admissible_count=len(admissible_rows),
        )

    control = _read_control_state(uid, db_client=client)
    start_index = 0
    rows_to_process = admissible_rows
    source_indexes = list(range(len(admissible_rows)))
    recovering_changed_source = False
    recovered_semantic_keys: set[str] = set()
    if resume and control.legacy_backfill_source_fingerprint == fingerprint:
        start_index = min(control.legacy_backfill_processed_count, len(admissible_rows))
    elif (
        resume and control.legacy_backfill_processed_count and control.legacy_backfill_source_fingerprint != fingerprint
    ):
        logger.warning(
            "legacy backfill source set changed for %s (fingerprint mismatch); reconciling pending destinations",
            uid,
        )
        # A changed source invalidates positional progress. Reconcile against
        # idempotent destinations instead, so newly inserted IDs cannot starve
        # behind an outdated cursor.
        items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
        items_by_id = {item.memory_id: item for item in items}
        destination_rows = [
            row
            for row in admissible_rows
            if _legacy_row_has_canonical_destination(uid=uid, legacy_row=row, items_by_id=items_by_id)
        ]
        rows_to_process = rows_missing_canonical_destinations(
            admissible_rows,
            has_destination=lambda row: _legacy_row_has_canonical_destination(
                uid=uid,
                legacy_row=row,
                items_by_id=items_by_id,
            ),
        )
        pending_ids = {id(row) for row in rows_to_process}
        source_indexes = [index for index, row in enumerate(admissible_rows) if id(row) in pending_ids]
        recovered_semantic_keys = {
            key
            for row in destination_rows
            if (key := semantic_materialization_key(uid=uid, legacy_row=row)) is not None
        }
        start_index = 0
        recovering_changed_source = True

    end_index = len(rows_to_process)
    if max_rows is not None:
        end_index = min(end_index, start_index + max(0, max_rows))
    intended_count = max(0, end_index - start_index)
    written_count = 0
    skipped_already_present = 0
    skipped_both_store_duplicate = 0
    skipped_semantic_duplicate = 0
    vector_sync_failures = 0
    keyword_sync_failures = 0
    kg_extraction_failures = 0
    errors: List[str] = []
    materialized_semantic_keys = recovered_semantic_keys

    processed_index = start_index
    while processed_index < end_index:
        if stop_requested is not None and stop_requested():
            break
        legacy_row = rows_to_process[processed_index]
        source_index = source_indexes[processed_index]
        semantic_key = semantic_materialization_key(uid=uid, legacy_row=legacy_row)
        if semantic_key is not None and semantic_key in materialized_semantic_keys:
            skipped_semantic_duplicate += 1
            processed_index += 1
            control = control.model_copy(
                update={
                    "legacy_backfill_processed_count": (0 if recovering_changed_source else processed_index),
                    "legacy_backfill_source_fingerprint": (
                        control.legacy_backfill_source_fingerprint if recovering_changed_source else fingerprint
                    ),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            _persist_control_state(control, db_client=client)
            continue
        attempt = apply_with_control_refresh(
            control=control,
            apply_fn=lambda latest: _apply_one_legacy_row(
                uid=uid,
                legacy_row=legacy_row,
                # Retain the stable source position: changing it on recovery
                # would create a second fallback evidence id for the same row.
                index=source_index,
                control=latest,
                run_id=effective_run_id,
                db_client=client,
            ),
            refresh_control=lambda: _read_control_state(uid, db_client=client, create_if_missing=False),
            retry_once=continue_on_error,
        )
        control, row_result, row_error = attempt.control, attempt.result, attempt.error
        if row_result is not None:
            control = row_result.control
            if row_result.written:
                written_count += 1
            elif row_result.skip_reason == "both_store_duplicate":
                skipped_both_store_duplicate += 1
            elif row_result.skip_reason in {"already_present", "idempotent_skip"}:
                skipped_already_present += 1
            if semantic_key is not None and row_result.skip_reason not in {"empty_content"}:
                materialized_semantic_keys.add(semantic_key)
            if row_result.vector_sync_failed:
                vector_sync_failures += 1
            if not row_result.keyword_sync_succeeded:
                keyword_sync_failures += 1
            if row_result.kg_extraction_failed:
                kg_extraction_failures += 1
        elif row_error is not None:
            safe_uid = sanitize_pii(uid)
            safe_legacy_id = sanitize_pii(_row_str(legacy_row, "id", "unknown"))
            logger.error("legacy backfill failed for %s row %s", safe_uid, safe_legacy_id)
            errors.append(f"{safe_legacy_id}: {sanitize(row_error)}")
            if not continue_on_error:
                break

        processed_index += 1
        control = control.model_copy(
            update={
                "legacy_backfill_processed_count": (0 if recovering_changed_source else processed_index),
                "legacy_backfill_source_fingerprint": (
                    control.legacy_backfill_source_fingerprint if recovering_changed_source else fingerprint
                ),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        _persist_control_state(control, db_client=client)

        if batch_size > 0 and (processed_index - start_index) % max(1, batch_size) == 0:
            logger.debug("legacy backfill checkpoint for %s at %s/%s", uid, processed_index, len(rows_to_process))

    _, destination_count, verified, discrepancy = reconcile_backfill_counts(uid, admissible_rows, db_client=client)
    # Semantic duplicate rows are intentionally handled as completed work even
    # when they share another row's canonical destination, preserving the
    # established single-source completion contract. The changed-source path
    # still reaches this point only after every currently missing destination
    # has been examined.
    completed = processed_index >= len(rows_to_process) and not errors
    if completed:
        control = control.model_copy(
            update={
                "legacy_backfill_processed_count": len(admissible_rows),
                "legacy_backfill_source_fingerprint": fingerprint,
                "legacy_backfill_completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        _persist_control_state(control, db_client=client)

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
        keyword_sync_failures=keyword_sync_failures,
        kg_extraction_failures=kg_extraction_failures,
        errors=errors,
        skipped_non_admissible=skipped_non_admissible,
        admissible_count=len(admissible_rows),
    )
