"""Worker death, stale claims and retry custody on the real Redis fence."""

import asyncio
import os
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Event
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis
import pytest

from database import sync_jobs
from database import sync_backfill_sequencer as registry
from tests.unit.test_sync_backfill_uid_sequencer import _Firestore
from utils.sync import worker_control, worker_job, worker_runtime

LEASE = {
    'payload': {
        'uid': 'synthetic',
        'job_id': 'job',
        'sequencer_epoch': 3,
        'lane': 'backfill',
        'ledger_fence_mode': 'active',
        'worker_eligible': True,
        'raw_blob_paths': ['syncing/synthetic/job/audio.bin'],
    },
    'token': 'worker-token',
}


async def test_lease_loss_kills_job_and_its_executor_process_group(monkeypatch, tmp_path):
    processes = []

    async def launch(env):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(Path(__file__).parent / 'fixtures/sync_worker_child.py'),
            str(tmp_path),
            stdin=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        processes.append(process)
        return process

    class Client:
        def __init__(self):
            self.beats = 0

        async def call(self, operation, body=None):
            assert operation == 'heartbeat'
            self.beats += 1
            if self.beats > 1:
                # Reject only after the descendant has actually started. A
                # fixed delay can kill it before startup on a loaded runner,
                # which proves no executor-leaf termination at all.
                async with asyncio.timeout(3):
                    while not (tmp_path / 'leaf-tick').exists():
                        await asyncio.sleep(0.01)
            return {'accepted': self.beats == 1}

    monkeypatch.setattr(worker_runtime, 'launch_job', launch)
    monkeypatch.setattr(worker_runtime, 'POLL_SECONDS', 0.01)
    monkeypatch.setattr(worker_runtime, 'HEARTBEAT_SECONDS', 0.5)
    runtime = worker_runtime.Runtime(Client())
    with pytest.raises(RuntimeError, match='sequencer lease lost'):
        await asyncio.wait_for(runtime.execute(LEASE), 5)
    assert processes[0].returncode is not None
    assert runtime.active is False
    assert (tmp_path / 'pids.json').is_file()
    before = (tmp_path / 'leaf-tick').read_text()
    await asyncio.sleep(0.05)
    assert (tmp_path / 'leaf-tick').read_text() == before


async def test_crashed_job_reaps_orphan_leaf_before_fail_rpc(monkeypatch, tmp_path):
    (tmp_path / 'crash').touch()

    async def launch(env):
        return await asyncio.create_subprocess_exec(
            sys.executable,
            str(Path(__file__).parent / 'fixtures/sync_worker_child.py'),
            str(tmp_path),
            stdin=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )

    class CrashClient:
        async def call(self, operation, body=None):
            if operation == 'fail':
                before = (tmp_path / 'leaf-tick').read_text()
                await asyncio.sleep(0.05)
                assert (tmp_path / 'leaf-tick').read_text() == before
            return {'accepted': True}

    monkeypatch.setattr(worker_runtime, 'launch_job', launch)
    await asyncio.wait_for(worker_runtime.Runtime(CrashClient()).execute(LEASE), 5)


async def test_work_deadline_kills_hung_job_before_fallback(execution, monkeypatch, tmp_path):
    processes = []
    operations = []
    now = datetime.now(timezone.utc)
    store = _Firestore()
    store.docs[(registry.COLLECTION, 'synthetic')] = {
        'active_job_id': 'job',
        'active_epoch': 3,
        'epoch': 3,
        'active_state': 'dispatching',
        'worker_available': True,
        'active_payload': LEASE['payload'],
        'active_accepted_at': now,
        'lease_expires_at': now + timedelta(seconds=1800),
    }

    def transactional(fn):
        def commit(transaction):
            with store.lock:
                return fn(transaction)

        return commit

    monkeypatch.setattr(registry.firestore, 'transactional', transactional)
    monkeypatch.setattr(registry, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(registry, '_now', lambda: now)
    assert registry.claim_worker('synthetic', 'job', 3, LEASE['token'])
    run_token = sync_jobs.try_acquire_sync_job_run_lock('job')
    assert run_token

    async def launch(env):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(Path(__file__).parent / 'fixtures/sync_worker_child.py'),
            str(tmp_path),
            stdin=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        processes.append(process)
        return process

    class HealthyClient:
        async def call(self, operation, body=None):
            operations.append(operation)
            if operation == 'fail':
                assert processes[0].returncode is not None
                before = (tmp_path / 'leaf-tick').read_text()
                await asyncio.sleep(0.05)
                assert (tmp_path / 'leaf-tick').read_text() == before
                assert sync_jobs.try_acquire_sync_job_run_lock('job') is None
            if operation == 'heartbeat':
                return {'accepted': worker_control.heartbeat(**body)}
            assert operation == 'fail'
            return {'accepted': worker_control.fail(**body)}

    monkeypatch.setattr(worker_runtime, 'launch_job', launch)
    monkeypatch.setattr(worker_runtime, 'WORK_DEADLINE_SECONDS', 1.5, raising=False)
    monkeypatch.setattr(worker_runtime, 'POLL_SECONDS', 0.01)
    monkeypatch.setattr(worker_runtime, 'HEARTBEAT_SECONDS', 0.1)
    runtime = worker_runtime.Runtime(HealthyClient())
    await asyncio.wait_for(runtime.execute(LEASE), 4)
    assert operations[-1] == 'fail'
    assert operations.count('heartbeat') >= 2
    assert runtime.active is False
    assert sync_jobs.sync_job_run_lock_present('job')
    assert execution[2].await_count == 0
    assert registry.redrive_job('synthetic', 'job', 3) is None
    # Advance the hermetic stores' clocks past the real 1800s silence windows;
    # neither TTL nor epoch rules are shortened to make the test pass.
    now += timedelta(seconds=1801)
    from fakeredis import _basefakesocket

    redis_time = time.time() + 1801
    monkeypatch.setattr(_basefakesocket, 'time', SimpleNamespace(time=lambda: redis_time))
    replacement = registry.redrive_job('synthetic', 'job', 3)
    assert replacement and replacement['epoch'] == 4
    assert registry.begin_job('synthetic', 'job', 4)
    fallback_token = sync_jobs.try_acquire_sync_job_run_lock('job')
    assert fallback_token
    assert not registry.renew_job('synthetic', 'job', 3, worker_token=LEASE['token'])
    assert not sync_jobs.renew_job_run_lock('job', run_token)
    sync_jobs.release_job_run_lock('job', fallback_token)


@pytest.fixture
def execution(monkeypatch):
    # The real pipeline imports lazily, without constructing credentialed
    # clients. Replace provider/storage leaves, retain actual Redis ownership.
    from database import account_deletion_marker as account_deletion
    from utils.account_cutover import access
    from utils.sync import ledger_completion, pipeline

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_LEDGER_FENCE_MODE', 'active')
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    redis.set(
        'sync_job:job',
        json.dumps(
            {
                'job_id': 'job',
                'uid': 'synthetic',
                'status': 'queued',
                'ledger_fence_mode': 'active',
                'dispatch_mode': 'sequenced',
                'created_stage': 'prod',
                'attempt': 0,
            }
        ),
    )
    monkeypatch.setattr(account_deletion, 'account_deletion_blocks_user_work', lambda _: False)
    monkeypatch.setattr(access, 'should_skip_background_account_mutation', lambda _: False)
    monkeypatch.setattr(ledger_completion, 'bind_or_converge_sync_ledger_completion', lambda **kw: None)
    monkeypatch.setattr(pipeline, 'download_staged_files', lambda *args, **kwargs: True)
    cleanup = AsyncMock()
    monkeypatch.setattr(worker_job, 'cleanup_terminal', cleanup)
    return redis, pipeline, cleanup


class Client:
    def __init__(self, accepted=True):
        self.accepted = accepted

    async def call(self, *args):
        return {'accepted': self.accepted}


@pytest.mark.parametrize('status', [0, 1])
async def test_normal_child_exit_flushes_holds_and_drains_owned_tasks(monkeypatch, status):
    from database import pinecone_partition_state as state
    from database import pinecone_mutation_lifecycle as lifecycle
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from utils.executors import start_background_task
    from utils.sync import cap_hold_lifecycle

    monkeypatch.setattr(state, '_mutations', state.MutationRegistry())
    for name in ('_begin_mutation', '_mark_mutation_uncertain'):
        monkeypatch.setattr(state, name, getattr(state, name).to_wrap)
    db = StrictFirestore()
    key = state.PartitionKey('synthetic-index', 'ns1', 'synthetic-owner')
    state.begin_mutation(key, affected_ids=['synthetic-vector'], firestore_client=db)
    entered, release, settled = Event(), Event(), Event()
    drain = state.drain_mutations
    lifespan_drain = lifecycle.drain_on_shutdown

    def delayed_settlement():
        entered.set()
        assert release.wait(5)
        result = drain()
        settled.set()
        return result

    async def lifespan_wait(callback):
        await lifespan_drain(callback, timeout=0.5)

    monkeypatch.setattr(state, 'drain_mutations', delayed_settlement)
    monkeypatch.setattr(lifecycle, 'drain_on_shutdown', lifespan_wait)
    closed = asyncio.Event()
    drained = asyncio.Event()

    class Hold:
        async def close(self):
            closed.set()

    async def tail():
        try:
            await asyncio.Event().wait()
        finally:
            drained.set()

    class Exited(BaseException):
        pass

    def exit_process(code):
        assert code == status
        assert closed.is_set()
        assert drained.is_set()
        assert settled.is_set()
        route = state.get_route(key, firestore_client=db)
        assert route.pending_count == 0
        assert route.uncertain_count == 1
        assert route.latest_write_lsn == 0
        raise Exited

    monkeypatch.setattr(cap_hold_lifecycle, 'ACTIVE', {Hold()})
    monkeypatch.setattr(worker_job, 'run', AsyncMock(return_value=status))
    monkeypatch.setattr(worker_job.os, '_exit', exit_process)
    task = start_background_task(tail(), name='test:worker-exit-tail')
    await asyncio.sleep(0)
    entry = asyncio.create_task(worker_job.process_entry(LEASE))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        # Simulate settlement outliving the bounded lifespan wait. A normal
        # child must remain alive until the actual metadata write completes.
        await asyncio.sleep(0.75)
        assert not entry.done()
        release.set()
        with pytest.raises(Exited):
            await asyncio.wait_for(entry, 5)
    finally:
        release.set()
        await asyncio.gather(entry, return_exceptions=True)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_lease_loss_exits_before_flushing_past_its_fence(monkeypatch):
    from database import pinecone_partition_state as state
    from utils.sync import cap_hold_lifecycle

    flush = AsyncMock()

    class Exited(BaseException):
        pass

    def exit_process(code):
        assert code == 2
        flush.assert_not_awaited()
        raise Exited

    monkeypatch.setattr(worker_job, 'run', AsyncMock(side_effect=asyncio.CancelledError))
    monkeypatch.setattr(cap_hold_lifecycle, 'flush_active', flush)
    monkeypatch.setattr(state, 'drain_mutations', lambda: pytest.fail('drain after lease loss'))
    monkeypatch.setattr(worker_job.os, '_exit', exit_process)
    with pytest.raises(Exited):
        await worker_job.process_entry(LEASE)


@pytest.mark.parametrize('project', ['', '   '])
def test_bootstrap_refuses_unpinned_customer_project_before_clients(monkeypatch, project):
    monkeypatch.setenv('OMI_DEPLOYMENT', 'production')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('OMI_CUSTOMER_DATA_PROJECT', project)
    with pytest.raises(RuntimeError, match='explicit stage and customer data project'):
        worker_job.bootstrap()


def test_blank_credential_env_is_unset_so_adc_uses_workload_identity(monkeypatch):
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '')
    monkeypatch.setenv('SERVICE_ACCOUNT_JSON', '  ')
    monkeypatch.setenv('FIREBASE_AUTH_CREDENTIALS_PATH', '/keys/kept.json')
    worker_job.drop_blank_credential_env()
    assert 'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ
    assert 'SERVICE_ACCOUNT_JSON' not in os.environ
    assert os.environ['FIREBASE_AUTH_CREDENTIALS_PATH'] == '/keys/kept.json'


async def test_stale_claim_is_rechecked_after_redis_acquisition(execution, monkeypatch):
    redis, pipeline, cleanup = execution
    process = AsyncMock()
    monkeypatch.setattr(pipeline, 'run_full_pipeline_background_async', process)
    assert not await worker_job.execute(LEASE, Client(False))
    process.assert_not_awaited()
    cleanup.assert_not_awaited()
    assert not sync_jobs.sync_job_run_lock_present('job')


@pytest.mark.parametrize('capture_received_at', [None, 1800000000.0])
async def test_worker_runs_fenced_pipeline_without_request_budget(execution, monkeypatch, capture_received_at):
    redis, pipeline, cleanup = execution

    async def process(*args, **kwargs):
        assert kwargs['task_mode'] is True
        assert kwargs['content_run_bound'] is True
        assert kwargs['ledger_fence_active'] is True
        assert kwargs.get('inline_run_lock_token') is None
        assert kwargs['capture_received_at'] == capture_received_at
        token = kwargs['run_lock_token']
        assert sync_jobs.renew_job_run_lock('job', token)
        assert sync_jobs.try_acquire_sync_job_run_lock('job') is None
        row = json.loads(redis.get('sync_job:job'))
        row['status'] = 'completed'
        redis.set('sync_job:job', json.dumps(row))

    monkeypatch.setattr(pipeline, 'run_full_pipeline_background_async', process)
    lease = {**LEASE, 'payload': {**LEASE['payload'], 'capture_received_at': capture_received_at}}
    assert await worker_job.execute(lease, Client())
    cleanup.assert_awaited_once()
    assert not sync_jobs.sync_job_run_lock_present('job')


async def test_disabled_minimal_redrive_refuses_before_any_work(execution, monkeypatch):
    _, pipeline, cleanup = execution
    monkeypatch.setenv('SYNC_MINIMAL_REDRIVE_ENABLED', 'false')
    process = AsyncMock()
    download = lambda *args, **kwargs: pytest.fail('download before minimal-mode refusal')
    monkeypatch.setattr(pipeline, 'run_full_pipeline_background_async', process)
    monkeypatch.setattr(pipeline, 'download_staged_files', download)
    lease = {**LEASE, 'payload': {**LEASE['payload'], 'redrive_mode': 'minimal'}}
    assert not await worker_job.execute(lease, Client())
    process.assert_not_awaited()
    cleanup.assert_not_awaited()
    assert not sync_jobs.sync_job_run_lock_present('job')


async def test_enabled_minimal_redrive_reaches_pipeline_unchanged(execution, monkeypatch):
    redis, pipeline, _ = execution
    monkeypatch.setenv('SYNC_MINIMAL_REDRIVE_ENABLED', 'true')

    async def process(*args, **kwargs):
        assert kwargs['redrive_mode'] == 'minimal'
        row = json.loads(redis.get('sync_job:job'))
        row['status'] = 'completed'
        redis.set('sync_job:job', json.dumps(row))

    monkeypatch.setattr(pipeline, 'run_full_pipeline_background_async', process)
    lease = {**LEASE, 'payload': {**LEASE['payload'], 'redrive_mode': 'minimal'}}
    assert await worker_job.execute(lease, Client())


async def test_cancelled_worker_keeps_redis_fence_and_retry_material(execution, monkeypatch):
    redis, pipeline, cleanup = execution

    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(pipeline, 'run_full_pipeline_background_async', cancelled)
    with pytest.raises(asyncio.CancelledError):
        await worker_job.execute(LEASE, Client())
    cleanup.assert_not_awaited()
    assert sync_jobs.try_acquire_sync_job_run_lock('job') is None
    assert json.loads(redis.get('sync_job:job'))['status'] == 'queued'
    assert redis.ttl('sync_job_lock:job') > 1700


async def test_worker_scopes_privacy_before_first_await_and_closes_on_cancellation(execution, monkeypatch):
    from database.batch_privacy_attempt import batch_privacy_attempt, current_attempt

    observed = []

    def cancel_at_first_await():
        observed.append(current_attempt())
        assert observed[-1] is not None
        raise asyncio.CancelledError

    monkeypatch.setattr(sync_jobs, 'get_sync_ledger_fence_mode', cancel_at_first_await)
    with batch_privacy_attempt() as parent:
        with pytest.raises(asyncio.CancelledError):
            await worker_job.execute(LEASE, Client())
        assert current_attempt() is parent
        assert len(observed) == 1 and observed[0] is not parent and observed[0]._closed
    assert current_attempt() is None


@pytest.mark.parametrize('blocked', [False, True])
async def test_worker_preflight_keeps_live_authority_and_privacy_shadow(execution, monkeypatch, blocked):
    from database import batch_pipeline_privacy as privacy, privacy_check_metrics as metrics
    from database.batch_privacy_attempt import current_attempt
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
    from utils.sync import ledger_completion

    redis, pipeline, cleanup = execution
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps({'privacy_checks_shadow': 100}))
    store = StrictFirestore(
        {
            ('users', 'synthetic'): {'data_protection_level': 'standard'},
            ('batch_pipeline_privacy', privacy.privacy_owner_key('synthetic')): {
                'generation': 7,
                'memo_token': 'a' * 32,
                'memo_schema': 1,
            },
        }
    )
    original_get = StrictFirestoreDocument.get

    def get(reference, **kwargs):
        snapshot = original_get(reference, **kwargs)
        snapshot.update_time = datetime(2026, 11, 2, tzinfo=timezone.utc) if snapshot.exists else None
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    live = metrics.CHECKS.labels('batch', 'live', 'account_deleted' if blocked else 'allow', 'unattributed')
    shadow = metrics.SHADOW_CHECKS.labels('batch', 'match')
    mismatch = metrics.DECISION_MISMATCH.labels('batch', 'stale_allow')
    hits = metrics.MEMO_REQUESTS.labels('batch', 'hit')
    before_live, before_shadow = live._value.get(), shadow._value.get()
    before_mismatch, before_hits = mismatch._value.get(), hits._value.get()
    observed = []

    def preflight(**kwargs):
        observed.append(current_attempt())
        assert privacy.assert_batch_write_allowed(store, store.transaction(), 'synthetic') == 7
        if blocked:
            # Deliberately bypass the writer token bump: shadow must detect it.
            store.rows[('account_deletions', 'synthetic')] = {'wipe_status': 'pending'}
        assert privacy.assert_batch_write_allowed(store, store.transaction(), 'synthetic') == 7
        row = json.loads(redis.get('sync_job:job'))
        row['status'] = 'completed'
        redis.set('sync_job:job', json.dumps(row))
        return row

    # This fence runs before entering the separately scoped coordinator.
    monkeypatch.setattr(ledger_completion, 'bind_or_converge_sync_ledger_completion', preflight)
    assert await worker_job.execute(LEASE, Client()) is (not blocked)
    assert live._value.get() == before_live + (1 if blocked else 2)
    assert shadow._value.get() == before_shadow + (1 if blocked else 2)
    assert hits._value.get() == before_hits + 1
    assert mismatch._value.get() == before_mismatch + int(blocked)
    assert len(observed) == 1 and observed[0] is not None and observed[0]._closed
    assert cleanup.await_count == (0 if blocked else 1)
    assert current_attempt() is None


async def test_worker_enters_real_coordinator_scope_and_closes_both_on_cancellation(execution, monkeypatch):
    from database.batch_privacy_attempt import current_attempt
    from utils.sync import ledger_completion

    _, pipeline, cleanup = execution
    observed = []

    def preflight(**kwargs):
        observed.append(current_attempt())
        return None

    async def cancel_at_coordinator_first_await(uid):
        observed.append(current_attempt())
        assert observed[-1] is not None
        raise asyncio.CancelledError

    monkeypatch.setattr(ledger_completion, 'bind_or_converge_sync_ledger_completion', preflight)
    monkeypatch.setattr(pipeline, 'warm_rollout_cohorts', cancel_at_coordinator_first_await)
    with pytest.raises(asyncio.CancelledError):
        await worker_job.execute(LEASE, Client())
    assert len(observed) == 2 and observed[0] is not observed[1]
    assert all(attempt is not None and attempt._closed for attempt in observed)
    assert current_attempt() is None
    cleanup.assert_not_awaited()
    assert sync_jobs.sync_job_run_lock_present('job')
