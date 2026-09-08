"""Hermetic planner/resume proof for the one-time knowledge-ledger migration.

LIFECYCLE: permanent

The runner has no Firestore or production entry point. It executes deterministic
plans only through an injected apply function and emits a content-free report so
tests can prove planner counts, minimum provenance identity, profile rendering,
and resume bookkeeping without checking user text into the repository or writing
completion markers. It does not prove the canonical transaction or authorize a
migration-completion marker.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, Dict, Iterable, Literal, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from models.product_memory import MemoryItem
from utils.memory.knowledge_ledger import LEDGER_SCHEMA_VERSION, render_profile
from utils.memory.knowledge_ledger_migration import (
    LedgerMigrationAction,
    LedgerMigrationPlan,
    migration_marker,
    plan_ledger_migration,
)

ApplyMigrationPlan = Callable[[str, LedgerMigrationPlan], MemoryItem]


class MigrationFixtureReport(BaseModel):
    """Planner proof containing counts and digests, never memory content."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["knowledge_ledger.fixture.v1"] = "knowledge_ledger.fixture.v1"
    total_rows: int = Field(ge=0)
    action_counts: Dict[str, int] = Field(default_factory=dict)
    applied_count: int = Field(ge=0)
    resumed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    blocking_row_count: int = Field(ge=0)
    provenance_complete_count: int = Field(ge=0)
    profile_slot_count: int = Field(ge=0)
    profile_character_count: int = Field(ge=0)
    profile_sha256: str = Field(min_length=64, max_length=64)
    planner_admissible: bool


@dataclass(frozen=True)
class MigrationFixtureExecution:
    """In-memory synthetic outputs plus the safe serializable report."""

    report: MigrationFixtureReport
    items: Tuple[MemoryItem, ...]
    completed_markers: frozenset[str]


def _provenance_is_complete(item: MemoryItem) -> bool:
    return bool(item.evidence) and all(
        evidence.evidence_id.strip() and (evidence.source_id or "").strip() and (evidence.source_version or "").strip()
        for evidence in item.evidence
    )


def run_migration_fixture(
    uid: str,
    items: Iterable[MemoryItem],
    *,
    apply_plan: ApplyMigrationPlan,
    completed_markers: Iterable[str] = (),
) -> MigrationFixtureExecution:
    """Execute a deterministic synthetic batch and return content-free proof.

    An already-completed marker is accepted only when the supplied current row
    is already ledger-shaped.  A marker beside an unchanged legacy row is a
    stale/inconsistent resume state and remains blocking.
    """

    source_items = sorted(tuple(items), key=lambda item: item.memory_id)
    markers: Set[str] = {marker for marker in completed_markers if marker}
    output_items: list[MemoryItem] = []
    action_counts = {action.value: 0 for action in LedgerMigrationAction}
    applied_count = 0
    resumed_count = 0
    failed_count = 0
    blocking_count = 0

    for item in source_items:
        if item.uid != uid:
            failed_count += 1
            blocking_count += 1
            output_items.append(item)
            continue
        plan = plan_ledger_migration(item)
        action_counts[plan.action.value] += 1
        marker = migration_marker(plan)
        if plan.action == LedgerMigrationAction.no_op and item.ledger_schema_version == LEDGER_SCHEMA_VERSION:
            resumed_count += 1
            if marker:
                markers.add(marker)
            output_items.append(item)
            continue
        if marker and marker in markers:
            if item.ledger_schema_version == LEDGER_SCHEMA_VERSION:
                resumed_count += 1
            else:
                failed_count += 1
                blocking_count += 1
            output_items.append(item)
            continue
        if plan.requires_human_or_policy_adjudication:
            blocking_count += 1
            output_items.append(item)
            continue
        if plan.action == LedgerMigrationAction.ignore_inactive:
            output_items.append(item)
            continue
        try:
            migrated = apply_plan(uid, plan)
            if migrated.uid != uid or migrated.memory_id != item.memory_id:
                raise ValueError("fixture apply returned mismatched authority")
            if migrated.ledger_schema_version != LEDGER_SCHEMA_VERSION:
                raise ValueError("fixture apply did not produce ledger v1")
        except Exception:
            failed_count += 1
            blocking_count += 1
            output_items.append(item)
            continue
        output_items.append(migrated)
        applied_count += 1
        applied_marker = migration_marker(plan)
        if applied_marker:
            markers.add(applied_marker)

    ledger_items = [item for item in output_items if item.ledger_schema_version == LEDGER_SCHEMA_VERSION]
    provenance_complete_count = sum(1 for item in ledger_items if _provenance_is_complete(item))
    profile = render_profile(ledger_items)
    report = MigrationFixtureReport(
        total_rows=len(source_items),
        action_counts=action_counts,
        applied_count=applied_count,
        resumed_count=resumed_count,
        failed_count=failed_count,
        blocking_row_count=blocking_count,
        provenance_complete_count=provenance_complete_count,
        profile_slot_count=len(profile.splitlines()) if profile else 0,
        profile_character_count=len(profile),
        profile_sha256=hashlib.sha256(profile.encode("utf-8")).hexdigest(),
        planner_admissible=(
            blocking_count == 0 and failed_count == 0 and provenance_complete_count == len(ledger_items)
        ),
    )
    return MigrationFixtureExecution(
        report=report,
        items=tuple(output_items),
        completed_markers=frozenset(markers),
    )


__all__ = [
    "MigrationFixtureExecution",
    "MigrationFixtureReport",
    "run_migration_fixture",
]
