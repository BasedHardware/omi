"""Governed multi-user legacy-to-canonical memory migration orchestration.

LIFECYCLE: permanent

This module coordinates existing enrollment and backfill primitives. It never
reads or returns raw memory content, never mutates legacy memory rows, and never
changes the code-owned canonical cohort or a user's read mode. Canonical L2
processing and promotion remain owned by ``memory-maintenance-job``.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Iterable, Optional, Protocol, Sequence

from database.memory_collections import MemoryCollections
from utils.executors import db_executor
from utils.memory.legacy_backfill_bulk_support import LegacyBackfillInventoryReport

GLOBAL_PAUSE_PATH = "memory_control/legacy_canonical_backfill_pause"
PAUSE_ENV = "MEMORY_BULK_BACKFILL_PAUSED"
WRITABLE_BUCKETS = frozenset({"manual_required_promotion", "reviewed_long_term"})


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value.strip()))
        except ValueError:
            return 0
    return 0


def _strict_bool(value: object) -> bool:
    # Firestore writes this as a native boolean.  Treat every drifted value as
    # false so malformed legacy data cannot accidentally claim stage success.
    return value if isinstance(value, bool) else False


class BackfillReport(Protocol):
    @property
    def written_count(self) -> int: ...

    @property
    def skipped_already_present(self) -> int: ...

    @property
    def skipped_both_store_duplicate(self) -> int: ...

    @property
    def destination_count(self) -> int: ...

    @property
    def intended_count(self) -> int: ...

    @property
    def legacy_rows_touched(self) -> int: ...

    @property
    def completed(self) -> bool: ...

    @property
    def verified(self) -> bool: ...

    @property
    def cohort_gated(self) -> bool: ...

    @property
    def errors(self) -> list[str]: ...


class MigrationState(str, Enum):
    not_started = "not_started"
    inventory_done = "inventory_done"
    enrolled = "enrolled"
    staged = "staged"
    processing = "processing"
    read_ready = "read_ready"
    failed = "failed"
    paused = "paused"


_FORWARD_TRANSITIONS: Dict[MigrationState, frozenset[MigrationState]] = {
    MigrationState.not_started: frozenset(
        {MigrationState.inventory_done, MigrationState.paused, MigrationState.failed}
    ),
    MigrationState.inventory_done: frozenset({MigrationState.enrolled, MigrationState.paused, MigrationState.failed}),
    MigrationState.enrolled: frozenset(
        {MigrationState.processing, MigrationState.staged, MigrationState.paused, MigrationState.failed}
    ),
    MigrationState.processing: frozenset({MigrationState.staged, MigrationState.paused, MigrationState.failed}),
    MigrationState.staged: frozenset({MigrationState.processing, MigrationState.paused, MigrationState.failed}),
    # ``read_ready`` is a retired legacy marker.  It remains parseable so an
    # old checkpoint can be reopened as staged/unverified, but no new write
    # may target it.
    MigrationState.read_ready: frozenset({MigrationState.staged, MigrationState.paused, MigrationState.failed}),
    MigrationState.failed: frozenset(
        {
            MigrationState.inventory_done,
            MigrationState.enrolled,
            MigrationState.processing,
            MigrationState.staged,
            MigrationState.paused,
        }
    ),
    MigrationState.paused: frozenset(
        {
            MigrationState.inventory_done,
            MigrationState.enrolled,
            MigrationState.processing,
            MigrationState.staged,
            MigrationState.failed,
        }
    ),
}


def validate_checkpoint_transition(current: MigrationState, target: MigrationState) -> None:
    """Reject checkpoint regressions while allowing idempotent re-entry."""
    if current == target:
        return
    if target not in _FORWARD_TRANSITIONS[current]:
        raise ValueError(f"invalid bulk memory migration transition: {current.value} -> {target.value}")


@dataclass(frozen=True)
class MigrationCheckpoint:
    uid: str
    state: MigrationState = MigrationState.not_started
    resume_state: Optional[MigrationState] = None
    source_count: int = 0
    bucket_counts: Dict[str, int] = field(default_factory=dict)
    admitted_candidate_count: int = 0
    admitted_candidate_estimated_tokens: int = 0
    staged_count: int = 0
    staging_complete: bool = False
    error_count: int = 0
    last_error_code: Optional[str] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_payload(cls, uid: str, payload: object) -> "MigrationCheckpoint":
        if not isinstance(payload, dict):
            return cls(uid=uid)
        try:
            state = MigrationState(str(payload.get("state", MigrationState.not_started.value)))
        except ValueError:
            state = MigrationState.failed
        raw_resume = payload.get("resume_state")
        try:
            resume_state = MigrationState(str(raw_resume)) if raw_resume else None
        except ValueError:
            resume_state = None
        raw_buckets = payload.get("bucket_counts")
        bucket_counts = (
            {str(key): _nonnegative_int(value) for key, value in raw_buckets.items()}
            if isinstance(raw_buckets, dict)
            else {}
        )
        return cls(
            uid=uid,
            state=state,
            resume_state=resume_state,
            source_count=_nonnegative_int(payload.get("source_count", 0)),
            bucket_counts=bucket_counts,
            admitted_candidate_count=_nonnegative_int(payload.get("admitted_candidate_count", 0)),
            admitted_candidate_estimated_tokens=_nonnegative_int(payload.get("admitted_candidate_estimated_tokens", 0)),
            staged_count=_nonnegative_int(payload.get("staged_count", 0)),
            staging_complete=_strict_bool(payload.get("staging_complete", False)),
            error_count=_nonnegative_int(payload.get("error_count", 0)),
            last_error_code=(str(payload["last_error_code"]) if payload.get("last_error_code") is not None else None),
            updated_at=payload.get("updated_at") if isinstance(payload.get("updated_at"), datetime) else None,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "state": self.state.value,
            "resume_state": self.resume_state.value if self.resume_state is not None else None,
            "source_count": self.source_count,
            "bucket_counts": dict(self.bucket_counts),
            "admitted_candidate_count": self.admitted_candidate_count,
            "admitted_candidate_estimated_tokens": self.admitted_candidate_estimated_tokens,
            "staged_count": self.staged_count,
            "staging_complete": self.staging_complete,
            "error_count": self.error_count,
            "last_error_code": self.last_error_code,
            "updated_at": self.updated_at or datetime.now(timezone.utc),
        }


class CheckpointStore(Protocol):
    def read(self, uid: str) -> MigrationCheckpoint: ...

    def write(self, checkpoint: MigrationCheckpoint) -> None: ...


class FirestoreCheckpointStore:
    """Server-owned checkpoint store under each user's ``memory_control``."""

    def __init__(self, db_client: Any):
        self._db_client = db_client

    def read(self, uid: str) -> MigrationCheckpoint:
        snapshot = self._db_client.document(MemoryCollections(uid).legacy_canonical_backfill_checkpoint).get()
        payload = snapshot.to_dict() if getattr(snapshot, "exists", False) else None
        return MigrationCheckpoint.from_payload(uid, payload)

    def write(self, checkpoint: MigrationCheckpoint) -> None:
        current = self.read(checkpoint.uid)
        validate_checkpoint_transition(current.state, checkpoint.state)
        self._db_client.document(MemoryCollections(checkpoint.uid).legacy_canonical_backfill_checkpoint).set(
            checkpoint.to_payload(), merge=True
        )


@dataclass(frozen=True)
class PauseDecision:
    paused: bool
    reason: Optional[str] = None


def read_global_pause(db_client: Any, *, env: Optional[dict[str, str]] = None) -> PauseDecision:
    """Fail closed when the environment or Firestore pause control cannot be cleared."""
    values = os.environ if env is None else env
    if str(values.get(PAUSE_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}:
        return PauseDecision(True, "paused_by_env")
    try:
        snapshot = db_client.document(GLOBAL_PAUSE_PATH).get()
        payload = snapshot.to_dict() if getattr(snapshot, "exists", False) else None
    except Exception:
        return PauseDecision(True, "pause_check_failed")
    if isinstance(payload, dict) and payload.get("paused") is True:
        return PauseDecision(True, "paused_by_firestore")
    return PauseDecision(False)


@dataclass(frozen=True)
class BulkMigrationConfig:
    dry_run: bool = True
    max_users_per_run: int = 10
    max_admitted_rows_per_user: int = 100
    max_estimated_tokens_per_run: int = 100_000
    wall_clock_seconds: Optional[float] = None
    concurrency_limit: int = 1
    process_buckets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.max_users_per_run <= 0:
            raise ValueError("max_users_per_run must be positive")
        if self.max_admitted_rows_per_user <= 0:
            raise ValueError("max_admitted_rows_per_user must be positive")
        if self.max_estimated_tokens_per_run <= 0:
            raise ValueError("max_estimated_tokens_per_run must be positive")
        if self.wall_clock_seconds is not None and self.wall_clock_seconds <= 0:
            raise ValueError("wall_clock_seconds must be positive")
        if self.concurrency_limit <= 0:
            raise ValueError("concurrency_limit must be positive")
        unknown = set(self.process_buckets) - WRITABLE_BUCKETS
        if unknown:
            raise ValueError("unsupported writable bucket(s): " + ", ".join(sorted(unknown)))


@dataclass(frozen=True)
class BulkUserResult:
    uid: str
    state: MigrationState
    inventory: LegacyBackfillInventoryReport
    actions: tuple[str, ...]
    staged_count: int = 0
    error_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "state": self.state.value,
            "inventory": asdict(self.inventory),
            "actions": list(self.actions),
            "staged_count": self.staged_count,
            "error_codes": list(self.error_codes),
        }


@dataclass(frozen=True)
class BulkRunSummary:
    dry_run: bool
    requested_user_count: int
    selected_user_count: int
    processed_user_count: int
    # Retained as a zero-valued compatibility metric; this controller no
    # longer emits read_ready checkpoints or user results.
    read_ready_count: int
    failed_user_count: int
    paused_user_count: int
    admitted_candidate_count: int
    estimated_tokens: int
    stopped_reason: Optional[str]
    users: tuple[BulkUserResult, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["users"] = [user.to_dict() for user in self.users]
        return payload


InventoryFn = Callable[[str], LegacyBackfillInventoryReport]
EnrollFn = Callable[[str], None]
StopFn = Callable[[], bool]
BackfillFn = Callable[[str, int, bool, StopFn], BackfillReport]
BucketProcessFn = Callable[[str, str, int, StopFn], BackfillReport]
PauseFn = Callable[[], PauseDecision]


def _deduplicate_uids(uids: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_uid in uids:
        uid = raw_uid.strip()
        if not uid or uid in seen:
            continue
        ordered.append(uid)
        seen.add(uid)
    return ordered


def _checkpoint_from_inventory(
    inventory: LegacyBackfillInventoryReport,
    *,
    state: MigrationState,
    resume_state: Optional[MigrationState] = None,
    staged_count: int = 0,
    staging_complete: bool = False,
    error_count: int = 0,
    last_error_code: Optional[str] = None,
) -> MigrationCheckpoint:
    return MigrationCheckpoint(
        uid=inventory.uid,
        state=state,
        resume_state=resume_state,
        source_count=inventory.source_count,
        bucket_counts=dict(inventory.bucket_counts),
        admitted_candidate_count=inventory.admitted_candidate_count,
        admitted_candidate_estimated_tokens=inventory.admitted_candidate_estimated_tokens,
        staged_count=staged_count,
        staging_complete=staging_complete,
        error_count=error_count,
        last_error_code=last_error_code,
        updated_at=datetime.now(timezone.utc),
    )


def _paused_result(
    inventory: LegacyBackfillInventoryReport,
    *,
    reason: str,
    actions: Sequence[str],
    staged_count: int = 0,
) -> BulkUserResult:
    return BulkUserResult(
        uid=inventory.uid,
        state=MigrationState.paused,
        inventory=inventory,
        actions=tuple(actions),
        staged_count=staged_count,
        error_codes=(reason,),
    )


def _apply_user(
    inventory: LegacyBackfillInventoryReport,
    *,
    config: BulkMigrationConfig,
    checkpoint_store: CheckpointStore,
    pause_fn: PauseFn,
    enroll_fn: EnrollFn,
    backfill_fn: BackfillFn,
    bucket_process_fn: Optional[BucketProcessFn],
    stop_fn: StopFn,
) -> BulkUserResult:
    current = checkpoint_store.read(inventory.uid)
    if current.state == MigrationState.read_ready:
        # ``read_ready`` was emitted by the retired controller before
        # canonical verification. Reopen it as staged/unverified and require
        # the canonical migration controller to prove projection convergence
        # and perform the explicit read cutover.
        reopened = _checkpoint_from_inventory(
            inventory,
            state=MigrationState.staged,
            staged_count=current.staged_count,
            staging_complete=True,
            last_error_code="legacy_read_ready_unverified",
        )
        checkpoint_store.write(reopened)
        return BulkUserResult(
            uid=inventory.uid,
            state=MigrationState.staged,
            inventory=inventory,
            actions=("legacy_read_ready_reopened_unverified", "canonical_migration_verification_required"),
            staged_count=current.staged_count,
        )

    if current.state == MigrationState.staged and current.staging_complete:
        return BulkUserResult(
            uid=inventory.uid,
            state=MigrationState.staged,
            inventory=inventory,
            actions=("already_staged", "canonical_migration_verification_required"),
            staged_count=current.staged_count,
        )

    resume_state = (
        current.resume_state if current.state in {MigrationState.failed, MigrationState.paused} else current.state
    )
    resume_state = resume_state or MigrationState.not_started
    actions: list[str] = []

    if resume_state == MigrationState.not_started:
        checkpoint_store.write(_checkpoint_from_inventory(inventory, state=MigrationState.inventory_done))
        resume_state = MigrationState.inventory_done
        actions.append("inventory_checkpointed")

    pause = pause_fn()
    if pause.paused:
        reason = pause.reason or "paused"
        checkpoint_store.write(
            _checkpoint_from_inventory(
                inventory,
                state=MigrationState.paused,
                resume_state=resume_state,
                staged_count=current.staged_count,
                staging_complete=current.staging_complete,
                last_error_code=reason,
            )
        )
        return _paused_result(inventory, reason=reason, actions=actions + ["paused_before_enroll_or_stage"])

    if resume_state == MigrationState.inventory_done:
        try:
            enroll_fn(inventory.uid)
        except Exception:
            checkpoint_store.write(
                _checkpoint_from_inventory(
                    inventory,
                    state=MigrationState.failed,
                    resume_state=MigrationState.inventory_done,
                    staging_complete=False,
                    error_count=current.error_count + 1,
                    last_error_code="enrollment_failed",
                )
            )
            return BulkUserResult(
                uid=inventory.uid,
                state=MigrationState.failed,
                inventory=inventory,
                actions=tuple(actions + ["enrollment_failed"]),
                error_codes=("enrollment_failed",),
            )
        checkpoint_store.write(_checkpoint_from_inventory(inventory, state=MigrationState.enrolled))
        resume_state = MigrationState.enrolled
        actions.append("enrolled_write_only")

    pause = pause_fn()
    if pause.paused:
        reason = pause.reason or "paused"
        checkpoint_store.write(
            _checkpoint_from_inventory(
                inventory,
                state=MigrationState.paused,
                resume_state=resume_state,
                staged_count=current.staged_count,
                staging_complete=current.staging_complete,
                last_error_code=reason,
            )
        )
        return _paused_result(inventory, reason=reason, actions=actions + ["paused_before_stage"])

    checkpoint_store.write(_checkpoint_from_inventory(inventory, state=MigrationState.processing))
    resume = current.state != MigrationState.failed
    try:
        report = backfill_fn(inventory.uid, config.max_admitted_rows_per_user, resume, stop_fn)
    except Exception:
        checkpoint_store.write(
            _checkpoint_from_inventory(
                inventory,
                state=MigrationState.failed,
                resume_state=MigrationState.processing,
                staging_complete=False,
                error_count=current.error_count + 1,
                last_error_code="backfill_failed",
            )
        )
        return BulkUserResult(
            uid=inventory.uid,
            state=MigrationState.failed,
            inventory=inventory,
            actions=tuple(actions + ["stage_failed"]),
            error_codes=("backfill_failed",),
        )

    staged_count = report.destination_count
    actions.append("stage_all_for_admission")
    if report.cohort_gated:
        error_code = "cohort_gated"
    elif report.errors:
        error_code = "row_errors"
    else:
        error_code = None
    if error_code is not None:
        checkpoint_store.write(
            _checkpoint_from_inventory(
                inventory,
                state=MigrationState.failed,
                resume_state=MigrationState.processing,
                staged_count=staged_count,
                staging_complete=False,
                error_count=current.error_count + max(1, len(report.errors)),
                last_error_code=error_code,
            )
        )
        return BulkUserResult(
            uid=inventory.uid,
            state=MigrationState.failed,
            inventory=inventory,
            actions=tuple(actions),
            staged_count=staged_count,
            error_codes=(error_code,),
        )

    checkpoint_store.write(
        _checkpoint_from_inventory(
            inventory,
            state=MigrationState.staged,
            staged_count=staged_count,
            staging_complete=bool(report.completed and report.verified),
        )
    )
    if not report.completed or not report.verified:
        pause_reason = "wall_clock_seconds" if stop_fn() else "max_admitted_rows_per_user"
        checkpoint_store.write(
            _checkpoint_from_inventory(
                inventory,
                state=MigrationState.paused,
                resume_state=MigrationState.staged,
                staged_count=staged_count,
                staging_complete=False,
                last_error_code=pause_reason,
            )
        )
        return _paused_result(
            inventory,
            reason=pause_reason,
            actions=actions + ["resume_required"],
            staged_count=staged_count,
        )

    remaining_rows = max(0, config.max_admitted_rows_per_user - report.intended_count)
    required_bucket_rows = sum(inventory.bucket_counts.get(bucket, 0) for bucket in config.process_buckets)
    if required_bucket_rows > remaining_rows:
        checkpoint_store.write(
            _checkpoint_from_inventory(
                inventory,
                state=MigrationState.paused,
                resume_state=MigrationState.staged,
                staged_count=staged_count,
                staging_complete=True,
                last_error_code="max_admitted_rows_per_user",
            )
        )
        return _paused_result(
            inventory,
            reason="max_admitted_rows_per_user",
            actions=actions + ["bucket_processing_deferred_row_cap", "resume_required"],
            staged_count=staged_count,
        )
    for bucket in config.process_buckets:
        if bucket_process_fn is None or remaining_rows == 0:
            break
        bucket_report = bucket_process_fn(inventory.uid, bucket, remaining_rows, stop_fn)
        actions.append(f"processed_bucket:{bucket}")
        consumed = max(bucket_report.legacy_rows_touched, bucket_report.intended_count)
        remaining_rows = max(0, remaining_rows - consumed)
        if bucket_report.errors or bucket_report.cohort_gated:
            checkpoint_store.write(
                _checkpoint_from_inventory(
                    inventory,
                    state=MigrationState.failed,
                    resume_state=MigrationState.staged,
                    staged_count=staged_count,
                    staging_complete=True,
                    error_count=current.error_count + max(1, len(bucket_report.errors)),
                    last_error_code="bucket_processing_failed",
                )
            )
            return BulkUserResult(
                uid=inventory.uid,
                state=MigrationState.failed,
                inventory=inventory,
                actions=tuple(actions),
                staged_count=staged_count,
                error_codes=("bucket_processing_failed",),
            )

    checkpoint_store.write(
        _checkpoint_from_inventory(
            inventory,
            state=MigrationState.staged,
            staged_count=staged_count,
            staging_complete=True,
        )
    )
    actions.append("staged_requires_canonical_migration_verification_and_read_cutover")
    return BulkUserResult(
        uid=inventory.uid,
        state=MigrationState.staged,
        inventory=inventory,
        actions=tuple(actions),
        staged_count=staged_count,
    )


def run_bulk_migration(
    uids: Iterable[str],
    *,
    config: BulkMigrationConfig,
    inventory_fn: InventoryFn,
    pause_fn: Optional[PauseFn] = None,
    checkpoint_store: Optional[CheckpointStore] = None,
    enroll_fn: Optional[EnrollFn] = None,
    backfill_fn: Optional[BackfillFn] = None,
    bucket_process_fn: Optional[BucketProcessFn] = None,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> BulkRunSummary:
    """Inventory and optionally enroll/stage a bounded set of users.

    The planning pass is sequential so pause, wall-clock, and token governors
    make deterministic admission decisions. Apply work is bounded by
    ``concurrency_limit`` and each user remains isolated from failures in peers.
    """
    requested_uids = _deduplicate_uids(uids)
    selected_uids = requested_uids[: config.max_users_per_run]
    stopped_reason = "max_users_per_run" if len(requested_uids) > len(selected_uids) else None
    started_at = monotonic_fn()
    pause_check = pause_fn or (lambda: PauseDecision(False))

    def wall_clock_exhausted() -> bool:
        return config.wall_clock_seconds is not None and monotonic_fn() - started_at >= config.wall_clock_seconds

    def governed_pause_check() -> PauseDecision:
        if wall_clock_exhausted():
            return PauseDecision(True, "wall_clock_seconds")
        return pause_check()

    planned: list[LegacyBackfillInventoryReport] = []
    results: list[BulkUserResult] = []
    estimated_tokens = 0

    for uid in selected_uids:
        pause = governed_pause_check()
        if pause.paused:
            stopped_reason = pause.reason or "paused"
            break
        try:
            inventory = inventory_fn(uid)
        except Exception:
            empty_inventory = LegacyBackfillInventoryReport(
                uid=uid,
                source_count=0,
                bucket_counts={},
                admitted_candidate_count=0,
                content_character_count=0,
                estimated_tokens=0,
                admitted_candidate_estimated_tokens=0,
            )
            results.append(
                BulkUserResult(
                    uid=uid,
                    state=MigrationState.failed,
                    inventory=empty_inventory,
                    actions=("inventory_failed",),
                    error_codes=("inventory_failed",),
                )
            )
            continue
        governed_tokens = inventory.admitted_candidate_estimated_tokens
        if inventory.admitted_candidate_count > config.max_admitted_rows_per_user:
            governed_tokens = (
                inventory.admitted_candidate_estimated_tokens * config.max_admitted_rows_per_user
                + inventory.admitted_candidate_count
                - 1
            ) // inventory.admitted_candidate_count
        projected_tokens = estimated_tokens + governed_tokens
        if projected_tokens > config.max_estimated_tokens_per_run:
            stopped_reason = "max_estimated_tokens_per_run"
            results.append(
                _paused_result(
                    inventory,
                    reason="max_estimated_tokens_per_run",
                    actions=("inventory_only", "not_selected_for_apply"),
                )
            )
            break
        estimated_tokens = projected_tokens
        planned.append(inventory)

    if config.dry_run:
        for inventory in planned:
            actions = [
                "would_enroll_write_only",
                "would_stage_all_for_admission",
                "would_require_canonical_migration_verification_and_read_cutover",
            ]
            actions.extend(f"would_process_bucket:{bucket}" for bucket in config.process_buckets)
            results.append(
                BulkUserResult(
                    uid=inventory.uid,
                    state=MigrationState.inventory_done,
                    inventory=inventory,
                    actions=tuple(actions),
                )
            )
    else:
        if checkpoint_store is None or enroll_fn is None or backfill_fn is None:
            raise ValueError("apply mode requires checkpoint_store, enroll_fn, and backfill_fn")

        def apply_one(inventory: LegacyBackfillInventoryReport) -> BulkUserResult:
            return _apply_user(
                inventory,
                config=config,
                checkpoint_store=checkpoint_store,
                pause_fn=governed_pause_check,
                enroll_fn=enroll_fn,
                backfill_fn=backfill_fn,
                bucket_process_fn=bucket_process_fn,
                stop_fn=wall_clock_exhausted,
            )

        # Submit only one bounded wave at a time so the CLI never exceeds its
        # configured user concurrency while reusing the process-wide DB pool.
        # The caller thread is the coordinator; each worker performs only this
        # user's synchronous Firestore leaf operations.
        for start_index in range(0, len(planned), config.concurrency_limit):
            batch = planned[start_index : start_index + config.concurrency_limit]
            futures = [db_executor.submit(apply_one, inventory) for inventory in batch]
            for inventory, future in zip(batch, futures):
                try:
                    results.append(future.result())
                except Exception:
                    results.append(
                        BulkUserResult(
                            uid=inventory.uid,
                            state=MigrationState.failed,
                            inventory=inventory,
                            actions=("worker_failed",),
                            error_codes=("checkpoint_or_worker_failed",),
                        )
                    )

    ordered_results = tuple(sorted(results, key=lambda result: requested_uids.index(result.uid)))
    return BulkRunSummary(
        dry_run=config.dry_run,
        requested_user_count=len(requested_uids),
        selected_user_count=len(planned),
        processed_user_count=len(ordered_results),
        read_ready_count=sum(result.state == MigrationState.read_ready for result in ordered_results),
        failed_user_count=sum(result.state == MigrationState.failed for result in ordered_results),
        paused_user_count=sum(result.state == MigrationState.paused for result in ordered_results),
        admitted_candidate_count=sum(result.inventory.admitted_candidate_count for result in ordered_results),
        estimated_tokens=estimated_tokens,
        stopped_reason=stopped_reason,
        users=ordered_results,
    )


__all__ = [
    "BulkMigrationConfig",
    "BulkRunSummary",
    "BulkUserResult",
    "FirestoreCheckpointStore",
    "GLOBAL_PAUSE_PATH",
    "LegacyBackfillInventoryReport",
    "MigrationCheckpoint",
    "MigrationState",
    "PAUSE_ENV",
    "PauseDecision",
    "read_global_pause",
    "run_bulk_migration",
    "validate_checkpoint_transition",
]
