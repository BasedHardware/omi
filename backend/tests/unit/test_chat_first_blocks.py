from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.task_intelligence import TaskWorkflowControl
import routers.chat_first as chat_first_router
from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(chat_first_router.router)
    app.dependency_overrides[chat_first_router.auth.get_current_user_uid] = lambda: 'user-1'
    return TestClient(app)


def _enable_chat_first(monkeypatch, *, generation: int = 7) -> None:
    set_canonical_cohort(monkeypatch, 'user-1')
    monkeypatch.setattr(
        chat_first_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(
            workflow_mode='read', account_generation=generation, chat_first_ui_enabled=True
        ),
    )
    monkeypatch.setattr(
        chat_first_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=True),
    )


def _request(*, generation: int = 7, blocks: list[dict] | None = None) -> dict:
    return {
        'source_surface': 'main_chat',
        'control_generation': generation,
        'owner_fence': 'user-1',
        'run_id': 'run-1',
        'attempt_id': 'attempt-1',
        'blocks': blocks or [{'type': 'taskCard', 'task_id': 'task-1'}],
    }


def test_chat_first_validate_admits_canonical_blocks_with_retry_stable_ids(monkeypatch):
    _enable_chat_first(monkeypatch)
    monkeypatch.setattr(chat_first_router.action_items_db, 'get_action_item', lambda uid, task_id: {'id': task_id})

    client = _client()
    first = client.post('/v1/chat-first/blocks/validate', json=_request())
    second = client.post('/v1/chat-first/blocks/validate', json=_request())

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()['accepted'] is True
    assert first.json()['code'] == 'accepted'
    assert first.json()['blocks'][0] == {
        'id': first.json()['blocks'][0]['id'],
        'type': 'taskCard',
        'task_id': 'task-1',
    }
    assert first.json()['blocks'][0]['id'].startswith('cfb_')


def test_chat_first_validate_rejects_the_entire_receipt_when_any_reference_is_unavailable(monkeypatch):
    _enable_chat_first(monkeypatch)
    monkeypatch.setattr(
        chat_first_router.action_items_db,
        'get_action_item',
        lambda uid, task_id: {'id': task_id} if task_id == 'task-1' else None,
    )

    response = _client().post(
        '/v1/chat-first/blocks/validate',
        json=_request(
            blocks=[
                {'type': 'taskCard', 'task_id': 'task-1'},
                {'type': 'taskCard', 'task_id': 'missing-task'},
            ]
        ),
    )

    assert response.status_code == 200
    assert response.json() == {'accepted': False, 'code': 'entity_unavailable', 'blocks': []}


def test_chat_first_validate_fails_closed_before_entity_resolution_outside_the_cohort(monkeypatch):
    monkeypatch.setattr(
        chat_first_router.task_control_db,
        'get_task_workflow_control',
        lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=7, chat_first_ui_enabled=False),
    )
    monkeypatch.setattr(
        chat_first_router,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=False),
    )
    monkeypatch.setattr(
        chat_first_router.action_items_db,
        'get_action_item',
        lambda *args: (_ for _ in ()).throw(AssertionError('entity resolution must not run when capability is off')),
    )

    response = _client().post('/v1/chat-first/blocks/validate', json=_request())

    assert response.status_code == 200
    assert response.json() == {'accepted': False, 'code': 'capability_unavailable', 'blocks': []}


def test_chat_first_validate_rejects_a_stale_owner_fence_before_any_entity_read(monkeypatch):
    _enable_chat_first(monkeypatch)
    monkeypatch.setattr(
        chat_first_router.action_items_db,
        'get_action_item',
        lambda *args: (_ for _ in ()).throw(AssertionError('stale owner must not resolve entities')),
    )

    response = _client().post(
        '/v1/chat-first/blocks/validate',
        json={**_request(), 'owner_fence': 'another-user'},
    )

    assert response.status_code == 200
    assert response.json() == {'accepted': False, 'code': 'capability_unavailable', 'blocks': []}


def test_chat_first_validate_returns_a_typed_rejection_for_malformed_block_schema(monkeypatch):
    _enable_chat_first(monkeypatch)
    monkeypatch.setattr(
        chat_first_router.action_items_db,
        'get_action_item',
        lambda *args: (_ for _ in ()).throw(AssertionError('malformed input must not resolve entities')),
    )

    response = _client().post(
        '/v1/chat-first/blocks/validate',
        json=_request(blocks=[{'type': 'taskCard'}]),
    )

    assert response.status_code == 200
    assert response.json() == {'accepted': False, 'code': 'invalid_request', 'blocks': []}
