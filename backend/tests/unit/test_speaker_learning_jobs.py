"""Durable voice-learning coordinator scheduling contracts.

The coordinator claims persisted jobs from the conversation ledger — never
receipts scanned from process memory — stays inside the per-pass and deadline
bounds, and scheduling can never move the caller's disposition.
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.conversation import ConversationStatus
from utils import speaker_learning_jobs as jobs
from utils.conversations import finalizer as persisted_finalizer

UID = 'account-a'
CONV = 'conv-1'
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clear_in_flight(monkeypatch):
    monkeypatch.setattr(persisted_finalizer, 'save_structured_vector', MagicMock())
    jobs._in_flight_retries.clear()
    yield
    jobs._in_flight_retries.clear()


@pytest.fixture
def world(monkeypatch):
    claimed = []
    finished = []
    extract = AsyncMock(return_value='stored')
    monkeypatch.setattr(jobs, 'extract_speaker_samples', extract)
    claim = MagicMock(side_effect=lambda uid, cid: claimed.pop(0) if claimed else None)
    monkeypatch.setattr(jobs.learning_jobs_db, 'claim_next_job', claim)
    finish = MagicMock(side_effect=lambda *args: finished.append(args))
    monkeypatch.setattr(jobs.learning_jobs_db, 'finish_job', finish)
    scheduled = []
    monkeypatch.setattr(
        jobs,
        'start_background_task',
        lambda coro, *, name=None: scheduled.append(coro) or asyncio.ensure_future(coro),
    )
    return SimpleNamespace(claimed=claimed, finished=finished, scheduled=scheduled, extract=extract, claim=claim)


def _claimed_job(**extra):
    job = {
        'job_id': 'j1',
        'target': 'person',
        'person_id': 'p1',
        'segment_ids': ['s0'],
        'lease_token': 'tok',
    }
    job.update(extra)
    return job


def test_run_executes_claimed_person_jobs(world):
    world.claimed.extend([_claimed_job(job_id='j1'), _claimed_job(job_id='j2', person_id='p2')])
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert [call.args[1] for call in world.extract.await_args_list] == ['p1', 'p2']
    assert [f[3] for f in world.finished] == ['tok', 'tok']
    assert [f[4] for f in world.finished] == ['stored', 'stored']


def test_run_respects_per_pass_bound(world):
    world.claimed.extend(_claimed_job(job_id=f'j{i}') for i in range(7))
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == jobs.VOICE_LEARNING_JOB_MAX_PER_PASS


def test_empty_ledger_is_noop(world):
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 0 and world.finished == []


def test_extractor_error_maps_to_bounded_outcome(world, monkeypatch):
    world.claimed.append(_claimed_job())
    world.extract.side_effect = RuntimeError('private failure detail')
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.finished[0][4] == 'error'


def test_owner_jobs_run_the_owner_worker(world, monkeypatch):
    owner = AsyncMock(return_value='stored')
    monkeypatch.setitem(
        sys.modules,
        'utils.speaker_tag_prompts.service',
        SimpleNamespace(store_owner_voice_sample=owner),
    )
    world.claimed.append(_claimed_job(target='owner', person_id=None, card_generation=3, segment_ids=['s0', 's1']))
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.extract.await_count == 0
    assert owner.await_args.kwargs['card_generation'] == 3
    assert owner.await_args.args[2] == ['s0', 's1']


def test_claim_failure_never_raises(world, monkeypatch):
    monkeypatch.setattr(jobs.learning_jobs_db, 'claim_next_job', MagicMock(side_effect=RuntimeError('storage gone')))
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))


def test_schedule_is_fail_open(world, monkeypatch):
    monkeypatch.setattr(
        jobs,
        'start_background_task',
        MagicMock(side_effect=RuntimeError('no loop')),
    )
    jobs.schedule_person_voice_learning_retry(UID, CONV)


def test_schedule_dispatches_tracked_task(world):
    async def run():
        jobs.schedule_person_voice_learning_retry(UID, CONV)
        await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()})

    asyncio.run(run())
    assert len(world.scheduled) == 1


def test_schedule_dedupes_and_bounds_in_flight(world, monkeypatch):
    async def hang(uid, cid):
        await asyncio.sleep(60)

    monkeypatch.setattr(jobs, 'run_speaker_learning_jobs', hang)

    async def run():
        jobs.schedule_person_voice_learning_retry(UID, CONV)
        jobs.schedule_person_voice_learning_retry(UID, CONV)
        jobs.schedule_person_voice_learning_retry(UID, 'conv-2')
        assert len(world.scheduled) == 2
        jobs._in_flight_retries.update((UID, f'filler-{i}') for i in range(15))
        jobs.schedule_person_voice_learning_retry(UID, 'conv-3')
        assert len(world.scheduled) == 2
        for task in asyncio.all_tasks() - {asyncio.current_task()}:
            task.cancel()
        await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()}, return_exceptions=True)

    asyncio.run(run())


def test_schedule_failure_closes_the_coroutine(world, monkeypatch):
    captured = []

    async def coro_factory(uid, cid):
        return None

    def make_coro(uid, cid):
        coro = coro_factory(uid, cid)
        captured.append(coro)
        return coro

    monkeypatch.setattr(jobs, 'run_speaker_learning_jobs', make_coro)
    monkeypatch.setattr(jobs, 'start_background_task', MagicMock(side_effect=RuntimeError('no loop')))
    jobs.schedule_person_voice_learning_retry(UID, CONV)
    assert not jobs._in_flight_retries
    assert captured and captured[0].cr_frame is None


def test_sync_retry_schedules_only_unfenced_conversations(world):
    response = {
        'new_memories': {'a', 'b'},
        'updated_memories': {'c'},
        'fenced': {'b'},
    }

    async def run():
        jobs.schedule_person_voice_learning_retries(UID, response, 'fenced')
        await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()})

    asyncio.run(run())
    assert len(world.scheduled) == 2


def test_schedule_reprocessed_learning_sets_header_and_task():
    tasks = []
    background_tasks = SimpleNamespace(add_task=lambda fn, *a: tasks.append((fn, a)))
    response = SimpleNamespace(headers={})
    conversation = SimpleNamespace(id='conv-9')
    result = jobs.schedule_reprocessed_learning(
        'u', conversation, background_tasks, response=response, receipt_applied=True
    )
    assert result is conversation
    assert response.headers['X-Omi-Speaker-Receipt-Summary'] == '1'
    assert tasks == [(jobs.run_speaker_learning_jobs, ('u', 'conv-9'))]


def test_schedule_reprocessed_learning_without_tasks_only_returns():
    conversation = SimpleNamespace(id='conv-9')
    response = SimpleNamespace(headers={})
    assert jobs.schedule_reprocessed_learning('u', conversation, None, response=response) is conversation
    assert response.headers == {}


@pytest.mark.anyio
async def test_finalizer_completion_schedules_learning_retry(monkeypatch):
    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(
        id='conversation-1',
        status=ConversationStatus.completed,
        language='en',
        source=SimpleNamespace(value='omi'),
        external_data=None,
        discarded=False,
        is_locked=False,
        started_at=datetime(2026, 8, 19, 12, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 19, 12, tzinfo=timezone.utc) + timedelta(minutes=10),
        transcript_segments=[SimpleNamespace(text='substantive exchange', start=0, end=60)],
        structured=SimpleNamespace(title='Captured title', overview='Captured overview'),
    )

    async def hang(uid, cid):
        await asyncio.sleep(60)

    monkeypatch.setattr(jobs, 'run_speaker_learning_jobs', hang)
    scheduled = MagicMock(side_effect=lambda uid, cid: jobs.schedule_person_voice_learning_retry(uid, cid))
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args, **kwargs: {
            'id': 'conversation-1',
            'status': ConversationStatus.completed.value,
            'discarded': False,
        },
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', MagicMock())
    monkeypatch.setattr(persisted_finalizer, 'smart_merge_step', AsyncMock(return_value=False))
    monkeypatch.setattr(persisted_finalizer, 'link_duplicate_captures', MagicMock())
    monkeypatch.setattr(persisted_finalizer, 'trigger_external_integrations', AsyncMock())
    monkeypatch.setattr(persisted_finalizer, 'record_finalized_meeting_receipt', MagicMock())
    monkeypatch.setattr(persisted_finalizer, 'schedule_person_voice_learning_retry', scheduled)

    async def disabled(*_args, **_kwargs):
        return SimpleNamespace(enabled=False, account_generation=None)

    monkeypatch.setattr(persisted_finalizer, 'resolve_frame_request_authority', disabled)
    monkeypatch.setattr(
        persisted_finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *args: {'status': 'claimed', 'fanout_key': 'conversation:conversation-1:finalization'},
    )
    monkeypatch.setattr(
        persisted_finalizer.lifecycle_service, 'complete_finalization_fanout', MagicMock(return_value=True)
    )

    try:
        result = await persisted_finalizer.finalize_persisted_conversation(
            'uid-1', 'conversation-1', finalization_job_id='job-1', dispatch_generation=2, lease_epoch=3
        )
        assert result == persisted_finalizer.ConversationFinalizationDisposition.completed
        scheduled.assert_called_once_with('uid-1', 'conversation-1')
        assert (
            'uid-1',
            'conversation-1',
        ) in jobs._in_flight_retries, 'finalization returned completed while the teaching task was still pending'
    finally:
        for task in asyncio.all_tasks() - {asyncio.current_task()}:
            task.cancel()
        await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()}, return_exceptions=True)


@pytest.mark.anyio
@pytest.mark.parametrize('fanout_status', ['fenced', 'failed'])
async def test_finalizer_fenced_or_failed_fanout_never_schedules(monkeypatch, fanout_status):
    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(
        id='conversation-1',
        status=ConversationStatus.completed,
        language='en',
        discarded=False,
        is_locked=False,
        transcript_segments=[],
        structured=SimpleNamespace(title='t', overview='o'),
    )
    scheduled = MagicMock()
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args, **kwargs: {
            'id': 'conversation-1',
            'status': ConversationStatus.completed.value,
            'discarded': False,
        },
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', MagicMock())
    monkeypatch.setattr(persisted_finalizer, 'smart_merge_step', AsyncMock(return_value=False))
    monkeypatch.setattr(persisted_finalizer, 'link_duplicate_captures', MagicMock())
    monkeypatch.setattr(persisted_finalizer, 'trigger_external_integrations', AsyncMock())
    monkeypatch.setattr(persisted_finalizer, 'record_finalized_meeting_receipt', MagicMock())
    monkeypatch.setattr(persisted_finalizer, 'schedule_person_voice_learning_retry', scheduled)

    async def disabled(*_args, **_kwargs):
        return SimpleNamespace(enabled=False, account_generation=None)

    monkeypatch.setattr(persisted_finalizer, 'resolve_frame_request_authority', disabled)

    if fanout_status == 'fenced':
        monkeypatch.setattr(
            persisted_finalizer.lifecycle_service,
            'claim_finalization_fanout',
            lambda *args: {'status': 'fenced'},
        )
        result = await persisted_finalizer.finalize_persisted_conversation(
            'uid-1', 'conversation-1', finalization_job_id='job-1', dispatch_generation=2, lease_epoch=3
        )
        assert result == persisted_finalizer.ConversationFinalizationDisposition.fenced
    else:
        monkeypatch.setattr(
            persisted_finalizer.lifecycle_service,
            'claim_finalization_fanout',
            lambda *args: {'status': 'claimed', 'fanout_key': 'k'},
        )
        monkeypatch.setattr(
            persisted_finalizer.lifecycle_service, 'complete_finalization_fanout', MagicMock(return_value=False)
        )
        with pytest.raises(persisted_finalizer.ConversationFinalizationError):
            await persisted_finalizer.finalize_persisted_conversation(
                'uid-1', 'conversation-1', finalization_job_id='job-1', dispatch_generation=2, lease_epoch=3
            )
    scheduled.assert_not_called()


def test_deadline_finishes_in_flight_job_as_timeout(world, monkeypatch):
    world.claimed.append(_claimed_job())

    async def slow(*args):
        await asyncio.sleep(60)

    world.extract.side_effect = slow
    # Leave room for the claim and executor handoff on a busy CI host; the
    # sleeping extractor still has to be cancelled by the deadline.
    monkeypatch.setattr(jobs, 'VOICE_LEARNING_RETRY_DEADLINE_SECONDS', 1.0)
    asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.finished and world.finished[0][4] == 'timeout'
    assert world.extract.await_count == 1


def test_cancellation_is_never_swallowed(world, monkeypatch):
    world.claimed.append(_claimed_job())

    async def cancelled(*args):
        raise asyncio.CancelledError()

    world.extract.side_effect = cancelled
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(jobs.run_speaker_learning_jobs(UID, CONV))
    assert world.finished and world.finished[0][4] == 'timeout'
