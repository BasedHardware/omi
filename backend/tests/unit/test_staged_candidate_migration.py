from datetime import datetime, timezone

import pytest

import database.candidates as candidates_db
from models.candidate import CandidateCreate, CandidateRecord, CandidateStatus
from models.task_intelligence import TaskWorkflowControl
import routers.staged_tasks as staged_router
from utils.task_intelligence import candidate_service
from utils.task_intelligence.staged_migration import migrate_staged_tasks, proposal_from_legacy_staged


def _rows():
    now = datetime(2026, 7, 9, tzinfo=timezone.utc)
    return [
        {'id': 'active-1', 'description': 'Send the budget', 'completed': False, 'updated_at': now},
        {
            'id': 'accepted-1',
            'description': 'Call Sarah',
            'completed': True,
            'promoted_to': 'task-1',
            'promoted_at': now,
            'updated_at': now,
        },
        {
            'id': 'rejected-1',
            'description': 'Duplicate task',
            'completed': True,
            'promotion_skipped': 'duplicate_without_target',
            'updated_at': now,
        },
    ]


@pytest.mark.parametrize('mode', ['off', 'shadow'])
def test_off_and_shadow_migration_are_dry_run_without_candidate_writes(monkeypatch, mode):
    monkeypatch.setattr('database.staged_tasks.get_all_staged_tasks_for_migration', lambda uid: _rows())
    monkeypatch.setattr(candidate_service, 'create_candidate', lambda *args, **kwargs: pytest.fail('unexpected write'))

    report = migrate_staged_tasks('user-1', TaskWorkflowControl(workflow_mode=mode, account_generation=2))

    assert report.dry_run is True
    assert report.scanned == 3
    assert report.unchanged == 3
    assert report.created == 0


def test_write_migration_reconciles_terminal_history_and_is_idempotent(monkeypatch):
    monkeypatch.setattr('database.staged_tasks.get_all_staged_tasks_for_migration', lambda uid: _rows())
    records = {}

    def get_candidate(uid, candidate_id):
        return records.get(candidate_id)

    def create_candidate(uid, proposal, *, idempotency_key, account_generation):
        candidate_id = candidates_db.candidate_id_for_idempotency(uid, account_generation, idempotency_key)
        records.setdefault(
            candidate_id,
            CandidateRecord(
                **proposal.model_dump(mode='python'),
                candidate_id=candidate_id,
                account_generation=account_generation,
                idempotency_key=f'idem-{candidate_id}',
                created_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
            ),
        )
        return records[candidate_id]

    def reconcile(uid, candidate_id, *, status, result_task_id=None, reason=None, resolved_at=None, **kwargs):
        current = records[candidate_id]
        records[candidate_id] = CandidateRecord.model_validate(
            {
                **current.model_dump(mode='python'),
                'status': status,
                'result_task_id': result_task_id,
                'resolution_reason': reason,
                'resolved_at': resolved_at or datetime(2026, 7, 9, tzinfo=timezone.utc),
            }
        )
        return records[candidate_id]

    monkeypatch.setattr(candidates_db, 'get_candidate', get_candidate)
    monkeypatch.setattr(candidate_service, 'create_candidate', create_candidate)
    monkeypatch.setattr(candidates_db, 'reconcile_migrated_candidate', reconcile)
    control = TaskWorkflowControl(workflow_mode='write', account_generation=2)

    first = migrate_staged_tasks('user-1', control)
    second = migrate_staged_tasks('user-1', control)

    assert first.created == 3
    assert first.reconciled == 2
    assert first.failed == 0
    assert second.created == 0
    assert second.reconciled == 0
    assert second.unchanged == 3
    statuses = {record.status for record in records.values()}
    assert statuses == {CandidateStatus.pending, CandidateStatus.accepted, CandidateStatus.rejected}
    accepted = next(record for record in records.values() if record.status == CandidateStatus.accepted)
    assert accepted.result_task_id == 'task-1'


def test_migration_checkpoint_and_failure_report_never_include_task_content(monkeypatch):
    rows = _rows() + [{'id': 'bad-1', 'description': 'x' * 5000, 'completed': False}]
    monkeypatch.setattr('database.staged_tasks.get_all_staged_tasks_for_migration', lambda uid: rows)
    monkeypatch.setattr(candidates_db, 'get_candidate', lambda *args: None)
    monkeypatch.setattr(
        candidate_service, 'create_candidate', lambda *args, **kwargs: pytest.fail('only bad row selected')
    )

    report = migrate_staged_tasks(
        'user-1',
        TaskWorkflowControl(workflow_mode='read', account_generation=2),
        after_id='active-1',
        limit=1,
    )

    assert report.failed == 1
    assert report.failure_ids == ['bad-1']
    assert report.checkpoint == 'bad-1'
    assert 'x' * 20 not in report.model_dump_json()


def test_legacy_proposal_has_envelope_authority_and_no_score_semantics():
    proposal = proposal_from_legacy_staged(
        {'id': 'staged-1', 'description': 'Send the budget', 'priority': 'high', 'relevance_score': 999}
    )
    payload = proposal.model_dump(mode='json')

    assert payload['source_surface'] == 'legacy_staged'
    assert payload['capture_confidence'] == 0.5
    assert payload['task_change']['priority'] == 'high'
    assert 'relevance_score' not in payload
    assert 'goal_id' not in payload['task_change']
    assert 'evidence_refs' not in payload['task_change']


def test_read_mode_staged_create_projects_candidate_without_staged_write(monkeypatch):
    control = TaskWorkflowControl(workflow_mode='read', account_generation=5)
    monkeypatch.setattr(staged_router.task_control_db, 'get_task_workflow_control', lambda uid: control)
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'create_staged_task',
        lambda *args, **kwargs: pytest.fail('read mode must not write staged_tasks'),
    )

    def create_candidate(uid, proposal, *, idempotency_key, account_generation):
        return CandidateRecord(
            **proposal.model_dump(mode='python'),
            candidate_id='candidate-1',
            account_generation=account_generation,
            idempotency_key='idem-1',
            created_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(staged_router.candidate_service, 'create_candidate', create_candidate)
    request = staged_router.CreateStagedTaskRequest(description='Send the budget', priority='high')

    response = staged_router.create_staged_task(request, uid='user-1')

    assert response['id'] == 'candidate-1'
    assert response['description'] == 'Send the budget'
    assert response['priority'] == 'high'


def test_read_compatibility_only_projects_and_clears_legacy_task_creates(monkeypatch):
    now = datetime(2026, 7, 9, tzinfo=timezone.utc)

    def record(candidate_id, payload):
        proposal = CandidateCreate.model_validate(payload)
        return CandidateRecord(
            **proposal.model_dump(mode='python'),
            candidate_id=candidate_id,
            account_generation=5,
            idempotency_key=f'idem-{candidate_id}',
            created_at=now,
        )

    common = {
        'capture_confidence': 0.8,
        'ownership_confidence': 0.8,
        'evidence_refs': [{'kind': 'external', 'id': 'evidence-1', 'scope': 'canonical'}],
    }
    staged = record(
        'candidate-staged',
        {
            **common,
            'subject_kind': 'task',
            'proposed_action': 'create',
            'task_change': {'description': 'Staged create'},
            'source_surface': 'legacy_staged',
        },
    )
    update = record(
        'candidate-update',
        {
            **common,
            'subject_kind': 'task',
            'proposed_action': 'update',
            'task_id': 'task-1',
            'task_change': {'description': 'Updated task'},
            'source_surface': 'agent',
        },
    )
    workstream = record(
        'candidate-workstream',
        {
            **common,
            'subject_kind': 'workstream',
            'proposed_action': 'create',
            'workstream_proposal': {
                'title': 'Investor follow-up',
                'objective': 'Send update',
                'anchor_task': {'description': 'Draft update'},
            },
            'source_surface': 'agent',
        },
    )
    monkeypatch.setattr(
        staged_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=5),
    )
    monkeypatch.setattr(
        staged_router.candidates_db,
        'list_candidates',
        lambda uid, **kwargs: [staged, update, workstream],
    )
    rejected = []
    monkeypatch.setattr(
        staged_router.candidate_service,
        'reject_candidate',
        lambda uid, candidate_id, **kwargs: rejected.append(candidate_id),
    )

    listed = staged_router.get_staged_tasks(limit=100, offset=0, uid='user-1')
    cleared = staged_router.clear_staged_tasks(uid='user-1')

    assert [item['id'] for item in listed['items']] == ['candidate-staged']
    assert cleared['deleted_count'] == 1
    assert rejected == ['candidate-staged']
