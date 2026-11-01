"""Real Firestore prepare/accept concurrency and retry tests; loopback only."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import os
from unittest.mock import Mock
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from google.api_core.exceptions import Aborted
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.transaction import Transaction
import pytest

from database import _client
from routers import candidates as router
from routers import action_items as tasks_router, task_integrations as integrations_router
from testing.hermetic_network import block_local_redis, block_outbound_network
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
    app.include_router(tasks_router.router)
    app.include_router(integrations_router.router)
    # Replace only authentication (including the list route's rate-limited
    # principal), leaving production queries, decoding and transactions intact.
    for route in app.routes:
        if isinstance(route, APIRoute):
            for dependency in route.dependant.dependencies:
                if dependency.name == 'uid':
                    app.dependency_overrides[dependency.call] = lambda: uid
    with block_outbound_network(), block_local_redis(), TestClient(app) as client:
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


@pytest.mark.parametrize('legacy_string', [False, True])
def test_mobile_prepare_accept_read_refresh_integrations_and_generation_contract(harness, legacy_string):
    client, user = harness
    conversation = user.collection('conversations').document('conversation-1')
    if legacy_string:
        structured = conversation.get().to_dict()['structured']
        structured['action_items'] = ['Send budget']
        conversation.update({'structured': structured})
    original_conversation = conversation.get().to_dict()
    # Existing phone/pendant tasks share this same read projection. No capture
    # path is changed or invoked by summary recovery.
    user.collection('action_items').document('phone-task').set(
        {
            'id': 'phone-task',
            'description': 'Existing phone task',
            'completed': False,
            'created_at': datetime.now(timezone.utc),
        }
    )
    control = client.get('/v1/candidates/control')
    assert control.status_code == 200
    assert control.json() == {'workflow_mode': 'read', 'account_generation': 3}
    before = client.get('/v1/action-items?limit=100&offset=0')
    assert before.status_code == 200, before.text
    assert [item['id'] for item in before.json()['action_items']] == ['phone-task']
    candidate_id = prepare(client)
    assert conversation.get().to_dict() == original_conversation
    candidate = client.get(f'/v1/candidates/{candidate_id}')
    assert candidate.status_code == 200
    assert candidate.json()['status'] == 'pending'
    suggested = client.get('/v1/candidates?surface=suggested')
    assert suggested.status_code == 200, suggested.text
    # Unknown-confidence historical rows remain explicit summary gestures,
    # rather than being promoted into the automatic high-confidence queue.
    assert len(suggested.json()['candidates']) == (0 if legacy_string else 1)
    receipt = accept(client, candidate_id)
    assert receipt.status_code == 200, receipt.text
    task_id = receipt.json()['task_id']
    task = client.get(f'/v1/action-items/{task_id}')
    assert task.status_code == 200, task.text
    assert task.json()['description'] == 'Send budget'
    assert task.json()['completed'] is False
    for _ in range(2):
        refreshed = client.get('/v1/action-items?limit=100&offset=0')
        assert refreshed.status_code == 200, refreshed.text
        assert {item['id'] for item in refreshed.json()['action_items']} == {task_id, 'phone-task'}
        assert refreshed.json()['has_more'] is False
    first = client.get('/v1/action-items?limit=1&offset=0').json()
    second = client.get('/v1/action-items?limit=1&offset=1').json()
    assert {first['action_items'][0]['id'], second['action_items'][0]['id']} == {task_id, 'phone-task'}
    assert first['has_more'] is True and second['has_more'] is False
    assert client.get('/v1/candidates?surface=suggested').json()['candidates'] == []
    replay = accept(client, prepare(client))
    assert replay.status_code == 200 and replay.json()['task_id'] == task_id
    assert replay.json()['newly_resolved'] is False
    assert len(list(user.collection('action_items').stream())) == 2
    assert client.get('/v1/task-integrations').json() == {'integrations': {}, 'default_app': None}
    assert client.get('/v1/task-integrations/default').json() == {'default_app': None}
    user.collection('task_intelligence_control').document('state').update({'account_generation': 4})
    assert client.get(f'/v1/candidates/{candidate_id}').status_code == 404
    assert accept(client, candidate_id).status_code == 409
    assert client.post('/v1/candidates/from-conversation', headers=HEADERS, json=SELECTED).status_code == 409


@pytest.mark.parametrize('phase', ['prepare', 'accept'])
@pytest.mark.parametrize('abort_at', ['read', 'sdk_exhaustion'])
def test_mobile_summary_retries_only_definite_contention_with_a_fresh_transaction(
    harness, monkeypatch, phase, abort_at
):
    client, user = harness
    candidate_id = prepare(client) if phase == 'accept' else None
    original_get = DocumentReference.get
    original_commit = Transaction._commit
    attempts = []

    def abort_read_once(reference, *args, **kwargs):
        transaction = kwargs.get('transaction')
        if transaction is not None and reference.id == 'state':
            attempts.append(transaction)
            if len(attempts) == 1:
                raise Aborted('synthetic read contention')
        return original_get(reference, *args, **kwargs)

    def exhaust_sdk_once(transaction):
        attempts.append(transaction)
        if len(attempts) <= 5:
            # Intermediate synthetic aborts release emulator locks. On the
            # final SDK attempt its own exhaustion handler owns rollback.
            if len(attempts) < 5:
                transaction._rollback()
            raise Aborted('synthetic exhausted commit contention')
        return original_commit(transaction)

    if abort_at == 'read':
        monkeypatch.setattr(DocumentReference, 'get', abort_read_once)
    else:
        monkeypatch.setattr(Transaction, '_commit', exhaust_sdk_once)
    response = (
        client.post('/v1/candidates/from-conversation', headers=HEADERS, json=SELECTED)
        if phase == 'prepare'
        else accept(client, candidate_id)
    )
    assert response.status_code == 200, response.text
    assert len({id(transaction) for transaction in attempts}) == 2
    assert len(attempts) == (2 if abort_at == 'read' else 6)
    saved = state(user)
    assert len(saved['candidates']) == 1
    assert len(saved.get('action_items', {})) == (0 if phase == 'prepare' else 1)
