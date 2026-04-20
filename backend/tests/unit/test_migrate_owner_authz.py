import ast
from pathlib import Path

import pytest
from fastapi import HTTPException


def _load_migrate_app_owner(verified_old_uid='legacy-user', verify_raises=None):
    path = Path('/tmp/omi-audit/backend/routers/apps.py')
    source = path.read_text()
    module = ast.parse(source)
    fn = next(node for node in module.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'migrate_app_owner')
    mod = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(mod)

    calls = []
    tasks = []

    class FakeRouter:
        def post(self, *args, **kwargs):
            def deco(f):
                return f
            return deco

    class FakeAsyncioModule:
        def create_task(self, coro):
            tasks.append(coro)
            return f'task-{len(tasks)}'

    async def fake_migrate_memories(old_id, uid):
        calls.append(('migrate_memories', old_id, uid))
        return 'ok'

    async def fake_update(uid):
        calls.append(('update_omi_persona_connected_accounts', uid))
        return 'ok'

    def fake_migrate_app_owner_id_db(uid, old_id):
        calls.append(('migrate_app_owner_id_db', uid, old_id))

    def fake_verify_token(token):
        calls.append(('verify_token', token))
        if verify_raises:
            raise verify_raises
        return verified_old_uid

    ns = {
        'router': FakeRouter(),
        'asyncio': FakeAsyncioModule(),
        'migrate_app_owner_id_db': fake_migrate_app_owner_id_db,
        'migrate_memories': fake_migrate_memories,
        'update_omi_persona_connected_accounts': fake_update,
        'auth': type('A', (), {'get_current_user_uid': object(), 'verify_token': staticmethod(fake_verify_token)})(),
        'Depends': lambda x: x,
        'Header': lambda *args, **kwargs: None,
        'HTTPException': HTTPException,
    }
    exec(compile(mod, str(path), 'exec'), ns)
    return ns['migrate_app_owner'], calls, tasks


@pytest.mark.asyncio
async def test_migrate_owner_rejects_when_old_auth_token_does_not_match_old_id():
    migrate_app_owner, calls, tasks = _load_migrate_app_owner(verified_old_uid='different-legacy-user')

    with pytest.raises(HTTPException, match='not authorized'):
        await migrate_app_owner('victim-old-uid', old_authorization='Bearer proof-token', uid='attacker-uid')

    assert calls == [('verify_token', 'proof-token')]
    assert tasks == []


@pytest.mark.asyncio
async def test_migrate_owner_allows_proven_legacy_account_migration_only():
    migrate_app_owner, calls, tasks = _load_migrate_app_owner(verified_old_uid='legacy-user')

    result = await migrate_app_owner('legacy-user', old_authorization='Bearer proof-token', uid='new-user')

    assert result == {'status': 'ok', 'message': 'Migration started'}
    assert calls == [
        ('verify_token', 'proof-token'),
        ('migrate_app_owner_id_db', 'new-user', 'legacy-user'),
    ]
    assert len(tasks) == 2

    for task in tasks:
        await task

    assert calls == [
        ('verify_token', 'proof-token'),
        ('migrate_app_owner_id_db', 'new-user', 'legacy-user'),
        ('migrate_memories', 'legacy-user', 'new-user'),
        ('update_omi_persona_connected_accounts', 'new-user'),
    ]
