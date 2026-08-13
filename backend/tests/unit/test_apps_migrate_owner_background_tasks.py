"""Regression: POST /v1/apps/migrate-owner must schedule its post-merge background
work (memory migration, persona connected-account sync) via the tracked
start_background_task helper, not a bare asyncio.create_task().

This endpoint fires when a user links an anonymous account to Google/Apple and the
credential already belongs to an existing account (app/lib/providers/auth_provider.dart
-> migrateAppOwnerId). The client sends the anonymous source's Firebase ID token after
it has signed into the destination account, and gets {"status": "ok"} back immediately
while the memory migration and persona sync continue in the background.

A bare asyncio.create_task() with its result discarded is exactly the fire-and-forget
footgun utils/executors.py warns about: the task has no reachable reference (so it can
be garbage-collected mid-flight) and, if the coroutine raises, nothing in the app ever
logs it -- the memory migration silently never completes while the API already told the
client "Migration started". start_background_task keeps a tracked reference and logs any
failure via 'background_task failed: ...'.

No live services: run_blocking still runs on the real (in-process) db_executor thread
pool, but the functions it calls are monkeypatched to pure Python fakes.
"""

import asyncio
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routers.apps as apps_mod
import utils.executors as executors_mod


def test_migrate_owner_schedules_tracked_background_tasks(monkeypatch, caplog):
    calls = {'migrate_memories': False, 'persona_sync': False}

    def fake_migrate_app_owner_id_db(new_id, old_id):
        return None

    def fake_migrate_memories(old_id, new_id):
        calls['migrate_memories'] = True
        raise RuntimeError('boom-migrate-memories')

    async def fake_update_persona(uid):
        calls['persona_sync'] = True
        raise RuntimeError('boom-persona-sync')

    monkeypatch.setattr(apps_mod, 'migrate_app_owner_id_db', fake_migrate_app_owner_id_db)
    monkeypatch.setattr(apps_mod, 'migrate_memories', fake_migrate_memories)
    monkeypatch.setattr(apps_mod, 'update_omi_persona_connected_accounts', fake_update_persona)
    monkeypatch.setattr(
        apps_mod.auth.auth,
        'verify_id_token',
        lambda token, check_revoked: {'uid': 'old-uid', 'firebase': {'sign_in_provider': 'anonymous'}},
    )
    monkeypatch.setattr(apps_mod.auth, 'get_user', lambda _uid: SimpleNamespace(disabled=False, provider_data=[]))
    monkeypatch.setattr(apps_mod.auth, 'enforce_account_deletion_http_access', lambda _uid: None)

    # Spy on asyncio.create_task (used directly by the buggy code, and internally by
    # start_background_task in the fixed code) so the test can await whatever tasks get
    # created either way, with no reliance on wall-clock sleeps.
    created_tasks = []
    real_create_task = asyncio.create_task

    def spying_create_task(coro, *args, **kwargs):
        task = real_create_task(coro, *args, **kwargs)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(asyncio, 'create_task', spying_create_task)

    baseline_tracked = executors_mod.get_background_task_count()

    async def scenario():
        result = await apps_mod.migrate_app_owner('old-uid', source_token='source-token', uid='new-uid')
        # Checked before any further await: start_background_task adds to the shared
        # registry synchronously at schedule time, so this is timing-independent.
        tracked_delta = executors_mod.get_background_task_count() - baseline_tracked
        await asyncio.gather(*created_tasks, return_exceptions=True)
        return result, tracked_delta

    caplog.set_level(logging.ERROR, logger='utils.executors')
    result, tracked_delta = asyncio.run(scenario())

    assert result == {"status": "ok", "message": "Migration started"}
    assert calls == {'migrate_memories': True, 'persona_sync': True}
    assert len(created_tasks) == 2

    assert tracked_delta == 2, (
        'migrate_app_owner must schedule its background work via start_background_task '
        '(tracked) instead of a bare asyncio.create_task() (untracked, GC-vulnerable)'
    )
    assert 'background_task failed' in caplog.text, 'a failed background migration must be logged, not dropped'
    assert 'boom-migrate-memories' in caplog.text
    assert 'boom-persona-sync' in caplog.text


@pytest.mark.parametrize(
    ('old_id', 'source_claims', 'source_user'),
    [
        (
            'registered-uid',
            {'uid': 'registered-uid', 'firebase': {'sign_in_provider': 'anonymous'}},
            SimpleNamespace(disabled=False, provider_data=[SimpleNamespace(provider_id='google.com')]),
        ),
        (
            'custom-token-uid',
            {'uid': 'custom-token-uid', 'firebase': {'sign_in_provider': 'custom'}},
            SimpleNamespace(disabled=False, provider_data=[]),
        ),
        (
            'wrong-uid',
            {'uid': 'another-uid', 'firebase': {'sign_in_provider': 'anonymous'}},
            SimpleNamespace(disabled=False, provider_data=[]),
        ),
        (
            'disabled-anonymous-uid',
            {'uid': 'disabled-anonymous-uid', 'firebase': {'sign_in_provider': 'anonymous'}},
            SimpleNamespace(disabled=True, provider_data=[]),
        ),
    ],
)
def test_migrate_owner_rejects_ineligible_source_before_any_effect(monkeypatch, old_id, source_claims, source_user):
    effects = []

    monkeypatch.setattr(apps_mod.auth.auth, 'verify_id_token', lambda _token, check_revoked: source_claims)
    monkeypatch.setattr(apps_mod.auth, 'get_user', lambda _uid: source_user)
    monkeypatch.setattr(apps_mod, 'migrate_app_owner_id_db', lambda *_args: effects.append('database'))
    monkeypatch.setattr(apps_mod, 'start_background_task', lambda *_args, **_kwargs: effects.append('background'))

    async def scenario():
        with pytest.raises(HTTPException) as exc_info:
            await apps_mod.migrate_app_owner(old_id, source_token='source-token', uid='authenticated-uid')
        return exc_info.value

    error = asyncio.run(scenario())

    assert error.status_code == 403
    assert effects == []


def test_migrate_owner_rejects_same_identity_before_any_effect(monkeypatch):
    effects = []

    monkeypatch.setattr(
        apps_mod.auth.auth,
        'verify_id_token',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('token verification should not run')),
    )
    monkeypatch.setattr(
        apps_mod.auth, 'get_user', lambda _uid: (_ for _ in ()).throw(AssertionError('lookup should not run'))
    )
    monkeypatch.setattr(apps_mod, 'migrate_app_owner_id_db', lambda *_args: effects.append('database'))
    monkeypatch.setattr(apps_mod, 'start_background_task', lambda *_args, **_kwargs: effects.append('background'))

    async def scenario():
        with pytest.raises(HTTPException) as exc_info:
            await apps_mod.migrate_app_owner('authenticated-uid', source_token='source-token', uid='authenticated-uid')
        return exc_info.value

    error = asyncio.run(scenario())

    assert error.status_code == 400
    assert effects == []


@pytest.mark.parametrize('lookup_error', [LookupError('missing'), RuntimeError('firebase unavailable')])
def test_migrate_owner_fails_closed_when_source_identity_lookup_fails(monkeypatch, lookup_error):
    effects = []

    def fail_lookup(_uid):
        raise lookup_error

    monkeypatch.setattr(
        apps_mod.auth.auth,
        'verify_id_token',
        lambda _token, check_revoked: {'uid': 'anonymous-uid', 'firebase': {'sign_in_provider': 'anonymous'}},
    )
    monkeypatch.setattr(apps_mod.auth, 'get_user', fail_lookup)
    monkeypatch.setattr(apps_mod, 'migrate_app_owner_id_db', lambda *_args: effects.append('database'))
    monkeypatch.setattr(apps_mod, 'start_background_task', lambda *_args, **_kwargs: effects.append('background'))

    async def scenario():
        with pytest.raises(HTTPException) as exc_info:
            await apps_mod.migrate_app_owner('anonymous-uid', source_token='source-token', uid='authenticated-uid')
        return exc_info.value

    error = asyncio.run(scenario())

    assert error.status_code == 403
    assert effects == []


def test_migrate_owner_fails_closed_when_source_token_verification_fails(monkeypatch):
    effects = []

    def fail_verification(_token, check_revoked):
        raise RuntimeError('invalid source token')

    monkeypatch.setattr(apps_mod.auth.auth, 'verify_id_token', fail_verification)
    monkeypatch.setattr(
        apps_mod.auth, 'get_user', lambda _uid: (_ for _ in ()).throw(AssertionError('lookup should not run'))
    )
    monkeypatch.setattr(apps_mod, 'migrate_app_owner_id_db', lambda *_args: effects.append('database'))
    monkeypatch.setattr(apps_mod, 'start_background_task', lambda *_args, **_kwargs: effects.append('background'))

    async def scenario():
        with pytest.raises(HTTPException) as exc_info:
            await apps_mod.migrate_app_owner('anonymous-uid', source_token='source-token', uid='authenticated-uid')
        return exc_info.value

    error = asyncio.run(scenario())

    assert error.status_code == 403
    assert effects == []


def test_migrate_owner_rejects_missing_source_token_before_any_effect(monkeypatch):
    effects = []

    monkeypatch.setattr(
        apps_mod.auth.auth,
        'verify_id_token',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('token verification should not run')),
    )
    monkeypatch.setattr(
        apps_mod.auth, 'get_user', lambda _uid: (_ for _ in ()).throw(AssertionError('lookup should not run'))
    )
    monkeypatch.setattr(apps_mod, 'migrate_app_owner_id_db', lambda *_args: effects.append('database'))
    monkeypatch.setattr(apps_mod, 'start_background_task', lambda *_args, **_kwargs: effects.append('background'))

    async def scenario():
        with pytest.raises(HTTPException) as exc_info:
            await apps_mod.migrate_app_owner('anonymous-uid', source_token=None, uid='authenticated-uid')
        return exc_info.value

    error = asyncio.run(scenario())

    assert error.status_code == 403
    assert effects == []
