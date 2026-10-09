"""Registered action-item HTTP routes reconcile saved canonical reminder state."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import action_items
from tests.unit.test_action_item_reminder_state_notifications import configure_reminder_transports

DUE = datetime(2027, 1, 15, 9, 0, tzinfo=timezone.utc)
TEST_UID = 'reminder-http-test-user'


class ReminderMemoryRepository:
    """Synthetic per-test durable state, including saved-state idempotent replay."""

    def __init__(self):
        self.rows = {}
        self.idempotency = {}
        self.created = []
        self.updated = []

    def get(self, uid, task_id):
        assert uid == TEST_UID
        return deepcopy(self.rows.get(task_id))

    def create(self, uid, payload, idempotency_key=None):
        assert uid == TEST_UID
        if idempotency_key and idempotency_key in self.idempotency:
            return self.idempotency[idempotency_key]
        task_id = f'task-{len(self.created) + 1}'
        self.rows[task_id] = {'id': task_id, **deepcopy(payload)}
        self.created.append(task_id)
        if idempotency_key:
            self.idempotency[idempotency_key] = task_id
        return task_id

    def create_batch(self, uid, payloads):
        return [self.create(uid, payload) for payload in payloads]

    def update(self, uid, task_id, payload):
        assert uid == TEST_UID
        if task_id not in self.rows:
            return False
        self.rows[task_id].update(deepcopy(payload))
        self.updated.append((task_id, deepcopy(payload)))
        return True

    def mark_completed(self, uid, task_id, completed):
        return self.update(uid, task_id, {'completed': completed, 'status': 'completed' if completed else 'active'})

    def seed(self, task_id, *, status='active', completed=False, due_at=DUE, deleted=False):
        self.rows[task_id] = {
            'id': task_id,
            'description': f'Synthetic {task_id}',
            'completed': completed,
            'status': status,
            'due_at': due_at,
            'deleted': deleted,
            'source': 'manual',
        }


def build_reminder_test_app(monkeypatch, *, expose_effects=False):
    """Reusable local HTTP smoke fixture; never initializes DB or delivery clients."""
    repo = ReminderMemoryRepository()
    transports = configure_reminder_transports(monkeypatch)
    monkeypatch.setattr(action_items.action_items_db, 'create_action_item', repo.create)
    monkeypatch.setattr(action_items.action_items_db, 'create_action_items_batch', repo.create_batch)
    monkeypatch.setattr(action_items.action_items_db, 'get_action_item', repo.get)
    monkeypatch.setattr(action_items.action_items_db, 'update_action_item', repo.update)
    monkeypatch.setattr(action_items.action_items_db, 'mark_action_item_completed', repo.mark_completed)
    monkeypatch.setattr(action_items.task_links, 'validate_task_links', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(action_items, 'upsert_action_item_vector', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(action_items, 'upsert_action_item_vectors_batch', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(action_items, 'submit_with_context', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(action_items, 'record_product_event', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(action_items, 'emit_product_event', lambda *_args, **_kwargs: None)
    app = FastAPI()
    app.include_router(action_items.router)
    app.dependency_overrides[action_items.auth.get_current_user_uid] = lambda: TEST_UID

    if expose_effects:

        @app.get('/__test__/reminder-effects')
        def reminder_effects():
            return {'fcm': transports.fcm, 'queued': transports.queued, 'created_ids': repo.created}

        @app.post('/__test__/reminder-effects/reset')
        def reset_reminder_effects():
            transports.fcm.clear()
            transports.queued.clear()
            return {'status': 'ok'}

    return SimpleNamespace(app=app, repo=repo, fcm=transports.fcm, queued=transports.queued)


@pytest.fixture
def scenario(monkeypatch):
    fixture = build_reminder_test_app(monkeypatch)
    with TestClient(fixture.app) as client:
        fixture.client = client
        yield fixture


def _armed_ids(scenario):
    return [
        call['data']['action_item_id']
        for call in scenario.fcm
        if call['data']['type'] in {'action_item_reminder', 'action_item_update'}
    ]


def _cancelled_ids(scenario):
    return [call['data']['action_item_id'] for call in scenario.fcm if call['data']['type'] == 'action_item_delete']


@pytest.mark.parametrize('status', ['cancelled', 'superseded'])
def test_status_only_patch_cancels_instead_of_rearming_an_open_dated_task(scenario, status):
    scenario.repo.seed('task-1')

    response = scenario.client.patch('/v1/action-items/task-1', json={'status': status})

    assert response.status_code == 200
    assert response.json()['status'] == status
    assert response.json()['completed'] is False
    assert _armed_ids(scenario) == []
    assert _cancelled_ids(scenario) == ['task-1']
    assert scenario.queued == []


@pytest.mark.parametrize('status', ['cancelled', 'superseded'])
def test_terminal_post_never_arms_a_dated_task(scenario, status):
    response = scenario.client.post(
        '/v1/action-items',
        json={'description': 'Retired task', 'status': status, 'due_at': DUE.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()['status'] == status
    assert response.json()['completed'] is False
    assert _armed_ids(scenario) == []
    assert scenario.queued == []


def test_mixed_batch_arms_only_saved_active_incomplete_dated_tasks(scenario):
    response = scenario.client.post(
        '/v1/action-items/batch',
        json=[
            {'description': 'Active dated', 'status': 'active', 'due_at': DUE.isoformat()},
            {'description': 'Cancelled dated', 'status': 'cancelled', 'due_at': DUE.isoformat()},
            {'description': 'Superseded dated', 'status': 'superseded', 'due_at': DUE.isoformat()},
            {'description': 'Completed dated', 'status': 'completed', 'due_at': DUE.isoformat()},
            {'description': 'Active undated', 'status': 'active'},
        ],
    )

    assert response.status_code == 200
    assert response.json()['created_count'] == 5
    assert _armed_ids(scenario) == ['task-1']
    assert [call['payload']['task_id'] for call in scenario.queued] == ['task-1']


@pytest.mark.parametrize('status', ['cancelled', 'superseded'])
def test_keyed_create_replay_uses_saved_terminal_state_not_the_stale_active_request(scenario, status):
    payload = {'description': 'Initial task', 'due_at': DUE.isoformat(), 'status': 'active'}
    first = scenario.client.post('/v1/action-items', json=payload, headers={'Idempotency-Key': 'request-1'})
    assert first.status_code == 200
    task_id = first.json()['id']
    scenario.repo.rows[task_id].update({'status': status, 'completed': False, 'description': 'Saved terminal title'})
    scenario.fcm.clear()
    scenario.queued.clear()

    replay = scenario.client.post('/v1/action-items', json=payload, headers={'Idempotency-Key': 'request-1'})

    assert replay.status_code == 200
    assert replay.json()['id'] == task_id
    assert replay.json()['description'] == 'Saved terminal title'
    assert replay.json()['status'] == status
    assert scenario.repo.created == [task_id]
    assert _armed_ids(scenario) == []
    assert scenario.queued == []


def test_saved_legacy_deleted_marker_prevents_replay_arming_even_with_active_status(scenario):
    payload = {'description': 'Initial task', 'due_at': DUE.isoformat(), 'status': 'active'}
    first = scenario.client.post('/v1/action-items', json=payload, headers={'Idempotency-Key': 'request-1'})
    assert first.status_code == 200
    task_id = first.json()['id']
    scenario.repo.rows[task_id]['deleted'] = True
    scenario.fcm.clear()
    scenario.queued.clear()

    replay = scenario.client.post('/v1/action-items', json=payload, headers={'Idempotency-Key': 'request-1'})

    assert replay.status_code == 200
    assert _armed_ids(scenario) == []
    assert scenario.queued == []


@pytest.mark.parametrize('previous_status', ['cancelled', 'superseded'])
def test_explicit_reopen_to_active_schedules_both_transports(scenario, previous_status):
    scenario.repo.seed('task-1', status=previous_status)

    response = scenario.client.patch('/v1/action-items/task-1', json={'status': 'active'})

    assert response.status_code == 200
    assert response.json()['status'] == 'active'
    assert response.json()['completed'] is False
    assert _armed_ids(scenario) == ['task-1']
    assert _cancelled_ids(scenario) == []
    assert [call['payload']['task_id'] for call in scenario.queued] == ['task-1']


@pytest.mark.parametrize('payload', [{'completed': True}, {'status': 'completed'}, {'clear_due_at': True}])
def test_existing_completion_and_clear_due_patch_behavior_still_cancels(scenario, payload):
    scenario.repo.seed('task-1')

    response = scenario.client.patch('/v1/action-items/task-1', json=payload)

    assert response.status_code == 200
    assert _armed_ids(scenario) == []
    assert _cancelled_ids(scenario) == ['task-1']
    assert scenario.queued == []


def test_completion_query_route_cancels_then_schedules_when_uncompleted(scenario):
    scenario.repo.seed('task-1')
    completed = scenario.client.patch('/v1/action-items/task-1/completed', params={'completed': 'true'})

    assert completed.status_code == 200
    assert completed.json()['completed'] is True
    assert _cancelled_ids(scenario) == ['task-1']
    assert scenario.queued == []
    scenario.fcm.clear()

    reopened = scenario.client.patch('/v1/action-items/task-1/completed', params={'completed': 'false'})

    assert reopened.status_code == 200
    assert reopened.json()['completed'] is False
    assert _armed_ids(scenario) == ['task-1']
    assert _cancelled_ids(scenario) == []
    assert [call['payload']['task_id'] for call in scenario.queued] == ['task-1']
