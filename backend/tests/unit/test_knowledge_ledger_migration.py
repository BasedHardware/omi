from datetime import datetime, timedelta, timezone

import pytest

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory import knowledge_ledger_migration
from utils.memory.knowledge_ledger_migration import LedgerMigrationAction, migration_marker, plan_ledger_migration
from utils.memory.knowledge_ledger_migration import (
    LedgerMigrationCompletion,
    apply_ledger_migration_plan,
    read_ledger_migration_completion,
)
from testing.jit_processing.migration_fixture import run_migration_fixture

NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)


def _item(**updates) -> MemoryItem:
    data = {
        "memory_id": "mem-1",
        "uid": "u1",
        "version": 1,
        "tier": MemoryLayer.long_term,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.processed,
        "content": "Lives in Brooklyn",
        "evidence": [
            MemoryEvidence(
                evidence_id="ev-1",
                source_type="conversation",
                source_id="conv-1",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": False,
        "captured_at": NOW,
        "updated_at": NOW,
        "ledger_commit_id": "commit-1",
        "ledger_sequence": 1,
        "item_revision": 4,
        "predicate": "resides_in",
    }
    data.update(updates)
    if data["tier"] == MemoryLayer.short_term:
        data.update({"expires_at": NOW + timedelta(days=2), "ledger_commit_id": None, "ledger_sequence": None})
    return MemoryItem(**data)


def test_long_term_rows_adapt_in_place_without_claiming_passive_intent():
    first = plan_ledger_migration(_item())
    second = plan_ledger_migration(_item())

    assert first == second
    assert first.action == LedgerMigrationAction.adapt_long_term_history
    assert first.updates["slot"] == "home_city"
    assert first.updates["intent_backed"] is False
    assert first.updates["write_reason"] == "legacy_migration"
    assert migration_marker(first) == "knowledge_ledger.v1:mem-1:r4"


def test_user_asserted_long_term_row_retains_direct_authority():
    plan = plan_ledger_migration(_item(user_asserted=True))

    assert plan.updates["intent_backed"] is True
    assert plan.updates["write_reason"] == "direct_user_statement"


def test_short_term_rows_fail_closed_to_separate_adjudication():
    plan = plan_ledger_migration(_item(tier=MemoryLayer.short_term))

    assert plan.action == LedgerMigrationAction.adjudicate_short_term
    assert plan.requires_human_or_policy_adjudication is True
    assert plan.updates == {}
    assert migration_marker(plan) is None


@pytest.mark.parametrize(
    "valid_to",
    [NOW + timedelta(hours=1), NOW + timedelta(days=1)],
)
def test_long_term_migration_preserves_expiry_or_closure(valid_to):
    plan = plan_ledger_migration(_item(valid_to=valid_to))

    assert plan.action == LedgerMigrationAction.adapt_long_term_history
    assert plan.updates["valid_to"] == valid_to


def test_archive_history_is_never_automatically_reopened():
    plan = plan_ledger_migration(_item(tier=MemoryLayer.archive))

    assert plan.action == LedgerMigrationAction.ignore_inactive
    assert plan.reason == "archive_history_requires_explicit_adjudication"
    assert plan.requires_human_or_policy_adjudication is True
    assert migration_marker(plan) is None


def test_third_party_rows_never_migrate_to_primary_profile_scope():
    plan = plan_ledger_migration(_item(subject_entity_id="person-sarah"))

    assert plan.updates["subject_scope"] == "third_party"
    assert plan.updates["slot"] == "home_city"


class _Snapshot:
    def __init__(self, value=None):
        self.value = value
        self.exists = value is not None

    def to_dict(self):
        return self.value


class _Document:
    def __init__(self):
        self.value = None

    def get(self):
        return _Snapshot(self.value)

    def set(self, value):
        self.value = value


class _DB:
    def __init__(self):
        self.doc = _Document()

    def document(self, _path):
        return self.doc


def test_completion_marker_is_fail_closed_and_round_trips():
    db = _DB()
    assert read_ledger_migration_completion("u1", db_client=db) is None

    written = LedgerMigrationCompletion(
        completed_at=NOW,
        source_head_commit_id="head-7",
        migrated_long_term_count=8,
        adjudicated_short_term_count=2,
        blocking_row_count=0,
    )
    written.validate_complete()
    db.doc.set(written.model_dump(mode="json"))

    assert read_ledger_migration_completion("u1", db_client=db) == written


def test_completion_marker_rejects_unadjudicated_rows():
    completion = LedgerMigrationCompletion(
        completed_at=NOW,
        source_head_commit_id="head-7",
        migrated_long_term_count=8,
        adjudicated_short_term_count=0,
        blocking_row_count=1,
    )
    with pytest.raises(ValueError, match="blocking rows"):
        completion.validate_complete()


def test_completion_reader_rejects_future_schema_and_naive_timestamp():
    db = _DB()
    db.doc.value = {
        "schema_version": "knowledge_ledger.v2",
        "status": "complete",
        "completed_at": NOW,
        "source_head_commit_id": "head-7",
        "migrated_long_term_count": 8,
        "adjudicated_short_term_count": 2,
        "blocking_row_count": 0,
    }
    assert read_ledger_migration_completion("u1", db_client=db) is None

    db.doc.value["schema_version"] = "knowledge_ledger.v1"
    db.doc.value["completed_at"] = datetime(2026, 8, 23)
    assert read_ledger_migration_completion("u1", db_client=db) is None


def test_apply_plan_routes_only_automatic_long_term_adaptation(monkeypatch):
    source = _item()
    plan = plan_ledger_migration(source)
    adapted = _item(
        item_revision=source.item_revision + 1,
        ledger_schema_version="knowledge_ledger.v1",
        kind="fact",
        subject_scope="primary_user",
        slot="home_city",
        valid_from=NOW,
        intent_backed=False,
        write_reason="legacy_migration",
    )
    calls = []

    def adapt(uid, memory_id, *, expected_item_revision, updates, db_client):
        calls.append((uid, memory_id, expected_item_revision, updates, db_client))
        return adapted

    monkeypatch.setattr(knowledge_ledger_migration, "adapt_canonical_memory_to_knowledge_ledger", adapt)

    assert apply_ledger_migration_plan("u1", plan, db_client="fixture-db") == adapted
    assert calls == [("u1", "mem-1", 4, plan.updates, "fixture-db")]

    blocked = plan_ledger_migration(_item(tier=MemoryLayer.short_term))
    with pytest.raises(ValueError, match="requires adjudication"):
        apply_ledger_migration_plan("u1", blocked, db_client="fixture-db")


def test_hermetic_fixture_proves_counts_provenance_profile_and_resume_without_content_report():
    long_term = _item(memory_id="mem-long", user_asserted=True)
    already_ledger = _item(
        memory_id="mem-ledger",
        user_asserted=True,
        ledger_schema_version="knowledge_ledger.v1",
        kind="fact",
        subject_scope="primary_user",
        slot="home_city",
        valid_from=NOW,
        intent_backed=True,
        write_reason="direct_user_statement",
    )
    inactive = _item(memory_id="mem-inactive", status=MemoryItemStatus.superseded, valid_to=NOW)
    short_term = _item(memory_id="mem-short", tier=MemoryLayer.short_term)
    archive = _item(memory_id="mem-archive", tier=MemoryLayer.archive)
    apply_calls = []

    def apply(uid, plan):
        apply_calls.append((uid, plan.memory_id, plan.source_revision))
        source = next(
            item
            for item in (long_term, already_ledger, inactive, short_term, archive)
            if item.memory_id == plan.memory_id
        )
        if plan.action == LedgerMigrationAction.no_op:
            return source
        return source.model_copy(
            update={
                **plan.updates,
                "item_revision": source.item_revision + 1,
                "ledger_schema_version": "knowledge_ledger.v1",
                "kind": "fact",
                "subject_scope": plan.updates["subject_scope"],
                "valid_from": plan.updates["valid_from"],
                "intent_backed": plan.updates["intent_backed"],
                "write_reason": plan.updates["write_reason"],
            }
        )

    first = run_migration_fixture(
        "u1",
        [archive, short_term, inactive, already_ledger, long_term],
        apply_plan=apply,
    )

    assert first.report.total_rows == 5
    assert first.report.action_counts == {
        "no_op": 1,
        "adapt_long_term_history": 1,
        "adjudicate_short_term": 1,
        "ignore_inactive": 2,
    }
    assert first.report.applied_count == 1
    assert first.report.resumed_count == 1
    assert first.report.blocking_row_count == 2
    assert first.report.provenance_complete_count == 2
    assert first.report.profile_slot_count == 2
    assert first.report.profile_character_count > 0
    assert len(first.report.profile_sha256) == 64
    assert first.report.planner_admissible is False
    serialized = first.report.model_dump_json()
    assert "Lives in Brooklyn" not in serialized
    assert "conv-1" not in serialized

    second = run_migration_fixture(
        "u1",
        first.items,
        apply_plan=lambda uid, plan: (_ for _ in ()).throw(AssertionError("resume reapplied a completed row")),
        completed_markers=first.completed_markers,
    )
    assert second.report.resumed_count == 2
    assert second.report.applied_count == 0
    assert second.report.profile_sha256 == first.report.profile_sha256


def test_hermetic_fixture_marks_stale_revision_and_inconsistent_resume_as_blocking():
    source = _item(memory_id="mem-stale", user_asserted=True)
    plan = plan_ledger_migration(source)

    stale = run_migration_fixture(
        "u1",
        [source],
        apply_plan=lambda uid, candidate: (_ for _ in ()).throw(ValueError("stale item revision")),
    )
    assert stale.report.failed_count == 1
    assert stale.report.blocking_row_count == 1
    assert stale.report.planner_admissible is False

    inconsistent_resume = run_migration_fixture(
        "u1",
        [source],
        apply_plan=lambda uid, candidate: source,
        completed_markers=[migration_marker(plan)],
    )
    assert inconsistent_resume.report.resumed_count == 0
    assert inconsistent_resume.report.failed_count == 1
    assert inconsistent_resume.report.blocking_row_count == 1


def test_hermetic_fixture_requires_complete_provenance_before_completion():
    complete = _item(
        memory_id="mem-complete",
        ledger_schema_version="knowledge_ledger.v1",
        kind="fact",
        subject_scope="primary_user",
        slot="home_city",
        valid_from=NOW,
        intent_backed=True,
        write_reason="direct_user_statement",
    )
    complete_run = run_migration_fixture(
        "u1",
        [complete],
        apply_plan=lambda uid, plan: complete,
    )
    assert complete_run.report.planner_admissible is True

    missing_provenance = complete.model_copy(update={"memory_id": "mem-no-evidence", "evidence": []})
    incomplete_run = run_migration_fixture(
        "u1",
        [missing_provenance],
        apply_plan=lambda uid, plan: missing_provenance,
    )
    assert incomplete_run.report.failed_count == 0
    assert incomplete_run.report.blocking_row_count == 0
    assert incomplete_run.report.provenance_complete_count == 0
    assert incomplete_run.report.planner_admissible is False
