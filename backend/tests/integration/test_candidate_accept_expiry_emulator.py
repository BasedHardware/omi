"""Real HTTP router + Firestore SDK proof; requires a loopback emulator only.

FIRESTORE_EMULATOR_HOST=127.0.0.1:10285 backend/.venv/bin/pytest -q \
  backend/tests/integration/test_candidate_accept_expiry_emulator.py
"""

from datetime import timedelta
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

from database import _client, candidates, workstreams
from routers import candidates as router
from testing.hermetic_network import block_outbound_network
from tests.unit.test_candidate_accept_expiry import Clock, NOW, record
from utils.task_intelligence import candidate_service


@pytest.fixture
def harness(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'localhost', '127.0.0.1', '::1'}:
        pytest.fail('A loopback Firestore emulator is required')
    db = firestore.Client(project='demo-candidate-expiry', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', db)
    monkeypatch.setattr(candidates, 'datetime', Clock)
    monkeypatch.setattr(workstreams, 'datetime', Clock)
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    uid = uuid4().hex
    user = db.collection('users').document(uid)
    user.collection('task_intelligence_control').document('state').set({'account_generation': 3})
    user.collection('action_items').document('existing-task').set(
        {
            'id': 'existing-task',
            'description': 'Original',
            'account_generation': 3,
            'status': 'active',
            'completed': False,
            'created_at': NOW,
        }
    )
    effects = []
    for name in ('_dispatch_task_integration', '_sync_task_reminder', 'refresh_workstream_association_index'):
        effect = Mock()
        monkeypatch.setattr(candidate_service, name, effect)
        effects.append(effect)
    monkeypatch.setattr(candidate_service, '_workstream_resolver', workstreams.resolve_workstream_candidate)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: uid
    with block_outbound_network(), TestClient(app) as client:
        yield client, user, effects
    db.close()


def state(user):
    return {collection.id: {doc.id: doc.to_dict() for doc in collection.stream()} for collection in user.collections()}


def accept(client):
    return client.post('/v1/candidates/candidate-1/accept', headers={'X-Account-Generation': '3'})


@pytest.mark.parametrize('kind', ['create', 'update', 'complete', 'cancel', 'supersede', 'workstream'])
@pytest.mark.parametrize('legacy', [False, True])
def test_expired_accept_has_no_committed_effect(harness, kind, legacy):
    client, user, effects = harness
    candidate = record(kind, legacy=legacy)
    user.collection('candidates').document(candidate.candidate_id).set(candidate.model_dump(mode='python'))
    before = state(user)
    response = accept(client)
    assert response.status_code == 409, response.text
    assert response.json()['detail'] == 'Candidate suggestion has expired'
    assert state(user) == before
    for effect in effects:
        effect.assert_not_called()


@pytest.mark.parametrize('kind', ['create', 'workstream'])
def test_retry_resamples_deadline_after_aborted_commit(harness, monkeypatch, kind):
    client, user, effects = harness
    candidate = record(kind, deadline=NOW + timedelta(seconds=1))
    user.collection('candidates').document(candidate.candidate_id).set(candidate.model_dump(mode='python'))
    before = state(user)
    original_commit = Transaction._commit
    commits = []

    def abort_once(transaction):
        commits.append(transaction)
        if len(commits) == 1:
            monkeypatch.setattr(Clock, 'now', classmethod(lambda cls, tz=None: NOW + timedelta(seconds=2)))
            # Release the real emulator locks as a server-aborted commit would.
            transaction._rollback()
            raise Aborted('synthetic retry crosses suggestion deadline')
        return original_commit(transaction)

    monkeypatch.setattr(Transaction, '_commit', abort_once)
    response = accept(client)
    assert response.status_code == 409, response.text
    assert response.json()['detail'] == 'Candidate suggestion has expired'
    assert len(commits) == 1, 'the retry must reject before staging another commit'
    assert state(user) == before
    for effect in effects:
        effect.assert_not_called()


@pytest.mark.parametrize('kind', ['create', 'workstream'])
def test_live_accept_replays_after_expiry(harness, monkeypatch, kind):
    client, user, _ = harness
    candidate = record(kind, deadline=NOW + timedelta(microseconds=1))
    user.collection('candidates').document(candidate.candidate_id).set(candidate.model_dump(mode='python'))
    first = accept(client)
    assert first.status_code == 200, first.text
    before = state(user)
    monkeypatch.setattr(Clock, 'now', classmethod(lambda cls, tz=None: NOW + timedelta(days=30)))
    second = accept(client)
    assert second.status_code == 200, second.text
    assert second.json()['receipt_id'] == first.json()['receipt_id']
    assert second.json()['newly_resolved'] is False
    assert state(user) == before
