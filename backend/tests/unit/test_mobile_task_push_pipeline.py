"""Production HTTP routes/workers, with only storage and provider I/O substituted.

Manual Share/Export is deliberately absent: task creation must start the normal
automatic cloud handoff even when Apple is connected and no push token exists.
"""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def pipeline(monkeypatch):
    from routers import action_items, notifications, task_integrations
    from utils import notifications as sender, task_sync
    from utils.other import endpoints as auth

    state = SimpleNamespace(
        tasks={},
        default='todoist',
        connected=True,
        provider_status=201,
        requests=[],
        futures=[],
        tokens=[],
        refuse_token=False,
    )

    def create(uid, data, *, idempotency_key=None):
        task_id = f'task-{len(state.tasks) + 1}'
        state.tasks[task_id] = {'id': task_id, **data}
        return task_id

    def update(uid, task_id, fields):
        state.tasks[task_id].update(fields)

    def integration(uid, key):
        if key == 'apple_reminders':
            return {'connected': True}
        assert key == 'todoist'
        return {'connected': state.connected, 'access_token': 'synthetic-provider-token'}

    def provider(request):
        assert request.url == 'https://api.todoist.com/api/v1/tasks'
        state.requests.append(json.loads(request.content))
        return httpx.Response(state.provider_status, json={'id': f'provider-{len(state.requests)}'})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        task_sync.httpx,
        'AsyncClient',
        lambda **kwargs: async_client(transport=httpx.MockTransport(provider), **kwargs),
    )
    monkeypatch.setattr(action_items, 'create_task', create)
    monkeypatch.setattr(action_items, 'upsert_action_item_vector', lambda *args: None)
    monkeypatch.setattr(action_items, 'record_product_event', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        action_items.action_items_db, 'get_action_item', lambda uid, task_id: dict(state.tasks[task_id])
    )
    monkeypatch.setattr(action_items.action_items_db, 'update_action_item', update)
    monkeypatch.setattr(task_sync.users_db, 'get_default_task_integration', lambda uid: state.default)
    monkeypatch.setattr(task_sync.users_db, 'get_task_integration', integration)
    monkeypatch.setattr(
        task_sync.users_db,
        'set_task_integration',
        lambda uid, key, details: setattr(state, 'connected', details['connected']),
    )

    def no_apple(**kwargs):
        pytest.fail('Todoist automatic export must not depend on an Apple push')

    monkeypatch.setattr(task_sync, 'send_apple_reminders_sync_push_async', no_apple)
    real_submit = action_items.submit_with_context

    def submit(executor, function):
        future = real_submit(executor, function)
        state.futures.append(future)
        return future

    monkeypatch.setattr(action_items, 'submit_with_context', submit)

    def save_token(uid, data):
        if state.refuse_token:
            raise RuntimeError('synthetic storage refusal')
        state.tokens[:] = [data['fcm_token']]

    monkeypatch.setattr(notifications.notification_db, 'save_token', save_token)
    monkeypatch.setattr(notifications, 'emit_posthog_event', lambda *args: None)
    monkeypatch.setattr(sender.notification_db, 'get_all_tokens', lambda uid: list(state.tokens))
    monkeypatch.setattr(sender, 'account_deletion_blocks_user_work', lambda uid: False)
    submitted_messages = []

    def send(messages):
        submitted_messages.extend(messages)
        return SimpleNamespace(responses=[SimpleNamespace(success=True, exception=None) for _ in messages])

    monkeypatch.setattr(sender, '_send_messages', send)
    state.messages = submitted_messages
    state.sender = sender

    app = FastAPI()
    app.include_router(action_items.router)
    app.include_router(notifications.router)
    app.include_router(task_integrations.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'synthetic-owner'
    with TestClient(app, raise_server_exceptions=False) as client:
        state.client = client
        yield state
    for future in state.futures:
        future.result(timeout=5)


@pytest.mark.parametrize('connected, provider_status', [(True, 201), (True, 401), (True, 503), (False, 201)])
def test_new_task_runs_real_automatic_todoist_handoff_without_a_push_token(pipeline, connected, provider_status):
    state = pipeline
    state.connected = connected
    state.provider_status = provider_status
    response = state.client.post('/v1/action-items', json={'description': 'Synthetic automatic task'})
    assert response.status_code == 200, response.text
    for future in state.futures:
        future.result(timeout=5)
    task = state.tasks[response.json()['id']]
    assert state.tokens == []  # Cloud routing is independent of FCM registration.
    assert len(state.requests) == int(connected)
    if connected:
        assert state.requests[0]['content'] == 'Synthetic automatic task'
    if connected and provider_status == 201:
        assert task['exported'] is True
        assert task['export_platform'] == 'todoist'
        assert task['external_task_id'] == 'provider-1'
    else:
        assert not task.get('exported')
    if provider_status == 401:
        assert state.connected is False


def test_refused_registration_can_retry_and_unlock_the_shared_push_sender(pipeline):
    state = pipeline
    assert state.sender.send_notification_result('synthetic-owner', 'Synthetic title', 'Synthetic body') == 0
    state.refuse_token = True
    headers = {'X-App-Platform': 'ios', 'X-Device-Id-Hash': 'synthetic-device'}
    payload = {'fcm_token': 'synthetic-fcm', 'time_zone': 'Europe/Berlin'}
    assert state.client.post('/v1/users/fcm-token', json=payload, headers=headers).status_code == 500
    assert not state.tokens
    state.refuse_token = False
    accepted = state.client.post('/v1/users/fcm-token', json=payload, headers=headers)
    assert accepted.status_code == 200
    assert accepted.json()['status'] == 'Ok'
    assert state.sender.send_notification_result('synthetic-owner', 'Synthetic title', 'Synthetic body') == 1
    assert len(state.messages) == 1
    assert state.messages[0].token == 'synthetic-fcm'
