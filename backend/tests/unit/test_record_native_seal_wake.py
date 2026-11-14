"""Native sealing wakes certified retries atomically and preserves live claims."""

import time

import pytest

from config.record_audio import record_identity
from tests.unit.test_record_audio_seal import records, PATH, env
from database.record_audio import seal_record_audio


@pytest.mark.parametrize('clock', ['due', 'retry', 'claim', 'stale_marker', 'unknown'])
def test_native_seal_preserves_claim_and_only_wakes_known_retry(records, clock):
    now = time.time()
    _, key = record_identity('uid-at', 'record')
    job_path = ('batch_pipeline_prod_jobs', key)
    available = now - 1 if clock == 'due' else now + 900
    job = dict(
        owner_id='uid-at',
        conversation_id='record',
        state='record_pending',
        enqueued_at=now - 30,
        available_at=available,
    )
    if clock == 'retry':
        job['record_intake_retry_at'] = available
    elif clock == 'stale_marker':
        job['record_intake_retry_at'] = available - 1
    elif clock == 'unknown':
        job['available_at'] = float('nan')
    records.rows[job_path] = job
    assert seal_record_audio('uid-at', 'record', firestore_client=records) is None
    assert records.rows[PATH]['record_audio_closed'] is True
    if clock in {'due', 'retry'}:
        assert records.rows[job_path]['available_at'] == 0
        assert records.rows[job_path]['record_intake_retry_at'] is None
        assert len(records.transactions[-1].updates) == 2
    elif clock != 'unknown':
        assert records.rows[job_path]['available_at'] == available
    else:
        assert str(records.rows[job_path]['available_at']) == 'nan'


@pytest.mark.parametrize('reason', ['producer', 'partial', 'failed', 'deleted'])
def test_unproven_native_seal_does_not_wake(records, reason):
    now = time.time()
    _, key = record_identity('uid-at', 'record')
    job_path = ('batch_pipeline_prod_jobs', key)
    records.rows[job_path] = dict(
        owner_id='uid-at',
        conversation_id='record',
        state='record_pending',
        enqueued_at=now - 30,
        available_at=now + 900,
        record_intake_retry_at=now + 900,
    )
    records.rows[PATH].update(
        {'record_upload_sessions': {'other': True}}
        if reason == 'producer'
        else (
            {'record_audio_partial': True}
            if reason == 'partial'
            else {'record_upload_failed': True} if reason == 'failed' else {'deleted': True}
        )
    )
    seal_record_audio('uid-at', 'record', firestore_client=records)
    assert records.rows[job_path]['available_at'] == now + 900


def test_native_wake_kill_switch_and_foreign_job_are_preserved(records, monkeypatch):
    now = time.time()
    _, key = record_identity('uid-at', 'record')
    path = ('batch_pipeline_prod_jobs', key)
    records.rows[path] = dict(
        owner_id='another',
        conversation_id='record',
        state='record_pending',
        enqueued_at=now - 30,
        available_at=now + 900,
        record_intake_retry_at=now + 900,
    )
    seal_record_audio('uid-at', 'record', firestore_client=records)
    assert records.rows[path]['available_at'] == now + 900
    records.rows[path]['owner_id'] = 'uid-at'
    monkeypatch.setenv('PUSHER_RECORD_SEAL_WAKE_ENABLED', 'false')
    seal_record_audio('uid-at', 'record', firestore_client=records)
    assert records.rows[path]['available_at'] == now + 900
