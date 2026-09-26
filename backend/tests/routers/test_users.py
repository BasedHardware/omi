import asyncio
import json
import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import users as users_router
from services.users import data_export


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _task_auth(retry_count=0):
    return users_router.AccountDeletionTaskAuthentication(retry_count=retry_count)


def test_delete_account_delegates_to_service():
    start_account_deletion = MagicMock(return_value={'status': 'ok', 'message': 'Account deletion started'})
    request = users_router.DeleteAccountRequest(reason='reason', reason_details='details')

    with patch.object(users_router, 'start_account_deletion', start_account_deletion):
        result = users_router.delete_account(request=request, uid='uid1')

    assert result == {'status': 'ok', 'message': 'Account deletion started'}
    start_account_deletion.assert_called_once_with('uid1', reason='reason', reason_details='details')


def test_delete_account_maps_unexpected_service_error_to_500():
    start_account_deletion = MagicMock(side_effect=Exception('boom'))
    with patch.object(users_router, 'start_account_deletion', start_account_deletion):
        with pytest.raises(HTTPException) as exc:
            users_router.delete_account(request=users_router.DeleteAccountRequest(), uid='uid1')

    assert exc.value.status_code == 500
    assert exc.value.detail == 'Could not delete account. Please try again.'


def test_invalid_geolocation_is_ignored_without_cache_access():
    cache_read = MagicMock()
    cache_write = MagicMock()

    with patch.object(users_router, 'get_cached_user_geolocation', cache_read), patch.object(
        users_router, 'cache_user_geolocation', cache_write
    ):
        result = users_router.set_user_geolocation(
            users_router.GeolocationInput(latitude=90.1, longitude=0), uid='uid1'
        )

    assert result == {'status': 'ok', 'message': 'Location ignored because its coordinates are invalid.'}
    cache_read.assert_not_called()
    cache_write.assert_not_called()


def test_location_context_consent_requires_disclosure_before_enabling():
    with pytest.raises(HTTPException) as exc:
        users_router.set_location_context_consent(
            users_router.LocationContextConsentUpdate(enabled=True, disclosure_accepted=False), uid='uid1'
        )

    assert exc.value.status_code == 422


def test_run_account_deletion_wipe_retries_failed_wipe(monkeypatch):
    calls = []

    async def run_blocking(_executor, fn, *args):
        calls.append((fn, args))
        if fn is users_router.resolve_deletion_wipe_job_id:
            return {'outcome': 'resolved', 'uid': 'uid1'}
        if fn is users_router.try_acquire_job_run_lock:
            return 'lock-token'
        if fn is users_router.claim_deletion_wipe_for_task:
            return 'claimed'
        if fn is users_router.background_wipe_user_data:
            return False
        if fn is users_router.release_job_run_lock:
            return None
        raise AssertionError(f'unexpected function {fn}')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)
    monkeypatch.setattr(users_router, 'get_account_deletion_tasks_max_attempts', lambda: 3)

    response = asyncio.run(
        users_router.run_account_deletion_wipe(_FakeRequest({'job_id': 'job-1'}), task_authentication=_task_auth())
    )

    assert response.status_code == 500
    assert json.loads(response.body) == {'status': 'retry'}
    assert calls == [
        (users_router.resolve_deletion_wipe_job_id, ('job-1',)),
        (users_router.try_acquire_job_run_lock, ('account-deletion:uid1',)),
        (users_router.claim_deletion_wipe_for_task, ('uid1',)),
        (users_router.background_wipe_user_data, ('uid1', 0, False)),
        (users_router.release_job_run_lock, ('account-deletion:uid1', 'lock-token')),
    ]


def test_run_account_deletion_wipe_consumes_final_failed_attempt(monkeypatch):
    background_args = []

    async def run_blocking(_executor, fn, *args):
        if fn is users_router.resolve_deletion_wipe_job_id:
            return {'outcome': 'resolved', 'uid': 'uid1'}
        if fn is users_router.try_acquire_job_run_lock:
            return 'lock-token'
        if fn is users_router.claim_deletion_wipe_for_task:
            return 'claimed'
        if fn is users_router.background_wipe_user_data:
            background_args.append(args)
            return False
        if fn is users_router.release_job_run_lock:
            return None
        raise AssertionError(f'unexpected function {fn}')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)
    monkeypatch.setattr(users_router, 'get_account_deletion_tasks_max_attempts', lambda: 2)

    response = asyncio.run(
        users_router.run_account_deletion_wipe(
            _FakeRequest({'job_id': 'job-1'}), task_authentication=_task_auth(retry_count=1)
        )
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'failed_final'}
    assert background_args == [('uid1', 1, True)]


def test_run_account_deletion_wipe_defers_when_locked(monkeypatch):
    release = MagicMock()

    async def run_blocking(_executor, fn, *args):
        if fn is users_router.resolve_deletion_wipe_job_id:
            return {'outcome': 'resolved', 'uid': 'uid1'}
        if fn is users_router.try_acquire_job_run_lock:
            return None
        if fn is users_router.release_job_run_lock:
            release(*args)
            return None
        raise AssertionError(f'unexpected function {fn}')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)

    response = asyncio.run(
        users_router.run_account_deletion_wipe(_FakeRequest({'job_id': 'job-1'}), task_authentication=_task_auth())
    )

    assert response.status_code == 409
    assert json.loads(response.body) == {'status': 'locked'}
    release.assert_not_called()


def test_run_account_deletion_wipe_drops_completed_job_without_mutation(monkeypatch):
    calls = []

    async def run_blocking(_executor, fn, *args):
        calls.append((fn, args))
        if fn is users_router.resolve_deletion_wipe_job_id:
            return {'outcome': 'completed', 'uid': None}
        raise AssertionError(f'unexpected function {fn}')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)

    response = asyncio.run(
        users_router.run_account_deletion_wipe(_FakeRequest({'job_id': 'job-1'}), task_authentication=_task_auth())
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'dropped', 'reason': 'completed'}
    assert calls == [(users_router.resolve_deletion_wipe_job_id, ('job-1',))]


@pytest.mark.parametrize('outcome', ['missing', 'ambiguous'])
def test_run_account_deletion_wipe_drops_unknown_or_ambiguous_job_without_mutation(monkeypatch, outcome):
    calls = []

    async def run_blocking(_executor, fn, *args):
        calls.append((fn, args))
        if fn is users_router.resolve_deletion_wipe_job_id:
            return {'outcome': outcome, 'uid': None}
        raise AssertionError(f'unexpected mutating function {fn}')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)

    response = asyncio.run(
        users_router.run_account_deletion_wipe(_FakeRequest({'job_id': 'job-1'}), task_authentication=_task_auth())
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'dropped', 'reason': outcome}
    assert calls == [(users_router.resolve_deletion_wipe_job_id, ('job-1',))]


def test_persisted_wipe_recovers_after_enqueue_crash_and_handler_runs_once(monkeypatch):
    """The durable marker bridges a lost enqueue acknowledgement without a duplicate wipe."""
    service_globals = users_router.start_account_deletion.__globals__
    state = {'status': None, 'job_id': None, 'enqueue_attempts': 0, 'wipe_runs': 0}

    def persist_intent(_uid):
        if state['job_id']:
            return {'wipe_job_id': state['job_id'], 'dispatch_claimed': False}
        state['status'] = 'deleting_auth'
        state['job_id'] = 'job-1'
        return {'wipe_job_id': state['job_id'], 'dispatch_claimed': True}

    def mark_started(_uid, job_id):
        assert job_id == state['job_id']
        state['status'] = 'pending'
        return True

    def mark_failed(_uid):
        state['status'] = 'failed'

    def enqueue_task(job_id):
        assert job_id == state['job_id']
        state['enqueue_attempts'] += 1
        if state['enqueue_attempts'] == 1:
            raise RuntimeError('lost create-task acknowledgement')

    users_db = types.SimpleNamespace(
        mark_user_deletion_wipe_intent=persist_intent,
        mark_user_deletion_wipe_started=mark_started,
        mark_user_deletion_wipe_failed=mark_failed,
        get_user_subscription=lambda _uid: None,
        get_pending_deletion_wipes=lambda limit=100: [
            {'uid': 'uid1', 'wipe_status': state['status'], 'wipe_job_id': state['job_id']}
        ],
        claim_deletion_wipe=lambda _uid: 'uid1',
    )
    monkeypatch.setitem(service_globals, 'users_db', users_db)
    monkeypatch.setitem(service_globals, 'auth', types.SimpleNamespace(delete_account=lambda _uid: None))
    monkeypatch.setitem(service_globals, 'assert_account_deletion_permitted', lambda _uid: None)
    monkeypatch.setitem(service_globals, 'is_account_deletion_dispatch_enabled', lambda: True)
    monkeypatch.setitem(service_globals, 'enqueue_account_deletion_wipe', enqueue_task)

    assert users_router.start_account_deletion('uid1')['status'] == 'ok'

    assert state == {'status': 'failed', 'job_id': 'job-1', 'enqueue_attempts': 1, 'wipe_runs': 0}

    reconcile = service_globals['reconcile_pending_deletion_wipes']
    assert reconcile() == {'requeued': 1, 'skipped': 0}
    assert state['enqueue_attempts'] == 2

    async def run_blocking(_executor, fn, *args):
        if fn is users_router.resolve_deletion_wipe_job_id:
            if state['status'] == 'completed':
                return {'outcome': 'completed', 'uid': None}
            return {'outcome': 'resolved', 'uid': 'uid1'}
        if fn is users_router.try_acquire_job_run_lock:
            return 'lock-token'
        if fn is users_router.claim_deletion_wipe_for_task:
            return 'claimed'
        if fn is users_router.background_wipe_user_data:
            state['wipe_runs'] += 1
            state['status'] = 'completed'
            return True
        if fn is users_router.release_job_run_lock:
            return None
        raise AssertionError(f'unexpected function {fn}')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)

    first = asyncio.run(
        users_router.run_account_deletion_wipe(_FakeRequest({'job_id': 'job-1'}), task_authentication=_task_auth())
    )
    duplicate = asyncio.run(
        users_router.run_account_deletion_wipe(
            _FakeRequest({'job_id': 'job-1'}), task_authentication=_task_auth(retry_count=1)
        )
    )

    assert json.loads(first.body) == {'status': 'done'}
    assert json.loads(duplicate.body) == {'status': 'dropped', 'reason': 'completed'}
    assert state['wipe_runs'] == 1


def test_run_account_deletion_wipe_drops_non_actionable_job(monkeypatch):
    async def run_blocking(_executor, fn, *args):
        if fn is users_router.resolve_deletion_wipe_job_id:
            return {'outcome': 'resolved', 'uid': 'uid1'}
        if fn is users_router.try_acquire_job_run_lock:
            return 'lock-token'
        if fn is users_router.claim_deletion_wipe_for_task:
            return 'not_actionable'
        if fn is users_router.release_job_run_lock:
            return None
        raise AssertionError(f'unexpected function {fn}')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)

    response = asyncio.run(
        users_router.run_account_deletion_wipe(_FakeRequest({'job_id': 'job-1'}), task_authentication=_task_auth())
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'dropped', 'reason': 'not_actionable'}


def test_run_account_deletion_wipe_preserves_lock_on_cancel(monkeypatch):
    released = []

    async def run_blocking(_executor, fn, *args):
        if fn is users_router.resolve_deletion_wipe_job_id:
            return {'outcome': 'resolved', 'uid': 'uid1'}
        if fn is users_router.try_acquire_job_run_lock:
            return 'lock-token'
        if fn is users_router.claim_deletion_wipe_for_task:
            return 'claimed'
        if fn is users_router.background_wipe_user_data:
            raise asyncio.CancelledError()
        if fn is users_router.release_job_run_lock:
            released.append(args)
            return None
        raise AssertionError(f'unexpected function {fn}')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)

    try:
        asyncio.run(
            users_router.run_account_deletion_wipe(_FakeRequest({'job_id': 'job-1'}), task_authentication=_task_auth())
        )
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError('expected cancellation to propagate')

    assert released == []


def test_export_all_user_data_keeps_streaming_headers(monkeypatch):
    iter_export = MagicMock(return_value=iter(['{"ok": true}\n']))
    monkeypatch.setattr(users_router, 'iter_user_data_export', iter_export)

    response = users_router.export_all_user_data(uid='uid1')

    assert response.media_type == 'application/json'
    assert response.headers['content-disposition'] == 'attachment; filename="omi-export.json"'
    iter_export.assert_called_once_with('uid1')

    async def _consume():
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk)
        return ''.join(parts)

    assert asyncio.run(_consume()) == '{"ok": true}\n'


def test_export_all_user_data_returns_500_before_streaming_headers_when_memory_preflight_fails(monkeypatch):
    def _failing_iter(_uid, *, include_archive=True):
        yield MagicMock(model_dump=MagicMock(return_value={'id': 'mem-ok'}))
        raise RuntimeError('canonical memory unavailable')

    monkeypatch.setattr(
        data_export,
        'MemoryService',
        MagicMock(return_value=MagicMock(iter_portability_export_memories=_failing_iter)),
    )
    app = FastAPI()
    app.include_router(users_router.router)
    app.dependency_overrides[users_router.auth.get_current_user_uid] = lambda: 'uid1'

    response = TestClient(app, raise_server_exceptions=False).get('/v1/users/export')

    assert response.status_code == 500
    assert 'content-disposition' not in response.headers


def test_task_assistant_prompt_contract_accepts_shipped_default_size_and_rejects_oversize():
    accepted = users_router.UpdateAssistantSettingsRequest(
        task={'analysis_prompt': 'x' * users_router.ASSISTANT_ANALYSIS_PROMPT_MAX_LENGTH}
    )

    assert len(accepted.task.analysis_prompt) == users_router.ASSISTANT_ANALYSIS_PROMPT_MAX_LENGTH
    with pytest.raises(ValueError):
        users_router.UpdateAssistantSettingsRequest(
            task={'analysis_prompt': 'x' * (users_router.ASSISTANT_ANALYSIS_PROMPT_MAX_LENGTH + 1)}
        )


def test_task_assistant_prompt_contract_counts_unicode_code_points():
    flag = '🇺🇸'
    prompt = flag * (users_router.ASSISTANT_ANALYSIS_PROMPT_MAX_LENGTH // len(flag) + 1)

    assert len(prompt) == users_router.ASSISTANT_ANALYSIS_PROMPT_MAX_LENGTH + 2
    with pytest.raises(ValueError):
        users_router.UpdateAssistantSettingsRequest(task={'analysis_prompt': prompt})


def test_update_person_name_missing_returns_404():
    # A well-formed PATCH for a nonexistent/stale person id must 404, not 500. update_person now
    # returns False for a missing person (instead of Firestore .update() raising NotFound).
    with patch.object(users_router, 'update_person', MagicMock(return_value=False)):
        with pytest.raises(HTTPException) as exc:
            users_router.update_person_name(person_id='missing', value='Alice', uid='uid1')

    assert exc.value.status_code == 404


def test_update_person_name_existing_returns_ok():
    update_person = MagicMock(return_value=True)
    with patch.object(users_router, 'update_person', update_person):
        result = users_router.update_person_name(person_id='p1', value='Alice', uid='uid1')

    assert result == {'status': 'ok'}
    update_person.assert_called_once_with('uid1', 'p1', 'Alice')


def _managed_allowance():
    from utils.subscription import TranscriptionAllowance

    return TranscriptionAllowance('managed', None, 'byok')


@pytest.fixture(autouse=True)
def _stub_transcription_allowance():
    """The subscription endpoint decorates every snapshot with the one allowance answer (S16).

    The resolver reads Firestore through its own bindings, which the per-test patches
    on `users_router.*` do not reach; these tests are about the snapshot itself, so the
    resolver is stubbed at the router seam. The one test that is about the decoration
    patches its own resolver inside the stub.
    """
    with patch.object(users_router, 'resolve_transcription_allowance', MagicMock(return_value=_managed_allowance())):
        yield


def test_byok_llm_only_subscription_meters_transcription_on_free_tier():
    # Snapshot split: a validated LLM BYOK key unlocks unlimited chat/insights,
    # but without a Deepgram header on the request the transcription/words
    # fields must stay metered on the free-tier limits (Omi still pays for STT),
    # not the 0/0 unlimited sentinel.
    basic_limits = users_router.PlanLimits(transcription_seconds=600, words_transcribed=8000)
    with patch.object(users_router.users_db, 'is_byok_active', MagicMock(return_value=True)), patch.object(
        users_router, 'request_has_llm_byok_key', MagicMock(return_value=True)
    ), patch.object(users_router, 'get_byok_key', MagicMock(return_value=None)), patch.object(
        users_router, 'get_basic_plan_limits', MagicMock(return_value=basic_limits)
    ), patch.object(
        users_router,
        'get_monthly_usage_for_subscription',
        MagicMock(return_value={'transcription_seconds': 120, 'words_transcribed': 500}),
    ):
        response = users_router.get_user_subscription_endpoint(uid='uid1')

    assert response.subscription.plan == users_router.PlanType.unlimited
    assert response.subscription.features == ['byok']
    # Chat/insights remain unlimited.
    assert response.subscription.limits.insights_gained is None
    assert response.insights_gained_used == 0
    assert response.insights_gained_limit == 0
    # Transcription/words are metered on the real free-tier usage.
    assert response.subscription.limits.transcription_seconds == 600
    assert response.transcription_seconds_used == 120
    assert response.transcription_seconds_limit == 600
    assert response.words_transcribed_limit == 8000
    assert response.words_transcribed_used == 500


def test_byok_llm_deepgram_subscription_returns_fully_unlimited_plan():
    # With a validated x-byok-deepgram header the whole snapshot is unlimited,
    # including transcription (None in the catalog, wire 0).
    with patch.object(users_router.users_db, 'is_byok_active', MagicMock(return_value=True)), patch.object(
        users_router, 'request_has_llm_byok_key', MagicMock(return_value=True)
    ), patch.object(
        users_router, 'get_byok_key', MagicMock(side_effect=lambda p: 'dg-key' if p == 'deepgram' else None)
    ):
        response = users_router.get_user_subscription_endpoint(uid='uid1')

    assert response.subscription.plan == users_router.PlanType.unlimited
    assert response.subscription.features == ['byok']
    assert response.subscription.limits.transcription_seconds is None
    assert response.subscription.limits.words_transcribed is None
    assert response.transcription_seconds_used == 0
    assert response.transcription_seconds_limit == 0
    assert response.words_transcribed_limit == 0


def test_marketplace_reviewer_subscription_endpoint_returns_unlimited_plan():
    # Same missing import on the reviewer branch (routers/users.py:1193).
    with patch.object(users_router.users_db, 'is_byok_active', MagicMock(return_value=False)), patch.dict(
        users_router.os.environ, {'MARKETPLACE_APP_REVIEWERS': 'reviewer-uid'}
    ):
        response = users_router.get_user_subscription_endpoint(uid='reviewer-uid')

    assert response.subscription.plan == users_router.PlanType.unlimited
    assert response.subscription.limits.words_transcribed is None


def test_subscription_endpoint_falls_back_to_basic_when_no_valid_subscription():
    # `get_default_basic_subscription` was called at routers/users.py:1220 without being
    # imported, so a user whose subscription is missing or expired got NameError -> 500
    # instead of the basic plan the branch exists to return.
    with patch.object(users_router.users_db, 'is_byok_active', MagicMock(return_value=False)), patch.object(
        users_router, 'get_user_subscription', MagicMock(return_value=None)
    ), patch.object(users_router, 'reconcile_basic_plan_with_stripe', MagicMock()), patch.object(
        users_router, 'get_user_valid_subscription', MagicMock(return_value=None)
    ), patch.object(
        users_router, 'get_monthly_usage_for_subscription', MagicMock(return_value={})
    ), patch.object(
        users_router, 'get_paid_plan_definitions', MagicMock(return_value=[])
    ), patch.object(
        users_router, 'should_hide_subscription_ui', MagicMock(return_value=False)
    ), patch.object(
        users_router,
        'get_phone_call_quota_snapshot',
        MagicMock(return_value=MagicMock(to_client_dict=lambda: {'has_access': False, 'is_paid': False})),
    ), patch.object(
        users_router,
        'get_chat_quota_snapshot',
        MagicMock(return_value={'used': 0.0, 'limit': None, 'unit': 'questions', 'allowed': True, 'reset_at': None}),
    ):
        response = users_router.get_user_subscription_endpoint(
            uid='uid-without-subscription', x_app_platform='ios', x_app_version='1.0.0'
        )

    assert response.subscription.plan == users_router.PlanType.basic


def test_usage_quota_endpoint_reads_customer_firestore_like_desktop_enforcement():
    # GET /v1/users/me/usage-quota (routers/users.py:1386) is the desktop app's own
    # quota display and called get_chat_quota_snapshot() with no firestore_client,
    # which defaults to the compute-local project. enforce_desktop_chat_quota() --
    # the function that actually gates POST /v2/chat/completions -- always forces
    # get_customer_firestore_client(). On a named dev/desktop bundle those are two
    # different Firestore projects, so this endpoint could report `allowed: true`
    # for the same uid that the chat endpoint 402s (#11199).
    sentinel_customer_client = object()
    snapshot_mock = MagicMock(
        return_value={
            'plan': users_router.PlanType.basic,
            'used': 1.0,
            'limit': 30.0,
            'unit': 'questions',
            'allowed': True,
            'reset_at': None,
        }
    )
    with patch.object(users_router.users_db, 'is_byok_active', MagicMock(return_value=False)), patch.object(
        users_router, 'get_customer_firestore_client', MagicMock(return_value=sentinel_customer_client)
    ), patch.object(users_router, 'get_chat_quota_snapshot', snapshot_mock):
        users_router.get_user_chat_usage_quota(uid='uid1', x_app_platform='desktop')

    snapshot_mock.assert_called_once_with(
        'uid1', platform='desktop', firestore_client=sentinel_customer_client, provision=False
    )


@pytest.mark.parametrize(
    'plan,expected_overage',
    [
        (users_router.PlanType.basic, False),
        (users_router.PlanType.plus, False),
        (users_router.PlanType.unlimited_v2, False),
        (users_router.PlanType.operator, True),
        (users_router.PlanType.unlimited, True),
        (users_router.PlanType.architect, True),
    ],
)
def test_usage_quota_endpoint_reports_catalog_exhaustion_policy(plan, expected_overage):
    # Desktop gates sends on this payload. Going past `limit` on an overage plan
    # accrues a charge rather than blocking (enforce_chat_quota returns without
    # raising), so `allowed: false` alone is not a block signal and the client
    # needs the catalog's own predicate to tell the two apart.
    snapshot_mock = MagicMock(
        return_value={
            'plan': plan,
            'used': 500.0,
            'limit': 500.0,
            'unit': 'questions',
            'allowed': False,
            'reset_at': 1_760_000_000,
        }
    )
    with patch.object(users_router.users_db, 'is_byok_active', MagicMock(return_value=False)), patch.object(
        users_router, 'get_customer_firestore_client', MagicMock(return_value=object())
    ), patch.object(users_router, 'get_chat_quota_snapshot', snapshot_mock):
        quota = users_router.get_user_chat_usage_quota(uid='uid1', x_app_platform='desktop')

    assert quota.is_overage_plan is expected_overage
    assert quota.allowed is False


def test_subscription_snapshot_carries_the_one_transcription_allowance_answer():
    """The startup snapshot exposes exactly what the listen socket will enforce (free tier S16),
    resolved with the app platform standing in for the listen `source`."""
    from utils.subscription import TranscriptionAllowance

    seen: list[tuple[str, object]] = []

    def resolver(uid: str, source=None, **already_read) -> TranscriptionAllowance:
        seen.append((uid, source))
        return TranscriptionAllowance('on_device', 0, 'plan_allowance_exhausted')

    with patch.object(users_router.users_db, 'is_byok_active', MagicMock(return_value=True)), patch.object(
        users_router, 'request_has_llm_byok_key', MagicMock(return_value=True)
    ), patch.object(
        users_router, 'get_byok_key', MagicMock(side_effect=lambda p: 'dg-key' if p == 'deepgram' else None)
    ), patch.object(
        users_router, 'resolve_transcription_allowance', resolver
    ):
        response = users_router.get_user_subscription_endpoint(uid='uid1', x_app_platform='desktop')

    assert seen == [('uid1', 'desktop')]
    assert response.transcription_allowance is not None
    assert response.transcription_allowance.model_dump() == {
        'mode': 'on_device',
        'remaining_seconds': 0,
        'reason': 'plan_allowance_exhausted',
    }


def test_subscription_snapshot_reuses_its_own_reads_for_the_allowance():
    """The ordinary branch reads the valid subscription and the monthly usage once; the resolver
    gets exactly those, so the snapshot and the allowance cannot come from different reads."""
    from utils.subscription import TranscriptionAllowance

    seen: list[dict] = []
    subscription = users_router.Subscription(
        plan=users_router.PlanType.plus, status=users_router.SubscriptionStatus.active
    )

    def resolver(uid: str, source=None, **already_read) -> TranscriptionAllowance:
        seen.append(already_read)
        return TranscriptionAllowance('managed', 5, 'plan_within_allowance')

    with patch.object(users_router.users_db, 'is_byok_active', MagicMock(return_value=False)), patch.object(
        users_router, 'get_user_subscription', MagicMock(return_value=subscription)
    ), patch.object(users_router, 'reconcile_basic_plan_with_stripe', MagicMock()), patch.object(
        users_router, 'get_user_valid_subscription', MagicMock(return_value=subscription)
    ), patch.object(
        users_router, 'get_monthly_usage_for_subscription', MagicMock(return_value={'transcription_seconds': 9})
    ), patch.object(
        users_router, 'get_paid_plan_definitions', MagicMock(return_value=[])
    ), patch.object(
        users_router, 'should_hide_subscription_ui', MagicMock(return_value=False)
    ), patch.object(
        users_router,
        'get_phone_call_quota_snapshot',
        MagicMock(return_value=MagicMock(to_client_dict=lambda: {'has_access': False, 'is_paid': False})),
    ), patch.object(
        users_router,
        'get_chat_quota_snapshot',
        MagicMock(return_value={'used': 0.0, 'limit': None, 'unit': 'questions', 'allowed': True, 'reset_at': None}),
    ), patch.object(
        users_router, 'resolve_transcription_allowance', resolver
    ), patch.object(
        # A legacy client is shown a remapped plan; the allowance must not see the remap.
        users_router,
        'wire_plan_for_client',
        MagicMock(return_value=users_router.PlanType.unlimited),
    ), patch.dict(
        users_router.os.environ, {'MARKETPLACE_APP_REVIEWERS': ''}
    ):
        response = users_router.get_user_subscription_endpoint(uid='uid1', x_app_platform='ios', x_app_version='1.0.0')

    assert [sorted(read) for read in seen] == [['byok_active', 'subscription', 'usage']]
    assert seen[0]['byok_active'] is False
    assert seen[0]['usage'] == {'transcription_seconds': 9}
    assert seen[0]['subscription'].plan is users_router.PlanType.plus  # not the client-facing remap
    assert response.subscription.plan is users_router.PlanType.unlimited  # the remap still ships to the client
    assert response.transcription_allowance.remaining_seconds == 5


def test_subscription_snapshot_survives_a_resolver_that_cannot_read_its_dependencies():
    """The real resolver never raises: a Firestore failure inside it becomes the free-path answer,
    and the snapshot the endpoint already built is still returned."""
    import utils.subscription as subscription_module

    with patch.object(users_router.users_db, 'is_byok_active', MagicMock(return_value=True)), patch.object(
        users_router, 'request_has_llm_byok_key', MagicMock(return_value=True)
    ), patch.object(
        users_router, 'get_byok_key', MagicMock(side_effect=lambda p: 'dg-key' if p == 'deepgram' else None)
    ), patch.object(
        users_router, 'resolve_transcription_allowance', subscription_module.resolve_transcription_allowance
    ), patch.object(
        subscription_module, 'is_trial_paywalled', MagicMock(side_effect=RuntimeError('firestore unavailable'))
    ):
        response = users_router.get_user_subscription_endpoint(uid='uid1', x_app_platform='desktop')

    assert response.subscription.features == ['byok']  # the snapshot itself is intact
    assert response.transcription_allowance.model_dump() == {
        'mode': 'on_device',
        'remaining_seconds': 0,
        'reason': 'allowance_unavailable',
    }


def test_an_expired_paid_subscription_is_downgraded_to_basic_by_the_real_lookup():
    """The real `get_user_valid_subscription` never returns None for an expired paid plan: it hands
    back a fresh basic subscription, so such a user gets basic's managed minutes, not nothing (S16)."""
    import importlib.util
    import time

    import utils.subscription as subscription_module

    # A private copy of database/users.py, not registered in sys.modules: other suites leave a
    # mock over the real module's `get_user_valid_subscription`, and this test exists to run
    # the genuine one.
    spec = importlib.util.spec_from_file_location('database.users_genuine_copy', users_router.users_db.__file__)
    assert spec is not None and spec.loader is not None
    genuine_users_db = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(genuine_users_db)
    assert genuine_users_db.get_user_valid_subscription.__module__ == 'database.users_genuine_copy'

    expired_plus = users_router.Subscription(
        plan=users_router.PlanType.plus,
        status=users_router.SubscriptionStatus.active,
        current_period_end=int(time.time()) - 86_400,
    )
    with patch.object(genuine_users_db, 'get_user_subscription', MagicMock(return_value=expired_plus)), patch.object(
        subscription_module.users_db, 'get_user_valid_subscription', genuine_users_db.get_user_valid_subscription
    ), patch.object(subscription_module.users_db, 'is_byok_active', MagicMock(return_value=False)), patch.object(
        subscription_module, 'is_trial_paywalled', MagicMock(return_value=False)
    ), patch.object(
        subscription_module, 'get_byok_key', MagicMock(return_value=None)
    ), patch.object(
        subscription_module, 'get_monthly_usage_for_subscription', MagicMock(return_value={'transcription_seconds': 0})
    ), patch.dict(
        users_router.os.environ, {'MARKETPLACE_APP_REVIEWERS': ''}
    ):
        assert genuine_users_db.get_user_valid_subscription('expired-plus-uid').plan is users_router.PlanType.basic
        allowance = subscription_module.resolve_transcription_allowance('expired-plus-uid')
        remaining = subscription_module.get_remaining_transcription_seconds('expired-plus-uid')

    assert (allowance.mode, allowance.remaining_seconds, allowance.reason) == (
        'managed',
        18_000,
        'plan_within_allowance',
    )
    assert remaining == 18_000


def test_llm_only_byok_snapshot_reads_monthly_usage_once_for_snapshot_and_allowance():
    """An enrolled BYOK request with an LLM key but no Deepgram key takes the early metered branch,
    which reads usage; the allowance must come from that same read, not a second one (S16)."""
    import utils.subscription as subscription_module

    usage_reads = MagicMock(return_value={'transcription_seconds': 17_000})
    with patch.object(users_router.users_db, 'is_byok_active', MagicMock(return_value=True)), patch.object(
        users_router, 'request_has_llm_byok_key', MagicMock(return_value=True)
    ), patch.object(
        users_router, 'get_byok_key', MagicMock(side_effect=lambda p: 'llm-key' if p == 'openai' else None)
    ), patch.object(
        users_router, 'get_monthly_usage_for_subscription', usage_reads
    ), patch.object(
        users_router, 'resolve_transcription_allowance', subscription_module.resolve_transcription_allowance
    ), patch.object(
        subscription_module, 'is_trial_paywalled', MagicMock(return_value=False)
    ), patch.object(
        subscription_module, 'get_byok_key', MagicMock(return_value=None)
    ), patch.object(
        subscription_module.users_db,
        'get_user_valid_subscription',
        MagicMock(
            return_value=users_router.Subscription(
                plan=users_router.PlanType.basic, status=users_router.SubscriptionStatus.active
            )
        ),
    ), patch.object(
        subscription_module, 'get_monthly_usage_for_subscription', usage_reads
    ), patch.dict(
        users_router.os.environ, {'MARKETPLACE_APP_REVIEWERS': ''}
    ):
        response = users_router.get_user_subscription_endpoint(uid='uid1', x_app_platform='ios')

    assert usage_reads.call_count == 1
    assert response.transcription_seconds_used == 17_000
    assert response.transcription_allowance.model_dump() == {
        'mode': 'managed',
        'remaining_seconds': 1_000,
        'reason': 'plan_within_allowance',
    }


def _route_dependency_names(path: str, method: str) -> list[str]:
    app = FastAPI()
    app.include_router(users_router.router)
    route = next(
        candidate
        for candidate in app.routes
        if getattr(candidate, 'path', None) == path and method in getattr(candidate, 'methods', set())
    )
    names: list[str] = []
    stack = [route.dependant]
    while stack:
        current = stack.pop()
        for dependency in getattr(current, 'dependencies', []) or []:
            names.append(getattr(dependency.call, '__name__', None))
            stack.append(dependency)
    return names


def test_get_memory_summary_rating_route_requires_auth():
    assert 'get_current_user_uid' in _route_dependency_names('/v1/users/analytics/memory_summary', 'GET')


def test_get_memory_summary_rating_returns_stored_score():
    with patch.object(users_router, 'get_conversation_summary_rating_score', return_value={'value': 1}) as fetch:
        result = users_router.get_memory_summary_rating(memory_id='mem-1')

    fetch.assert_called_once_with('mem-1')
    assert result == {'has_rating': True, 'rating': 1}


def test_get_memory_summary_rating_without_score():
    with patch.object(users_router, 'get_conversation_summary_rating_score', return_value=None):
        result = users_router.get_memory_summary_rating(memory_id='mem-1')

    assert result == {'has_rating': False}
