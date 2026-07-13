"""Cloud Tasks task-schema contract for durable listen finalization."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database import conversation_finalization_jobs as jobs_db
from routers.conversation_finalization import _parse_task_payload
import routers.conversation_finalization as finalization_router
import routers.pusher as pusher_router
from services import conversation_finalization as finalization_service
from utils import cloud_tasks
from utils.conversations.finalizer import ConversationFinalizationError


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
    monkeypatch.setattr(
        finalization_service.jobs_db, 'create_or_get_finalization_intent', MagicMock(return_value=intent)
    )
    monkeypatch.setattr(finalization_service, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(finalization_service, 'enqueue_listen_finalization_job', enqueue)

    result = finalization_service.prepare_listen_finalization('uid-1', 'conversation-1', has_byok_keys=False)

    assert result['route'] == 'cloud_tasks'
    enqueue.assert_called_once_with('job-1', 2)


def test_enqueue_failure_leaves_job_queued_for_reconciler(monkeypatch):
    intent = {'job_id': 'job-1', 'status': 'queued', 'dispatch_generation': 2, 'requires_byok': False}
    fallback = MagicMock()
    monkeypatch.setattr(
        finalization_service.jobs_db, 'create_or_get_finalization_intent', MagicMock(return_value=intent)
    )
    monkeypatch.setattr(finalization_service, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(
        finalization_service, 'enqueue_listen_finalization_job', MagicMock(side_effect=RuntimeError('offline'))
    )
    monkeypatch.setattr(finalization_service, 'record_fallback', fallback)

    result = finalization_service.prepare_listen_finalization('uid-1', 'conversation-1', has_byok_keys=False)

    assert result['route'] == 'queued'
    fallback.assert_called_once()
    assert fallback.call_args.kwargs['reason'] == 'enqueue_failed'


def test_byok_never_dispatches_to_platform_worker(monkeypatch):
    intent = {'job_id': 'job-1', 'status': 'blocked_byok', 'dispatch_generation': 1, 'requires_byok': True}
    enqueue = MagicMock()
    monkeypatch.setattr(
        finalization_service.jobs_db, 'create_or_get_finalization_intent', MagicMock(return_value=intent)
    )
    monkeypatch.setattr(finalization_service, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(finalization_service, 'enqueue_listen_finalization_job', enqueue)

    result = finalization_service.prepare_listen_finalization('uid-1', 'conversation-1', has_byok_keys=True)

    assert result['route'] == 'blocked_byok'
    enqueue.assert_not_called()


def test_byok_job_without_current_keys_remains_explicitly_blocked(monkeypatch):
    intent = {'job_id': 'job-1', 'status': 'blocked_byok', 'dispatch_generation': 1, 'requires_byok': True}
    resume = MagicMock()
    monkeypatch.setattr(
        finalization_service.jobs_db, 'create_or_get_finalization_intent', MagicMock(return_value=intent)
    )
    monkeypatch.setattr(finalization_service, 'is_listen_finalization_dispatch_enabled', lambda: False)
    monkeypatch.setattr(finalization_service.jobs_db, 'resume_blocked_byok_job_for_live_session', resume)

    result = finalization_service.prepare_listen_finalization('uid-1', 'conversation-1', has_byok_keys=False)

    assert result['route'] == 'blocked_byok'
    resume.assert_not_called()


class _Request:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


class _PusherWebSocket:
    def __init__(self):
        self.sent: list[bytes] = []

    async def send_bytes(self, payload: bytes) -> None:
        self.sent.append(payload)


async def _inline_run_blocking(_executor, func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.mark.anyio
async def test_worker_retries_processing_failure_before_final_attempt(monkeypatch):
    monkeypatch.setattr(finalization_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda key: 'lock-token')
    monkeypatch.setattr(finalization_router, 'release_job_run_lock', lambda key, token: None)
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', lambda *args, **kwargs: 'claimed')
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
    retryable.assert_called_once_with('job-1', 1, 'processing_failed')


@pytest.mark.anyio
async def test_worker_dead_letters_the_final_failed_attempt(monkeypatch):
    monkeypatch.setattr(finalization_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda key: 'lock-token')
    monkeypatch.setattr(finalization_router, 'release_job_run_lock', lambda key, token: None)
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', lambda *args, **kwargs: 'claimed')
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
    dead_letter.assert_called_once_with('job-1', 1, 3)


@pytest.mark.anyio
async def test_worker_completes_claimed_job(monkeypatch):
    monkeypatch.setattr(finalization_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda key: 'lock-token')
    monkeypatch.setattr(finalization_router, 'release_job_run_lock', lambda key, token: None)
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', lambda *args, **kwargs: 'claimed')
    monkeypatch.setattr(
        jobs_db, 'get_finalization_job', lambda job_id: {'uid': 'uid-1', 'conversation_id': 'conversation-1'}
    )
    monkeypatch.setattr(finalization_router, 'finalize_persisted_conversation', AsyncMock())
    completed = MagicMock(return_value=True)
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', completed)

    response = await finalization_router.run_listen_finalization_job(
        _Request({'job_id': 'job-1', 'dispatch_generation': 1}), task_retry_count=0
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'done'}
    completed.assert_called_once_with('job-1', 1)


@pytest.mark.anyio
async def test_pusher_rejects_legacy_finalization_without_a_durable_job():
    websocket = _PusherWebSocket()

    await pusher_router._process_conversation_task('uid-1', 'conversation-1', 'en', websocket)

    frame_type = int.from_bytes(websocket.sent[0][:4], 'little')
    result = json.loads(websocket.sent[0][4:])
    assert frame_type == 201
    assert result == {'conversation_id': 'conversation-1', 'error': 'durable_job_required'}


@pytest.mark.anyio
async def test_pusher_claims_the_durable_job_before_finalizing(monkeypatch):
    websocket = _PusherWebSocket()
    claim = MagicMock(return_value='claimed')
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
    finalizer.assert_awaited_once_with('uid-1', 'conversation-1', 'en')
    completed.assert_called_once_with('job-1', 3)
    assert json.loads(websocket.sent[0][4:]) == {'conversation_id': 'conversation-1', 'success': True}
