"""Real Firestore prepare/accept concurrency and retry tests; loopback only."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import os
from unittest.mock import Mock
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import Aborted
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.transaction import Transaction
import pytest

from database import _client
from routers import candidates as router
from testing.hermetic_network import block_outbound_network
from utils.task_intelligence import candidate_service

SELECTED = {'conversation_id': 'conversation-1', 'action_item_index': 0, 'expected_description': 'Send budget'}
HEADERS = {'X-Account-Generation': '3', 'Idempotency-Key': 'summary-gesture'}


@pytest.fixture
def harness(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'localhost', '127.0.0.1', '::1'}:
        pytest.fail('A loopback Firestore emulator is required')
    db = firestore.Client(project='demo-summary-tasks', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', db)
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    uid = uuid4().hex
    user = db.collection('users').document(uid)
    user.collection('task_intelligence_control').document('state').set({'account_generation': 3})
    user.collection('conversations').document('conversation-1').set(
        {
            'structured': {
                'title': 'Budget',
                'action_items': [
                    {
                        'description': 'Send budget',
                        'capture_owner': 'user',
                        'capture_confidence': 0.9,
                        'ownership_confidence': 1.0,
                        'source_segment_ids': ['segment-1'],
                        'due_at': datetime(2026, 10, 1, 9, tzinfo=timezone.utc),
                    }
                ],
            },
            'transcript_segments': b'opaque transcript',
        }
    )
    for name in ('_dispatch_task_integration', '_sync_task_reminder'):
        monkeypatch.setattr(candidate_service, name, Mock())
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: uid
    with block_outbound_network(), TestClient(app) as client:
        yield client, user
    db.close()


def prepare(client):
    response = client.post('/v1/candidates/from-conversation', headers=HEADERS, json=SELECTED)
    assert response.status_code == 200, response.text
    return response.json()['candidate_id']


def accept(client, candidate_id, summary=True):
    body = {'json': {'summary_item': SELECTED}} if summary else {}
    return client.post(f'/v1/candidates/{candidate_id}/accept', headers=HEADERS, **body)


def state(user):
    return {collection.id: {doc.id: doc.to_dict() for doc in collection.stream()} for collection in user.collections()}


def test_concurrent_summary_and_suggested_accept_commit_one_linked_task(harness):
    client, user = harness
    with ThreadPoolExecutor(max_workers=2) as pool:
        prepared = list(pool.map(lambda _: prepare(client), range(2)))
    assert prepared[0] == prepared[1]
    assert list(user.collection('action_items').stream()) == []
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda summary: accept(client, prepared[0], summary), [True, False]))
    assert [response.status_code for response in responses] == [200, 200]
    receipts = [response.json() for response in responses]
    assert sum(receipt['newly_resolved'] for receipt in receipts) == 1
    assert receipts[0]['task_id'] == receipts[1]['task_id']
    saved = state(user)
    assert len(saved['action_items']) == 1
    task = saved['action_items'][receipts[0]['task_id']]
    assert task['conversation_id'] == 'conversation-1'
    assert task['provenance'][0]['transcript_segment_ids'] == ['segment-1']
    assert saved['conversations']['conversation-1']['structured']['action_items'][0]['target_task_id'] == task['id']
    assert saved['candidates'][prepared[0]]['status'] == 'accepted'
    replay = accept(client, prepare(client))
    assert replay.status_code == 200, replay.text
    assert replay.json()['newly_resolved'] is False
    assert state(user) == saved


@pytest.mark.parametrize('mutation', ['description', 'due_at', 'account_generation'])
def test_transaction_retry_rereads_summary_and_generation_before_any_commit(harness, monkeypatch, mutation):
    client, user = harness
    candidate_id = prepare(client)
    original_commit = Transaction._commit
    commits = []
    expected = []

    def abort_once(transaction):
        commits.append(transaction)
        if len(commits) == 1:
            transaction._rollback()
            if mutation == 'account_generation':
                user.collection('task_intelligence_control').document('state').update({'account_generation': 4})
            else:
                ref = user.collection('conversations').document('conversation-1')
                structured = deepcopy(ref.get().to_dict()['structured'])
                structured['action_items'][0][mutation] = (
                    'Changed after transaction read'
                    if mutation == 'description'
                    else datetime(2026, 10, 2, 9, tzinfo=timezone.utc)
                )
                ref.update({'structured': structured})
            expected.append(state(user))
            raise Aborted('synthetic abort after summary edit')
        return original_commit(transaction)

    monkeypatch.setattr(Transaction, '_commit', abort_once)
    response = accept(client, candidate_id)
    assert response.status_code == 409, response.text
    assert len(commits) == 1
    assert state(user) == expected[0]
    assert list(user.collection('action_items').stream()) == []
