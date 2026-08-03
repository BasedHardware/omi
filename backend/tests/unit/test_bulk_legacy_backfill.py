from __future__ import annotations

from dataclasses import dataclass, field
from threading import Barrier, Lock

import pytest

from utils.memory.bulk_legacy_backfill import (
    BulkMigrationConfig,
    MigrationCheckpoint,
    MigrationState,
    PauseDecision,
    read_global_pause,
    run_bulk_migration,
    validate_checkpoint_transition,
)
from utils.memory.legacy_backfill_bulk_support import LegacyBackfillInventoryReport


@dataclass(frozen=True)
class _BackfillReport:
    written_count: int = 1
    skipped_already_present: int = 0
    skipped_both_store_duplicate: int = 0
    destination_count: int = 1
    intended_count: int = 1
    legacy_rows_touched: int = 1
    completed: bool = True
    verified: bool = True
    cohort_gated: bool = False
    errors: list[str] = field(default_factory=list)


class _CheckpointStore:
    def __init__(self):
        self.checkpoints: dict[str, MigrationCheckpoint] = {}
        self.lock = Lock()

    def read(self, uid: str) -> MigrationCheckpoint:
        with self.lock:
            return self.checkpoints.get(uid, MigrationCheckpoint(uid=uid))

    def write(self, checkpoint: MigrationCheckpoint) -> None:
        with self.lock:
            current = self.checkpoints.get(checkpoint.uid, MigrationCheckpoint(uid=checkpoint.uid))
            validate_checkpoint_transition(current.state, checkpoint.state)
            self.checkpoints[checkpoint.uid] = checkpoint


def _inventory(uid: str, *, candidates: int = 2, tokens: int = 20) -> LegacyBackfillInventoryReport:
    return LegacyBackfillInventoryReport(
        uid=uid,
        source_count=candidates + 1,
        bucket_counts={"manual_required_promotion": candidates, "hold_sensitive": 1},
        admitted_candidate_count=candidates,
        content_character_count=tokens * 6,
        estimated_tokens=tokens + 10,
        admitted_candidate_estimated_tokens=tokens,
    )


def test_checkpoint_state_machine_rejects_regressions_and_read_ready_mutation():
    validate_checkpoint_transition(MigrationState.not_started, MigrationState.inventory_done)
    validate_checkpoint_transition(MigrationState.processing, MigrationState.staged)
    validate_checkpoint_transition(MigrationState.staged, MigrationState.processing)
    validate_checkpoint_transition(MigrationState.failed, MigrationState.processing)

    with pytest.raises(ValueError, match="inventory_done -> not_started"):
        validate_checkpoint_transition(MigrationState.inventory_done, MigrationState.not_started)
    with pytest.raises(ValueError, match="read_ready -> processing"):
        validate_checkpoint_transition(MigrationState.read_ready, MigrationState.processing)


def test_malformed_checkpoint_counts_fail_closed_to_zero():
    checkpoint = MigrationCheckpoint.from_payload(
        "uid-a",
        {
            "state": "unexpected",
            "source_count": "not-a-number",
            "bucket_counts": {"hold_sensitive": "bad"},
        },
    )

    assert checkpoint.state == MigrationState.failed
    assert checkpoint.source_count == 0
    assert checkpoint.bucket_counts == {"hold_sensitive": 0}


def test_dry_run_token_governor_stops_before_over_budget_user_without_callbacks():
    callback_calls: list[str] = []
    inventories = {"uid-a": _inventory("uid-a", tokens=60), "uid-b": _inventory("uid-b", tokens=60)}

    def unused_backfill(uid: str, cap: int, resume: bool, stop) -> _BackfillReport:
        callback_calls.append(f"backfill:{uid}")
        return _BackfillReport()

    summary = run_bulk_migration(
        ["uid-a", "uid-b"],
        config=BulkMigrationConfig(max_estimated_tokens_per_run=100),
        inventory_fn=inventories.__getitem__,
        enroll_fn=lambda uid: callback_calls.append(f"enroll:{uid}"),
        backfill_fn=unused_backfill,
    )

    assert summary.dry_run is True
    assert summary.stopped_reason == "max_estimated_tokens_per_run"
    assert summary.selected_user_count == 1
    assert summary.estimated_tokens == 60
    assert [user.state for user in summary.users] == [MigrationState.inventory_done, MigrationState.paused]
    assert callback_calls == []


def test_user_governor_limits_inventory_to_configured_count():
    inventoried: list[str] = []

    def inventory(uid: str) -> LegacyBackfillInventoryReport:
        inventoried.append(uid)
        return _inventory(uid)

    summary = run_bulk_migration(
        ["uid-a", "uid-b", "uid-c"],
        config=BulkMigrationConfig(max_users_per_run=2),
        inventory_fn=inventory,
    )

    assert summary.stopped_reason == "max_users_per_run"
    assert summary.selected_user_count == 2
    assert inventoried == ["uid-a", "uid-b"]


def test_global_pause_env_and_read_failure_both_fail_closed():
    assert read_global_pause(object(), env={"MEMORY_BULK_BACKFILL_PAUSED": "true"}) == PauseDecision(
        True, "paused_by_env"
    )

    class _FailingDb:
        def document(self, path):
            raise RuntimeError("unavailable")

    assert read_global_pause(_FailingDb(), env={}) == PauseDecision(True, "pause_check_failed")


def test_apply_is_idempotent_across_multiple_uids_and_skips_read_ready_reentry():
    store = _CheckpointStore()
    calls: list[str] = []

    def enroll(uid: str) -> None:
        calls.append(f"enroll:{uid}")

    def backfill(uid: str, cap: int, resume: bool, stop) -> _BackfillReport:
        calls.append(f"backfill:{uid}:{cap}:{resume}")
        return _BackfillReport(written_count=2, intended_count=2, legacy_rows_touched=2)

    config = BulkMigrationConfig(
        dry_run=False,
        max_admitted_rows_per_user=5,
        concurrency_limit=2,
    )
    first = run_bulk_migration(
        ["uid-a", "uid-b", "uid-a"],
        config=config,
        inventory_fn=lambda uid: _inventory(uid),
        checkpoint_store=store,
        enroll_fn=enroll,
        backfill_fn=backfill,
    )
    calls_after_first = list(calls)
    second = run_bulk_migration(
        ["uid-a", "uid-b"],
        config=config,
        inventory_fn=lambda uid: _inventory(uid),
        checkpoint_store=store,
        enroll_fn=enroll,
        backfill_fn=backfill,
    )

    assert first.read_ready_count == 2
    assert second.read_ready_count == 2
    assert calls == calls_after_first
    assert all(checkpoint.state == MigrationState.read_ready for checkpoint in store.checkpoints.values())


def test_row_cap_pauses_cleanly_and_resume_reaches_read_ready():
    store = _CheckpointStore()
    reports = iter(
        [
            _BackfillReport(written_count=1, intended_count=1, completed=False, verified=False),
            _BackfillReport(written_count=1, intended_count=1, completed=True, verified=True),
        ]
    )

    def backfill(uid: str, cap: int, resume: bool, stop) -> _BackfillReport:
        assert cap == 1
        return next(reports)

    config = BulkMigrationConfig(dry_run=False, max_admitted_rows_per_user=1)
    first = run_bulk_migration(
        ["uid-a"],
        config=config,
        inventory_fn=lambda uid: _inventory(uid),
        checkpoint_store=store,
        enroll_fn=lambda uid: None,
        backfill_fn=backfill,
    )
    second = run_bulk_migration(
        ["uid-a"],
        config=config,
        inventory_fn=lambda uid: _inventory(uid),
        checkpoint_store=store,
        enroll_fn=lambda uid: None,
        backfill_fn=backfill,
    )

    assert first.stopped_reason is None
    assert first.paused_user_count == 1
    assert first.users[0].error_codes == ("max_admitted_rows_per_user",)
    assert second.read_ready_count == 1
    assert store.checkpoints["uid-a"].state == MigrationState.read_ready


def test_pause_is_checked_between_enrollment_and_staging():
    store = _CheckpointStore()
    decisions = iter([PauseDecision(False), PauseDecision(False), PauseDecision(True, "paused_by_firestore")])
    backfill_calls: list[str] = []

    def unused_backfill(uid: str, cap: int, resume: bool, stop) -> _BackfillReport:
        backfill_calls.append(uid)
        return _BackfillReport()

    summary = run_bulk_migration(
        ["uid-a"],
        config=BulkMigrationConfig(dry_run=False),
        inventory_fn=lambda uid: _inventory(uid),
        pause_fn=lambda: next(decisions),
        checkpoint_store=store,
        enroll_fn=lambda uid: None,
        backfill_fn=unused_backfill,
    )

    assert summary.paused_user_count == 1
    assert summary.users[0].error_codes == ("paused_by_firestore",)
    assert store.checkpoints["uid-a"].state == MigrationState.paused
    assert store.checkpoints["uid-a"].resume_state == MigrationState.enrolled
    assert backfill_calls == []


def test_wall_clock_stop_is_forwarded_to_row_worker_and_checkpoints_pause():
    store = _CheckpointStore()
    clock_values = iter([0.0, 0.0, 0.0, 0.0, 2.0, 2.0])

    def backfill(uid: str, cap: int, resume: bool, stop) -> _BackfillReport:
        assert stop() is True
        return _BackfillReport(written_count=0, intended_count=0, completed=False, verified=False)

    summary = run_bulk_migration(
        ["uid-a"],
        config=BulkMigrationConfig(dry_run=False, wall_clock_seconds=1.0),
        inventory_fn=lambda uid: _inventory(uid),
        checkpoint_store=store,
        enroll_fn=lambda uid: None,
        backfill_fn=backfill,
        monotonic_fn=lambda: next(clock_values),
    )

    assert summary.paused_user_count == 1
    assert summary.users[0].error_codes == ("wall_clock_seconds",)
    assert store.checkpoints["uid-a"].last_error_code == "wall_clock_seconds"


def test_requested_bucket_processing_waits_for_row_budget_then_resumes():
    store = _CheckpointStore()
    stage_reports = iter(
        [
            _BackfillReport(written_count=2, destination_count=2, intended_count=2),
            _BackfillReport(written_count=0, destination_count=2, intended_count=0),
        ]
    )
    bucket_calls: list[str] = []

    def stage(uid: str, cap: int, resume: bool, stop) -> _BackfillReport:
        return next(stage_reports)

    def process_bucket(uid: str, bucket: str, cap: int, stop) -> _BackfillReport:
        bucket_calls.append(f"{uid}:{bucket}:{cap}")
        return _BackfillReport(
            written_count=0,
            destination_count=2,
            intended_count=2,
            legacy_rows_touched=2,
        )

    config = BulkMigrationConfig(
        dry_run=False,
        max_admitted_rows_per_user=2,
        process_buckets=("manual_required_promotion",),
    )
    first = run_bulk_migration(
        ["uid-a"],
        config=config,
        inventory_fn=lambda uid: _inventory(uid),
        checkpoint_store=store,
        enroll_fn=lambda uid: None,
        backfill_fn=stage,
        bucket_process_fn=process_bucket,
    )
    second = run_bulk_migration(
        ["uid-a"],
        config=config,
        inventory_fn=lambda uid: _inventory(uid),
        checkpoint_store=store,
        enroll_fn=lambda uid: None,
        backfill_fn=stage,
        bucket_process_fn=process_bucket,
    )

    assert first.paused_user_count == 1
    assert "bucket_processing_deferred_row_cap" in first.users[0].actions
    assert bucket_calls == ["uid-a:manual_required_promotion:2"]
    assert second.read_ready_count == 1


def test_checkpoint_worker_failure_isolated_from_other_uids():
    class _FailOneStore(_CheckpointStore):
        def write(self, checkpoint: MigrationCheckpoint) -> None:
            if checkpoint.uid == "uid-a":
                raise RuntimeError("checkpoint unavailable")
            super().write(checkpoint)

    store = _FailOneStore()
    summary = run_bulk_migration(
        ["uid-a", "uid-b"],
        config=BulkMigrationConfig(dry_run=False, concurrency_limit=2),
        inventory_fn=lambda uid: _inventory(uid),
        checkpoint_store=store,
        enroll_fn=lambda uid: None,
        backfill_fn=lambda uid, cap, resume, stop: _BackfillReport(),
    )

    assert summary.failed_user_count == 1
    assert summary.read_ready_count == 1
    assert summary.users[0].error_codes == ("checkpoint_or_worker_failed",)
    assert summary.users[1].state == MigrationState.read_ready


def test_apply_user_concurrency_never_exceeds_configured_limit():
    store = _CheckpointStore()
    first_wave = Barrier(2)
    counters = {"active": 0, "maximum": 0}
    counter_lock = Lock()

    def backfill(uid: str, cap: int, resume: bool, stop) -> _BackfillReport:
        with counter_lock:
            counters["active"] += 1
            counters["maximum"] = max(counters["maximum"], counters["active"])
        if uid in {"uid-a", "uid-b"}:
            first_wave.wait(timeout=2)
        with counter_lock:
            counters["active"] -= 1
        return _BackfillReport()

    summary = run_bulk_migration(
        ["uid-a", "uid-b", "uid-c"],
        config=BulkMigrationConfig(dry_run=False, max_users_per_run=3, concurrency_limit=2),
        inventory_fn=lambda uid: _inventory(uid),
        checkpoint_store=store,
        enroll_fn=lambda uid: None,
        backfill_fn=backfill,
    )

    assert summary.read_ready_count == 3
    assert counters["maximum"] == 2
