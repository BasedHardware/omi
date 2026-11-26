"""Experiment ``receipt_long_poll``: one waiting request for several upload jobs.

Off (the default) the path answers 404 exactly like a route that does not exist,
and a finished legacy job publishes no wake. On, the waiter subscribes before it
reads job state and replays every job that finished.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from config import reliability_experiments
from database import redis_db, sync_jobs
from models.sync_job_status import SyncReceiptsWaitRequest
from routers import sync

EXPERIMENT = 'receipt_long_poll'


@pytest.mark.asyncio
async def test_path_is_a_plain_404_for_an_account_the_experiment_is_off_for(monkeypatch):
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    monkeypatch.setattr(reliability_experiments, '_resolver', lambda name, uid: name == EXPERIMENT and uid == 'in')
    # Decided per account, so after authentication and before the poll allowance or any job read.
    monkeypatch.setattr(sync, 'admit_sync_job_poll', lambda uid: pytest.fail('no allowance spent while off'))
    body = SyncReceiptsWaitRequest(job_ids=['job-a'])
    with pytest.raises(HTTPException) as refused:
        await sync.wait_for_sync_receipts(body, SimpleNamespace(), 'out')
    assert refused.value.status_code == 404 and refused.value.detail == 'Not Found'
    assert reliability_experiments.enabled(EXPERIMENT, 'in') is True
    route = next(r for r in sync.router.routes if getattr(r, 'path', '') == '/v2/sync-local-files/receipts/wait')
    assert route.include_in_schema is False


@pytest.mark.parametrize('on', [False, True])
def test_finished_legacy_job_publishes_a_wake_only_with_the_experiment(monkeypatch, on):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    if on:
        monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    else:
        monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    redis = Mock()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    sync_jobs._cleanup_terminal_segments('job-1', {'status': 'completed', 'uid': 'owner'})
    if on:
        redis.publish.assert_called_once_with(sync_jobs.receipt_channel('owner'), 'job-1')
    else:
        redis.publish.assert_not_called()


@pytest.mark.asyncio
async def test_wait_subscribes_before_snapshot_and_replays_multiple_completed_jobs(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    jobs = {'a': 'processing', 'b': 'processing', 'c': 'processing'}
    listening = asyncio.Event()
    messages = asyncio.Queue()
    snapshots = []

    class Subscription:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def subscribe(self, channel):
            assert channel == sync_jobs.receipt_channel('owner')
            messages.put_nowait({'type': 'subscribe'})

        async def get_message(self, ignore_subscribe_messages=False, timeout=None):
            if ignore_subscribe_messages:
                listening.set()
            return await asyncio.wait_for(messages.get(), timeout)

    class Redis:
        pubsub = Subscription

    async def get_redis():
        return Redis()

    class Request:
        async def is_disconnected(self):
            return False

    def read(job, uid, *_):
        assert uid == 'owner'
        snapshots.append(job)
        return {'job_id': job, 'status': jobs[job]}

    async def run(_executor, fn, *args):
        return fn(*args)

    monkeypatch.setattr(redis_db, 'get_async_redis_client', get_redis)
    monkeypatch.setattr(sync, 'admit_sync_job_poll', lambda _: True)
    monkeypatch.setattr(sync, '_read_sync_job_status', read)
    monkeypatch.setattr(sync, 'run_blocking', run)
    body = SyncReceiptsWaitRequest(job_ids=['a', 'b', 'c'])
    waiter = asyncio.create_task(sync.wait_for_sync_receipts(body, Request(), 'owner'))
    await asyncio.wait_for(listening.wait(), 2)
    assert len(snapshots) == 3
    jobs.update(b='completed', c='completed')
    messages.put_nowait({'type': 'message', 'data': 'b'})
    result = await asyncio.wait_for(waiter, 2)
    assert {x['job_id'] for x in result['receipts']} == {'b', 'c'}
    assert await sync.wait_for_sync_receipts(body, Request(), 'owner') == result
