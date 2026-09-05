"""Canonical Firestore apply adapter for long-term memory patches (WS-G7)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import wraps
import hashlib
import hmac
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, TypeVar, TypedDict, cast

from pydantic import BaseModel

from config.memory_rollout import MemoryRolloutMode, rollout_mode_env_value

try:
    from google.cloud.firestore_v1 import transactional as _firestore_transactional  # type: ignore[reportAssignmentType,reportUnknownMemberType]  # firebase_admin firestore_v1 untyped
except ImportError:  # pragma: no cover - local unit tests mock Firestore.
    _firestore_transactional = None

from database._client import data_plane_db as db
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.legal_holds import (
    assert_destructive_operation_transaction,
    assert_no_destructive_operation_transaction,
    destructive_operation_gate,
)
from database.memory_collections import MemoryCollections
from database.read_boundary import parse_snapshot_strict
from models.memory_evidence import (
    ArtifactPreservationState,
    MemoryEvidence,
    ProvenanceVisibility,
    RedactionStatus,
    SourceState,
    SourceStateReason,
)
from models.memory_contracts import DurablePatchDecision, deterministic_contract_id
from models.memory_apply import (
    ApplyResult,
    ApplyStatus,
    MemoryControlState,
    MemoryWriterClass,
    MemoryOutboxEvent,
    MemoryOutboxEventType,
    WriterAdmissionError,
    apply_long_term_patch_transaction,
    require_writer_admitted,
)
from models.memory_operations import MemoryLedgerReopenReceipt, MemoryOperation, MemoryOperationType
from models.jit_proactivity import JITProactivityEventReceipt
from models.jit_trigger_feedback import JITTriggerFeedbackReceipt
from models.memory_promotion import MemoryGraphAssertion, PromotionGraphPlan, build_memory_graph_assertion
from models.memory_review import build_memory_review_conflict
from models.memory_source_replacement import ConversationSourceReplacementReceipt
from models.product_memory import (
    RESTRICTED_SENSITIVITY_LABELS,
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemorySubjectScope,
)
from models.memory_state_head import trusted_memory_state_head_fields


class MemoryFirestoreApplyError(Exception):
    pass


MemoryFirestoreApplyError = MemoryFirestoreApplyError


class CanonicalMemoryIntakePausedError(MemoryFirestoreApplyError):
    """The deployment-wide incident fence has paused canonical mutations."""


def _require_canonical_intake_enabled() -> None:
    """Fence every canonical intake boundary with the global deployment mode."""

    try:
        mode = MemoryRolloutMode(rollout_mode_env_value())
    except ValueError as exc:
        raise CanonicalMemoryIntakePausedError("canonical memory intake mode is malformed") from exc
    if mode not in {MemoryRolloutMode.write, MemoryRolloutMode.read}:
        raise CanonicalMemoryIntakePausedError("canonical memory intake is globally paused")


class MissingMemoryDocument(MemoryFirestoreApplyError):
    pass


_DIRECT_USER_LEDGER_EVIDENCE_TYPES = {
    "explicit_user_correction",
    "explicit_user_reopen",
    "explicit_user_revert",
}
_DIRECT_USER_WRITE_AUTHORITY = object()
_DIRECT_USER_MUTATION_PATCH_FIELDS = frozenset(
    {
        "patch_id",
        "packet_id",
        "run_id",
        "observed_head_commit_id",
        "idempotency_key",
        "decision",
        "target_memory_id",
        "result_status",
        "mutation_metadata",
        "evidence_ids",
        "expected_item_revision",
        "expected_content_hash",
        "memory_text",
        "target_tier",
        "target_user_asserted",
        "target_visibility",
        "clear_graph_assertion",
        "arguments",
        "promotion_audit",
        "expires_at",
        "kg_extracted",
        "valid_to",
    }
)
_LEDGER_MIGRATION_PATCH_FIELDS = frozenset(
    {
        "patch_id",
        "packet_id",
        "run_id",
        "observed_head_commit_id",
        "idempotency_key",
        "decision",
        "target_memory_id",
        "result_status",
        "mutation_metadata",
        "evidence_ids",
        "expected_item_revision",
        "expected_content_hash",
        "ledger_schema_version",
        "kind",
        "subject_scope",
        "slot",
        "valid_from",
        "valid_to",
        "curation_weight",
        "trigger_condition",
        "intent_backed",
        "write_reason",
        "arguments",
    }
)


class ConversationSourceReplacementConflict(MemoryFirestoreApplyError):
    """The source snapshot changed after replacement planning."""


class ConversationSourceReplacementLimitError(MemoryFirestoreApplyError):
    """A source replacement cannot fit in one Firestore transaction."""


class CanonicalMemoryTombstoneConflict(MemoryFirestoreApplyError):
    """The canonical item/control snapshot changed during a privacy tombstone."""


class CanonicalMemoryTombstoneLimitError(MemoryFirestoreApplyError):
    """A privacy tombstone cannot fit in one Firestore transaction."""


class CanonicalReviewResolutionConflict(MemoryFirestoreApplyError):
    """A canonical review was already resolved or no longer owns its source revision."""

    def __init__(self, status: str, message: str, *, review_item: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status = status
        self.review_item = review_item


@dataclass(frozen=True)
class CanonicalApplyWrite:
    """One server-built canonical apply staged inside a source replacement."""

    operation: MemoryOperation
    patch_payload: Dict[str, Any]
    evidence: List[MemoryEvidence]


@dataclass(frozen=True)
class ConversationSourceReplacementResult:
    control_state: MemoryControlState
    retracted_memory_ids: List[str]
    committed_memory_ids: List[str]
    reactivated_memory_ids: List[str]
    tombstoned_evidence_ids: List[str]


@dataclass(frozen=True)
class CanonicalMemoryTombstoneResult:
    control_state: MemoryControlState
    memory_items: List[MemoryItem]
    tombstoned_evidence_ids: List[str]


@dataclass(frozen=True)
class CanonicalReviewResolution:
    review_id: str
    memory_id: str
    decision: str
    reason: str = ""
    authority: Optional[str] = "canonical_memory"
    expected_candidate: Optional[Dict[str, Any]] = None
    mutation_target_memory_id: Optional[str] = None
    correction_record: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class _MemoryControlFence:
    head_commit_id: str
    account_generation: int
    source_generation: int
    commit_sequence: int


class MemoryApplyDoc(TypedDict, total=False):
    """Firestore document contract for the memory-apply store.

    Captures the union of keys read into ``MemoryControlState``,
    ``MemoryOperation``, ``MemoryEvidence`` and ``MemoryItem`` plus the
    ``commit`` and ``state-head`` projections written back through this store.
    Every key is optional because each read uses ``**`` into a pydantic model
    that supplies defaults, and the document shape varies per collection.
    """

    # control state
    uid: str
    head_commit_id: str
    account_generation: int
    source_generation: int
    commit_sequence: int
    projection_watermark_commit_id: Optional[str]
    projection_watermark_sequence: int
    vector_watermark_commit_id: Optional[str]
    last_promotion_run_at: Optional[datetime]
    last_consolidation_run_at: Optional[datetime]
    legacy_backfill_processed_count: int
    legacy_backfill_source_fingerprint: Optional[str]
    legacy_backfill_completed_at: Optional[datetime]
    updated_at: datetime
    # operation
    operation_id: str
    operation_type: Any
    status: Any
    source_packet_id: Optional[str]
    target_memory_id: Optional[str]
    evidence_ids: List[str]
    logical_payload: Any
    logical_payload_digest: str
    observed_head_commit_id: Optional[str]
    committed_head_commit_id: Optional[str]
    committed_sequence: Optional[int]
    committed_memory_item_ids: List[str]
    committed_outbox_event_ids: List[str]
    attempt_count: int
    error_code: Optional[str]
    untrusted_proposed_operation_id: Optional[str]
    created_at: datetime
    # evidence
    evidence_id: str
    source_type: str
    source_id: Optional[str]
    source_version: Optional[str]
    conversation_id: Optional[str]
    artifact_refs: List[Dict[str, Any]]
    artifact_preservation: Any
    quote_refs: List[Dict[str, Any]]
    content_hash: Optional[str]
    lineage_id: Optional[str]
    source_state: Any
    source_state_reason: Any
    provenance_visibility: Any
    redaction_status: Any
    encryption_or_redaction_status: Any
    patch_id: Optional[str]
    commit_id: Optional[str]
    client_device_id: Optional[str]
    # memory item
    memory_id: str
    canonical_memory_id: Optional[str]
    version: int
    tier: Any
    processing_state: Any
    content: Optional[str]
    evidence: List[Dict[str, Any]]
    source_ids: List[str]
    sensitivity_labels: List[str]
    visibility: str
    user_asserted: bool
    captured_at: datetime
    expires_at: Optional[datetime]
    ledger_commit_id: Optional[str]
    ledger_sequence: Optional[int]
    item_revision: int
    source_commit_id: Optional[str]
    source_commit_sequence: Optional[int]
    promotion: Optional[Dict[str, Any]]
    capture_device_ids: List[str]
    primary_capture_device: Optional[str]
    corroboration_count: int
    last_corroborated_at: Optional[datetime]
    confidence: Optional[float]
    superseded_by: Optional[str]
    subject_entity_id: Optional[str]
    predicate: Optional[str]
    arguments: Dict[str, Any]
    kg_extracted: bool
    graph_ready: bool
    graph_assertion_id: Optional[str]
    graph_plan_hash: Optional[str]
    # commit projection (write-only)
    memory_item_ids: List[str]
    outbox_event_ids: List[str]
    # state-head projection (write-only)
    schema_version: int
    source: str


F = TypeVar("F", bound=Callable[..., Any])
M = TypeVar("M", bound=BaseModel)


def transactional(func: F) -> F:
    """Typed facade over ``google.cloud.firestore_v1.transactional``.

    Delegates to the real Firestore decorator when the SDK is importable;
    otherwise falls back to a transaction-lifecycle simulator used by local
    unit tests that mock Firestore.
    """
    if _firestore_transactional is not None:
        return cast("F", _firestore_transactional(func))

    @wraps(func)
    def wrapper(transaction: Any, *args: Any, **kwargs: Any) -> Any:
        if hasattr(transaction, "_begin"):
            transaction._begin()
        try:
            result: Any = func(transaction, *args, **kwargs)
            if hasattr(transaction, "_commit"):
                transaction._commit()
            return result
        except Exception:
            if hasattr(transaction, "_rollback"):
                transaction._rollback()
            raise
        finally:
            if hasattr(transaction, "_clean_up"):
                transaction._clean_up()

    return cast("F", wrapper)


def _typed_doc(doc: Any) -> Dict[str, Any]:
    """Typed adapter for Firestore ``DocumentSnapshot.to_dict()`` reads."""
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def apply_long_term_patch_firestore(
    *,
    uid: str,
    operation_id: str,
    patch_payload: Dict[str, Any],
    proposed_operation: Optional[MemoryOperation] = None,
    proposed_evidence: Optional[List[MemoryEvidence]] = None,
    review_resolution: Optional[CanonicalReviewResolution] = None,
    required_source_item: Optional[MemoryItem] = None,
    ledger_reopen_receipt: Optional[MemoryLedgerReopenReceipt] = None,
    trigger_feedback_receipt: Optional[JITTriggerFeedbackReceipt] = None,
    allow_ledger_migration: bool = False,
    _direct_user_authority: object | None = None,
    db_client: Any = db,
) -> ApplyResult:
    """Apply a memory Long-term patch through the Firestore transaction boundary.

    The pure contract in `models.memory_apply` stays dependency-free. This
    adapter owns authoritative Firestore reads/writes and never trusts caller
    snapshots for control state, operation state, or evidence/source state.
    """
    _require_canonical_intake_enabled()
    transaction = db_client.transaction()
    return _apply_long_term_patch_firestore_transaction(
        transaction,
        db_client,
        uid,
        operation_id,
        patch_payload,
        proposed_operation,
        proposed_evidence,
        review_resolution,
        required_source_item,
        ledger_reopen_receipt,
        trigger_feedback_receipt,
        allow_ledger_migration,
        _direct_user_authority is _DIRECT_USER_WRITE_AUTHORITY,
    )


def apply_direct_user_long_term_patch_firestore(
    *,
    uid: str,
    operation_id: str,
    patch_payload: Dict[str, Any],
    proposed_operation: Optional[MemoryOperation] = None,
    proposed_evidence: Optional[List[MemoryEvidence]] = None,
    review_resolution: Optional[CanonicalReviewResolution] = None,
    required_source_item: Optional[MemoryItem] = None,
    ledger_reopen_receipt: Optional[MemoryLedgerReopenReceipt] = None,
    trigger_feedback_receipt: Optional[JITTriggerFeedbackReceipt] = None,
    allow_ledger_migration: bool = False,
    db_client: Any = db,
) -> ApplyResult:
    """Apply a mutation admitted only through the trusted user-facing adapter.

    User authority is an opaque in-process capability. It is deliberately not
    inferred from operation ids, packet prefixes, evidence, or patch content.
    """

    if allow_ledger_migration:
        raise ValueError("direct user authority cannot grant ledger migration capability")
    return apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation_id,
        patch_payload=patch_payload,
        proposed_operation=proposed_operation,
        proposed_evidence=proposed_evidence,
        review_resolution=review_resolution,
        required_source_item=required_source_item,
        ledger_reopen_receipt=ledger_reopen_receipt,
        trigger_feedback_receipt=trigger_feedback_receipt,
        _direct_user_authority=_DIRECT_USER_WRITE_AUTHORITY,
        db_client=db_client,
    )


_MAX_FIRESTORE_TRANSACTION_MUTATIONS = 500


def replace_conversation_source_firestore(
    *,
    uid: str,
    conversation_id: str,
    replacement_id: str,
    replacement_digest: str,
    replacement_operation: MemoryOperation,
    observed_control: MemoryControlState,
    expected_source_items: List[MemoryItem],
    expected_reactivation_items: List[MemoryItem],
    writes: List[CanonicalApplyWrite],
    deletion_gate_token: str | None = None,
    db_client: Any = db,
) -> ConversationSourceReplacementResult:
    """Atomically replace every active item sourced from one conversation.

    Planning and the source scan happen outside the transaction. The observed
    control fence is revalidated inside the transaction before every source
    item/evidence and every proposed operation target is read. Any intervening
    canonical write therefore restarts planning instead of committing a partial
    or stale replacement.
    """
    _require_canonical_intake_enabled()
    transaction = db_client.transaction()
    return _replace_conversation_source_firestore_transaction(
        transaction,
        db_client,
        uid,
        conversation_id,
        replacement_id,
        replacement_digest,
        replacement_operation,
        observed_control,
        expected_source_items,
        expected_reactivation_items,
        writes,
        deletion_gate_token,
    )


def tombstone_memory_items_firestore(
    *,
    uid: str,
    reason: str,
    observed_control: MemoryControlState,
    expected_items: List[MemoryItem],
    preserved_evidence_ids: Iterable[str],
    deletion_gate_token: str,
    review_resolution: Optional[CanonicalReviewResolution] = None,
    db_client: Any = db,
) -> CanonicalMemoryTombstoneResult:
    """Atomically journal and tombstone one bounded authoritative item set."""
    transaction = db_client.transaction()
    return _tombstone_memory_items_firestore_transaction(
        transaction,
        db_client,
        uid,
        reason,
        observed_control,
        expected_items,
        frozenset(preserved_evidence_ids),
        deletion_gate_token,
        review_resolution,
    )


def privacy_deletion_receipt_id(uid: str, memory_id: str) -> str:
    """Return a server-keyed, non-enumerable anti-resurrection identity."""

    secret = (os.getenv("ENCRYPTION_SECRET") or "").encode("utf-8")
    if len(secret) < 32:
        raise MemoryFirestoreApplyError("privacy deletion receipt secret is unavailable")
    digest = hmac.new(
        secret,
        f"memory-privacy-receipt.v2\n{uid}\n{memory_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"receipt_{digest}"


def _control_fence(control: MemoryControlState) -> _MemoryControlFence:
    return _MemoryControlFence(
        head_commit_id=control.head_commit_id,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        commit_sequence=control.commit_sequence,
    )


def _privacy_delete_events(
    *,
    uid: str,
    item: MemoryItem,
    parent_control: MemoryControlState,
    committed_control: MemoryControlState,
    operation_id: str,
    reason: str,
    now: datetime,
) -> List[MemoryOutboxEvent]:
    events: List[MemoryOutboxEvent] = []
    for event_type in (MemoryOutboxEventType.projection_sync, MemoryOutboxEventType.vector_sync):
        event_id = (
            "evt_"
            + deterministic_contract_id(
                "memory-outbox",
                {
                    "event_type": event_type.value,
                    "commit_id": committed_control.head_commit_id,
                    "memory_id": item.memory_id,
                    "operation_id": operation_id,
                },
            )[:32]
        )
        events.append(
            MemoryOutboxEvent(
                event_id=event_id,
                uid=uid,
                event_type=event_type,
                commit_id=committed_control.head_commit_id,
                # Privacy deletion rotates the externally visible hash epoch.
                # Do not retain the pre-delete content-derived parent commit.
                parent_commit_id=committed_control.head_commit_id,
                commit_sequence=committed_control.commit_sequence,
                memory_id=item.memory_id,
                operation_id=operation_id,
                account_generation=committed_control.account_generation,
                source_generation=committed_control.source_generation,
                payload={
                    "memory_id": item.memory_id,
                    "tier": item.tier.value,
                    "action": "delete",
                    "item_revision": item.item_revision,
                    "content_hash": item.content_hash,
                    "reason": reason,
                },
                available_at=now,
            )
        )
    return events


def _read_canonical_review_resolution(
    *,
    transaction: Any,
    db_client: Any,
    collections: MemoryCollections,
    request: Optional[CanonicalReviewResolution],
) -> Optional[Dict[str, Any]]:
    if request is None:
        return None
    if (
        not request.review_id.strip()
        or not request.memory_id.strip()
        or request.decision not in {"accept", "correct", "reject", "drop"}
    ):
        raise CanonicalReviewResolutionConflict("stale_review", "canonical review resolution identity is invalid")
    review_ref = db_client.document(f"{collections.memory_review_queue}/{request.review_id}")
    snapshot = review_ref.get(transaction=transaction)
    if not getattr(snapshot, "exists", False):
        raise CanonicalReviewResolutionConflict("stale_review", "canonical review no longer exists")
    review_item = _typed_doc(snapshot)
    if (
        review_item.get("authority") != request.authority
        or review_item.get("review_id") != request.review_id
        or review_item.get("fact_id") != request.memory_id
        or (request.expected_candidate is not None and review_item.get("candidate") != request.expected_candidate)
    ):
        raise CanonicalReviewResolutionConflict(
            "stale_review",
            "canonical review identity no longer matches",
            review_item=review_item,
        )
    if review_item.get("status") not in {"pending", "pending_review"}:
        raise CanonicalReviewResolutionConflict(
            "already_resolved",
            "canonical review is already resolved",
            review_item=review_item,
        )
    return review_item


def _validate_canonical_review_source(
    *,
    review_item: Optional[Dict[str, Any]],
    request: Optional[CanonicalReviewResolution],
    item: MemoryItem,
) -> None:
    if request is None:
        return
    if request.authority != "canonical_memory":
        return
    if review_item is None:
        raise CanonicalReviewResolutionConflict("stale_review", "canonical review source is missing")
    promotion = item.promotion or {}
    if (
        item.memory_id != request.memory_id
        or item.status != MemoryItemStatus.active
        or item.ledger_commit_id != review_item.get("source_commit_id")
        or item.item_revision != review_item.get("source_item_revision")
        or item.content_hash != review_item.get("source_content_hash")
        or promotion.get("route") != "review"
    ):
        raise CanonicalReviewResolutionConflict(
            "stale_review",
            "canonical review no longer owns the current memory revision",
            review_item=review_item,
        )


def _write_canonical_review_resolution(
    *,
    transaction: Any,
    db_client: Any,
    collections: MemoryCollections,
    request: Optional[CanonicalReviewResolution],
    review_item: Optional[Dict[str, Any]],
    commit_id: str,
    now: datetime,
) -> None:
    if request is None:
        return
    if review_item is None:
        raise CanonicalReviewResolutionConflict("stale_review", "canonical review source is missing")
    status_by_decision = {
        "accept": "accepted",
        "correct": "accepted",
        "reject": "rejected",
        "drop": "dropped",
    }
    redacted = {
        **review_item,
        "status": status_by_decision[request.decision],
        "decision": request.decision,
        "reason": (
            f"canonical_review_{request.decision}" if request.decision in {"reject", "drop"} else request.reason
        ),
        "resolved_at": now,
        "updated_at": now,
        "resolution_commit_id": commit_id,
        # Resolution history is not an authority or deletion receipt.  Once a
        # decision is committed it must not retain candidate plaintext, a
        # dictionary-attackable content hash, or source-location identifiers.
        "candidate": {},
        "source_commit_id": None,
        "source_short_term_id": None,
        "source_item_revision": None,
        "source_content_hash": None,
        "veracity": None,
        "impact": None,
        "permitted_uses": [],
    }
    review_ref = db_client.document(f"{collections.memory_review_queue}/{request.review_id}")
    transaction.set(review_ref, _firestore_data(redacted))
    if request.correction_record is not None:
        correction_id = request.correction_record.get("correction_id")
        if request.authority == "canonical_memory" or not isinstance(correction_id, str) or not correction_id.strip():
            raise CanonicalReviewResolutionConflict(
                "stale_review",
                "legacy review correction receipt is invalid",
                review_item=review_item,
            )
        correction_ref = db_client.document(f"{collections.user_root}/memory_corrections/{correction_id}")
        transaction.set(correction_ref, _firestore_data(request.correction_record))


def _privacy_tombstoned_evidence(evidence: MemoryEvidence, *, scrub_source_identity: bool = False) -> MemoryEvidence:
    """Retain only non-content lineage identity after a user privacy deletion."""
    return evidence.model_copy(
        update={
            "artifact_refs": [],
            "artifact_preservation": ArtifactPreservationState.deleted_by_user,
            "quote_refs": [],
            "content_hash": None,
            "source_id": None if scrub_source_identity else evidence.source_id,
            "source_version": None if scrub_source_identity else evidence.source_version,
            "conversation_id": None if scrub_source_identity else evidence.conversation_id,
            "lineage_id": None if scrub_source_identity else evidence.lineage_id,
            "source_state": SourceState.tombstoned,
            "source_state_reason": SourceStateReason.deleted_by_user,
            "provenance_visibility": ProvenanceVisibility.hidden,
            "redaction_status": RedactionStatus.tombstoned,
            "encryption_or_redaction_status": RedactionStatus.tombstoned,
            "patch_id": None,
            "commit_id": None,
            "client_device_id": None,
        }
    )


def _privacy_tombstoned_memory_item(
    item: MemoryItem,
    *,
    embedded_evidence: List[MemoryEvidence],
    now: datetime,
    commit_id: str,
    commit_sequence: int,
    account_generation: int,
) -> MemoryItem:
    """Build the one content-free canonical tombstone shape.

    Explicit memory deletion and empty conversation-source retraction must not
    drift: both can carry knowledge-ledger bodies and trigger action prompts in
    fields outside ``content``.  Keeping this scrubber shared makes every
    privacy tombstone clear the complete semantic payload.
    """

    return item.model_copy(
        update={
            "status": MemoryItemStatus.tombstoned,
            "source_state": SourceState.tombstoned,
            "content": None,
            "evidence": embedded_evidence,
            "sensitivity_labels": [],
            "promotion": None,
            "capture_device_ids": [],
            "primary_capture_device": None,
            "corroboration_count": 0,
            "last_corroborated_at": None,
            "half_life_days": None,
            "belief_class": None,
            "confidence": None,
            "subject_entity_id": None,
            "predicate": None,
            "arguments": {},
            "ledger_schema_version": None,
            "kind": MemoryKind.fact,
            "subject_scope": MemorySubjectScope.primary_user,
            "slot": None,
            "body": None,
            "valid_from": None,
            "valid_to": None,
            "curation_weight": 0,
            "trigger_condition": {},
            "intent_backed": False,
            "write_reason": None,
            "updated_at": max(now, item.updated_at),
            "version": item.version + 1,
            "item_revision": item.item_revision + 1,
            "ledger_commit_id": commit_id,
            "ledger_sequence": commit_sequence,
            "source_commit_id": commit_id,
            "source_commit_sequence": commit_sequence,
            "normalized_content_key": None,
            "content_hash": None,
            "account_generation": account_generation,
            "kg_extracted": False,
            "graph_ready": False,
            "graph_assertion_id": None,
            "graph_plan_hash": None,
        }
    )


@transactional
def _tombstone_memory_items_firestore_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
    reason: str,
    observed_control: MemoryControlState,
    expected_items: List[MemoryItem],
    preserved_evidence_ids: frozenset[str],
    deletion_gate_token: str,
    review_resolution: Optional[CanonicalReviewResolution],
) -> CanonicalMemoryTombstoneResult:
    if not reason.strip():
        raise ValueError("canonical privacy tombstone reason is required")
    expected_by_id = {item.memory_id: item for item in expected_items}
    if not expected_by_id or len(expected_by_id) != len(expected_items):
        raise CanonicalMemoryTombstoneConflict("privacy tombstone requires unique items")

    collections = MemoryCollections(uid=uid)
    assert_destructive_operation_transaction(
        transaction,
        db_client,
        uid=uid,
        kind="explicit_memory_deletion",
        token=deletion_gate_token,
    )
    review_item = _read_canonical_review_resolution(
        transaction=transaction,
        db_client=db_client,
        collections=collections,
        request=review_resolution,
    )
    control_ref = db_client.document(collections.memory_apply_control_state)
    control_snapshot = control_ref.get(transaction=transaction)
    if not getattr(control_snapshot, "exists", False):
        raise CanonicalMemoryTombstoneConflict("canonical memory control state is missing")
    control = parse_snapshot_strict(
        MemoryControlState,
        control_snapshot,
        payload_from_snapshot=_typed_doc,
    )
    if _control_fence(control) != _control_fence(observed_control):
        raise CanonicalMemoryTombstoneConflict("memory control changed during privacy tombstone")

    authoritative_items: List[MemoryItem] = []
    evidence_by_id: Dict[str, MemoryEvidence] = {}
    for memory_id in sorted(expected_by_id):
        item_ref = db_client.document(f"{collections.memory_items}/{memory_id}")
        item_snapshot = item_ref.get(transaction=transaction)
        if not getattr(item_snapshot, "exists", False):
            raise CanonicalMemoryTombstoneConflict(f"privacy tombstone item disappeared: {memory_id}")
        item = parse_snapshot_strict(MemoryItem, item_snapshot, payload_from_snapshot=_typed_doc)
        expected = expected_by_id[memory_id]
        if (
            item.uid != uid
            or item.status == MemoryItemStatus.tombstoned
            or item.item_revision != expected.item_revision
            or item.content_hash != expected.content_hash
            or item.canonical_memory_id != expected.canonical_memory_id
        ):
            raise CanonicalMemoryTombstoneConflict(f"privacy tombstone item changed: {memory_id}")
        authoritative_items.append(item)
        for embedded in item.evidence:
            if embedded.evidence_id in evidence_by_id:
                continue
            evidence_ref = db_client.document(f"{collections.memory_evidence}/{embedded.evidence_id}")
            evidence_snapshot = evidence_ref.get(transaction=transaction)
            if not getattr(evidence_snapshot, "exists", False):
                raise CanonicalMemoryTombstoneConflict(
                    f"privacy tombstone evidence disappeared: {embedded.evidence_id}"
                )
            evidence = parse_snapshot_strict(
                MemoryEvidence,
                evidence_snapshot,
                payload_from_snapshot=_typed_doc,
            )
            evidence_by_id[evidence.evidence_id] = evidence
    if review_resolution is not None:
        reviewed_item = next(
            (item for item in authoritative_items if item.memory_id == review_resolution.memory_id),
            None,
        )
        if reviewed_item is None:
            raise CanonicalReviewResolutionConflict(
                "stale_review",
                "canonical review target is outside the privacy transaction",
                review_item=review_item,
            )
        _validate_canonical_review_source(
            review_item=review_item,
            request=review_resolution,
            item=reviewed_item,
        )

    logical_payload = {
        "decision": "delete",
        "reason": reason,
        "items": [
            {
                "memory_id": item.memory_id,
                "item_revision": item.item_revision,
            }
            for item in authoritative_items
        ],
    }
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.deletion,
        source_packet_id=f"privacy_delete:{reason}",
        target_memory_id=None,
        # Evidence/source identities are intentionally absent from the durable
        # operation. The authoritative tombstone is already content-free and
        # the bounded anti-resurrection receipt below expires after 30 days.
        evidence_ids=[],
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        # The transaction validates the exact control fence above. Persisting
        # the old content-derived head would retain a dictionary oracle after
        # explicit deletion.
        observed_head_commit_id=None,
    )
    operation_ref = db_client.document(f"{collections.memory_operations}/{operation.operation_id}")
    if getattr(operation_ref.get(transaction=transaction), "exists", False):
        raise CanonicalMemoryTombstoneConflict("privacy tombstone operation already exists")

    commit_id = (
        "commit_"
        + deterministic_contract_id(
            "memory-privacy-epoch",
            {
                "uid": uid,
                "deletion_gate_token": deletion_gate_token,
                "commit_sequence": control.commit_sequence + 1,
            },
        )[:32]
    )
    committed_control = control.advance_head(commit_id).model_copy(
        update={
            "projection_watermark_commit_id": None,
            "vector_watermark_commit_id": None,
        }
    )
    now = datetime.now(timezone.utc)
    embedded_tombstoned_evidence = {
        evidence_id: _privacy_tombstoned_evidence(evidence, scrub_source_identity=True)
        for evidence_id, evidence in evidence_by_id.items()
    }
    tombstoned_evidence = {
        evidence_id: evidence
        for evidence_id, evidence in embedded_tombstoned_evidence.items()
        if evidence_id not in preserved_evidence_ids
    }
    tombstoned_items: List[MemoryItem] = []
    events: List[MemoryOutboxEvent] = []
    for item in authoritative_items:
        embedded_evidence = [embedded_tombstoned_evidence[evidence.evidence_id] for evidence in item.evidence]
        tombstoned = _privacy_tombstoned_memory_item(
            item,
            embedded_evidence=embedded_evidence,
            now=now,
            commit_id=commit_id,
            commit_sequence=committed_control.commit_sequence,
            account_generation=committed_control.account_generation,
        )
        tombstoned_items.append(tombstoned)
        events.extend(
            _privacy_delete_events(
                uid=uid,
                item=tombstoned,
                parent_control=control,
                committed_control=committed_control,
                operation_id=operation.operation_id,
                reason=reason,
                now=now,
            )
        )

    # Each item writes its authoritative tombstone plus two durable projection
    # delete events. The graph assertion is derived and is deleted by that
    # outbox path after reads have already been fenced by this tombstone.
    mutation_count = (
        len(tombstoned_evidence) + 4 + (4 * len(tombstoned_items)) + (1 if review_resolution is not None else 0)
    )
    if mutation_count > _MAX_FIRESTORE_TRANSACTION_MUTATIONS:
        raise CanonicalMemoryTombstoneLimitError(
            "canonical memory batch exceeds Firestore's 500-mutation transaction limit"
        )

    committed_operation = operation.mark_committed(
        commit_id,
        committed_sequence=committed_control.commit_sequence,
        committed_memory_item_ids=[item.memory_id for item in tombstoned_items],
        committed_outbox_event_ids=[event.event_id for event in events],
    )
    result = ApplyResult(
        status=ApplyStatus.committed,
        control_state=committed_control,
        operation=committed_operation,
        memory_items=tombstoned_items,
        outbox_events=events,
    )

    for evidence in tombstoned_evidence.values():
        evidence_ref = db_client.document(f"{collections.memory_evidence}/{evidence.evidence_id}")
        transaction.set(evidence_ref, _firestore_data(evidence))
    for item in tombstoned_items:
        receipt_id = privacy_deletion_receipt_id(uid, item.memory_id)
        receipt_ref = db_client.document(f"{collections.memory_deletion_receipts}/{receipt_id}")
        transaction.set(
            receipt_ref,
            {
                "schema_version": "memory_deletion_receipt.v2",
                "uid": uid,
                "receipt_id": receipt_id,
                "privacy_epoch_commit_id": committed_control.head_commit_id,
                "deleted_at": now,
                "expires_at": now + timedelta(days=30),
            },
        )
    _write_apply_result(
        transaction=transaction,
        db_client=db_client,
        collections=collections,
        operation_ref=operation_ref,
        result=result,
    )
    _write_canonical_review_resolution(
        transaction=transaction,
        db_client=db_client,
        collections=collections,
        request=review_resolution,
        review_item=review_item,
        commit_id=committed_control.head_commit_id,
        now=now,
    )
    return CanonicalMemoryTombstoneResult(
        control_state=committed_control,
        memory_items=tombstoned_items,
        tombstoned_evidence_ids=sorted(tombstoned_evidence),
    )


def _item_has_conversation_source(item: MemoryItem, conversation_id: str) -> bool:
    return any(
        evidence.source_id == conversation_id or evidence.conversation_id == conversation_id
        for evidence in item.evidence
    )


def _replacement_delete_events(
    *,
    uid: str,
    item: MemoryItem,
    parent_control: MemoryControlState,
    replacement_control: MemoryControlState,
    operation_id: str,
    now: datetime,
) -> List[MemoryOutboxEvent]:
    reason = "conversation_reprocess_retract"
    events: List[MemoryOutboxEvent] = []
    for event_type in (MemoryOutboxEventType.projection_sync, MemoryOutboxEventType.vector_sync):
        event_id = (
            "evt_"
            + deterministic_contract_id(
                "memory-outbox",
                {
                    "event_type": event_type.value,
                    "commit_id": replacement_control.head_commit_id,
                    "memory_id": item.memory_id,
                    "operation_id": operation_id,
                },
            )[:32]
        )
        events.append(
            MemoryOutboxEvent(
                event_id=event_id,
                uid=uid,
                event_type=event_type,
                commit_id=replacement_control.head_commit_id,
                parent_commit_id=parent_control.head_commit_id,
                commit_sequence=replacement_control.commit_sequence,
                memory_id=item.memory_id,
                operation_id=operation_id,
                account_generation=replacement_control.account_generation,
                source_generation=replacement_control.source_generation,
                payload={
                    "memory_id": item.memory_id,
                    "tier": item.tier.value,
                    "action": "delete",
                    "item_revision": item.item_revision,
                    "content_hash": item.content_hash,
                    "reason": reason,
                },
                available_at=now,
            )
        )
    return events


def _replacement_reactivation_events(
    *,
    uid: str,
    item: MemoryItem,
    parent_control: MemoryControlState,
    replacement_control: MemoryControlState,
    operation_id: str,
    now: datetime,
) -> List[MemoryOutboxEvent]:
    has_restricted_sensitivity = bool(set(item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS))
    projection_eligible = (
        item.status == MemoryItemStatus.active
        and item.processing_state.value == "processed"
        and (item.promotion or {}).get("user_review") is not False
        and not has_restricted_sensitivity
    )
    action = "upsert" if projection_eligible else "delete"
    events: List[MemoryOutboxEvent] = []
    for event_type in (MemoryOutboxEventType.projection_sync, MemoryOutboxEventType.vector_sync):
        event_id = (
            "evt_"
            + deterministic_contract_id(
                "memory-outbox",
                {
                    "event_type": event_type.value,
                    "commit_id": replacement_control.head_commit_id,
                    "memory_id": item.memory_id,
                    "operation_id": operation_id,
                },
            )[:32]
        )
        events.append(
            MemoryOutboxEvent(
                event_id=event_id,
                uid=uid,
                event_type=event_type,
                commit_id=replacement_control.head_commit_id,
                parent_commit_id=parent_control.head_commit_id,
                commit_sequence=replacement_control.commit_sequence,
                memory_id=item.memory_id,
                operation_id=operation_id,
                account_generation=replacement_control.account_generation,
                source_generation=replacement_control.source_generation,
                payload={
                    "memory_id": item.memory_id,
                    "tier": item.tier.value,
                    "action": action,
                    "item_revision": item.item_revision,
                    "content_hash": item.content_hash,
                    "reason": "independent_lineage_source_survived",
                },
                available_at=now,
            )
        )
    return events


def _reactivate_replacement_lineage_item(
    *,
    item: MemoryItem,
    item_snapshot: Any,
    replacement_control: MemoryControlState,
    now: datetime,
) -> tuple[MemoryItem, MemoryGraphAssertion]:
    raw_graph_plan = (item.promotion or {}).get("graph_plan")
    if not isinstance(raw_graph_plan, dict):
        raise ConversationSourceReplacementConflict(
            f"superseded lineage item has no restorable graph plan: {item.memory_id}"
        )
    try:
        graph_plan = parse_snapshot_strict(
            PromotionGraphPlan,
            item_snapshot,
            payload_from_snapshot=lambda _snapshot: raw_graph_plan,
        )
    except Exception as exc:
        raise ConversationSourceReplacementConflict(
            f"superseded lineage item has an invalid graph plan: {item.memory_id}"
        ) from exc
    if not item.content_hash:
        raise ConversationSourceReplacementConflict(
            f"superseded lineage item has no restorable content hash: {item.memory_id}"
        )

    item_revision = item.item_revision + 1
    assertion = build_memory_graph_assertion(
        uid=item.uid,
        memory_id=item.memory_id,
        item_revision=item_revision,
        content_hash=item.content_hash,
        evidence_ids=[evidence.evidence_id for evidence in item.evidence],
        graph_plan=graph_plan,
        commit_id=replacement_control.head_commit_id,
        commit_sequence=replacement_control.commit_sequence,
        created_at=now,
    )
    payload = item.model_dump(mode="python")
    payload.update(
        {
            "canonical_memory_id": None,
            "status": MemoryItemStatus.active,
            "superseded_by": None,
            "updated_at": max(now, item.updated_at),
            "ledger_commit_id": replacement_control.head_commit_id,
            "ledger_sequence": replacement_control.commit_sequence,
            "version": item.version + 1,
            "item_revision": item_revision,
            "account_generation": replacement_control.account_generation,
            "subject_entity_id": graph_plan.subject_entity_id,
            "predicate": graph_plan.predicate,
            "arguments": graph_plan.arguments,
            "graph_ready": True,
            "graph_assertion_id": assertion.assertion_id,
            "graph_plan_hash": graph_plan.plan_hash,
            "kg_extracted": True,
        }
    )
    reactivated = parse_snapshot_strict(
        MemoryItem,
        item_snapshot,
        payload_from_snapshot=lambda _snapshot: payload,
    )
    return reactivated, assertion


def _replacement_barrier_events(
    *,
    uid: str,
    parent_control: MemoryControlState,
    replacement_control: MemoryControlState,
    operation_id: str,
    now: datetime,
) -> List[MemoryOutboxEvent]:
    return [
        MemoryOutboxEvent(
            event_id=(
                "evt_"
                + deterministic_contract_id(
                    "memory-outbox",
                    {
                        "event_type": event_type.value,
                        "commit_id": replacement_control.head_commit_id,
                        "memory_id": None,
                        "operation_id": operation_id,
                    },
                )[:32]
            ),
            uid=uid,
            event_type=event_type,
            commit_id=replacement_control.head_commit_id,
            parent_commit_id=parent_control.head_commit_id,
            commit_sequence=replacement_control.commit_sequence,
            memory_id=None,
            operation_id=operation_id,
            account_generation=replacement_control.account_generation,
            source_generation=replacement_control.source_generation,
            payload={"action": "barrier"},
            available_at=now,
        )
        for event_type in (MemoryOutboxEventType.projection_sync, MemoryOutboxEventType.vector_sync)
    ]


def _refresh_replacement_result(
    result: ApplyResult,
    *,
    prior_item: Optional[MemoryItem],
    prior_was_active_source: bool,
) -> ApplyResult:
    if prior_item is None or len(result.memory_items) != 1:
        return result
    created = result.memory_items[0]
    revision_increment = 2 if prior_was_active_source else 1
    refreshed = created.model_copy(
        update={
            "version": prior_item.version + revision_increment,
            "item_revision": prior_item.item_revision + revision_increment,
            "updated_at": max(created.updated_at, prior_item.updated_at),
        }
    )
    refreshed_events = [
        event.model_copy(
            update={
                "payload": {
                    **event.payload,
                    "item_revision": refreshed.item_revision,
                    "content_hash": refreshed.content_hash,
                }
            }
        )
        for event in result.outbox_events
    ]
    return result.model_copy(
        update={
            "memory_items": [refreshed],
            "outbox_events": refreshed_events,
        }
    )


def _replacement_mutation_count(
    *,
    tombstoned_evidence_count: int,
    old_item_count: int,
    overlapping_item_count: int,
    new_evidence_count: int,
    results: List[ApplyResult],
) -> int:
    old_only_count = old_item_count - overlapping_item_count
    count = tombstoned_evidence_count
    count += old_only_count * 2  # item set + graph assertion delete
    count += new_evidence_count
    if not results:
        return count + 1  # source-generation control update
    for result in results:
        count += 4  # operation + control + state head + commit
        count += len(result.memory_items) * 2  # item + graph assertion set/delete
        count += len(result.outbox_events)
        count += sum(
            1
            for item in result.memory_items
            if item.status == MemoryItemStatus.active and (item.promotion or {}).get("route") == "review"
        )
    return count


@transactional
def _replace_conversation_source_firestore_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
    conversation_id: str,
    replacement_id: str,
    replacement_digest: str,
    replacement_operation: MemoryOperation,
    observed_control: MemoryControlState,
    expected_source_items: List[MemoryItem],
    expected_reactivation_items: List[MemoryItem],
    writes: List[CanonicalApplyWrite],
    deletion_gate_token: str | None,
) -> ConversationSourceReplacementResult:
    collections = MemoryCollections(uid=uid)
    if writes:
        assert_no_destructive_operation_transaction(transaction, db_client, uid=uid)
    else:
        if deletion_gate_token is None:
            raise ConversationSourceReplacementConflict("empty replacement requires privacy gate authority")
        assert_destructive_operation_transaction(
            transaction,
            db_client,
            uid=uid,
            kind="explicit_memory_deletion",
            token=deletion_gate_token,
        )
    control_ref = db_client.document(collections.memory_apply_control_state)
    control_snapshot = control_ref.get(transaction=transaction)
    if getattr(control_snapshot, "exists", False):
        control = parse_snapshot_strict(MemoryControlState, control_snapshot, payload_from_snapshot=_typed_doc)
    else:
        control = MemoryControlState(
            uid=uid,
            head_commit_id="head0",
            account_generation=1,
            source_generation=1,
        )

    replacement_ref = db_client.document(f"{collections.memory_source_replacements}/{replacement_id}")
    replacement_snapshot = replacement_ref.get(transaction=transaction)
    if getattr(replacement_snapshot, "exists", False):
        receipt = parse_snapshot_strict(
            ConversationSourceReplacementReceipt,
            replacement_snapshot,
            payload_from_snapshot=_typed_doc,
        )
        if (
            receipt.uid != uid
            or receipt.conversation_id != conversation_id
            or receipt.replacement_digest != replacement_digest
        ):
            raise ConversationSourceReplacementConflict("replacement receipt identity mismatch")
        receipt_is_current = (
            receipt.control_state.account_generation == control.account_generation
            and receipt.control_state.source_generation == control.source_generation
        )
        expected_source_version = f"source_generation:{receipt.control_state.source_generation}"
        for memory_id in receipt.committed_memory_ids:
            item_snapshot = db_client.document(f"{collections.memory_items}/{memory_id}").get(transaction=transaction)
            if not getattr(item_snapshot, "exists", False):
                receipt_is_current = False
                break
            item = parse_snapshot_strict(MemoryItem, item_snapshot, payload_from_snapshot=_typed_doc)
            if (
                item.uid != uid
                or item.status != MemoryItemStatus.active
                or item.source_state != SourceState.active
                or not any(
                    evidence.source_state == SourceState.active
                    and evidence.source_version == expected_source_version
                    and (evidence.source_id == conversation_id or evidence.conversation_id == conversation_id)
                    for evidence in item.evidence
                )
            ):
                receipt_is_current = False
                break
        for memory_id in receipt.reactivated_memory_ids:
            item_snapshot = db_client.document(f"{collections.memory_items}/{memory_id}").get(transaction=transaction)
            if not getattr(item_snapshot, "exists", False):
                receipt_is_current = False
                break
            item = parse_snapshot_strict(MemoryItem, item_snapshot, payload_from_snapshot=_typed_doc)
            if (
                item.uid != uid
                or item.status != MemoryItemStatus.active
                or item.source_state != SourceState.active
                or item.canonical_memory_id is not None
                or item.superseded_by is not None
            ):
                receipt_is_current = False
                break
        if receipt_is_current:
            return ConversationSourceReplacementResult(
                control_state=control,
                retracted_memory_ids=receipt.retracted_memory_ids,
                committed_memory_ids=receipt.committed_memory_ids,
                reactivated_memory_ids=receipt.reactivated_memory_ids,
                tombstoned_evidence_ids=receipt.tombstoned_evidence_ids,
            )

    if _control_fence(control) != _control_fence(observed_control):
        raise ConversationSourceReplacementConflict("memory control changed during conversation replacement")
    replacement_writer_classes = {
        (
            MemoryWriterClass.ledger
            if write.patch_payload.get("ledger_schema_version") == "knowledge_ledger.v1"
            else MemoryWriterClass.compatibility
        )
        for write in writes
    }
    if not replacement_writer_classes:
        replacement_writer_classes = {
            (
                MemoryWriterClass.ledger
                if item.ledger_schema_version == "knowledge_ledger.v1"
                else MemoryWriterClass.compatibility
            )
            for item in expected_source_items
        }
    if len(replacement_writer_classes) > 1:
        raise ConversationSourceReplacementConflict("conversation replacement mixes writer authorities")
    try:
        require_writer_admitted(
            control,
            next(iter(replacement_writer_classes), MemoryWriterClass.compatibility),
        )
    except WriterAdmissionError as exc:
        raise ConversationSourceReplacementConflict(str(exc)) from exc
    if (
        replacement_operation.uid != uid
        or replacement_operation.operation_type != MemoryOperationType.source_replacement
        or replacement_operation.source_packet_id != conversation_id
        or replacement_operation.account_generation != control.account_generation
        or replacement_operation.source_generation != control.source_generation + 1
        or replacement_operation.observed_head_commit_id != control.head_commit_id
        or replacement_operation.logical_payload.metadata.get("replacement_id") != replacement_id
        or replacement_operation.logical_payload.metadata.get("replacement_digest") != replacement_digest
    ):
        raise ConversationSourceReplacementConflict("source replacement operation mismatch")
    replacement_operation_ref = db_client.document(
        f"{collections.memory_operations}/{replacement_operation.operation_id}"
    )
    if getattr(replacement_operation_ref.get(transaction=transaction), "exists", False):
        raise ConversationSourceReplacementConflict("source replacement operation already exists")

    expected_by_id = {item.memory_id: item for item in expected_source_items}
    if len(expected_by_id) != len(expected_source_items):
        raise ConversationSourceReplacementConflict("duplicate expected source memory id")

    authoritative_by_id: Dict[str, MemoryItem] = {}
    evidence_by_old_item: Dict[str, List[MemoryEvidence]] = {}
    old_evidence_ids: set[str] = set()
    for memory_id in sorted(expected_by_id):
        item_ref = db_client.document(f"{collections.memory_items}/{memory_id}")
        item_snapshot = item_ref.get(transaction=transaction)
        if not getattr(item_snapshot, "exists", False):
            raise ConversationSourceReplacementConflict(f"source memory disappeared: {memory_id}")
        item = parse_snapshot_strict(MemoryItem, item_snapshot, payload_from_snapshot=_typed_doc)
        expected = expected_by_id[memory_id]
        if (
            item.uid != uid
            or item.status == MemoryItemStatus.tombstoned
            or item.status != expected.status
            or item.source_state != SourceState.active
            or item.source_state != expected.source_state
            or item.item_revision != expected.item_revision
            or item.content_hash != expected.content_hash
            or not _item_has_conversation_source(item, conversation_id)
        ):
            raise ConversationSourceReplacementConflict(f"source memory changed: {memory_id}")
        authoritative_by_id[memory_id] = item
        item_evidence: List[MemoryEvidence] = []
        for embedded in item.evidence:
            evidence_ref = db_client.document(f"{collections.memory_evidence}/{embedded.evidence_id}")
            evidence_snapshot = evidence_ref.get(transaction=transaction)
            if not getattr(evidence_snapshot, "exists", False):
                raise ConversationSourceReplacementConflict(f"source evidence disappeared: {embedded.evidence_id}")
            evidence = parse_snapshot_strict(
                MemoryEvidence,
                evidence_snapshot,
                payload_from_snapshot=_typed_doc,
            )
            if evidence.source_id != conversation_id and evidence.conversation_id != conversation_id:
                raise ConversationSourceReplacementConflict(f"source evidence changed: {embedded.evidence_id}")
            item_evidence.append(evidence)
            old_evidence_ids.add(evidence.evidence_id)
        evidence_by_old_item[memory_id] = item_evidence

    terminal_source_ids = {
        item.memory_id
        for item in authoritative_by_id.values()
        if item.status == MemoryItemStatus.active and not (item.canonical_memory_id or item.superseded_by or "").strip()
    }
    expected_reactivation_by_id = {item.memory_id: item for item in expected_reactivation_items}
    if len(expected_reactivation_by_id) != len(expected_reactivation_items):
        raise ConversationSourceReplacementConflict("duplicate expected lineage reactivation id")
    if set(expected_reactivation_by_id).intersection(authoritative_by_id):
        raise ConversationSourceReplacementConflict("source item cannot also be a lineage reactivation")

    authoritative_reactivation_by_id: Dict[str, tuple[MemoryItem, Any]] = {}
    for memory_id in sorted(expected_reactivation_by_id):
        item_ref = db_client.document(f"{collections.memory_items}/{memory_id}")
        item_snapshot = item_ref.get(transaction=transaction)
        if not getattr(item_snapshot, "exists", False):
            raise ConversationSourceReplacementConflict(f"superseded lineage item disappeared: {memory_id}")
        item = parse_snapshot_strict(MemoryItem, item_snapshot, payload_from_snapshot=_typed_doc)
        expected = expected_reactivation_by_id[memory_id]
        canonical_target = (item.canonical_memory_id or item.superseded_by or "").strip()
        if (
            item.uid != uid
            or item.status != MemoryItemStatus.superseded
            or item.status != expected.status
            or item.source_state != SourceState.active
            or item.source_state != expected.source_state
            or item.item_revision != expected.item_revision
            or item.content_hash != expected.content_hash
            or item.canonical_memory_id != expected.canonical_memory_id
            or item.superseded_by != expected.superseded_by
            or canonical_target not in terminal_source_ids
            or _item_has_conversation_source(item, conversation_id)
            or not item.evidence
        ):
            raise ConversationSourceReplacementConflict(f"superseded lineage item changed: {memory_id}")
        for embedded in item.evidence:
            evidence_ref = db_client.document(f"{collections.memory_evidence}/{embedded.evidence_id}")
            evidence_snapshot = evidence_ref.get(transaction=transaction)
            if not getattr(evidence_snapshot, "exists", False):
                raise ConversationSourceReplacementConflict(
                    f"superseded lineage evidence disappeared: {embedded.evidence_id}"
                )
            evidence = parse_snapshot_strict(
                MemoryEvidence,
                evidence_snapshot,
                payload_from_snapshot=_typed_doc,
            )
            if evidence != embedded or evidence.source_state != SourceState.active:
                raise ConversationSourceReplacementConflict(
                    f"superseded lineage evidence changed: {embedded.evidence_id}"
                )
        authoritative_reactivation_by_id[memory_id] = (item, item_snapshot)

    new_memory_ids: List[str] = []
    prior_new_items: Dict[str, MemoryItem] = {}
    new_evidence_ids: set[str] = set()
    expected_source_generation = control.source_generation + 1
    expected_source_version = f"source_generation:{expected_source_generation}"
    for write in writes:
        operation = write.operation
        if (
            operation.uid != uid
            or operation.account_generation != control.account_generation
            or operation.source_generation != expected_source_generation
            or operation.source_packet_id != conversation_id
        ):
            raise ConversationSourceReplacementConflict("replacement operation generation/source mismatch")
        operation_ref = db_client.document(f"{collections.memory_operations}/{operation.operation_id}")
        if getattr(operation_ref.get(transaction=transaction), "exists", False):
            raise ConversationSourceReplacementConflict("replacement operation already exists")
        raw_memory_id = write.patch_payload.get("new_memory_id")
        if not isinstance(raw_memory_id, str) or not raw_memory_id.strip():
            raise MemoryFirestoreApplyError("conversation replacement writes require new_memory_id")
        memory_id = raw_memory_id.strip()
        if memory_id in new_memory_ids:
            raise MemoryFirestoreApplyError("conversation replacement contains duplicate memory ids")
        new_memory_ids.append(memory_id)
        if memory_id not in authoritative_by_id:
            memory_ref = db_client.document(f"{collections.memory_items}/{memory_id}")
            memory_snapshot = memory_ref.get(transaction=transaction)
            if getattr(memory_snapshot, "exists", False):
                prior_item = parse_snapshot_strict(
                    MemoryItem,
                    memory_snapshot,
                    payload_from_snapshot=_typed_doc,
                )
                if (
                    prior_item.uid != uid
                    or not _item_has_conversation_source(prior_item, conversation_id)
                    or prior_item.status == MemoryItemStatus.active
                ):
                    raise ConversationSourceReplacementConflict(
                        f"replacement target belongs to unrelated state: {memory_id}"
                    )
                prior_new_items[memory_id] = prior_item
            receipt_ref = db_client.document(
                f"{collections.memory_deletion_receipts}/{privacy_deletion_receipt_id(uid, memory_id)}"
            )
            if getattr(receipt_ref.get(transaction=transaction), "exists", False):
                raise ConversationSourceReplacementConflict("replacement target is privacy-deleted")
        if not write.evidence:
            raise MemoryFirestoreApplyError("conversation replacement writes require evidence")
        for evidence in write.evidence:
            if (
                evidence.evidence_id in new_evidence_ids
                or evidence.evidence_id in old_evidence_ids
                or evidence.source_id != conversation_id
                or evidence.conversation_id != conversation_id
                or evidence.source_version != expected_source_version
                or evidence.source_state != SourceState.active
            ):
                raise MemoryFirestoreApplyError("invalid conversation replacement evidence")
            new_evidence_ids.add(evidence.evidence_id)
            evidence_ref = db_client.document(f"{collections.memory_evidence}/{evidence.evidence_id}")
            if getattr(evidence_ref.get(transaction=transaction), "exists", False):
                raise ConversationSourceReplacementConflict("replacement evidence already exists")
    if sorted(replacement_operation.logical_payload.metadata.get("new_memory_ids") or []) != sorted(new_memory_ids):
        raise ConversationSourceReplacementConflict("source replacement manifest does not match writes")

    bumped_control = control.model_copy(
        update={
            "source_generation": expected_source_generation,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    if writes:
        replacement_commit_id = bumped_control.next_commit_id(replacement_operation.operation_id)
        replacement_control = bumped_control.advance_head(replacement_commit_id)
    else:
        assert deletion_gate_token is not None
        replacement_commit_id = (
            "commit_"
            + deterministic_contract_id(
                "memory-privacy-epoch",
                {
                    "uid": uid,
                    "deletion_gate_token": deletion_gate_token,
                    "commit_sequence": bumped_control.commit_sequence + 1,
                },
            )[:32]
        )
        replacement_control = bumped_control.advance_head(replacement_commit_id).model_copy(
            update={
                "projection_watermark_commit_id": None,
                "vector_watermark_commit_id": None,
            }
        )
    working_control = replacement_control
    results: List[ApplyResult] = []
    for write, memory_id in zip(writes, new_memory_ids):
        authoritative_payload = dict(write.patch_payload)
        authoritative_payload["evidence"] = write.evidence
        result = apply_long_term_patch_transaction(
            control_state=working_control,
            operation=write.operation,
            patch_payload=authoritative_payload,
        )
        if result.status != ApplyStatus.committed:
            raise ConversationSourceReplacementConflict(
                f"replacement apply failed: {result.status.value} ({result.reason})"
            )
        prior = authoritative_by_id.get(memory_id) or prior_new_items.get(memory_id)
        result = _refresh_replacement_result(
            result,
            prior_item=prior,
            prior_was_active_source=memory_id in authoritative_by_id,
        )
        results.append(result)
        working_control = result.control_state

    now = datetime.now(timezone.utc)
    tombstoned_items: Dict[str, MemoryItem] = {}
    tombstoned_evidence: Dict[str, MemoryEvidence] = {}
    delete_events: List[MemoryOutboxEvent] = []
    scrub_source_identity = not writes
    for memory_id, item in authoritative_by_id.items():
        next_evidence: List[MemoryEvidence] = []
        for evidence in evidence_by_old_item[memory_id]:
            scrubbed = _privacy_tombstoned_evidence(
                evidence,
                scrub_source_identity=scrub_source_identity,
            )
            tombstoned_evidence[scrubbed.evidence_id] = scrubbed
            next_evidence.append(scrubbed)
        tombstoned = _privacy_tombstoned_memory_item(
            item,
            embedded_evidence=next_evidence,
            now=now,
            commit_id=replacement_control.head_commit_id,
            commit_sequence=replacement_control.commit_sequence,
            account_generation=replacement_control.account_generation,
        )
        tombstoned_items[memory_id] = tombstoned
        delete_events.extend(
            _replacement_delete_events(
                uid=uid,
                item=tombstoned,
                parent_control=control,
                replacement_control=replacement_control,
                operation_id=replacement_operation.operation_id,
                now=now,
            )
        )

    reactivated_items: List[MemoryItem] = []
    reactivated_assertions: List[MemoryGraphAssertion] = []
    reactivation_events: List[MemoryOutboxEvent] = []
    new_memory_id_set = set(new_memory_ids)
    for item, item_snapshot in authoritative_reactivation_by_id.values():
        canonical_target = (item.canonical_memory_id or item.superseded_by or "").strip()
        if canonical_target in new_memory_id_set:
            continue
        reactivated, assertion = _reactivate_replacement_lineage_item(
            item=item,
            item_snapshot=item_snapshot,
            replacement_control=replacement_control,
            now=now,
        )
        reactivated_items.append(reactivated)
        reactivated_assertions.append(assertion)
        reactivation_events.extend(
            _replacement_reactivation_events(
                uid=uid,
                item=reactivated,
                parent_control=control,
                replacement_control=replacement_control,
                operation_id=replacement_operation.operation_id,
                now=now,
            )
        )

    barrier_events = _replacement_barrier_events(
        uid=uid,
        parent_control=control,
        replacement_control=replacement_control,
        operation_id=replacement_operation.operation_id,
        now=now,
    )
    replacement_outbox_events = [*barrier_events, *delete_events, *reactivation_events]
    committed_replacement_operation = replacement_operation.mark_committed(
        replacement_control.head_commit_id,
        committed_sequence=replacement_control.commit_sequence,
        committed_memory_item_ids=sorted(
            set(tombstoned_items).union(new_memory_ids).union(item.memory_id for item in reactivated_items)
        ),
        committed_outbox_event_ids=[event.event_id for event in replacement_outbox_events],
    )
    replacement_apply_result = ApplyResult(
        status=ApplyStatus.committed,
        control_state=replacement_control,
        operation=committed_replacement_operation,
        memory_items=reactivated_items,
        graph_assertions=reactivated_assertions,
        outbox_events=replacement_outbox_events,
    )

    mutation_count = _replacement_mutation_count(
        tombstoned_evidence_count=len(tombstoned_evidence),
        old_item_count=len(tombstoned_items),
        overlapping_item_count=len(set(tombstoned_items).intersection(new_memory_ids)),
        new_evidence_count=sum(len(write.evidence) for write in writes),
        results=[replacement_apply_result, *results],
    )
    mutation_count += 1  # committed replacement receipt
    if not writes:
        mutation_count += len(tombstoned_items)  # opaque anti-resurrection receipts
    if mutation_count > _MAX_FIRESTORE_TRANSACTION_MUTATIONS:
        raise ConversationSourceReplacementLimitError(
            "conversation source replacement exceeds Firestore's 500-mutation transaction limit"
        )

    # No writes occur before the complete source/control/operation validation
    # and mutation preflight above.
    for evidence in tombstoned_evidence.values():
        evidence_ref = db_client.document(f"{collections.memory_evidence}/{evidence.evidence_id}")
        transaction.set(evidence_ref, _firestore_data(evidence))
    for write in writes:
        for evidence in write.evidence:
            evidence_ref = db_client.document(f"{collections.memory_evidence}/{evidence.evidence_id}")
            transaction.set(evidence_ref, _firestore_data(evidence))
    for memory_id, item in tombstoned_items.items():
        if memory_id not in new_memory_ids:
            item_ref = db_client.document(f"{collections.memory_items}/{memory_id}")
            transaction.set(item_ref, _firestore_data(item))
            assertion_ref = db_client.document(f"{collections.memory_graph_assertions}/{memory_id}")
            transaction.delete(assertion_ref)
        if not writes:
            receipt_id = privacy_deletion_receipt_id(uid, memory_id)
            transaction.set(
                db_client.document(f"{collections.memory_deletion_receipts}/{receipt_id}"),
                {
                    "schema_version": "memory_deletion_receipt.v2",
                    "uid": uid,
                    "receipt_id": receipt_id,
                    "privacy_epoch_commit_id": replacement_control.head_commit_id,
                    "deleted_at": now,
                    "expires_at": now + timedelta(days=30),
                },
            )
    for result in [replacement_apply_result, *results]:
        operation_ref = db_client.document(f"{collections.memory_operations}/{result.operation.operation_id}")
        _write_apply_result(
            transaction=transaction,
            db_client=db_client,
            collections=collections,
            operation_ref=operation_ref,
            result=result,
        )
    receipt = ConversationSourceReplacementReceipt(
        replacement_id=replacement_id,
        replacement_digest=replacement_digest,
        uid=uid,
        conversation_id=conversation_id,
        operation_id=committed_replacement_operation.operation_id,
        control_state=working_control,
        retracted_memory_ids=sorted(tombstoned_items),
        committed_memory_ids=new_memory_ids,
        reactivated_memory_ids=sorted(item.memory_id for item in reactivated_items),
        tombstoned_evidence_ids=sorted(old_evidence_ids),
        committed_at=now,
    )
    transaction.set(replacement_ref, _firestore_data(receipt))

    return ConversationSourceReplacementResult(
        control_state=working_control,
        retracted_memory_ids=sorted(tombstoned_items),
        committed_memory_ids=new_memory_ids,
        reactivated_memory_ids=sorted(item.memory_id for item in reactivated_items),
        tombstoned_evidence_ids=sorted(old_evidence_ids),
    )


def atomic_bump_source_generation(uid: str, *, db_client: Any) -> MemoryControlState:
    """Atomically advance canonical apply ``source_generation`` (Q7 reprocess)."""
    transaction = db_client.transaction()
    return _atomic_bump_source_generation_transaction(transaction, db_client, uid)


@transactional
def _atomic_bump_source_generation_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
) -> MemoryControlState:
    now = datetime.now(timezone.utc)
    collections = MemoryCollections(uid=uid)
    control_ref = db_client.document(collections.memory_apply_control_state)
    snapshot = control_ref.get(transaction=transaction)
    if not getattr(snapshot, "exists", False):
        control = MemoryControlState(
            uid=uid,
            head_commit_id="head0",
            account_generation=1,
            source_generation=1,
            updated_at=now,
        )
    else:
        control = parse_snapshot_strict(MemoryControlState, snapshot, payload_from_snapshot=_typed_doc)
    try:
        require_writer_admitted(control, MemoryWriterClass.compatibility)
    except WriterAdmissionError as exc:
        raise MemoryFirestoreApplyError(str(exc)) from exc
    bumped = control.model_copy(
        update={
            "source_generation": control.source_generation + 1,
            "updated_at": now,
        }
    )
    transaction.set(control_ref, _firestore_data(bumped))
    return bumped


@transactional
def _apply_long_term_patch_firestore_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
    operation_id: str,
    patch_payload: Dict[str, Any],
    proposed_operation: Optional[MemoryOperation],
    proposed_evidence: Optional[List[MemoryEvidence]],
    review_resolution: Optional[CanonicalReviewResolution],
    required_source_item: Optional[MemoryItem],
    ledger_reopen_receipt: Optional[MemoryLedgerReopenReceipt],
    trigger_feedback_receipt: Optional[JITTriggerFeedbackReceipt],
    allow_ledger_migration: bool = False,
    direct_user_authorized: bool = False,
) -> ApplyResult:
    collections = MemoryCollections(uid=uid)
    # Canonical writes and destructive privacy cleanup share the same
    # account-wide fence.  Without this transactional read, a delayed legacy
    # review acceptance could recreate content after a tombstone committed but
    # before its required review/correction scrub completed.
    assert_no_destructive_operation_transaction(transaction, db_client, uid=uid)
    # The deletion authority must be part of this very transaction, not only a
    # best-effort preflight.  Otherwise a wipe can race a canonical apply and
    # the apply can recreate an item after the wipe's inventory was read.
    # Reading the marker here makes Firestore retry the transaction when the
    # deletion lifecycle changes, and a non-restoring marker fails closed.
    deletion_ref = db_client.document(f"account_deletions/{uid}")
    deletion_snapshot = deletion_ref.get(transaction=transaction)
    deletion_payload = deletion_snapshot.to_dict() if getattr(deletion_snapshot, "exists", False) else {}
    deletion_status = normalize_account_deletion_status(
        marker_exists=bool(getattr(deletion_snapshot, "exists", False)),
        raw_status=deletion_payload.get("wipe_status") if isinstance(deletion_payload, dict) else None,
    )
    if account_deletion_blocks_access(deletion_status):
        raise MemoryFirestoreApplyError("canonical apply blocked by account deletion fence")
    feedback_receipt_ref = None
    existing_feedback_receipt = None
    feedback_event_ref = None
    feedback_event_receipt = None
    if trigger_feedback_receipt is not None:
        if trigger_feedback_receipt.uid != uid:
            raise MemoryFirestoreApplyError("trigger feedback receipt owner mismatch")
        feedback_receipt_ref = db_client.document(
            f"{MemoryCollections(uid=uid).jit_trigger_feedback}/{trigger_feedback_receipt.feedback_id}"
        )
        feedback_snapshot = feedback_receipt_ref.get(transaction=transaction)
        if getattr(feedback_snapshot, "exists", False):
            existing_feedback_receipt = parse_snapshot_strict(
                JITTriggerFeedbackReceipt,
                feedback_snapshot,
                payload_from_snapshot=_typed_doc,
            )
            if existing_feedback_receipt.request_hash != trigger_feedback_receipt.request_hash:
                raise MemoryFirestoreApplyError("trigger feedback id was reused with a different payload")
        feedback_event_ref = db_client.document(
            f"{collections.jit_proactivity_events}/{trigger_feedback_receipt.event_id}"
        )
        feedback_event_snapshot = feedback_event_ref.get(transaction=transaction)
        if not getattr(feedback_event_snapshot, "exists", False):
            raise MemoryFirestoreApplyError("trigger feedback event receipt is unavailable")
        feedback_event_receipt = parse_snapshot_strict(
            JITProactivityEventReceipt,
            feedback_event_snapshot,
            payload_from_snapshot=_typed_doc,
        )
        if (
            feedback_event_receipt.uid != uid
            or feedback_event_receipt.operation != "planned_notification"
            or feedback_event_receipt.account_generation != trigger_feedback_receipt.account_generation
            or feedback_event_receipt.trigger_memory_id != trigger_feedback_receipt.trigger_memory_id
            or feedback_event_receipt.trigger_revision != trigger_feedback_receipt.expected_trigger_revision
            or (
                feedback_event_receipt.feedback_id is not None
                and feedback_event_receipt.feedback_id != trigger_feedback_receipt.feedback_id
            )
        ):
            raise MemoryFirestoreApplyError("trigger feedback event authority fence is stale or invalid")
    review_item = _read_canonical_review_resolution(
        transaction=transaction,
        db_client=db_client,
        collections=collections,
        request=review_resolution,
    )
    control_ref = db_client.document(collections.memory_apply_control_state)
    operation_ref = db_client.document(f"{collections.memory_operations}/{operation_id}")

    control_state = _required_model(
        ref=control_ref,
        transaction=transaction,
        model=MemoryControlState,
        label="memory control state",
    )
    operation_snapshot = operation_ref.get(transaction=transaction)
    if getattr(operation_snapshot, "exists", False):
        operation = parse_snapshot_strict(
            MemoryOperation,
            operation_snapshot,
            payload_from_snapshot=_typed_doc,
        )
    elif proposed_operation is not None:
        operation = proposed_operation
    else:
        raise MissingMemoryDocument(f"missing memory operation: {operation_ref.path}")
    if operation.uid != uid:
        raise MemoryFirestoreApplyError("operation uid does not match requested uid")
    if operation.operation_id != operation_id:
        raise MemoryFirestoreApplyError("operation_id does not match requested operation document")
    source_packet_id = operation.source_packet_id or ""

    committed_replay = apply_long_term_patch_transaction(
        control_state=control_state,
        operation=operation,
        patch_payload=patch_payload,
    )
    if committed_replay.status == ApplyStatus.idempotent_skip:
        if review_resolution is not None:
            raise CanonicalReviewResolutionConflict(
                "stale_review",
                "canonical review operation was already committed without its projection",
                review_item=review_item,
            )
        if trigger_feedback_receipt is not None and existing_feedback_receipt is None:
            raise MemoryFirestoreApplyError("committed trigger feedback is missing its receipt")
        return committed_replay
    if committed_replay.status == ApplyStatus.payload_mismatch:
        return committed_replay

    reopen_receipt_ref = None
    if ledger_reopen_receipt is not None:
        if ledger_reopen_receipt.uid != uid:
            raise MemoryFirestoreApplyError("ledger reopen receipt uid does not match requested uid")
        if required_source_item is None or ledger_reopen_receipt.source_memory_id != required_source_item.memory_id:
            raise MemoryFirestoreApplyError("ledger reopen receipt source does not match the fenced source")
        if (
            ledger_reopen_receipt.account_generation != control_state.account_generation
            or ledger_reopen_receipt.source_generation != control_state.source_generation
            or ledger_reopen_receipt.source_item_revision != required_source_item.item_revision
            or ledger_reopen_receipt.source_content_hash != (required_source_item.content_hash or "")
        ):
            return _source_not_active(control_state, operation, "standalone ledger reopen receipt fence is stale")
        reopen_receipt_ref = db_client.document(
            f"{collections.memory_ledger_reopens}/{ledger_reopen_receipt.source_memory_id}"
        )
        existing_receipt_snapshot = reopen_receipt_ref.get(transaction=transaction)
        if getattr(existing_receipt_snapshot, "exists", False):
            existing_receipt = parse_snapshot_strict(
                MemoryLedgerReopenReceipt,
                existing_receipt_snapshot,
                payload_from_snapshot=_typed_doc,
            )
            if (
                existing_receipt.uid != uid
                or existing_receipt.source_memory_id != ledger_reopen_receipt.source_memory_id
                or existing_receipt.account_generation != control_state.account_generation
                or existing_receipt.source_generation != control_state.source_generation
            ):
                return _source_not_active(
                    control_state, operation, "standalone ledger source reopen receipt is invalid"
                )
            # A committed operation should have been handled by the idempotent
            # replay above. Any other operation is a duplicate current-tail
            # attempt and must not mutate the ledger or operation journal.
            return _source_not_active(control_state, operation, "standalone ledger source is already reopened")

    source_validation = _validate_required_ledger_source(
        db_client=db_client,
        transaction=transaction,
        collections=collections,
        expected=required_source_item,
        operation=operation,
        control_state=control_state,
        ledger_reopen_receipt=ledger_reopen_receipt,
    )
    if source_validation is not None:
        # The proposed operation carries memory_text. A privacy-invalidated
        # source must fail without persisting that stale content anywhere.
        return source_validation
    if committed_replay.status in {ApplyStatus.generation_mismatch, ApplyStatus.retryable_head_mismatch}:
        _write_apply_result(
            transaction=transaction,
            db_client=db_client,
            collections=collections,
            operation_ref=operation_ref,
            result=committed_replay,
        )
        return committed_replay

    evidence_items, staged_evidence = _read_or_stage_authoritative_evidence(
        db_client=db_client,
        transaction=transaction,
        collections=collections,
        evidence_ids=operation.evidence_ids,
        proposed_evidence=proposed_evidence,
    )
    target_validation = _validate_authoritative_targets(
        db_client=db_client,
        transaction=transaction,
        collections=collections,
        operation=operation,
        control_state=control_state,
    )
    if target_validation is not None:
        _write_apply_result(
            transaction=transaction,
            db_client=db_client,
            collections=collections,
            operation_ref=operation_ref,
            result=target_validation,
        )
        return target_validation

    authoritative_payload: Dict[str, Any] = dict(patch_payload)
    authoritative_payload["evidence"] = evidence_items
    existing_item = _read_authoritative_target_item(
        db_client=db_client,
        transaction=transaction,
        collections=collections,
        operation=operation,
    )
    if existing_item is not None:
        authoritative_payload["existing_item"] = existing_item.model_dump(mode="python")
    if trigger_feedback_receipt is not None:
        if existing_feedback_receipt is not None:
            raise MemoryFirestoreApplyError("trigger feedback receipt exists without a committed replay")
        if (
            not direct_user_authorized
            or existing_item is None
            or existing_item.uid != uid
            or existing_item.kind != MemoryKind.trigger
            or existing_item.ledger_schema_version != "knowledge_ledger.v1"
            or existing_item.account_generation != trigger_feedback_receipt.account_generation
            or control_state.account_generation != trigger_feedback_receipt.account_generation
            or existing_item.memory_id != trigger_feedback_receipt.trigger_memory_id
            or existing_item.item_revision != trigger_feedback_receipt.expected_trigger_revision
            or operation.target_memory_id != trigger_feedback_receipt.trigger_memory_id
            or not source_packet_id.startswith(
                f"user_mutation:jit_trigger_feedback:{trigger_feedback_receipt.feedback_id}:"
            )
        ):
            raise MemoryFirestoreApplyError("trigger feedback authority fence is stale or invalid")
        feedback_arguments = patch_payload.get("arguments")
        if (
            not isinstance(feedback_arguments, dict)
            or "jit_trigger_feedback" not in feedback_arguments
            or {key: value for key, value in feedback_arguments.items() if key != "jit_trigger_feedback"}
            != {key: value for key, value in existing_item.arguments.items() if key != "jit_trigger_feedback"}
        ):
            raise MemoryFirestoreApplyError("trigger feedback may only update its bounded argument state")
    if allow_ledger_migration:
        migration_prefix = source_packet_id.startswith(
            ("user_mutation:knowledge_ledger_migration:", "user_mutation:legacy_short_term_adjudication:")
        )
        invalid_migration_fields = set(patch_payload) - _LEDGER_MIGRATION_PATCH_FIELDS
        if (
            existing_item is None
            or existing_item.ledger_schema_version is not None
            or operation.operation_type != MemoryOperationType.ledger_mutation
            or operation.logical_payload.decision != DurablePatchDecision.update.value
            or patch_payload.get("ledger_schema_version") != "knowledge_ledger.v1"
            or not migration_prefix
            or invalid_migration_fields
        ):
            return ApplyResult(
                status=ApplyStatus.invalid_patch,
                control_state=control_state,
                operation=operation,
                reason="ledger migration capability requires an allowlisted pre-ledger schema adaptation",
            )
        writer_class = MemoryWriterClass.ledger
    elif operation.operation_type != MemoryOperationType.deletion:
        allowed_direct_user_fields = _DIRECT_USER_MUTATION_PATCH_FIELDS
        if trigger_feedback_receipt is not None:
            allowed_direct_user_fields = allowed_direct_user_fields | {"curation_weight"}
        invalid_direct_user_fields = set(patch_payload) - allowed_direct_user_fields
        direct_user_update = (
            direct_user_authorized
            and existing_item is not None
            and operation.logical_payload.decision == DurablePatchDecision.update.value
            and operation.operation_type in {MemoryOperationType.user_mutation, MemoryOperationType.ledger_mutation}
            and not invalid_direct_user_fields
        )
        direct_user_append = (
            direct_user_authorized
            and operation.operation_type == MemoryOperationType.ledger_mutation
            and operation.logical_payload.decision == DurablePatchDecision.add.value
            and patch_payload.get("ledger_schema_version") == "knowledge_ledger.v1"
            and patch_payload.get("write_reason") == LedgerWriteReason.direct_user_statement.value
            and patch_payload.get("user_asserted") is True
            and (bool(operation.logical_payload.supersedes) or ledger_reopen_receipt is not None)
            and any(evidence.source_type in _DIRECT_USER_LEDGER_EVIDENCE_TYPES for evidence in evidence_items)
        )
        if direct_user_update or direct_user_append:
            writer_class = MemoryWriterClass.user
        else:
            writer_class = (
                MemoryWriterClass.ledger
                if (
                    (existing_item is not None and existing_item.ledger_schema_version == "knowledge_ledger.v1")
                    or patch_payload.get("ledger_schema_version") == "knowledge_ledger.v1"
                )
                else MemoryWriterClass.compatibility
            )
    else:
        writer_class = None
    if writer_class is not None:
        try:
            require_writer_admitted(
                control_state,
                writer_class,
                allow_ledger_migration=allow_ledger_migration,
            )
        except WriterAdmissionError as exc:
            return ApplyResult(
                status=ApplyStatus.invalid_patch,
                control_state=control_state,
                operation=operation,
                reason=str(exc),
            )
    if review_resolution is not None:
        if review_resolution.authority == "canonical_memory":
            if existing_item is None:
                raise CanonicalReviewResolutionConflict(
                    "stale_review",
                    "canonical review target no longer exists",
                    review_item=review_item,
                )
            _validate_canonical_review_source(
                review_item=review_item,
                request=review_resolution,
                item=existing_item,
            )
        elif review_resolution.decision == "accept":
            if (
                existing_item is not None
                or operation.logical_payload.decision != DurablePatchDecision.add.value
                or patch_payload.get("new_memory_id") != review_resolution.memory_id
            ):
                raise CanonicalReviewResolutionConflict(
                    "stale_review",
                    "legacy review acceptance no longer owns an exact add",
                    review_item=review_item,
                )
        elif review_resolution.decision == "correct":
            mutation_target = review_resolution.mutation_target_memory_id
            if (
                existing_item is None
                or not mutation_target
                or operation.target_memory_id != mutation_target
                or existing_item.memory_id != mutation_target
                or operation.logical_payload.decision != DurablePatchDecision.update.value
            ):
                raise CanonicalReviewResolutionConflict(
                    "stale_review",
                    "legacy review correction no longer owns an exact update",
                    review_item=review_item,
                )
        else:
            raise CanonicalReviewResolutionConflict(
                "stale_review",
                "legacy review resolution operation is unsupported",
                review_item=review_item,
            )
    superseded_items = _read_authoritative_superseded_items(
        db_client=db_client,
        transaction=transaction,
        collections=collections,
        operation=operation,
    )
    if superseded_items:
        authoritative_payload["superseded_items"] = [item.model_dump(mode="python") for item in superseded_items]

    result = apply_long_term_patch_transaction(
        control_state=control_state,
        operation=operation,
        patch_payload=authoritative_payload,
        allow_trigger_feedback_arguments=trigger_feedback_receipt is not None,
    )
    # Validate the authoritative source before reporting a row-id collision so
    # a delayed replay from deleted evidence remains fail-closed as
    # ``source_not_active``. A valid add still cannot overwrite any existing
    # row, including non-active history.
    if result.status == ApplyStatus.committed and operation.logical_payload.decision == DurablePatchDecision.add.value:
        new_memory_id = patch_payload.get("new_memory_id")
        if isinstance(new_memory_id, str) and new_memory_id.strip():
            new_item_ref = db_client.document(f"{collections.memory_items}/{new_memory_id}")
            deleted_receipt_ref = db_client.document(
                f"{collections.memory_deletion_receipts}/{privacy_deletion_receipt_id(uid, new_memory_id)}"
            )
            if getattr(deleted_receipt_ref.get(transaction=transaction), "exists", False):
                result = ApplyResult(
                    status=ApplyStatus.invalid_patch,
                    control_state=control_state,
                    operation=operation,
                    reason="add patch new_memory_id is privacy-deleted",
                )
            elif getattr(new_item_ref.get(transaction=transaction), "exists", False):
                result = ApplyResult(
                    status=ApplyStatus.invalid_patch,
                    control_state=control_state,
                    operation=operation,
                    reason="add patch new_memory_id already exists",
                )
    if result.status == ApplyStatus.committed and allow_ledger_migration:
        control_updates: Dict[str, Any]
        if source_packet_id.startswith("user_mutation:knowledge_ledger_migration:"):
            control_updates = {
                "ledger_migration_migrated_count": result.control_state.ledger_migration_migrated_count + 1
            }
        else:
            control_updates = {
                "ledger_migration_adjudicated_count": result.control_state.ledger_migration_adjudicated_count + 1
            }
        result = result.model_copy(update={"control_state": result.control_state.model_copy(update=control_updates)})
    if result.status == ApplyStatus.committed:
        for evidence_ref, evidence in staged_evidence:
            transaction.set(evidence_ref, _firestore_data(evidence))
    _write_apply_result(
        transaction=transaction,
        db_client=db_client,
        collections=collections,
        operation_ref=operation_ref,
        result=result,
    )
    if result.status == ApplyStatus.committed:
        _write_canonical_review_resolution(
            transaction=transaction,
            db_client=db_client,
            collections=collections,
            request=review_resolution,
            review_item=review_item,
            commit_id=result.control_state.head_commit_id,
            now=result.control_state.updated_at,
        )
        if ledger_reopen_receipt is not None:
            if reopen_receipt_ref is None or len(result.memory_items) != 1:
                raise MemoryFirestoreApplyError("standalone ledger reopen did not produce exactly one replacement")
            replacement = result.memory_items[0]
            if replacement.memory_id != ledger_reopen_receipt.replacement_memory_id:
                raise MemoryFirestoreApplyError("standalone ledger reopen replacement identity mismatch")
            transaction.set(reopen_receipt_ref, _firestore_data(ledger_reopen_receipt))
        if trigger_feedback_receipt is not None:
            if (
                feedback_receipt_ref is None
                or feedback_event_ref is None
                or feedback_event_receipt is None
                or len(result.memory_items) != 1
            ):
                raise MemoryFirestoreApplyError("trigger feedback did not update exactly one trigger")
            applied_item = result.memory_items[0]
            transaction.set(
                feedback_receipt_ref,
                _firestore_data(
                    trigger_feedback_receipt.model_copy(update={"applied_trigger_revision": applied_item.item_revision})
                ),
            )
            transaction.set(
                feedback_event_ref,
                _firestore_data(
                    feedback_event_receipt.model_copy(update={"feedback_id": trigger_feedback_receipt.feedback_id})
                ),
            )
    return result


@transactional
def _read_trigger_feedback_replay_transaction(
    transaction: Any,
    db_client: Any,
    uid: str,
    feedback_id: str,
    request_hash: str,
) -> Optional[Tuple[MemoryItem, JITTriggerFeedbackReceipt]]:
    collections = MemoryCollections(uid=uid)
    deletion_ref = db_client.document(f"account_deletions/{uid}")
    deletion_snapshot = deletion_ref.get(transaction=transaction)
    deletion_payload = deletion_snapshot.to_dict() if getattr(deletion_snapshot, "exists", False) else {}
    deletion_status = normalize_account_deletion_status(
        marker_exists=bool(getattr(deletion_snapshot, "exists", False)),
        raw_status=deletion_payload.get("wipe_status") if isinstance(deletion_payload, dict) else None,
    )
    if account_deletion_blocks_access(deletion_status):
        raise MemoryFirestoreApplyError("trigger feedback replay blocked by account deletion fence")
    control = _required_model(
        ref=db_client.document(collections.memory_apply_control_state),
        transaction=transaction,
        model=MemoryControlState,
        label="memory control state",
    )
    receipt_ref = db_client.document(f"{collections.jit_trigger_feedback}/{feedback_id}")
    receipt_snapshot = receipt_ref.get(transaction=transaction)
    if not getattr(receipt_snapshot, "exists", False):
        return None
    receipt = parse_snapshot_strict(
        JITTriggerFeedbackReceipt,
        receipt_snapshot,
        payload_from_snapshot=_typed_doc,
    )
    if receipt.uid != uid or receipt.request_hash != request_hash:
        raise MemoryFirestoreApplyError("trigger feedback id was reused with a different payload")
    if receipt.account_generation != control.account_generation or receipt.applied_trigger_revision is None:
        raise MemoryFirestoreApplyError("trigger feedback replay generation is stale")
    event = _required_model(
        ref=db_client.document(f"{collections.jit_proactivity_events}/{receipt.event_id}"),
        transaction=transaction,
        model=JITProactivityEventReceipt,
        label="JIT proactivity event receipt",
    )
    if (
        event.uid != uid
        or event.account_generation != receipt.account_generation
        or event.trigger_memory_id != receipt.trigger_memory_id
        or event.trigger_revision != receipt.expected_trigger_revision
        or event.feedback_id != receipt.feedback_id
    ):
        raise MemoryFirestoreApplyError("trigger feedback replay event authority is stale")
    item = _required_model(
        ref=db_client.document(f"{collections.memory_items}/{receipt.trigger_memory_id}"),
        transaction=transaction,
        model=MemoryItem,
        label="trigger feedback target",
    )
    if (
        item.uid != uid
        or item.account_generation != receipt.account_generation
        or item.item_revision < receipt.applied_trigger_revision
        or item.kind != MemoryKind.trigger
    ):
        raise MemoryFirestoreApplyError("trigger feedback replay target authority is stale")
    return item, receipt


def read_trigger_feedback_replay_firestore(
    uid: str,
    *,
    feedback_id: str,
    request_hash: str,
    db_client: Any = None,
) -> Optional[Tuple[MemoryItem, JITTriggerFeedbackReceipt]]:
    client = db_client or db
    transaction = client.transaction()
    return _read_trigger_feedback_replay_transaction(
        transaction,
        client,
        uid,
        feedback_id,
        request_hash,
    )


_EVIDENCE_SEMANTIC_EXCLUDES = {
    "created_at",
    "artifact_preservation",
    "source_state",
    "source_state_reason",
    "provenance_visibility",
    "redaction_status",
    "encryption_or_redaction_status",
}


def _evidence_semantic_payload(evidence: MemoryEvidence) -> Dict[str, Any]:
    return evidence.model_dump(mode="json", exclude=_EVIDENCE_SEMANTIC_EXCLUDES)


def _read_or_stage_authoritative_evidence(
    *,
    db_client: Any,
    transaction: Any,
    collections: MemoryCollections,
    evidence_ids: Iterable[str],
    proposed_evidence: Optional[List[MemoryEvidence]],
) -> tuple[List[MemoryEvidence], List[tuple[Any, MemoryEvidence]]]:
    proposed_by_id = {evidence.evidence_id: evidence for evidence in proposed_evidence or []}
    if len(proposed_by_id) != len(proposed_evidence or []):
        raise MemoryFirestoreApplyError("proposed evidence contains duplicate ids")
    expected_ids = list(evidence_ids)
    if proposed_evidence is not None and set(proposed_by_id) != set(expected_ids):
        raise MemoryFirestoreApplyError("proposed evidence ids do not match the operation")
    evidence_items: List[MemoryEvidence] = []
    staged: List[tuple[Any, MemoryEvidence]] = []
    for evidence_id in expected_ids:
        evidence_ref = db_client.document(f"{collections.memory_evidence}/{evidence_id}")
        snapshot = evidence_ref.get(transaction=transaction)
        proposed = proposed_by_id.get(evidence_id)
        if getattr(snapshot, "exists", False):
            evidence = parse_snapshot_strict(MemoryEvidence, snapshot, payload_from_snapshot=_typed_doc)
            if (
                evidence.source_state == SourceState.active
                and proposed is not None
                and _evidence_semantic_payload(evidence) != _evidence_semantic_payload(proposed)
            ):
                raise MemoryFirestoreApplyError("proposed evidence conflicts with existing evidence identity")
        elif proposed is not None:
            if proposed.source_state != SourceState.active:
                raise MemoryFirestoreApplyError("proposed evidence must be active")
            evidence = proposed
            staged.append((evidence_ref, evidence))
        else:
            raise MissingMemoryDocument(f"missing memory evidence: {evidence_ref.path}")
        evidence_items.append(evidence)
    return evidence_items, staged


def _read_authoritative_target_item(
    *,
    db_client: Any,
    transaction: Any,
    collections: MemoryCollections,
    operation: MemoryOperation,
) -> Optional[MemoryItem]:
    if operation.logical_payload.decision != DurablePatchDecision.update.value:
        return None
    target_id = operation.logical_payload.target_memory_id or operation.target_memory_id
    if not target_id:
        return None
    target_ref = db_client.document(f"{collections.memory_items}/{target_id}")
    snapshot = target_ref.get(transaction=transaction)
    if not snapshot.exists:
        return None
    return parse_snapshot_strict(MemoryItem, snapshot, payload_from_snapshot=_typed_doc)


def _read_authoritative_superseded_items(
    *,
    db_client: Any,
    transaction: Any,
    collections: MemoryCollections,
    operation: MemoryOperation,
) -> List[MemoryItem]:
    items: List[MemoryItem] = []
    for memory_id in operation.logical_payload.supersedes:
        ref = db_client.document(f"{collections.memory_items}/{memory_id}")
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            continue
        items.append(parse_snapshot_strict(MemoryItem, snapshot, payload_from_snapshot=_typed_doc))
    return items


def _validate_authoritative_targets(
    *,
    db_client: Any,
    transaction: Any,
    collections: MemoryCollections,
    operation: MemoryOperation,
    control_state: MemoryControlState,
) -> Optional[ApplyResult]:
    target_ids = _operation_target_ids(operation)
    for target_id in target_ids:
        target_ref = db_client.document(f"{collections.memory_items}/{target_id}")
        snapshot = target_ref.get(transaction=transaction)
        if not snapshot.exists:
            return _target_not_active(control_state, operation, f"missing target memory item: {target_id}")
        target = parse_snapshot_strict(MemoryItem, snapshot, payload_from_snapshot=_typed_doc)
        if target.uid != operation.uid:
            return _target_not_active(control_state, operation, "target memory uid mismatch")
        if target.account_generation != control_state.account_generation:
            return _target_not_active(control_state, operation, "target memory generation mismatch")
        if target.status != MemoryItemStatus.active:
            return _target_not_active(control_state, operation, "target memory is not active")
    return None


def _validate_required_ledger_source(
    *,
    db_client: Any,
    transaction: Any,
    collections: MemoryCollections,
    expected: Optional[MemoryItem],
    operation: MemoryOperation,
    control_state: MemoryControlState,
    ledger_reopen_receipt: Optional[MemoryLedgerReopenReceipt] = None,
) -> Optional[ApplyResult]:
    """Fence a user-selected ledger source in the same transaction as its append."""

    if expected is None:
        return None
    source_ref = db_client.document(f"{collections.memory_items}/{expected.memory_id}")
    snapshot = source_ref.get(transaction=transaction)
    if not getattr(snapshot, "exists", False):
        return _source_not_active(control_state, operation, "required ledger source is missing")
    source = parse_snapshot_strict(MemoryItem, snapshot, payload_from_snapshot=_typed_doc)
    restricted = bool(set(source.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS))
    if (
        source.uid != operation.uid
        or source.memory_id != expected.memory_id
        or str(getattr(snapshot, "id", expected.memory_id)) != expected.memory_id
        or source.account_generation != control_state.account_generation
        or source.item_revision != expected.item_revision
        or source.content_hash != expected.content_hash
        or source.source_state != SourceState.active
        or source.source_state != expected.source_state
        or source.status != expected.status
        or source.sensitivity_labels != expected.sensitivity_labels
        or restricted
        or bool((source.promotion or {}).get("is_locked", False))
    ):
        return _source_not_active(control_state, operation, "required ledger source changed or is unavailable")
    if ledger_reopen_receipt is None:
        return None
    if (
        source.valid_to != expected.valid_to
        or source.superseded_by != expected.superseded_by
        or source.canonical_memory_id != expected.canonical_memory_id
        or source.ledger_schema_version != expected.ledger_schema_version
        or source.kind != expected.kind
        or source.intent_backed != expected.intent_backed
        or source.processing_state != expected.processing_state
        or source.visibility != expected.visibility
        or source.slot != expected.slot
        or source.subject_scope != expected.subject_scope
        or source.subject_entity_id != expected.subject_entity_id
        or source.promotion != expected.promotion
    ):
        return _source_not_active(control_state, operation, "standalone ledger source changed or is unavailable")
    # Reopening is allowed to preserve the source evidence only while every
    # referenced evidence record is still active.  Do not permit the external
    # evidence-reissue path to turn a privacy tombstone into a fresh source.
    for expected_evidence in expected.evidence:
        evidence_ref = db_client.document(f"{collections.memory_evidence}/{expected_evidence.evidence_id}")
        evidence_snapshot = evidence_ref.get(transaction=transaction)
        if not getattr(evidence_snapshot, "exists", False):
            return _source_not_active(control_state, operation, "required ledger source evidence is missing")
        evidence = parse_snapshot_strict(MemoryEvidence, evidence_snapshot, payload_from_snapshot=_typed_doc)
        if (
            evidence.evidence_id != expected_evidence.evidence_id
            or evidence.source_state != SourceState.active
            or evidence.redaction_status == RedactionStatus.tombstoned
            or evidence.redaction_status == RedactionStatus.redacted
            or evidence.encryption_or_redaction_status != RedactionStatus.active
        ):
            return _source_not_active(control_state, operation, "required ledger source evidence is unavailable")
    return None


def _operation_target_ids(operation: MemoryOperation) -> List[str]:
    target_ids: List[str] = []
    if operation.target_memory_id:
        target_ids.append(operation.target_memory_id)
    if operation.logical_payload.target_memory_id:
        target_ids.append(operation.logical_payload.target_memory_id)
    target_ids.extend(operation.logical_payload.supersedes or [])
    return sorted(set(target_ids))


def _target_not_active(control_state: MemoryControlState, operation: MemoryOperation, reason: str) -> ApplyResult:
    return ApplyResult(
        status=ApplyStatus.target_not_active,
        control_state=control_state,
        operation=operation,
        reason=reason,
    )


def _source_not_active(control_state: MemoryControlState, operation: MemoryOperation, reason: str) -> ApplyResult:
    return ApplyResult(
        status=ApplyStatus.source_not_active,
        control_state=control_state,
        operation=operation,
        reason=reason,
    )


def _write_apply_result(
    *,
    transaction: Any,
    db_client: Any,
    collections: MemoryCollections,
    operation_ref: Any,
    result: ApplyResult,
) -> None:
    transaction.set(operation_ref, _firestore_data(result.operation))
    if result.status != ApplyStatus.committed:
        return

    control_ref = db_client.document(collections.memory_apply_control_state)
    commit_ref = db_client.document(f"{collections.memory_commits}/{result.control_state.head_commit_id}")
    state_head_ref = db_client.document(collections.memory_state_head)
    transaction.set(control_ref, _firestore_data(result.control_state))
    transaction.set(state_head_ref, _firestore_data(_memory_state_head_from_control(result.control_state)))
    commit_doc: MemoryApplyDoc = {
        "commit_id": result.control_state.head_commit_id,
        "uid": result.control_state.uid,
        "account_generation": result.control_state.account_generation,
        "source_generation": result.control_state.source_generation,
        "commit_sequence": result.control_state.commit_sequence,
        "operation_id": result.operation.operation_id,
        "memory_item_ids": result.operation.committed_memory_item_ids,
        "outbox_event_ids": result.operation.committed_outbox_event_ids,
        "updated_at": result.control_state.updated_at,
    }
    transaction.set(commit_ref, _firestore_data(commit_doc))
    for item in result.memory_items:
        item_ref = db_client.document(f"{collections.memory_items}/{item.memory_id}")
        transaction.set(item_ref, _firestore_data(item))
        assertion_ref = db_client.document(f"{collections.memory_graph_assertions}/{item.memory_id}")
        matching_assertion = next(
            (assertion for assertion in result.graph_assertions if assertion.memory_id == item.memory_id),
            None,
        )
        if matching_assertion is not None:
            transaction.set(assertion_ref, _firestore_data(matching_assertion))
        elif item.status != MemoryItemStatus.tombstoned and (
            item.status != MemoryItemStatus.active or not item.graph_ready
        ):
            transaction.delete(assertion_ref)
        promotion = item.promotion or {}
        if item.status == MemoryItemStatus.active and promotion.get("route") == "review":
            conflict_id = promotion.get("target_memory_id")
            review_item = build_memory_review_conflict(
                fact={
                    "id": item.memory_id,
                    "content": item.content,
                    "veracity": 0.4,
                    "importance": 0.5,
                },
                conflict_with=[conflict_id] if isinstance(conflict_id, str) and conflict_id else [],
                authority="canonical_memory",
                source_commit_id=result.control_state.head_commit_id,
                source_item_revision=item.item_revision,
                source_content_hash=item.content_hash,
                source_short_term_id=item.memory_id,
                impact=0.5,
                now=item.updated_at,
            )
            review_ref = db_client.document(f"{collections.memory_review_queue}/{review_item['review_id']}")
            transaction.set(review_ref, _firestore_data(review_item))
    for event in result.outbox_events:
        event_ref = db_client.document(f"{collections.memory_outbox}/{event.event_id}")
        transaction.set(event_ref, _firestore_data(event))


def _memory_state_head_from_control(control_state: MemoryControlState) -> MemoryApplyDoc:
    trusted_fields = trusted_memory_state_head_fields(
        uid=control_state.uid,
        account_generation=control_state.account_generation,
        head_commit_id=control_state.head_commit_id,
        commit_sequence=control_state.commit_sequence,
    )
    if trusted_fields is None:  # MemoryControlState has already validated this input.
        raise MemoryFirestoreApplyError("invalid memory state-head control fields")
    return cast(MemoryApplyDoc, {**trusted_fields, "updated_at": control_state.updated_at})


def _required_model(*, ref: Any, transaction: Any, model: type[M], label: str) -> M:
    snapshot = ref.get(transaction=transaction)
    if not snapshot.exists:
        raise MissingMemoryDocument(f"missing {label}: {ref.path}")
    return parse_snapshot_strict(model, snapshot, payload_from_snapshot=_typed_doc)


def _firestore_data(value: object) -> Any:
    if isinstance(value, BaseModel):
        return _firestore_data(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_firestore_data(item) for item in cast(List[Any], value)]
    if isinstance(value, tuple):
        return [_firestore_data(item) for item in cast(List[Any], value)]
    if isinstance(value, dict):
        mapping = cast(Dict[str, Any], value)
        return {key: _firestore_data(item) for key, item in mapping.items()}
    return value


def cleanup_expired_memory_deletion_receipts(
    uid: str,
    *,
    db_client: Any = db,
    now: datetime | None = None,
    limit: int = 128,
) -> int:
    """Remove only expired, content-free anti-resurrection receipts.

    V2 receipts contain only a server-keyed identity and privacy epoch. Legacy
    V1 receipts remain readable until their own expiry so rollout never drops
    an existing deletion fence. Any malformed row fails closed.
    """

    cutoff = now or datetime.now(timezone.utc)
    bounded_limit = max(1, min(256, int(limit)))
    collection = db_client.collection(MemoryCollections(uid=uid).memory_deletion_receipts)
    try:
        query = collection.where("expires_at", "<=", cutoff).limit(bounded_limit)
        rows = list(query.stream())
    except Exception:
        return 0
    try:
        # Legal hold and retention cleanup share the same account-wide
        # linearization gate. A hold that wins first preserves every receipt;
        # a cleanup that wins first completes before a hold can activate.
        with destructive_operation_gate(
            uid,
            kind="retention_cleanup",
            firestore_client=db_client,
        ):
            deleted = 0
            for row in rows:
                try:
                    payload = row.to_dict()
                    if not isinstance(payload, dict):
                        continue
                    expires_at = payload.get("expires_at")
                    if (
                        payload.get("schema_version") == "memory_deletion_receipt.v2"
                        and payload.get("uid") == uid
                        and payload.get("receipt_id") == str(row.id)
                        and isinstance(payload.get("privacy_epoch_commit_id"), str)
                        and payload.get("privacy_epoch_commit_id")
                        and isinstance(expires_at, datetime)
                        and expires_at.tzinfo is not None
                        and expires_at.utcoffset() is not None
                        and expires_at <= cutoff
                    ):
                        row.reference.delete()
                        deleted += 1
                        continue
                    memory_ids = payload.get("memory_ids")
                    operation_id = payload.get("operation_id")
                    commit_id = payload.get("commit_id")
                    if (
                        payload.get("schema_version") != "memory_deletion_receipt.v1"
                        or payload.get("uid") != uid
                        or not isinstance(memory_ids, list)
                        or not memory_ids
                        or not all(isinstance(memory_id, str) and memory_id for memory_id in memory_ids)
                        or not isinstance(operation_id, str)
                        or not operation_id
                        or not isinstance(commit_id, str)
                        or not commit_id
                        or not isinstance(expires_at, datetime)
                        or expires_at.tzinfo is None
                        or expires_at.utcoffset() is None
                        or expires_at > cutoff
                    ):
                        continue
                    operation_snapshot = db_client.document(
                        f"{MemoryCollections(uid=uid).memory_operations}/{operation_id}"
                    ).get()
                    operation_payload = (
                        operation_snapshot.to_dict() if getattr(operation_snapshot, "exists", False) else None
                    )
                    if (
                        not isinstance(operation_payload, dict)
                        or operation_payload.get("operation_type") != MemoryOperationType.deletion.value
                        or operation_payload.get("committed_head_commit_id") != commit_id
                    ):
                        continue
                    items_match = True
                    for memory_id in memory_ids:
                        item_snapshot = db_client.document(
                            f"{MemoryCollections(uid=uid).memory_items}/{memory_id}"
                        ).get()
                        item_payload = item_snapshot.to_dict() if getattr(item_snapshot, "exists", False) else None
                        if (
                            not isinstance(item_payload, dict)
                            or item_payload.get("status") != MemoryItemStatus.tombstoned.value
                            or item_payload.get("ledger_commit_id") != commit_id
                        ):
                            items_match = False
                            break
                    if not items_match:
                        continue
                    row.reference.delete()
                    deleted += 1
                except Exception:
                    continue
            return deleted
    except Exception:
        # Active/malformed/unavailable legal-hold authority fails closed.
        return 0


__all__ = [
    "CanonicalApplyWrite",
    "CanonicalMemoryIntakePausedError",
    "CanonicalMemoryTombstoneConflict",
    "CanonicalMemoryTombstoneLimitError",
    "CanonicalMemoryTombstoneResult",
    "CanonicalReviewResolution",
    "CanonicalReviewResolutionConflict",
    "ConversationSourceReplacementConflict",
    "ConversationSourceReplacementLimitError",
    "ConversationSourceReplacementResult",
    "MemoryFirestoreApplyError",
    "MissingMemoryDocument",
    "MemoryFirestoreApplyError",
    "apply_long_term_patch_firestore",
    "atomic_bump_source_generation",
    "cleanup_expired_memory_deletion_receipts",
    "privacy_deletion_receipt_id",
    "replace_conversation_source_firestore",
    "tombstone_memory_items_firestore",
]
