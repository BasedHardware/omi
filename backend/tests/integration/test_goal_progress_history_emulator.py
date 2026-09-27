"""Progress/history consistency through real routes and the Firestore SDK.

Run against a loopback emulator with project demo-goal-history:
  FIRESTORE_EMULATOR_HOST=127.0.0.1:10276 PYTHONPATH=backend backend/.venv/bin/pytest -q \
    backend/tests/integration/test_goal_progress_history_emulator.py
Only authentication and proactive delivery are replaced; records are synthetic.
"""

from datetime import datetime, timezone
import os
from unittest.mock import Mock
from urllib.parse import urlparse
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.transaction import Transaction
import pytest

from database import _client, goals
from routers import goals as routes


@pytest.fixture
def progress(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'localhost', '127.0.0.1', '::1'}:
        pytest.fail('This proof requires a loopback Firestore emulator')
    db = firestore.Client(project='demo-goal-history', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', db)
    uid = f'goal-history-{uuid.uuid4().hex}'
    user = db.collection('users').document(uid)
    user.set({'time_zone': 'America/Los_Angeles'})
    goal = user.collection('goals').document('g1')
    goals.create_goal(uid, {'id': 'g1', 'title': 'Read books', 'goal_type': 'numeric', 'target_value': 20})
    wake = Mock()
    monkeypatch.setattr(routes, '_wake_goal_change', wake)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: uid
    app.dependency_overrides[routes.require_canonical_task_user] = lambda: uid
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, uid, goal, wake
    db.close()


def freeze_time(monkeypatch, day):
    # 02:30 UTC is the preceding day in Los Angeles.
    now = datetime(2026, 9, day, 2, 30, tzinfo=timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(goals, 'datetime', FrozenDatetime)
    return now


def post_event(client, key='one', value=7):
    return client.post(
        '/v1/goals/g1/progress-events',
        json={
            'kind': 'metric_update',
            'summary': 'Books read',
            'metric': {'type': 'numeric', 'current': value, 'target': 20},
        },
        headers={'Idempotency-Key': key, 'X-Account-Generation': '0'},
    )


def test_canonical_metric_event_updates_the_released_history_chart(progress, monkeypatch):
    client, _, goal, _ = progress
    now = freeze_time(monkeypatch, 27)
    response = post_event(client)
    assert response.status_code == 200, response.text
    assert goal.get().to_dict()['metric']['current'] == 7
    history = client.get('/v1/goals/g1/history').json()
    assert [(row['date'], row['value']) for row in history] == [('2026-09-26', 7)]
    assert goal.collection('goal_history').document('2026-09-26').get().to_dict()['recorded_at'] == now


def test_released_progress_failure_cannot_commit_only_the_goal_and_event(progress, monkeypatch):
    client, _, goal, wake = progress
    before = goal.get().to_dict()
    original_set = Transaction.set
    direct_set = DocumentReference.set

    def reject_history_commit(transaction, reference, data, *args, **kwargs):
        result = original_set(transaction, reference, data, *args, **kwargs)
        if '/goal_history/' in reference.path:
            # Real emulator precondition failure: none of the staged writes may persist.
            transaction.update(goal.collection('fault_injection').document('missing'), {'value': 1})
        return result

    def reject_standalone_history(reference, data, *args, **kwargs):
        if '/goal_history/' in reference.path:
            raise RuntimeError('injected history write failure')
        return direct_set(reference, data, *args, **kwargs)

    monkeypatch.setattr(Transaction, 'set', reject_history_commit)
    monkeypatch.setattr(DocumentReference, 'set', reject_standalone_history)
    response = client.patch('/v1/goals/g1/progress', params={'current_value': 7})
    assert response.status_code == 500
    assert goal.get().to_dict() == before, 'a failed history commit must not leave progress advanced'
    assert list(goal.collection('events').stream()) == []
    assert list(goal.collection('goal_history').stream()) == []
    wake.assert_not_called()


def test_older_released_writer_cannot_overwrite_a_newer_chart_value(progress, monkeypatch):
    client, uid, goal, _ = progress
    original_append = goals._append_goal_progress_event

    def append_then_newer_update(*args, **kwargs):
        event = original_append(*args, **kwargs)
        if event.metric.current == 7:
            # Pause writer A just after its journal commit and finish writer B.
            goals.update_goal_progress(uid, 'g1', 8)
        return event

    monkeypatch.setattr(goals, '_append_goal_progress_event', append_then_newer_update)
    assert client.patch('/v1/goals/g1/progress', params={'current_value': 7}).status_code == 200
    assert goal.get().to_dict()['metric']['current'] == 8
    assert len(list(goal.collection('events').stream())) == 2
    assert client.get('/v1/goals/g1/history').json()[0]['value'] == 8


def test_internal_retry_on_later_day_does_not_fabricate_new_history(progress, monkeypatch):
    _, uid, goal, _ = progress
    freeze_time(monkeypatch, 27)
    goals.update_goal_progress(uid, 'g1', 7, idempotency_key='conversation-one', account_generation=0)
    original_history = [row.to_dict() for row in goal.collection('goal_history').stream()]
    assert len(original_history) == 1
    freeze_time(monkeypatch, 28)
    goals.update_goal_progress(uid, 'g1', 99, idempotency_key='conversation-one', account_generation=0)
    assert goal.get().to_dict()['metric']['current'] == 7
    assert len(list(goal.collection('events').stream())) == 1
    assert [row.to_dict() for row in goal.collection('goal_history').stream()] == original_history


def test_canonical_retry_does_not_replace_newer_history(progress, monkeypatch):
    client, _, goal, _ = progress
    freeze_time(monkeypatch, 27)
    first = post_event(client).json()
    assert post_event(client, key='two', value=8).status_code == 200
    before = [row.to_dict() for row in goal.collection('goal_history').stream()]
    assert len(before) == 1
    freeze_time(monkeypatch, 28)
    assert post_event(client).json() == first
    assert goal.get().to_dict()['metric']['current'] == 8
    assert [row.to_dict() for row in goal.collection('goal_history').stream()] == before
