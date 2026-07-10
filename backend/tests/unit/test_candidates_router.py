from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from jsonschema import ValidationError as JsonSchemaValidationError, validate

import database.candidates as candidates_db
from models.candidate import CandidateCreate, CandidateRecord, CandidateResolutionReceipt
from models.task_intelligence import TaskWorkflowControl
import routers.candidates as candidates_router


def _proposal():
    return CandidateCreate.model_validate(
        {
            'subject_kind': 'task',
            'proposed_action': 'create',
            'task_change': {'description': 'Send the budget'},
            'capture_confidence': 0.8,
            'ownership_confidence': 1,
            'evidence_refs': [{'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}],
            'source_surface': 'conversation',
        }
    )


def _record():
    return CandidateRecord(
        **_proposal().model_dump(mode='python'),
        candidate_id='candidate-1',
        account_generation=3,
        idempotency_key='idem-1',
        created_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
    )


def test_candidate_router_publishes_complete_lifecycle_openapi():
    app = FastAPI()
    app.include_router(candidates_router.router)
    paths = app.openapi()['paths']

    assert set(paths['/v1/candidates']) == {'get', 'post'}
    assert set(paths['/v1/candidates/{candidate_id}']) == {'get'}
    assert set(paths['/v1/candidates/{candidate_id}/accept']) == {'post'}
    assert set(paths['/v1/candidates/{candidate_id}/reject']) == {'post'}
    assert set(paths['/v1/candidates/{candidate_id}/expire']) == {'post'}
    assert set(paths['/v1/candidates/migrate-staged']) == {'post'}
    assert set(paths['/v1/candidates/integrations/drain']) == {'post'}
    create_parameters = paths['/v1/candidates']['post']['parameters']
    required_contract_headers = {
        (parameter['name'], parameter['in'], parameter.get('required'))
        for parameter in create_parameters
        if parameter['name'] in {'Idempotency-Key', 'X-Account-Generation'}
    }
    assert required_contract_headers == {
        ('Idempotency-Key', 'header', True),
        ('X-Account-Generation', 'header', True),
    }
    candidate_schema = app.openapi()['components']['schemas']['CandidateCreate']
    assert 'oneOf' in candidate_schema
    assert candidate_schema['discriminator']['propertyName'] == 'subject_kind'
    assert candidate_schema['discriminator']['mapping'] == {
        'task': '#/components/schemas/TaskCandidate',
        'workstream': '#/components/schemas/WorkstreamCreateCandidate',
    }
    task_union = app.openapi()['components']['schemas']['TaskCandidate']
    assert task_union['discriminator']['propertyName'] == 'proposed_action'
    assert len(task_union['oneOf']) == 5
    assert len(app.openapi()['components']['schemas']['CandidateRecord']['oneOf']) == 6


def test_candidate_record_serialization_satisfies_its_response_schema():
    validate(_record().model_dump(mode='json'), CandidateRecord.model_json_schema())


@pytest.mark.parametrize(
    'patch',
    [
        {'task_change': {'status': 'completed'}},
        {
            'proposed_action': 'complete',
            'task_id': 'task-1',
            'task_change': {'description': 'Send the budget'},
        },
        {
            'proposed_action': 'supersede',
            'task_id': 'task-1',
            'task_change': {'status': 'superseded'},
        },
    ],
)
def test_candidate_record_response_schema_rejects_payloads_runtime_rejects(patch):
    payload = _record().model_dump(mode='json')
    payload.update(patch)

    with pytest.raises(JsonSchemaValidationError):
        validate(payload, CandidateRecord.model_json_schema())


def test_accept_maps_task_link_validation_to_conflict(monkeypatch):
    monkeypatch.setattr(
        candidates_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=3),
    )
    monkeypatch.setattr(
        candidates_router.candidate_service,
        'accept_candidate',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            candidates_router.TaskLinkValidationError('workstream and goal do not match')
        ),
    )

    with pytest.raises(HTTPException) as error:
        candidates_router.accept_candidate('candidate-1', account_generation=3, uid='user-1')

    assert error.value.status_code == 409
    assert error.value.detail == 'workstream and goal do not match'


def test_create_and_list_candidate_router_forward_idempotency_and_pagination(monkeypatch):
    calls = []
    list_calls = []
    record = _record()
    monkeypatch.setattr(
        candidates_router.candidate_service,
        'create_candidate',
        lambda uid, proposal, **kwargs: calls.append((uid, proposal, kwargs)) or record,
    )
    monkeypatch.setattr(
        candidates_router.candidates_db,
        'list_candidates',
        lambda uid, **kwargs: list_calls.append((uid, kwargs)) or [record],
    )
    monkeypatch.setattr(
        candidates_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=3),
    )

    created = candidates_router.create_candidate(
        _proposal(),
        idempotency_key='request-1',
        account_generation=3,
        uid='user-1',
    )
    listed = candidates_router.list_candidates(candidate_status=None, limit=10, offset=0, uid='user-1')

    assert created == record
    assert calls[0][2] == {'idempotency_key': 'request-1', 'account_generation': 3}
    assert list_calls == [('user-1', {'status': None, 'account_generation': 3, 'limit': 11, 'offset': 0})]
    assert listed.candidates == [record]
    assert listed.has_more is False


def test_candidate_point_read_hides_old_account_generation(monkeypatch):
    monkeypatch.setattr(candidates_router.candidates_db, 'get_candidate', lambda uid, candidate_id: _record())
    monkeypatch.setattr(
        candidates_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=4),
    )

    with pytest.raises(HTTPException) as error:
        candidates_router.get_candidate('candidate-1', uid='user-1')

    assert error.value.status_code == 404


@pytest.mark.parametrize(
    ('exception', 'expected_status'),
    [
        (candidates_db.CandidateNotFoundError('x'), 404),
        (candidates_db.CandidateGenerationMismatchError('x'), 409),
        (candidates_db.CandidateConflictError('x'), 409),
        (candidates_db.WorkstreamCandidateResolverUnavailableError('x'), 409),
    ],
)
def test_candidate_router_maps_store_errors_without_leaking_content(monkeypatch, exception, expected_status):
    monkeypatch.setattr(
        candidates_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=3),
    )
    monkeypatch.setattr(
        candidates_router.candidate_service,
        'accept_candidate',
        lambda *args, **kwargs: (_ for _ in ()).throw(exception),
    )

    with pytest.raises(HTTPException) as error:
        candidates_router.accept_candidate('candidate-1', account_generation=3, uid='user-1')

    assert error.value.status_code == expected_status


def test_accept_reject_and_expire_return_stable_receipts(monkeypatch):
    now = datetime(2026, 7, 9, tzinfo=timezone.utc)
    receipts = {
        'accept': CandidateResolutionReceipt(
            candidate_id='candidate-1',
            status='accepted',
            receipt_id='receipt-accept',
            task_id='task-1',
            newly_resolved=True,
            resolved_at=now,
        ),
        'reject': CandidateResolutionReceipt(
            candidate_id='candidate-1',
            status='rejected',
            receipt_id='receipt-reject',
            newly_resolved=True,
            resolved_at=now,
        ),
        'expire': CandidateResolutionReceipt(
            candidate_id='candidate-1',
            status='expired',
            receipt_id='receipt-expire',
            newly_resolved=True,
            resolved_at=now,
        ),
    }
    monkeypatch.setattr(
        candidates_router.candidate_service, 'accept_candidate', lambda *args, **kwargs: receipts['accept']
    )
    monkeypatch.setattr(
        candidates_router.candidate_service, 'reject_candidate', lambda *args, **kwargs: receipts['reject']
    )
    monkeypatch.setattr(
        candidates_router.candidate_service, 'expire_candidate', lambda *args, **kwargs: receipts['expire']
    )
    monkeypatch.setattr(
        candidates_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=3),
    )
    request = candidates_router.CandidateResolutionRequest(reason='not_mine')

    assert candidates_router.accept_candidate('candidate-1', account_generation=3, uid='user-1').task_id == 'task-1'
    assert (
        candidates_router.reject_candidate('candidate-1', request, account_generation=3, uid='user-1').status
        == 'rejected'
    )
    assert (
        candidates_router.expire_candidate('candidate-1', request, account_generation=3, uid='user-1').status
        == 'expired'
    )


@pytest.mark.parametrize(
    ('control', 'generation'),
    [
        (TaskWorkflowControl(workflow_mode='off', account_generation=3), 3),
        (TaskWorkflowControl(workflow_mode='shadow', account_generation=3), 3),
        (TaskWorkflowControl(workflow_mode='read', account_generation=4), 3),
    ],
)
def test_candidate_router_rejects_disabled_or_stale_writes(monkeypatch, control, generation):
    monkeypatch.setattr(candidates_router.task_control_db, 'get_task_workflow_control', lambda uid: control)
    monkeypatch.setattr(
        candidates_router.candidate_service,
        'create_candidate',
        lambda *args, **kwargs: pytest.fail('disabled or stale writes must not reach persistence'),
    )

    with pytest.raises(HTTPException) as error:
        candidates_router.create_candidate(
            _proposal(),
            idempotency_key='request-1',
            account_generation=generation,
            uid='user-1',
        )

    assert error.value.status_code == 409
