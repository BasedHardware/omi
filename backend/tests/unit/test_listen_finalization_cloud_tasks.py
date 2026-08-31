"""Cloud Tasks task-schema contract for durable listen finalization."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import conversation_finalization_jobs as jobs_db
from database.firestore_transaction_retry import FirestoreContentionExhausted
from models.conversation_enums import ConversationStatus
from routers.conversation_finalization import _parse_task_payload
import routers.conversation_finalization as finalization_router
import routers.pusher as pusher_router
import utils.pusher_finalization as pusher_finalization
import utils.pusher_protocol as pusher_protocol
from utils.conversations import lifecycle as lifecycle_service
from utils import app_integrations
from utils import cloud_tasks
from utils.conversations.finalizer import ConversationFinalizationDisposition, ConversationFinalizationError
import utils.conversations.finalizer as persisted_finalizer
import services.conversation_finalization as finalization_service


def _prod_backend_sync_runtime_env(monkeypatch):
    """Render the production backend-sync contract instead of duplicating it here."""
    backend_root = Path(__file__).resolve().parents[2]
    renderer = runpy.run_path(
        str(backend_root / 'scripts/render_backend_runtime_env.py'), run_name='render_backend_runtime_env_contract'
    )
    validator = runpy.run_path(
        str(backend_root / 'scripts/validate-backend-runtime-env.py'), run_name='validate_backend_runtime_env_contract'
    )
    assert validator['validate_runtime_env'](env='prod', check_workflows=True) == []

    manifest = renderer['_load_yaml'](renderer['DEFAULT_MANIFEST'])
    env_entries = manifest['environments']['prod']['cloud_run']['services']['backend-sync']['env']
    for entry in env_entries.values():
        if env_var := entry.get('env_var'):
            monkeypatch.setenv(env_var, f'{env_var.lower()}.contract.invalid')

    handler_path = next(
        route.path for route in finalization_router.router.routes if route.name == 'run_listen_finalization_job'
    )
    handler_url = f'https://backend-sync.contract.invalid{handler_path}'
    invoker_sa = 'finalization-contract@project.iam.gserviceaccount.com'
    monkeypatch.setenv('LISTEN_FINALIZATION_TASKS_HANDLER_URL', handler_url)
    monkeypatch.setenv('LISTEN_FINALIZATION_TASKS_INVOKER_SA', invoker_sa)

    rendered_env = dict(line.split('=', 1) for line in renderer['_render_env_vars'](env_entries).splitlines())
    return renderer, env_entries, rendered_env, handler_path


@pytest.fixture
def prod_backend_sync_runtime_env(monkeypatch):
    return _prod_backend_sync_runtime_env(monkeypatch)


@pytest.fixture(autouse=True)
def _isolate_keyframe_outbox(monkeypatch):
    """Keyframe lifecycle behavior is covered by its focused service tests."""

    async def disabled(*_args, **_kwargs):
        return SimpleNamespace(enabled=False, account_generation=None)

    monkeypatch.setattr(persisted_finalizer, "resolve_frame_request_authority", disabled)
    monkeypatch.setattr(
        persisted_finalizer,
        "ensure_conversation_keyframe_job",
        lambda *_args, **_kwargs: pytest.fail("dark rollout must create zero keyframe jobs"),
    )


def _finalization_task_client():
    app = FastAPI()
    app.include_router(finalization_router.router)
    return TestClient(app, raise_server_exceptions=False)


def _cloud_tasks_headers():
    return {
        'authorization': 'Bearer contract-token',
        'x-cloudtasks-taskretrycount': '2',
    }


def _opaque_finalization_task():
    return {'job_id': 'opaque-finalization-job', 'dispatch_generation': 7}


def test_prod_backend_sync_finalization_task_route_uses_rendered_oidc_contract(
    monkeypatch, prod_backend_sync_runtime_env
):
    _, _, rendered_env, handler_path = prod_backend_sync_runtime_env
    verified_claims = {
        'email': rendered_env['LISTEN_FINALIZATION_TASKS_INVOKER_SA'],
        'email_verified': True,
    }
    verify = MagicMock(return_value=verified_claims)
    monkeypatch.setattr(cloud_tasks.id_token, 'verify_oauth2_token', verify)
    # A lock contention is the narrow post-auth dependency seam: it proves the
    # real FastAPI route accepted the task without touching a durable job.
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda _key: None)

    with _finalization_task_client() as client:
        response = client.post(
            handler_path,
            json=_opaque_finalization_task(),
            headers=_cloud_tasks_headers(),
        )

    assert response.status_code == 409
    assert response.json() == {'status': 'locked'}
    assert verify.call_args.kwargs['audience'] == rendered_env['LISTEN_FINALIZATION_TASKS_HANDLER_URL']
    assert verify.call_args.args[0] == 'contract-token'


def test_prod_backend_sync_finalization_task_route_fails_closed_without_rendered_handler_binding(
    monkeypatch, prod_backend_sync_runtime_env
):
    renderer, env_entries, _, handler_path = prod_backend_sync_runtime_env
    monkeypatch.delenv('LISTEN_FINALIZATION_TASKS_HANDLER_URL')

    with pytest.raises(ValueError, match='LISTEN_FINALIZATION_TASKS_HANDLER_URL requires'):
        renderer['_render_env_vars'](env_entries)

    verify = MagicMock()
    monkeypatch.setattr(cloud_tasks.id_token, 'verify_oauth2_token', verify)
    with _finalization_task_client() as client:
        response = client.post(handler_path, json=_opaque_finalization_task(), headers=_cloud_tasks_headers())

    assert response.status_code == 403
    verify.assert_not_called()


def test_prod_backend_sync_finalization_task_route_rejects_wrong_audience(monkeypatch, prod_backend_sync_runtime_env):
    _, _, rendered_env, handler_path = prod_backend_sync_runtime_env
    expected_audience = rendered_env['LISTEN_FINALIZATION_TASKS_HANDLER_URL']

    def reject_wrong_audience(_token, _request, *, audience):
        if audience != expected_audience:
            raise ValueError('wrong audience')
        return {
            'email': rendered_env['LISTEN_FINALIZATION_TASKS_INVOKER_SA'],
            'email_verified': True,
        }

    monkeypatch.setattr(cloud_tasks.id_token, 'verify_oauth2_token', reject_wrong_audience)
    monkeypatch.setenv('LISTEN_FINALIZATION_TASKS_OIDC_AUDIENCE', 'https://wrong-audience.contract.invalid')
    with _finalization_task_client() as client:
        wrong_audience = client.post(handler_path, json=_opaque_finalization_task(), headers=_cloud_tasks_headers())

    assert wrong_audience.status_code == 403


def test_prod_backend_sync_finalization_task_route_rejects_untrusted_identity(
    monkeypatch, prod_backend_sync_runtime_env
):
    _, _, rendered_env, handler_path = prod_backend_sync_runtime_env
    monkeypatch.setattr(
        cloud_tasks.id_token,
        'verify_oauth2_token',
        MagicMock(return_value={'email': 'untrusted@project.iam.gserviceaccount.com', 'email_verified': True}),
    )
    with _finalization_task_client() as client:
        untrusted_identity = client.post(
            handler_path,
            json=_opaque_finalization_task(),
            headers=_cloud_tasks_headers(),
        )

    assert untrusted_identity.status_code == 403


def _mock_lifecycle_conversation(monkeypatch, *, status: str = 'in_progress'):
    monkeypatch.setattr(
        lifecycle_service.conversations_db,
        'get_conversation',
        lambda uid, conversation_id, **kwargs: {'id': conversation_id, 'status': status},
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
    client_accepted = MagicMock()
    _mock_lifecycle_conversation(monkeypatch)
    monkeypatch.setattr(lifecycle_service.jobs_db, 'create_or_get_finalization_intent', MagicMock(return_value=intent))
    monkeypatch.setattr(lifecycle_service, 'is_listen_finalization_dispatch_enabled', lambda: False)
    monkeypatch.setattr(lifecycle_service, 'record_journey_accepted', accepted)
    monkeypatch.setattr(lifecycle_service, 'record_client_journey_accepted', client_accepted)

    result = lifecycle_service.request_finalization(
        'uid-1', 'conversation-1', has_byok_keys=False, client_kind='mobile_android'
    )

    assert result['route'] == 'pusher'
    accepted.assert_called_once_with('capture_finalization')
    client_accepted.assert_called_once_with('conversation_finalization', 'mobile_android')


def test_durable_finalization_redelivery_does_not_count_as_new_traffic(monkeypatch):
    intent = {'job_id': 'job-1', 'status': 'queued', 'dispatch_generation': 2, 'requires_byok': False, 'created': False}
    accepted = MagicMock()
    client_accepted = MagicMock()
    _mock_lifecycle_conversation(monkeypatch)
    monkeypatch.setattr(lifecycle_service.jobs_db, 'create_or_get_finalization_intent', MagicMock(return_value=intent))
    monkeypatch.setattr(lifecycle_service, 'is_listen_finalization_dispatch_enabled', lambda: False)
    monkeypatch.setattr(lifecycle_service, 'record_journey_accepted', accepted)
    monkeypatch.setattr(lifecycle_service, 'record_client_journey_accepted', client_accepted)

    lifecycle_service.request_finalization('uid-1', 'conversation-1', has_byok_keys=False)

    accepted.assert_not_called()
    client_accepted.assert_not_called()


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
        lambda uid, conversation_id, **kwargs: {'finalization_job_id': 'job-1'},
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
        'meeting_treatment_eligible': False,
        'terminal_outcome': 'unknown',
        'fanout_status': 'unknown',
    }

    job['status'] = 'dead_letter'
    job['task_retry_count'] = 3
    job['meeting_treatment_eligible'] = True
    job['terminal_outcome'] = 'failure'
    job['fanout_status'] = 'fenced'
    assert lifecycle_service.get_finalization_status('uid-1', 'conversation-1') == {
        'job_id': 'job-1',
        'status': 'dead_letter',
        'terminal': True,
        'retryable': False,
        'attempt_count': 2,
        'task_retry_count': 3,
        'meeting_treatment_eligible': True,
        'terminal_outcome': 'failure',
        'fanout_status': 'fenced',
    }


def test_finalization_status_distinguishes_success_from_fenced_completion(monkeypatch):
    monkeypatch.setattr(
        lifecycle_service.conversations_db,
        'get_conversation',
        lambda uid, conversation_id, **kwargs: {'finalization_job_id': 'job-1'},
    )
    job = {
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'status': 'completed',
        'terminal_outcome': 'stale',
        'fanout_status': 'fenced',
    }
    monkeypatch.setattr(lifecycle_service.jobs_db, 'get_finalization_job', lambda job_id: job)

    status = lifecycle_service.get_finalization_status('uid-1', 'conversation-1')

    assert status is not None
    assert status['status'] == 'completed'
    assert status['terminal'] is True
    assert status['terminal_outcome'] == 'stale'
    assert status['fanout_status'] == 'fenced'


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
async def test_worker_acknowledges_stale_generation_without_cloud_task_retry(monkeypatch, caplog):
    # Reconciliation has already enqueued the newer generation. Retrying this
    # old named task would return stale_generation forever without claiming an
    # attempt or making progress.
    caplog.set_level(logging.INFO, logger=finalization_router.__name__)
    monkeypatch.setattr(finalization_router, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalization_router, 'try_acquire_job_run_lock', lambda key: 'lock-token')
    monkeypatch.setattr(finalization_router, 'release_job_run_lock', lambda key, token: None)
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', lambda *args, **kwargs: {'status': 'stale_generation'})

    response = await finalization_router.run_listen_finalization_job(
        _Request({'job_id': 'job-1', 'dispatch_generation': 1}), task_retry_count=2
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'dropped', 'reason': 'stale_generation'}
    assert any(
        record.levelno == logging.INFO
        and record.getMessage()
        == 'listen finalization stale generation task acknowledged job=job-1 dispatch_generation=1'
        for record in caplog.records
    )


def test_final_failed_attempt_records_client_failure_after_dead_letter(monkeypatch):
    job = {
        'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
        'client_platform': 'android',
    }
    client_terminal = MagicMock()
    monkeypatch.setattr(finalization_service.jobs_db, 'mark_finalization_dead_letter', MagicMock(return_value=True))
    monkeypatch.setattr(finalization_service.jobs_db, 'get_finalization_job', MagicMock(return_value=job))
    monkeypatch.setattr(finalization_service, 'record_capture_finalization_terminal', MagicMock())
    monkeypatch.setattr(finalization_service, 'record_conversation_finalization_client_terminal', client_terminal)

    assert finalization_service.final_attempt_failed('job-1', 1, 7, 3) is True

    client_terminal.assert_called_once_with('failure', job, issue_class='unknown')


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
    client_terminal = MagicMock()
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', completed)
    monkeypatch.setattr(finalization_router, 'record_capture_finalization_terminal', terminal)
    monkeypatch.setattr(finalization_router, 'record_conversation_finalization_client_terminal', client_terminal)

    response = await finalization_router.run_listen_finalization_job(
        _Request({'job_id': 'job-1', 'dispatch_generation': 1}), task_retry_count=0
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'done'}
    completed.assert_called_once_with('job-1', 1, 1)
    terminal.assert_called_once_with('success', 'accepted-at')
    client_terminal.assert_called_once_with(
        'success', {'uid': 'uid-1', 'conversation_id': 'conversation-1', 'created_at': 'accepted-at'}
    )


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
        final_attempt=False,
    )


@pytest.mark.anyio
async def test_worker_marks_the_terminal_attempt_so_delivery_cannot_strand_the_conversation(monkeypatch):
    """The last attempt dead-letters regardless, so the finalizer may drop a failing webhook."""
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
    finalizer = AsyncMock()
    monkeypatch.setattr(finalization_router, 'finalize_persisted_conversation', finalizer)
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', MagicMock(return_value=True))
    monkeypatch.setattr(finalization_router, 'record_capture_finalization_terminal', MagicMock())
    monkeypatch.setattr(finalization_router, 'get_listen_finalization_tasks_max_attempts_for_worker', lambda: 3)

    response = await finalization_router.run_listen_finalization_job(
        _Request({'job_id': 'job-1', 'dispatch_generation': 1}), task_retry_count=2
    )

    assert response.status_code == 200
    assert finalizer.await_args.kwargs['final_attempt'] is True


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

    await pusher_finalization.process_conversation_task('uid-1', 'conversation-1', 'en', websocket)

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
    assert pusher_protocol.pusher_session_outcome(close_code, application_failed=application_failed) == outcome


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
    monkeypatch.setattr(pusher_finalization, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(jobs_db, 'claim_finalization_job', claim)
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', completed)
    monkeypatch.setattr(pusher_finalization, 'finalize_persisted_conversation', finalizer)

    await pusher_finalization.process_conversation_task(
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
        final_attempt=False,
    )
    completed.assert_called_once_with('job-1', 3, 7)
    assert json.loads(websocket.sent[0][4:]) == {'conversation_id': 'conversation-1', 'success': True}


@pytest.mark.anyio
async def test_pusher_keeps_a_completed_job_terminal_when_source_result_delivery_fails(monkeypatch):
    """#9995: source disconnect after 104 cannot reclassify durable success."""
    websocket = _PusherWebSocket()

    async def closed_send(_payload: bytes) -> None:
        raise RuntimeError('Cannot call send once closed')

    websocket.send_bytes = closed_send
    completed = MagicMock(return_value=True)
    retryable = MagicMock()
    monkeypatch.setattr(pusher_finalization, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 7, 'attempt_count': 1},
    )
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', completed)
    monkeypatch.setattr(jobs_db, 'mark_finalization_retryable', retryable)
    monkeypatch.setattr(pusher_finalization, 'finalize_persisted_conversation', AsyncMock())

    await pusher_finalization.process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    completed.assert_called_once_with('job-1', 3, 7)
    retryable.assert_not_called()


@pytest.mark.anyio
async def test_pusher_closes_a_fenced_finalization_without_fanout(monkeypatch):
    websocket = _PusherWebSocket()
    monkeypatch.setattr(pusher_finalization, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 7, 'attempt_count': 1},
    )
    monkeypatch.setattr(
        pusher_finalization,
        'finalize_persisted_conversation',
        AsyncMock(return_value=ConversationFinalizationDisposition.fenced),
    )
    normal_completion = MagicMock()
    fenced_completion = MagicMock(return_value=True)
    monkeypatch.setattr(jobs_db, 'mark_finalization_completed', normal_completion)
    monkeypatch.setattr(pusher_finalization.lifecycle_service, 'complete_fenced_finalization', fenced_completion)

    await pusher_finalization.process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    normal_completion.assert_not_called()
    fenced_completion.assert_called_once_with('job-1', 3, 7)
    assert json.loads(websocket.sent[0][4:]) == {'conversation_id': 'conversation-1', 'fenced': True}


@pytest.mark.anyio
async def test_pusher_replays_a_terminal_fenced_job_without_completed_signal(monkeypatch):
    websocket = _PusherWebSocket()
    finalizer = AsyncMock()
    monkeypatch.setattr(pusher_finalization, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db, 'claim_finalization_job', lambda *args, **kwargs: {'status': 'fenced', 'lease_epoch': None}
    )
    monkeypatch.setattr(pusher_finalization, 'finalize_persisted_conversation', finalizer)

    await pusher_finalization.process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    finalizer.assert_not_awaited()
    assert json.loads(websocket.sent[0][4:]) == {'conversation_id': 'conversation-1', 'fenced': True}


@pytest.mark.anyio
async def test_pusher_requeues_an_unexpected_failure_after_claim(monkeypatch):
    websocket = _PusherWebSocket()
    retryable = MagicMock(return_value=True)
    monkeypatch.setattr(pusher_finalization, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 4, 'attempt_count': 1},
    )
    monkeypatch.setattr(jobs_db, 'mark_finalization_retryable', retryable)
    monkeypatch.setattr(pusher_finalization, 'get_listen_finalization_tasks_max_attempts', lambda: 5)
    monkeypatch.setattr(
        pusher_finalization, 'finalize_persisted_conversation', AsyncMock(side_effect=RuntimeError('raw transcript'))
    )

    await pusher_finalization.process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    retryable.assert_called_once_with('job-1', 3, 4, 'worker_failed')
    assert json.loads(websocket.sent[0][4:]) == {
        'conversation_id': 'conversation-1',
        'error': 'processing_failed',
        'terminal': False,
    }


@pytest.mark.anyio
async def test_pusher_dead_letters_a_job_that_exhausted_its_attempt_budget(monkeypatch):
    """Inline dispatch owns the attempt budget: no Cloud Tasks worker will ever exhaust it.

    Without this the conversation stays `processing` forever and every later
    listen session re-runs the same failing LLM finalization.
    """
    websocket = _PusherWebSocket()
    retryable = MagicMock(return_value=True)
    dead_letter = MagicMock(return_value=True)
    monkeypatch.setattr(pusher_finalization, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 4, 'attempt_count': 5},
    )
    monkeypatch.setattr(jobs_db, 'mark_finalization_retryable', retryable)
    monkeypatch.setattr(pusher_finalization, 'final_attempt_failed', dead_letter)
    monkeypatch.setattr(pusher_finalization, 'get_listen_finalization_tasks_max_attempts', lambda: 5)
    monkeypatch.setattr(
        pusher_finalization,
        'finalize_persisted_conversation',
        AsyncMock(side_effect=ConversationFinalizationError('processing_failed')),
    )

    await pusher_finalization.process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    dead_letter.assert_called_once_with('job-1', 3, 4, 5)
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
    monkeypatch.setattr(pusher_finalization, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'claimed', 'lease_epoch': 4, 'attempt_count': 5},
    )
    monkeypatch.setattr(pusher_finalization, 'final_attempt_failed', dead_letter)
    monkeypatch.setattr(pusher_finalization, 'get_listen_finalization_tasks_max_attempts', lambda: 5)
    monkeypatch.setattr(
        pusher_finalization,
        'finalize_persisted_conversation',
        AsyncMock(side_effect=ConversationFinalizationError('processing_failed')),
    )

    await pusher_finalization.process_conversation_task(
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
    monkeypatch.setattr(pusher_finalization, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'dead_letter', 'lease_epoch': None, 'attempt_count': 0},
    )

    await pusher_finalization.process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    assert json.loads(websocket.sent[0][4:]) == {
        'conversation_id': 'conversation-1',
        'error': 'job_dead_letter',
        'terminal': True,
    }


@pytest.mark.anyio
async def test_legacy_pusher_result_keeps_stale_generation_response_backward_compatible(monkeypatch):
    websocket = _PusherWebSocket()
    monkeypatch.setattr(pusher_finalization, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'stale_generation', 'lease_epoch': None, 'attempt_count': 0},
    )

    await pusher_finalization.process_conversation_task(
        'uid-1', 'conversation-1', 'en', websocket, finalization_job_id='job-1', dispatch_generation=3
    )

    assert json.loads(websocket.sent[0][4:]) == {
        'conversation_id': 'conversation-1',
        'error': 'job_stale_generation',
        'terminal': False,
    }


@pytest.mark.anyio
async def test_v2_pusher_result_includes_rejected_generation(monkeypatch):
    websocket = _PusherWebSocket()
    monkeypatch.setattr(pusher_finalization, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        jobs_db,
        'claim_finalization_job',
        lambda *args, **kwargs: {'status': 'stale_generation', 'lease_epoch': None, 'attempt_count': 0},
    )

    await pusher_finalization.process_conversation_task(
        'uid-1',
        'conversation-1',
        'en',
        websocket,
        finalization_job_id='job-1',
        dispatch_generation=3,
        finalization_result_protocol=2,
    )

    assert json.loads(websocket.sent[0][4:]) == {
        'conversation_id': 'conversation-1',
        'error': 'job_stale_generation',
        'dispatch_generation': 3,
        'terminal': False,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(('final_attempt', 'expect_completion'), [(False, False), (True, True)])
async def test_a_webhook_stuck_on_5xx_only_strands_the_conversation_while_retries_remain(
    monkeypatch, final_attempt, expect_completion
):
    """Runs the real finalizer over the real fanout with an app endpoint answering 530.

    A third-party endpoint that has been down for days (webhook health only
    auto-disables after 72h) failed every attempt of the durable job, so the
    conversation dead-lettered and its capture journey ended in `failure`. The
    terminal attempt dead-letters whatever the delivery does, so it drops the
    delivery and completes the conversation instead.
    """

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
    app = SimpleNamespace(
        id='app-1',
        uid='owner-1',
        enabled=True,
        external_integration=SimpleNamespace(webhook_url='https://app.test/hook'),
        triggers_on_conversation_creation=lambda: True,
    )
    response = MagicMock(status_code=530, text='origin unreachable')
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(app_integrations, 'run_blocking', inline_run_blocking)
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
    monkeypatch.setattr(
        persisted_finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *args: {'status': 'claimed', 'fanout_key': 'conversation:conversation-1:finalization'},
    )
    completed = MagicMock(return_value=True)
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'complete_finalization_fanout', completed)
    monkeypatch.setattr(app_integrations, 'get_available_apps', lambda uid: [app])
    monkeypatch.setattr(app_integrations, 'is_app_webhook_disabled', lambda app_id: False)
    monkeypatch.setattr(app_integrations, 'conversation_to_dict', lambda value: {})
    monkeypatch.setattr(app_integrations, 'safe_request_target', lambda url: (url, {'headers': {}, 'extensions': {}}))
    monkeypatch.setattr(app_integrations, 'get_webhook_circuit_breaker', lambda url: MagicMock())
    monkeypatch.setattr(app_integrations, 'get_webhook_client', lambda: client)
    monkeypatch.setattr(app_integrations, 'record_app_webhook_failure', MagicMock(return_value=0))
    monkeypatch.setattr(app_integrations, '_handle_webhook_health_action', MagicMock())

    async def finalize():
        return await persisted_finalizer.finalize_persisted_conversation(
            'uid-1',
            'conversation-1',
            finalization_job_id='job-1',
            dispatch_generation=2,
            lease_epoch=3,
            final_attempt=final_attempt,
        )

    if expect_completion:
        assert await finalize() == ConversationFinalizationDisposition.completed
        completed.assert_called_once()
    else:
        with pytest.raises(ConversationFinalizationError):
            await finalize()
        completed.assert_not_called()
    assert client.post.await_count == 1


@pytest.mark.anyio
async def test_finalizer_never_logs_a_provider_exception_body(monkeypatch, caplog):
    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(id='conversation-1', status=ConversationStatus.processing, language='en')
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db, 'get_conversation', lambda *args, **kwargs: {'id': 'conversation-1'}
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
@pytest.mark.parametrize(
    ('source', 'external_data', 'discarded', 'expected_intent_kwargs'),
    [
        ('omi', None, False, {'conversation_id': 'conversation-1', 'summary': 'Captured title'}),
        (
            'desktop',
            {'conversation_role': 'meeting'},
            False,
            {
                'conversation_id': 'conversation-1',
                'summary': 'Captured title',
                'is_desktop_meeting': True,
                'recommended_action_items': [],
            },
        ),
        ('desktop', {'conversation_role': 'ambient'}, False, None),
        (
            'desktop',
            {'conversation_role': 'meeting', 'conversation_finalization_reason': 'max_duration_rotation'},
            False,
            None,
        ),
        ('desktop', {'conversation_role': 'meeting'}, True, None),
    ],
)
async def test_completed_conversation_replays_only_the_durable_fanout_boundary(
    monkeypatch, source, external_data, discarded, expected_intent_kwargs
):
    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(
        id='conversation-1',
        status=ConversationStatus.completed,
        language='en',
        source=SimpleNamespace(value=source),
        external_data=external_data,
        discarded=discarded,
        started_at=datetime(2026, 8, 18, 12, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 18, 12, tzinfo=timezone.utc) + timedelta(minutes=10),
        transcript_segments=[SimpleNamespace(text='substantive exchange', start=0, end=60)],
        structured=SimpleNamespace(title='Captured title', overview='Captured overview'),
    )
    integrations = AsyncMock(return_value=[])
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
    capture_arrival = MagicMock()
    monkeypatch.setattr(persisted_finalizer, 'persist_capture_arrival_intent', capture_arrival)
    receipt_writer = MagicMock(return_value=None)
    monkeypatch.setattr(persisted_finalizer, 'record_and_persist_finalized_meeting_receipt', receipt_writer)

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
        last_delivery_attempt=False,
    )
    if discarded:
        extracted.assert_not_called()
    else:
        extracted.assert_called_once_with('uid-1', conversation)
    assert disposition == ConversationFinalizationDisposition.completed
    completed.assert_called_once_with('job-1', 2, 3)
    receipt_writer.assert_called_once_with('uid-1', conversation, finalization_job_id='job-1')
    if source != 'omi' or expected_intent_kwargs is None:
        capture_arrival.assert_not_called()
    else:
        capture_arrival.assert_called_once_with('uid-1', **expected_intent_kwargs)


@pytest.mark.anyio
async def test_async_finalizer_records_degraded_redis_location_fallback(monkeypatch):
    conversation = SimpleNamespace(id='conversation-1', status=ConversationStatus.completed, language='en')
    fallback = MagicMock()
    resolved = MagicMock()
    integrations = AsyncMock(return_value=[])
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args, **kwargs: {'id': 'conversation-1', 'status': ConversationStatus.completed.value},
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(
        persisted_finalizer,
        'get_cached_user_geolocation',
        lambda uid: {'latitude': 37.7749, 'longitude': -122.4194},
    )
    monkeypatch.setattr(persisted_finalizer, 'record_fallback', fallback)
    monkeypatch.setattr(persisted_finalizer, 'async_resolve_geolocation', AsyncMock(return_value=resolved))
    monkeypatch.setattr(
        persisted_finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *args: {'status': 'claimed', 'fanout_key': 'conversation:conversation-1:finalization'},
    )
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'complete_finalization_fanout', lambda *args: True)
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', MagicMock())
    monkeypatch.setattr(persisted_finalizer, 'trigger_external_integrations', integrations)

    await persisted_finalizer.finalize_persisted_conversation(
        'uid-1',
        'conversation-1',
        finalization_job_id='job-1',
        dispatch_generation=2,
        lease_epoch=3,
    )

    fallback.assert_called_once_with(
        component='conversation_finalization',
        from_mode='conversation_snapshot',
        to_mode='redis_user_cache',
        reason='other',
        outcome='degraded',
        log=persisted_finalizer.logger,
    )
    assert conversation.geolocation is resolved


@pytest.mark.anyio
async def test_finalizer_fences_a_deleted_conversation_before_processing(monkeypatch):
    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    process = MagicMock()
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(persisted_finalizer.conversations_db, 'get_conversation', lambda *args, **kwargs: None)
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
    monkeypatch.setattr(persisted_finalizer.conversations_db, 'get_conversation', lambda *args, **kwargs: None)
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
        lambda *args, **kwargs: {
            'id': 'conversation-1',
            'status': ConversationStatus.processing.value,
            'discarded': False,
        },
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
    claim_fanout = MagicMock(
        return_value={'status': 'claimed', 'fanout_key': 'conversation:conversation-1:finalization'}
    )
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args, **kwargs: {
            'id': 'conversation-1',
            'status': ConversationStatus.processing.value,
            'discarded': False,
        },
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

    assert process.call_args.kwargs['defer_derived_effects'] is True
    # The ownership fence (fanout claim) now runs before extract_memories;
    # a failing canonical extraction still raises for retry, and the fanout
    # lease is left for the next delivery to re-claim.
    claim_fanout.assert_called_once_with('job-1', 2, 3)
    extract.assert_called_once_with('uid-1', conversation)


@pytest.mark.anyio
async def test_finalizer_fences_before_memory_extraction_on_fanout_loss(monkeypatch):
    """#10468 r4: extract_memories must not run when the durable fanout claim
    loses to discard/terminal state.  The ownership fence must precede every
    canonical memory side effect."""

    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(
        id='conversation-1', status=ConversationStatus.processing, language='en', discarded=False
    )
    extract = MagicMock()
    claim_fanout = MagicMock(
        return_value={'status': 'fenced', 'fanout_key': 'conversation:conversation-1:finalization'}
    )
    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args, **kwargs: {
            'id': 'conversation-1',
            'status': ConversationStatus.processing.value,
            'discarded': False,
        },
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(persisted_finalizer, 'process_conversation', lambda *args, **kwargs: conversation)
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', extract)
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'claim_finalization_fanout', claim_fanout)

    disposition = await persisted_finalizer.finalize_persisted_conversation(
        'uid-1',
        'conversation-1',
        finalization_job_id='job-1',
        dispatch_generation=2,
        lease_epoch=3,
    )

    assert disposition == ConversationFinalizationDisposition.fenced
    claim_fanout.assert_called_once_with('job-1', 2, 3)
    extract.assert_not_called()


@pytest.mark.anyio
async def test_finalizer_fences_before_memory_extraction_on_persistence_loss(monkeypatch):
    """#10468 r4: when process_conversation reports that lifecycle persistence
    lost (discard/terminal), the finalizer must skip extract_memories entirely
    without even attempting the fanout claim."""

    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(
        id='conversation-1', status=ConversationStatus.processing, language='en', discarded=False
    )
    extract = MagicMock()
    claim_fanout = MagicMock()

    def losing_process(_uid, _lang, conv, **kwargs):
        observer = kwargs.get('persistence_observer')
        if observer:
            observer(False)
        return conv

    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args, **kwargs: {
            'id': 'conversation-1',
            'status': ConversationStatus.processing.value,
            'discarded': False,
        },
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(persisted_finalizer, 'process_conversation', losing_process)
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', extract)
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'claim_finalization_fanout', claim_fanout)

    disposition = await persisted_finalizer.finalize_persisted_conversation(
        'uid-1',
        'conversation-1',
        finalization_job_id='job-1',
        dispatch_generation=2,
        lease_epoch=3,
    )

    assert disposition == ConversationFinalizationDisposition.fenced
    extract.assert_not_called()
    claim_fanout.assert_not_called()


@pytest.mark.anyio
async def test_finalizer_emits_zero_derived_effects_when_claim_loses_after_persistence(monkeypatch):
    """#10468 r5: the durable finalizer must defer the WHOLE derived-effect
    bundle (calendar, usage/app, vector, action/goal, audio, webhook, memory)
    until after a transactionally validated lifecycle/finalization claim.
    Forcing a claim loss AFTER persistence succeeded must leave every
    dispatcher/callback with zero calls — a no-side-effect outcome."""

    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(
        id='conversation-1', status=ConversationStatus.processing, language='en', discarded=False
    )
    derived_runner = MagicMock()
    integrations = AsyncMock()

    def contract_faithful_process(_uid, _lang, conv, **kwargs):
        # Simulate the real defer_derived_effects contract: persistence wins,
        # the entire derived bundle is handed back as a deferred runner.
        observer = kwargs.get('persistence_observer')
        if observer:
            observer(True)
        effects_observer = kwargs.get('derived_effects_observer')
        if effects_observer:
            effects_observer(derived_runner)
        return conv

    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args, **kwargs: {
            'id': 'conversation-1',
            'status': ConversationStatus.processing.value,
            'discarded': False,
        },
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(persisted_finalizer, 'process_conversation', contract_faithful_process)
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
    # The derived-effect runner must never fire when the claim loses.
    derived_runner.assert_not_called()
    integrations.assert_not_awaited()


@pytest.mark.anyio
async def test_finalizer_runs_derived_effects_only_after_winning_claim(monkeypatch):
    """#10468 r5: when the claim WINS, the deferred derived-effect runner fires
    exactly once (after the claim, before integration fanout)."""

    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(
        id='conversation-1', status=ConversationStatus.processing, language='en', discarded=False
    )
    derived_runner = MagicMock()
    integrations = AsyncMock(return_value=[])
    complete = MagicMock(return_value=True)

    def contract_faithful_process(_uid, _lang, conv, **kwargs):
        observer = kwargs.get('persistence_observer')
        if observer:
            observer(True)
        effects_observer = kwargs.get('derived_effects_observer')
        if effects_observer:
            effects_observer(derived_runner)
        return conv

    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args, **kwargs: {
            'id': 'conversation-1',
            'status': ConversationStatus.processing.value,
            'discarded': False,
        },
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(persisted_finalizer, 'process_conversation', contract_faithful_process)
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', MagicMock())
    monkeypatch.setattr(
        persisted_finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *args: {'status': 'claimed', 'fanout_key': 'conversation:conversation-1:finalization'},
    )
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'complete_finalization_fanout', complete)
    monkeypatch.setattr(persisted_finalizer, 'trigger_external_integrations', integrations)

    disposition = await persisted_finalizer.finalize_persisted_conversation(
        'uid-1',
        'conversation-1',
        finalization_job_id='job-1',
        dispatch_generation=2,
        lease_epoch=3,
    )

    assert disposition == ConversationFinalizationDisposition.completed
    derived_runner.assert_called_once()
    integrations.assert_awaited_once()
    complete.assert_called_once_with('job-1', 2, 3)


@pytest.mark.anyio
async def test_finalizer_completes_when_an_app_permanently_rejects_the_delivery(monkeypatch):
    """A user's broken app webhook (expired token, deleted target) answers every
    retry identically, so it must not strand the conversation in `processing`
    until the finalization job dead-letters. The real fanout runs here."""

    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(
        id='conversation-1',
        status=ConversationStatus.processing,
        language='en',
        discarded=False,
        is_locked=False,
        source=None,
    )
    complete = MagicMock(return_value=True)

    def contract_faithful_process(_uid, _lang, conv, **kwargs):
        if observer := kwargs.get('persistence_observer'):
            observer(True)
        if effects_observer := kwargs.get('derived_effects_observer'):
            effects_observer(MagicMock())
        return conv

    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args, **kwargs: {
            'id': 'conversation-1',
            'status': ConversationStatus.processing.value,
            'discarded': False,
        },
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(persisted_finalizer, 'process_conversation', contract_faithful_process)
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', MagicMock())
    monkeypatch.setattr(
        persisted_finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *args: {'status': 'claimed', 'fanout_key': 'conversation:conversation-1:finalization'},
    )
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'complete_finalization_fanout', complete)

    app = MagicMock()
    app.id = 'omi-google-drive-integration'
    app.enabled = True
    app.uid = None
    app.external_integration.webhook_url = 'https://app.test/hook'
    app.triggers_on_conversation_creation.return_value = True
    webhook_client = AsyncMock()
    webhook_client.post = AsyncMock(return_value=MagicMock(status_code=401, text='re-authenticate'))
    pinned_url = 'https://8.8.8.8/hook?uid=uid-1'
    safe_target = MagicMock(
        return_value=(
            pinned_url,
            {'headers': {'Host': 'app.test'}, 'extensions': {'sni_hostname': 'app.test'}},
        )
    )
    monkeypatch.setattr(app_integrations, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(app_integrations, 'get_available_apps', lambda uid: [app])
    monkeypatch.setattr(app_integrations, 'conversation_to_dict', lambda conv: {'id': conv.id})
    monkeypatch.setattr(app_integrations, 'get_webhook_client', lambda: webhook_client)
    monkeypatch.setattr(app_integrations, 'is_app_webhook_disabled', lambda app_id: False)
    monkeypatch.setattr(app_integrations, 'safe_request_target', safe_target)
    record_failure = MagicMock(return_value=0)
    monkeypatch.setattr(app_integrations, 'record_app_webhook_failure', record_failure)
    monkeypatch.setattr(app_integrations, '_handle_webhook_health_action', MagicMock())

    disposition = await persisted_finalizer.finalize_persisted_conversation(
        'uid-1',
        'conversation-1',
        finalization_job_id='job-1',
        dispatch_generation=2,
        lease_epoch=3,
    )

    assert disposition == ConversationFinalizationDisposition.completed
    complete.assert_called_once_with('job-1', 2, 3)
    safe_target.assert_called_once_with('https://app.test/hook?uid=uid-1')
    webhook_client.post.assert_awaited_once_with(
        pinned_url,
        json={'id': 'conversation-1'},
        headers={'Host': 'app.test', 'X-Omi-Idempotency-Key': 'conversation:conversation-1:finalization'},
        extensions={'sni_hostname': 'app.test'},
        follow_redirects=False,
    )
    # The failure is still owned by webhook health, which disables the app after 72h.
    record_failure.assert_called_once_with('omi-google-drive-integration', 401, 'HTTP 401')
