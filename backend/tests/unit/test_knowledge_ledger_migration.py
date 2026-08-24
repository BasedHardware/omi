from datetime import datetime, timedelta, timezone

import pytest

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.knowledge_ledger_policy import LEDGER_SLOT_BY_LEGACY_PREDICATE, canonicalize_ledger_slot
from models.memories import MemoryCategory, MemoryDB
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory import knowledge_ledger_migration
from utils.memory import canonical_memory_adapter
from utils.memory.knowledge_ledger_migration import LedgerMigrationAction, migration_marker, plan_ledger_migration
from utils.memory.knowledge_ledger_migration import (
    LedgerMigrationCompletion,
    LedgerPromptProjectionReceipt,
    apply_ledger_migration_plan,
    publish_ledger_migration_cutover,
    read_ledger_migration_completion,
    read_ledger_prompt_projection_receipt,
    run_ledger_migration_sweep,
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


@pytest.mark.parametrize(("predicate", "expected_slot"), LEDGER_SLOT_BY_LEGACY_PREDICATE.items())
def test_every_migration_producer_slot_is_in_the_released_registry(predicate, expected_slot):
    plan = plan_ledger_migration(_item(predicate=predicate, user_asserted=True))

    assert plan.updates["slot"] == expected_slot
    assert canonicalize_ledger_slot(expected_slot) == expected_slot


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


class _KeyedDB:
    def __init__(self, values):
        self.values = values

    def document(self, path):
        doc = _Document()
        doc.value = self.values.get(path)
        return doc


def _prompt_row(memory_id="prompt-1", **updates):
    payload = {
        "id": memory_id,
        "uid": "u1",
        "content": "Lives in Brooklyn",
        "category": MemoryCategory.manual,
        "tags": [],
        "created_at": NOW,
        "updated_at": NOW,
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": "fact",
        "subject_scope": "primary_user",
        "slot": "home_city",
        "intent_backed": True,
        "write_reason": "direct_user_statement",
    }
    payload.update(updates)
    return MemoryDB(**payload)


def test_prompt_projection_receipt_is_tied_to_current_head_and_generations():
    completion = LedgerMigrationCompletion(
        completed_at=NOW,
        source_head_commit_id="head-7",
        migrated_long_term_count=8,
        adjudicated_short_term_count=2,
    )
    receipt = LedgerPromptProjectionReceipt(
        uid="u1",
        generated_at=NOW,
        source_head_commit_id="head-7",
        account_generation=4,
        source_generation=9,
        scanned_row_count=10,
        rows=[_prompt_row()],
    )
    base = "users/u1"
    values = {
        f"{base}/memory_control/knowledge_ledger_prompt_projection": receipt.model_dump(mode="json"),
        f"{base}/memory_state/apply_control": {
            "uid": "u1",
            "head_commit_id": "head-7",
            "account_generation": 4,
            "source_generation": 9,
            "commit_sequence": 12,
        },
    }
    db = _KeyedDB(values)
    assert read_ledger_prompt_projection_receipt("u1", db_client=db, completion=completion) == receipt

    values[f"{base}/memory_state/apply_control"]["head_commit_id"] = "head-8"
    assert read_ledger_prompt_projection_receipt("u1", db_client=db, completion=completion) is None
    values[f"{base}/memory_state/apply_control"]["head_commit_id"] = "head-7"
    values[f"{base}/memory_state/apply_control"]["account_generation"] = 5
    assert read_ledger_prompt_projection_receipt("u1", db_client=db, completion=completion) is None


def test_prompt_projection_receipt_rejects_control_head_change_during_read():
    completion = LedgerMigrationCompletion(
        completed_at=NOW,
        source_head_commit_id="head-7",
        migrated_long_term_count=0,
        adjudicated_short_term_count=0,
    )
    receipt = LedgerPromptProjectionReceipt(
        uid="u1",
        generated_at=NOW,
        source_head_commit_id="head-7",
        account_generation=1,
        source_generation=1,
        scanned_row_count=0,
        rows=[],
    )
    control_reads = iter(
        [
            {"uid": "u1", "head_commit_id": "head-7", "account_generation": 1, "source_generation": 1},
            {"uid": "u1", "head_commit_id": "head-8", "account_generation": 1, "source_generation": 1},
        ]
    )

    class SequencedDocument:
        def __init__(self, is_control):
            self.is_control = is_control

        def get(self):
            return _Snapshot(next(control_reads) if self.is_control else receipt.model_dump(mode="json"))

    class SequencedDB:
        def document(self, path):
            return SequencedDocument(path.endswith("/memory_state/apply_control"))

    assert read_ledger_prompt_projection_receipt("u1", db_client=SequencedDB(), completion=completion) is None


def test_prompt_projection_receipt_rejects_playbook_bodies_and_duplicate_rows():
    completion = LedgerMigrationCompletion(
        completed_at=NOW,
        source_head_commit_id="head-7",
        migrated_long_term_count=0,
        adjudicated_short_term_count=0,
    )
    control = knowledge_ledger_migration.MemoryControlState(
        uid="u1",
        head_commit_id="head-7",
        account_generation=1,
        source_generation=1,
    )
    body_row = _prompt_row(
        kind="document",
        slot=None,
        body="secret full playbook",
        write_reason="recurring_workflow",
    )
    receipt = LedgerPromptProjectionReceipt(
        uid="u1",
        generated_at=NOW,
        source_head_commit_id="head-7",
        account_generation=1,
        source_generation=1,
        scanned_row_count=1,
        rows=[body_row],
    )
    with pytest.raises(ValueError, match="handles"):
        receipt.validate_authoritative(uid="u1", completion=completion, control=control)

    duplicate = receipt.model_copy(update={"rows": [_prompt_row(), _prompt_row()]})
    with pytest.raises(ValueError, match="duplicate"):
        duplicate.validate_authoritative(uid="u1", completion=completion, control=control)

    with pytest.raises(ValueError, match="64"):
        LedgerPromptProjectionReceipt(
            uid="u1",
            generated_at=NOW,
            source_head_commit_id="head-7",
            account_generation=1,
            source_generation=1,
            scanned_row_count=65,
            rows=[_prompt_row(f"row-{index}") for index in range(65)],
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"memory_tier": "archive"},
        {"is_dismissed": True},
        {"superseded_by": "replacement"},
    ],
)
def test_prompt_projection_receipt_rejects_every_non_current_lifecycle_shape(updates):
    completion = LedgerMigrationCompletion(
        completed_at=NOW,
        source_head_commit_id="head-7",
        migrated_long_term_count=0,
        adjudicated_short_term_count=0,
    )
    control = knowledge_ledger_migration.MemoryControlState(
        uid="u1",
        head_commit_id="head-7",
        account_generation=1,
        source_generation=1,
    )
    receipt = LedgerPromptProjectionReceipt(
        uid="u1",
        generated_at=NOW,
        source_head_commit_id="head-7",
        account_generation=1,
        source_generation=1,
        scanned_row_count=1,
        rows=[_prompt_row(**updates)],
    )

    with pytest.raises(ValueError, match="non-current"):
        receipt.validate_authoritative(uid="u1", completion=completion, control=control)


class _PublishingSnapshot(_Snapshot):
    pass


class _PublishingDocument:
    def __init__(self, store, path):
        self.store = store
        self.path = path

    def get(self, transaction=None):
        values = transaction.pending if transaction is not None else self.store.values
        return _PublishingSnapshot(values.get(self.path))


class _PublishingTransaction:
    def __init__(self, store):
        self.store = store
        self.pending = dict(store.values)
        self.set_count = 0

    def set(self, reference, value):
        self.set_count += 1
        if self.store.fail_on_set == self.set_count:
            raise RuntimeError("simulated publication crash")
        self.pending[reference.path] = value


class _PublishingDB:
    def __init__(self, control):
        self.control_path = "users/u1/memory_state/apply_control"
        self.values = {self.control_path: control}
        self.fail_on_set = None
        self.transaction_count = 0
        self.events = []

    def document(self, path):
        return _PublishingDocument(self, path)

    def transaction(self):
        self.transaction_count += 1
        self.events.append("transaction")
        return _PublishingTransaction(self)


def _install_publisher_fakes(monkeypatch, db, rows):
    import database.memory_apply_store as apply_store
    import utils.memory.memory_service as memory_service

    def transactional(function):
        def wrapper(transaction, *args, **kwargs):
            result = function(transaction, *args, **kwargs)
            transaction.store.values = transaction.pending
            return result

        return wrapper

    class Service:
        def __init__(self, *, db_client):
            assert db_client is db

        def iter_export_memories(self, uid, *, include_archive):
            assert uid == "u1" and include_archive is True
            db.events.append("scan-start")
            yield from rows
            db.events.append("scan-complete")

    monkeypatch.setattr(apply_store, "transactional", transactional)
    monkeypatch.setattr(memory_service, "MemoryService", Service)


def _publisher_control(head="head-7", account_generation=1, source_generation=1):
    return {
        "uid": "u1",
        "head_commit_id": head,
        "account_generation": account_generation,
        "source_generation": source_generation,
        "commit_sequence": 7,
    }


def test_cutover_publisher_atomically_publishes_authoritative_empty_snapshot(monkeypatch):
    db = _PublishingDB(_publisher_control())
    _install_publisher_fakes(monkeypatch, db, [])

    receipt = publish_ledger_migration_cutover(
        "u1",
        db_client=db,
        publication_authorizer=lambda: True,
        migrated_long_term_count=0,
        adjudicated_short_term_count=0,
        completed_at=NOW,
    )

    assert receipt.rows == []
    assert receipt.scanned_row_count == 0
    assert "users/u1/memory_control/knowledge_ledger_migration" in db.values
    assert "users/u1/memory_control/knowledge_ledger_prompt_projection" in db.values


def test_cutover_publisher_requires_authority_and_denial_after_empty_scan_writes_nothing(monkeypatch):
    db = _PublishingDB(_publisher_control())
    _install_publisher_fakes(monkeypatch, db, [])

    with pytest.raises(TypeError):
        publish_ledger_migration_cutover(  # type: ignore[call-arg]
            "u1",
            db_client=db,
            migrated_long_term_count=0,
            adjudicated_short_term_count=0,
            completed_at=NOW,
        )
    assert db.events == []
    assert db.transaction_count == 0

    def deny():
        db.events.append("refresh")
        return False

    with pytest.raises(knowledge_ledger_migration.LedgerMigrationPublicationError, match="denied"):
        publish_ledger_migration_cutover(
            "u1",
            db_client=db,
            publication_authorizer=deny,
            migrated_long_term_count=0,
            adjudicated_short_term_count=0,
            completed_at=NOW,
        )

    assert db.events == ["scan-start", "scan-complete", "refresh"]
    assert db.transaction_count == 0
    assert not any("knowledge_ledger_" in path for path in db.values)


@pytest.mark.parametrize("authorization_error", [TimeoutError("timed out"), RuntimeError("resolver failed")])
def test_cutover_publisher_authorization_error_or_timeout_fails_closed(monkeypatch, authorization_error):
    db = _PublishingDB(_publisher_control())
    _install_publisher_fakes(monkeypatch, db, [])

    def fail_authorization():
        db.events.append("refresh")
        raise authorization_error

    with pytest.raises(knowledge_ledger_migration.LedgerMigrationPublicationError, match="authorization failed"):
        publish_ledger_migration_cutover(
            "u1",
            db_client=db,
            publication_authorizer=fail_authorization,
            migrated_long_term_count=0,
            adjudicated_short_term_count=0,
            completed_at=NOW,
        )

    assert db.events == ["scan-start", "scan-complete", "refresh"]
    assert db.transaction_count == 0
    assert not any("knowledge_ledger_" in path for path in db.values)


def test_cutover_publisher_refreshes_after_scan_immediately_before_transaction(monkeypatch):
    db = _PublishingDB(_publisher_control())
    _install_publisher_fakes(monkeypatch, db, [_prompt_row()])

    def authorize():
        db.events.append("refresh")
        return True

    publish_ledger_migration_cutover(
        "u1",
        db_client=db,
        publication_authorizer=authorize,
        migrated_long_term_count=0,
        adjudicated_short_term_count=0,
        completed_at=NOW,
    )

    assert db.events == ["scan-start", "scan-complete", "refresh", "transaction"]


def test_kill_flip_during_publication_scan_never_opens_transaction(monkeypatch):
    db = _PublishingDB(_publisher_control())
    authority = {"enabled": True}

    class Rows(list):
        def __iter__(self):
            yield _prompt_row()
            authority["enabled"] = False

    _install_publisher_fakes(monkeypatch, db, Rows())

    with pytest.raises(knowledge_ledger_migration.LedgerMigrationPublicationError, match="denied"):
        publish_ledger_migration_cutover(
            "u1",
            db_client=db,
            publication_authorizer=lambda: authority["enabled"],
            migrated_long_term_count=0,
            adjudicated_short_term_count=0,
            completed_at=NOW,
        )

    assert db.transaction_count == 0
    assert not any("knowledge_ledger_" in path for path in db.values)


def test_cutover_filters_historical_slot_winner_before_arbitrating_valid_runner_up(monkeypatch):
    valid = _prompt_row(
        "valid-runner-up",
        content="Lives in Brooklyn",
        created_at=NOW,
        updated_at=NOW,
        write_reason="direct_user_statement",
    )
    superseded = _prompt_row(
        "superseded-would-win",
        content="Lives in Boston",
        created_at=NOW + timedelta(days=1),
        updated_at=NOW + timedelta(days=1),
        write_reason="explicit_remember",
        superseded_by=valid.id,
    )
    archived_handle = _prompt_row(
        "archived-playbook",
        kind="document",
        slot=None,
        write_reason="recurring_workflow",
        memory_tier="archive",
    )
    dismissed_trigger = _prompt_row(
        "dismissed-trigger",
        kind="trigger",
        slot=None,
        write_reason="standing_trigger",
        is_dismissed=True,
    )
    db = _PublishingDB(_publisher_control())
    _install_publisher_fakes(monkeypatch, db, [valid, superseded, archived_handle, dismissed_trigger])

    receipt = publish_ledger_migration_cutover(
        "u1",
        db_client=db,
        publication_authorizer=lambda: True,
        migrated_long_term_count=0,
        adjudicated_short_term_count=0,
        completed_at=NOW,
    )

    assert [row.id for row in receipt.rows] == ["valid-runner-up"]


def test_cutover_preserves_inactive_legacy_history_outside_default_prompt(monkeypatch):
    archived = _prompt_row(
        "legacy-archive",
        ledger_schema_version=None,
        kind=None,
        subject_scope=None,
        slot=None,
        intent_backed=False,
        write_reason=None,
        memory_tier="archive",
    )
    closed = _prompt_row(
        "legacy-closed",
        ledger_schema_version=None,
        kind=None,
        subject_scope=None,
        slot=None,
        intent_backed=False,
        write_reason=None,
        invalid_at=NOW,
        superseded_by="replacement",
        user_review=False,
    )
    source_rows = [archived, closed]
    db = _PublishingDB(_publisher_control())
    _install_publisher_fakes(monkeypatch, db, source_rows)

    receipt = publish_ledger_migration_cutover(
        "u1",
        db_client=db,
        publication_authorizer=lambda: True,
        migrated_long_term_count=0,
        adjudicated_short_term_count=0,
        completed_at=NOW,
    )

    assert receipt.rows == []
    assert receipt.preserved_historical_legacy_count == 2
    assert source_rows == [archived, closed], "cutover must not rewrite or delete retained generated history"


@pytest.mark.parametrize(
    "rows",
    [
        [_prompt_row("legacy", ledger_schema_version=None)],
        [_prompt_row("foreign", uid="u2")],
        [
            _prompt_row(
                f"trigger-{index}",
                kind="trigger",
                slot=None,
                write_reason="standing_trigger",
            )
            for index in range(65)
        ],
    ],
)
def test_cutover_publisher_fails_closed_without_any_receipt_for_invalid_or_overbound_scan(monkeypatch, rows):
    db = _PublishingDB(_publisher_control())
    _install_publisher_fakes(monkeypatch, db, rows)

    with pytest.raises(knowledge_ledger_migration.LedgerMigrationPublicationError):
        publish_ledger_migration_cutover(
            "u1",
            db_client=db,
            publication_authorizer=lambda: True,
            migrated_long_term_count=0,
            adjudicated_short_term_count=0,
            completed_at=NOW,
        )

    assert not any("knowledge_ledger_" in path for path in db.values)


def test_cutover_publisher_rechecks_head_and_rolls_back_partial_transaction(monkeypatch):
    db = _PublishingDB(_publisher_control())

    class MutatingRows(list):
        def __iter__(self):
            yield _prompt_row()
            db.values[db.control_path] = _publisher_control(head="head-8")

    _install_publisher_fakes(monkeypatch, db, MutatingRows())

    def authorize_after_changed_scan():
        db.events.append("refresh")
        return True

    with pytest.raises(knowledge_ledger_migration.LedgerMigrationPublicationError, match="changed"):
        publish_ledger_migration_cutover(
            "u1",
            db_client=db,
            publication_authorizer=authorize_after_changed_scan,
            migrated_long_term_count=1,
            adjudicated_short_term_count=0,
            completed_at=NOW,
        )
    assert db.events == ["scan-start", "scan-complete", "refresh", "transaction"]
    assert not any("knowledge_ledger_" in path for path in db.values)

    db.values[db.control_path] = _publisher_control()
    db.fail_on_set = 2
    db.events.clear()
    _install_publisher_fakes(monkeypatch, db, [_prompt_row()])
    with pytest.raises(RuntimeError, match="publication crash"):
        publish_ledger_migration_cutover(
            "u1",
            db_client=db,
            publication_authorizer=lambda: True,
            migrated_long_term_count=1,
            adjudicated_short_term_count=0,
            completed_at=NOW,
        )
    assert not any("knowledge_ledger_" in path for path in db.values)


def test_cutover_publisher_can_republish_after_canonical_write_invalidation(monkeypatch):
    db = _PublishingDB(_publisher_control())
    _install_publisher_fakes(monkeypatch, db, [_prompt_row("first")])
    first = publish_ledger_migration_cutover(
        "u1",
        db_client=db,
        publication_authorizer=lambda: True,
        migrated_long_term_count=1,
        adjudicated_short_term_count=0,
        completed_at=NOW,
    )
    completion = read_ledger_migration_completion("u1", db_client=db)
    assert completion is not None
    assert read_ledger_prompt_projection_receipt("u1", db_client=db, completion=completion) == first

    db.values[db.control_path] = _publisher_control(head="head-8")
    assert read_ledger_prompt_projection_receipt("u1", db_client=db, completion=completion) is None

    _install_publisher_fakes(monkeypatch, db, [_prompt_row("second")])
    second = publish_ledger_migration_cutover(
        "u1",
        db_client=db,
        publication_authorizer=lambda: True,
        migrated_long_term_count=2,
        adjudicated_short_term_count=0,
        completed_at=NOW,
    )
    new_completion = read_ledger_migration_completion("u1", db_client=db)
    assert new_completion is not None
    assert second.source_head_commit_id == "head-8"
    assert [row.id for row in second.rows] == ["second"]
    assert read_ledger_prompt_projection_receipt("u1", db_client=db, completion=new_completion) == second


def test_production_sweep_resumes_adapts_live_rows_and_preserves_history(monkeypatch):
    import database.memory_apply_store as apply_store
    import utils.memory.memory_service as memory_service

    live_legacy = _prompt_row(
        "mem-1",
        ledger_schema_version=None,
        kind=None,
        subject_scope=None,
        slot=None,
        intent_backed=False,
        write_reason=None,
    )
    archived_legacy = _prompt_row(
        "old-generated",
        ledger_schema_version=None,
        kind=None,
        subject_scope=None,
        slot=None,
        intent_backed=False,
        write_reason=None,
        memory_tier="archive",
    )
    canonical = _prompt_row("mem-1")
    scan_count = 0

    class Service:
        def __init__(self, *, db_client):
            pass

        def iter_export_memories(self, uid, *, include_archive):
            nonlocal scan_count
            scan_count += 1
            yield from ([live_legacy, archived_legacy] if scan_count == 1 else [canonical, archived_legacy])

    def transactional(function):
        def wrapper(transaction, *args, **kwargs):
            result = function(transaction, *args, **kwargs)
            transaction.store.values = transaction.pending
            return result

        return wrapper

    applied = []
    monkeypatch.setattr(memory_service, "MemoryService", Service)
    monkeypatch.setattr(apply_store, "transactional", transactional)
    monkeypatch.setattr(knowledge_ledger_migration, "read_canonical_memory_item", lambda *_args, **_kwargs: _item())
    monkeypatch.setattr(
        knowledge_ledger_migration,
        "apply_ledger_migration_plan",
        lambda uid, plan, *, db_client: applied.append((uid, plan.memory_id)),
    )
    db = _PublishingDB(_publisher_control())

    result = run_ledger_migration_sweep(
        "u1",
        db_client=db,
        mutation_authorizer=lambda _memory_id: True,
        publication_authorizer=lambda: True,
        publish=True,
        completed_at=NOW,
    )

    assert applied == [("u1", "mem-1")]
    assert result.migrated_long_term_count == 1
    assert result.preserved_historical_legacy_count == 1
    assert result.receipt.preserved_historical_legacy_count == 1
    assert archived_legacy.memory_tier.value == "archive"


def test_production_sweep_closes_short_term_as_legacy_generated_history(monkeypatch):
    import database.memory_apply_store as apply_store
    import utils.memory.memory_service as memory_service

    live_short = _prompt_row(
        "mem-1",
        ledger_schema_version=None,
        kind=None,
        subject_scope=None,
        slot=None,
        intent_backed=False,
        write_reason=None,
        memory_tier="short_term",
    )
    scans = iter([[live_short], []])

    class Service:
        def __init__(self, *, db_client):
            pass

        def iter_export_memories(self, uid, *, include_archive):
            yield from next(scans)

    def transactional(function):
        def wrapper(transaction, *args, **kwargs):
            result = function(transaction, *args, **kwargs)
            transaction.store.values = transaction.pending
            return result

        return wrapper

    short_item = _item(tier=MemoryLayer.short_term)
    closed = []
    monkeypatch.setattr(memory_service, "MemoryService", Service)
    monkeypatch.setattr(apply_store, "transactional", transactional)
    monkeypatch.setattr(knowledge_ledger_migration, "read_canonical_memory_item", lambda *_args, **_kwargs: short_item)
    monkeypatch.setattr(
        knowledge_ledger_migration,
        "close_canonical_legacy_generated_history",
        lambda uid, memory_id, **kwargs: closed.append((uid, memory_id, kwargs["expected_item_revision"])),
    )
    db = _PublishingDB(_publisher_control())

    result = run_ledger_migration_sweep(
        "u1",
        db_client=db,
        mutation_authorizer=lambda _memory_id: True,
        publication_authorizer=lambda: True,
        publish=True,
        completed_at=NOW,
    )

    assert closed == [("u1", "mem-1", short_item.item_revision)]
    assert result.adjudicated_short_term_count == 1
    assert result.receipt is not None


def test_short_term_adjudication_uses_canonical_close_and_marks_retained_history(monkeypatch):
    item = _item(tier=MemoryLayer.short_term, arguments={"origin": "legacy"})
    captured = {}

    monkeypatch.setattr(
        canonical_memory_adapter,
        "_read_canonical_memory_item_for_lineage",
        lambda *_args, **_kwargs: item,
    )

    def apply(uid, memory_id, *, build_patch, **_kwargs):
        logical, updates = build_patch(item, NOW)
        captured.update({"logical": logical, "updates": updates})
        closed = item.model_copy(
            update={
                "status": MemoryItemStatus.superseded,
                "valid_to": updates["valid_to"],
                "arguments": updates["arguments"],
                "ledger_schema_version": updates["ledger_schema_version"],
                "kind": updates["kind"],
                "subject_scope": updates["subject_scope"],
                "intent_backed": updates["intent_backed"],
                "write_reason": updates["write_reason"],
            }
        )
        return item, closed

    monkeypatch.setattr(canonical_memory_adapter, "_apply_canonical_user_mutation", apply)

    closed = canonical_memory_adapter.close_canonical_legacy_generated_history(
        "u1",
        item.memory_id,
        expected_item_revision=item.item_revision,
        expected_tier=item.tier,
        valid_to=NOW,
        db_client=object(),
    )

    assert captured["logical"]["result_status"] == "superseded"
    assert captured["updates"]["arguments"] == {
        "origin": "legacy",
        "history_class": "legacy_generated",
    }
    assert captured["updates"]["ledger_schema_version"] == "knowledge_ledger.v1"
    assert captured["updates"]["kind"] == "fact"
    assert captured["updates"]["subject_scope"] == "primary_user"
    assert captured["updates"]["intent_backed"] is False
    assert captured["updates"]["write_reason"] == "legacy_migration"
    assert closed.status == MemoryItemStatus.superseded
    assert closed.valid_to == NOW
    assert closed.arguments["history_class"] == "legacy_generated"
    assert closed.write_reason == "legacy_migration"


def test_migration_mutation_budget_bounds_one_authorized_run(monkeypatch):
    import utils.memory.memory_service as memory_service

    rows = [
        _prompt_row(
            f"mem-{index}",
            ledger_schema_version=None,
            kind=None,
            subject_scope=None,
            slot=None,
            intent_backed=False,
            write_reason=None,
        )
        for index in range(101)
    ]

    class Service:
        def __init__(self, *, db_client):
            pass

        def iter_export_memories(self, uid, *, include_archive):
            yield from rows

    applied = []
    monkeypatch.setattr(memory_service, "MemoryService", Service)
    monkeypatch.setattr(knowledge_ledger_migration, "read_canonical_memory_item", lambda *_args, **_kwargs: _item())
    monkeypatch.setattr(
        knowledge_ledger_migration,
        "apply_ledger_migration_plan",
        lambda uid, plan, *, db_client: applied.append(plan.memory_id),
    )

    result = run_ledger_migration_sweep(
        "u1",
        db_client=object(),
        mutation_authorizer=lambda _memory_id: True,
        publication_authorizer=lambda: True,
        publish=False,
    )
    assert len(applied) == knowledge_ledger_migration.MAX_LEDGER_MIGRATION_MUTATIONS_PER_RUN
    assert result.remaining_live_legacy_count == 1
    assert result.receipt is None


def test_mid_batch_authority_flip_stops_before_every_later_row_write(monkeypatch):
    import utils.memory.memory_service as memory_service

    rows = [
        _prompt_row(
            f"mem-{index}",
            ledger_schema_version=None,
            kind=None,
            subject_scope=None,
            slot=None,
            intent_backed=False,
            write_reason=None,
        )
        for index in range(3)
    ]

    class Service:
        def __init__(self, *, db_client):
            pass

        def iter_export_memories(self, uid, *, include_archive):
            yield from rows

    applied = []
    publication_authorizations = []
    decisions = iter([True, False])
    monkeypatch.setattr(memory_service, "MemoryService", Service)
    monkeypatch.setattr(
        knowledge_ledger_migration,
        "read_canonical_memory_item",
        lambda _uid, memory_id, **_kwargs: _item(memory_id=memory_id),
    )
    monkeypatch.setattr(
        knowledge_ledger_migration,
        "apply_ledger_migration_plan",
        lambda uid, plan, *, db_client: applied.append(plan.memory_id),
    )

    with pytest.raises(
        knowledge_ledger_migration.LedgerMigrationPublicationError,
        match="2 live rows remaining",
    ):
        run_ledger_migration_sweep(
            "u1",
            db_client=object(),
            publish=True,
            mutation_authorizer=lambda _memory_id: next(decisions),
            publication_authorizer=lambda: publication_authorizations.append(True) or True,
        )

    assert applied == ["mem-0"]
    assert publication_authorizations == []


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
    # Both migrated rows claim home_city. The released slot-governance
    # contract renders one authority/recency winner per canonical slot.
    assert first.report.profile_slot_count == 1
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
