"""Real HTTP polling of expiry-retired legacy handles held in custody; reads only."""

from copy import deepcopy

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import sync_jobs
from routers import sync as router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.sync import completed_status, retired_handle_ack


@pytest.fixture
def poll(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_DURABLE_STATUS_RECONCILIATION', 'true')
    monkeypatch.delenv('SYNC_RETIRED_HANDLE_ACK_ENABLED', raising=False)
    monkeypatch.setattr(router, 'admit_sync_job_poll', lambda uid: True)
    monkeypatch.setattr(sync_jobs, 'r', fakeredis.FakeRedis())
    database = StrictFirestore({('users', 'owner'): {'data_protection_level': 'standard'}})
    monkeypatch.setattr(completed_status, 'get_firestore_client', lambda: database)
    monkeypatch.setattr(retired_handle_ack, 'get_firestore_client', lambda: database)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: 'owner'
    with TestClient(app) as client:
        yield client, database
    assert all(not tx.has_written for tx in database.transactions)


def custody(database, *, job='retired', owner='owner', content='content', admit=True, **extra):
    database.collection('sync_retired_handles').document(job).create(
        {'uid': owner, 'job_id': job, 'content_id': content, 'campaign': 'preserve-20261018', **extra}
    )
    if admit is not None:
        database.collection('sync_retired_handle_owners').document(owner).create({'enabled': admit})


def test_admitted_custody_handle_is_acknowledged_without_mutation(poll):
    client, database = poll
    custody(database)
    database.collection('users').document('owner').collection('sync_content_ledger').document('content').create(
        {'status': 'retryable'}
    )
    before = deepcopy(database.rows)
    response = client.get('/v2/sync-local-files/retired')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'completed' and body['job_id'] == 'retired'
    assert body['reason_code'] == 'sync_retired_preserved'
    assert body['total_segments'] == body['failed_segments'] == 0
    assert body['result']['new_memories'] == body['result']['updated_memories'] == []
    assert body['result']['errors'] == []
    assert database.rows == before


def test_unknown_handle_keeps_404(poll):
    client, _ = poll
    assert client.get('/v2/sync-local-files/unknown').status_code == 404


@pytest.mark.parametrize('admit', [None, False])
def test_unadmitted_owner_keeps_404(poll, admit):
    client, database = poll
    custody(database, admit=admit)
    assert client.get('/v2/sync-local-files/retired').status_code == 404


def test_other_owners_handle_is_never_acknowledged(poll):
    client, database = poll
    custody(database, owner='someone-else')
    database.collection('sync_retired_handle_owners').document('owner').create({'enabled': True})
    assert client.get('/v2/sync-local-files/retired').status_code == 404


def test_record_bound_to_another_handle_declines(poll):
    client, database = poll
    database.collection('sync_retired_handles').document('retired').create(
        {'uid': 'owner', 'job_id': 'other', 'content_id': 'content'}
    )
    database.collection('sync_retired_handle_owners').document('owner').create({'enabled': True})
    assert client.get('/v2/sync-local-files/retired').status_code == 404


@pytest.mark.parametrize('value', ['false', 'off', '0', 'typo'])
def test_kill_switch_restores_404(poll, monkeypatch, value):
    client, database = poll
    custody(database)
    monkeypatch.setenv('SYNC_RETIRED_HANDLE_ACK_ENABLED', value)
    assert client.get('/v2/sync-local-files/retired').status_code == 404


def test_real_completion_wins_over_archival_ack(poll):
    client, database = poll
    custody(database)
    database.collection('users').document('owner').collection('sync_content_ledger').document('content').create(
        {
            'status': 'completed',
            'job_id': 'retired',
            'result': {'total_segments': 2, 'failed_segments': 0, 'errors': [], 'outcome': 'success'},
        }
    )
    body = client.get('/v2/sync-local-files/retired').json()
    assert body['status'] == 'completed' and body['total_segments'] == 2
    assert body.get('reason_code') is None


def test_live_redis_job_is_never_shadowed(poll):
    client, database = poll
    custody(database)
    sync_jobs.create_sync_job('owner', 1, 1, 'retired', content_id='content')
    body = client.get('/v2/sync-local-files/retired').json()
    assert body['status'] != 'completed' or body.get('reason_code') != 'sync_retired_preserved'


def test_deleted_account_declines(poll):
    client, database = poll
    custody(database)
    database.collection('account_deletions').document('owner').create({'wipe_status': 'completed'})
    assert client.get('/v2/sync-local-files/retired').status_code == 404


def test_lookup_failure_fails_open_to_404(poll, monkeypatch):
    client, database = poll
    custody(database)

    def boom():
        raise RuntimeError('firestore down')

    monkeypatch.setattr(retired_handle_ack, 'get_firestore_client', boom)
    assert client.get('/v2/sync-local-files/retired').status_code == 404


def test_batch_handles_are_out_of_scope():
    assert retired_handle_ack.get_retired_handle_ack('bp_abc', 'owner', firestore_client=object()) is None
