"""``/v2/sync-local-files/receipts/wait`` rechecks account deletion before it answers a job.

The auth fence runs once, before a wait of up to ~23 seconds. A deletion that becomes pending
during the wait must not let a completed job's result (conversation IDs) leave the server: a
completed legacy Redis job carries its raw result with no deletion check of its own, and a durable
reconciliation's own marker read can predate the marker. Every answer that names a job therefore
re-reads the marker once, uncached, after the wait; a pending or active deletion answers
``503 {'status': 'account_pending_deletion'}`` and an unreadable marker answers no job.
"""

import asyncio
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from config import reliability_experiments
from database import redis_db, sync_jobs
from models.sync_job_status import SyncReceiptsWaitRequest
from routers import sync
from utils.sync import completed_status

OWNER = 'owner'
SECRET = 'conversation-must-not-leave'


class Harness:
    """The real route and status reader against a scripted Redis, job store and deletion marker."""

    def __init__(self, monkeypatch, *, jobs, marker=None):
        monkeypatch.setenv('OMI_ENV_STAGE', 'local')
        monkeypatch.setenv(reliability_experiments.ENV, 'receipt_long_poll')
        monkeypatch.setenv('SYNC_DURABLE_STATUS_RECONCILIATION', 'true')
        self.jobs = jobs
        self.pending_deletion = False
        self.marker_reads = []
        self.listening, self.messages = asyncio.Event(), asyncio.Queue()
        harness = self

        class Subscription:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def subscribe(self, channel):
                assert channel == sync_jobs.receipt_channel(OWNER)
                harness.messages.put_nowait({'type': 'subscribe'})

            async def get_message(self, ignore_subscribe_messages=False, timeout=None):
                if ignore_subscribe_messages:
                    harness.listening.set()
                try:
                    return await asyncio.wait_for(harness.messages.get(), timeout)
                except asyncio.TimeoutError:
                    return None

        class Redis:
            pubsub = Subscription

        async def get_redis():
            return Redis()

        def blocks(uid, fresh=False):
            assert uid == OWNER
            harness.marker_reads.append(fresh)
            if marker is not None:
                return marker()
            return harness.pending_deletion

        async def run(_executor, fn, *args, **kwargs):
            return fn(*args, **kwargs)

        monkeypatch.setattr(redis_db, 'get_async_redis_client', get_redis)
        monkeypatch.setattr(sync, 'admit_sync_job_poll', lambda _: True)
        monkeypatch.setattr(sync, 'run_blocking', run)
        monkeypatch.setattr(sync, 'account_deletion_blocks_user_work', blocks)
        # The real _read_sync_job_status runs; only its stores are scripted.
        monkeypatch.setattr(sync, 'get_durable_job_status', lambda job_id, uid, **_: None)
        monkeypatch.setattr(sync, 'get_sync_job', lambda job_id: self.jobs.get(job_id))
        monkeypatch.setattr(sync, 'with_custody_hold_poll_hint', lambda status: status)
        monkeypatch.setattr(sync, 'acknowledge_retired_handle', lambda job_id, uid: None)
        real_reconcile = completed_status.get_completed_legacy_status

        def reconcile(job_id, uid, job):
            # The real reconciliation for a completed Redis job (it returns before any Firestore
            # read); an unfinished job has no durable completion in this harness.
            return real_reconcile(job_id, uid, job) if job and job.get('status') == 'completed' else None

        monkeypatch.setattr(completed_status, 'get_completed_legacy_status', reconcile)

    def start(self, *job_ids):
        class Request:
            async def is_disconnected(self):
                return False

        return asyncio.create_task(
            sync.wait_for_sync_receipts(SyncReceiptsWaitRequest(job_ids=list(job_ids)), Request(), OWNER)
        )


def legacy_job(status, **extra):
    return {'job_id': 'job-a', 'uid': OWNER, 'status': status, 'lane': 'fresh', **extra}


COMPLETED_RESULT = {'new_memories': [SECRET], 'updated_memories': [], 'total_segments': 1}


def assert_pending_deletion_answer(answer):
    assert isinstance(answer, JSONResponse)
    assert answer.status_code == 503
    assert json.loads(answer.body) == {'status': 'account_pending_deletion'}
    assert SECRET.encode() not in answer.body and b'job-a' not in answer.body


@pytest.mark.asyncio
async def test_completed_legacy_redis_job_after_deletion_turns_pending_returns_no_result(monkeypatch):
    harness = Harness(monkeypatch, jobs={'job-a': legacy_job('processing')})
    waiter = harness.start('job-a')
    # Authenticated and waiting: the account is not being deleted yet.
    await asyncio.wait_for(harness.listening.wait(), 2)
    assert harness.marker_reads == []
    harness.pending_deletion = True
    harness.jobs['job-a'] = legacy_job('completed', result=COMPLETED_RESULT, completed_at='2026-11-26T00:00:00Z')
    # The completed Redis job is answered from Redis: durable reconciliation declines it unread.
    assert completed_status.get_completed_legacy_status('job-a', OWNER, harness.jobs['job-a']) is None
    harness.messages.put_nowait({'type': 'message', 'data': 'job-a'})
    answer = await asyncio.wait_for(waiter, 2)
    assert_pending_deletion_answer(answer)
    # One uncached marker read for the whole request.
    assert harness.marker_reads == [True]


@pytest.mark.asyncio
async def test_durable_reconciliation_completion_after_deletion_turns_pending_returns_no_result(monkeypatch):
    harness = Harness(monkeypatch, jobs={'job-a': legacy_job('processing')})
    reconciled = {}

    def reconcile(job_id, uid, job):
        assert uid == OWNER
        return reconciled.get(job_id)

    monkeypatch.setattr(completed_status, 'get_completed_legacy_status', reconcile)
    waiter = harness.start('job-a')
    await asyncio.wait_for(harness.listening.wait(), 2)
    harness.pending_deletion = True
    # The Redis job expires; the content ledger proves the completion.
    del harness.jobs['job-a']
    reconciled['job-a'] = {
        'job_id': 'job-a',
        'status': 'completed',
        'completed_at': '2026-11-26T00:00:00Z',
        'lane': 'fresh',
        'total_segments': 1,
        'processed_segments': 1,
        'successful_segments': 1,
        'failed_segments': 0,
        'result': COMPLETED_RESULT,
    }
    harness.messages.put_nowait({'type': 'message', 'data': 'job-a'})
    answer = await asyncio.wait_for(waiter, 2)
    assert_pending_deletion_answer(answer)
    assert harness.marker_reads == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['raises', 'hangs'])
async def test_unreadable_deletion_marker_fails_closed(monkeypatch, failure):
    def marker():
        if failure == 'raises':
            raise RuntimeError('synthetic firestore outage')
        return False

    harness = Harness(
        monkeypatch,
        jobs={'job-a': legacy_job('completed', result=COMPLETED_RESULT)},
        marker=marker,
    )
    timeout = 0.6
    hung = asyncio.Event()
    if failure == 'hangs':
        real_run = sync.run_blocking
        never = asyncio.Event()

        async def run(executor, fn, *args, **kwargs):
            if fn is sync.account_deletion_blocks_user_work:
                hung.set()
                # Far past the route's timeout; then it would answer "not deleted", which only an
                # absent timeout guard could pass through (and the 2 s bound below fails first).
                try:
                    await asyncio.wait_for(never.wait(), 5)
                except asyncio.TimeoutError:
                    pass
            return await real_run(executor, fn, *args, **kwargs)

        monkeypatch.setattr(sync, 'run_blocking', run)
        monkeypatch.setattr(sync, 'RECEIPT_DELETION_CHECK_TIMEOUT_SECONDS', timeout)
    started = time.monotonic()
    with pytest.raises(HTTPException) as refused:
        await asyncio.wait_for(harness.start('job-a'), 2)
    elapsed = time.monotonic() - started
    assert refused.value.status_code == 503
    if failure == 'hangs':
        # The marker read was in flight and the route gave up at its timeout, plus a small grace.
        assert hung.is_set() and timeout <= elapsed < timeout + 1
    assert SECRET not in str(refused.value.detail) and 'job-a' not in str(refused.value.detail)


@pytest.mark.asyncio
async def test_without_deletion_the_completed_receipt_is_unchanged(monkeypatch):
    harness = Harness(monkeypatch, jobs={'job-a': legacy_job('processing'), 'job-b': legacy_job('processing')})
    harness.jobs['job-b']['job_id'] = 'job-b'
    waiter = harness.start('job-a', 'job-b')
    await asyncio.wait_for(harness.listening.wait(), 2)
    harness.jobs['job-a'] = legacy_job('completed', result=COMPLETED_RESULT, completed_at='2026-11-26T00:00:00Z')
    harness.messages.put_nowait({'type': 'message', 'data': 'job-a'})
    answer = await asyncio.wait_for(waiter, 2)
    assert answer['fallback'] == []
    [receipt] = answer['receipts']
    assert receipt['job_id'] == 'job-a' and receipt['status'] == 'completed'
    assert receipt['result'] == COMPLETED_RESULT
    assert harness.marker_reads == [True]


@pytest.mark.asyncio
async def test_an_empty_answer_reads_no_marker(monkeypatch):
    harness = Harness(monkeypatch, jobs={'job-a': legacy_job('processing')})
    clock = iter([0.0, 100.0])
    monkeypatch.setattr(sync, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    answer = await asyncio.wait_for(harness.start('job-a'), 2)
    assert answer == {'receipts': [], 'fallback': []}
    assert harness.marker_reads == []
