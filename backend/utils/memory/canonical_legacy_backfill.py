"""Bounded legacy-to-canonical staging for the code-owned memory cohort.

LIFECYCLE: permanent

This is an orchestration seam for a future maintenance owner. It selects only
users returned by ``list_canonical_cohort_uids()``, stages at most one bounded
page of legacy rows per user, and resumes from the existing durable bulk
checkpoint. It does not change rollout documents or read grants. Terminal
processing and any later promotion remain owned by the canonical maintenance
pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Optional

from database._client import get_firestore_client
from utils.memory.bulk_legacy_backfill import (
    BulkMigrationConfig,
    BulkRunSummary,
    FirestoreCheckpointStore,
    MigrationState,
    read_global_pause,
    run_bulk_migration,
)
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
    dry_run: bool = False

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


def _cohort_enrollment_hook(uid: str) -> None:
    """Satisfy the bulk state machine without writing rollout documents."""
    del uid


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

    def backfill_fn(
        uid: str,
        max_rows: int,
        resume: bool,
        stop_requested: Callable[[], bool],
    ) -> BackfillReport:
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
        inventory_fn=lambda uid: inventory_legacy_user(uid, db_client=client),
        pause_fn=lambda: read_global_pause(client),
        checkpoint_store=None if config.dry_run else checkpoint_store,
        enroll_fn=None if config.dry_run else _cohort_enrollment_hook,
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
