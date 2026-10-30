"""Exercise shared-task acceptance with the real Firestore transaction boundary.

Run under a loopback Firestore emulator, e.g. from the repository root:
firebase emulators:exec --only firestore --project demo-task-sharing \
  'PYTHONPATH=backend backend/.venv/bin/pytest -q backend/tests/integration/test_shared_task_acceptance_atomic_emulator.py'
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from unittest.mock import Mock
from urllib.parse import urlparse
import uuid

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.transaction import Transaction
import pytest

from database import _client, redis_db
from routers import action_items


@pytest.fixture
def sharing(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('This proof requires a loopback Firestore emulator')
    db = firestore.Client(project='demo-task-sharing', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', db)
    monkeypatch.setattr(redis_db, 'r', fakeredis.FakeRedis(decode_responses=True))
    sender, recipient, token = [uuid.uuid4().hex for _ in range(3)]
    source = db.collection('users').document(sender).collection('action_items')
    target = db.collection('users').document(recipient).collection('action_items')
    due = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for index in range(2):
        source.document(f'task-{index}').set({'description': f'Task {index}', 'due_at': due})
    redis_db.store_task_share(token, sender, 'Synthetic sender', ['task-0', 'task-1'])
    vectors, reminders, wake = Mock(), Mock(), Mock()
    monkeypatch.setattr(action_items, 'upsert_action_item_vector', vectors)
    monkeypatch.setattr(action_items, '_schedule_action_item_reminder', reminders)
    app = FastAPI()
    app.include_router(action_items.router)
    app.dependency_overrides[action_items.auth.get_current_user_uid] = lambda: recipient
    with TestClient(app) as client:
        yield client, db, source, target, sender, recipient, token, vectors, reminders, wake
    db.close()


@pytest.mark.parametrize('failure', ['second_write', 'second_source_read'])
def test_failed_acceptance_copies_nothing_and_can_retry_all_tasks(sharing, monkeypatch, failure):
    client, _, source, target, _, recipient, token, vectors, reminders, wake = sharing
    real_set, real_get = Transaction.set, DocumentReference.get
    seen = 0

    def fail_second_write(transaction, reference, *args, **kwargs):
        if reference.path.startswith(f'users/{recipient}/action_items/') and args[0].get('description') == 'Task 1':
            raise RuntimeError('synthetic write failure before commit')
        return real_set(transaction, reference, *args, **kwargs)

    def fail_second_source_read(reference, *args, **kwargs):
        nonlocal seen
        if reference.path == source.document('task-1').path:
            seen += 1
            if seen == 2:
                raise RuntimeError('synthetic source read failure')
        return real_get(reference, *args, **kwargs)

    with monkeypatch.context() as fault:
        if failure == 'second_write':
            fault.setattr(Transaction, 'set', fail_second_write)
        else:
            fault.setattr(DocumentReference, 'get', fail_second_source_read)
        with pytest.raises(RuntimeError, match='synthetic .*failure'):
            client.post('/v1/action-items/accept', json={'token': token})

    assert list(target.stream()) == [], 'a failed acceptance must not leave a copied prefix'
    assert not redis_db.r.sismember(f'task_share:{token}:accepted', recipient)
    vectors.assert_not_called()
    reminders.assert_not_called()
    wake.assert_not_called()

    retry = client.post('/v1/action-items/accept', json={'token': token})
    assert retry.status_code == 200, retry.text
    assert retry.json()['count'] == 2
    assert {row.id for row in target.stream()} == set(retry.json()['created'])
    assert vectors.call_count == reminders.call_count == 2
    wake.assert_not_called()


def test_delivery_failure_cannot_prevent_later_tasks_from_being_saved(sharing):
    client, _, _, target, _, _, token, _, reminders, _ = sharing
    reminders.side_effect = RuntimeError('synthetic notification failure')
    with pytest.raises(RuntimeError, match='synthetic notification failure'):
        client.post('/v1/action-items/accept', json={'token': token})
    assert len(list(target.stream())) == 2, 'persist the whole batch before sending reminders'
    reminders.side_effect = None
    assert client.post('/v1/action-items/accept', json={'token': token}).status_code == 409
    assert len(list(target.stream())) == 2


def test_overlapping_acceptance_creates_one_complete_batch_with_provenance(sharing):
    client, db, _, target, sender, recipient, token, _, _, _ = sharing
    db.document(f'users/{recipient}/task_intelligence_control/state').set({'account_generation': 5})
    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(lambda _: client.post('/v1/action-items/accept', json={'token': token}), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    rows = list(target.stream())
    assert len(rows) == 2
    for row in rows:
        data = row.to_dict()
        assert data['account_generation'] == 5
        assert data['completed'] is False
        assert data['shared_from'] == {
            'token': token,
            'sender_uid': sender,
            'sender_name': 'Synthetic sender',
            'original_task_id': f"task-{data['description'][-1]}",
        }
