"""Experiment ``receipt_finished_note`` (with ``receipt_long_poll``): the wait reads only finished jobs.

Off (``receipt_long_poll`` alone) a finished job leaves no note and the wait re-reads every listed
job when it starts, on each wake and when it expires. On, a finished job leaves a note before its
wake, and the wait reads job state only for a job that a note or a wake names.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import reliability_experiments
from database import redis_db, sync_jobs
from database.batch_pipeline_projection import ProjectionStore
from models.sync_job_status import SyncReceiptsWaitRequest
from routers import sync
from utils.batch_pipeline.contracts import ProjectionBinding

LONG_POLL, EXPERIMENT = 'receipt_long_poll', 'receipt_finished_note'
OWNER = 'owner'


def select(monkeypatch, *names):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    if names:
        monkeypatch.setenv(reliability_experiments.ENV, ','.join(names))
    else:
        monkeypatch.delenv(reliability_experiments.ENV, raising=False)


def test_experiment_is_registered():
    assert EXPERIMENT in reliability_experiments.EXPERIMENTS
    assert LONG_POLL in reliability_experiments.EXPERIMENTS[EXPERIMENT]


@pytest.mark.parametrize('on', [False, True])
def test_finished_legacy_job_leaves_a_note_before_its_wake_only_with_the_experiment(monkeypatch, on):
    select(monkeypatch, LONG_POLL, *([EXPERIMENT] if on else []))
    redis = Mock()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    sync_jobs._cleanup_terminal_segments('job-1', {'status': 'completed', 'uid': OWNER})
    redis.publish.assert_called_once_with(sync_jobs.receipt_channel(OWNER), 'job-1')
    if on:
        redis.set.assert_called_once_with(
            sync_jobs.receipt_note_key(OWNER, 'job-1'), '1', ex=sync_jobs.RECEIPT_NOTE_TTL_SECONDS
        )
        names = [call[0] for call in redis.method_calls]
        assert names.index('set') < names.index('publish')
    else:
        redis.set.assert_not_called()


def test_note_alone_changes_nothing_without_the_long_poll(monkeypatch):
    select(monkeypatch, EXPERIMENT)
    redis = Mock()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    sync_jobs._cleanup_terminal_segments('job-1', {'status': 'completed', 'uid': OWNER})
    redis.set.assert_not_called()
    redis.publish.assert_not_called()


@pytest.mark.parametrize('on', [False, True])
def test_batch_completion_leaves_a_note_for_the_upload_and_each_coalesced_member(monkeypatch, on):
    select(monkeypatch, LONG_POLL, *([EXPERIMENT] if on else []))
    redis = Mock()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    binding = ProjectionBinding(OWNER, 'bp_target', 'content', ('segment',))
    ProjectionStore._wake_receipt_waiters(binding, [('intakes', 'bp_member')])
    channel = sync_jobs.receipt_channel(OWNER)
    assert [call.args for call in redis.publish.call_args_list] == [(channel, 'bp_target'), (channel, 'bp_member')]
    noted = [call.args[0] for call in redis.set.call_args_list]
    expected = [sync_jobs.receipt_note_key(OWNER, 'bp_target'), sync_jobs.receipt_note_key(OWNER, 'bp_member')]
    assert noted == (expected if on else [])


def test_a_failed_note_does_not_fail_the_completion(monkeypatch):
    select(monkeypatch, LONG_POLL, EXPERIMENT)
    redis = Mock()
    redis.set.side_effect = RuntimeError('synthetic redis outage')
    monkeypatch.setattr(sync_jobs, 'r', redis)
    sync_jobs._cleanup_terminal_segments('job-1', {'status': 'completed', 'uid': OWNER})
    ProjectionStore._wake_receipt_waiters(ProjectionBinding(OWNER, 'bp_target', 'content', ('segment',)), [])


class Wait:
    """The wait endpoint against a scripted Redis and a recording job-state reader."""

    def __init__(self, monkeypatch, states, notes=()):
        self.states, self.notes, self.reads = dict(states), set(notes), []
        self.listening, self.messages, self.note_checks = asyncio.Event(), asyncio.Queue(), []
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

            async def mget(self, keys):
                harness.note_checks.append(list(keys))
                wanted = {sync_jobs.receipt_note_key(OWNER, job) for job in harness.notes}
                return ['1' if key in wanted else None for key in keys]

        async def get_redis():
            return Redis()

        def read(job, uid, *_):
            assert uid == OWNER
            self.reads.append(job)
            return {'job_id': job, 'status': self.states[job]}

        async def run(_executor, fn, *args, **kwargs):
            return fn(*args, **kwargs)

        monkeypatch.setattr(redis_db, 'get_async_redis_client', get_redis)
        monkeypatch.setattr(sync, 'admit_sync_job_poll', lambda _: True)
        monkeypatch.setattr(sync, '_read_sync_job_status', read)
        monkeypatch.setattr(sync, 'run_blocking', run)
        monkeypatch.setattr(sync, 'account_deletion_blocks_user_work', lambda uid, fresh=False: False)

    def start(self, *jobs):
        class Request:
            async def is_disconnected(self):
                return False

        return asyncio.create_task(
            sync.wait_for_sync_receipts(SyncReceiptsWaitRequest(job_ids=list(jobs)), Request(), OWNER)
        )


@pytest.mark.asyncio
async def test_start_reads_only_noted_jobs_and_a_wake_reads_only_the_job_it_names(monkeypatch):
    select(monkeypatch, LONG_POLL, EXPERIMENT)
    wait = Wait(monkeypatch, {'a': 'queued', 'b': 'queued', 'c': 'queued'})
    waiter = wait.start('a', 'b', 'c')
    await asyncio.wait_for(wait.listening.wait(), 2)
    # Subscribed, checked the three notes in one Redis call, and read no job state.
    assert wait.reads == [] and len(wait.note_checks) == 1 and len(wait.note_checks[0]) == 3
    # A wake for a job outside this request is ignored; one for a listed job reads that job only.
    wait.messages.put_nowait({'type': 'message', 'data': 'elsewhere'})
    wait.states.update(b='completed', c='completed')
    wait.messages.put_nowait({'type': 'message', 'data': 'b'})
    result = await asyncio.wait_for(waiter, 2)
    assert wait.reads == ['b']
    assert [receipt['job_id'] for receipt in result['receipts']] == ['b'] and result['fallback'] == []


@pytest.mark.asyncio
async def test_a_job_that_finished_before_the_wait_is_found_by_its_note(monkeypatch):
    select(monkeypatch, LONG_POLL, EXPERIMENT)
    wait = Wait(monkeypatch, {'a': 'queued', 'b': 'completed', 'c': 'failed'}, notes={'b', 'c'})
    result = await asyncio.wait_for(wait.start('a', 'b', 'c'), 2)
    assert sorted(wait.reads) == ['b', 'c']
    assert sorted(receipt['job_id'] for receipt in result['receipts']) == ['b', 'c']


@pytest.mark.asyncio
async def test_a_noted_job_whose_state_is_not_final_goes_to_the_paced_path(monkeypatch):
    select(monkeypatch, LONG_POLL, EXPERIMENT)
    wait = Wait(monkeypatch, {'a': 'queued', 'b': 'processing'}, notes={'b'})
    result = await asyncio.wait_for(wait.start('a', 'b'), 2)
    assert wait.reads == ['b']
    assert result == {'receipts': [], 'fallback': ['b']}


@pytest.mark.asyncio
async def test_an_expired_wait_answers_empty_without_reading_job_state(monkeypatch):
    select(monkeypatch, LONG_POLL, EXPERIMENT)
    wait = Wait(monkeypatch, {'a': 'queued', 'b': 'queued'})
    clock = iter([0.0, 100.0])
    monkeypatch.setattr(sync, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    result = await asyncio.wait_for(wait.start('a', 'b'), 2)
    assert result == {'receipts': [], 'fallback': []}
    assert wait.reads == []


@pytest.mark.asyncio
async def test_without_the_experiment_every_start_wake_and_expiry_reads_every_job(monkeypatch):
    select(monkeypatch, LONG_POLL)
    wait = Wait(monkeypatch, {'a': 'queued', 'b': 'queued'}, notes={'a', 'b'})
    clock = iter([0.0, 1.0, 100.0])
    monkeypatch.setattr(sync, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    waiter = wait.start('a', 'b')
    await asyncio.wait_for(wait.listening.wait(), 2)
    wait.messages.put_nowait({'type': 'message', 'data': 'a'})
    result = await asyncio.wait_for(waiter, 2)
    # Start, wake and expiry: three full reads of both jobs, and the notes are never consulted.
    assert sorted(wait.reads) == ['a', 'a', 'a', 'b', 'b', 'b']
    assert wait.note_checks == [] and result == {'receipts': [], 'fallback': []}
