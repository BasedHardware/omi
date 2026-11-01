"""Required-intake cursor advances fairly without mutating the apply head."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace

import pytest

from models.memory_admission import (
    REQUIRED_PROCESSING_RECEIPT_VERSION,
    REQUIRED_PROCESSOR_ID,
    REQUIRED_PROCESSOR_VERSION,
)
from models.memory_evidence import MemoryEvidence
from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItem
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.memory import canonical_consolidation as intake

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)
UID = 'synthetic-required-intake'


def item(memory_id, *, required=True):
    content = 'Synthetic owner prefers green tea.'
    promotion = {
        'required': required,
        'processing_status': 'processed',
        'processor_id': REQUIRED_PROCESSOR_ID,
        'processor_version': REQUIRED_PROCESSOR_VERSION,
        'submission': {'submission_id': memory_id, 'content_hash': 'submitted'},
        'processing_receipt': {
            'receipt_version': REQUIRED_PROCESSING_RECEIPT_VERSION,
            'processor_id': REQUIRED_PROCESSOR_ID,
            'processor_version': REQUIRED_PROCESSOR_VERSION,
            'decision': 'durable_required',
            'source_submission_id': memory_id,
            'input_hash': 'submitted',
            'output_hash': hashlib.sha256(content.encode()).hexdigest(),
            'input_item_revision': 1,
            'output_item_revision': 2,
        },
    }
    return MemoryItem(
        memory_id=memory_id,
        uid=UID,
        version=1,
        tier='short_term',
        status='active',
        processing_state='processed',
        source_state='active',
        content=content,
        item_revision=2,
        evidence=[
            MemoryEvidence(
                evidence_id='ev-' + memory_id,
                source_id='source-' + memory_id,
                source_type='manual',
                source_version='1',
                artifact_preservation='preserved',
            )
        ],
        sensitivity_labels=[],
        visibility='private',
        user_asserted=True,
        captured_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(days=7),
        subject_entity_id='user',
        predicate='prefers',
        arguments={'drink': 'green tea'},
        promotion=promotion,
    )


def setup(monkeypatch, items):
    db = StrictFirestore()
    head = db.document(f'users/{UID}/memory_state/apply_control')
    control = MemoryControlState(
        uid=UID, head_commit_id='concurrent', commit_sequence=42, account_generation=0, source_generation=0
    )
    head.create(control.model_dump(mode='python'))

    def page(uid, *, db_client, cursor=None):
        assert uid == UID and db_client is db
        selected = [row for row in items if not cursor or row.memory_id > cursor['memory_id']]
        return [SimpleNamespace(to_dict=lambda row=row: row.model_dump(mode='python')) for row in selected[:100]]

    monkeypatch.setattr(intake, '_required_intake_page', page)
    monkeypatch.setattr(intake, '_read_control_state', lambda *_, **__: control)
    return db, head


def test_only_valid_required_receipts_complete_and_cursor_preserves_head(monkeypatch):
    ordinary = item('a', required=False)
    invalid = item('b')
    invalid.promotion['processing_receipt']['output_hash'] = 'stale'
    valid = item('c')
    db, head = setup(monkeypatch, [ordinary, invalid, valid])
    applied = []
    monkeypatch.setattr(intake, 'apply_consolidation_decision', lambda *_, **kw: applied.append(kw))
    before = deepcopy(head.get().to_dict())
    result = intake.complete_required_intake(UID, db_client=db, now=NOW, run_id='required')
    assert result.promoted_memory_ids == ['c']
    assert len(applied) == 1
    assert applied[0]['decision'].memory_text == valid.content
    assert not applied[0]['decision'].supersedes
    assert head.get().to_dict() == before
    assert db.document(f'users/{UID}/memory_runs/required_intake_cursor').get().to_dict()['memory_id'] == 'c'


def test_ordinary_observations_do_not_starve_required_intake(monkeypatch):
    rows = [item(f'a-{i:03}', required=False) for i in range(101)] + [item('z')]
    db, _ = setup(monkeypatch, rows)
    monkeypatch.setattr(intake, 'apply_consolidation_decision', lambda *_, **__: None)
    first = intake.complete_required_intake(UID, db_client=db, now=NOW, run_id='page-1')
    second = intake.complete_required_intake(UID, db_client=db, now=NOW, run_id='page-2')
    assert first.promoted_memory_ids == []
    assert second.promoted_memory_ids == ['z']


def test_disposition_failure_advances_bounded_cursor_and_reports_failure(monkeypatch):
    db, _ = setup(monkeypatch, [item('a'), item('b')])

    def apply(*_, **kw):
        if kw['decision'].source_memory_id == 'a':
            raise intake.ConsolidationApplySkipped('revision changed')

    monkeypatch.setattr(intake, 'apply_consolidation_decision', apply)
    result = intake.complete_required_intake(UID, db_client=db, now=NOW, run_id='failure')
    assert result.failed_memory_ids == ['a'] and result.promoted_memory_ids == ['b']


def test_cursor_concurrency_cannot_rewind_another_run(monkeypatch):
    db, _ = setup(monkeypatch, [item('a')])
    cursor = db.document(f'users/{UID}/memory_runs/required_intake_cursor')

    def apply(*_, **__):
        cursor.create({'captured_at': NOW, 'memory_id': 'z'})

    monkeypatch.setattr(intake, 'apply_consolidation_decision', apply)
    with pytest.raises(RuntimeError, match='cursor changed'):
        intake.complete_required_intake(UID, db_client=db, now=NOW, run_id='race')
    assert cursor.get().to_dict()['memory_id'] == 'z'
