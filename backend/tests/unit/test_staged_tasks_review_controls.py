"""Staged-task storage primitives and universal compatibility review controls."""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from database import action_items as action_items_db
from database import staged_tasks as staged_tasks_db
from models.candidate import CandidateAction, CandidateCreate, CandidateRecord, CandidateStatus
from models.task_intelligence import TaskWorkflowControl
import routers.staged_tasks as router
from utils.task_intelligence.staged_migration import proposal_from_legacy_staged

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'sk-test')

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def universal_control(monkeypatch):
    monkeypatch.setattr(
        router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=7),
    )


def _make_doc(doc_id, data):
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    return doc


def _stub_staged_by_id(monkeypatch, task_id, data):
    snapshot = MagicMock()
    snapshot.exists = data is not None
    snapshot.id = task_id
    snapshot.to_dict.return_value = data
    updates = {}
    ref = MagicMock()
    ref.get.return_value = snapshot
    ref.update.side_effect = lambda payload: updates.update(payload)
    collection = MagicMock()
    collection.document.return_value = ref
    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: collection)
    return collection, updates


def _candidate(candidate_id: str, *, row_id: str = 'compat-1', description: str = 'Task') -> CandidateRecord:
    proposal = proposal_from_legacy_staged({'id': row_id, 'description': description})
    return CandidateRecord(
        **proposal.model_dump(mode='python'),
        candidate_id=candidate_id,
        account_generation=7,
        idempotency_key=f'idem-{candidate_id}',
        created_at=NOW,
    )


def test_storage_promotes_exact_historical_row(monkeypatch):
    collection, updates = _stub_staged_by_id(
        monkeypatch,
        'staged-x',
        {'id': 'staged-x', 'description': 'Unique task', 'completed': False},
    )
    monkeypatch.setattr(action_items_db, 'get_active_action_item_by_description', lambda uid, desc: None)
    monkeypatch.setattr(action_items_db, 'create_action_item', lambda uid, data: 'fresh-1')
    monkeypatch.setattr(
        action_items_db,
        'get_action_item',
        lambda uid, task_id: {'id': task_id, 'description': 'Unique task'},
    )

    result = staged_tasks_db.promote_staged_task('uid', task_id='staged-x')

    assert result == {'id': 'fresh-1', 'description': 'Unique task'}
    collection.document.assert_any_call('staged-x')
    assert updates['completed'] is True
    assert updates['promoted_to'] == 'fresh-1'


def test_storage_clear_deletes_only_active_rows(monkeypatch):
    query = MagicMock()
    query.select.return_value = query
    query.stream.return_value = iter([_make_doc('a', {}), _make_doc('b', {})])
    collection = MagicMock()
    collection.where.return_value = query
    batch = MagicMock()
    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: collection)
    monkeypatch.setattr(staged_tasks_db, 'db', MagicMock(batch=MagicMock(return_value=batch)))

    assert staged_tasks_db.clear_staged_tasks('uid') == 2
    assert batch.delete.call_count == 2
    batch.commit.assert_called_once()
    collection.where.assert_called_once()


def test_historical_projection_reads_every_row_and_includes_pre_completed_schema(monkeypatch):
    snapshots = [
        _make_doc('old-1', {'description': 'Old task'}),
        _make_doc('closed-1', {'description': 'Closed task', 'completed': True}),
    ]
    collection = MagicMock()
    collection.order_by.return_value = collection
    collection.stream.return_value = snapshots
    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: collection)

    rows = staged_tasks_db.get_active_staged_tasks_for_compatibility('user-1')

    assert rows == [{'id': 'old-1', 'description': 'Old task'}]
    collection.order_by.assert_called_once_with('__name__')
    collection.limit.assert_not_called()


def test_historical_point_lookup_includes_missing_completed_and_hides_terminal(monkeypatch):
    snapshots = {
        'active': _make_doc('active', {'description': 'Old task'}),
        'closed': _make_doc('closed', {'description': 'Closed task', 'completed': True}),
    }
    for snapshot in snapshots.values():
        snapshot.exists = True
    missing = MagicMock(exists=False)
    collection = MagicMock()
    collection.document.side_effect = lambda staged_id: MagicMock(
        get=MagicMock(return_value=snapshots.get(staged_id, missing))
    )
    monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: collection)

    assert staged_tasks_db.get_staged_task_for_compatibility('user-1', 'active') == {
        'id': 'active',
        'description': 'Old task',
    }
    assert staged_tasks_db.get_staged_task_for_compatibility('user-1', 'closed') is None
    assert staged_tasks_db.get_staged_task_for_compatibility('user-1', 'missing') is None


def test_candidate_by_id_promotion_never_calls_historical_promoter(monkeypatch):
    candidate = _candidate('candidate-1')
    monkeypatch.setattr(router.candidates_db, 'get_candidate', lambda uid, candidate_id: candidate)
    monkeypatch.setattr(
        router.staged_tasks_db,
        'get_staged_task_for_compatibility',
        lambda uid, staged_id: pytest.fail('canonical id must not read historical rows'),
    )
    monkeypatch.setattr(
        router.staged_tasks_db,
        'promote_staged_task',
        lambda *args, **kwargs: pytest.fail('router must not use historical action-item authority'),
    )
    retired = []
    monkeypatch.setattr(
        router.staged_tasks_db,
        'delete_staged_task',
        lambda uid, row_id: retired.append(row_id) or False,
    )
    monkeypatch.setattr(
        router.candidate_service,
        'accept_candidate',
        lambda *args, **kwargs: type('Receipt', (), {'task_id': 'task-1'})(),
    )
    monkeypatch.setattr(router.action_items_db, 'get_action_item', lambda uid, task_id: {'id': task_id})

    result = router.promote_staged_task_by_id('candidate-1', uid='user-1')

    assert result == {'promoted': True, 'reason': None, 'promoted_task': {'id': 'task-1'}}
    assert retired == ['compat-1']


def test_non_staged_candidate_is_not_mutable_through_compatibility_route(monkeypatch):
    proposal = CandidateCreate.model_validate(
        {
            'subject_kind': 'task',
            'proposed_action': CandidateAction.update,
            'task_id': 'task-1',
            'task_change': {'description': 'Update'},
            'capture_confidence': 0.8,
            'ownership_confidence': 0.8,
            'evidence_refs': [{'kind': 'external', 'id': 'agent-1', 'scope': 'canonical'}],
            'source_surface': 'agent',
        }
    )
    candidate = CandidateRecord(
        **proposal.model_dump(mode='python'),
        candidate_id='candidate-update',
        account_generation=7,
        idempotency_key='idem',
        created_at=NOW,
    )
    monkeypatch.setattr(router.candidates_db, 'get_candidate', lambda uid, candidate_id: candidate)
    monkeypatch.setattr(router.staged_tasks_db, 'get_staged_task_for_compatibility', lambda uid, staged_id: None)

    assert router.delete_staged_task('candidate-update', uid='user-1') == {'status': 'ok'}
    with pytest.raises(HTTPException) as error:
        router.promote_staged_task_by_id('candidate-update', uid='user-1')
    assert error.value.status_code == 404


def test_clear_rejects_candidate_and_each_historical_row_before_cleanup(monkeypatch):
    candidate = _candidate('candidate-new', row_id='compat-new')
    rows = [
        {'id': 'old-1', 'description': 'Old 1', 'completed': False, 'created_at': NOW, 'updated_at': NOW},
        {'id': 'old-2', 'description': 'Old 2', 'completed': False, 'created_at': NOW, 'updated_at': NOW},
    ]
    monkeypatch.setattr(
        router.candidates_db,
        'list_candidates_compatibility_page',
        lambda uid, **kwargs: ([candidate], 1, candidate) if kwargs.get('cursor') is None else ([], 0, None),
    )
    monkeypatch.setattr(router.staged_tasks_db, 'get_active_staged_tasks_for_compatibility', lambda uid: rows)
    events = []

    def materialize(uid, proposal, *, idempotency_key, account_generation):
        row_id = proposal.evidence_refs[0].id.removeprefix('legacy-staged-')
        events.append(f'materialize:{row_id}')
        return _candidate(f'candidate-{row_id}', row_id=row_id)

    monkeypatch.setattr(router.candidate_service, 'create_candidate', materialize)
    monkeypatch.setattr(
        router.candidate_service,
        'reject_candidate',
        lambda uid, candidate_id, **kwargs: events.append(f'reject:{candidate_id}'),
    )
    monkeypatch.setattr(
        router.staged_tasks_db,
        'delete_staged_task',
        lambda uid, row_id: events.append(f'retire:{row_id}') or True,
    )

    response = router.clear_staged_tasks(uid='user-1')

    assert response == {'status': 'ok', 'deleted_count': 3}
    assert events == [
        'reject:candidate-new',
        'materialize:old-1',
        'reject:candidate-old-1',
        'retire:old-1',
        'materialize:old-2',
        'reject:candidate-old-2',
        'retire:old-2',
    ]


def test_batch_scores_update_canonical_candidate_compatibility(monkeypatch):
    calls = []
    monkeypatch.setattr(
        router,
        '_candidate_for_public_id',
        lambda uid, task_id, **kwargs: _candidate('candidate-1', row_id=task_id),
    )
    monkeypatch.setattr(
        router.candidates_db,
        'update_candidate_compatibility_score',
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    response = router.batch_update_staged_scores(
        router.BatchUpdateScoresRequest(scores=[router.BatchScoreEntry(id='old-1', relevance_score=42)]),
        uid='user-1',
    )

    assert response == {'status': 'ok'}
    assert calls == [
        (('user-1', 'candidate-1'), {'relevance_score': 42, 'account_generation': 7}),
    ]


def test_batch_scores_ignore_terminal_candidate_conflict(monkeypatch):
    monkeypatch.setattr(
        router,
        '_candidate_for_public_id',
        lambda uid, task_id, **kwargs: _candidate('candidate-1', row_id=task_id),
    )
    monkeypatch.setattr(
        router.candidates_db,
        'update_candidate_compatibility_score',
        lambda *args, **kwargs: (_ for _ in ()).throw(router.candidates_db.CandidateConflictError('accepted')),
    )

    response = router.batch_update_staged_scores(
        router.BatchUpdateScoresRequest(scores=[router.BatchScoreEntry(id='old-1', relevance_score=42)]),
        uid='user-1',
    )

    assert response == {'status': 'ok'}


def test_create_preserves_staged_annotations_and_uses_them_in_identity(monkeypatch):
    rows = []

    def materialize(uid, row, *, account_generation):
        rows.append(row)
        proposal = proposal_from_legacy_staged(row)
        return CandidateRecord(
            **proposal.model_dump(mode='python'),
            candidate_id=row['id'],
            account_generation=account_generation,
            idempotency_key=row['id'],
            created_at=NOW,
        )

    monkeypatch.setattr(router, '_materialize_historical_candidate', materialize)

    first = router.create_staged_task(
        router.CreateStagedTaskRequest(
            description='Send the budget',
            metadata='from-agent',
            category='finance',
            relevance_score=10,
        ),
        uid='user-1',
    )
    second = router.create_staged_task(
        router.CreateStagedTaskRequest(
            description='Send the budget',
            metadata='from-agent',
            category='finance',
            relevance_score=20,
        ),
        uid='user-1',
    )

    assert rows[0]['metadata'] == 'from-agent'
    assert rows[0]['category'] == 'finance'
    assert rows[0]['relevance_score'] == 10
    assert rows[0]['id'] != rows[1]['id']
    assert first['metadata'] == 'from-agent'
    assert first['category'] == 'finance'
    assert first['relevance_score'] == 10
    assert second['relevance_score'] == 20


def test_top_promotion_uses_deterministic_merged_first_item(monkeypatch):
    monkeypatch.setattr(
        router,
        '_merged_staged_projection',
        lambda uid, *, account_generation: [
            {'id': 'first', 'description': 'First'},
            {'id': 'second', 'description': 'Second'},
        ],
    )
    monkeypatch.setattr(
        router,
        'promote_staged_task_by_id',
        lambda task_id, uid: {'promoted': True, 'reason': None, 'promoted_task': {'id': task_id}},
    )

    assert router.promote_staged_task(uid='user-1')['promoted_task']['id'] == 'first'
