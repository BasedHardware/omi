"""Behavioral tests for the authoritative L2 route/apply boundary."""

from __future__ import annotations

import hashlib
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (
    CONSOLIDATION_APPLY_STUB_MODULE_NAMES,
    ensure_utils_memory_packages_importable,
    install_consolidation_apply_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)

canonical_consolidation = None
observation_intake = None
ConsolidationAgentDecision = None
apply_consolidation_decision = None


@pytest.fixture(scope="module", autouse=True)
def _consolidation_apply_import_isolation():
    saved = snapshot_sys_modules(CONSOLIDATION_APPLY_STUB_MODULE_NAMES)
    touched = install_consolidation_apply_stubs()
    saved.update(snapshot_sys_modules(touched))
    ensure_utils_memory_packages_importable()

    for stale_module in ("database.memory_apply_store", "utils.memory.canonical_consolidation"):
        sys.modules.pop(stale_module, None)

    module = importlib.import_module("utils.memory.canonical_consolidation")
    globals()["canonical_consolidation"] = module
    globals()['observation_intake'] = module
    globals()["ConsolidationAgentDecision"] = module.ConsolidationAgentDecision
    globals()["apply_consolidation_decision"] = module.apply_consolidation_decision
    yield
    restore_sys_modules(saved)


from models.memory_apply import MemoryControlState, memory_content_hash
from models.memory_admission import (
    REQUIRED_PROCESSING_RECEIPT_VERSION,
    REQUIRED_PROCESSOR_ID,
    REQUIRED_PROCESSOR_VERSION,
    valid_required_processing_receipt,
)
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_operations import MemoryOperation, MemoryOperationStatus, MemoryOperationType
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.canonical_lineage import canonical_lineage_root
from utils.memory.memory_system import MemorySystem

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
UID = "uid-canonical"


class _FakeSnapshot:
    def __init__(self, data, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _FakeDocumentRef:
    def __init__(self, path, db):
        self.path = path
        self._db = db

    def get(self, transaction=None):
        if self.path not in self._db.docs:
            return _FakeSnapshot(None, exists=False)
        return _FakeSnapshot(self._db.docs[self.path], exists=True)

    def set(self, data, merge=False):
        if merge and self.path in self._db.docs:
            merged = dict(self._db.docs[self.path])
            merged.update(data)
            self._db.docs[self.path] = merged
        else:
            self._db.docs[self.path] = data


class _FakeTransaction:
    def __init__(self, db):
        self._db = db
        self.sets = []
        self.deletes = []
        self.fail_after_sets: Optional[int] = None
        self._id = None
        self._read_only = False
        self._max_attempts = 5

    def set(self, ref, data):
        self.sets.append((ref.path, data))
        if self.fail_after_sets is not None and len(self.sets) > self.fail_after_sets:
            raise RuntimeError("injected transaction set failure")

    def delete(self, ref):
        self.deletes.append(ref.path)

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or "txn-1"
        self.sets = []
        self.deletes = []

    def _commit(self):
        for path, data in self.sets:
            self._db.docs[path] = data
        for path in self.deletes:
            self._db.docs.pop(path, None)

    def _rollback(self):
        self._id = None
        self.sets = []
        self.deletes = []


class _FakeDb:
    def __init__(self, docs):
        self.docs = docs
        self.transaction_obj = _FakeTransaction(self)

    def transaction(self):
        return self.transaction_obj

    def document(self, path):
        return _FakeDocumentRef(path, self)


def _evidence(evidence_id: str, *, source_id: str = "conv-1") -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id=evidence_id,
        source_id=source_id,
        source_type="conversation",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _item(
    memory_id: str,
    content: str,
    *,
    tier: MemoryTier = MemoryTier.short_term,
    evidence_ids: Optional[list[str]] = None,
) -> MemoryItem:
    evidence = [_evidence(evidence_id) for evidence_id in (evidence_ids or [f"ev_{memory_id}"])]
    return MemoryItem(
        memory_id=memory_id,
        uid=UID,
        version=2,
        tier=tier,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=evidence,
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=NOW - timedelta(hours=2),
        updated_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=30) if tier == MemoryTier.short_term else None,
        ledger_commit_id="commit-1",
        ledger_sequence=1,
        item_revision=2,
        source_commit_id="commit-1",
        source_commit_sequence=1,
        content_hash=memory_content_hash(
            content=content,
            evidence_ids=[item.evidence_id for item in evidence],
        ),
        account_generation=1,
    )


def _stored(model) -> dict:
    return model.model_dump(mode="json")


def _db_for_items(source: MemoryItem, *other_items: MemoryItem) -> _FakeDb:
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    docs = {
        f"users/{UID}/memory_state/apply_control": _stored(control),
    }
    for item in (source, *other_items):
        docs[f"users/{UID}/memory_items/{item.memory_id}"] = _stored(item)
        for evidence in item.evidence:
            docs[f"users/{UID}/memory_evidence/{evidence.evidence_id}"] = _stored(evidence)
    return _FakeDb(docs)


def _promote_decision(
    source: MemoryItem,
    *,
    supersedes: Optional[list[str]] = None,
    target_memory_id: Optional[str] = None,
):
    return ConsolidationAgentDecision(
        source_memory_id=source.memory_id,
        route="promote",
        reconciliation="replace" if supersedes else "create",
        target_memory_id=target_memory_id,
        supersedes=supersedes or [],
        memory_text="The user enjoys hiking in Seattle.",
        evidence_ids=[evidence.evidence_id for evidence in source.evidence],
        subject_entity_id="user",
        predicate="enjoys_activity",
        arguments={"activity": "hiking", "location": "Seattle"},
        relationship_to_user="self",
        aboutness="primary_user",
        basis_for_memory="explicit",
        confidence="high",
        rationale="Explicit first-person preference.",
    )


def _apply(source: MemoryItem, decision, db: _FakeDb, *, quarantine: bool = False):
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_state/apply_control"])
    return apply_consolidation_decision(
        UID,
        decision=decision,
        pending_by_id={source.memory_id: source},
        control=control,
        run_id="run-route",
        now=NOW,
        db_client=db,
        quarantine=quarantine,
    )


def test_promote_route_atomically_commits_long_term_item_and_graph_assertion():
    source = _item("mem_source", "I enjoy hiking in Seattle.")
    db = _db_for_items(source)

    applied_ids = _apply(source, _promote_decision(source), db)

    stored = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    assertion = db.docs[f"users/{UID}/memory_graph_assertions/{source.memory_id}"]
    operations = [
        MemoryOperation(**payload)
        for path, payload in db.docs.items()
        if path.startswith(f"users/{UID}/memory_operations/")
    ]
    assert applied_ids == [source.memory_id]
    assert stored.tier == MemoryTier.long_term
    assert stored.graph_ready is True
    assert stored.graph_assertion_id == assertion["assertion_id"]
    assert assertion["item_revision"] == stored.item_revision
    assert assertion["content_hash"] == stored.content_hash
    assert assertion["predicate"] == "enjoys_activity"
    assert len(operations) == 1
    assert operations[0].operation_type == MemoryOperationType.synthesis
    assert operations[0].status == MemoryOperationStatus.committed


def test_promotion_and_supersession_share_one_commit_and_remove_old_assertion():
    source = _item("mem_new", "I now live in Seattle.")
    old = _item("mem_old", "The user lives in Portland.", tier=MemoryTier.long_term)
    old = old.model_copy(
        update={
            "graph_ready": True,
            "graph_assertion_id": "mga_old",
            "graph_plan_hash": "old-plan",
            "kg_extracted": True,
        }
    )
    db = _db_for_items(source, old)
    db.docs[f"users/{UID}/memory_graph_assertions/{old.memory_id}"] = {
        "assertion_id": "mga_old",
    }
    decision = _promote_decision(
        source,
        supersedes=[old.memory_id],
        target_memory_id=old.memory_id,
    )

    applied_ids = _apply(source, decision, db)

    promoted = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    superseded = MemoryItem(**db.docs[f"users/{UID}/memory_items/{old.memory_id}"])
    assert applied_ids == [source.memory_id, old.memory_id]
    assert promoted.tier == MemoryTier.long_term
    assert superseded.status == MemoryItemStatus.superseded
    assert superseded.superseded_by == source.memory_id
    assert superseded.canonical_memory_id == source.memory_id
    items_by_id = {item.memory_id: item for item in (promoted, superseded)}
    assert canonical_lineage_root(promoted, items_by_id=items_by_id) == source.memory_id
    assert canonical_lineage_root(superseded, items_by_id=items_by_id) == source.memory_id
    assert promoted.ledger_commit_id == superseded.ledger_commit_id
    assert f"users/{UID}/memory_graph_assertions/{old.memory_id}" not in db.docs


@pytest.mark.parametrize(
    ("route", "expected_status"),
    [
        ("archive", MemoryItemStatus.active),
        ("review", MemoryItemStatus.active),
        ("reject", MemoryItemStatus.hidden),
    ],
)
def test_nonpromote_routes_are_terminal_archive_outcomes(route: str, expected_status: MemoryItemStatus, monkeypatch):
    monkeypatch.setenv('MEMORY_UNDECIDED_VISIBLE', 'false')
    source = _item(f"mem_{route}", "A broad but non-durable observation.")
    db = _db_for_items(source)
    decision = ConsolidationAgentDecision(
        source_memory_id=source.memory_id,
        route=route,
        evidence_ids=[],
        relationship_to_user="unclear",
        basis_for_memory="weak_or_none",
        rationale="Not safe or useful enough for durable memory.",
    )

    _apply(source, decision, db)

    stored = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    assert stored.tier == MemoryTier.archive
    assert stored.status == expected_status
    review_path = f"users/{UID}/memory_review_queue/review:{source.memory_id}:r{stored.item_revision}:"
    if route == "review":
        assert db.docs[review_path]["source_commit_id"] == stored.ledger_commit_id
        assert db.docs[review_path]["status"] == "pending"
        assert db.docs[review_path]["authority"] == "canonical_memory"
    else:
        assert review_path not in db.docs
    assert stored.graph_ready is False
    assert f"users/{UID}/memory_graph_assertions/{source.memory_id}" not in db.docs


def test_reject_hides_after_consolidation():
    source = _item("mem_reject_off", "A broad but non-durable observation.")
    db = _db_for_items(source)
    decision = ConsolidationAgentDecision(
        source_memory_id=source.memory_id,
        route="reject",
        evidence_ids=[],
        relationship_to_user="unclear",
        basis_for_memory="weak_or_none",
        rationale="Not safe or useful enough for durable memory.",
    )
    _apply(source, decision, db)
    stored = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    assert stored.tier == MemoryTier.archive
    assert stored.status == MemoryItemStatus.hidden


def test_expired_review_is_not_requeued_by_consolidation_replay():
    source = _item('mem_expired_review', 'A synthetic review candidate.')
    db = _db_for_items(source)
    decision = ConsolidationAgentDecision(
        source_memory_id=source.memory_id,
        route='review',
        evidence_ids=[],
        relationship_to_user='unclear',
        basis_for_memory='weak_or_none',
        rationale='Needs review.',
    )
    _apply(source, decision, db)
    stored = MemoryItem(**db.docs[f'users/{UID}/memory_items/{source.memory_id}'])
    review_path = f'users/{UID}/memory_review_queue/review:{source.memory_id}:r{stored.item_revision}:'
    db.docs[review_path].update({'status': 'expired', 'permitted_uses': []})
    before = {path: dict(row) for path, row in db.docs.items()}

    assert stored.tier == MemoryTier.short_term
    _apply(source, decision, db)

    assert db.docs == before
    assert db.docs[review_path]['status'] == 'expired'


def test_quarantine_review_is_a_canonical_blocked_commit_with_projection_deletes():
    source = _item("mem_quarantine", "A source that exhausted automatic consolidation.")
    db = _db_for_items(source)
    decision = ConsolidationAgentDecision(
        source_memory_id=source.memory_id,
        route="review",
        relationship_to_user="unclear",
        basis_for_memory="weak_or_none",
        rationale="Automatic consolidation exhausted its bounded retry budget.",
    )

    _apply(source, decision, db, quarantine=True)

    stored = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    assert stored.tier == MemoryTier.short_term
    assert stored.processing_state == ProcessingState.blocked
    assert stored.promotion is not None
    assert stored.promotion["route"] == "review"
    assert stored.promotion["processing_status"] == "processing_blocked"
    review_path = f"users/{UID}/memory_review_queue/review:{source.memory_id}:r{stored.item_revision}:"
    assert db.docs[review_path]["status"] == "pending"
    outbox = [payload for path, payload in db.docs.items() if path.startswith(f"users/{UID}/memory_outbox/")]
    assert len(outbox) == 2
    assert {event["payload"]["action"] for event in outbox} == {"delete"}


def test_same_route_retry_is_idempotent_and_does_not_increment_revision_twice():
    source = _item("mem_idempotent", "I enjoy hiking.")
    db = _db_for_items(source)
    decision = _promote_decision(source)

    _apply(source, decision, db)
    first = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    _apply(source, decision, db)
    second = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])

    assert second.item_revision == first.item_revision
    assert second.ledger_commit_id == first.ledger_commit_id


def test_pending_required_promote_stamps_processing_receipt_then_routes():
    content = "Remember I enjoy hiking in Seattle."
    source = _item("mem_required", content)
    source = source.model_copy(
        update={
            "processing_state": ProcessingState.pending,
            "user_asserted": True,
            "promotion": {
                "required": True,
                "status": "pending",
                "processing_status": "pending_processing",
                "processor_id": REQUIRED_PROCESSOR_ID,
                "processor_version": REQUIRED_PROCESSOR_VERSION,
                "submission": {
                    "submission_id": source.memory_id,
                    "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                },
                "source_attribution": {
                    "subject_entity_id": "user",
                    "subject_attribution": "user",
                },
            },
        }
    )
    db = _db_for_items(source)

    applied_ids = _apply(source, _promote_decision(source), db)

    stored = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    operations = [
        MemoryOperation(**payload)
        for path, payload in db.docs.items()
        if path.startswith(f"users/{UID}/memory_operations/")
    ]
    assert applied_ids == [source.memory_id]
    assert stored.tier == MemoryTier.long_term
    assert stored.content == "The user enjoys hiking in Seattle."
    assert stored.processing_state == ProcessingState.processed
    assert stored.promotion is not None
    assert stored.promotion.get("required") is True
    assert valid_required_processing_receipt(
        content=stored.content,
        item_revision=stored.item_revision,
        promotion=stored.promotion,
    )
    assert (
        stored.promotion["processing_receipt"]["output_hash"]
        == hashlib.sha256(stored.content.encode("utf-8")).hexdigest()
    )
    assert len(operations) == 2
    assert {op.operation_type for op in operations} == {MemoryOperationType.synthesis}


def test_already_processed_required_promote_rebinds_memory_text_to_l2_content():
    l2_content = "The user enjoys hiking in Seattle."
    raw = "Remember I enjoy hiking in Seattle."
    source = _item("mem_required_processed", l2_content)
    source = source.model_copy(
        update={
            "user_asserted": True,
            "promotion": {
                "required": True,
                "status": "pending",
                "processing_status": "processed",
                "processor_id": REQUIRED_PROCESSOR_ID,
                "processor_version": REQUIRED_PROCESSOR_VERSION,
                "submission": {
                    "submission_id": source.memory_id,
                    "content_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                },
                "processing_receipt": {
                    "receipt_version": REQUIRED_PROCESSING_RECEIPT_VERSION,
                    "processor_id": REQUIRED_PROCESSOR_ID,
                    "processor_version": REQUIRED_PROCESSOR_VERSION,
                    "decision": "durable_required",
                    "processed_at": NOW.isoformat(),
                    "input_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "output_hash": hashlib.sha256(l2_content.encode("utf-8")).hexdigest(),
                    "input_item_revision": source.item_revision - 1,
                    "output_item_revision": source.item_revision,
                    "source_submission_id": source.memory_id,
                    "rationale": "normalized during consolidation",
                },
                "source_attribution": {
                    "subject_entity_id": "user",
                    "subject_attribution": "user",
                },
            },
        }
    )
    db = _db_for_items(source)
    decision = _promote_decision(source).model_copy(update={"memory_text": "The user loves backpacking instead."})

    applied_ids = _apply(source, decision, db)

    stored = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    assert applied_ids == [source.memory_id]
    assert stored.tier == MemoryTier.long_term
    assert stored.content == l2_content
    assert valid_required_processing_receipt(
        content=stored.content,
        item_revision=stored.item_revision,
        promotion=stored.promotion or {},
    )


def test_free_owner_observation_gets_receipted_decision_without_dream_membership(monkeypatch):
    """Post-retirement regression: ordinary processed rows had no route writer."""
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'allowlist')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', '')
    source = _item('mem_ordinary', 'Enjoys hiking in Seattle.')
    source.subject_entity_id = 'user'
    source.promotion = {'source_attribution': {'subject_entity_id': 'user', 'subject_attribution': 'user'}}
    # Expiry is not a decision; backlogged rows must also reach intake.
    source.captured_at = NOW - timedelta(days=4)
    db = _db_for_items(source)
    report = observation_intake.complete_observation_intake(
        UID,
        memory_ids=[source.memory_id],
        db_client=db,
        now=NOW,
        run_id='ordinary',
        planner=lambda items: [_promote_decision(items[0])],
    )
    stored = MemoryItem(**db.docs[f'users/{UID}/memory_items/{source.memory_id}'])
    assert report.promoted_memory_ids == [source.memory_id]
    assert stored.tier == MemoryTier.long_term
    assert stored.promotion['admission_receipt']
    assert stored.graph_ready


def test_observation_failure_preserves_committed_capture(monkeypatch):
    source = _item('mem_retry', 'Enjoys hiking.')
    db = _db_for_items(source)
    before = dict(db.docs[f'users/{UID}/memory_items/{source.memory_id}'])

    def fail(items):
        raise RuntimeError('synthetic planner unavailable')

    report = observation_intake.complete_observation_intake(
        UID,
        memory_ids=[source.memory_id],
        db_client=db,
        now=NOW,
        run_id='retry',
        planner=fail,
    )
    assert report.failed_memory_ids == [source.memory_id]
    assert db.docs[f'users/{UID}/memory_items/{source.memory_id}'] == before


def test_review_stays_short_term_and_rollback_restores_archive(monkeypatch):
    for enabled, expected in [('true', MemoryTier.short_term), ('false', MemoryTier.archive)]:
        monkeypatch.setenv('MEMORY_UNDECIDED_VISIBLE', enabled)
        source = _item('mem_review_switch', 'A synthetic observation awaiting confirmation.')
        db = _db_for_items(source)
        _apply(source, ConsolidationAgentDecision(source_memory_id=source.memory_id, route='review'), db)
        stored = MemoryItem(**db.docs[f'users/{UID}/memory_items/{source.memory_id}'])
        assert stored.tier == expected
        assert stored.promotion['route'] == 'review'


@pytest.mark.parametrize(
    'field,value',
    [
        ('status', MemoryItemStatus.hidden),
        ('processing_state', ProcessingState.blocked),
        ('source_state', SourceState.tombstoned),
    ],
)
def test_observation_intake_never_resurrects_fenced_rows(field, value):
    source = _item('mem_fenced', 'A synthetic observation.')
    source = source.model_copy(update={field: value})
    db = _db_for_items(source)
    canonical_consolidation._read_control_state(UID, db_client=db)
    before = dict(db.docs)
    report = observation_intake.complete_observation_intake(
        UID,
        memory_ids=[source.memory_id],
        db_client=db,
        now=NOW,
        run_id='fenced',
        planner=lambda items: pytest.fail('fenced row reached planner'),
    )
    assert not report.decided_memory_ids
    assert db.docs == before


@pytest.mark.parametrize('promotion', [{'is_locked': True}, {'user_review': False}, {'required': True}])
def test_observation_intake_preserves_locks_rejection_and_explicit_intake(promotion):
    source = _item('mem_locked', 'A synthetic observation.')
    source.promotion = promotion
    db = _db_for_items(source)
    report = observation_intake.complete_observation_intake(
        UID,
        memory_ids=[source.memory_id],
        db_client=db,
        now=NOW,
        run_id='locked',
        planner=lambda items: pytest.fail('protected row reached planner'),
    )
    assert not report.decided_memory_ids


@pytest.mark.parametrize('unsafe', ['partition', 'foreign_evidence', 'unknown_subject', 'supersedes'])
def test_observation_intake_validates_whole_batch_before_writing(unsafe):
    source = _item('mem_unsafe', 'A synthetic observation.')
    db = _db_for_items(source)
    canonical_consolidation._read_control_state(UID, db_client=db)
    before = dict(db.docs)
    decision = _promote_decision(source)
    if unsafe == 'partition':
        decisions = []
    else:
        changes = {
            'foreign_evidence': {'evidence_ids': ['foreign']},
            'unknown_subject': {'subject_entity_id': 'invented'},
            'supersedes': {'supersedes': ['unseen']},
        }
        decisions = [decision.model_copy(update=changes[unsafe])]
    report = observation_intake.complete_observation_intake(
        UID,
        memory_ids=[source.memory_id],
        db_client=db,
        now=NOW,
        run_id='unsafe',
        planner=lambda items: decisions,
    )
    assert report.failed_memory_ids == [source.memory_id]
    assert db.docs == before


def test_restricted_observation_gets_review_without_provider_call():
    from unittest.mock import Mock

    source = _item('mem_restricted', 'Sensitive fixture content.')
    source.sensitivity_labels = ['credential']
    model = Mock(side_effect=AssertionError('restricted evidence reached provider'))
    decisions = observation_intake.plan_observation_intake([source], llm=model)
    assert [d.route for d in decisions] == ['review']
    model.invoke.assert_not_called()


@pytest.mark.parametrize('changed_field', ['source_generation', 'writer_epoch', 'writer_mode'])
def test_observation_generation_race_keeps_source_undecided(changed_field):
    source = _item('mem_generation', 'Enjoys hiking in Seattle.')
    source.subject_entity_id = 'user'
    source.promotion = {'source_attribution': {'subject_entity_id': 'user', 'subject_attribution': 'user'}}
    db = _db_for_items(source)

    def race(items):
        state = db.docs[f'users/{UID}/memory_state/apply_control']
        if changed_field == 'writer_mode':
            state[changed_field] = 'ledger'
        else:
            state[changed_field] += 1
        return [_promote_decision(items[0])]

    report = observation_intake.complete_observation_intake(
        UID,
        memory_ids=[source.memory_id],
        db_client=db,
        now=NOW,
        run_id='generation',
        planner=race,
    )
    assert report.failed_memory_ids == [source.memory_id]
    stored = MemoryItem(**db.docs[f'users/{UID}/memory_items/{source.memory_id}'])
    assert stored.tier == MemoryTier.short_term
    assert not (stored.promotion or {}).get('route')


@pytest.mark.asyncio
async def test_observation_recovery_separates_db_and_model_steps(monkeypatch):
    from utils import executors

    source = _item('mem_recovery', 'Enjoys hiking in Seattle.')
    source.subject_entity_id = 'user'
    source.promotion = {'source_attribution': {'subject_entity_id': 'user', 'subject_attribution': 'user'}}
    db = _db_for_items(source)
    pools = []

    async def blocking(pool, fn, *args, **kwargs):
        pools.append(pool)
        return fn(*args, **kwargs)

    monkeypatch.setattr(executors, 'run_blocking', blocking)
    monkeypatch.setattr(observation_intake, '_pending_observation_ids', lambda *args, **kwargs: [source.memory_id])
    monkeypatch.setattr(observation_intake, 'plan_observation_intake', lambda items: [_promote_decision(items[0])])
    report = await observation_intake.complete_pending_observation_intake(
        UID,
        db_client=db,
        now=NOW,
        run_id='recovery',
    )
    assert report.promoted_memory_ids == [source.memory_id]
    assert pools == [executors.db_executor, executors.db_executor, executors.llm_executor, executors.db_executor]


@pytest.mark.parametrize('setting', ['0', 'false', 'off', 'no'])
@pytest.mark.asyncio
async def test_observation_kill_switch_stops_all_entrypoints_before_any_work(monkeypatch, setting):
    monkeypatch.setenv('MEMORY_OBSERVATION_INTAKE_ENABLED', setting)
    monkeypatch.setenv('MEMORY_UNDECIDED_VISIBLE', 'true')

    def unexpected(*args, **kwargs):
        pytest.fail('disabled intake attempted a read, cursor write or planner call')

    monkeypatch.setattr(observation_intake, '_load_observation_intake', unexpected)
    monkeypatch.setattr(observation_intake, '_pending_observation_ids', unexpected)
    monkeypatch.setattr(observation_intake, 'plan_observation_intake', unexpected)
    common = dict(db_client=object(), now=NOW, run_id='disabled')
    reports = [
        observation_intake.complete_observation_intake(UID, memory_ids=['already_committed'], **common),
        observation_intake.complete_pending_observation_intake_sync(UID, **common),
        await observation_intake.complete_pending_observation_intake(UID, **common),
    ]
    assert all(not r.decided_memory_ids and not r.failed_memory_ids and r.error_code is None for r in reports)


@pytest.mark.parametrize('sizes,expected_calls', [([20_000] * 4, 2), ([100_000], 0), ([2_000, 100_000, 2_000], 2)])
def test_context_budget_splits_to_items_and_reviews_oversized_singleton(sizes, expected_calls, monkeypatch):
    import json
    from types import SimpleNamespace

    from langchain_core import output_parsers

    # This file's isolation fixture replaces LangChain; preserve real Pydantic
    # validation at the seam instead of the fixture's unrestricted MagicMock.
    class Parser:
        def __init__(self, *, pydantic_object):
            self.schema = pydantic_object

        def get_format_instructions(self):
            return json.dumps(self.schema.model_json_schema())

        def parse(self, content):
            return self.schema.model_validate_json(content)

    monkeypatch.setattr(output_parsers, 'PydanticOutputParser', Parser)
    monkeypatch.delenv('MEMORY_OBSERVATION_INTAKE_ENABLED', raising=False)
    items = [_item(f'mem_budget_{i}', 'x' * size) for i, size in enumerate(sizes)]
    db = _db_for_items(*items)
    requests = []

    class Model:
        def invoke(self, messages):
            payload = messages[-1]['content']
            assert len(payload.encode()) <= 64_000
            rows = json.loads(payload)
            requests.append([row['memory_id'] for row in rows])
            return SimpleNamespace(
                content=json.dumps(
                    {'decisions': [{'source_memory_id': row['memory_id'], 'route': 'review'} for row in rows]}
                )
            )

    report = observation_intake.complete_observation_intake(
        UID,
        memory_ids=[item.memory_id for item in items],
        db_client=db,
        now=NOW,
        run_id='budget',
        planner=lambda selected: observation_intake.plan_observation_intake(selected, llm=Model()),
    )
    assert report.error_code is None
    assert report.decided_memory_ids == [item.memory_id for item in items]
    assert len(requests) == expected_calls
    sent = [memory_id for batch in requests for memory_id in batch]
    assert len(sent) == len(set(sent))
    assert set(sent) == {item.memory_id for item, size in zip(items, sizes) if size < 64_000}
    for source in items:
        stored = MemoryItem(**db.docs[f'users/{UID}/memory_items/{source.memory_id}'])
        assert stored.promotion['route'] == 'review'
        assert stored.content == source.content
        assert stored.status == MemoryItemStatus.active
