from __future__ import annotations

import inspect
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from database import document_store
from database.memory_collections import MemoryCollections
from tests.store_fakes import FakeDocumentStore
from utils.memory import canonical_legacy_backfill as backfill
from utils.memory.bulk_legacy_backfill import MigrationCheckpoint, MigrationState
from utils.memory.legacy_backfill import BackfillReport
from utils.memory.legacy_backfill_bulk_support import LegacyBackfillInventoryReport
from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort


class _RecordingStore(FakeDocumentStore):
    """FakeDocumentStore that records the paths written during a run.

    The module now talks to the backend-neutral DocumentStore via the ``_store`` seams
    (``canonical_legacy_backfill._store`` for the enrollment control read and the ``document_store``
    facade for the checkpoint store + global pause), so seeding writes straight to ``_docs`` (not a
    recorded write) and the run's durable writes land in ``writes``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.writes: list[str] = []

    def set(self, path: str, data, *, merge: bool = False) -> None:
        self.writes.append(path)
        super().set(path, data, merge=merge)

    def create(self, path: str, data) -> None:
        self.writes.append(path)
        super().create(path, data)

    def update(self, path: str, data) -> None:
        self.writes.append(path)
        super().update(path, data)


def _install_store(monkeypatch) -> _RecordingStore:
    store = _RecordingStore()
    monkeypatch.setattr(backfill, "_store", lambda: store)
    monkeypatch.setattr(document_store, "_store", lambda: store)
    return store


def _inventory(uid: str, *, candidates: int = 1) -> LegacyBackfillInventoryReport:
    return LegacyBackfillInventoryReport(
        uid=uid,
        source_count=candidates,
        bucket_counts={"manual_required_promotion": candidates},
        admitted_candidate_count=candidates,
        content_character_count=candidates * 10,
        estimated_tokens=candidates * 3,
        admitted_candidate_estimated_tokens=candidates * 3,
    )


def _backfill_report(uid: str, **kwargs) -> BackfillReport:
    return BackfillReport(
        uid=uid,
        dry_run=False,
        source_count=1,
        intended_count=1,
        written_count=1,
        skipped_already_present=0,
        skipped_both_store_duplicate=0,
        skipped_semantic_duplicate=0,
        destination_count=1,
        verified=True,
        completed=True,
    )


def _seed_checkpoint(store: _RecordingStore, uid: str, state: MigrationState) -> None:
    # Seed directly into the backing store (not a recorded write).
    store._docs[MemoryCollections(uid).legacy_canonical_backfill_checkpoint] = MigrationCheckpoint(
        uid=uid,
        state=state,
    ).to_payload()


def _seed_rollout_control(
    store: _RecordingStore, uid: str, *, stage: str = "write", writes_blocked: bool | None = None
) -> None:
    payload = backfill.build_user_control_state(uid=uid, stage=stage, account_generation=1)
    if writes_blocked is not None:
        payload["writes_blocked"] = writes_blocked
    store._docs[MemoryCollections(uid).memory_control_state] = payload


def _allow_canonical_writes(monkeypatch) -> None:
    monkeypatch.setattr(backfill, "canonical_write_decision", lambda *args, **kwargs: SimpleNamespace(enabled=True))


@pytest.fixture(autouse=True)
def _canonical_test_cohort(monkeypatch):
    set_canonical_cohort(monkeypatch, "already-done", "cohort-a", "cohort-b")


def test_config_rejects_unbounded_pages():
    with pytest.raises(ValueError, match="page_size"):
        backfill.CanonicalLegacyBackfillConfig(page_size=backfill.MAX_COHORT_PAGE_SIZE + 1)
    with pytest.raises(ValueError, match="max_rows_per_user"):
        backfill.CanonicalLegacyBackfillConfig(max_rows_per_user=backfill.MAX_ROWS_PER_USER + 1)


def test_config_defaults_to_dry_run():
    """The default config must be fail-safe: no durable writes without opt-in."""
    assert backfill.CanonicalLegacyBackfillConfig().dry_run is True


def test_default_config_does_not_stage_or_write(monkeypatch):
    """An unparameterized page run inventories only and writes no checkpoints."""
    store = _install_store(monkeypatch)
    monkeypatch.setattr(backfill, "list_canonical_cohort_uids", lambda: ["cohort-a"])
    monkeypatch.setattr(backfill, "inventory_legacy_user", lambda uid, **_: _inventory(uid))
    monkeypatch.setattr(backfill, "backfill_user", lambda *a, **k: pytest.fail("dry-run must not stage"))

    page = backfill.run_canonical_legacy_backfill_page()

    assert page.summary.dry_run is True
    assert store.writes == []


def test_enrollment_hook_rejects_non_cohort_uid():
    """A non-cohort uid must never reach terminal read_ready via this seam."""
    with pytest.raises(ValueError, match="non-cohort"):
        backfill._cohort_enrollment_hook("intruder", canonical_uids=frozenset({"cohort-a"}))


def test_helper_does_not_import_terminal_graph_or_cron_owners():
    source = inspect.getsource(backfill)

    assert "canonical_short_term_maintenance_cron" not in source
    assert "canonical_kg_promotion" not in source
    assert "run_enrichment" not in source


def test_page_uses_only_whitelisted_users_and_skips_durable_completions(monkeypatch):
    store = _install_store(monkeypatch)
    _seed_checkpoint(store, "already-done", MigrationState.read_ready)
    _seed_rollout_control(store, "cohort-a")
    _allow_canonical_writes(monkeypatch)
    monkeypatch.setattr(backfill, "list_canonical_cohort_uids", lambda: ["already-done", "cohort-a", "cohort-b"])
    monkeypatch.setattr(backfill, "inventory_legacy_user", lambda uid, **_: _inventory(uid))
    calls: list[str] = []

    def stage(uid: str, **kwargs):
        calls.append(uid)
        return _backfill_report(uid, **kwargs)

    monkeypatch.setattr(backfill, "backfill_user", stage)

    page = backfill.run_canonical_legacy_backfill_page(
        config=backfill.CanonicalLegacyBackfillConfig(page_size=1, dry_run=False),
    )

    assert page.cohort_user_count == 3
    assert page.pending_user_count == 2
    assert page.selected_uids == ("cohort-a",)
    assert calls == ["cohort-a"]
    assert page.summary.read_ready_count == 1
    assert page.remaining_user_count == 1
    assert page.has_more is True
    assert "already-done" not in calls


def test_second_page_call_resumes_and_is_idempotent(monkeypatch):
    store = _install_store(monkeypatch)
    _seed_rollout_control(store, "cohort-a")
    _allow_canonical_writes(monkeypatch)
    monkeypatch.setattr(backfill, "list_canonical_cohort_uids", lambda: ["cohort-a"])
    monkeypatch.setattr(backfill, "inventory_legacy_user", lambda uid, **_: _inventory(uid))
    calls: list[str] = []

    def stage(uid: str, **kwargs):
        calls.append(uid)
        return _backfill_report(uid, **kwargs)

    monkeypatch.setattr(backfill, "backfill_user", stage)
    config = backfill.CanonicalLegacyBackfillConfig(page_size=1, dry_run=False)

    first = backfill.run_canonical_legacy_backfill_page(config=config)
    calls_after_first = list(calls)
    second = backfill.run_canonical_legacy_backfill_page(config=config)

    assert first.summary.read_ready_count == 1
    assert first.remaining_user_count == 0
    assert second.selected_uids == ()
    assert second.summary.processed_user_count == 0
    assert second.remaining_user_count == 0
    assert calls == calls_after_first == ["cohort-a"]
    checkpoint_path = MemoryCollections("cohort-a").legacy_canonical_backfill_checkpoint
    assert store.get(checkpoint_path).to_dict()["state"] == MigrationState.read_ready.value


def test_row_page_is_forwarded_and_only_durable_checkpoints_are_written(monkeypatch):
    store = _install_store(monkeypatch)
    _seed_rollout_control(store, "cohort-a")
    _allow_canonical_writes(monkeypatch)
    monkeypatch.setattr(backfill, "list_canonical_cohort_uids", lambda: ["cohort-a"])
    monkeypatch.setattr(backfill, "inventory_legacy_user", lambda uid, **_: _inventory(uid))
    stage_kwargs: list[dict] = []

    def stage(uid: str, **kwargs):
        stage_kwargs.append(kwargs)
        return _backfill_report(uid, **kwargs)

    monkeypatch.setattr(backfill, "backfill_user", stage)

    page = backfill.run_canonical_legacy_backfill_page(
        config=backfill.CanonicalLegacyBackfillConfig(page_size=1, max_rows_per_user=7, dry_run=False),
    )

    assert page.summary.read_ready_count == 1
    assert len(stage_kwargs) == 1
    assert stage_kwargs[0]["dry_run"] is False
    assert stage_kwargs[0]["batch_size"] == 7
    assert stage_kwargs[0]["resume"] is True
    assert stage_kwargs[0]["max_rows"] == 7
    assert stage_kwargs[0]["continue_on_error"] is True
    assert callable(stage_kwargs[0]["stop_requested"])
    # The neutral store port owns persistence now, so backfill_user is no longer handed a db_client.
    assert "db_client" not in stage_kwargs[0]
    written_paths = set(store.writes)
    assert written_paths == {MemoryCollections("cohort-a").legacy_canonical_backfill_checkpoint}
    assert not any("memory_graph_assertions" in path for path in written_paths)


def test_dry_run_inventories_page_without_durable_writes(monkeypatch):
    store = _install_store(monkeypatch)
    monkeypatch.setattr(backfill, "list_canonical_cohort_uids", lambda: ["cohort-a"])
    monkeypatch.setattr(backfill, "inventory_legacy_user", lambda uid, **_: _inventory(uid))
    stage = lambda *args, **kwargs: pytest.fail("dry-run must not stage canonical candidates")
    monkeypatch.setattr(backfill, "backfill_user", stage)

    page = backfill.run_canonical_legacy_backfill_page(
        config=backfill.CanonicalLegacyBackfillConfig(dry_run=True),
    )

    assert page.summary.dry_run is True
    assert page.summary.users[0].actions == ("would_enroll_write_only", "would_stage_all_for_admission")
    assert store.writes == []


@pytest.mark.parametrize("control_state", ["missing", "off", "write_blocked"])
def test_page_fails_closed_without_write_stage_enrollment_control(monkeypatch, control_state):
    store = _install_store(monkeypatch)
    if control_state == "off":
        _seed_rollout_control(store, "cohort-a", stage="off")
    elif control_state == "write_blocked":
        _seed_rollout_control(store, "cohort-a", writes_blocked=True)
    monkeypatch.setattr(backfill, "list_canonical_cohort_uids", lambda: ["cohort-a"])
    monkeypatch.setattr(backfill, "inventory_legacy_user", lambda uid, **_: _inventory(uid))
    calls: list[str] = []

    def stage(uid: str, **kwargs):
        calls.append(uid)
        return _backfill_report(uid, **kwargs)

    monkeypatch.setattr(backfill, "backfill_user", stage)

    page = backfill.run_canonical_legacy_backfill_page(
        config=backfill.CanonicalLegacyBackfillConfig(page_size=1, dry_run=False),
    )

    assert page.summary.read_ready_count == 0
    assert page.summary.failed_user_count == 1
    assert calls == []
    assert page.remaining_user_count == 1
    checkpoint_path = MemoryCollections("cohort-a").legacy_canonical_backfill_checkpoint
    assert not store.exists(checkpoint_path)
