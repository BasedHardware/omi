"""Admission diagnostics distinguish custody waits without releasing client audio."""

import json
import logging
from copy import deepcopy
from types import SimpleNamespace

import pytest

from config.policy import BatchUnitPolicy
from database.firestore_transaction_retry import FirestoreContentionExhausted
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import intake, live_upload


@pytest.fixture(autouse=True)
def explicit_stage(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')


@pytest.mark.parametrize(
    'case,expected',
    [
        ('reservation', 'reservation_pending'),
        ('mismatch', 'owner_context_mismatch'),
        ('missing_jobs', 'record_jobs_missing'),
        ('prior_content', 'content_receipt_conflict'),
        ('uncovered', 'audio_coverage_unproven'),
        ('failed_check', 'coverage_check_failed'),
    ],
)
async def test_record_wait_reason_retains_custody_without_alias(monkeypatch, caplog, case, expected):
    store = MemoryStore()
    uid, conversation = 'synthetic-owner', 'synthetic-conversation'
    content, _ = live_upload.record_identity(uid, conversation)
    row = {'record_lane_owner': live_upload.OWNER, 'source': 'omi', 'client_device_id': 'synthetic-device'}
    store.rows['intakes', 'bp_' + content] = {'segment_ids': ['synthetic-segment']}
    store.rows['jobs', 'synthetic-segment'] = {'segment_id': 'synthetic-segment'}
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
    elif case == 'failed_check':

        def fail(*_):
            raise RuntimeError('sensitive@example.test users/0123456789012345678901234567/jobs/private-job')

        monkeypatch.setattr(live_upload, '_covered', fail)
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
    assert response.headers['retry-after'] == '30'
    assert json.loads(response.body) == {
        'code': 'record_capture_pending',
        'detail': 'Retain local audio until the registered record is complete',
    }
    assert store.rows == before
    messages = [record.getMessage() for record in caplog.records]
    assert messages == [f'event=sync_record_upload outcome=pending reason={expected}']


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
