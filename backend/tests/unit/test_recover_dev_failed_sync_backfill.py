"""Recovery eligibility is decided entirely from operational metadata."""

from scripts import recover_dev_failed_sync_backfill as recovery
from scripts.recover_dev_failed_sync_backfill import selection_reason

import fakeredis
import pytest
from unittest.mock import MagicMock

from database import sync_backfill_sequencer, sync_dead_letters, sync_jobs, sync_ledger
from utils.cloud_tasks import SYNC_JOB_TASK_PAYLOAD_KEYS
from utils.sync import uid_sequencer


def _candidate():
    uid, job_id = 'uid-1', 'job-1'
    payload = {key: None for key in SYNC_JOB_TASK_PAYLOAD_KEYS}
    payload.update(
        {
            'uid': uid,
            'job_id': job_id,
            'lane': 'backfill',
            'raw_blob_paths': [f'syncing/{uid}/{job_id}/part.bin'],
            'content_id': 'content-1',
        }
    )
    row = {
        'uid': uid,
        'job_id': job_id,
        'failure_origin': 'dev',
        'origin_evidence': 'dev_log',
        'failure_code': 'sync_staged_audio_expired',
        'payload': payload,
    }
    job = {
        'uid': uid,
        'job_id': job_id,
        'status': 'failed',
        'reason_code': 'sync_staged_audio_expired',
        'content_id': 'content-1',
    }
    return row, job


def test_recovery_requires_dev_evidence_and_prod_blob_metadata():
    row, job = _candidate()
    assert selection_reason(row, job, True) == 'ready'
    assert selection_reason(row, job, False) == 'staged_audio_missing'
    row['failure_origin'] = 'prod'
    assert selection_reason(row, job, True) == 'unproven_dev_failure'
    row['failure_origin'] = 'dev'
    job['failure_stage'] = 'prod'
    assert selection_reason(row, job, True) == 'worker_marker_mismatch'


def test_recovery_rejects_unrelated_or_unsafe_payload():
    row, job = _candidate()
    row['payload']['unexpected'] = 'metadata'
    assert selection_reason(row, job, True) == 'invalid_payload_schema'
    row, job = _candidate()
    row['payload']['raw_blob_paths'] = ['syncing/other/job-1/part.bin']
    assert selection_reason(row, job, True) == 'invalid_staged_paths'
    row, job = _candidate()
    job['status'] = 'completed'
    assert selection_reason(row, job, True) == 'job_not_matching_failure'
    row, job = _candidate()
    row['payload']['content_id'] = 'other-content'
    assert selection_reason(row, job, True) == 'content_identity_missing'


def test_expired_redis_job_requires_timestamped_dev_failure_event():
    row, _ = _candidate()
    assert selection_reason(row, None, True) == 'job_metadata_missing'
    row['failure_at'] = '2026-09-28T16:30:00Z'
    assert selection_reason(row, None, True) == 'ready'


@pytest.mark.parametrize('interrupt_after', ['create', 'claim', 'register', 'kick'])
def test_recovery_resumes_each_partial_apply_and_dispatches_once(monkeypatch, interrupt_after):
    row, old_job = _candidate()
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    state = {'job': None, 'claim': None, 'registered': False, 'dispatched': False}
    calls = {'create': 0, 'register': 0, 'dispatch': 0}
    interrupted = False

    def interrupt(step):
        nonlocal interrupted
        if step == interrupt_after and not interrupted:
            interrupted = True
            raise RuntimeError(f'interrupted after {step}')

    def get_job(job_id):
        return state['job']

    def create_job(uid, total_files, total_segments, **kwargs):
        calls['create'] += 1
        state['job'] = {
            'job_id': kwargs['job_id'],
            'uid': uid,
            'content_id': kwargs['content_id'],
            'lane': kwargs['lane'],
            'dispatch_mode': kwargs['dispatch_mode'],
            'created_stage': 'prod',
            'status': 'queued',
        }
        interrupt('create')
        return state['job']

    def claim(uid, content_id, job_id, lane):
        assert state['job'] is not None
        assert state['claim'] in (None, job_id)
        state['claim'] = job_id
        interrupt('claim')
        return {'outcome': 'owned'}

    def register(uid, job_id, payload, captured_at):
        assert state['claim'] == job_id
        assert not state['registered']
        calls['register'] += 1
        state['registered'] = True
        interrupt('register')
        return True

    def kick(uid):
        assert state['registered']
        if not state['dispatched']:
            calls['dispatch'] += 1
            state['dispatched'] = True
        interrupt('kick')
        return True

    monkeypatch.setattr(sync_jobs, 'get_sync_job', get_job)
    monkeypatch.setattr(sync_jobs, 'create_sync_job', create_job)
    monkeypatch.setattr(sync_ledger, 'claim_sync_content', claim)
    monkeypatch.setattr(sync_backfill_sequencer, 'is_registered', lambda uid, job_id: state['registered'])
    monkeypatch.setattr(sync_backfill_sequencer, 'register_job', register)
    monkeypatch.setattr(uid_sequencer, 'kick', kick)

    with pytest.raises(RuntimeError, match=f'interrupted after {interrupt_after}'):
        recovery._requeue(row, old_job)
    new_id = recovery._requeue(row, old_job)
    assert new_id == state['job']['job_id']
    assert recovery._requeue(row, old_job) == new_id
    assert calls == {'create': 1, 'register': 1, 'dispatch': 1}


def test_recovery_rejects_existing_job_with_wrong_identity_or_terminal_status(monkeypatch):
    row, old_job = _candidate()
    existing = {
        'job_id': 'different',
        'uid': row['uid'],
        'content_id': row['payload']['content_id'],
        'lane': 'backfill',
        'dispatch_mode': 'sequenced',
        'created_stage': 'prod',
        'status': 'queued',
    }
    monkeypatch.setattr(sync_jobs, 'get_sync_job', lambda _job_id: existing)
    assert recovery._requeue(row, old_job) == 'recovery_job_mismatch'
    existing['job_id'] = str(
        recovery.uuid.uuid5(recovery.uuid.NAMESPACE_URL, f"omi:dev-failed-backfill:{row['job_id']}")
    )
    existing['status'] = 'failed'
    assert recovery._requeue(row, old_job) == 'recovery_job_started_or_terminal'


def test_dev_sync_job_and_run_lock_keys_cannot_see_prod(monkeypatch):
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    sync_jobs.create_sync_job('u', 1, 0, job_id='shared-id', lane='backfill')
    token = sync_jobs.try_acquire_job_run_lock('shared-id')
    assert token
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert sync_jobs.get_sync_job('shared-id') is None
    assert not sync_jobs.sync_job_run_lock_present('shared-id')
    assert sync_jobs.try_acquire_job_run_lock('shared-id')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    assert sync_jobs.get_sync_job('shared-id')['uid'] == 'u'
    assert sync_jobs.sync_job_run_lock_present('shared-id')


def test_dev_sync_firestore_metadata_uses_separate_collections(monkeypatch):
    client = MagicMock()
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    sync_ledger._ledger_ref(client, 'u', 'content')
    sync_dead_letters._doc_ref(client, 'job')
    assert client.collection.call_args.args == ('sync_dead_letters',)
    assert client.collection('users').document('u').collection.call_args.args == ('sync_content_ledger',)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    sync_ledger._ledger_ref(client, 'u', 'content')
    sync_dead_letters._doc_ref(client, 'job')
    assert client.collection.call_args.args == ('sync_dead_letters_dev',)
    assert client.collection('users').document('u').collection.call_args.args == ('sync_content_ledger_dev',)
