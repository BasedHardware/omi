import asyncio
import json
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

    response = asyncio.run(users_router.run_account_deletion_wipe(_FakeRequest({'uid': 'uid1'}), task_retry_count=0))

    assert response.status_code == 500
    assert json.loads(response.body) == {'status': 'retry'}
    assert calls == [
        (users_router.try_acquire_job_run_lock, ('account-deletion:uid1',)),
        (users_router.claim_deletion_wipe_for_task, ('uid1',)),
        (users_router.background_wipe_user_data, ('uid1',)),
        (users_router.release_job_run_lock, ('account-deletion:uid1', 'lock-token')),
    ]


def test_run_account_deletion_wipe_consumes_final_failed_attempt(monkeypatch):
    async def run_blocking(_executor, fn, *args):
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

    response = asyncio.run(users_router.run_account_deletion_wipe(_FakeRequest({'uid': 'uid1'}), task_retry_count=1))

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'failed_final'}


def test_run_account_deletion_wipe_defers_when_locked(monkeypatch):
    release = MagicMock()

    async def run_blocking(_executor, fn, *args):
        if fn is users_router.try_acquire_job_run_lock:
            return None
        if fn is users_router.release_job_run_lock:
            release(*args)
            return None
        raise AssertionError(f'unexpected function {fn}')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)

    response = asyncio.run(users_router.run_account_deletion_wipe(_FakeRequest({'uid': 'uid1'}), task_retry_count=0))

    assert response.status_code == 409
    assert json.loads(response.body) == {'status': 'locked'}
    release.assert_not_called()


def test_run_account_deletion_wipe_acks_completed_job(monkeypatch):
    async def run_blocking(_executor, fn, *args):
        if fn is users_router.try_acquire_job_run_lock:
            return 'lock-token'
        if fn is users_router.claim_deletion_wipe_for_task:
            return 'completed'
        if fn is users_router.release_job_run_lock:
            return None
        raise AssertionError(f'unexpected function {fn}')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)

    response = asyncio.run(users_router.run_account_deletion_wipe(_FakeRequest({'uid': 'uid1'}), task_retry_count=0))

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'acked', 'job_status': 'completed'}


def test_run_account_deletion_wipe_drops_non_actionable_job(monkeypatch):
    async def run_blocking(_executor, fn, *args):
        if fn is users_router.try_acquire_job_run_lock:
            return 'lock-token'
        if fn is users_router.claim_deletion_wipe_for_task:
            return 'not_actionable'
        if fn is users_router.release_job_run_lock:
            return None
        raise AssertionError(f'unexpected function {fn}')

    monkeypatch.setattr(users_router, 'run_blocking', run_blocking)

    response = asyncio.run(users_router.run_account_deletion_wipe(_FakeRequest({'uid': 'uid1'}), task_retry_count=0))

    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'dropped', 'reason': 'not_actionable'}


def test_run_account_deletion_wipe_preserves_lock_on_cancel(monkeypatch):
    released = []

    async def run_blocking(_executor, fn, *args):
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
        asyncio.run(users_router.run_account_deletion_wipe(_FakeRequest({'uid': 'uid1'}), task_retry_count=0))
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
