"""Regression: POST /v1/apps/migrate-owner must schedule its post-merge background
work (memory migration, persona connected-account sync) via the tracked
start_background_task helper, not a bare asyncio.create_task().

This endpoint fires when a user links an anonymous account to Google/Apple and the
credential already belongs to an existing account (app/lib/providers/auth_provider.dart
-> migrateAppOwnerId). The client gets {"status": "ok"} back immediately while the
memory migration and persona sync continue in the background.

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

import routers.apps as apps_mod
import utils.executors as executors_mod


def _anonymous_user_info():
    # firebase_admin UserRecord.provider_data is empty for an anonymous sign-in.
    return SimpleNamespace(provider_data=[])


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
    monkeypatch.setattr(apps_mod.auth, 'get_user', lambda uid: _anonymous_user_info())

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
        result = await apps_mod.migrate_app_owner('old-uid', uid='new-uid')
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


def test_migrate_owner_rejects_non_anonymous_old_id(monkeypatch):
    """Regression: old_id is client-supplied. Without verifying it names an anonymous
    Firebase identity, any authenticated user could pass another real user's uid as
    old_id and have that victim's apps and memories folded into the attacker's account
    (a full account-takeover IDOR). Only a provider-less (anonymous) account may be the
    source of a migration.
    """
    migrate_called = False

    def fake_migrate_app_owner_id_db(new_id, old_id):
        nonlocal migrate_called
        migrate_called = True

    monkeypatch.setattr(apps_mod, 'migrate_app_owner_id_db', fake_migrate_app_owner_id_db)
    monkeypatch.setattr(
        apps_mod.auth, 'get_user', lambda uid: SimpleNamespace(provider_data=[SimpleNamespace(provider_id='google.com')])
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(apps_mod.migrate_app_owner('victim-uid', uid='attacker-uid'))

    assert exc_info.value.status_code == 403
    assert not migrate_called, 'migration must not run when old_id is not an anonymous account'


def test_migrate_owner_rejects_missing_old_id(monkeypatch):
    from fastapi import HTTPException
    from firebase_admin.auth import UserNotFoundError

    def raise_not_found(uid):
        raise UserNotFoundError('no such user')

    monkeypatch.setattr(apps_mod.auth, 'get_user', raise_not_found)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(apps_mod.migrate_app_owner('missing-uid', uid='attacker-uid'))

    assert exc_info.value.status_code == 404


def test_migrate_owner_rejects_self_migration():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(apps_mod.migrate_app_owner('same-uid', uid='same-uid'))

    assert exc_info.value.status_code == 400
