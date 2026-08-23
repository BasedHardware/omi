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
