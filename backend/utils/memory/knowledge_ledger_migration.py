"""Deterministic, resumable planning for canonical-to-ledger migration.

The planner is side-effect free. Production callers must apply its output
through canonical apply with the current item revision and control head; this
module never writes legacy or canonical collections directly.
"""

from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from database.memory_collections import MemoryCollections
from models.knowledge_ledger_policy import LEDGER_SLOT_BY_LEGACY_PREDICATE
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
    read_canonical_memory_item,
)
from utils.memory.knowledge_ledger import LEDGER_SCHEMA_VERSION


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


def read_ledger_migration_completion(uid: str, *, db_client: Any) -> Optional[LedgerMigrationCompletion]:
    """Fail closed when the per-user completion proof is absent or malformed."""
    snapshot = db_client.document(MemoryCollections(uid=uid).knowledge_ledger_migration_state).get()
    if not getattr(snapshot, "exists", False):
        return None
    try:
        completion = LedgerMigrationCompletion.model_validate(snapshot.to_dict() or {})
        completion.validate_complete()
    except (TypeError, ValueError):
        return None
    return completion


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
    "apply_ledger_migration_plan",
    "LedgerMigrationAction",
    "LedgerMigrationPlan",
    "migration_marker",
    "plan_ledger_migration",
    "read_ledger_migration_completion",
]
