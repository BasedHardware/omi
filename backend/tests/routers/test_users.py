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


def _task_auth(retry_count=0, audience='account_deletion'):
    return users_router.AccountDeletionTaskAuthentication(retry_count=retry_count, audience=audience)


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


def test_run_account_deletion_wipe_accepts_legacy_sync_audience_only_for_legacy_uid(monkeypatch):
    calls = []

    async def run_blocking(_executor, fn, *args):
        calls.append((fn, args))
        if fn is users_router.resolve_legacy_deletion_wipe_uid:
            return {'outcome': 'missing', 'uid': None}
        raise AssertionError(f'unexpected mutating function {fn}')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)

    response = asyncio.run(
        users_router.run_account_deletion_wipe(
            _FakeRequest({'uid': 'legacy-uid'}), task_authentication=_task_auth(audience='legacy_sync')
        )
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'dropped', 'reason': 'missing'}
    assert calls == [(users_router.resolve_legacy_deletion_wipe_uid, ('legacy-uid',))]


def test_run_account_deletion_wipe_drops_job_id_with_legacy_sync_audience_without_mutation(monkeypatch):
    async def run_blocking(*_args):
        raise AssertionError('legacy sync audience must not resolve or mutate a job-ID payload')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)

    response = asyncio.run(
        users_router.run_account_deletion_wipe(
            _FakeRequest({'job_id': 'job-1'}), task_authentication=_task_auth(audience='legacy_sync')
        )
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'dropped', 'reason': 'legacy_audience_for_job_id'}


def test_run_account_deletion_wipe_drops_legacy_uid_with_account_deletion_audience_without_mutation(monkeypatch):
    async def run_blocking(*_args):
        raise AssertionError('account_deletion audience must not resolve or mutate a legacy uid payload')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)

    response = asyncio.run(
        users_router.run_account_deletion_wipe(
            _FakeRequest({'uid': 'legacy-uid'}), task_authentication=_task_auth(audience='account_deletion')
        )
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'dropped', 'reason': 'legacy_uid_requires_legacy_audience'}


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
        MagicMock(return_value=MagicMock(iter_export_memories=_failing_iter)),
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
