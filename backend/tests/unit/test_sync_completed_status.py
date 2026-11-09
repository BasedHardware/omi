"""Real HTTP polling plus durable receipts; no provider work or store writes."""

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import Mock

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import sync_jobs
from database.batch_pipeline_privacy import BatchPrivacyBlocked, BatchPrivacyReason, privacy_owner_key
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


# Shared with the real Dart WAL/poller tests, not a copy of client policy.
PRIVACY_CASES = json.loads((Path(__file__).parents[1] / 'fixtures/sync_status_privacy_cases.json').read_text())


def apply_fence(database, case):
    user = database.rows['users', 'owner']
    conversation = ('users', 'owner', 'conversations', 'target')
    database.rows[conversation] = {}
    privacy = ('batch_pipeline_privacy', privacy_owner_key('owner'))
    if case == 'account_deleted':
        database.rows['account_deletions', 'owner'] = {'wipe_status': 'completed'}
    elif case == 'account_invalid_marker':
        database.rows['account_deletions', 'owner'] = {}
    elif case == 'account_missing':
        database.rows.pop(('users', 'owner'))
    elif case == 'e2ee':
        user['data_protection_level'] = 'e2ee'
    elif case == 'migration':
        user['migration_status'] = 'in_progress'
    elif case in {'privacy_blocked', 'privacy_purging'}:
        database.rows[privacy] = {
            'generation': 1,
            'blocked': case == 'privacy_blocked',
            'purging': case == 'privacy_purging',
        }
    elif case == 'conversation_tombstone':
        database.rows['users', 'owner', 'deleted_conversations', 'target'] = {}
    elif case == 'conversation_deleted':
        database.rows[conversation] = {'deleted': True}
    elif case == 'redirect_cycle':
        database.rows[conversation] = {'deleted': True, 'sync_merged_into': 'target'}
    elif case == 'redirect_missing':
        database.rows[conversation] = {'deleted': True, 'sync_merged_into': 'missing'}
    elif case == 'fence_budget':
        # A real chain crossing the fence's bounded read budget.
        for i in range(257):
            name = 'target' if i == 0 else f'target-{i}'
            database.rows['users', 'owner', 'conversations', name] = {
                'deleted': True,
                'sync_merged_into': f'target-{i + 1}',
            }
    elif case in {'custom_stt', 'owner_opt_out', 'source_opt_out'}:
        user['private_cloud_sync_enabled'] = case != 'owner_opt_out'
        database.rows[conversation] = {
            'record_lane_owner': 'batch_live_v1',
            'uses_custom_stt': case == 'custom_stt',
            'private_cloud_sync_enabled': case != 'source_opt_out',
        }
    else:
        raise AssertionError(f'unimplemented fence case: {case}')


DELETION_CASES = [case for case in PRIVACY_CASES if case['reason'] == 'conversation_deleted']
DENIAL_CASES = [case for case in PRIVACY_CASES if case['reason'] != 'conversation_deleted']


@pytest.mark.parametrize('case', DELETION_CASES, ids=lambda case: case['case'])
@pytest.mark.parametrize('state', [None, 'queued', 'processing', 'failed', 'partial_failure'])
def test_user_deletion_completes_terminally_without_ids(poll, monkeypatch, caplog, case, state):
    import logging

    caplog.set_level(logging.INFO)
    client, database = poll
    receipt(
        database,
        result={
            'total_segments': 2,
            'failed_segments': 0,
            'errors': [],
            'outcome': 'success',
            'new_memories': ['target'],
            'updated_memories': ['survivor'],
        },
    )
    database.rows['users', 'owner', 'conversations', 'survivor'] = {}
    apply_fence(database, case['case'])
    if state is not None:
        sync_jobs.create_sync_job('owner', 1, 1, 'original', content_id='content')
        sync_jobs.update_sync_job('original', {'status': state, 'reason_code': 'sync_worker_stale'})
    before = deepcopy(database.rows)
    redis_before = sync_jobs.get_sync_job('original')
    response = client.get('/v2/sync-local-files/original')
    assert response.status_code == 200
    body = response.json()
    assert body['job_id'] == 'original' and body['status'] == 'completed'
    assert body['reason_code'] == 'conversation_deleted'
    assert body['result'] == {
        'new_memories': [],
        'updated_memories': [],
        'failed_segments': 0,
        'total_segments': 2,
        'errors': [],
    }
    assert 'target' not in response.text and 'survivor' not in response.text
    assert 'outcome=conversation_deleted_terminal' in caplog.text
    assert database.rows == before
    assert sync_jobs.get_sync_job('original') == redis_before


@pytest.mark.parametrize('status', ['processing', 'retryable'])
def test_user_deletion_never_completes_unproven_work(poll, status):
    client, database = poll
    result = {'total_segments': 1, 'failed_segments': 0, 'errors': [], 'outcome': 'success', 'new_memories': ['target']}
    receipt(database, result=result, status=status)
    apply_fence(database, 'conversation_tombstone')
    assert client.get('/v2/sync-local-files/original').status_code == 404


@pytest.mark.parametrize('order', [['target', 'donor'], ['donor', 'target']])
def test_user_deletion_beside_redirect_failure_never_acks(poll, order):
    # The fence walk stops at the first denied ID of an unordered set; the
    # answer must not depend on which one it reaches first.
    client, database = poll
    result = {'total_segments': 1, 'failed_segments': 0, 'errors': [], 'outcome': 'success', 'new_memories': order}
    receipt(database, result=result)
    apply_fence(database, 'conversation_tombstone')
    database.rows['users', 'owner', 'conversations', 'donor'] = {'deleted': True, 'sync_merged_into': 'missing'}
    assert client.get('/v2/sync-local-files/original').status_code == 404


def test_account_denial_dominates_user_deletion(poll):
    client, database = poll
    result = {'total_segments': 1, 'failed_segments': 0, 'errors': [], 'outcome': 'success', 'new_memories': ['target']}
    receipt(database, result=result)
    apply_fence(database, 'conversation_tombstone')
    database.rows['account_deletions', 'owner'] = {'wipe_status': 'completed'}
    assert client.get('/v2/sync-local-files/original').status_code == 404


@pytest.mark.parametrize('case', DENIAL_CASES, ids=lambda case: case['case'])
@pytest.mark.parametrize('state', [None, 'queued', 'processing', 'failed', 'partial_failure'])
def test_privacy_denial_matches_old_contract_without_ack(poll, monkeypatch, caplog, case, state):
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
    apply_fence(database, case['case'])
    if state is not None:
        sync_jobs.create_sync_job('owner', 1, 1, 'original', content_id='content')
        sync_jobs.update_sync_job('original', {'status': state, 'reason_code': 'sync_worker_stale'})
    monkeypatch.setenv('SYNC_DURABLE_STATUS_RECONCILIATION', 'false')
    legacy = client.get('/v2/sync-local-files/original')
    before = deepcopy(database.rows)
    redis_before = sync_jobs.get_sync_job('original')
    monkeypatch.setenv('SYNC_DURABLE_STATUS_RECONCILIATION', 'true')
    response = client.get('/v2/sync-local-files/original')
    assert response.status_code == legacy.status_code == (404 if state is None else 200)
    assert response.json() == legacy.json()
    assert response.json().get('status') != 'completed'
    assert 'retry-after' not in response.headers
    assert f'outcome=privacy_blocked fence_reason={case["reason"]}' in caplog.text
    assert database.rows == before
    assert sync_jobs.get_sync_job('original') == redis_before


@pytest.mark.parametrize(
    'read', ['account_deletions', 'users', 'batch_pipeline_privacy', 'deleted_conversations', 'conversations']
)
def test_fence_read_errors_remain_retryable(poll, monkeypatch, read):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

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
    original = StrictFirestoreDocument.get

    def fail_read(reference, *args, **kwargs):
        if reference.path[-2] == read:
            raise RuntimeError('synthetic read unavailable')
        return original(reference, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', fail_read)
    response = client.get('/v2/sync-local-files/original')
    assert response.status_code == 503
    assert response.headers['retry-after'] == '10'


@pytest.mark.parametrize('reason', [(), ('unsafe-owner-or-content',), (None,), ({'unsafe': 'value'},)])
def test_unknown_privacy_reason_is_bounded(poll, monkeypatch, caplog, reason):
    client, database = poll
    receipt(database)
    monkeypatch.setattr(completed_status, 'assert_batch_write_allowed', Mock(side_effect=BatchPrivacyBlocked(*reason)))
    response = client.get('/v2/sync-local-files/original')
    assert response.status_code == 404
    assert 'fence_reason=unknown' in caplog.text
    assert 'unsafe' not in caplog.text


def test_all_known_privacy_reasons_are_bounded():
    for reason in BatchPrivacyReason:
        assert BatchPrivacyBlocked(reason.value).reason is reason


@pytest.mark.parametrize('marker', [None, 'cancelled', 'billing_failed'])
def test_missing_protection_document_and_nonblocking_markers_allow_proven_completion(poll, marker):
    client, database = poll
    receipt(database)
    if marker is not None:
        database.rows['account_deletions', 'owner'] = {'wipe_status': marker}
    assert client.get('/v2/sync-local-files/original').json()['status'] == 'completed'


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


HELD = {'total_segments': 1, 'failed_segments': 0, 'errors': [], 'outcome': 'success', 'held_audio': True}


def test_expired_cap_hold_handle_reaches_a_terminal_poll(poll):
    """M1 review L10-2: the dark fence ACKs a valid hold with its ledger job id and
    writes no Redis job; after the TTL the poll must answer it, not 404 forever."""
    client, database = poll
    database.collection('users').document('owner').collection('sync_content_ledger').document('content').create(
        {'dispatch_protocol': 'stt_cap_hold_v1', 'status': 'held', 'job_id': 'original', 'result': HELD}
    )
    before = deepcopy(database.rows)
    response = client.get('/v2/sync-local-files/original')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'completed' and body['result']['held_audio'] is True
    assert database.rows == before


@pytest.mark.parametrize(
    'row',
    [
        {'status': 'held', 'job_id': 'original', 'result': HELD},
        {
            'dispatch_protocol': 'stt_cap_hold_v1',
            'status': 'held',
            'job_id': 'original',
            'result': {**HELD, 'errors': ['x']},
        },
        {'dispatch_protocol': 'stt_cap_hold_v1', 'status': 'processing', 'job_id': 'original', 'result': HELD},
    ],
    ids=['no-hold-protocol', 'invalid-hold', 'not-held'],
)
def test_only_a_valid_cap_hold_is_acknowledged(poll, row):
    client, database = poll
    database.collection('users').document('owner').collection('sync_content_ledger').document('content').create(row)
    assert client.get('/v2/sync-local-files/original').status_code == 404
