"""Finalization voice-learning retry coordinator contracts.

Reads the fresh conversation, retries only receipt-named people still missing a
usable voiceprint, stays inside the people/deadline bounds, and can never move
finalization's disposition.
"""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.conversation import ConversationStatus
from utils import speaker_learning_jobs as jobs
from utils.conversations import finalizer as persisted_finalizer

UID = 'account-a'
CONV = 'conv-1'


def _conv(receipt=None, segments=None):
    return {
        'transcript_segments': segments or [],
        'manual_speaker_assignments': receipt or {},
        'audio_files': [{'chunk_timestamps': [1700000000.0]}],
        'started_at': 1700000000.0,
    }


def _receipt_speakers(*person_ids):
    return {
        'speakers': {
            str(index): {'person_id': pid, 'is_user': False, 'generation': 1} for index, pid in enumerate(person_ids)
        },
        'generation': 1,
    }


def _segments_for(*person_ids):
    return [
        {
            'id': f's{index}',
            'start': index * 10.0,
            'end': index * 10.0 + 6.0,
            'speaker_id': index,
            'person_id': pid,
            'is_user': False,
            'text': f'segment {index}',
        }
        for index, pid in enumerate(person_ids)
    ]


@pytest.fixture(autouse=True)
def clear_in_flight():
    jobs._in_flight_retries.clear()
    yield
    jobs._in_flight_retries.clear()


@pytest.fixture
def world(monkeypatch):
    conversation = [_conv()]
    people = {}
    extracted = []
    monkeypatch.setattr(
        jobs.conversations_db,
        'get_conversation',
        lambda uid, cid: deepcopy(conversation[0]) if conversation[0] else None,
    )
    monkeypatch.setattr(jobs.users_db, 'get_person', lambda uid, pid: deepcopy(people.get(pid)))
    extract = AsyncMock(side_effect=lambda uid, pid, cid, segment_ids: extracted.append((pid, segment_ids)))
    monkeypatch.setattr(jobs, 'extract_speaker_samples', extract)
    scheduled = []
    monkeypatch.setattr(
        jobs,
        'start_background_task',
        lambda coro, *, name=None: scheduled.append(coro) or asyncio.ensure_future(coro),
    )
    return SimpleNamespace(
        conversation=conversation, people=people, extracted=extracted, scheduled=scheduled, extract=extract
    )


def ready_person():
    return {
        'speech_samples': ['a.wav'],
        'speech_samples_version': 3,
        'speaker_embedding': [1.0, 0.0],
    }


def test_retry_extracts_for_receipt_person_without_voiceprint(world):
    world.conversation[0] = _conv(receipt=_receipt_speakers('person-1'), segments=_segments_for('person-1'))
    world.people['person-1'] = {'name': 'Alex'}
    asyncio.run(jobs.retry_people_without_voiceprint(UID, CONV))
    assert [call[0] for call in world.extracted] == ['person-1']
    assert world.extracted[0][1] == ['s0']


def test_ready_voiceprint_is_skipped(world):
    world.conversation[0] = _conv(receipt=_receipt_speakers('person-1'), segments=_segments_for('person-1'))
    world.people['person-1'] = ready_person()
    asyncio.run(jobs.retry_people_without_voiceprint(UID, CONV))
    assert world.extracted == []


def test_training_opt_out_person_is_excluded(world):
    receipt = _receipt_speakers('person-1')
    receipt['speakers']['0']['use_for_speech_training'] = False
    world.conversation[0] = _conv(receipt=receipt, segments=_segments_for('person-1'))
    world.people['person-1'] = {'name': 'Alex'}
    asyncio.run(jobs.retry_people_without_voiceprint(UID, CONV))
    assert world.extracted == [], 'use_for_speech_training=False must not teach'


def test_people_bound_and_deadline(world, monkeypatch):
    person_ids = [f'person-{i}' for i in range(7)]
    world.conversation[0] = _conv(receipt=_receipt_speakers(*person_ids), segments=_segments_for(*person_ids))
    for pid in person_ids:
        world.people[pid] = {'name': pid}
    seen = []
    monkeypatch.setattr(
        jobs.users_db, 'get_person', lambda uid, pid: seen.append(pid) or deepcopy(world.people.get(pid))
    )
    asyncio.run(jobs.retry_people_without_voiceprint(UID, CONV))
    assert len(world.extracted) == jobs.VOICE_LEARNING_RETRY_MAX_PEOPLE
    assert len(seen) == jobs.VOICE_LEARNING_RETRY_MAX_PEOPLE, 'collection stops once the cap is full'

    world.extracted.clear()

    async def slow(*args):
        await asyncio.sleep(60)

    extract = AsyncMock(side_effect=slow)
    monkeypatch.setattr(jobs, 'extract_speaker_samples', extract)
    monkeypatch.setattr(jobs, 'VOICE_LEARNING_RETRY_DEADLINE_SECONDS', 0.05)
    asyncio.run(jobs.retry_people_without_voiceprint(UID, CONV))
    assert extract.call_count <= jobs.VOICE_LEARNING_RETRY_MAX_PEOPLE


def test_job_failure_never_raises(world):
    world.conversation[0] = _conv(receipt=_receipt_speakers('person-1'), segments=_segments_for('person-1'))
    world.people['person-1'] = {'name': 'Alex'}
    world.extract.side_effect = RuntimeError('private failure detail')
    asyncio.run(jobs.retry_people_without_voiceprint(UID, CONV))


def test_missing_conversation_is_noop(world):
    world.conversation[0] = None
    asyncio.run(jobs.retry_people_without_voiceprint(UID, CONV))
    assert world.extracted == []


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

    world.conversation[0] = None
    asyncio.run(run())
    assert len(world.scheduled) == 1


def test_discarded_or_locked_conversation_teaches_nothing(world):
    for flag in ('discarded', 'is_locked', 'deleted'):
        conv = _conv(receipt=_receipt_speakers('person-1'), segments=_segments_for('person-1'))
        conv[flag] = True
        world.conversation[0] = conv
        world.people['person-1'] = {'name': 'Alex'}
        asyncio.run(jobs.retry_people_without_voiceprint(UID, CONV))
        assert world.extracted == []
        world.extracted.clear()


def test_ready_people_do_not_consume_the_cap(world):
    person_ids = [f'person-{i}' for i in range(7)]
    world.conversation[0] = _conv(receipt=_receipt_speakers(*person_ids), segments=_segments_for(*person_ids))
    for pid in person_ids[:5]:
        world.people[pid] = ready_person()
    for pid in person_ids[5:]:
        world.people[pid] = {'name': pid}
    asyncio.run(jobs.retry_people_without_voiceprint(UID, CONV))
    assert sorted(call[0] for call in world.extracted) == [
        'person-5',
        'person-6',
    ], 'ineligible targets must be filtered before the five-person cap'


def test_schedule_dedupes_and_bounds_in_flight(world, monkeypatch):
    async def hang(uid, cid):
        await asyncio.sleep(60)

    monkeypatch.setattr(jobs, 'retry_people_without_voiceprint', hang)

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

    monkeypatch.setattr(jobs, 'retry_people_without_voiceprint', make_coro)
    monkeypatch.setattr(jobs, 'start_background_task', MagicMock(side_effect=RuntimeError('no loop')))
    jobs.schedule_person_voice_learning_retry(UID, CONV)
    assert not jobs._in_flight_retries
    assert captured and captured[0].cr_frame is None


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

    monkeypatch.setattr(jobs, 'retry_people_without_voiceprint', hang)
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
    monkeypatch.setattr(persisted_finalizer, 'persist_capture_arrival_intent', MagicMock())
    monkeypatch.setattr(persisted_finalizer, 'smart_merge_step', AsyncMock(return_value=False))
    monkeypatch.setattr(persisted_finalizer, 'link_duplicate_captures', MagicMock())
    monkeypatch.setattr(persisted_finalizer, 'trigger_external_integrations', AsyncMock())
    monkeypatch.setattr(persisted_finalizer, 'record_and_persist_finalized_meeting_receipt', MagicMock())
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
    monkeypatch.setattr(persisted_finalizer, 'persist_capture_arrival_intent', MagicMock())
    monkeypatch.setattr(persisted_finalizer, 'smart_merge_step', AsyncMock(return_value=False))
    monkeypatch.setattr(persisted_finalizer, 'link_duplicate_captures', MagicMock())
    monkeypatch.setattr(persisted_finalizer, 'trigger_external_integrations', AsyncMock())
    monkeypatch.setattr(persisted_finalizer, 'record_and_persist_finalized_meeting_receipt', MagicMock())
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
