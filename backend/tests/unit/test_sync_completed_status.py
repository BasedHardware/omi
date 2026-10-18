"""Real HTTP polling plus durable receipts; no provider work or store writes."""

from copy import deepcopy
from unittest.mock import Mock

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import sync_jobs
from routers import sync as router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.sync import completed_status


@pytest.fixture
def poll(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_DURABLE_STATUS_RECONCILIATION', 'true')
    monkeypatch.setattr(router, 'admit_sync_job_poll', lambda uid: True)
    monkeypatch.setattr(sync_jobs, 'r', fakeredis.FakeRedis())
    database = StrictFirestore({('users', 'owner'): {'data_protection_level': 'standard'}})
    monkeypatch.setattr(completed_status, 'get_firestore_client', lambda: database)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: 'owner'
    with TestClient(app) as client:
        yield client, database
    assert all(not tx.has_written for tx in database.transactions)


def receipt(database, *, job='original', content='content', result=None, status='completed', owner='owner'):
    if result is None:
        result = {'total_segments': 1, 'failed_segments': 0, 'errors': [], 'outcome': 'expected_silence'}
    database.collection('users').document(owner).collection('sync_content_ledger').document(content).create(
        {'status': status, 'job_id': job, 'result': result}
    )


def test_expired_redis_silence_completes_original_handle_without_mutation(poll):
    client, database = poll
    receipt(database)
    before = deepcopy(database.rows)
    response = client.get('/v2/sync-local-files/original')
    assert response.status_code == 200
    body = response.json()
    assert body['job_id'] == 'original' and body['status'] == 'completed'
    assert body['result']['new_memories'] == body['result']['updated_memories'] == []
    assert body['failed_segments'] == 0 and body['processed_segments'] == 1
    assert database.rows == before
    assert sync_jobs.get_sync_job('original') is None


@pytest.mark.parametrize('state', ['queued', 'processing', 'failed'])
def test_redrive_completion_dominates_old_execution_handle(poll, state):
    client, database = poll
    sync_jobs.create_sync_job('owner', 1, 1, 'original', content_id='content')
    sync_jobs.update_sync_job('original', {'status': state})
    result = {
        'total_segments': 1,
        'failed_segments': 0,
        'errors': [],
        'outcome': 'success',
        'updated_memories': ['survivor'],
    }
    receipt(database, job='redrive', result=result)
    database.collection('users').document('owner').collection('conversations').document('survivor').create({})
    response = client.get('/v2/sync-local-files/original')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'completed' and body['job_id'] == 'original'
    assert body['result']['updated_memories'] == ['survivor']
    assert sync_jobs.get_sync_job('original')['status'] == state


def test_custody_alias_resolves_expired_original_after_redrive(poll):
    client, database = poll
    receipt(database, job='redrive')
    database.collection('sync_redrive_required').document('original').create(
        {'uid': 'owner', 'job_id': 'original', 'payload': {'content_id': 'content'}}
    )
    assert client.get('/v2/sync-local-files/original').json()['status'] == 'completed'


@pytest.mark.parametrize(
    'result,status',
    [
        ({'total_segments': 0, 'failed_segments': 0, 'errors': []}, 'completed'),
        ({'total_segments': 1, 'failed_segments': 1, 'errors': ['failed'], 'outcome': 'success'}, 'completed'),
        (
            {'total_segments': 1, 'failed_segments': 0, 'errors': [], 'outcome': 'success', 'held_audio': True},
            'completed',
        ),
        ({'total_segments': 1, 'failed_segments': 0, 'errors': [], 'outcome': 'success'}, 'processing'),
        ({'total_segments': 1, 'failed_segments': 0, 'errors': [], 'outcome': 'success'}, 'retryable'),
    ],
)
def test_unproven_work_is_never_acknowledged(poll, result, status):
    client, database = poll
    receipt(database, result=result, status=status)
    assert client.get('/v2/sync-local-files/original').status_code == 404


def test_unknown_and_ambiguous_handles_preserve_404(poll):
    client, database = poll
    assert client.get('/v2/sync-local-files/original').status_code == 404
    receipt(database)
    receipt(database, content='duplicate')
    assert client.get('/v2/sync-local-files/original').status_code == 404


def test_foreign_owner_and_alias_cannot_disclose_completion(poll):
    client, database = poll
    receipt(database, owner='foreign')
    assert client.get('/v2/sync-local-files/original').status_code == 404
    database.collection('sync_redrive_required').document('original').create(
        {'uid': 'foreign', 'job_id': 'original', 'payload': {'content_id': 'content'}}
    )
    assert client.get('/v2/sync-local-files/original').status_code == 404
    sync_jobs.create_sync_job('foreign', 1, 1, 'original', content_id='content')
    assert client.get('/v2/sync-local-files/original').status_code == 403


@pytest.mark.parametrize('fence', ['account', 'protection', 'conversation'])
def test_privacy_change_retains_local_audio_instead_of_ack(poll, fence):
    client, database = poll
    receipt(
        database,
        result={
            'total_segments': 1,
            'failed_segments': 0,
            'errors': [],
            'outcome': 'success',
            'new_memories': ['target'],
        },
    )
    if fence == 'account':
        database.rows.pop(('users', 'owner'))
    elif fence == 'protection':
        database.rows['users', 'owner']['data_protection_level'] = 'e2ee'
    else:
        database.collection('users').document('owner').collection('deleted_conversations').document('target').create({})
    response = client.get('/v2/sync-local-files/original')
    assert response.status_code == 503
    assert response.headers['retry-after'] == '10'


def test_read_failure_is_transient_not_unknown(poll, monkeypatch):
    client, database = poll
    monkeypatch.setattr(completed_status, 'get_firestore_client', Mock(side_effect=RuntimeError('unavailable')))
    assert client.get('/v2/sync-local-files/original').status_code == 503


def test_flag_off_preserves_legacy_contract_without_firestore(poll, monkeypatch):
    client, database = poll
    monkeypatch.delenv('SYNC_DURABLE_STATUS_RECONCILIATION')
    lookup = Mock(side_effect=AssertionError('dark path must not read Firestore'))
    monkeypatch.setattr(completed_status, 'get_firestore_client', lookup)
    receipt(database)
    assert client.get('/v2/sync-local-files/original').status_code == 404
    sync_jobs.create_sync_job('owner', 1, 1, 'original', content_id='content')
    assert client.get('/v2/sync-local-files/original').json()['status'] == 'queued'
    lookup.assert_not_called()
