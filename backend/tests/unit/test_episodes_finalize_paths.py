"""Every finalize path closes the live episode when it starts and runs the episode hook after processing.

The pendant double-tap and the app's Wrap up reach ``POST /v1/conversations`` (synchronous);
desktop reaches ``POST /v1/conversations/{id}/finalize``; listen and quiet recovery reach the
durable finalizer. ``test_episodes_service`` covers what the close and the hook do.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from config import episodes as config
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from utils.conversations import finalizer
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.episodes import finalize as episode_finalize

_UID = 'finalize-paths-uid'
_STARTED = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_PERCENT_ENV, raising=False)


@pytest.fixture(scope='module')
def conv():
    import routers.conversations as conversations_router

    return conversations_router


def _conversation(status: ConversationStatus) -> Conversation:
    return Conversation(
        id='conv-finalize',
        created_at=_STARTED,
        started_at=_STARTED,
        finished_at=_STARTED,
        language='en',
        structured=Structured(title=''),
        transcript_segments=[],
        status=status,
        source=ConversationSource.omi,
    )


@contextmanager
def _noop_guard(*_args: Any, **_kwargs: Any):
    yield


def _episode_spies(monkeypatch, module, timeline):
    monkeypatch.setattr(
        module.episode_finalize,
        'close_now',
        lambda uid, cid, trigger, source=None: timeline.append(('close', cid, trigger)) or 'closed',
    )
    monkeypatch.setattr(
        module.episode_finalize,
        'schedule_after_finalization',
        lambda uid, cid, trigger: timeline.append(('after', cid, trigger)),
    )


def _drive_sync_route(conv, monkeypatch, *, persisted=True):
    timeline: list[tuple] = []
    in_progress = _conversation(ConversationStatus.in_progress)
    processed = _conversation(ConversationStatus.completed)

    def process(_uid, _language, conversation, **kwargs):
        timeline.append(('process', conversation.id, kwargs.get('trigger')))
        kwargs['persistence_observer'](persisted)
        return processed

    monkeypatch.setattr(conv, 'retrieve_in_progress_conversation', lambda uid: {'id': in_progress.id})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: in_progress)
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid})
    monkeypatch.setattr(conv.lifecycle_service, 'admit_processing', lambda uid, cid: True)
    monkeypatch.setattr(conv.lifecycle_service, 'processing_admission_guard', _noop_guard)
    monkeypatch.setattr(conv.redis_db, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(conv.redis_db, 'get_in_progress_conversation_id', lambda uid: in_progress.id)
    monkeypatch.setattr(conv.redis_db, 'remove_in_progress_conversation_id', lambda uid: None)
    monkeypatch.setattr(conv, 'process_conversation', process)
    monkeypatch.setattr(conv, 'trigger_external_integrations', AsyncMock(return_value=[]))
    _episode_spies(monkeypatch, conv, timeline)
    conv.process_in_progress_conversation(uid=_UID)
    return timeline


def test_sync_finalize_closes_the_episode_before_processing_and_runs_the_hook_after(conv, monkeypatch):
    timeline = _drive_sync_route(conv, monkeypatch)
    final = ProcessingTrigger.CLIENT_FINALIZE
    assert timeline == [
        ('close', 'conv-finalize', final),
        ('process', 'conv-finalize', final),
        ('after', 'conv-finalize', final),
    ]


def test_sync_finalize_that_lost_ownership_runs_no_hook(conv, monkeypatch):
    timeline = _drive_sync_route(conv, monkeypatch, persisted=False)
    assert [step for step, *_ in timeline] == ['close', 'process']


def test_sync_finalize_that_lost_admission_leaves_the_episode_alone(conv, monkeypatch):
    timeline: list[tuple] = []
    in_progress = _conversation(ConversationStatus.in_progress)
    monkeypatch.setattr(conv, 'retrieve_in_progress_conversation', lambda uid: {'id': in_progress.id})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: in_progress)
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid})
    monkeypatch.setattr(conv.lifecycle_service, 'admit_processing', lambda uid, cid: False)
    monkeypatch.setattr(conv.redis_db, 'get_cached_user_geolocation', lambda uid: None)
    _episode_spies(monkeypatch, conv, timeline)
    # A second double-tap on the same conversation: the first request owns it, this one is a no-op.
    conv.process_in_progress_conversation(uid=_UID)
    assert timeline == []


def test_durable_client_finalize_closes_the_episode_with_the_request(conv, monkeypatch):
    timeline: list[tuple] = []
    in_progress = _conversation(ConversationStatus.in_progress)
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: in_progress)
    monkeypatch.setattr(conv.byok, 'has_byok_keys', lambda: False)
    monkeypatch.setattr(
        conv.lifecycle_service,
        'request_finalization',
        lambda *a, **k: timeline.append(('enqueue',)) or {'route': 'cloud_tasks', 'job_id': 'job-1'},
    )
    monkeypatch.setattr(conv.redis_db, 'get_in_progress_conversation_id', lambda uid: None)
    _episode_spies(monkeypatch, conv, timeline)
    response = conv.finalize_conversation('conv-finalize', request=None, uid=_UID)
    assert response.conversation.status == ConversationStatus.processing
    # The worker runs the post-processing hook; the route only closes.
    assert timeline == [('enqueue',), ('close', 'conv-finalize', ProcessingTrigger.CLIENT_FINALIZE)]


# --------------------------------------------------------------------------- durable finalizer


class _Stop(Exception):
    pass


def test_durable_finalizer_closes_the_episode_before_processing(monkeypatch):
    seen: list[tuple] = []
    row = {'id': 'c1', 'source': 'omi'}
    conversation = _conversation(ConversationStatus.processing)

    async def admitted(*_args, **_kwargs):
        return None, row, conversation

    async def evidence(*_args, **_kwargs):
        seen.append(('processing',))
        raise _Stop

    async def run_inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(finalizer, '_load_admitted_conversation', admitted)
    monkeypatch.setattr(finalizer, 'await_meeting_evidence', evidence)
    monkeypatch.setattr(finalizer, 'run_blocking', run_inline)
    monkeypatch.setattr(
        finalizer, 'close_episode_now', lambda uid, cid, trigger, source: seen.append(('close', cid, trigger, source))
    )
    with pytest.raises(_Stop):
        asyncio.run(
            finalizer.finalize_persisted_conversation(
                _UID,
                'c1',
                finalization_job_id='job-1',
                dispatch_generation=1,
                lease_epoch=1,
                trigger=ProcessingTrigger.SERVER_RECOVERY,
            )
        )
    assert seen == [('close', 'c1', ProcessingTrigger.SERVER_RECOVERY, 'omi'), ('processing',)]


def test_durable_finalizer_close_is_bounded_and_fail_open(monkeypatch):
    budgets = []

    async def expired(awaitable, timeout):
        budgets.append(timeout)
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(finalizer.asyncio, 'wait_for', expired)
    asyncio.run(finalizer._episode_at_finalization_start(_UID, 'c1', {'id': 'c1'}, ProcessingTrigger.CAPTURE_END))
    assert budgets == [finalizer.EPISODE_CLOSE_TIMEOUT_SECONDS]
    # Nothing to close without a row, and nothing at all with episodes off.
    asyncio.run(finalizer._episode_at_finalization_start(_UID, 'c1', None, ProcessingTrigger.CAPTURE_END))
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    asyncio.run(finalizer._episode_at_finalization_start(_UID, 'c1', {'id': 'c1'}, ProcessingTrigger.CAPTURE_END))
    assert budgets == [finalizer.EPISODE_CLOSE_TIMEOUT_SECONDS]


# --------------------------------------------------------------------------- shared hooks


def test_close_now_passes_the_trigger_and_never_raises(monkeypatch):
    from utils.episodes import service

    calls = []
    monkeypatch.setattr(episode_finalize.client_gate, 'client_seen_cached', lambda uid: True)
    monkeypatch.setattr(service, 'close_on_finalize', lambda uid, cid, **kw: calls.append((cid, kw)) or 'closed')
    assert episode_finalize.close_now(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE) == 'closed'
    assert calls == [('c1', {'trigger': 'client_finalize', 'source': None})]

    def boom(*_args, **_kwargs):
        raise RuntimeError('episode store down')

    monkeypatch.setattr(service, 'close_on_finalize', boom)
    assert episode_finalize.close_now(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE) == 'error'
    monkeypatch.setattr(episode_finalize.client_gate, 'client_seen_cached', lambda uid: False)
    assert episode_finalize.close_now(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE) == 'skipped_no_client'
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    assert episode_finalize.close_now(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE) == 'disabled'


def test_schedule_after_finalization_runs_the_finalizer_hook_off_the_request(monkeypatch):
    from database import conversations as conversations_db
    from utils.episodes import service

    submitted = []
    hooked = []
    monkeypatch.setattr(
        episode_finalize, 'submit_with_context', lambda executor, fn, *args: submitted.append((fn, args))
    )
    episode_finalize.schedule_after_finalization(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE)
    assert len(submitted) == 1
    row = {'id': 'c1', 'source': 'omi'}
    monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, cid: row if cid == 'c1' else None)
    monkeypatch.setattr(service, 'on_conversation_finalized', lambda *a, **k: hooked.append((a, k)))
    fn, args = submitted[0]
    fn(*args)
    assert hooked == [((_UID, 'c1', row), {'trigger': 'client_finalize'})]


def test_schedule_after_finalization_survives_a_saturated_pool(monkeypatch):
    def saturated(*_args, **_kwargs):
        raise RuntimeError('episode pool saturated')

    monkeypatch.setattr(episode_finalize, 'submit_with_context', saturated)
    episode_finalize.schedule_after_finalization(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE)
