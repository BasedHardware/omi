import os

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

import routers.goals as goals_router
import routers.task_recommendations as task_recommendations_router
import routers.workstreams as workstreams_router
from models.goal import GoalCreate, GoalFocusRequest, GoalUpdate
from models.workstream import TaskOriginWorkIntent, WorkIntentReceipt, WorkstreamUpdate


def test_openapi_exposes_intent_and_thread_resources_without_manual_workstream_create():
    app = FastAPI()
    app.include_router(goals_router.router)
    app.include_router(task_recommendations_router.router)
    app.include_router(workstreams_router.router)
    schema = app.openapi()

    assert '/v1/work-intents' in schema['paths']
    assert '/v1/workstreams/{workstream_id}' in schema['paths']
    assert 'post' not in schema['paths']['/v1/workstreams/{workstream_id}']
    assert '/v1/workstreams' not in schema['paths']
    assert 'target_value' not in schema['components']['schemas']['GoalCreate'].get('required', [])
    assert 'metric' in schema['components']['schemas']['GoalResponse']['properties']
    request_schema = schema['paths']['/v1/work-intents']['post']['requestBody']['content']['application/json']['schema']
    assert request_schema['discriminator']['propertyName'] == 'origin'
    canonical_writes = [
        ('/v1/goals/canonical', 'post'),
        ('/v1/goals/{goal_id}/focus', 'post'),
        ('/v1/goals/{goal_id}/focus', 'delete'),
        ('/v1/goals/{goal_id}/lifecycle', 'post'),
        ('/v1/goals/{goal_id}/progress-events', 'post'),
        ('/v1/work-intents', 'post'),
        ('/v1/workstreams/{workstream_id}', 'patch'),
        ('/v1/workstreams/{workstream_id}/events', 'post'),
        ('/v1/workstreams/{workstream_id}/artifacts', 'post'),
        ('/v1/workstreams/{workstream_id}/artifacts/{artifact_id}/status', 'patch'),
        ('/v1/workstreams/{workstream_id}/checkpoints/{runtime_id}', 'put'),
        ('/v1/workflow-migrations/task-goal-links', 'post'),
        ('/v1/task-intelligence/interventions', 'post'),
        ('/v1/task-intelligence/feedback', 'post'),
        ('/v1/task-intelligence/outcomes', 'post'),
    ]
    for path, method in canonical_writes:
        headers = {
            parameter['name']: parameter
            for parameter in schema['paths'][path][method].get('parameters', [])
            if parameter.get('in') == 'header'
        }
        assert headers['Idempotency-Key']['required'] is True
        assert headers['X-Account-Generation']['required'] is True


def test_task_intelligence_mutations_reject_stale_account_generation(monkeypatch):
    monkeypatch.setattr(
        task_recommendations_router,
        '_rollout',
        lambda _uid: SimpleNamespace(intelligence_product_enabled=True, account_generation=8),
    )

    with pytest.raises(HTTPException) as error:
        task_recommendations_router._require_mutation_generation('u1', 7)

    assert error.value.status_code == 409
    assert error.value.detail == 'account generation mismatch'


def _device_request(*, device_hash: str = 'abcdef12') -> Request:
    return Request(
        {
            'type': 'http',
            'method': 'GET',
            'scheme': 'https',
            'path': '/v1/what-matters-now',
            'query_string': b'',
            'headers': [(b'x-app-platform', b'macos'), (b'x-device-id-hash', device_hash.encode())],
            'server': ('testserver', 443),
            'client': ('testclient', 1234),
        }
    )


@pytest.mark.parametrize('requested_device_id', ['abcdef12', 'macos_abcdef12'])
def test_task_intelligence_device_scope_accepts_only_authenticated_legacy_aliases(requested_device_id):
    assert (
        task_recommendations_router._bound_device_id(_device_request(), requested_device_id, required=False)
        == 'macos_abcdef12'
    )


def test_task_intelligence_device_scope_rejects_another_device():
    with pytest.raises(HTTPException) as error:
        task_recommendations_router._bound_device_id(_device_request(), 'macos_deadbeef', required=False)

    assert error.value.status_code == 403
    assert error.value.detail == 'Device scope mismatch'


@pytest.mark.parametrize('surface', ['get', 'evaluate', 'debug'])
def test_task_intelligence_reads_fail_closed_when_generation_changes_during_projection_read(monkeypatch, surface):
    generations = iter([3, 4])
    projection_reads = []
    monkeypatch.setattr(
        task_recommendations_router,
        '_rollout',
        lambda _uid: SimpleNamespace(
            intelligence_product_enabled=True,
            account_generation=next(generations),
        ),
    )
    monkeypatch.setattr(task_recommendations_router, '_bound_device_id', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        task_recommendations_router.recommendations,
        'evaluate',
        lambda *args, **kwargs: projection_reads.append('evaluate') or object(),
    )
    monkeypatch.setattr(
        task_recommendations_router.recommendations,
        'get_debug_projection',
        lambda *args, **kwargs: projection_reads.append('debug') or object(),
    )

    with pytest.raises(HTTPException) as error:
        if surface == 'get':
            task_recommendations_router.get_what_matters_now(
                request_context=object(),
                device_id=None,
                uid='u1',
            )
        elif surface == 'evaluate':
            task_recommendations_router.evaluate_what_matters_now(
                request=task_recommendations_router.EvaluationRequest(),
                request_context=object(),
                uid='u1',
            )
        else:
            task_recommendations_router.get_evaluation_debug_projection(
                request_context=object(),
                evaluation_id='evaluation-old-generation',
                x_omi_debug=True,
                device_id=None,
                uid='u1',
            )

    assert error.value.status_code == 404
    assert projection_reads == ['debug' if surface == 'debug' else 'evaluate']


def test_qualitative_goal_create_forwards_canonical_shape_without_numeric_defaults(monkeypatch):
    captured = {}

    def create(uid, payload):
        captured.update(payload)
        now = datetime.now(timezone.utc)
        return {
            **payload,
            'goal_id': payload['id'],
            'status': 'background',
            'source': 'user',
            'is_active': True,
            'latest_progress_sequence': 0,
            'created_at': now,
            'updated_at': now,
        }

    monkeypatch.setattr(goals_router.goals_db, 'create_goal', create)
    result = goals_router.create_goal(
        GoalCreate(
            title='Launch desktop',
            desired_outcome='Ship a trustworthy release',
            why_it_matters='Users rely on it',
            success_criteria=['Signed build ships'],
        ),
        uid='u1',
    )

    assert captured['desired_outcome'] == 'Ship a trustworthy release'
    assert 'metric' not in captured
    assert result['metric'] is None
    assert result['target_value'] == 0


def test_all_goals_preserves_active_default_and_can_include_unbounded_history(monkeypatch):
    expected = [{'goal_id': f'g{index}'} for index in range(125)]
    captured = {}

    def get_all(uid, include_inactive=False):
        captured.update(uid=uid, include_inactive=include_inactive)
        return expected

    monkeypatch.setattr(goals_router.goals_db, 'get_all_goals', get_all)
    monkeypatch.setattr(goals_router, 'normalize_goal_response', lambda goal: goal)

    assert goals_router.get_all_goals(include_ended=False, uid='u1') == expected
    assert captured == {'uid': 'u1', 'include_inactive': False}
    assert goals_router.get_all_goals(include_ended=True, uid='u1') == expected
    assert captured == {'uid': 'u1', 'include_inactive': True}


def test_goal_update_rejects_null_required_fields():
    with pytest.raises(ValueError):
        GoalUpdate.model_validate({'title': None})
    with pytest.raises(ValueError):
        GoalUpdate.model_validate({'desired_outcome': None})
    with pytest.raises(ValueError):
        GoalUpdate.model_validate({'success_criteria': None})
    with pytest.raises(ValueError):
        GoalUpdate.model_validate({'target_value': None})
    with pytest.raises(ValueError):
        GoalUpdate.model_validate({'current_value': None})


def test_workstream_update_rejects_empty_or_null_required_fields_and_allows_clearing_review_time():
    with pytest.raises(ValueError):
        WorkstreamUpdate.model_validate({})
    with pytest.raises(ValueError):
        WorkstreamUpdate.model_validate({'title': None})
    clear = WorkstreamUpdate.model_validate({'next_review_at': None})
    assert clear.model_dump(exclude_unset=True) == {'next_review_at': None}


def test_focus_overflow_maps_to_conflict(monkeypatch):
    monkeypatch.setattr(
        goals_router.goals_db,
        'focus_goal',
        lambda *args, **kwargs: (_ for _ in ()).throw(goals_router.goals_db.GoalConflictError('focus full')),
    )

    with pytest.raises(HTTPException) as error:
        goals_router.focus_goal(
            'g6',
            GoalFocusRequest(),
            idempotency_key='focus-g6',
            account_generation=3,
            uid='u1',
        )

    assert error.value.status_code == 409
    assert error.value.detail == 'focus full'


def test_work_intent_route_forwards_idempotency_and_generation(monkeypatch):
    captured = {}
    receipt = WorkIntentReceipt(
        receipt_id='receipt-1',
        workstream_id='w1',
        task_id='t1',
        newly_created=True,
        created_at=datetime.now(timezone.utc),
    )

    def resolve(uid, request, **kwargs):
        captured.update(uid=uid, request=request, **kwargs)
        return receipt

    monkeypatch.setattr(workstreams_router.workstreams_db, 'resolve_work_intent', resolve)
    refreshed = []
    monkeypatch.setattr(
        workstreams_router,
        'refresh_workstream_association_index',
        lambda uid, workstream_id: refreshed.append((uid, workstream_id)),
    )
    result = workstreams_router.resolve_work_intent(
        TaskOriginWorkIntent(task_id='t1'),
        idempotency_key='click-1',
        account_generation=7,
        uid='u1',
    )

    assert result == receipt
    assert captured['idempotency_key'] == 'click-1'
    assert captured['account_generation'] == 7
    assert refreshed == [('u1', 'w1')]
