import asyncio
import json
import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from routers import users as users_router


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
        (users_router.background_wipe_user_data, ('uid1',)),
        (users_router.release_job_run_lock, ('account-deletion:uid1', 'lock-token')),
    ]


def test_run_account_deletion_wipe_consumes_final_failed_attempt(monkeypatch):
    async def run_blocking(_executor, fn, *args):
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
    monkeypatch.setattr(users_router, 'get_account_deletion_tasks_max_attempts', lambda: 2)

    response = asyncio.run(
        users_router.run_account_deletion_wipe(
            _FakeRequest({'job_id': 'job-1'}), task_authentication=_task_auth(retry_count=1)
        )
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'failed_final'}


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


def test_export_all_user_data_keeps_streaming_headers():
    users_router.iter_user_data_export = MagicMock(return_value=iter(['{"ok": true}\n']))

    response = users_router.export_all_user_data(uid='uid1')

    assert response.media_type == 'application/json'
    assert response.headers['content-disposition'] == 'attachment; filename="omi-export.json"'
    users_router.iter_user_data_export.assert_called_once_with('uid1')

    async def _consume():
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk)
        return ''.join(parts)

    assert asyncio.run(_consume()) == '{"ok": true}\n'


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
