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
