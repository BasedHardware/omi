from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import database.candidates as candidates_db
from models.candidate import CandidateRecord, CandidateStatus
from models.task_intelligence import TaskWorkflowControl
import routers.staged_tasks as staged_router
from utils.task_intelligence.staged_migration import migrate_staged_tasks, proposal_from_legacy_staged

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def universal_task_control(monkeypatch):
    monkeypatch.setattr(
        staged_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=7),
    )


def _candidate(
    candidate_id: str,
    *,
    row_id: str,
    description: str,
    status: CandidateStatus = CandidateStatus.pending,
    created_at: datetime = NOW,
    result_task_id: str | None = None,
) -> CandidateRecord:
    proposal = proposal_from_legacy_staged({'id': row_id, 'description': description})
    return CandidateRecord(
        **proposal.model_dump(mode='python'),
        candidate_id=candidate_id,
        account_generation=7,
        idempotency_key=f'idem-{candidate_id}',
        status=status,
        result_task_id=result_task_id,
        resolution_reason=status.value if status != CandidateStatus.pending else None,
        created_at=created_at,
        resolved_at=created_at if status != CandidateStatus.pending else None,
    )


def _stub_candidates(monkeypatch, records: list[CandidateRecord]) -> None:
    monkeypatch.setattr(
        staged_router.candidates_db,
        'list_candidates_compatibility_page',
        lambda uid, **kwargs: (
            (records, len(records), records[-1] if records else None) if kwargs.get('cursor') is None else ([], 0, None)
        ),
    )


def test_migration_report_is_permanently_read_only_in_every_old_mode(monkeypatch):
    rows = [
        {'id': 'active-1', 'description': 'Send budget'},
        {'id': 'active-2', 'description': 'Call Sarah'},
    ]
    monkeypatch.setattr(
        'database.staged_tasks.get_all_staged_tasks_for_migration',
        lambda uid: rows,
    )

    for mode in ('off', 'shadow', 'write', 'read'):
        report = migrate_staged_tasks(
            'user-1',
            TaskWorkflowControl(workflow_mode=mode, account_generation=7),
        )
        assert report.dry_run is True
        assert report.scanned == 2
        assert report.unchanged == 2
        assert report.created == report.reconciled == report.failed == 0


def test_legacy_proposal_retains_compatibility_metadata_on_candidate_envelope():
    proposal = proposal_from_legacy_staged(
        {'id': 'staged-1', 'description': 'Send the budget', 'priority': 'high', 'relevance_score': 999}
    )
    payload = proposal.model_dump(mode='json')

    assert payload['source_surface'] == 'legacy_staged'
    assert payload['task_change']['priority'] == 'high'
    assert payload['evidence_refs'][0]['id'] == 'legacy-staged-staged-1'
    assert payload['compatibility'] == {'metadata': None, 'category': None, 'relevance_score': 999}


def test_semantic_candidate_reuse_merges_compatibility_annotations():
    existing_proposal = proposal_from_legacy_staged(
        {'id': 'old-row', 'description': 'Send the budget', 'metadata': 'old', 'category': 'finance'}
    )
    existing = CandidateRecord(
        **existing_proposal.model_dump(mode='python'),
        candidate_id='candidate-1',
        account_generation=7,
        idempotency_key='idem-1',
        created_at=NOW,
    )
    incoming = proposal_from_legacy_staged(
        {'id': 'new-row', 'description': 'Send the budget', 'metadata': 'new', 'relevance_score': 850}
    )

    merged = candidates_db._merge_candidate_annotations(existing, incoming)

    assert merged.compatibility is not None
    assert merged.compatibility.metadata == 'new'
    assert merged.compatibility.category == 'finance'
    assert merged.compatibility.relevance_score == 850


def test_get_pure_projects_mixed_rows_without_creating_candidates(monkeypatch):
    candidates = [
        _candidate('cand-new', row_id='compat-new', description='New candidate', created_at=NOW),
        _candidate('cand-old', row_id='old-materialized', description='Materialized row', created_at=NOW),
        _candidate(
            'cand-terminal',
            row_id='old-terminal',
            description='Already rejected',
            status=CandidateStatus.rejected,
        ),
    ]
    _stub_candidates(monkeypatch, candidates)
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'get_active_staged_tasks_for_compatibility',
        lambda uid: [
            {
                'id': 'old-visible',
                'description': 'Visible historical row',
                'completed': False,
                'created_at': NOW - timedelta(days=1),
                'updated_at': NOW,
                'relevance_score': 10,
            },
            {
                'id': 'old-materialized',
                'description': 'Must dedupe',
                'completed': False,
                'created_at': NOW,
                'updated_at': NOW,
            },
            {
                'id': 'old-terminal',
                'description': 'Must stay suppressed',
                'completed': False,
                'created_at': NOW,
                'updated_at': NOW,
            },
            {'id': 'old-closed', 'description': 'Closed', 'completed': True},
        ],
    )
    monkeypatch.setattr(
        staged_router.candidate_service,
        'create_candidate',
        lambda *args, **kwargs: pytest.fail('GET must never materialize a Candidate'),
    )
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'delete_staged_task',
        lambda *args, **kwargs: pytest.fail('GET must never retire historical data'),
    )

    response = staged_router.get_staged_tasks(limit=100, offset=0, uid='user-1')

    assert [item['id'] for item in response['items']] == ['old-visible', 'cand-new', 'cand-old']
    assert response['has_more'] is False


def test_get_order_and_pagination_are_deterministic(monkeypatch):
    _stub_candidates(
        monkeypatch,
        [
            _candidate('cand-b', row_id='compat-b', description='B', created_at=NOW),
            _candidate('cand-a', row_id='compat-a', description='A', created_at=NOW),
        ],
    )
    monkeypatch.setattr(staged_router.staged_tasks_db, 'get_active_staged_tasks_for_compatibility', lambda uid: [])

    first = staged_router.get_staged_tasks(limit=1, offset=0, uid='user-1')
    second = staged_router.get_staged_tasks(limit=1, offset=1, uid='user-1')

    assert [item['id'] for item in first['items']] == ['cand-a']
    assert first['has_more'] is True
    assert [item['id'] for item in second['items']] == ['cand-b']
    assert second['has_more'] is False


def test_candidate_projection_pages_past_5000_to_find_pending_data(monkeypatch):
    pending = _candidate('candidate-after-5000', row_id='compat-after-5000', description='Still visible')
    cursors = []

    def page(uid, *, account_generation, limit, cursor):
        cursors.append(cursor)
        page_number = 0 if cursor is None else cursor + 1
        if page_number < 10:
            return [], 500, page_number
        if page_number == 10:
            return [pending], 1, page_number
        raise AssertionError('pagination continued after exhaustion')

    monkeypatch.setattr(staged_router.candidates_db, 'list_candidates_compatibility_page', page)
    monkeypatch.setattr(staged_router.staged_tasks_db, 'get_active_staged_tasks_for_compatibility', lambda uid: [])

    response = staged_router.get_staged_tasks(limit=100, offset=0, uid='user-1')

    assert [item['id'] for item in response['items']] == ['candidate-after-5000']
    assert cursors == [None, *range(10)]


def test_terminal_candidate_after_5000_still_suppresses_historical_duplicate(monkeypatch):
    terminal = _candidate(
        'terminal-after-5000',
        row_id='old-terminal',
        description='Already closed',
        status=CandidateStatus.rejected,
    )

    def page(uid, *, account_generation, limit, cursor):
        page_number = 0 if cursor is None else cursor + 1
        if page_number < 10:
            return [], 500, page_number
        return ([terminal], 1, page_number) if page_number == 10 else ([], 0, None)

    monkeypatch.setattr(staged_router.candidates_db, 'list_candidates_compatibility_page', page)
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'get_active_staged_tasks_for_compatibility',
        lambda uid: [{'id': 'old-terminal', 'description': 'Must not resurrect', 'created_at': NOW}],
    )
    monkeypatch.setattr(
        staged_router.candidate_service,
        'create_candidate',
        lambda *args, **kwargs: pytest.fail('terminal dedup is read-only'),
    )

    response = staged_router.get_staged_tasks(limit=100, offset=0, uid='user-1')

    assert response == {'items': [], 'has_more': False}


def test_released_offset_can_reach_historical_row_after_5000(monkeypatch):
    _stub_candidates(monkeypatch, [])
    rows = [
        {
            'id': f'old-{index:05d}',
            'description': f'Historical {index}',
            'created_at': NOW,
            'updated_at': NOW,
        }
        for index in range(5001)
    ]
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'get_active_staged_tasks_for_compatibility',
        lambda uid: rows,
    )
    monkeypatch.setattr(
        staged_router.candidate_service,
        'create_candidate',
        lambda *args, **kwargs: pytest.fail('offset read must not write'),
    )

    response = staged_router.get_staged_tasks(limit=1, offset=5000, uid='user-1')

    assert [item['id'] for item in response['items']] == ['old-05000']
    assert response['has_more'] is False


def test_clear_reconciles_every_historical_row_after_5000(monkeypatch):
    _stub_candidates(monkeypatch, [])
    rows = [{'id': f'old-{index:05d}', 'description': f'Task {index}'} for index in range(5001)]
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'get_active_staged_tasks_for_compatibility',
        lambda uid: rows,
    )
    rejected = []
    retired = []
    monkeypatch.setattr(
        staged_router,
        '_materialize_historical_candidate',
        lambda uid, row, **kwargs: SimpleNamespace(
            candidate_id=f'candidate-{row["id"]}',
            status=CandidateStatus.pending,
        ),
    )
    monkeypatch.setattr(
        staged_router,
        '_reject_pending_candidate',
        lambda uid, candidate, **kwargs: rejected.append(candidate.candidate_id),
    )
    monkeypatch.setattr(
        staged_router,
        '_retire_historical_row',
        lambda uid, row_id: retired.append(row_id),
    )

    response = staged_router.clear_staged_tasks(uid='user-1')

    assert response == {'status': 'ok', 'deleted_count': 5001}
    assert len(rejected) == len(retired) == 5001
    assert rejected[-1] == 'candidate-old-05000'
    assert retired[-1] == 'old-05000'


def test_create_writes_candidate_only_with_stable_idempotency(monkeypatch):
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'create_staged_task',
        lambda *args, **kwargs: pytest.fail('new creates must not write historical staged_tasks'),
    )
    calls = []

    def create_candidate(uid, proposal, *, idempotency_key, account_generation):
        calls.append((idempotency_key, account_generation))
        return CandidateRecord(
            **proposal.model_dump(mode='python'),
            candidate_id='candidate-1',
            account_generation=account_generation,
            idempotency_key='stored-idempotency',
            created_at=NOW,
        )

    monkeypatch.setattr(staged_router.candidate_service, 'create_candidate', create_candidate)
    request = staged_router.CreateStagedTaskRequest(description='Send budget', priority='high')

    first = staged_router.create_staged_task(request, uid='user-1')
    second = staged_router.create_staged_task(request, uid='user-1')

    assert first['id'] == second['id'] == 'candidate-1'
    assert calls[0] == calls[1]
    assert calls[0][0].startswith('legacy-staged:compat-')
    assert calls[0][1] == 7


def test_historical_delete_materializes_one_then_rejects_then_retires(monkeypatch):
    row = {'id': 'old-1', 'description': 'Old task', 'completed': False, 'created_at': NOW, 'updated_at': NOW}
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'get_staged_task_for_compatibility',
        lambda uid, staged_id: row if staged_id == row['id'] else None,
    )
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'get_active_staged_tasks_for_compatibility',
        lambda uid: pytest.fail('single delete must point-read historical identity'),
    )
    monkeypatch.setattr(staged_router.candidates_db, 'get_candidate', lambda *args: None)
    candidate = _candidate('cand-old-1', row_id='old-1', description='Old task')
    events = []
    monkeypatch.setattr(
        staged_router.candidate_service,
        'create_candidate',
        lambda *args, **kwargs: events.append('materialize') or candidate,
    )
    monkeypatch.setattr(
        staged_router.candidate_service,
        'reject_candidate',
        lambda *args, **kwargs: events.append('reject'),
    )
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'delete_staged_task',
        lambda *args, **kwargs: events.append('retire') or True,
    )

    assert staged_router.delete_staged_task('old-1', uid='user-1') == {'status': 'ok'}
    assert events == ['materialize', 'reject', 'retire']


def test_historical_delete_keeps_row_when_canonical_rejection_fails(monkeypatch):
    row = {'id': 'old-1', 'description': 'Old task', 'completed': False, 'created_at': NOW, 'updated_at': NOW}
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'get_staged_task_for_compatibility',
        lambda uid, staged_id: row if staged_id == row['id'] else None,
    )
    monkeypatch.setattr(staged_router.candidates_db, 'get_candidate', lambda *args: None)
    monkeypatch.setattr(
        staged_router.candidate_service,
        'create_candidate',
        lambda *args, **kwargs: _candidate('cand-old-1', row_id='old-1', description='Old task'),
    )
    monkeypatch.setattr(
        staged_router.candidate_service,
        'reject_candidate',
        lambda *args, **kwargs: (_ for _ in ()).throw(candidates_db.CandidateConflictError('busy')),
    )
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'delete_staged_task',
        lambda *args, **kwargs: pytest.fail('historical cleanup must follow canonical success'),
    )

    with pytest.raises(HTTPException) as error:
        staged_router.delete_staged_task('old-1', uid='user-1')
    assert error.value.status_code == 409


def test_historical_promotion_accepts_candidate_before_retiring_row(monkeypatch):
    row = {'id': 'old-1', 'description': 'Old task', 'completed': False, 'created_at': NOW, 'updated_at': NOW}
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'get_staged_task_for_compatibility',
        lambda uid, staged_id: row if staged_id == row['id'] else None,
    )
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'get_active_staged_tasks_for_compatibility',
        lambda uid: pytest.fail('single promotion must point-read historical identity'),
    )
    monkeypatch.setattr(staged_router.candidates_db, 'get_candidate', lambda *args: None)
    candidate = _candidate('cand-old-1', row_id='old-1', description='Old task')
    events = []
    monkeypatch.setattr(staged_router.candidate_service, 'create_candidate', lambda *a, **k: candidate)
    monkeypatch.setattr(
        staged_router.candidate_service,
        'accept_candidate',
        lambda *args, **kwargs: events.append('accept') or type('Receipt', (), {'task_id': 'task-1'})(),
    )
    monkeypatch.setattr(
        staged_router.action_items_db,
        'get_action_item',
        lambda uid, task_id: {'id': task_id, 'description': 'Old task'},
    )
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'delete_staged_task',
        lambda *args, **kwargs: events.append('retire') or True,
    )

    result = staged_router.promote_staged_task_by_id('old-1', uid='user-1')

    assert result['promoted_task']['id'] == 'task-1'
    assert events == ['accept', 'retire']


def test_retired_migrate_and_restore_routes_are_inert(monkeypatch):
    monkeypatch.setattr(
        staged_router.staged_tasks_db,
        'restore_legacy_conversation_items',
        lambda *args, **kwargs: pytest.fail('compatibility endpoint must not bulk-migrate'),
    )

    assert staged_router.migrate_conversation_items(uid='user-1', limit=50, cursor=None)['restored'] == 0
    assert staged_router.restore_legacy_conversation_items(uid='user-1', limit=50, cursor=None) == {
        'status': 'ok',
        'restored': 0,
        'skipped_existing': 0,
        'has_more': False,
        'next_cursor': None,
    }
