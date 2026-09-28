"""Recovery eligibility is decided entirely from operational metadata."""

from scripts.recover_dev_failed_sync_backfill import selection_reason

import fakeredis
from unittest.mock import MagicMock

from database import sync_dead_letters, sync_jobs, sync_ledger
from utils.cloud_tasks import SYNC_JOB_TASK_PAYLOAD_KEYS


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


def test_dev_sync_job_and_run_lock_keys_cannot_see_prod(monkeypatch):
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    sync_jobs.create_sync_job('u', 1, 0, job_id='shared-id', lane='backfill')
    token = sync_jobs.try_acquire_job_run_lock('shared-id')
    assert token
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert sync_jobs.get_raw_sync_job('shared-id') is None
    assert not sync_jobs.sync_job_run_lock_present('shared-id')
    assert sync_jobs.try_acquire_job_run_lock('shared-id')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    assert sync_jobs.get_raw_sync_job('shared-id')['uid'] == 'u'
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
