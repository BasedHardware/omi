"""Admission diagnostics distinguish custody waits without releasing client audio."""

import io
import json
import logging
import wave
from copy import deepcopy
from types import SimpleNamespace

import pytest

from config.policy import BatchUnitPolicy
from database.firestore_transaction_retry import FirestoreContentionExhausted
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import intake, live_upload
from utils.batch_pipeline.contracts import Priority


@pytest.fixture(autouse=True)
def explicit_stage(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')


@pytest.fixture(autouse=True)
def record_wait_memo(monkeypatch):
    memo = {}
    # This suite isolates pending diagnostics; WAL memo behavior has its own
    # expiry-aware Redis fake in test_sync_record_coverage_wait_memo.py.
    monkeypatch.setattr(live_upload, 'cached_coverage_wait', lambda *_: False)
    monkeypatch.setattr(live_upload, 'remember_coverage_wait', lambda *_: None)
    monkeypatch.setattr(
        live_upload, 'remember_record_wait', lambda uid, cid, reason: memo.__setitem__((uid, cid), reason)
    )
    monkeypatch.setattr(live_upload, 'cached_record_wait', lambda uid, cid: memo.get((uid, cid)))
    return memo


@pytest.mark.parametrize(
    'case,expected',
    [
        ('reservation', 'reservation_pending'),
        ('mismatch', 'owner_context_mismatch'),
        ('missing_jobs', 'record_jobs_missing'),
        ('prior_content', 'content_receipt_conflict'),
        ('uncovered', 'audio_coverage_unproven'),
        ('failed_check', 'coverage_check_failed'),
        ('artifact_failed', 'artifact_lookup_failed'),
        ('alias_failed', 'alias_write_failed'),
        ('status_failed', 'receipt_status_read_failed'),
    ],
)
async def test_record_wait_reason_retains_custody_without_alias(monkeypatch, caplog, case, expected):
    store = MemoryStore()
    uid, conversation = 'synthetic-owner', 'synthetic-conversation'
    content, _ = live_upload.record_identity(uid, conversation)
    row = {'record_lane_owner': live_upload.OWNER, 'source': 'omi', 'client_device_id': 'synthetic-device'}
    store.rows['intakes', 'bp_' + content] = {'segment_ids': ['synthetic-segment']}
    store.rows['jobs', 'synthetic-segment'] = {'segment_id': 'synthetic-segment'}
    store.rows['content', f'{uid}/{content}'] = {
        'status': 'processing',
        'dispatch_protocol': 'batch_v1',
        'job_id': 'bp_' + content,
    }
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: store)
    monkeypatch.setattr(live_upload, 'artifacts_for', lambda *_: object())
    monkeypatch.setattr(live_upload, '_covered', lambda *_: False)
    monkeypatch.setattr(live_upload, 'record_capture_eligible', lambda *a, **kw: True)
    if case == 'reservation':
        row.pop('record_lane_owner')
        row['status'] = 'in_progress'
    elif case == 'mismatch':
        row['client_device_id'] = 'other-synthetic-device'
    elif case == 'missing_jobs':
        store.rows['intakes', 'bp_' + content]['segment_ids'] = []
    elif case == 'prior_content':
        store.rows['content', f'{uid}/synthetic-content'] = {'status': 'processing'}
    elif case in {'failed_check', 'artifact_failed', 'alias_failed', 'status_failed'}:

        def fail(*_):
            raise RuntimeError('sensitive@example.test users/0123456789012345678901234567/jobs/private-job')

        if case == 'failed_check':
            monkeypatch.setattr(live_upload, '_covered', fail)
        elif case == 'artifact_failed':
            monkeypatch.setattr(live_upload, 'artifacts_for', fail)
        else:
            monkeypatch.setattr(live_upload, '_covered', lambda *_: True)
            if case == 'status_failed':
                monkeypatch.setattr(live_upload, 'durable_status', fail)
            else:
                original_run = store.run
                calls = 0

                def fail_alias(body):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        return fail()
                    return original_run(body)

                monkeypatch.setattr(store, 'run', fail_alias)
    before = deepcopy(store.rows)
    with caplog.at_level(logging.INFO, logger=live_upload.__name__):
        response = await live_upload.registered_record_response(
            uid=uid,
            conversation_id=conversation,
            content_id='synthetic-content',
            paths=['synthetic-audio.bin'],
            source='omi',
            client_device_id='synthetic-device',
            loaded_conversation=row,
            policy=BatchUnitPolicy(batch_enabled=True, live_admission_enabled=True, live_record_enabled=True),
        )
    assert response.status_code == 503
    # A conversation-scoped wait must not pause the account's whole drain.
    assert 'retry-after' not in response.headers
    assert json.loads(response.body) == {
        'code': 'record_capture_pending',
        'detail': 'Retain local audio until the registered record is complete',
        'retry_after_seconds': 30,
    }
    if case == 'status_failed':
        # The alias committed before the read failed; the client still keeps
        # its audio, and the next retry can reuse that durable receipt.
        after = deepcopy(store.rows)
        alias = after.pop(('content', f'{uid}/synthetic-content'))
        assert alias['record_content_id'] == content
        assert alias['job_id'] == 'bp_' + content
        assert after == before
    else:
        assert store.rows == before
    messages = [record.getMessage() for record in caplog.records]
    # A hashed record key groups waits per recording; raw ids never reach the log.
    record = '-' if case == 'mismatch' else content[:16]
    assert messages == [f'event=sync_record_upload outcome=pending reason={expected} record={record}']
    assert uid not in messages[0] and conversation not in messages[0]


async def test_conversation_level_wait_is_memoized_and_repeated_without_upload_work(record_wait_memo):
    response = await live_upload.conversation_pending(
        live_upload.RecordUploadWait.RECORD_JOBS_MISSING, 'synthetic-owner', 'synthetic-conversation'
    )
    assert response.status_code == 503
    repeated = await live_upload.memoized_record_wait('synthetic-owner', 'synthetic-conversation')
    assert repeated is not None and repeated.status_code == 503
    assert 'retry-after' not in repeated.headers
    assert json.loads(bytes(repeated.body))['code'] == 'record_capture_pending'
    # Another conversation of the same owner is never held by this memo.
    assert await live_upload.memoized_record_wait('synthetic-owner', 'other-conversation') is None


async def test_content_level_wait_is_not_memoized(record_wait_memo):
    await live_upload.conversation_pending(
        live_upload.RecordUploadWait.AUDIO_COVERAGE_UNPROVEN, 'synthetic-owner', 'synthetic-conversation'
    )
    assert record_wait_memo == {}
    assert await live_upload.memoized_record_wait('synthetic-owner', 'synthetic-conversation') is None


async def test_unknown_or_missing_memo_falls_through(record_wait_memo):
    record_wait_memo[('synthetic-owner', 'synthetic-conversation')] = 'not-a-reason'
    assert await live_upload.memoized_record_wait('synthetic-owner', 'synthetic-conversation') is None
    assert await live_upload.memoized_record_wait('synthetic-owner', None) is None


async def test_intake_contention_logs_phase_and_monotonic_elapsed_without_error_text(monkeypatch, caplog):
    def fail(*_):
        raise FirestoreContentionExhausted('sensitive@example.test users/0123456789012345678901234567/jobs/private-job')

    monkeypatch.setattr(intake, 'FirestoreStore', fail)
    clock = iter((10.0, 10.5))
    monkeypatch.setattr(intake, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    with caplog.at_level(logging.ERROR, logger=intake.__name__):
        response = await intake.accept_upload(
            uid='synthetic-owner',
            job_id='synthetic-job',
            content_id='synthetic-content',
            paths=[],
            lane='fresh',
            recording_age_seconds=1,
            source='omi',
            should_lock=False,
            conversation_id=None,
            client_device_id=None,
            client_platform='ios',
            policy=BatchUnitPolicy(batch_enabled=True),
        )
    assert response.status_code == 503
    assert response.headers['retry-after'] == '30'
    assert json.loads(response.body)['code'] == 'sync_batch_unavailable'
    assert [record.getMessage() for record in caplog.records] == [
        'event=batch_intake outcome=retry exception_type=FirestoreContentionExhausted phase=receipt_read elapsed_ms=500'
    ]


def _wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(pcm)
    return buffer.getvalue()


@pytest.mark.parametrize(
    'wal_start,wal_pcm,cause',
    [
        (0.0, b'\x01\x00' * 16000, None),
        (-0.5, b'\x01\x00' * 16000, 'wal_audio_outside_record'),
        (0.0, b'\x02\x00' * 16000, 'audio_bytes_differ'),
        (0.5, b'\x01\x00' * 16000, 'wal_audio_past_record'),
    ],
)
def test_coverage_failure_logs_which_way_the_wal_and_record_disagree(monkeypatch, caplog, wal_start, wal_pcm, cause):
    record_pcm = b'\x01\x00' * 16000  # one second of the record at t=0
    unit = SimpleNamespace(wav=_wav(wal_pcm), capture_at=wal_start, duration_seconds=1.0)
    monkeypatch.setattr(live_upload, 'decode_units', lambda paths: iter([unit]))
    job = {
        'segment_id': 'synthetic-segment',
        'owner_id': 'synthetic-owner',
        'capture_at': 0.0,
        'audio_uri': 'synthetic-uri',
        'duration_seconds': 1.0,
        'priority': Priority.FRESH,
    }
    artifacts = SimpleNamespace(fetch_audio=lambda item: _wav(record_pcm))
    with caplog.at_level(logging.INFO, logger=live_upload.__name__):
        covered = live_upload._covered(['synthetic-audio.bin'], [job], artifacts)
    assert covered is (cause is None)
    messages = [record.getMessage() for record in caplog.records]
    assert messages == ([] if cause is None else [f'event=sync_record_coverage outcome=unproven cause={cause}'])
