"""Acceptance must enforce the same lifetime as the Suggested projection."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database import _client, candidates, workstreams
from models.candidate import CandidateRecord
from routers import candidates as router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.task_intelligence import candidate_service

NOW = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
UID = 'expiry-test-user'


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


def record(kind, *, deadline=NOW, legacy=False):
    payload = dict(
        candidate_id='candidate-1',
        account_generation=3,
        idempotency_key='capture-1',
        subject_kind='workstream' if kind == 'workstream' else 'task',
        proposed_action='create' if kind == 'workstream' else kind,
        capture_confidence=0.95,
        ownership_confidence=1,
        evidence_refs=[{'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}],
        source_surface='conversation',
        created_at=deadline - candidates.SUGGESTION_TTL,
    )
    if not legacy:
        payload['expires_at'] = deadline
    if kind == 'workstream':
        payload['workstream_proposal'] = {
            'title': 'Budget',
            'objective': 'Ship the budget',
            'anchor_task': {'description': 'Send budget'},
        }
    elif kind == 'create':
        payload['task_change'] = {'description': 'Send budget'}
    else:
        payload['task_id'] = 'existing-task'
        payload['task_change'] = {
            'update': {'description': 'Updated budget', 'status': 'active'},
            'complete': {'status': 'completed'},
            'cancel': {'status': 'cancelled'},
            'supersede': {'status': 'superseded', 'superseded_by': 'replacement'},
        }[kind]
    return CandidateRecord.model_validate(payload)


@pytest.fixture
def harness(monkeypatch):
    db = StrictFirestore()
    monkeypatch.setattr(_client, '_firestore_client', db)
    monkeypatch.setattr(candidates, 'datetime', Clock)
    monkeypatch.setattr(workstreams, 'datetime', Clock)
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    db.rows[('users', UID, 'task_intelligence_control', 'state')] = {'account_generation': 3}
    db.rows[('users', UID, 'action_items', 'existing-task')] = {
        'id': 'existing-task',
        'description': 'Original',
        'account_generation': 3,
        'status': 'active',
        'completed': False,
        'created_at': NOW,
    }
    # The narrow strict fixture has no snapshot.id; only the service pre-read is
    # adapted. The authoritative task read/write still runs in the transaction.
    monkeypatch.setattr(
        candidate_service.action_items_db,
        'get_action_item',
        lambda uid, task_id: deepcopy(db.rows.get(('users', uid, 'action_items', task_id))),
    )
    effects = []
    for name in ('_dispatch_task_integration', '_sync_task_reminder', 'refresh_workstream_association_index'):
        effect = Mock()
        monkeypatch.setattr(candidate_service, name, effect)
        effects.append(effect)
    monkeypatch.setattr(candidate_service, '_workstream_resolver', workstreams.resolve_workstream_candidate)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: UID
    with TestClient(app) as client:
        yield db, client, effects


def accept(client):
    return client.post('/v1/candidates/candidate-1/accept', headers={'X-Account-Generation': '3'})


@pytest.mark.parametrize('kind', ['create', 'update', 'complete', 'cancel', 'supersede', 'workstream'])
@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('age', [timedelta(0), timedelta(days=10)])
def test_expired_accept_conflicts_without_any_writes_or_delivery(harness, kind, legacy, age):
    db, client, effects = harness
    candidate = record(kind, deadline=NOW - age, legacy=legacy)
    db.rows[('users', UID, 'candidates', candidate.candidate_id)] = candidate.model_dump(mode='python')
    before = deepcopy(db.rows)
    response = accept(client)
    assert response.status_code == 409, response.text
    assert response.json()['detail'] == 'Candidate suggestion has expired'
    assert db.rows == before
    for effect in effects:
        effect.assert_not_called()


@pytest.mark.parametrize('kind', ['create', 'workstream'])
@pytest.mark.parametrize('legacy', [False, True])
def test_live_accept_and_old_successful_replay_keep_the_same_receipt(harness, monkeypatch, kind, legacy):
    db, client, _ = harness
    candidate = record(kind, deadline=NOW + timedelta(microseconds=1), legacy=legacy)
    db.rows[('users', UID, 'candidates', candidate.candidate_id)] = candidate.model_dump(mode='python')
    first = accept(client)
    assert first.status_code == 200, first.text
    assert first.json()['newly_resolved'] is True
    monkeypatch.setattr(Clock, 'now', classmethod(lambda cls, tz=None: NOW + timedelta(days=30)))
    before = deepcopy(db.rows)
    replay = accept(client)
    assert replay.status_code == 200, replay.text
    assert replay.json()['newly_resolved'] is False
    assert replay.json()['receipt_id'] == first.json()['receipt_id']
    assert replay.json()['task_id'] == first.json()['task_id']
    assert db.rows == before


@pytest.mark.parametrize('kind', ['create', 'workstream'])
def test_generation_fence_precedes_expiry(harness, kind):
    db, client, _ = harness
    candidate = record(kind).model_copy(update={'account_generation': 2})
    db.rows[('users', UID, 'candidates', candidate.candidate_id)] = candidate.model_dump(mode='python')
    before = deepcopy(db.rows)
    response = accept(client)
    assert response.status_code == 409
    assert response.json()['detail'] == 'Account generation mismatch'
    assert db.rows == before
