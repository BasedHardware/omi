"""Deterministic, resumable planning for canonical-to-ledger migration.

The planner is side-effect free. Production callers must apply its output
through canonical apply with the current item revision and control head; this
module never writes legacy or canonical collections directly.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Literal, Optional

from pydantic import BaseModel, Field

import database.memory_apply_store as memory_apply_store
import utils.memory.memory_service as memory_service
from database.memory_collections import MemoryCollections
from models.knowledge_ledger_policy import (
    LEDGER_SLOT_BY_LEGACY_PREDICATE,
    select_profile_slot_winners,
)
from models.memories import MemoryDB
from models.memory_apply import MemoryControlState, WriterMode
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    MemorySubjectScope,
)
from utils.memory.canonical_memory_adapter import (
    adapt_canonical_memory_to_knowledge_ledger,
    close_canonical_legacy_generated_history,
    read_canonical_memory_item,
)
from utils.memory.knowledge_ledger import LEDGER_SCHEMA_VERSION
from utils.memory.knowledge_ledger_writer_transition import (
    CompleteUnionProofReceipt,
    WriterTransitionError,
    abort_writer_transition,
    begin_writer_transition,
    complete_writer_transition,
)

MAX_LEDGER_MIGRATION_SCAN_ROWS = 20_000
MAX_LEDGER_MIGRATION_MUTATIONS_PER_RUN = 100


class LedgerMigrationAction(str, Enum):
    no_op = "no_op"
    adapt_long_term_history = "adapt_long_term_history"
    adjudicate_short_term = "adjudicate_short_term"
    ignore_inactive = "ignore_inactive"


class LedgerMigrationPlan(BaseModel):
    memory_id: str
    source_revision: int
    action: LedgerMigrationAction
    reason: str
    updates: Dict[str, Any] = Field(default_factory=dict)
    requires_human_or_policy_adjudication: bool = False


class LedgerMigrationCompletion(BaseModel):
    """Auditable proof required before legacy prompt compatibility is disabled."""

    schema_version: Literal["knowledge_ledger.v1"] = LEDGER_SCHEMA_VERSION
    status: str = "complete"
    completed_at: datetime
    source_head_commit_id: str
    writer_epoch: int = Field(ge=1)
    migrated_long_term_count: int = Field(ge=0)
    adjudicated_short_term_count: int = Field(ge=0)
    blocking_row_count: int = Field(default=0, ge=0)

    def validate_complete(self) -> None:
        if self.status != "complete":
            raise ValueError("ledger migration completion status must be complete")
        if self.blocking_row_count:
            raise ValueError("ledger migration cannot complete with blocking rows")
        if not self.source_head_commit_id.strip():
            raise ValueError("ledger migration completion requires a source head")
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("ledger migration completion timestamp must be timezone-aware")


MAX_LEDGER_PROMPT_PROJECTION_ROWS = 64


class LedgerPromptProjectionReceipt(BaseModel):
    """Bounded sweep receipt, never an independently writable memory store.

    The receipt is useful only while its complete canonical-control fence is
    still current. Any canonical write, account reset, or source reprocessing
    invalidates it immediately and returns readers to compatibility mode until
    the next migration sweep publishes a new receipt.
    """

    schema_version: Literal["knowledge_ledger_prompt_projection.v1"] = "knowledge_ledger_prompt_projection.v1"
    status: Literal["complete"] = "complete"
    uid: str
    generated_at: datetime
    source_head_commit_id: str
    account_generation: int = Field(ge=0)
    source_generation: int = Field(ge=0)
    writer_epoch: int = Field(ge=1)
    legacy_row_count: Literal[0] = 0
    preserved_historical_legacy_count: int = Field(default=0, ge=0)
    blocking_row_count: Literal[0] = 0
    scanned_row_count: int = Field(ge=0)
    rows: list[MemoryDB] = Field(default_factory=list, max_length=MAX_LEDGER_PROMPT_PROJECTION_ROWS)

    def validate_authoritative(
        self,
        *,
        uid: str,
        completion: LedgerMigrationCompletion,
        control: MemoryControlState,
    ) -> None:
        if self.uid != uid or control.uid != uid:
            raise ValueError("ledger prompt projection owner mismatch")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("ledger prompt projection timestamp must be timezone-aware")
        if not self.source_head_commit_id.strip():
            raise ValueError("ledger prompt projection requires a source head")
        if (
            self.source_head_commit_id != completion.source_head_commit_id
            or self.source_head_commit_id != control.head_commit_id
            or self.account_generation != control.account_generation
            or self.source_generation != control.source_generation
            or self.writer_epoch != completion.writer_epoch
            or self.writer_epoch != control.writer_epoch
            or control.writer_mode != WriterMode.ledger
        ):
            raise ValueError("ledger prompt projection control fence is stale")
        if len({row.id for row in self.rows}) != len(self.rows):
            raise ValueError("ledger prompt projection contains duplicate rows")
        for row in self.rows:
            if row.uid != uid or row.ledger_schema_version != LEDGER_SCHEMA_VERSION:
                raise ValueError("ledger prompt projection contains a foreign or unsupported row")
            if (
                row.is_locked
                or row.user_review is False
                or row.invalid_at is not None
                or (row.superseded_by or "").strip()
                or row.is_dismissed
                or getattr(row.memory_tier, "value", row.memory_tier) == "archive"
                or (row.visibility or "").strip().lower() == "hidden"
                or row.evidence
            ):
                raise ValueError("ledger prompt projection contains a private or non-current row")
            kind = getattr(row.kind, "value", row.kind)
            scope = getattr(row.subject_scope, "value", row.subject_scope)
            if kind == "fact" and not (row.slot and row.intent_backed and scope == "primary_user"):
                raise ValueError("ledger prompt projection contains an ineligible fact")
            if kind not in {"fact", "document", "trigger"}:
                raise ValueError("ledger prompt projection contains an unsupported kind")
            if kind == "document" and (row.body or "").strip():
                raise ValueError("ledger prompt projection must contain handles, not playbook bodies")


class LedgerMigrationPublicationError(RuntimeError):
    """The cutover sweep could not prove one complete bounded snapshot."""


def _prompt_eligible(row: MemoryDB) -> bool:
    if (
        row.ledger_schema_version != LEDGER_SCHEMA_VERSION
        or row.is_locked
        or row.user_review is False
        or row.invalid_at is not None
        or (row.superseded_by or "").strip()
        or row.is_dismissed
        or getattr(row.memory_tier, "value", row.memory_tier) == "archive"
        or (row.visibility or "").strip().lower() == "hidden"
    ):
        return False
    kind = getattr(row.kind, "value", row.kind)
    scope = getattr(row.subject_scope, "value", row.subject_scope)
    if kind == "fact":
        return bool(row.slot and row.intent_backed and scope == "primary_user")
    return kind in {"document", "trigger"}


def _legacy_prompt_serving(row: MemoryDB) -> bool:
    tier = getattr(row.memory_tier, "value", row.memory_tier)
    return not (
        tier == "archive"
        or row.invalid_at is not None
        or (row.superseded_by or "").strip()
        or row.is_locked
        or row.user_review is False
        or row.is_dismissed
        or (row.visibility or "").strip().lower() == "hidden"
    )


def _bounded_prompt_projection(rows: list[MemoryDB]) -> list[MemoryDB]:
    facts = [row for row in rows if getattr(row.kind, "value", row.kind) == "fact"]
    winners = [row for _, row in select_profile_slot_winners(facts)]
    handles = sorted(
        (row for row in rows if getattr(row.kind, "value", row.kind) in {"document", "trigger"}),
        key=lambda row: (str(getattr(row.kind, "value", row.kind)), row.id),
    )
    projected = [*winners, *handles]
    if len(projected) > MAX_LEDGER_PROMPT_PROJECTION_ROWS:
        raise LedgerMigrationPublicationError("ledger prompt projection exceeds the bounded row limit")
    # The prompt receipt carries no provenance or document body. Canonical ids,
    # trigger conditions, entity arguments, and lifecycle fields remain enough
    # for the desktop mirror and on-demand canonical read tools.
    return [row.model_copy(update={"body": None, "evidence": []}) for row in projected]


def _read_control(uid: str, *, db_client: Any, transaction: Any = None) -> MemoryControlState:
    ref = db_client.document(MemoryCollections(uid=uid).memory_apply_control_state)
    snapshot = ref.get(transaction=transaction) if transaction is not None else ref.get()
    if not getattr(snapshot, "exists", False):
        raise LedgerMigrationPublicationError("canonical control state is missing")
    try:
        control = MemoryControlState.model_validate(snapshot.to_dict() or {})
    except (TypeError, ValueError) as exc:
        raise LedgerMigrationPublicationError("canonical control state is malformed") from exc
    if control.uid != uid:
        raise LedgerMigrationPublicationError("canonical control owner mismatch")
    return control


def _same_control_fence(left: MemoryControlState, right: MemoryControlState) -> bool:
    return (
        left.uid,
        left.head_commit_id,
        left.account_generation,
        left.source_generation,
        left.commit_sequence,
        left.writer_mode,
        left.writer_epoch,
        left.writer_transition_owner,
    ) == (
        right.uid,
        right.head_commit_id,
        right.account_generation,
        right.source_generation,
        right.commit_sequence,
        right.writer_mode,
        right.writer_epoch,
        right.writer_transition_owner,
    )


def _same_writer_transition_authority(left: MemoryControlState, right: MemoryControlState) -> bool:
    """Compare the transition fence while allowing its authorized drain to advance the head."""
    return (
        left.uid,
        left.account_generation,
        left.source_generation,
        left.writer_mode,
        left.writer_epoch,
        left.writer_transition_owner,
    ) == (
        right.uid,
        right.account_generation,
        right.source_generation,
        right.writer_mode,
        right.writer_epoch,
        right.writer_transition_owner,
    )


def _content_free_union_record(row: MemoryDB) -> dict[str, Any]:
    """Return bounded lifecycle metadata for a proof digest, never memory content."""
    return {
        "id": row.id,
        "ledger_schema_version": row.ledger_schema_version,
        "updated_at": row.updated_at.isoformat(),
        "invalid_at": row.invalid_at.isoformat() if row.invalid_at is not None else None,
        "superseded_by": row.superseded_by,
        "memory_tier": getattr(row.memory_tier, "value", row.memory_tier),
        "kind": getattr(row.kind, "value", row.kind),
    }


def _content_free_union_digest(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        sorted(rows, key=lambda item: item["id"]),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def publish_ledger_migration_cutover(
    uid: str,
    *,
    db_client: Any,
    publication_authorizer: Callable[[], bool],
    mutation_authorizer: Callable[[str], bool] | None = None,
    migrated_long_term_count: int,
    adjudicated_short_term_count: int,
    completed_at: datetime | None = None,
) -> LedgerPromptProjectionReceipt:
    """Production cutover authority for the migration/daily reconciliation sweep.

    This is intentionally not an HTTP or ordinary memory-write verb. It scans
    the complete compatibility union once, rejects every surviving legacy row,
    constructs the deterministic bounded prompt projection, then atomically
    joins completion and receipt to the still-current canonical control fence.
    The required authorizer is evaluated only after that complete proof scan
    and immediately before the atomic publication transaction is opened.
    """
    transition_owner = "knowledge-ledger-migration.v1"

    def require_publication_authority() -> None:
        try:
            authorized = publication_authorizer()
        except Exception as exc:
            raise LedgerMigrationPublicationError("ledger cutover publication authorization failed") from exc
        if not authorized:
            raise LedgerMigrationPublicationError("ledger cutover publication authorization denied")

    # Entering a writer transition is itself rollout work. Resolve authority
    # immediately before the control mutation, then resolve it again after the
    # complete proof scan and immediately before publication.
    require_publication_authority()
    initial_control = _read_control(uid, db_client=db_client)
    cutover_transition = False
    if initial_control.writer_mode == WriterMode.ledger:
        # Stable ledger writers may advance the canonical head after cutover.
        # Reconciliation republishes a freshly fenced bounded projection
        # without reopening the compatibility writer.
        transition_control = initial_control
    elif initial_control.writer_mode == WriterMode.compatibility:
        cutover_transition = True
        try:
            transition_control = begin_writer_transition(
                uid,
                target_mode=WriterMode.ledger,
                transition_owner=transition_owner,
                expected_control=initial_control,
                db_client=db_client,
            )
        except WriterTransitionError as exc:
            raise LedgerMigrationPublicationError("ledger writer transition could not begin") from exc
    elif (
        initial_control.writer_mode == WriterMode.transitioning_to_ledger
        and initial_control.writer_transition_owner == transition_owner
    ):
        cutover_transition = True
        transition_control = initial_control
    else:
        raise LedgerMigrationPublicationError("another writer transition owns the account")

    try:
        # A compatibility writer may have committed immediately before the
        # transition CAS. The source-generation bump makes pre-CAS plans lose;
        # this optional bounded drain catches rows that won before that bump.
        if mutation_authorizer is not None:
            final_drain = run_ledger_migration_sweep(
                uid,
                db_client=db_client,
                mutation_authorizer=mutation_authorizer,
                publication_authorizer=publication_authorizer,
                publish=False,
                completed_at=completed_at,
            )
            if final_drain.authorization_revoked:
                raise LedgerMigrationPublicationError("ledger final drain authorization was revoked")
            if final_drain.remaining_live_legacy_count:
                raise LedgerMigrationPublicationError("ledger final drain exhausted its bounded mutation budget")
            migrated_long_term_count += final_drain.migrated_long_term_count
            adjudicated_short_term_count += final_drain.adjudicated_short_term_count

        observed_control = _read_control(uid, db_client=db_client)
        if not _same_writer_transition_authority(observed_control, transition_control):
            raise LedgerMigrationPublicationError("canonical control changed before migration proof scan")

        scanned = 0
        preserved_historical_legacy = 0
        eligible: list[MemoryDB] = []
        digest_rows: list[dict[str, Any]] = []
        for row in memory_service.MemoryService(db_client=db_client).iter_export_memories(uid, include_archive=True):
            scanned += 1
            if scanned > MAX_LEDGER_MIGRATION_SCAN_ROWS:
                raise LedgerMigrationPublicationError("migration scan exceeds the controlled row limit")
            if row.uid != uid:
                raise LedgerMigrationPublicationError("migration scan returned a foreign row")
            digest_rows.append(_content_free_union_record(row))
            if row.ledger_schema_version != LEDGER_SCHEMA_VERSION:
                if _legacy_prompt_serving(row):
                    raise LedgerMigrationPublicationError("live legacy prompt row survives migration")
                preserved_historical_legacy += 1
                continue
            if _prompt_eligible(row):
                eligible.append(row)

        projection = _bounded_prompt_projection(eligible)
        published_at = completed_at or datetime.now(timezone.utc)
        completion = LedgerMigrationCompletion(
            completed_at=published_at,
            source_head_commit_id=observed_control.head_commit_id,
            writer_epoch=observed_control.writer_epoch,
            migrated_long_term_count=observed_control.ledger_migration_migrated_count,
            adjudicated_short_term_count=observed_control.ledger_migration_adjudicated_count,
            blocking_row_count=0,
        )
        completion.validate_complete()
        receipt = LedgerPromptProjectionReceipt(
            uid=uid,
            generated_at=published_at,
            source_head_commit_id=observed_control.head_commit_id,
            account_generation=observed_control.account_generation,
            source_generation=observed_control.source_generation,
            writer_epoch=observed_control.writer_epoch,
            scanned_row_count=scanned,
            preserved_historical_legacy_count=preserved_historical_legacy,
            rows=projection,
        )
        transition_receipt = None
        if cutover_transition:
            transition_receipt = CompleteUnionProofReceipt(
                uid=uid,
                transition_owner=transition_owner,
                writer_mode=observed_control.writer_mode,
                target_mode=WriterMode.ledger,
                writer_epoch=observed_control.writer_epoch,
                head_commit_id=observed_control.head_commit_id,
                account_generation=observed_control.account_generation,
                source_generation=observed_control.source_generation,
                commit_sequence=observed_control.commit_sequence,
                complete_union_digest=_content_free_union_digest(digest_rows),
                complete_union_count=scanned,
                generated_at=published_at,
            )

        @memory_apply_store.transactional
        def publish(transaction: Any) -> None:
            current_control = _read_control(uid, db_client=db_client, transaction=transaction)
            if not _same_control_fence(current_control, observed_control):
                raise LedgerMigrationPublicationError("canonical control changed during migration scan")
            collections = MemoryCollections(uid=uid)
            transaction.set(
                db_client.document(collections.knowledge_ledger_migration_state),
                completion.model_dump(mode="python"),
            )
            transaction.set(
                db_client.document(collections.knowledge_ledger_prompt_projection),
                receipt.model_dump(mode="python"),
            )

        require_publication_authority()
        publish(db_client.transaction())
        if transition_receipt is not None:
            # Receipt publication is still invisible while the writer fence is
            # transitioning. Re-resolve rollout authority at the exact action
            # that makes stable ledger mode externally visible.
            require_publication_authority()
            completed_control = complete_writer_transition(
                uid,
                transition_owner=transition_owner,
                expected_control=observed_control,
                receipt=transition_receipt,
                db_client=db_client,
            )
        else:
            completed_control = _read_control(uid, db_client=db_client)
            if not _same_control_fence(completed_control, observed_control):
                raise LedgerMigrationPublicationError("canonical control changed after ledger reconciliation")
        receipt.validate_authoritative(
            uid=uid,
            completion=completion,
            control=completed_control,
        )
        return receipt
    except Exception:
        try:
            current_control = _read_control(uid, db_client=db_client)
            if (
                current_control.writer_mode == WriterMode.transitioning_to_ledger
                and current_control.writer_transition_owner == transition_owner
            ):
                abort_writer_transition(
                    uid,
                    transition_owner=transition_owner,
                    expected_control=current_control,
                    db_client=db_client,
                )
        except Exception:
            # Preserve the original failure. A same-owner future run can resume
            # a transition if the best-effort safety abort itself is unavailable.
            pass
        raise


def rollback_ledger_writer_to_compatibility(
    uid: str,
    *,
    db_client: Any,
    rollback_authorizer: Callable[[], bool],
    completed_at: datetime | None = None,
) -> MemoryControlState:
    """Fence ledger writers and restore the compatibility union without rewriting rows.

    This bridge rollback is intentionally control-plane-only. Ledger rows,
    preserved generated history, evidence, and prompt receipts remain durable;
    compatibility readers resume their explicit mixed-schema union.
    """
    transition_owner = "knowledge-ledger-rollback.v1"

    def require_rollback_authority() -> None:
        try:
            authorized = rollback_authorizer()
        except Exception as exc:
            raise LedgerMigrationPublicationError("ledger rollback authorization failed") from exc
        if not authorized:
            raise LedgerMigrationPublicationError("ledger rollback authorization denied")

    require_rollback_authority()
    initial_control = _read_control(uid, db_client=db_client)
    if initial_control.writer_mode == WriterMode.compatibility:
        return initial_control
    if initial_control.writer_mode == WriterMode.ledger:
        try:
            transition_control = begin_writer_transition(
                uid,
                target_mode=WriterMode.compatibility,
                transition_owner=transition_owner,
                expected_control=initial_control,
                db_client=db_client,
            )
        except WriterTransitionError as exc:
            raise LedgerMigrationPublicationError("ledger rollback transition could not begin") from exc
    elif (
        initial_control.writer_mode == WriterMode.transitioning_to_compatibility
        and initial_control.writer_transition_owner == transition_owner
    ):
        transition_control = initial_control
    else:
        raise LedgerMigrationPublicationError("another writer transition owns the account")

    try:
        scanned = 0
        digest_rows: list[dict[str, Any]] = []
        for row in memory_service.MemoryService(db_client=db_client).iter_export_memories(uid, include_archive=True):
            scanned += 1
            if scanned > MAX_LEDGER_MIGRATION_SCAN_ROWS:
                raise LedgerMigrationPublicationError("rollback union scan exceeds the controlled row limit")
            if row.uid != uid:
                raise LedgerMigrationPublicationError("rollback union scan returned a foreign row")
            digest_rows.append(_content_free_union_record(row))

        observed_control = _read_control(uid, db_client=db_client)
        if not _same_control_fence(observed_control, transition_control):
            raise LedgerMigrationPublicationError("canonical control changed during rollback proof scan")
        require_rollback_authority()
        proof = CompleteUnionProofReceipt(
            uid=uid,
            transition_owner=transition_owner,
            writer_mode=observed_control.writer_mode,
            target_mode=WriterMode.compatibility,
            writer_epoch=observed_control.writer_epoch,
            head_commit_id=observed_control.head_commit_id,
            account_generation=observed_control.account_generation,
            source_generation=observed_control.source_generation,
            commit_sequence=observed_control.commit_sequence,
            complete_union_digest=_content_free_union_digest(digest_rows),
            complete_union_count=scanned,
            generated_at=completed_at or datetime.now(timezone.utc),
        )
        return complete_writer_transition(
            uid,
            transition_owner=transition_owner,
            expected_control=observed_control,
            receipt=proof,
            db_client=db_client,
        )
    except Exception:
        try:
            current_control = _read_control(uid, db_client=db_client)
            if (
                current_control.writer_mode == WriterMode.transitioning_to_compatibility
                and current_control.writer_transition_owner == transition_owner
            ):
                abort_writer_transition(
                    uid,
                    transition_owner=transition_owner,
                    expected_control=current_control,
                    db_client=db_client,
                )
        except Exception:
            pass
        raise


class LedgerMigrationSweepResult(BaseModel):
    uid: str
    scanned_row_count: int = Field(ge=0)
    migrated_long_term_count: int = Field(ge=0)
    adjudicated_short_term_count: int = Field(ge=0)
    already_ledger_count: int = Field(ge=0)
    preserved_historical_legacy_count: int = Field(ge=0)
    remaining_live_legacy_count: int = Field(ge=0)
    authorization_revoked: bool = False
    receipt: LedgerPromptProjectionReceipt | None = None


def run_ledger_migration_sweep(
    uid: str,
    *,
    db_client: Any,
    mutation_authorizer: Callable[[str], bool],
    publication_authorizer: Callable[[], bool],
    publish: bool,
    completed_at: datetime | None = None,
) -> LedgerMigrationSweepResult:
    """Resumable production sweep used by the canonical maintenance job.

    Each live canonical legacy row is adapted through the normal canonical
    apply transaction. Already-adapted rows are idempotent resume points.
    Inactive/archive legacy rows are deliberately preserved for explicit
    historical export/query and never rewritten merely to satisfy prompt
    cutover. Every canonical mutation requires a fresh affirmative decision
    from ``mutation_authorizer``; revocation stops the resumable sweep before
    the next write. Publication occurs only after a fresh complete proof scan.
    """
    service = memory_service.MemoryService(db_client=db_client)
    scanned = 0
    migrated = 0
    adjudicated = 0
    already_ledger = 0
    preserved_historical = 0
    live_legacy_ids: list[str] = []
    for row in service.iter_export_memories(uid, include_archive=True):
        scanned += 1
        if scanned > MAX_LEDGER_MIGRATION_SCAN_ROWS:
            raise LedgerMigrationPublicationError("migration scan exceeds the controlled row limit")
        if row.uid != uid:
            raise LedgerMigrationPublicationError("migration scan returned a foreign row")
        if row.ledger_schema_version == LEDGER_SCHEMA_VERSION:
            already_ledger += 1
        elif _legacy_prompt_serving(row):
            live_legacy_ids.append(row.id)
        else:
            preserved_historical += 1

    admitted_ids = live_legacy_ids[:MAX_LEDGER_MIGRATION_MUTATIONS_PER_RUN]
    handled_rows = 0
    authorization_revoked = False

    for memory_id in admitted_ids:
        item = read_canonical_memory_item(uid, memory_id, db_client=db_client)
        if item is None:
            # Materialization is itself a canonical mutation. It needs a fresh
            # authority decision independently of the later ledger adaptation.
            if not mutation_authorizer(memory_id):
                authorization_revoked = True
                break
            try:
                item = service.materialize_legacy_for_ledger_migration(uid, memory_id)
            except Exception as exc:
                raise LedgerMigrationPublicationError("live legacy row lacks canonical migration authority") from exc
        plan = plan_ledger_migration(item)
        if plan.action == LedgerMigrationAction.adapt_long_term_history:
            if not mutation_authorizer(memory_id):
                authorization_revoked = True
                break
            apply_ledger_migration_plan(uid, plan, db_client=db_client)
            migrated += 1
        elif plan.action == LedgerMigrationAction.adjudicate_short_term:
            if not mutation_authorizer(memory_id):
                authorization_revoked = True
                break
            close_canonical_legacy_generated_history(
                uid,
                memory_id,
                expected_item_revision=plan.source_revision,
                expected_tier=item.tier,
                db_client=db_client,
            )
            adjudicated += 1
        elif plan.action == LedgerMigrationAction.no_op:
            already_ledger += 1
        else:
            raise LedgerMigrationPublicationError(f"live legacy row remains blocked: {plan.reason}")
        handled_rows += 1

    remaining = max(0, len(live_legacy_ids) - handled_rows)
    if remaining and publish:
        raise LedgerMigrationPublicationError(
            f"migration mutation budget exhausted with {remaining} live rows remaining"
        )
    receipt = None
    if publish:
        receipt = publish_ledger_migration_cutover(
            uid,
            db_client=db_client,
            publication_authorizer=publication_authorizer,
            mutation_authorizer=mutation_authorizer,
            migrated_long_term_count=migrated,
            adjudicated_short_term_count=adjudicated,
            completed_at=completed_at,
        )
    return LedgerMigrationSweepResult(
        uid=uid,
        scanned_row_count=scanned,
        migrated_long_term_count=migrated,
        adjudicated_short_term_count=adjudicated,
        already_ledger_count=already_ledger,
        preserved_historical_legacy_count=preserved_historical,
        remaining_live_legacy_count=remaining,
        authorization_revoked=authorization_revoked,
        receipt=receipt,
    )


def read_ledger_migration_completion(uid: str, *, db_client: Any) -> Optional[LedgerMigrationCompletion]:
    """Fail closed unless completion belongs to the current stable ledger epoch."""
    snapshot = db_client.document(MemoryCollections(uid=uid).knowledge_ledger_migration_state).get()
    if not getattr(snapshot, "exists", False):
        return None
    try:
        completion = LedgerMigrationCompletion.model_validate(snapshot.to_dict() or {})
        completion.validate_complete()
        control = _read_control(uid, db_client=db_client)
    except (TypeError, ValueError):
        return None
    except LedgerMigrationPublicationError:
        return None
    if (
        control.writer_mode != WriterMode.ledger
        or control.writer_epoch != completion.writer_epoch
        or control.head_commit_id != completion.source_head_commit_id
    ):
        return None
    return completion


def read_ledger_prompt_projection_receipt(
    uid: str,
    *,
    db_client: Any,
    completion: LedgerMigrationCompletion,
) -> Optional[LedgerPromptProjectionReceipt]:
    """Read an O(1), generation-fenced proof and bounded prompt projection."""
    collections = MemoryCollections(uid=uid)
    control_ref = db_client.document(collections.memory_apply_control_state)
    control_before_snapshot = control_ref.get()
    receipt_snapshot = db_client.document(collections.knowledge_ledger_prompt_projection).get()
    control_after_snapshot = control_ref.get()
    if (
        not getattr(receipt_snapshot, "exists", False)
        or not getattr(control_before_snapshot, "exists", False)
        or not getattr(control_after_snapshot, "exists", False)
    ):
        return None
    try:
        receipt = LedgerPromptProjectionReceipt.model_validate(receipt_snapshot.to_dict() or {})
        control_before = MemoryControlState.model_validate(control_before_snapshot.to_dict() or {})
        control_after = MemoryControlState.model_validate(control_after_snapshot.to_dict() or {})
        if not _same_control_fence(control_before, control_after):
            return None
        receipt.validate_authoritative(uid=uid, completion=completion, control=control_after)
    except (TypeError, ValueError):
        return None
    return receipt


def _subject_scope(item: MemoryItem) -> MemorySubjectScope:
    attribution = str(((item.promotion or {}).get("source_attribution") or {}).get("subject_attribution") or "")
    if attribution == "third_party":
        return MemorySubjectScope.third_party
    if item.subject_entity_id and item.subject_entity_id != "user":
        return MemorySubjectScope.third_party
    return MemorySubjectScope.primary_user


def plan_ledger_migration(item: MemoryItem) -> LedgerMigrationPlan:
    """Return one deterministic migration decision without touching storage."""
    if item.ledger_schema_version == LEDGER_SCHEMA_VERSION:
        return LedgerMigrationPlan(
            memory_id=item.memory_id,
            source_revision=item.item_revision,
            action=LedgerMigrationAction.no_op,
            reason="already_ledger_v1",
        )
    if item.status != MemoryItemStatus.active:
        return LedgerMigrationPlan(
            memory_id=item.memory_id,
            source_revision=item.item_revision,
            action=LedgerMigrationAction.ignore_inactive,
            reason=f"inactive_{item.status.value}",
        )
    if item.tier == MemoryLayer.short_term:
        return LedgerMigrationPlan(
            memory_id=item.memory_id,
            source_revision=item.item_revision,
            action=LedgerMigrationAction.adjudicate_short_term,
            reason="short_term_requires_explicit_adjudication",
            requires_human_or_policy_adjudication=True,
        )
    # archive_requires_explicit_query: archive history is never a default-read
    # migration candidate and requires an explicit adjudication capability.
    if item.tier == MemoryLayer.archive:
        return LedgerMigrationPlan(
            memory_id=item.memory_id,
            source_revision=item.item_revision,
            action=LedgerMigrationAction.ignore_inactive,
            reason="archive_history_requires_explicit_adjudication",
            requires_human_or_policy_adjudication=True,
        )

    scope = _subject_scope(item)
    write_reason = LedgerWriteReason.direct_user_statement if item.user_asserted else LedgerWriteReason.legacy_migration
    return LedgerMigrationPlan(
        memory_id=item.memory_id,
        source_revision=item.item_revision,
        action=LedgerMigrationAction.adapt_long_term_history,
        reason="canonical_long_term_adapts_in_place",
        updates={
            "ledger_schema_version": LEDGER_SCHEMA_VERSION,
            "kind": MemoryKind.fact.value,
            "subject_scope": scope.value,
            "slot": LEDGER_SLOT_BY_LEGACY_PREDICATE.get(item.predicate or ""),
            "valid_from": item.captured_at,
            # Preserve historical/expiry semantics. Clearing this boundary
            # would make a closed legacy row look current in the ledger view.
            "valid_to": item.valid_to,
            "curation_weight": 0,
            "trigger_condition": {},
            "intent_backed": bool(item.user_asserted),
            "write_reason": write_reason.value,
        },
    )


def migration_marker(plan: LedgerMigrationPlan) -> Optional[str]:
    """Stable per-row resume marker for an authorized batch runner."""
    if plan.action not in {LedgerMigrationAction.no_op, LedgerMigrationAction.adapt_long_term_history}:
        return None
    return f"{LEDGER_SCHEMA_VERSION}:{plan.memory_id}:r{plan.source_revision}"


def apply_ledger_migration_plan(uid: str, plan: LedgerMigrationPlan, *, db_client: Any) -> MemoryItem:
    """Apply one previously planned row through canonical transaction fences."""
    if plan.action == LedgerMigrationAction.adapt_long_term_history:
        return adapt_canonical_memory_to_knowledge_ledger(
            uid,
            plan.memory_id,
            expected_item_revision=plan.source_revision,
            updates=plan.updates,
            db_client=db_client,
        )
    if plan.action == LedgerMigrationAction.no_op:
        item = read_canonical_memory_item(uid, plan.memory_id, db_client=db_client)
        if item is None or item.ledger_schema_version != LEDGER_SCHEMA_VERSION:
            raise ValueError("ledger migration no-op row is no longer active ledger history")
        return item
    raise ValueError(f"ledger migration action requires adjudication, not automatic apply: {plan.action.value}")


__all__ = [
    "LedgerMigrationCompletion",
    "LedgerMigrationPublicationError",
    "LedgerMigrationSweepResult",
    "LedgerPromptProjectionReceipt",
    "MAX_LEDGER_PROMPT_PROJECTION_ROWS",
    "MAX_LEDGER_MIGRATION_SCAN_ROWS",
    "MAX_LEDGER_MIGRATION_MUTATIONS_PER_RUN",
    "apply_ledger_migration_plan",
    "LedgerMigrationAction",
    "LedgerMigrationPlan",
    "migration_marker",
    "plan_ledger_migration",
    "publish_ledger_migration_cutover",
    "read_ledger_migration_completion",
    "read_ledger_prompt_projection_receipt",
    "run_ledger_migration_sweep",
]
