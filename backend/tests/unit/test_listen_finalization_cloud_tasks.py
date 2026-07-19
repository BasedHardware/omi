"""Cloud Tasks task-schema contract for durable listen finalization."""

from __future__ import annotations

import asyncio
import json
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database import conversation_finalization_jobs as jobs_db
from database.firestore_transaction_retry import FirestoreContentionExhausted
from models.conversation_enums import ConversationStatus
from routers.conversation_finalization import _parse_task_payload
import routers.conversation_finalization as finalization_router
import routers.pusher as pusher_router
from utils.conversations import lifecycle as lifecycle_service
from utils import cloud_tasks
from utils.conversations.finalizer import ConversationFinalizationDisposition, ConversationFinalizationError
import utils.conversations.finalizer as persisted_finalizer


def _mock_lifecycle_conversation(monkeypatch, *, status: str = 'in_progress'):
    monkeypatch.setattr(
        lifecycle_service.conversations_db,
        'get_conversation',
        lambda uid, conversation_id: {'id': conversation_id, 'status': status},
    )


def test_enqueue_uses_only_opaque_job_routing_fields():
    with patch.object(cloud_tasks, '_enqueue_named_task') as enqueue:
        cloud_tasks.enqueue_listen_finalization_job('9ee6f9ce-d6dc-4b5d-bf13-f80eb4fabd36', 7)

    queue, url, task_id, payload = enqueue.call_args.args
    assert queue == ''
    assert url == ''
    assert task_id == 'listen-finalization-9ee6f9ce-d6dc-4b5d-bf13-f80eb4fabd36-7'
    assert payload == {'job_id': '9ee6f9ce-d6dc-4b5d-bf13-f80eb4fabd36', 'dispatch_generation': 7}
    assert set(enqueue.call_args.kwargs) == {'audience', 'invoker_sa'}


def test_worker_rejects_task_payloads_with_content_or_credentials():
    assert _parse_task_payload({'job_id': 'job-1', 'dispatch_generation': 1}) == ('job-1', 1)
    assert _parse_task_payload({'job_id': 'job-1', 'dispatch_generation': 1, 'byok_keys': {'openai': 'secret'}}) is None
    assert _parse_task_payload({'job_id': 'job-1', 'dispatch_generation': 1, 'transcript': 'private'}) is None
    assert _parse_task_payload({'job_id': 'job-1', 'dispatch_generation': 1, 'authorization': 'Bearer secret'}) is None


def test_platform_key_job_dispatches_to_cloud_tasks(monkeypatch):
    intent = {'job_id': 'job-1', 'status': 'queued', 'dispatch_generation': 2, 'requires_byok': False}
    enqueue = MagicMock()
    _mock_lifecycle_conversation(monkeypatch)
    monkeypatch.setattr(lifecycle_service.jobs_db, 'create_or_get_finalization_intent', MagicMock(return_value=intent))
    monkeypatch.setattr(lifecycle_service, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(lifecycle_service, 'enqueue_listen_finalization_job', enqueue)

    result = lifecycle_service.request_finalization('uid-1', 'conversation-1', has_byok_keys=False)

    assert result['route'] == 'cloud_tasks'
    enqueue.assert_called_once_with('job-1', 2)


def test_durable_finalization_acceptance_counts_only_a_new_outbox_job(monkeypatch):
    intent = {'job_id': 'job-1', 'status': 'queued', 'dispatch_generation': 2, 'requires_byok': False, 'created': True}
    accepted = MagicMock()
    _mock_lifecycle_conversation(monkeypatch)
    monkeypatch.setattr(lifecycle_service.jobs_db, 'create_or_get_finalization_intent', MagicMock(return_value=intent))
    monkeypatch.setattr(lifecycle_service, 'is_listen_finalization_dispatch_enabled', lambda: False)
    monkeypatch.setattr(lifecycle_service, 'record_journey_accepted', accepted)

    result = lifecycle_service.request_finalization('uid-1', 'conversation-1', has_byok_keys=False)

    assert result['route'] == 'pusher'
    accepted.assert_called_once_with('capture_finalization')


def test_durable_finalization_redelivery_does_not_count_as_new_traffic(monkeypatch):
    intent = {'job_id': 'job-1', 'status': 'queued', 'dispatch_generation': 2, 'requires_byok': False, 'created': False}
    accepted = MagicMock()
    _mock_lifecycle_conversation(monkeypatch)
    monkeypatch.setattr(lifecycle_service.jobs_db, 'create_or_get_finalization_intent', MagicMock(return_value=intent))
    monkeypatch.setattr(lifecycle_service, 'is_listen_finalization_dispatch_enabled', lambda: False)
    monkeypatch.setattr(lifecycle_service, 'record_journey_accepted', accepted)

    lifecycle_service.request_finalization('uid-1', 'conversation-1', has_byok_keys=False)

    accepted.assert_not_called()


def test_enqueue_failure_leaves_job_queued_for_reconciler(monkeypatch):
    intent = {'job_id': 'job-1', 'status': 'queued', 'dispatch_generation': 2, 'requires_byok': False}
    fallback = MagicMock()
    _mock_lifecycle_conversation(monkeypatch)
    monkeypatch.setattr(lifecycle_service.jobs_db, 'create_or_get_finalization_intent', MagicMock(return_value=intent))
    monkeypatch.setattr(lifecycle_service, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(
        lifecycle_service, 'enqueue_listen_finalization_job', MagicMock(side_effect=RuntimeError('offline'))
    )
    monkeypatch.setattr(lifecycle_service, 'record_fallback', fallback)

    result = lifecycle_service.request_finalization('uid-1', 'conversation-1', has_byok_keys=False)

    assert result['route'] == 'queued'
    fallback.assert_called_once()
    assert fallback.call_args.kwargs['reason'] == 'enqueue_failed'


def test_required_cloud_tasks_rejects_rest_admission_before_outbox_mutation(monkeypatch):
    create = MagicMock()
    monkeypatch.setattr(lifecycle_service.jobs_db, 'create_or_get_finalization_intent', create)
    monkeypatch.setattr(lifecycle_service, 'is_listen_finalization_dispatch_configured', lambda: False)

    with pytest.raises(lifecycle_service.FinalizationDispatchUnavailable):
        lifecycle_service.request_finalization(
            'uid-1',
            'conversation-1',
            has_byok_keys=False,
            require_cloud_tasks=True,
        )

    create.assert_not_called()


def test_durable_finalization_maps_exhausted_firestore_contention_to_retryable_admission_failure(monkeypatch):
    create = MagicMock(side_effect=FirestoreContentionExhausted('contention'))
    monkeypatch.setattr(lifecycle_service.jobs_db, 'create_or_get_finalization_intent', create)

    with pytest.raises(lifecycle_service.FinalizationDispatchUnavailable) as raised:
        lifecycle_service.request_finalization('uid-1', 'conversation-1', has_byok_keys=False)

    assert isinstance(raised.value.__cause__, FirestoreContentionExhausted)
    create.assert_called_once()


def test_listen_finalization_dispatch_configuration_requires_every_static_binding(monkeypatch):
    for name in (
        'SYNC_TASKS_PROJECT',
        'SYNC_TASKS_LOCATION',
        'SYNC_TASKS_INVOKER_SA',
        'LISTEN_FINALIZATION_TASKS_QUEUE',
        'LISTEN_FINALIZATION_TASKS_HANDLER_URL',
        'LISTEN_FINALIZATION_TASKS_INVOKER_SA',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('LISTEN_FINALIZATION_DISPATCH_MODE', 'cloud_tasks')

    assert cloud_tasks.is_listen_finalization_dispatch_configured() is False

    monkeypatch.setenv('SYNC_TASKS_PROJECT', 'project')
    monkeypatch.setenv('SYNC_TASKS_LOCATION', 'location')
    monkeypatch.setenv('LISTEN_FINALIZATION_TASKS_QUEUE', 'conversation-finalization')
    monkeypatch.setenv('LISTEN_FINALIZATION_TASKS_HANDLER_URL', 'https://example.invalid/finalize')
    monkeypatch.setenv('LISTEN_FINALIZATION_TASKS_INVOKER_SA', 'worker@example.invalid')

    assert cloud_tasks.is_listen_finalization_dispatch_configured() is True


def test_finalization_status_exposes_retry_and_terminal_state(monkeypatch):
    monkeypatch.setattr(
        lifecycle_service.conversations_db,
        'get_conversation',
        lambda uid, conversation_id: {'finalization_job_id': 'job-1'},
    )
    job = {'uid': 'uid-1', 'conversation_id': 'conversation-1', 'status': 'queued', 'attempt_count': 2}
    monkeypatch.setattr(lifecycle_service.jobs_db, 'get_finalization_job', lambda job_id: job)

    assert lifecycle_service.get_finalization_status('uid-1', 'conversation-1') == {
        'job_id': 'job-1',
        'status': 'queued',
        'terminal': False,
        'retryable': True,
        'attempt_count': 2,
        'task_retry_count': 0,
    }

    job['status'] = 'dead_letter'
    job['task_retry_count'] = 3
    assert lifecycle_service.get_finalization_status('uid-1', 'conversation-1') == {
        'job_id': 'job-1',
        'status': 'dead_letter',
        'terminal': True,
        'retryable': False,
        'attempt_count': 2,
        'task_retry_count': 3,
    }


def test_byok_live_session_uses_pusher_even_when_platform_jobs_use_cloud_tasks(monkeypatch):
    intent = {'job_id': 'job-1', 'status': 'blocked_byok', 'dispatch_generation': 1, 'requires_byok': True}
    enqueue = MagicMock()
    _mock_lifecycle_conversation(monkeypatch)
    resumed = {'job_id': 'job-1', 'status': 'queued', 'dispatch_generation': 1, 'requires_byok': True}
    monkeypatch.setattr(lifecycle_service.jobs_db, 'create_or_get_finalization_intent', MagicMock(return_value=intent))
    monkeypatch.setattr(lifecycle_service, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(lifecycle_service, 'enqueue_listen_finalization_job', enqueue)
    monkeypatch.setattr(
        lifecycle_service.jobs_db, 'resume_blocked_byok_job_for_live_session', MagicMock(return_value=resumed)
    )

    result = lifecycle_service.request_finalization('uid-1', 'conversation-1', has_byok_keys=True)

    assert result['route'] == 'pusher'
    enqueue.assert_not_called()


def test_byok_job_without_current_keys_remains_explicitly_blocked(monkeypatch):
    intent = {'job_id': 'job-1', 'status': 'blocked_byok', 'dispatch_generation': 1, 'requires_byok': True}
    resume = MagicMock()
    _mock_lifecycle_conversation(monkeypatch)
    monkeypatch.setattr(lifecycle_service.jobs_db, 'create_or_get_finalization_intent', MagicMock(return_value=intent))
    monkeypatch.setattr(lifecycle_service, 'is_listen_finalization_dispatch_enabled', lambda: False)
    monkeypatch.setattr(lifecycle_service.jobs_db, 'resume_blocked_byok_job_for_live_session', resume)

    result = lifecycle_service.request_finalization('uid-1', 'conversation-1', has_byok_keys=False)

    assert result['route'] == 'blocked_byok'
    resume.assert_not_called()


def test_lifecycle_runtime_persists_the_fuzzer_decisions_fanout_key(monkeypatch):
    original_decider = lifecycle_service.decide_finalization
    decider = MagicMock(side_effect=original_decider)
    intent = {
        'job_id': 'job-1',
        'status': 'queued',
        'dispatch_generation': 1,
        'requires_byok': False,
        'fanout_key': 'conversation:conversation-1:finalization:1',
    }
    create_intent = MagicMock(return_value=intent)
    monkeypatch.setattr(lifecycle_service, 'decide_finalization', decider)
    monkeypatch.setattr(lifecycle_service.jobs_db, 'create_or_get_finalization_intent', create_intent)
    monkeypatch.setattr(lifecycle_service, 'is_listen_finalization_dispatch_enabled', lambda: False)

    result = lifecycle_service.request_finalization('uid-1', 'conversation-1', has_byok_keys=False)

    assert result['route'] == 'pusher'
    admission = create_intent.call_args.kwargs['finalization_admission'](
        {'id': 'conversation-1', 'status': ConversationStatus.in_progress.value}
    )
    decider.assert_called_once()
    assert admission['fanout_key'] == 'conversation:conversation-1:finalization:1'


@pytest.mark.parametrize(
    ('status', 'discarded'),
    [
        (ConversationStatus.failed.value, False),
        (ConversationStatus.in_progress.value, True),
    ],
    ids=['failed', 'discarded'],
)
def test_lifecycle_runtime_rejects_late_terminal_finalization(monkeypatch, status, discarded):
    observed = {}

    def create_intent(_uid, _conversation_id, **kwargs):
        admission = kwargs['finalization_admission'](
            {
                'id': 'conversation-1',
                'status': status,
                'discarded': discarded,
                'transcript_segments': [{'text': 'persisted'}],
            }
        )
        observed.update(admission)
        return {
            'job_id': None,
            'status': admission['reason'],
            'dispatch_generation': None,
            'requires_byok': False,
            'fanout_key': None,
        }

    monkeypatch.setattr(lifecycle_service.jobs_db, 'create_or_get_finalization_intent', create_intent)

    result = lifecycle_service.request_finalization('uid-1', 'conversation-1', has_byok_keys=False)

    assert result['route'] == 'noop'
    assert observed == {'accepted': False, 'terminal': True, 'reason': 'terminal', 'fanout_key': None}


class _Request:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


class _PusherWebSocket:
    def __init__(self):
        self.sent: list[bytes] = []
        self.client_state = pusher_router.WebSocketState.CONNECTED
        self.application_state = pusher_router.WebSocketState.CONNECTED

    async def send_bytes(self, payload: bytes) -> None:
        self.sent.append(payload)


class _PusherLifecycleWebSocket:
    def __init__(self, receive_bytes):
        self._receive_bytes = receive_bytes
        self.accepted = False
        self.client_state = pusher_router.WebSocketState.DISCONNECTED

    async def accept(self) -> None:
        self.accepted = True

    async def receive_bytes(self) -> bytes:
        return await self._receive_bytes()


class _PusherJourneyAttempt:
    outcomes: list[str] = []

    def __init__(self, journey: str) -> None:
        assert journey == 'pusher_session'

    def finish(self, outcome: str) -> None:
        self.outcomes.append(outcome)


def _patch_pusher_session_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(pusher_router, 'get_audio_bytes_webhook_seconds', lambda _uid: None)
    monkeypatch.setattr(pusher_router, 'is_audio_bytes_app_enabled', lambda _uid: False)
    monkeypatch.setattr(pusher_router.users_db, 'get_user_private_cloud_sync_enabled', lambda _uid: False)
    monkeypatch.setattr(pusher_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(pusher_router, 'PUSHER_ACTIVE_WS_CONNECTIONS', MagicMock())
    monkeypatch.setattr(pusher_router, 'JourneyAttempt', _PusherJourneyAttempt)
    monkeypatch.setattr(pusher_router, 'create_named_task', lambda coro, *, name: asyncio.create_task(coro, name=name))

    async def drain(tasks, *, cancel, **_kwargs):
        if not cancel:
            return
        tasks = list(tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    monkeypatch.setattr(pusher_router, 'drain_tasks', drain)


async def _inline_run_blocking(_executor, func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.mark.anyio
async def test_worker_retries_processing_failure_before_final_attempt(monkeypatch):
    monkeypatch.setattr(finalization_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda key: 'lock-token')
    monkeypatch.setattr(finalization_router, 'release_job_run_lock', lambda key, token: None)
    monkeypatch.setattr(
        jobs_db, 'claim_finalization_job', lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 1}
    )
    monkeypatch.setattr(
        jobs_db, 'get_finalization_job', lambda job_id: {'uid': 'uid-1', 'conversation_id': 'conversation-1'}
    )
    monkeypatch.setattr(
        finalization_router,
        'finalize_persisted_conversation',
        AsyncMock(side_effect=ConversationFinalizationError('processing_failed')),
    )
    retryable = MagicMock(return_value=True)
    monkeypatch.setattr(jobs_db, 'mark_finalization_retryable', retryable)
    monkeypatch.setattr(finalization_router, 'get_listen_finalization_tasks_max_attempts_for_worker', lambda: 3)

    response = await finalization_router.run_listen_finalization_job(
        _Request({'job_id': 'job-1', 'dispatch_generation': 1}), task_retry_count=0
    )

    assert response.status_code == 500
    assert json.loads(response.body) == {'status': 'retry'}
    retryable.assert_called_once_with('job-1', 1, 1, 'processing_failed')


@pytest.mark.anyio
async def test_worker_dead_letters_the_final_failed_attempt(monkeypatch):
    monkeypatch.setattr(finalization_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda key: 'lock-token')
    monkeypatch.setattr(finalization_router, 'release_job_run_lock', lambda key, token: None)
    monkeypatch.setattr(
        jobs_db, 'claim_finalization_job', lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 1}
    )
    monkeypatch.setattr(
        jobs_db, 'get_finalization_job', lambda job_id: {'uid': 'uid-1', 'conversation_id': 'conversation-1'}
    )
    monkeypatch.setattr(
        finalization_router,
        'finalize_persisted_conversation',
        AsyncMock(side_effect=ConversationFinalizationError('processing_failed')),
    )
    dead_letter = MagicMock(return_value=True)
    monkeypatch.setattr(finalization_router, 'final_attempt_failed', dead_letter)
    monkeypatch.setattr(finalization_router, 'get_listen_finalization_tasks_max_attempts_for_worker', lambda: 3)

    response = await finalization_router.run_listen_finalization_job(
        _Request({'job_id': 'job-1', 'dispatch_generation': 1}), task_retry_count=2
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'dead_letter'}
    dead_letter.assert_called_once_with('job-1', 1, 1, 3)


@pytest.mark.anyio
async def test_worker_completes_claimed_job(monkeypatch):
    monkeypatch.setattr(finalization_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda key: 'lock-token')
    monkeypatch.setattr(finalization_router, 'release_job_run_lock', lambda key, token: None)
    monkeypatch.setattr(
        jobs_db, 'claim_finalization_job', lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 1}
    )
    monkeypatch.setattr(
        jobs_db,
        'get_finalization_job',
        lambda job_id: {'uid': 'uid-1', 'conversation_id': 'conversation-1', 'created_at': 'accepted-at'},
    )
    monkeypatch.setattr(finalization_router, 'finalize_persisted_conversation', AsyncMock())
    completed = MagicMock(return_value=True)
    terminal = MagicMock()
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', completed)
    monkeypatch.setattr(finalization_router, 'record_capture_finalization_terminal', terminal)

    response = await finalization_router.run_listen_finalization_job(
        _Request({'job_id': 'job-1', 'dispatch_generation': 1}), task_retry_count=0
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'done'}
    completed.assert_called_once_with('job-1', 1, 1)
    terminal.assert_called_once_with('success', 'accepted-at')


@pytest.mark.anyio
async def test_worker_forwards_rest_force_processing_mode_from_the_durable_job(monkeypatch):
    monkeypatch.setattr(finalization_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda key: 'lock-token')
    monkeypatch.setattr(finalization_router, 'release_job_run_lock', lambda key, token: None)
    monkeypatch.setattr(
        jobs_db, 'claim_finalization_job', lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 1}
    )
    monkeypatch.setattr(
        jobs_db,
        'get_finalization_job',
        lambda job_id: {
            'uid': 'uid-1',
            'conversation_id': 'conversation-1',
            'force_process': True,
            'created_at': 'accepted-at',
        },
    )
    finalizer = AsyncMock()
    monkeypatch.setattr(finalization_router, 'finalize_persisted_conversation', finalizer)
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', MagicMock(return_value=True))
    monkeypatch.setattr(finalization_router, 'record_capture_finalization_terminal', MagicMock())

    response = await finalization_router.run_listen_finalization_job(
        _Request({'job_id': 'job-1', 'dispatch_generation': 1}), task_retry_count=0
    )

    assert response.status_code == 200
    finalizer.assert_awaited_once_with(
        'uid-1',
        'conversation-1',
        finalization_job_id='job-1',
        dispatch_generation=1,
        lease_epoch=1,
        force_process=True,
    )


@pytest.mark.anyio
async def test_worker_closes_a_fenced_finalization_without_fanout(monkeypatch):
    monkeypatch.setattr(finalization_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda key: 'lock-token')
    monkeypatch.setattr(finalization_router, 'release_job_run_lock', lambda key, token: None)
    monkeypatch.setattr(
        jobs_db, 'claim_finalization_job', lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 1}
    )
    monkeypatch.setattr(
        jobs_db,
        'get_finalization_job',
        lambda job_id: {'uid': 'uid-1', 'conversation_id': 'conversation-1', 'created_at': 'accepted-at'},
    )
    monkeypatch.setattr(
        finalization_router,
        'finalize_persisted_conversation',
        AsyncMock(return_value=ConversationFinalizationDisposition.fenced),
    )
    normal_completion = MagicMock()
    fenced_completion = MagicMock(return_value=True)
    retryable = MagicMock()
    dead_letter = MagicMock()
    terminal = MagicMock()
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', normal_completion)
    monkeypatch.setattr(jobs_db, 'mark_finalization_retryable', retryable)
    monkeypatch.setattr(finalization_router, 'final_attempt_failed', dead_letter)
    monkeypatch.setattr(finalization_router.lifecycle_service, 'complete_fenced_finalization', fenced_completion)
    monkeypatch.setattr(finalization_router, 'record_capture_finalization_terminal', terminal)

    response = await finalization_router.run_listen_finalization_job(
        _Request({'job_id': 'job-1', 'dispatch_generation': 1}), task_retry_count=0
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'done'}
    normal_completion.assert_not_called()
    fenced_completion.assert_called_once_with('job-1', 1, 1)
    retryable.assert_not_called()
    dead_letter.assert_not_called()
    terminal.assert_called_once_with('stale', 'accepted-at')


@pytest.mark.anyio
async def test_worker_requeues_an_unexpected_failure_after_claim(monkeypatch):
    monkeypatch.setattr(finalization_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda key: 'lock-token')
    monkeypatch.setattr(finalization_router, 'release_job_run_lock', lambda key, token: None)
    monkeypatch.setattr(
        jobs_db, 'claim_finalization_job', lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 9}
    )
    monkeypatch.setattr(
        jobs_db, 'get_finalization_job', lambda job_id: {'uid': 'uid-1', 'conversation_id': 'conversation-1'}
    )
    monkeypatch.setattr(
        finalization_router, 'finalize_persisted_conversation', AsyncMock(side_effect=RuntimeError('raw text'))
    )
    retryable = MagicMock(return_value=True)
    monkeypatch.setattr(jobs_db, 'mark_finalization_retryable', retryable)
    monkeypatch.setattr(finalization_router, 'get_listen_finalization_tasks_max_attempts_for_worker', lambda: 3)

    response = await finalization_router.run_listen_finalization_job(
        _Request({'job_id': 'job-1', 'dispatch_generation': 1}), task_retry_count=0
    )

    assert response.status_code == 500
    assert json.loads(response.body) == {'status': 'retry'}
    retryable.assert_called_once_with('job-1', 1, 9, 'worker_failed')


@pytest.mark.anyio
async def test_pusher_rejects_legacy_finalization_without_a_durable_job():
    websocket = _PusherWebSocket()

    await pusher_router._process_conversation_task('uid-1', 'conversation-1', 'en', websocket)

    frame_type = int.from_bytes(websocket.sent[0][:4], 'little')
    result = json.loads(websocket.sent[0][4:])
    assert frame_type == 201
    assert result == {'conversation_id': 'conversation-1', 'error': 'durable_job_required'}


@pytest.mark.parametrize(
    ('close_code', 'application_failed', 'outcome'),
    [
        (1000, False, 'success'),
        (1001, False, 'success'),
        (1006, False, 'cancelled'),
        (1011, False, 'failure'),
        (1000, True, 'failure'),
    ],
)
def test_pusher_session_outcome_keeps_normal_disconnects_out_of_failures(close_code, application_failed, outcome):
    assert pusher_router.pusher_session_outcome(close_code, application_failed=application_failed) == outcome


@pytest.mark.anyio
async def test_pusher_setup_cancellation_terminalizes_an_accepted_session(monkeypatch):
    _PusherJourneyAttempt.outcomes = []

    async def cancel_during_setup(*_args, **_kwargs):
        raise asyncio.CancelledError

    websocket = _PusherLifecycleWebSocket(receive_bytes=AsyncMock())
    monkeypatch.setattr(pusher_router, 'get_audio_bytes_webhook_seconds', lambda _uid: None)
    monkeypatch.setattr(pusher_router, 'run_blocking', cancel_during_setup)
    monkeypatch.setattr(pusher_router, 'JourneyAttempt', _PusherJourneyAttempt)

    with pytest.raises(asyncio.CancelledError):
        await pusher_router._websocket_util_trigger(websocket, 'uid-1')

    assert websocket.accepted is True
    assert _PusherJourneyAttempt.outcomes == ['cancelled']


@pytest.mark.anyio
async def test_pusher_background_task_crash_terminalizes_as_failure(monkeypatch):
    _PusherJourneyAttempt.outcomes = []
    _patch_pusher_session_dependencies(monkeypatch)
    websocket = _PusherLifecycleWebSocket(receive_bytes=AsyncMock())

    async def supervisor(**_kwargs):
        return SimpleNamespace(reason='crash', task_name='ws:uid-1:transcripts')

    monkeypatch.setattr(pusher_router, 'supervise_tasks', supervisor)

    await pusher_router._websocket_util_trigger(websocket, 'uid-1')

    assert websocket.accepted is True
    assert _PusherJourneyAttempt.outcomes == ['failure']


@pytest.mark.anyio
async def test_pusher_dead_peer_timeout_terminalizes_as_failure(monkeypatch):
    _PusherJourneyAttempt.outcomes = []
    _patch_pusher_session_dependencies(monkeypatch)

    async def timeout() -> bytes:
        raise asyncio.TimeoutError

    websocket = _PusherLifecycleWebSocket(receive_bytes=timeout)

    async def supervisor(*, receive_task, **_kwargs):
        await receive_task
        return SimpleNamespace(reason='disconnect', task_name='ws:uid-1:receive')

    monkeypatch.setattr(pusher_router, 'supervise_tasks', supervisor)

    await pusher_router._websocket_util_trigger(websocket, 'uid-1')

    assert websocket.accepted is True
    assert _PusherJourneyAttempt.outcomes == ['failure']


@pytest.mark.anyio
async def test_pusher_claims_the_durable_job_before_finalizing(monkeypatch):
    websocket = _PusherWebSocket()
    claim = MagicMock(return_value={'status': 'claimed', 'lease_epoch': 7, 'attempt_count': 1})
    completed = MagicMock(return_value=True)
    finalizer = AsyncMock()
    monkeypatch.setattr(pusher_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', claim)
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', completed)
    monkeypatch.setattr(pusher_router, 'finalize_persisted_conversation', finalizer)

    await pusher_router._process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    claim.assert_called_once_with(
        'job-1',
        3,
        allow_byok=False,
        expected_uid='uid-1',
        expected_conversation_id='conversation-1',
    )
    finalizer.assert_awaited_once_with(
        'uid-1',
        'conversation-1',
        'en',
        finalization_job_id='job-1',
        dispatch_generation=3,
        lease_epoch=7,
    )
    completed.assert_called_once_with('job-1', 3, 7)
    assert json.loads(websocket.sent[0][4:]) == {'conversation_id': 'conversation-1', 'success': True}


@pytest.mark.anyio
async def test_pusher_closes_a_fenced_finalization_without_fanout(monkeypatch):
    websocket = _PusherWebSocket()
    monkeypatch.setattr(pusher_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 7, 'attempt_count': 1},
    )
    monkeypatch.setattr(
        pusher_router,
        'finalize_persisted_conversation',
        AsyncMock(return_value=ConversationFinalizationDisposition.fenced),
    )
    normal_completion = MagicMock()
    fenced_completion = MagicMock(return_value=True)
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', normal_completion)
    monkeypatch.setattr(pusher_router.lifecycle_service, 'complete_fenced_finalization', fenced_completion)

    await pusher_router._process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    normal_completion.assert_not_called()
    fenced_completion.assert_called_once_with('job-1', 3, 7)
    assert json.loads(websocket.sent[0][4:]) == {'conversation_id': 'conversation-1', 'fenced': True}


@pytest.mark.anyio
async def test_pusher_replays_a_terminal_fenced_job_without_completed_signal(monkeypatch):
    websocket = _PusherWebSocket()
    finalizer = AsyncMock()
    monkeypatch.setattr(pusher_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db, 'claim_finalization_job', lambda *args, **kwargs: {'status': 'fenced', 'lease_epoch': None}
    )
    monkeypatch.setattr(pusher_router, 'finalize_persisted_conversation', finalizer)

    await pusher_router._process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    finalizer.assert_not_awaited()
    assert json.loads(websocket.sent[0][4:]) == {'conversation_id': 'conversation-1', 'fenced': True}


@pytest.mark.anyio
async def test_pusher_requeues_an_unexpected_failure_after_claim(monkeypatch):
    websocket = _PusherWebSocket()
    retryable = MagicMock(return_value=True)
    monkeypatch.setattr(pusher_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 4, 'attempt_count': 1},
    )
    monkeypatch.setattr(jobs_db, 'mark_finalization_retryable', retryable)
    monkeypatch.setattr(pusher_router, 'get_listen_finalization_tasks_max_attempts', lambda: 5)
    monkeypatch.setattr(
        pusher_router, 'finalize_persisted_conversation', AsyncMock(side_effect=RuntimeError('raw transcript'))
    )

    await pusher_router._process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    retryable.assert_called_once_with('job-1', 3, 4, 'worker_failed')
    assert json.loads(websocket.sent[0][4:]) == {
        'conversation_id': 'conversation-1',
        'error': 'processing_failed',
        'terminal': False,
    }


class _CloseAfterHandoffWebSocket:
    """One opcode-104 frame, then a clean remote close (#9995)."""

    def __init__(self, frame: bytes):
        self._frames = [frame]
        self.accepted = False
        self.sent: list[bytes] = []
        self.client_state = pusher_router.WebSocketState.DISCONNECTED
        self.application_state = pusher_router.WebSocketState.DISCONNECTED

    async def accept(self) -> None:
        self.accepted = True

    async def receive_bytes(self) -> bytes:
        if self._frames:
            return self._frames.pop(0)
        raise pusher_router.WebSocketDisconnect(1000)

    async def send_bytes(self, payload: bytes) -> None:
        self.sent.append(payload)


def _finalization_frame(conversation_id: str, job_id: str, dispatch_generation: int) -> bytes:
    payload = {
        'conversation_id': conversation_id,
        'language': 'en',
        'finalization_job_id': job_id,
        'dispatch_generation': dispatch_generation,
    }
    return struct.pack('<I', 104) + json.dumps(payload).encode('utf-8')


@pytest.mark.anyio
async def test_pusher_finalization_survives_session_close_after_handoff(monkeypatch):
    """Close-after-104: the claimed job must converge without a later live session.

    Regression for #9995 — session cleanup used to cancel the connection-scoped
    finalizer task; CancelledError bypassed retry/dead-letter handling and left
    the claimed job leased until a later session or lease expiry.
    """
    _PusherJourneyAttempt.outcomes = []
    _patch_pusher_session_dependencies(monkeypatch)

    claim = MagicMock(return_value={'status': 'claimed', 'lease_epoch': 7, 'attempt_count': 1})
    completed = MagicMock(return_value=True)
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', claim)
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', completed)

    session_torn_down = asyncio.Event()

    async def finalize(*_args, **_kwargs):
        # Simulate LLM finalization still running while the origin session
        # finishes its teardown, including the old cancel-everything drain.
        await asyncio.wait_for(session_torn_down.wait(), timeout=5)
        return ConversationFinalizationDisposition.completed

    monkeypatch.setattr(pusher_router, 'finalize_persisted_conversation', finalize)

    async def supervisor(*, receive_task, **_kwargs):
        await receive_task
        return SimpleNamespace(reason='disconnect', task_name='ws:uid-1:receive')

    monkeypatch.setattr(pusher_router, 'supervise_tasks', supervisor)

    websocket = _CloseAfterHandoffWebSocket(_finalization_frame('conversation-1', 'job-1', 3))
    await pusher_router._websocket_util_trigger(websocket, 'uid-1')

    detached = list(pusher_router._detached_finalization_tasks)
    assert len(detached) == 1, 'finalization must keep running after session cleanup'
    assert pusher_router.PUSHER_DETACHED_FINALIZATION_TASKS._value.get() == 1
    session_torn_down.set()
    await asyncio.wait_for(detached[0], timeout=5)

    claim.assert_called_once()
    completed.assert_called_once_with('job-1', 3, 7)
    assert pusher_router.PUSHER_DETACHED_FINALIZATION_TASKS._value.get() == 0
    # The origin socket is gone; the result frame is dropped, not raised.
    assert websocket.sent == []


@pytest.mark.anyio
async def test_pusher_cancelled_finalization_requeues_the_held_lease(monkeypatch):
    """Process shutdown mid-lease releases the job instead of stranding it leased."""
    websocket = _PusherWebSocket()
    retryable = MagicMock(return_value=True)
    claimed = asyncio.Event()
    monkeypatch.setattr(pusher_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 7, 'attempt_count': 1},
    )
    monkeypatch.setattr(jobs_db, 'mark_finalization_retryable', retryable)

    async def finalize(*_args, **_kwargs):
        claimed.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(pusher_router, 'finalize_persisted_conversation', finalize)

    task = asyncio.create_task(
        pusher_router._process_conversation_task(
            'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
        )
    )
    await asyncio.wait_for(claimed.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    retryable.assert_called_once_with('job-1', 3, 7, 'worker_shutdown')


@pytest.mark.anyio
async def test_pusher_dead_letters_a_job_that_exhausted_its_attempt_budget(monkeypatch):
    """Inline dispatch owns the attempt budget: no Cloud Tasks worker will ever exhaust it.

    Without this the conversation stays `processing` forever and every later
    listen session re-runs the same failing LLM finalization.
    """
    websocket = _PusherWebSocket()
    retryable = MagicMock(return_value=True)
    dead_letter = MagicMock(return_value=True)
    monkeypatch.setattr(pusher_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 4, 'attempt_count': 5},
    )
    monkeypatch.setattr(jobs_db, 'mark_finalization_retryable', retryable)
    monkeypatch.setattr(jobs_db, 'mark_finalization_dead_letter', dead_letter)
    monkeypatch.setattr(pusher_router, 'get_listen_finalization_tasks_max_attempts', lambda: 5)
    monkeypatch.setattr(
        pusher_router,
        'finalize_persisted_conversation',
        AsyncMock(side_effect=ConversationFinalizationError('processing_failed')),
    )

    await pusher_router._process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    dead_letter.assert_called_once_with('job-1', 3, 4, 5, firestore_client=None)
    retryable.assert_not_called()
    assert json.loads(websocket.sent[0][4:]) == {
        'conversation_id': 'conversation-1',
        'error': 'processing_failed',
        'terminal': True,
    }


@pytest.mark.anyio
async def test_pusher_lease_loss_never_terminalizes_a_newer_finalization_owner(monkeypatch):
    websocket = _PusherWebSocket()
    dead_letter = MagicMock(return_value=False)
    monkeypatch.setattr(pusher_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 4, 'attempt_count': 5},
    )
    monkeypatch.setattr(pusher_router, 'final_attempt_failed', dead_letter)
    monkeypatch.setattr(pusher_router, 'get_listen_finalization_tasks_max_attempts', lambda: 5)
    monkeypatch.setattr(
        pusher_router,
        'finalize_persisted_conversation',
        AsyncMock(side_effect=ConversationFinalizationError('processing_failed')),
    )

    await pusher_router._process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    dead_letter.assert_called_once_with('job-1', 3, 4, 5)
    assert json.loads(websocket.sent[0][4:]) == {
        'conversation_id': 'conversation-1',
        'error': 'processing_failed',
        'terminal': False,
    }


@pytest.mark.anyio
async def test_pusher_tells_the_live_session_a_dead_lettered_job_is_terminal(monkeypatch):
    websocket = _PusherWebSocket()
    monkeypatch.setattr(pusher_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'dead_letter', 'lease_epoch': None, 'attempt_count': 0},
    )

    await pusher_router._process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    assert json.loads(websocket.sent[0][4:]) == {
        'conversation_id': 'conversation-1',
        'error': 'job_dead_letter',
        'terminal': True,
    }


@pytest.mark.anyio
async def test_finalizer_never_logs_a_provider_exception_body(monkeypatch, caplog):
    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(id='conversation-1', status=ConversationStatus.processing, language='en')
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db, 'get_conversation', lambda *args: {'id': 'conversation-1'}
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(
        persisted_finalizer,
        'process_conversation',
        lambda *args: (_ for _ in ()).throw(RuntimeError('private transcript excerpt')),
    )

    with pytest.raises(ConversationFinalizationError):
        await persisted_finalizer.finalize_persisted_conversation(
            'uid-1',
            'conversation-1',
            finalization_job_id='job-1',
            dispatch_generation=1,
            lease_epoch=1,
        )

    assert 'private transcript excerpt' not in caplog.text


@pytest.mark.anyio
async def test_completed_conversation_replays_only_the_durable_fanout_boundary(monkeypatch):
    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(id='conversation-1', status=ConversationStatus.completed, language='en')
    integrations = AsyncMock(return_value=[])
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args: {'id': 'conversation-1', 'status': ConversationStatus.completed.value, 'discarded': False},
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    extracted = MagicMock()
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', extracted)
    monkeypatch.setattr(
        persisted_finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *args: {'status': 'claimed', 'fanout_key': 'conversation:conversation-1:finalization'},
    )
    completed = MagicMock(return_value=True)
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'complete_finalization_fanout', completed)
    monkeypatch.setattr(persisted_finalizer, 'trigger_external_integrations', integrations)

    disposition = await persisted_finalizer.finalize_persisted_conversation(
        'uid-1',
        'conversation-1',
        finalization_job_id='job-1',
        dispatch_generation=2,
        lease_epoch=3,
    )

    integrations.assert_awaited_once_with(
        'uid-1',
        conversation,
        idempotency_key='conversation:conversation-1:finalization',
        require_delivery=True,
    )
    extracted.assert_called_once_with('uid-1', conversation)
    assert disposition == ConversationFinalizationDisposition.completed
    completed.assert_called_once_with('job-1', 2, 3)


@pytest.mark.anyio
async def test_finalizer_fences_a_deleted_conversation_before_processing(monkeypatch):
    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    process = MagicMock()
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(persisted_finalizer.conversations_db, 'get_conversation', lambda *args: None)
    monkeypatch.setattr(persisted_finalizer, 'process_conversation', process)
    claim_fanout = MagicMock(
        return_value={'status': 'fenced', 'fanout_key': 'conversation:conversation-1:finalization'}
    )
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'claim_finalization_fanout', claim_fanout)

    disposition = await persisted_finalizer.finalize_persisted_conversation(
        'uid-1',
        'conversation-1',
        finalization_job_id='job-1',
        dispatch_generation=2,
        lease_epoch=3,
    )

    assert disposition == ConversationFinalizationDisposition.fenced
    process.assert_not_called()
    claim_fanout.assert_called_once_with('job-1', 2, 3)


@pytest.mark.anyio
async def test_deleted_conversation_after_delivered_fanout_replay_completes_job(monkeypatch):
    """A deletion after durable fanout acknowledgement cannot strand the lease."""
    monkeypatch.setattr(finalization_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda key: 'lock-token')
    monkeypatch.setattr(finalization_router, 'release_job_run_lock', lambda key, token: None)
    monkeypatch.setattr(
        jobs_db, 'claim_finalization_job', lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 3}
    )
    monkeypatch.setattr(
        jobs_db, 'get_finalization_job', lambda job_id: {'uid': 'uid-1', 'conversation_id': 'conversation-1'}
    )
    monkeypatch.setattr(persisted_finalizer.conversations_db, 'get_conversation', lambda *args: None)
    fanout = MagicMock(return_value={'status': 'completed', 'fanout_key': 'conversation:conversation-1:finalization'})
    integrations = AsyncMock()
    completed = MagicMock(return_value=True)
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'claim_finalization_fanout', fanout)
    monkeypatch.setattr(persisted_finalizer, 'trigger_external_integrations', integrations)
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', completed)

    response = await finalization_router.run_listen_finalization_job(
        _Request({'job_id': 'job-1', 'dispatch_generation': 2}), task_retry_count=0
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'done'}
    fanout.assert_called_once_with('job-1', 2, 3)
    integrations.assert_not_awaited()
    completed.assert_called_once_with('job-1', 2, 3)


@pytest.mark.anyio
async def test_finalizer_skips_fanout_when_atomic_claim_is_fenced(monkeypatch):
    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(id='conversation-1', status=ConversationStatus.processing, language='en')
    integrations = AsyncMock()
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args: {'id': 'conversation-1', 'status': ConversationStatus.processing.value, 'discarded': False},
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(persisted_finalizer, 'process_conversation', lambda *args, **kwargs: conversation)
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', MagicMock())
    claim_fanout = MagicMock(
        return_value={'status': 'fenced', 'fanout_key': 'conversation:conversation-1:finalization'}
    )
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'claim_finalization_fanout', claim_fanout)
    monkeypatch.setattr(persisted_finalizer, 'trigger_external_integrations', integrations)

    disposition = await persisted_finalizer.finalize_persisted_conversation(
        'uid-1',
        'conversation-1',
        finalization_job_id='job-1',
        dispatch_generation=2,
        lease_epoch=3,
    )

    assert disposition == ConversationFinalizationDisposition.fenced
    claim_fanout.assert_called_once_with('job-1', 2, 3)
    integrations.assert_not_awaited()


@pytest.mark.anyio
async def test_finalizer_retries_canonical_memory_extraction_before_fanout(monkeypatch):
    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(
        id='conversation-1', status=ConversationStatus.processing, language='en', discarded=False
    )
    process = MagicMock(return_value=conversation)
    extract = MagicMock(side_effect=RuntimeError('canonical write gate unavailable'))
    claim_fanout = MagicMock()
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args: {'id': 'conversation-1', 'status': ConversationStatus.processing.value, 'discarded': False},
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(persisted_finalizer, 'process_conversation', process)
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', extract)
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'claim_finalization_fanout', claim_fanout)

    with pytest.raises(ConversationFinalizationError):
        await persisted_finalizer.finalize_persisted_conversation(
            'uid-1',
            'conversation-1',
            finalization_job_id='job-1',
            dispatch_generation=2,
            lease_epoch=3,
        )

    assert process.call_args.kwargs['defer_memory_extraction'] is True
    extract.assert_called_once_with('uid-1', conversation)
    claim_fanout.assert_not_called()
