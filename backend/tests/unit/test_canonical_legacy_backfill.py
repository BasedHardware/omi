from __future__ import annotations

import inspect
from dataclasses import dataclass

import pytest

from database.memory_collections import MemoryCollections
from utils.memory import canonical_legacy_backfill as backfill
from utils.memory.bulk_legacy_backfill import MigrationCheckpoint, MigrationState
from utils.memory.legacy_backfill import BackfillReport
from utils.memory.legacy_backfill_bulk_support import LegacyBackfillInventoryReport


@dataclass
class _Snapshot:
    payload: dict | None

    @property
    def exists(self) -> bool:
        return self.payload is not None

    def to_dict(self):
        return self.payload


class _Document:
    def __init__(self, db: "_Db", path: str):
        self._db = db
        self._path = path

    def get(self):
        self._db.reads.append(self._path)
        return _Snapshot(self._db.documents.get(self._path))

    def set(self, payload, merge: bool = False):
        self._db.writes.append((self._path, payload, merge))
        if merge and self._path in self._db.documents:
            self._db.documents[self._path] = {**self._db.documents[self._path], **payload}
        else:
            self._db.documents[self._path] = dict(payload)


class _Db:
    def __init__(self):
        self.documents: dict[str, dict] = {}
        self.reads: list[str] = []
        self.writes: list[tuple[str, dict, bool]] = []

    def document(self, path: str):
        return _Document(self, path)


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


def _seed_checkpoint(db: _Db, uid: str, state: MigrationState) -> None:
    db.documents[MemoryCollections(uid).legacy_canonical_backfill_checkpoint] = MigrationCheckpoint(
        uid=uid,
        state=state,
    ).to_payload()


def test_config_rejects_unbounded_pages():
    with pytest.raises(ValueError, match="page_size"):
        backfill.CanonicalLegacyBackfillConfig(page_size=backfill.MAX_COHORT_PAGE_SIZE + 1)
    with pytest.raises(ValueError, match="max_rows_per_user"):
        backfill.CanonicalLegacyBackfillConfig(max_rows_per_user=backfill.MAX_ROWS_PER_USER + 1)


def test_helper_does_not_import_terminal_graph_or_cron_owners():
    source = inspect.getsource(backfill)

    assert "canonical_short_term_maintenance_cron" not in source
    assert "canonical_kg_promotion" not in source
    assert "run_enrichment" not in source


def test_page_uses_only_whitelisted_users_and_skips_durable_completions(monkeypatch):
    db = _Db()
    _seed_checkpoint(db, "already-done", MigrationState.read_ready)
    monkeypatch.setattr(backfill, "list_canonical_cohort_uids", lambda: ["already-done", "cohort-a", "cohort-b"])
    monkeypatch.setattr(backfill, "inventory_legacy_user", lambda uid, **_: _inventory(uid))
    calls: list[str] = []

    def stage(uid: str, **kwargs):
        calls.append(uid)
        return _backfill_report(uid, **kwargs)

    monkeypatch.setattr(backfill, "backfill_user", stage)

    page = backfill.run_canonical_legacy_backfill_page(
        config=backfill.CanonicalLegacyBackfillConfig(page_size=1),
        db_client=db,
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
    db = _Db()
    monkeypatch.setattr(backfill, "list_canonical_cohort_uids", lambda: ["cohort-a"])
    monkeypatch.setattr(backfill, "inventory_legacy_user", lambda uid, **_: _inventory(uid))
    calls: list[str] = []

    def stage(uid: str, **kwargs):
        calls.append(uid)
        return _backfill_report(uid, **kwargs)

    monkeypatch.setattr(backfill, "backfill_user", stage)
    config = backfill.CanonicalLegacyBackfillConfig(page_size=1)

    first = backfill.run_canonical_legacy_backfill_page(config=config, db_client=db)
    calls_after_first = list(calls)
    second = backfill.run_canonical_legacy_backfill_page(config=config, db_client=db)

    assert first.summary.read_ready_count == 1
    assert first.remaining_user_count == 0
    assert second.selected_uids == ()
    assert second.summary.processed_user_count == 0
    assert second.remaining_user_count == 0
    assert calls == calls_after_first == ["cohort-a"]
    checkpoint_path = MemoryCollections("cohort-a").legacy_canonical_backfill_checkpoint
    assert db.documents[checkpoint_path]["state"] == MigrationState.read_ready.value


def test_row_page_is_forwarded_and_only_durable_checkpoints_are_written(monkeypatch):
    db = _Db()
    monkeypatch.setattr(backfill, "list_canonical_cohort_uids", lambda: ["cohort-a"])
    monkeypatch.setattr(backfill, "inventory_legacy_user", lambda uid, **_: _inventory(uid))
    stage_kwargs: list[dict] = []

    def stage(uid: str, **kwargs):
        stage_kwargs.append(kwargs)
        return _backfill_report(uid, **kwargs)

    monkeypatch.setattr(backfill, "backfill_user", stage)

    page = backfill.run_canonical_legacy_backfill_page(
        config=backfill.CanonicalLegacyBackfillConfig(page_size=1, max_rows_per_user=7),
        db_client=db,
    )

    assert page.summary.read_ready_count == 1
    assert len(stage_kwargs) == 1
    assert stage_kwargs[0]["dry_run"] is False
    assert stage_kwargs[0]["batch_size"] == 7
    assert stage_kwargs[0]["resume"] is True
    assert stage_kwargs[0]["max_rows"] == 7
    assert stage_kwargs[0]["continue_on_error"] is True
    assert callable(stage_kwargs[0]["stop_requested"])
    assert stage_kwargs[0]["db_client"] is db
    written_paths = {path for path, _, _ in db.writes}
    assert written_paths == {MemoryCollections("cohort-a").legacy_canonical_backfill_checkpoint}
    assert not any("memory_graph_assertions" in path for path in written_paths)


def test_dry_run_inventories_page_without_durable_writes(monkeypatch):
    db = _Db()
    monkeypatch.setattr(backfill, "list_canonical_cohort_uids", lambda: ["cohort-a"])
    monkeypatch.setattr(backfill, "inventory_legacy_user", lambda uid, **_: _inventory(uid))
    stage = lambda *args, **kwargs: pytest.fail("dry-run must not stage canonical candidates")
    monkeypatch.setattr(backfill, "backfill_user", stage)

    page = backfill.run_canonical_legacy_backfill_page(
        config=backfill.CanonicalLegacyBackfillConfig(dry_run=True),
        db_client=db,
    )

    assert page.summary.dry_run is True
    assert page.summary.users[0].actions == ("would_enroll_write_only", "would_stage_all_for_admission")
    assert db.writes == []
