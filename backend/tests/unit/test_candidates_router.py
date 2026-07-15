from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jsonschema import ValidationError as JsonSchemaValidationError, validate

import database.candidates as candidates_db
from models.candidate import CandidateCreate, CandidateRecord, CandidateResolutionReceipt, CandidateStatus
from models.task_intelligence import TaskWorkflowControl
import routers.candidates as candidates_router


def _proposal(**overrides):
    payload = {
        'subject_kind': 'task',
        'proposed_action': 'create',
        'task_change': {'description': 'Send the budget'},
        'capture_confidence': 0.8,
        'ownership_confidence': 1,
        'evidence_refs': [{'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}],
        'source_surface': 'conversation',
    }
    payload.update(overrides)
    return CandidateCreate.model_validate(payload)


def _record(*, candidate_id='candidate-1', proposal=None, created_at=None):
    return CandidateRecord(
        **(proposal or _proposal()).model_dump(mode='python'),
        candidate_id=candidate_id,
        account_generation=3,
        idempotency_key=f'idem-{candidate_id}',
        created_at=created_at or datetime(2026, 7, 9, tzinfo=timezone.utc),
    )


@pytest.fixture(scope='module')
def candidate_router_openapi():
    """Build the expensive schema once as shared file setup, not per-test work."""

    app = FastAPI()
    app.include_router(candidates_router.router)
    return app.openapi()


def test_candidate_router_publishes_complete_lifecycle_openapi(candidate_router_openapi):
    spec = candidate_router_openapi
    paths = spec['paths']

    assert set(paths['/v1/candidates']) == {'get', 'post'}
    assert set(paths['/v1/candidates/{candidate_id}']) == {'get'}
    assert set(paths['/v1/candidates/{candidate_id}/accept']) == {'post'}
    assert set(paths['/v1/candidates/{candidate_id}/reject']) == {'post'}
    assert set(paths['/v1/candidates/{candidate_id}/expire']) == {'post'}
    assert set(paths['/v1/candidates/migrate-staged']) == {'post'}
    assert set(paths['/v1/candidates/control']) == {'get'}
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
    list_parameters = paths['/v1/candidates']['get']['parameters']
    assert {'status', 'limit', 'offset', 'surface'}.issubset({parameter['name'] for parameter in list_parameters})
    candidate_schema = spec['components']['schemas']['CandidateCreate']
    assert 'oneOf' in candidate_schema
    assert candidate_schema['discriminator']['propertyName'] == 'subject_kind'
    assert candidate_schema['discriminator']['mapping'] == {
        'task': '#/components/schemas/TaskCandidate',
        'workstream': '#/components/schemas/WorkstreamCreateCandidate',
    }
    task_union = spec['components']['schemas']['TaskCandidate']
    assert task_union['discriminator']['propertyName'] == 'proposed_action'
    assert len(task_union['oneOf']) == 5
    assert len(spec['components']['schemas']['CandidateRecord']['oneOf']) == 6
    workflow_control_schema = spec['components']['schemas']['TaskWorkflowControl']
    assert 'chat_first_ui' in workflow_control_schema['properties']
    assert 'chat_first_ui_enabled' not in workflow_control_schema['properties']


def _workflow_control_client() -> TestClient:
    app = FastAPI()
    app.include_router(candidates_router.router)
    app.dependency_overrides[candidates_router.auth.get_current_user_uid] = lambda: 'user-1'
    return TestClient(app)


def test_candidate_workflow_control_exposes_composed_chat_first_ui_capability(monkeypatch):
    control = TaskWorkflowControl(workflow_mode='read', account_generation=8, chat_first_ui_enabled=True)
    monkeypatch.setattr(candidates_router.task_control_db, 'get_task_workflow_control', lambda uid: control)
    monkeypatch.setattr(
        candidates_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=True),
    )

    response = _workflow_control_client().get('/v1/candidates/control')

    assert response.status_code == 200
    assert response.json() == {
        'workflow_mode': 'read',
        'account_generation': 8,
        'chat_first_ui': True,
    }


def test_candidate_workflow_control_fails_closed_when_chat_first_composition_raises(monkeypatch):
    control = TaskWorkflowControl(workflow_mode='read', account_generation=8, chat_first_ui_enabled=True)
    monkeypatch.setattr(candidates_router.task_control_db, 'get_task_workflow_control', lambda uid: control)
    monkeypatch.setattr(
        candidates_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError('canonical selector unavailable')),
    )

    response = _workflow_control_client().get('/v1/candidates/control')

    assert response.status_code == 200
    assert response.json()['chat_first_ui'] is False
    assert 'chat_first_ui_enabled' not in response.json()


def test_candidate_workflow_control_fails_closed_when_control_lookup_raises(monkeypatch):
    def unavailable(_uid):
        raise RuntimeError('task workflow control unavailable')

    monkeypatch.setattr(candidates_router.task_control_db, 'get_task_workflow_control', unavailable)
    monkeypatch.setattr(
        candidates_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: pytest.fail('a missing control record must not attempt cohort resolution'),
    )

    response = _workflow_control_client().get('/v1/candidates/control')

    assert response.status_code == 200
    assert response.json() == {
        'workflow_mode': 'off',
        'account_generation': 0,
        'chat_first_ui': False,
    }


def test_candidate_workflow_control_defaults_chat_first_ui_off_when_the_flag_is_missing(monkeypatch):
    control = TaskWorkflowControl(workflow_mode='read', account_generation=8)
    monkeypatch.setattr(candidates_router.task_control_db, 'get_task_workflow_control', lambda uid: control)
    monkeypatch.setattr(
        candidates_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=True),
    )

    response = _workflow_control_client().get('/v1/candidates/control')

    assert response.status_code == 200
    assert response.json()['chat_first_ui'] is False
    assert 'chat_first_ui_enabled' not in response.json()


def test_candidate_workflow_control_e2e_fixture_uses_real_transport_failure(monkeypatch):
    monkeypatch.setattr(candidates_router.chat_first_e2e_fixture, 'is_control_unreachable', lambda uid: True)
    monkeypatch.setattr(
        candidates_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: pytest.fail('fixture transport failure must precede control resolution'),
    )

    response = _workflow_control_client().get('/v1/candidates/control')

    assert response.status_code == 503
    assert response.json() == {'detail': 'Control temporarily unavailable'}


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
    monkeypatch.setattr(
        candidates_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: pytest.fail('generic Candidate listing must not use the product rollout gate'),
    )

    created = candidates_router.create_candidate(
        _proposal(),
        idempotency_key='request-1',
        account_generation=3,
        uid='user-1',
    )
    listed = candidates_router.list_candidates(candidate_status=None, limit=10, offset=0, surface=None, uid='user-1')

    assert created == record
    assert calls[0][2] == {'idempotency_key': 'request-1', 'account_generation': 3}
    assert list_calls == [('user-1', {'status': None, 'account_generation': 3, 'limit': 11, 'offset': 0})]
    assert listed.candidates == [record]
    assert listed.has_more is False


def test_suggested_surface_is_hidden_when_composed_product_gate_is_disabled(monkeypatch):
    monkeypatch.setattr(
        candidates_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=3),
    )
    monkeypatch.setattr(
        candidates_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=False, account_generation=3),
    )
    monkeypatch.setattr(
        candidates_router.candidates_db,
        'list_candidates',
        lambda *args, **kwargs: pytest.fail('disabled product surface must not read Candidates'),
    )
    monkeypatch.setattr(
        candidates_router.recommendation_db,
        'list_active_override_dedupe_keys',
        lambda *args, **kwargs: pytest.fail('disabled product surface must not read attention overrides'),
    )

    with pytest.raises(HTTPException) as error:
        candidates_router.list_candidates(
            candidate_status=None,
            limit=100,
            offset=0,
            surface='suggested',
            uid='legacy-memory-user',
        )

    assert error.value.status_code == 404
    assert error.value.detail == 'Not found'


def test_suggested_surface_fails_closed_when_account_generation_changes_during_read(monkeypatch):
    current_generation = 3
    control_reads = []

    def get_control(uid):
        control_reads.append((uid, current_generation))
        return TaskWorkflowControl(workflow_mode='read', account_generation=current_generation)

    def list_candidates(uid, **kwargs):
        nonlocal current_generation
        current_generation = 4
        return [_record(candidate_id='prior-owner-private-candidate')]

    monkeypatch.setattr(candidates_router.task_control_db, 'get_task_workflow_control', get_control)
    monkeypatch.setattr(
        candidates_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(
            intelligence_product_enabled=True,
            account_generation=kwargs['account_generation'],
        ),
    )
    monkeypatch.setattr(candidates_router.candidates_db, 'list_candidates', list_candidates)
    monkeypatch.setattr(
        candidates_router.recommendation_db,
        'list_active_override_dedupe_keys',
        lambda *args, **kwargs: set(),
    )

    with pytest.raises(HTTPException) as error:
        candidates_router.list_candidates(
            candidate_status=None,
            limit=100,
            offset=0,
            surface='suggested',
            uid='canonical-user',
        )

    assert error.value.status_code == 404
    assert control_reads == [('canonical-user', 3), ('canonical-user', 4)]


@pytest.mark.parametrize('terminal_status', [CandidateStatus.accepted, CandidateStatus.rejected])
def test_terminal_exact_representative_prevents_pending_duplicate_resurrection(terminal_status):
    now = datetime.now(timezone.utc)
    proposal = _proposal(
        task_change={'description': 'Review the launch recap', 'owner': 'user'},
        capture_confidence=0.9,
        ownership_confidence=0.9,
    )
    representative = _record(candidate_id='representative', proposal=proposal, created_at=now)
    duplicate_payload = proposal.model_dump(mode='python')
    duplicate_payload.update(
        {
            'source_surface': 'screen',
            'evidence_refs': [
                {
                    'kind': 'local_screen',
                    'id': 'screen-duplicate',
                    'scope': 'device_local',
                    'device_id': 'macos_1',
                }
            ],
        }
    )
    duplicate = _record(
        candidate_id='historical-duplicate',
        proposal=CandidateCreate.model_validate(duplicate_payload),
        created_at=now - timedelta(minutes=1),
    )

    initial = candidates_router._suggested_candidates(
        [representative, duplicate],
        limit=5,
        suppressed_dedupe_keys=set(),
        now=now,
    )
    terminal_updates = {
        'status': terminal_status,
        'resolved_at': now + timedelta(seconds=1),
        'resolution_reason': terminal_status.value,
    }
    if terminal_status == CandidateStatus.accepted:
        terminal_updates['result_task_id'] = 'task-created'
    terminal_representative = CandidateRecord.model_validate(
        {**representative.model_dump(mode='python'), **terminal_updates}
    )
    after_terminal_action = candidates_router._suggested_candidates(
        [terminal_representative, duplicate],
        limit=5,
        suppressed_dedupe_keys=set(),
        now=now,
    )

    assert [candidate.candidate_id for candidate in initial] == ['representative']
    assert after_terminal_action == []


@pytest.mark.parametrize('terminal_status', [CandidateStatus.accepted, CandidateStatus.rejected])
def test_new_exact_occurrence_after_terminal_resolution_can_be_suggested(terminal_status):
    now = datetime.now(timezone.utc)
    proposal = _proposal(
        task_change={'description': 'Review the launch recap', 'owner': 'user'},
        capture_confidence=0.9,
        ownership_confidence=0.9,
    )
    resolved_at = now - timedelta(days=1)
    terminal_payload = {
        **_record(
            candidate_id='prior-occurrence',
            proposal=proposal,
            created_at=resolved_at - timedelta(minutes=1),
        ).model_dump(mode='python'),
        'status': terminal_status,
        'resolved_at': resolved_at,
        'resolution_reason': terminal_status.value,
    }
    if terminal_status == CandidateStatus.accepted:
        terminal_payload['result_task_id'] = 'completed-prior-task'
    terminal = CandidateRecord.model_validate(terminal_payload)
    next_occurrence = _record(
        candidate_id='next-occurrence',
        proposal=proposal,
        created_at=resolved_at + timedelta(hours=1),
    )

    projection = candidates_router._suggested_candidates(
        [next_occurrence, terminal],
        limit=5,
        suppressed_dedupe_keys=set(),
        now=now,
    )

    assert [candidate.candidate_id for candidate in projection] == ['next-occurrence']


def test_active_override_suppresses_fresh_duplicate_of_old_terminal_candidate():
    now = datetime.now(timezone.utc)
    proposal = _proposal(
        task_change={'description': 'Review the launch recap', 'owner': 'user'},
        capture_confidence=0.9,
        ownership_confidence=0.9,
    )
    old_terminal = CandidateRecord.model_validate(
        {
            **_record(
                candidate_id='old-representative',
                proposal=proposal,
                created_at=now - timedelta(days=20),
            ).model_dump(mode='python'),
            'status': CandidateStatus.rejected,
            'resolved_at': now - timedelta(days=19),
            'resolution_reason': 'dismissed',
        }
    )
    fresh_duplicate = _record(
        candidate_id='fresh-duplicate',
        proposal=proposal,
        created_at=now - timedelta(minutes=1),
    )

    projection = candidates_router._suggested_candidates(
        [fresh_duplicate, old_terminal],
        limit=5,
        suppressed_dedupe_keys={candidates_router.candidate_recommendation_dedupe_key('old-representative')},
        now=now,
    )

    assert projection == []


def test_suggested_surface_returns_five_quality_candidates_and_suppresses_exact_semantic_groups(monkeypatch):
    now = datetime.now(timezone.utc)
    eligible = [
        _record(
            candidate_id=f'eligible-{index}',
            proposal=_proposal(
                task_change={'description': f'Useful task {index}', 'owner': 'user'},
                capture_confidence=0.9,
                ownership_confidence=0.9,
            ),
            created_at=now - timedelta(minutes=index),
        )
        for index in range(6)
    ]
    eligible[4] = _record(
        candidate_id='eligible-4',
        proposal=CandidateCreate.model_validate(
            {
                'subject_kind': 'workstream',
                'proposed_action': 'create',
                'workstream_proposal': {
                    'title': 'Launch follow-up',
                    'objective': 'Close the launch feedback loop',
                    'anchor_task': {'description': 'Review launch feedback'},
                },
                'capture_confidence': 0.9,
                'ownership_confidence': 0.9,
                'evidence_refs': [{'kind': 'conversation', 'id': 'conversation-4', 'scope': 'canonical'}],
                'source_surface': 'conversation',
            }
        ),
        created_at=now - timedelta(minutes=4),
    )
    duplicate_workstream = _record(
        candidate_id='duplicate-workstream',
        proposal=CandidateCreate.model_validate(
            {
                'subject_kind': 'workstream',
                'proposed_action': 'create',
                'workstream_proposal': {
                    'title': 'Launch follow-up',
                    'objective': 'Close the launch feedback loop',
                    'anchor_task': {'description': 'Review launch feedback'},
                },
                'capture_confidence': 0.95,
                'ownership_confidence': 0.9,
                'evidence_refs': [
                    {
                        'kind': 'local_screen',
                        'id': 'screen-workstream-4',
                        'scope': 'device_local',
                        'device_id': 'macos_4',
                    }
                ],
                'source_surface': 'screen',
            }
        ),
        created_at=now - timedelta(minutes=3, seconds=30),
    )
    duplicate = _record(
        candidate_id='duplicate-of-newest',
        proposal=_proposal(
            task_change={'description': 'Useful task 0', 'owner': 'user'},
            capture_confidence=0.95,
            ownership_confidence=0.95,
            source_surface='screen',
            evidence_refs=[{'kind': 'conversation', 'id': 'conversation-2', 'scope': 'canonical'}],
        ),
        created_at=now - timedelta(seconds=30),
    )
    mutation = _record(
        candidate_id='mutation',
        proposal=_proposal(
            proposed_action='update',
            task_id='task-1',
            task_change={'description': 'Mutated task'},
            capture_confidence=0.95,
            ownership_confidence=0.95,
        ),
        created_at=now,
    )
    stale = _record(candidate_id='stale', created_at=now - timedelta(days=15))
    weak = _record(
        candidate_id='weak',
        proposal=_proposal(capture_confidence=0.79, ownership_confidence=1),
        created_at=now,
    )
    weak_ownership = _record(
        candidate_id='weak-ownership',
        proposal=_proposal(capture_confidence=0.95, ownership_confidence=0.79),
        created_at=now,
    )
    without_evidence = _record(candidate_id='without-evidence', created_at=now).model_copy(update={'evidence_refs': []})
    calls = []
    override_calls = []
    monkeypatch.setattr(
        candidates_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=3),
    )
    monkeypatch.setattr(
        candidates_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=True, account_generation=3),
    )
    monkeypatch.setattr(
        candidates_router.candidates_db,
        'list_candidates',
        lambda uid, **kwargs: calls.append((uid, kwargs))
        or [
            stale,
            eligible[5],
            mutation,
            duplicate_workstream,
            duplicate,
            eligible[2],
            weak,
            *eligible[:2],
            without_evidence,
            weak_ownership,
            *eligible[3:5],
        ],
    )
    monkeypatch.setattr(
        candidates_router.recommendation_db,
        'list_active_override_dedupe_keys',
        lambda uid, **kwargs: override_calls.append((uid, kwargs))
        or {candidates_router.candidate_recommendation_dedupe_key('duplicate-workstream')},
    )

    response = candidates_router.list_candidates(
        candidate_status=CandidateStatus.accepted,
        limit=100,
        offset=200,
        surface='suggested',
        uid='canonical-user',
    )

    assert calls == [
        (
            'canonical-user',
            {
                'status': None,
                'account_generation': 3,
                'limit': candidates_router.SUGGESTED_CANDIDATE_RAW_LIMIT,
                'offset': 0,
            },
        )
    ]
    assert [candidate.candidate_id for candidate in response.candidates] == [
        'eligible-0',
        'eligible-1',
        'eligible-2',
        'eligible-3',
        'eligible-5',
    ]
    assert override_calls[0][0] == 'canonical-user'
    assert override_calls[0][1]['account_generation'] == 3
    assert isinstance(override_calls[0][1]['now'], datetime)
    assert response.has_more is False


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
