"""Native sealing wakes certified retries atomically and preserves live claims."""

import time

import pytest

from config.record_audio import record_identity
from tests.unit.test_record_audio_seal import records, PATH, env
from database.record_audio import seal_record_audio


@pytest.fixture(autouse=True)
def notify_off_independent_wake(monkeypatch):
    monkeypatch.delenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', raising=False)


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
        seal_tx = next(
            tx
            for tx in records.transactions
            if any(path == PATH and patch.get('record_audio_closed') for path, patch in tx.updates)
        )
        assert len(seal_tx.updates) == 2
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


@pytest.mark.parametrize('ledger_fails', [False, True])
@pytest.mark.parametrize('failure_site', ['transaction', 'observer'])
def test_post_seal_ledger_observes_atomic_wake_and_cannot_undo_it(records, monkeypatch, ledger_fails, failure_site):
    from database import pipeline_ledger

    monkeypatch.setenv('PIPELINE_LEDGER', 'true')
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
    attribute = '_commit' if failure_site == 'transaction' else 'advance'
    original = getattr(pipeline_ledger, attribute)
    observed = []

    def after_seal(*args, **kwargs):
        assert records.rows[PATH]['record_audio_closed'] is True
        assert records.rows[job_path]['available_at'] == 0
        observed.append(True)
        if ledger_fails:
            raise OSError('synthetic ledger failure after authoritative seal')
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline_ledger, attribute, after_seal)
    assert seal_record_audio('uid-at', 'record', firestore_client=records) is None
    assert observed == [True]
    seal_tx = next(
        tx
        for tx in records.transactions
        if any(path == PATH and patch.get('record_audio_closed') for path, patch in tx.updates)
    )
    assert (job_path, {'available_at': 0, 'record_intake_retry_at': None}) in seal_tx.updates
    assert any(path == PATH and isinstance(patch.get('record_sealed_at'), float) for path, patch in seal_tx.updates)
    later = records.transactions[records.transactions.index(seal_tx) + 1 :]
    assert all(path != job_path for tx in later for path, _ in tx.updates)
    if not ledger_fails:
        assert any(path[:3] == ('users', 'uid-at', 'pipeline_ledger') for tx in later for path, _ in tx.sets)
    assert records.rows[job_path]['available_at'] == 0
    assert records.rows[PATH]['record_audio_closed'] is True
