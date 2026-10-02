"""Real-route replay proofs using only a loopback Firestore emulator.

firebase emulators:exec --only firestore --project demo-task-replay \
  'PYTHONPATH=backend backend/.venv/bin/pytest -q backend/tests/integration/test_action_item_replay_emulator.py'
"""

from datetime import datetime, timezone
import os
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlparse
import uuid

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import _client, redis_db
from routers import action_items
from testing.hermetic_network import block_outbound_network


@pytest.fixture
def replay(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'localhost', '127.0.0.1', '::1'}:
        pytest.fail('This proof requires a loopback Firestore emulator')
    db = firestore.Client(project='demo-task-replay', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', db)
    monkeypatch.setattr(redis_db, 'r', fakeredis.FakeRedis(decode_responses=True))
    uid = uuid.uuid4().hex
    user = db.collection('users').document(uid)
    items = user.collection('action_items')
    effects = {'vector': Mock(), 'reminder': Mock(), 'sync': AsyncMock()}
    monkeypatch.setattr(action_items, 'upsert_action_item_vector', effects['vector'])
    monkeypatch.setattr(action_items, '_schedule_action_item_reminder', effects['reminder'])
    monkeypatch.setattr(action_items, 'auto_sync_action_item', effects['sync'])
    monkeypatch.setattr(action_items, 'submit_with_context', lambda _pool, fn: fn())
    monkeypatch.setattr(action_items, '_wake_task_changes', Mock())
    monkeypatch.setattr(action_items, 'record_product_event', Mock())
    app = FastAPI()
    app.include_router(action_items.router)
    app.dependency_overrides[action_items.auth.get_current_user_uid] = lambda: uid
    with block_outbound_network(), TestClient(app) as client:
        yield client, user, items, effects
    db.close()


def create(client, *, key='retry-key', **payload):
    response = client.post(
        '/v1/action-items',
        json={'description': 'Original task', **payload},
        headers={'Idempotency-Key': key} if key else {},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('generation', [0, 7])
def test_retry_after_completion_returns_same_completed_task(replay, generation):
    client, user, items, effects = replay
    if generation:
        user.collection('task_intelligence_control').document('state').set({'account_generation': generation})
    first = create(client, due_at='2030-01-01T12:00:00Z')
    completed_at = datetime(2026, 9, 27, tzinfo=timezone.utc)
    items.document(first['id']).update({'completed': True, 'completed_at': completed_at})
    for effect in effects.values():
        effect.reset_mock()

    second = create(client, due_at='2030-01-01T12:00:00Z')

    assert second['id'] == first['id'], 'a delayed retry must not recreate a completed task'
    assert second['completed'] is True
    assert len(list(items.stream())) == 1
    assert items.document(first['id']).get().to_dict()['completed_at'] == completed_at
    effects['reminder'].assert_not_called()
    effects['sync'].assert_not_called()


def test_completed_create_is_idempotent_and_does_not_export_an_open_task(replay):
    client, _, items, effects = replay
    first = create(client, completed=True)
    second = create(client, completed=True)
    assert second['id'] == first['id']
    assert len(list(items.stream())) == 1
    effects['sync'].assert_not_called()


def test_retry_projects_saved_edits_instead_of_stale_create_payload(replay):
    client, _, items, effects = replay
    first = create(client, due_at='2030-01-01T12:00:00Z')
    due = datetime(2030, 2, 1, 12, tzinfo=timezone.utc)
    items.document(first['id']).update({'description': 'Edited task', 'due_at': due})
    for effect in effects.values():
        effect.reset_mock()

    second = create(client, due_at='2030-01-01T12:00:00Z')

    assert second['id'] == first['id']
    assert second['description'] == 'Edited task'
    assert len(list(items.stream())) == 1
    assert effects['vector'].call_args.args[2] == 'Edited task'
    assert effects['reminder'].call_args.args[2:] == ('Edited task', due)
    exported = effects['sync'].call_args.args[1]
    assert exported['id'] == first['id']
    assert exported['description'] == 'Edited task'
    assert exported['due_at'] == due


def test_retry_does_not_rearm_a_removed_due_date(replay):
    client, _, items, effects = replay
    first = create(client, due_at='2030-01-01T12:00:00Z')
    items.document(first['id']).update({'due_at': None})
    effects['reminder'].reset_mock()
    assert create(client, due_at='2030-01-01T12:00:00Z')['id'] == first['id']
    effects['reminder'].assert_not_called()


def test_generation_reset_and_unkeyed_creates_remain_distinct(replay):
    client, user, items, _ = replay
    first = create(client)
    user.collection('task_intelligence_control').document('state').set({'account_generation': 1})
    fresh = create(client)
    assert fresh['id'] != first['id']
    assert create(client)['id'] == fresh['id']
    assert create(client, key=None)['id'] != create(client, key=None)['id']
    assert len(list(items.stream())) == 4
