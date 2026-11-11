"""The live session and durable worker converge after floor-off processing faults."""

import asyncio
import json
import logging
import struct
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import anthropic
import httpx
import pytest
from fastapi import HTTPException

from database import conversation_finalization_jobs as jobs
from models.conversation import Conversation
from models.structured import Structured
from services import conversation_finalization as service
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.utils.test_listen_pusher_session import make_session
from utils import pusher_finalization as worker
from utils.conversations import finalizer, process_conversation as processing, typesense_index
from utils.conversations.processing_retry import (
    DETERMINISTIC_PROCESSING_FAILURE,
    TRANSIENT_PROCESSING_FAILURE,
    processing_failure_code,
)
from utils.llm.notes_short_clip import quiet_minimum
from utils.observability.fallback import record_fallback

NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)
JOB = (jobs.FINALIZATION_JOBS_COLLECTION, 'job-1')
ROW = ('users', 'uid-1', 'conversations', 'conv-1')


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def provider_timeout():
    return anthropic.APITimeoutError(request=httpx.Request('POST', 'https://provider.invalid'))


@pytest.mark.parametrize('failure', [AttributeError('synthetic'), HTTPException(500, 'processing failed')])
def test_processing_500_and_programming_errors_are_deterministic(failure):
    assert processing_failure_code(failure) == DETERMINISTIC_PROCESSING_FAILURE


@pytest.mark.parametrize('status', [429, 500, 503])
def test_provider_status_is_transient(status):
    response = httpx.Response(status, request=httpx.Request('POST', 'https://provider.invalid'))
    error = anthropic.APIStatusError('synthetic provider failure', response=response, body=None)
    assert processing_failure_code(error) == TRANSIENT_PROCESSING_FAILURE


def test_timeout_classification_survives_processing_and_rollback_wrappers():
    timeout = provider_timeout()
    processing_error = HTTPException(500, 'processing failed')
    processing_error.__cause__ = timeout
    rollback_error = ValueError('The transaction has no transaction ID, so it cannot be rolled back.')
    rollback_error.__context__ = processing_error
    assert processing_failure_code(rollback_error) == TRANSIENT_PROCESSING_FAILURE


@pytest.fixture
def durable_loop(monkeypatch):
    monkeypatch.setenv('NOTES_SHORT_CLIP_FLOOR', 'false')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    monkeypatch.delenv('NOTES_PACKET_V2_MODE_SERVE_PERCENT', raising=False)
    monkeypatch.delenv('NOTES_PACKET_V2_MODE_SERVE_UID_SHA256S', raising=False)
    monkeypatch.setenv('CONVERSATION_OCCASION_RELEVANCE_ENABLED', 'false')
    monkeypatch.setenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', 'false')
    conversation = Conversation(
        id=ROW[-1],
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
        structured=Structured(),
        status='processing',
        source='omi',
        transcript_segments=[dict(text='A tiny recording', speaker='SPEAKER_00', is_user=True, start=0, end=2)],
    )
    store = StrictFirestore(
        {
            JOB: dict(
                uid=ROW[1],
                conversation_id=ROW[-1],
                status='queued',
                dispatch_generation=1,
                lease_epoch=0,
                attempt_count=0,
                fanout_status='pending',
                finalization_revision=1,
                created_at=NOW,
            ),
            ROW: {**conversation.model_dump(), 'finalization_job_id': JOB[-1], 'finalization_revision': 1},
        }
    )
    monkeypatch.setattr(jobs, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    monkeypatch.setattr(jobs, 'stop_quiet_checks_for_job', Mock())
    monkeypatch.setattr(jobs, 'prepare_calendar_probe', lambda *a: None)
    monkeypatch.setattr(jobs.conversations_db, 'invalidate_people_stats_cache', Mock())
    monkeypatch.setattr(jobs.conversations_db, 'sync_conversation_search_index_public', Mock())
    monkeypatch.setattr(typesense_index, 'sync_conversation_index_after_write', Mock())

    async def inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(worker, 'run_blocking', inline)
    monkeypatch.setattr(finalizer, 'run_blocking', inline)
    monkeypatch.setattr(worker, 'get_listen_finalization_tasks_max_attempts', lambda: 5)
    monkeypatch.setattr(worker, 'record_capture_finalization_terminal', Mock())
    monkeypatch.setattr(worker, 'record_conversation_finalization_client_terminal', Mock())
    monkeypatch.setattr(service, 'record_capture_finalization_terminal', Mock())
    monkeypatch.setattr(service, 'record_conversation_finalization_client_terminal', Mock())

    async def load(*args):
        return None, store.rows[ROW], conversation

    monkeypatch.setattr(finalizer, '_load_admitted_conversation', load)
    monkeypatch.setattr(finalizer, '_episode_at_finalization_start', AsyncMock())
    monkeypatch.setattr(finalizer, 'await_meeting_evidence', AsyncMock(return_value='not_applicable'))
    monkeypatch.setattr(finalizer, 'get_cached_user_geolocation', lambda *_: None)
    monkeypatch.setattr(finalizer, 'apply_call_metadata', lambda _uid, conv: conv)
    monkeypatch.setattr(finalizer, 'warm_rollout_cohorts', AsyncMock())
    monkeypatch.setattr(finalizer, '_maybe_start_shadow', Mock())
    monkeypatch.setattr(finalizer.member_notes, 'waits', lambda *a: False)
    monkeypatch.setattr(finalizer, 'process_with_episode_budget', lambda fn, *a, **kw: fn(*a, **kw))
    monkeypatch.setattr(
        finalizer, 'process_conversation', lambda uid, lang, conv, **kw: processing._get_structured(uid, lang, conv)
    )
    monkeypatch.setattr(processing.notification_db, 'get_user_time_zone', lambda *_: 'UTC')
    monkeypatch.setattr(processing.users_db, 'get_user_language_preference', lambda *_: 'en')
    monkeypatch.setattr(processing.redis_db, 'get_user_preferred_app', lambda *_: None)
    monkeypatch.setattr(
        processing, 'conversation_transcripts_for_llm', lambda *a: ('A tiny recording', 'A tiny recording', {})
    )
    monkeypatch.setattr(processing, 'should_discard_conversation', lambda *a, **kw: False)
    monkeypatch.setattr(processing, 'adjacent_conversation', lambda *a: None)
    monkeypatch.setattr(processing, '_calendar_overlap_retains_conversation', lambda *a: False)
    monkeypatch.setattr(processing, 'rich_notes_inputs', lambda *a, **kw: (None, None, None, None, 0))
    monkeypatch.setattr(processing, 'conversation_known_spellings', lambda *_: [])
    monkeypatch.setattr(processing, 'before_notes', lambda *a, **kw: None)
    monkeypatch.setattr(processing, '_fetch_dedup_candidates_for_query', lambda *a: [])
    monkeypatch.setattr(processing, 'notes_agent_inputs', lambda *a: {})
    assert quiet_minimum(ROW[1], conversation) is None
    return store, conversation


class LoopSocket:
    """Opcode 104 -> real durable worker -> opcode 201, with a synthetic clock."""

    def __init__(self, clock, active):
        self.clock, self.active, self.incoming, self.sent = clock, active, [], []

    async def send(self, frame):
        if struct.unpack('<I', frame[:4])[0] != 104:
            return
        self.sent.append(frame)
        request = json.loads(frame[4:])
        await worker.process_conversation_task(
            ROW[1],
            ROW[-1],
            'en',
            self,
            finalization_job_id=request['finalization_job_id'],
            dispatch_generation=request['dispatch_generation'],
        )

    async def send_bytes(self, frame):
        self.incoming.append(frame)

    async def recv(self):
        # Let the 300 s cooldown elapse instantly; the test remains hermetic.
        self.clock[0] += 301
        assert len(self.sent) <= 8, 'processing storm exceeded the session budget'
        if not self.incoming:
            raise asyncio.TimeoutError
        return self.incoming.pop(0)


@pytest.mark.anyio
@pytest.mark.parametrize('seam', ['attribute', 'processing_500', 'transaction'])
async def test_session_dead_letters_deterministic_floor_off_failure_after_one_burst(
    monkeypatch, durable_loop, caplog, seam
):
    store, _ = durable_loop
    errors = {
        'attribute': AttributeError('synthetic processing bug'),
        'processing_500': HTTPException(500, 'synthetic processing error'),
        'transaction': ValueError('The transaction has no transaction ID, so it cannot be committed.'),
    }
    paid = Mock(side_effect=errors[seam])
    monkeypatch.setattr(processing, 'get_conversation_notes', paid)
    clock, active = [1000.0], {'active': True}
    socket = LoopSocket(clock, active)
    session = make_session(
        ws=socket,
        active_ref=active,
        deps_overrides={
            'now': lambda: clock[0],
            'get_byok_keys': lambda: {},
            'is_active': lambda: bool(session.pending_conversation_requests),
        },
    )
    session.pusher_connected, session.pusher_ws = True, socket
    with caplog.at_level(logging.WARNING):
        await session.request_conversation_processing(ROW[-1], JOB[-1], 1)
        await asyncio.wait_for(session.pusher_receive(), 3)
    assert paid.call_count == len(socket.sent) == 4
    assert store.rows[JOB]['status'] == 'dead_letter'
    assert store.rows[JOB]['attempt_count'] == 4
    assert store.rows[JOB].get('budget_requeue_count', 0) == 0
    assert store.rows[ROW]['status'] == 'completed'
    assert not session.pending_conversation_requests
    assert any('listen finalization dead_letter terminal=True' in r.message for r in caplog.records)
    assert not await session.request_conversation_processing(ROW[-1], JOB[-1], 1)
    assert paid.call_count == 4  # Same terminal transaction/generation cannot re-enter.


@pytest.mark.anyio
async def test_floor_off_provider_timeout_recovers_in_second_burst(monkeypatch, durable_loop):
    store, _ = durable_loop
    paid = Mock(side_effect=provider_timeout())
    monkeypatch.setattr(processing, 'get_conversation_notes', paid)
    original = worker.finalize_persisted_conversation
    calls = 0

    async def recover(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls <= 4:
            return await original(*args, **kwargs)
        assert jobs.mark_finalization_fanout_completed(JOB[-1], kwargs['dispatch_generation'], kwargs['lease_epoch'])
        return finalizer.ConversationFinalizationDisposition.completed

    monkeypatch.setattr(worker, 'finalize_persisted_conversation', recover)
    clock, active = [1000.0], {'active': True}
    socket = LoopSocket(clock, active)
    session = make_session(
        ws=socket,
        active_ref=active,
        deps_overrides={
            'now': lambda: clock[0],
            'get_byok_keys': lambda: {},
            'is_active': lambda: bool(session.pending_conversation_requests),
        },
    )
    session.pusher_connected, session.pusher_ws = True, socket
    await session.request_conversation_processing(ROW[-1], JOB[-1], 1)
    await asyncio.wait_for(session.pusher_receive(), 3)
    assert paid.call_count == 4 and len(socket.sent) == 5
    assert store.rows[JOB]['status'] == 'completed'
    assert session.callbacks == [ROW[-1]]


@pytest.mark.anyio
@pytest.mark.parametrize('post_commit_failure', ['ack', 'journey'])
async def test_committed_job_never_reenters_failure_transactions(monkeypatch, durable_loop, post_commit_failure):
    store, _ = durable_loop

    async def complete(*args, **kwargs):
        assert jobs.mark_finalization_fanout_completed(JOB[-1], kwargs['dispatch_generation'], kwargs['lease_epoch'])
        return finalizer.ConversationFinalizationDisposition.completed

    finalize = AsyncMock(side_effect=complete)
    monkeypatch.setattr(worker, 'finalize_persisted_conversation', finalize)
    retry = Mock(side_effect=AssertionError('completed transaction was released for retry'))
    monkeypatch.setattr(jobs, 'mark_finalization_retryable', retry)
    fallback = Mock(wraps=record_fallback)
    monkeypatch.setattr(worker, 'record_fallback', fallback)
    socket = Mock()
    socket.send_bytes = AsyncMock()
    if post_commit_failure == 'ack':
        socket.send_bytes.side_effect = OSError('source closed after commit')
    else:
        monkeypatch.setattr(
            worker, 'record_capture_finalization_terminal', Mock(side_effect=RuntimeError('telemetry failed'))
        )
    for _ in range(2):
        await worker.process_conversation_task(
            ROW[1], ROW[-1], 'en', socket, finalization_job_id=JOB[-1], dispatch_generation=1
        )
    assert store.rows[JOB]['status'] == 'completed'
    assert finalize.await_count == 1
    retry.assert_not_called()
    assert fallback.call_count >= 1
