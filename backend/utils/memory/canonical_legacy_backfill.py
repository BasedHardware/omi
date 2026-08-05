"""Bounded legacy-to-canonical staging for the code-owned memory cohort.

LIFECYCLE: permanent

This is an orchestration seam for a future maintenance owner. It selects only
users returned by ``list_canonical_cohort_uids()``, stages at most one bounded
page of legacy rows per user, and resumes from the existing durable bulk
checkpoint. It verifies the existing per-user write-stage enrollment control
but does not change rollout documents, global gates, or read grants. Terminal
processing and any later promotion remain owned by the canonical maintenance
pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import partial
from typing import Any, Optional

from database._client import get_firestore_client
from database.memory_collections import MemoryCollections
from scripts.enroll_canonical_memory_user import build_user_control_state
from utils.memory.bulk_legacy_backfill import (
    BulkMigrationConfig,
    BulkRunSummary,
    FirestoreCheckpointStore,
    MigrationState,
    read_global_pause,
    run_bulk_migration,
)
from utils.memory.canonical_activation import canonical_write_decision
from utils.memory.legacy_backfill import BackfillReport, backfill_user
from utils.memory.legacy_backfill_inventory import inventory_legacy_user
from utils.memory.memory_system import list_canonical_cohort_uids

DEFAULT_COHORT_PAGE_SIZE = 10
MAX_COHORT_PAGE_SIZE = 100
DEFAULT_MAX_ROWS_PER_USER = 100
MAX_ROWS_PER_USER = 100


@dataclass(frozen=True)
class CanonicalLegacyBackfillConfig:
    """One bounded apply/inventory page for canonical legacy backfill."""

    page_size: int = DEFAULT_COHORT_PAGE_SIZE
    max_rows_per_user: int = DEFAULT_MAX_ROWS_PER_USER
    max_estimated_tokens_per_run: int = 100_000
    wall_clock_seconds: Optional[float] = None
    dry_run: bool = True

    def __post_init__(self) -> None:
        if self.page_size <= 0 or self.page_size > MAX_COHORT_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {MAX_COHORT_PAGE_SIZE}")
        if self.max_rows_per_user <= 0 or self.max_rows_per_user > MAX_ROWS_PER_USER:
            raise ValueError(f"max_rows_per_user must be between 1 and {MAX_ROWS_PER_USER}")
        if self.max_estimated_tokens_per_run <= 0:
            raise ValueError("max_estimated_tokens_per_run must be positive")
        if self.wall_clock_seconds is not None and self.wall_clock_seconds <= 0:
            raise ValueError("wall_clock_seconds must be positive")


@dataclass(frozen=True)
class CanonicalLegacyBackfillPage:
    """Content-free result for one bounded cohort operation."""

    cohort_user_count: int
    pending_user_count: int
    selected_uids: tuple[str, ...]
    remaining_user_count: int
    summary: BulkRunSummary

    @property
    def has_more(self) -> bool:
        return self.remaining_user_count > 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["selected_uids"] = list(self.selected_uids)
        payload["summary"] = self.summary.to_dict()
        return payload


def _cohort_uids_with_pending_checkpoints(
    checkpoint_store: FirestoreCheckpointStore,
) -> tuple[tuple[str, ...], list[str]]:
    """Return the current whitelist and users not durably marked complete."""
    cohort_uids = tuple(list_canonical_cohort_uids())
    pending_uids = _pending_uids(cohort_uids, checkpoint_store)
    return cohort_uids, pending_uids


def _pending_uids(cohort_uids: tuple[str, ...], checkpoint_store: FirestoreCheckpointStore) -> list[str]:
    return [uid for uid in cohort_uids if checkpoint_store.read(uid).state != MigrationState.read_ready]


def _cohort_enrollment_hook(
    uid: str,
    *,
    canonical_uids: frozenset[str],
    db_client: Any,
) -> None:
    """Verify whitelist and existing write enrollment before staging.

    The bulk state machine treats ``enroll_fn`` as a side effect that makes a
    user write-ready; once it returns, the checkpoint advances through
    ``enrolled`` toward the terminal ``read_ready`` state. Because this seam is
    not the enrollment owner, it must only advance users the cohort whitelist
    has already enrolled. Passing ``enroll_fn`` to ``run_bulk_migration`` without
    this guard would let a non-enrolled uid reach ``read_ready``, permanently
    blocking the real enrollment owner until the checkpoint is manually repaired.
    """
    if uid not in canonical_uids:
        raise ValueError(
            f"refusing to advance checkpoint for non-cohort uid {uid!r}: "
            "canonical legacy backfill is not the enrollment owner"
        )
    path = MemoryCollections(uid=uid).memory_control_state
    snapshot = db_client.document(path).get()
    if not getattr(snapshot, "exists", False):
        raise RuntimeError("missing_write_stage_enrollment_control")
    payload = snapshot.to_dict()
    if not isinstance(payload, dict):
        raise RuntimeError("malformed_write_stage_enrollment_control")

    account_generation = payload.get("account_generation")
    if isinstance(account_generation, bool) or not isinstance(account_generation, int) or account_generation < 0:
        raise RuntimeError("malformed_write_stage_enrollment_control")

    expected = build_user_control_state(
        uid=uid,
        stage="write",
        account_generation=account_generation,
    )
    if payload.get("uid") != expected["uid"] or payload.get("schema_version") != expected["schema_version"]:
        raise RuntimeError("malformed_write_stage_enrollment_control")
    if payload.get("mode") not in {"write", "read"}:
        raise RuntimeError("write_stage_enrollment_control_not_ready")
    for field in ("persistent_memory_writes_started", "writes_blocked"):
        if payload.get(field) != expected[field]:
            raise RuntimeError("write_stage_enrollment_control_not_ready")
    stage_gates = payload.get("stage_gates")
    if not isinstance(stage_gates, dict) or any(
        stage_gates.get(gate) != expected["stage_gates"][gate] for gate in ("shadow", "write")
    ):
        raise RuntimeError("write_stage_enrollment_control_not_ready")

    decision = canonical_write_decision(uid, db_client=db_client)
    if not decision.enabled:
        raise RuntimeError(f"write_stage_enrollment_control_not_ready:{decision.reason}")


def run_canonical_legacy_backfill_page(
    *,
    config: CanonicalLegacyBackfillConfig = CanonicalLegacyBackfillConfig(),
    db_client: Any = None,
) -> CanonicalLegacyBackfillPage:
    """Stage one resumable page for the currently whitelisted canonical users.

    Repeated calls are safe: completed users are skipped by their durable
    checkpoint, while paused users resume through the existing per-user legacy
    checkpoint. The operation never accepts a caller-supplied UID list, so an
    admin override cannot widen its cohort.
    """
    client = db_client if db_client is not None else get_firestore_client()
    checkpoint_store = FirestoreCheckpointStore(client)
    cohort_uids, pending_uids = _cohort_uids_with_pending_checkpoints(checkpoint_store)
    selected_uids = tuple(pending_uids[: config.page_size])
    bulk_config = BulkMigrationConfig(
        dry_run=config.dry_run,
        max_users_per_run=config.page_size,
        max_admitted_rows_per_user=config.max_rows_per_user,
        max_estimated_tokens_per_run=config.max_estimated_tokens_per_run,
        wall_clock_seconds=config.wall_clock_seconds,
        concurrency_limit=1,
        process_buckets=(),
    )

    def inventory_fn(uid: str):
        if not config.dry_run:
            _cohort_enrollment_hook(uid, db_client=client)
        return inventory_legacy_user(uid, db_client=client)

    def backfill_fn(
        uid: str,
        max_rows: int,
        resume: bool,
        stop_requested: Callable[[], bool],
    ) -> BackfillReport:
        _cohort_enrollment_hook(uid, db_client=client)
        return backfill_user(
            uid,
            dry_run=False,
            batch_size=max_rows,
            resume=resume,
            max_rows=max_rows,
            continue_on_error=True,
            stop_requested=stop_requested,
            db_client=client,
        )

    summary = run_bulk_migration(
        selected_uids,
        config=bulk_config,
        inventory_fn=inventory_fn,
        pause_fn=lambda: read_global_pause(client),
        checkpoint_store=None if config.dry_run else checkpoint_store,
        enroll_fn=None
        if config.dry_run
        else partial(_cohort_enrollment_hook, canonical_uids=frozenset(cohort_uids), db_client=client),
        backfill_fn=None if config.dry_run else backfill_fn,
    )

    pending_after = _pending_uids(cohort_uids, checkpoint_store)
    return CanonicalLegacyBackfillPage(
        cohort_user_count=len(cohort_uids),
        pending_user_count=len(pending_uids),
        selected_uids=selected_uids,
        remaining_user_count=len(pending_after),
        summary=summary,
    )


__all__ = [
    "CanonicalLegacyBackfillConfig",
    "CanonicalLegacyBackfillPage",
    "DEFAULT_COHORT_PAGE_SIZE",
    "DEFAULT_MAX_ROWS_PER_USER",
    "MAX_COHORT_PAGE_SIZE",
    "MAX_ROWS_PER_USER",
    "run_canonical_legacy_backfill_page",
]
