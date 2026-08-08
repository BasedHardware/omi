import asyncio
import sys
from pathlib import Path
from types import ModuleType

import pytest

from database.api_key_metadata import ApiKeyCacheReadMode, ApiKeyCacheReadResult


def _drop_stale_module(name: str, expected_file: Path) -> None:
    module = sys.modules.get(name)
    if module is None:
        if "." in name:
            parent_name, attr_name = name.rsplit(".", 1)
            parent = sys.modules.get(parent_name)
            parent_attr = getattr(parent, attr_name, None) if isinstance(parent, ModuleType) else None
            if parent_attr is not None and getattr(parent_attr, "__file__", None) != str(expected_file):
                delattr(parent, attr_name)
        return
    module_file = getattr(module, "__file__", None)
    try:
        module_path = Path(module_file).resolve() if module_file else None
    except TypeError:
        module_path = None
    if module_path == expected_file.resolve():
        return
    sys.modules.pop(name, None)
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if isinstance(parent, ModuleType) and getattr(parent, attr_name, None) is module:
            delattr(parent, attr_name)


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_drop_stale_module("database.mcp_api_key", _BACKEND_DIR / "database" / "mcp_api_key.py")
sys.modules.pop("dependencies", None)

import dependencies
from fastapi import HTTPException

import database.mcp_api_key as mcp_api_key_db
from dependencies import get_mcp_api_key_auth, get_mcp_memory_default_memory_read_context
from tests.store_fakes import FakeDocumentStore
from utils.mcp_memories import McpVerifiedAuth, build_mcp_default_memory_read_context
from utils.memory.product_authorization import authorize_memory_external_default_memory_read


def _grant_path(user_id: str) -> str:
    return (
        f"users/{user_id}/{mcp_api_key_db.MCP_MEMORY_CONTROL_COLLECTION}"
        f"/{mcp_api_key_db.MCP_APP_KEY_MEMORY_GRANTS_DOC_ID}"
    )


class _FakeRedis:
    def __init__(self, cached=None):
        self.cached = cached
        self.cached_writes = []

    def read_cached_mcp_api_key_auth_context(self, _hashed_key):
        if self.cached is None:
            return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.MISS)
        return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.HIT, data=self.cached)

    def cache_mcp_api_key_auth_context(
        self,
        hashed_key,
        user_id,
        scopes=None,
        key_id=None,
        app_id=None,
        memory_grant_seeded=True,
        auth_context_version=mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION,
    ):
        payload = {
            'hashed_key': hashed_key,
            'user_id': user_id,
            'scopes': scopes,
            'key_id': key_id,
            'app_id': app_id,
            'memory_grant_seeded': memory_grant_seeded,
            'auth_context_version': auth_context_version,
        }
        self.cached_writes.append(payload)
        self.cached = {key: value for key, value in payload.items() if key != 'hashed_key'}
        return True

    def get_cached_mcp_api_key_user_id(self, _hashed_key):
        return None

    def cache_mcp_api_key(self, _hashed_key, _user_id):
        raise AssertionError('new auth-context cache should be used after Firestore lookup')


class _GrantStateRead:
    def __init__(self, state):
        self.state = state
        self.reason = 'ok'
        self.source_path = 'users/u1/memory_control/app_key_memory_grants'


def _grant_reader(*, uid):
    assert uid == 'u1'
    return _GrantStateRead(
        {
            'grants': {
                'mcp': {
                    'apps': {
                        'mcp-api': {
                            'keys': {
                                'key-1': {
                                    'enabled': True,
                                    'scopes': ['memories.read'],
                                    'default_read': True,
                                    'archive_read': False,
                                    'write': False,
                                }
                            }
                        }
                    }
                }
            }
        }
    )


def test_old_mcp_key_doc_still_authenticates_uid_only_and_has_no_verified_scopes(monkeypatch):
    store = FakeDocumentStore()
    store.set(
        'mcp_api_keys/legacy-key',
        {'id': 'legacy-key', 'user_id': 'u1', 'hashed_key': 'hashed', 'name': 'legacy'},
    )
    fake_redis = _FakeRedis()
    monkeypatch.setattr(mcp_api_key_db, 'hash_api_key', lambda secret: 'hashed')
    monkeypatch.setattr(mcp_api_key_db, '_store', lambda: store)
    monkeypatch.setattr(mcp_api_key_db, 'redis_db', fake_redis)

    assert mcp_api_key_db.get_user_id_by_api_key('omi_mcp_secret') == 'u1'
    auth = mcp_api_key_db.get_user_and_scopes_by_api_key('omi_mcp_secret')

    assert auth['user_id'] == 'u1'
    assert auth['key_id'] == 'legacy-key'
    assert auth['app_id'] == 'mcp-api'
    assert 'memories.read' in auth['scopes']
    assert 'memories.write' in auth['scopes']
    # The lazy repair persisted a memory grant for this key.
    grant = store.get(_grant_path('u1')).to_dict()
    assert grant['grants']['mcp']['apps']['mcp-api']['keys']['legacy-key']['enabled'] is True
    assert fake_redis.cached_writes[-1]['key_id'] == 'legacy-key'
    assert fake_redis.cached_writes[-1]['app_id'] == 'mcp-api'

    context = build_mcp_default_memory_read_context(
        McpVerifiedAuth(
            uid=auth['user_id'], app_id=auth['app_id'], key_id=auth['key_id'], scopes=tuple(auth['scopes'] or ())
        )
    )
    decision = authorize_memory_external_default_memory_read(
        context, read_app_key_grants_state=_grant_reader
    )
    assert decision.allowed is False
    assert decision.reason == 'missing_app_key_scope_grant'


def test_persisted_mcp_app_key_scopes_build_verified_memory_context_without_archive(monkeypatch):
    store = FakeDocumentStore()
    store.set(
        'mcp_api_keys/key-1',
        {
            'id': 'key-1',
            'user_id': 'u1',
            'hashed_key': 'hashed',
            'app_id': 'mcp-api',
            'scopes': ['memories.read', 'goals.read'],
        },
    )
    monkeypatch.setattr(mcp_api_key_db, 'hash_api_key', lambda secret: 'hashed')
    monkeypatch.setattr(mcp_api_key_db, '_store', lambda: store)
    monkeypatch.setattr(mcp_api_key_db, 'redis_db', _FakeRedis())

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key('omi_mcp_secret')
    assert auth['user_id'] == 'u1'
    assert auth['key_id'] == 'key-1'
    assert auth['app_id'] == 'mcp-api'
    assert 'memories.read' in auth['scopes']
    assert 'goals.read' in auth['scopes']

    context = build_mcp_default_memory_read_context(
        McpVerifiedAuth(uid=auth['user_id'], app_id=auth['app_id'], key_id=auth['key_id'], scopes=tuple(auth['scopes']))
    )
    decision = authorize_memory_external_default_memory_read(
        context, read_app_key_grants_state=_grant_reader
    )

    assert decision.allowed is True
    assert decision.context.consumer == 'mcp'
    assert decision.context.surface == 'mcp_default_memory_read'
    assert decision.policy.archive_capability is False


def test_mcp_auth_dependency_preserves_uid_scope_identity_shape(monkeypatch):
    monkeypatch.setattr(
        mcp_api_key_db,
        'get_api_key_auth_result',
        lambda token: mcp_api_key_db.ApiKeyAuthLookupResult(
            context={'user_id': 'u1', 'scopes': ['memories.read'], 'key_id': 'key-1', 'app_id': 'mcp-api'}
        ),
    )
    monkeypatch.setattr(dependencies, 'check_api_key_rate_limit', lambda **_kwargs: None)
    monkeypatch.setattr(dependencies, 'enforce_account_deletion_http_access', lambda _uid: None)

    auth = asyncio.run(get_mcp_api_key_auth('Bearer omi_mcp_secret'))
    context = asyncio.run(get_mcp_memory_default_memory_read_context(auth))

    assert auth.uid == 'u1'
    assert auth.scopes == ['memories.read']
    assert auth.key_id == 'key-1'
    assert auth.app_id == 'mcp-api'
    assert context.uid == 'u1'
    assert context.consumer == 'mcp'
    assert context.app_id == 'mcp-api'
    assert context.key_id == 'key-1'
    assert context.scopes == ('memories.read',)


def test_mcp_memory_dependency_fails_closed_without_persisted_memories_read_scope(monkeypatch):
    monkeypatch.setattr(
        mcp_api_key_db,
        'get_api_key_auth_result',
        lambda token: mcp_api_key_db.ApiKeyAuthLookupResult(
            context={'user_id': 'u1', 'scopes': [], 'key_id': 'key-1', 'app_id': 'mcp-api'}
        ),
    )
    monkeypatch.setattr(dependencies, 'enforce_account_deletion_http_access', lambda _uid: None)

    auth = asyncio.run(get_mcp_api_key_auth('Bearer omi_mcp_secret'))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_mcp_memory_default_memory_read_context(auth))

    assert exc.value.status_code == 403
    assert 'memories.read' in exc.value.detail


def test_create_mcp_key_seeds_default_memory_scopes(monkeypatch):
    """Newly minted MCP keys must seed scopes and the matching grant."""
    monkeypatch.setattr(mcp_api_key_db, 'generate_api_key', lambda: ('raw', 'hashed', 'omi_mcp_xxxx'))
    store = FakeDocumentStore()
    monkeypatch.setattr(mcp_api_key_db, '_store', lambda: store)

    raw_key, api_key_data = mcp_api_key_db.create_mcp_key('u1', 'desktop-key')

    assert raw_key == 'raw'
    assert 'memories.read' in api_key_data.scopes
    assert 'memories.write' in api_key_data.scopes
    assert api_key_data.app_id == 'mcp-api'
    persisted = store.get(f'mcp_api_keys/{api_key_data.id}').to_dict()
    assert 'memories.read' in persisted['scopes']
    assert 'memories.write' in persisted['scopes']
    assert persisted['app_id'] == 'mcp-api'
    grant_doc = store.get(_grant_path('u1')).to_dict()
    seeded_grant = grant_doc['grants']['mcp']['apps']['mcp-api']['keys'][api_key_data.id]
    assert seeded_grant['scopes'] == ['memories.read', 'memories.write']
    assert seeded_grant['default_read'] is True
    assert seeded_grant['write'] is True


def test_create_mcp_key_explicit_none_scopes_mints_legacy_key(monkeypatch):
    """Explicit scopes=None still mints a full-access MCP key."""
    monkeypatch.setattr(mcp_api_key_db, 'generate_api_key', lambda: ('raw', 'hashed', 'omi_mcp_xxxx'))
    store = FakeDocumentStore()
    monkeypatch.setattr(mcp_api_key_db, '_store', lambda: store)

    _raw_key, api_key_data = mcp_api_key_db.create_mcp_key('u1', 'legacy-key', scopes=None)

    assert 'memories.read' in api_key_data.scopes
    assert store.get(f'mcp_api_keys/{api_key_data.id}').to_dict()['scopes'] == api_key_data.scopes
    assert store.exists(_grant_path('u1'))
