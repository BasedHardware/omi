"""Admission protocol fencing and rollback with synthetic content identities."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from database.batch_pipeline_intake import AdmissionDisabled, admit
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.intake import durable_status, get_durable_job_status
from utils.batch_pipeline.scheduler import owner_key

NAMESPACE = 'batch_pipeline_test_intake'


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')


def proposal(job='bp_first', segment='segment'):
    work = replace(item(segment, owner='synthetic-owner'), privacy_generation=0)
    binding = ProjectionBinding('synthetic-owner', job, 'content', (segment,))
    return [work], binding


def submit(store, works, binding, now=100):
    return admit(
        store,
        works,
        binding,
        now,
        namespace=NAMESPACE,
        intake={
            'owner_id': binding.owner_id,
            'owner_key': owner_key(binding.owner_id),
            'content_id': binding.content_id,
            'segment_ids': list(binding.segment_ids),
            'total_files': 1,
            'lane': 'backfill',
        },
    )


def test_competing_uploads_seal_one_protocol_and_one_public_job(cohort):
    store = MemoryStore()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda args: submit(store, *args), [proposal(), proposal('bp_second', 'other')]))
    assert outcomes[0]['job_id'] == outcomes[1]['job_id']
    assert sum(table == 'jobs' for table, _ in store.rows) == 1
    ledger = store.rows[('content', 'synthetic-owner/content')]
    assert ledger['dispatch_protocol'] == 'batch_v1'
    assert ledger['batch_pipeline']['namespace'] == NAMESPACE
    assert sum(table == 'intakes' for table, _ in store.rows) == 1


def test_rollback_retries_existing_route_but_never_admits_new_content(cohort, monkeypatch):
    store = MemoryStore()
    assert submit(store, *proposal())['outcome'] == 'batch'
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    assert submit(store, *proposal('bp_retry', 'retry')) == {'outcome': 'batch', 'job_id': 'bp_first'}
    works, binding = proposal('bp_new', 'new')
    with pytest.raises(AdmissionDisabled):
        submit(store, works, replace(binding, content_id='new-content'))
    assert ('jobs', 'new') not in store.rows


def test_legacy_owner_cannot_be_taken_even_when_redis_expired(cohort):
    store = MemoryStore()
    store.rows['content', 'synthetic-owner/content'] = {'status': 'processing', 'job_id': 'legacy', 'updated_at': 0}
    assert submit(store, *proposal()) == {'outcome': 'busy', 'job_id': 'legacy'}
    assert not any(table == 'jobs' for table, _ in store.rows)


def test_late_capture_admits_without_rewriting_high_watermark(cohort):
    store = MemoryStore()
    watermark = {'capture_at': 2, 'segment_id': 'committed'}
    store.rows['owners', owner_key('synthetic-owner')] = {'watermark': watermark}
    assert submit(store, *proposal())['outcome'] == 'batch'
    job = store.rows['jobs', 'segment']
    assert job['capture_at'] == 1 and job['late_capture'] and job['merge_pending']
    assert store.rows['owners', owner_key('synthetic-owner')]['watermark'] == watermark
    assert durable_status(store, 'synthetic-owner', 'bp_first')['status'] == 'queued'


def test_client_poll_redrives_historical_dead_even_after_admission_rollback(cohort, monkeypatch):
    from utils.batch_pipeline.scheduler import Scheduler

    store = MemoryStore()
    submit(store, *proposal())
    queue = Scheduler(store)
    queue.pull(100)
    store.rows['jobs', 'segment'].update(state='dead', token='', lease_until=0)
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    status = durable_status(store, 'synthetic-owner', 'bp_first')
    assert status['status'] == 'queued' and status['failed_segments'] == 0
    assert status['poll_after_ms'] == 3000
    assert queue.pull(9999999999)[0].item.segment_id == 'segment'
    assert sum(table == 'jobs' for table, _ in store.rows) == 1


def test_lost_admission_ack_retries_without_duplicate_queue_or_binding(cohort):
    store = MemoryStore()
    original = store.run

    def uncertain(body):
        original(body)
        raise TimeoutError('synthetic lost reply')

    store.run = uncertain
    with pytest.raises(TimeoutError):
        submit(store, *proposal())
    store.run = original
    assert submit(store, *proposal('bp_retry', 'retry'))['job_id'] == 'bp_first'
    assert sum(table == 'jobs' for table, _ in store.rows) == 1


def test_status_is_durable_and_completed_result_is_authoritative(cohort):
    store = MemoryStore()
    submit(store, *proposal())
    assert durable_status(store, 'synthetic-owner', 'bp_first')['status'] == 'queued'
    ledger = store.rows['content', 'synthetic-owner/content']
    ledger.update(
        status='completed',
        result={'new_memories': [], 'updated_memories': [], 'failed_segments': 0, 'total_segments': 1, 'errors': []},
    )
    assert durable_status(store, 'synthetic-owner', 'bp_first')['status'] == 'completed'
    with pytest.raises(Exception) as error:
        durable_status(store, 'foreign-owner', 'bp_first')
    assert error.value.status_code == 403


def test_legacy_poll_has_no_new_store_or_stage_lookup(monkeypatch):
    def forbidden(*args):
        raise AssertionError('legacy poll touched durable batch store')

    monkeypatch.setattr('utils.batch_pipeline.intake.FirestoreStore', forbidden)
    monkeypatch.setattr('utils.batch_pipeline.intake.current_stage', forbidden)
    assert get_durable_job_status('legacy-uuid', 'synthetic-owner') is None


def test_expired_route_receipt_cannot_rebind_a_retained_segment(cohort):
    store = MemoryStore()
    submit(store, *proposal())
    original = dict(store.rows['jobs', 'segment']['projection_binding'])
    del store.rows['content', 'synthetic-owner/content']
    with pytest.raises(ValueError, match='immutable intake binding'):
        submit(store, *proposal('bp_relabel'))
    assert store.rows['jobs', 'segment']['projection_binding'] == original
    assert ('content', 'synthetic-owner/content') not in store.rows


def test_completed_legacy_content_gets_durable_alias_without_gpu_or_redis(cohort):
    from database.batch_pipeline_intake import cache_completed

    store = MemoryStore()
    result = {
        'new_memories': ['conversation'],
        'updated_memories': [],
        'failed_segments': 0,
        'total_segments': 2,
        'errors': [],
    }
    store.rows['content', 'synthetic-owner/content'] = {'status': 'completed', 'job_id': 'old', 'result': result}
    assert cache_completed(
        store,
        'synthetic-owner',
        'content',
        'bp_cached',
        {
            'owner_key': owner_key('synthetic-owner'),
            'total_files': 1,
            'lane': 'backfill',
        },
        100,
    )
    status = durable_status(store, 'synthetic-owner', 'bp_cached')
    assert status['status'] == 'completed' and status['total_segments'] == 2
    assert status['result'] == result
    assert not any(table == 'jobs' for table, _ in store.rows)


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['processing', 'retryable', 'completed'])
async def test_prior_legacy_receipt_uses_canonical_legacy_recovery_without_staging(monkeypatch, status):
    from utils.batch_pipeline import intake

    store = MemoryStore()
    store.rows['content', 'synthetic-owner/content'] = {'status': status, 'job_id': 'expired-legacy'}
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **kw: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')

    def forbidden(*args, **kwargs):
        raise AssertionError('legacy receipt entered batch staging')

    monkeypatch.setattr(intake, 'decode_units', forbidden)
    monkeypatch.setattr(intake, 'artifacts_for', forbidden)
    response = await intake.accept_upload(
        uid='synthetic-owner',
        job_id='retry',
        content_id='content',
        paths=['retained.bin'],
        lane='backfill',
        recording_age_seconds=60,
        source='omi',
        should_lock=False,
        conversation_id=None,
        client_device_id=None,
        client_platform='ios',
        byok_enabled=True,
    )
    assert response is None  # Caller invokes original cap/stale/missing-Redis claim logic.
    assert not any(table == 'jobs' for table, _ in store.rows)


@pytest.mark.asyncio
async def test_prior_batch_receipt_or_ambiguous_error_never_selects_legacy(monkeypatch):
    from utils.batch_pipeline import intake

    store = MemoryStore()
    store.rows['content', 'synthetic-owner/content'] = {'dispatch_protocol': 'batch_v1', 'job_id': 'bp_prior'}
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **kw: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    arguments = dict(
        uid='synthetic-owner',
        job_id='retry',
        content_id='content',
        paths=['retained.bin'],
        lane='backfill',
        recording_age_seconds=60,
        source='omi',
        should_lock=False,
        conversation_id=None,
        client_device_id=None,
        client_platform='ios',
    )
    response = await intake.accept_upload(**arguments)
    assert response is not None and response.status_code == 409

    def ambiguous(*args):
        raise TimeoutError('synthetic lost database reply')

    monkeypatch.setattr(store, 'run', ambiguous)
    response = await intake.accept_upload(**arguments)
    assert response is not None and response.status_code == 503


@pytest.mark.asyncio
async def test_store_initialization_leaves_event_loop_and_fails_closed(monkeypatch):
    import threading
    from utils.batch_pipeline import intake

    request_thread = threading.get_ident()
    initialization_threads = []

    def unavailable(namespace):
        initialization_threads.append(threading.get_ident())
        raise TimeoutError('synthetic client initialization timeout')

    monkeypatch.setattr(intake, 'FirestoreStore', unavailable)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    response = await intake.accept_upload(
        uid='synthetic-owner',
        job_id='retry',
        content_id='content',
        paths=['retained.bin'],
        lane='backfill',
        recording_age_seconds=60,
        source='omi',
        should_lock=False,
        conversation_id=None,
        client_device_id=None,
        client_platform='ios',
    )
    assert initialization_threads and initialization_threads[0] != request_thread
    assert response is not None and response.status_code == 503


def test_admitted_duration_emits_only_after_new_committed_ownership(cohort, monkeypatch):
    from database import batch_pipeline_intake as module
    from unittest.mock import Mock

    metric = Mock()
    monkeypatch.setattr(module, 'record_correctness', metric)
    store = MemoryStore()
    works, binding = proposal()
    submit(store, works, binding)
    submit(store, works, binding)
    metric.assert_called_once_with('admitted', seconds=works[0].duration_seconds)


@pytest.mark.parametrize('recovery_state', ['held', 'prepared', 'running', 'cancelled', None])
def test_quarantine_poll_distinguishes_recoverable_and_terminal(cohort, recovery_state):
    store = MemoryStore()
    submit(store, *proposal())
    job = store.rows['jobs', 'segment']
    job.update(state='quarantined', recovery_state=recovery_state, merge_pending=False)
    status = durable_status(store, 'synthetic-owner', 'bp_first')
    recoverable = recovery_state in {'held', 'prepared', 'running'}
    assert status['status'] == ('processing' if recoverable else 'failed')
    assert status['failed_segments'] == (0 if recoverable else 1)
    assert status['poll_after_ms'] == (3000 if recoverable else 0)
    assert status['errors'] == ([] if recoverable else ['batch_worker_quarantined'])
    assert 'reason_code' not in status


def held_upload(store, sibling_state='committed'):
    """One terminally held unit beside one sibling in ``sibling_state``."""
    works, binding = proposal()
    sibling = replace(works[0], segment_id='sibling', capture_at=works[0].capture_at + 30)
    submit(store, [works[0], sibling], replace(binding, segment_ids=('segment', 'sibling')))
    store.rows['jobs', 'segment'].update(state='quarantined', recovery_state='failed_held', merge_pending=False)
    store.rows['jobs', 'sibling'].update(state=sibling_state, conversation_id='projected-sibling')


def test_terminally_held_upload_completes_without_ids_or_writes(cohort):
    store = MemoryStore()
    held_upload(store)
    before = dict(store.rows)
    status = durable_status(store, 'synthetic-owner', 'bp_first')
    assert status['status'] == 'completed' and status['reason_code'] == 'batch_unit_held'
    assert status['poll_after_ms'] == 0 and status['errors'] == []
    assert status['total_segments'] == 2 and status['failed_segments'] == 1
    assert status['processed_segments'] == status['successful_segments'] == 1
    assert status['result']['new_memories'] == status['result']['updated_memories'] == []
    assert 'projected-sibling' not in repr(status)
    assert store.rows == before
    assert store.rows['content', 'synthetic-owner/content']['status'] == 'processing'


@pytest.mark.parametrize(
    'intent', ['speech_redrive', 'terminal_disposition', 'silence_disposition'], ids=lambda value: value
)
def test_open_operator_intent_waits_instead_of_completing(cohort, intent):
    store = MemoryStore()
    held_upload(store)
    store.rows['jobs', 'segment'][intent] = {'state': 'prepared'}
    status = durable_status(store, 'synthetic-owner', 'bp_first')
    assert status['status'] == 'processing' and status['poll_after_ms'] == 3000
    assert status['result'] is None and 'reason_code' not in status


@pytest.mark.parametrize('sibling_state', ['ready', 'leased', 'retry', 'result_ready'])
def test_in_flight_sibling_waits_beside_held_unit(cohort, sibling_state):
    store = MemoryStore()
    held_upload(store, sibling_state)
    status = durable_status(store, 'synthetic-owner', 'bp_first')
    assert status['status'] == 'processing' and status['poll_after_ms'] == 3000


@pytest.mark.parametrize('recovery_state', ['held', 'prepared', 'running'])
def test_recoverable_quarantined_sibling_waits_beside_held_unit(cohort, recovery_state):
    store = MemoryStore()
    held_upload(store)
    store.rows['jobs', 'sibling'].update(state='quarantined', recovery_state=recovery_state)
    status = durable_status(store, 'synthetic-owner', 'bp_first')
    assert status['status'] == 'processing' and status['poll_after_ms'] == 3000
    assert 'reason_code' not in status


def test_operator_call_that_settled_failed_held_is_closed(cohort):
    store = MemoryStore()
    held_upload(store)
    store.rows['jobs', 'segment']['speech_redrive'] = {'state': 'failed_held'}
    status = durable_status(store, 'synthetic-owner', 'bp_first')
    assert status['status'] == 'completed' and status['reason_code'] == 'batch_unit_held'


def test_mixed_held_and_other_failure_keeps_failed(cohort):
    store = MemoryStore()
    held_upload(store)
    store.rows['jobs', 'sibling'].update(state='quarantined', recovery_state='cancelled')
    status = durable_status(store, 'synthetic-owner', 'bp_first')
    assert status['status'] == 'failed' and status['errors'] == ['batch_worker_quarantined']


def test_held_terminal_kill_switch_restores_failed(cohort, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_HELD_TERMINAL_STATUS_ENABLED', 'false')
    store = MemoryStore()
    held_upload(store)
    status = durable_status(store, 'synthetic-owner', 'bp_first')
    assert status['status'] == 'failed' and status['errors'] == ['batch_worker_quarantined']
    assert 'reason_code' not in status


def deleting_privacy(monkeypatch, reason='conversation_deleted'):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from tests.unit.test_batch_pipeline_scheduler import MemoryTransaction

    def check(tx, uid, conversation_ids=(), expected_generation=None):
        # Models the real walk's first-hit behaviour: a deletion may surface
        # before another denied ID in the same receipt.
        ids = set(conversation_ids)
        if 'deleted' in ids:
            raise BatchPrivacyBlocked(reason)
        if 'redirect-missing' in ids:
            raise BatchPrivacyBlocked('conversation_redirect_missing')
        return expected_generation or 0

    monkeypatch.setattr(MemoryTransaction, 'check_privacy', check)


def completed_receipt(store):
    result = {
        'new_memories': ['deleted'],
        'updated_memories': ['survivor'],
        'failed_segments': 0,
        'total_segments': 3,
        'errors': [],
    }
    store.rows['content', 'synthetic-owner/content'] = {'status': 'completed', 'job_id': 'old', 'result': result}


def test_deleted_conversation_completes_cached_alias_without_ids(cohort, monkeypatch):
    store = MemoryStore()
    completed_receipt(store)
    store.rows['intakes', 'bp_cached'] = {
        'owner_id': 'synthetic-owner',
        'content_id': 'content',
        'segment_ids': [],
        'total_files': 1,
        'lane': 'backfill',
    }
    deleting_privacy(monkeypatch)
    status = durable_status(store, 'synthetic-owner', 'bp_cached')
    assert status['status'] == 'completed' and status['reason_code'] == 'conversation_deleted'
    assert status['total_segments'] == status['successful_segments'] == 3
    assert status['result'] == {
        'new_memories': [],
        'updated_memories': [],
        'failed_segments': 0,
        'total_segments': 3,
        'errors': [],
    }
    assert 'deleted' not in repr(status['result']) and 'survivor' not in repr(status)


@pytest.mark.parametrize('reason', ['account_deleted', 'privacy_generation_changed', 'conversation_redirect_missing'])
def test_other_privacy_denials_still_raise(cohort, monkeypatch, reason):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    store = MemoryStore()
    completed_receipt(store)
    store.rows['intakes', 'bp_cached'] = {
        'owner_id': 'synthetic-owner',
        'content_id': 'content',
        'segment_ids': [],
        'total_files': 1,
        'lane': 'backfill',
    }
    deleting_privacy(monkeypatch, reason)
    with pytest.raises(BatchPrivacyBlocked):
        durable_status(store, 'synthetic-owner', 'bp_cached')


def test_deletion_beside_another_denial_never_acks(cohort, monkeypatch):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    store = MemoryStore()
    completed_receipt(store)
    store.rows['content', 'synthetic-owner/content']['result']['updated_memories'] = ['redirect-missing']
    store.rows['intakes', 'bp_cached'] = {
        'owner_id': 'synthetic-owner',
        'content_id': 'content',
        'segment_ids': [],
        'total_files': 1,
        'lane': 'backfill',
    }
    deleting_privacy(monkeypatch)
    with pytest.raises(BatchPrivacyBlocked) as raised:
        durable_status(store, 'synthetic-owner', 'bp_cached')
    assert raised.value.reason.value == 'conversation_redirect_missing'


@pytest.mark.asyncio
async def test_reupload_with_deletion_beside_another_denial_keeps_409(cohort, monkeypatch):
    from utils.batch_pipeline import intake

    store = MemoryStore()
    completed_receipt(store)
    store.rows['content', 'synthetic-owner/content']['result']['updated_memories'] = ['redirect-missing']
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **kw: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    deleting_privacy(monkeypatch)
    response = await intake.accept_upload(**upload_arguments())
    assert response is not None and response.status_code == 409


def test_deleted_conversation_on_unfinished_upload_still_raises(cohort, monkeypatch):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    store = MemoryStore()
    submit(store, *proposal())
    store.rows['jobs', 'segment']['conversation_id'] = 'deleted'
    deleting_privacy(monkeypatch)
    with pytest.raises(BatchPrivacyBlocked):
        durable_status(store, 'synthetic-owner', 'bp_first')


def upload_arguments():
    return dict(
        uid='synthetic-owner',
        job_id='retry',
        content_id='content',
        paths=['retained.bin'],
        lane='backfill',
        recording_age_seconds=60,
        source='omi',
        should_lock=False,
        conversation_id=None,
        client_device_id=None,
        client_platform='ios',
    )


@pytest.mark.asyncio
async def test_reupload_of_deleted_legacy_receipt_acks_synchronously(cohort, monkeypatch):
    import json
    from utils.batch_pipeline import intake

    store = MemoryStore()
    completed_receipt(store)
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **kw: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    deleting_privacy(monkeypatch)
    response = await intake.accept_upload(**upload_arguments())
    assert response is not None and response.status_code == 200
    assert json.loads(response.body) == {
        'new_memories': [],
        'updated_memories': [],
        'failed_segments': 0,
        'total_segments': 3,
        'errors': [],
    }
    assert not any(table in {'intakes', 'jobs'} for table, _ in store.rows)


@pytest.mark.asyncio
async def test_reupload_of_held_batch_upload_reads_completed(cohort, monkeypatch):
    import json
    from utils.batch_pipeline import intake

    store = MemoryStore()
    held_upload(store)
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **kw: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    response = await intake.accept_upload(**upload_arguments())
    assert response is not None and response.status_code == 202
    body = json.loads(response.body)
    assert body['status'] == 'completed' and body['job_id'] == 'bp_first' and body['poll_after_ms'] == 0
