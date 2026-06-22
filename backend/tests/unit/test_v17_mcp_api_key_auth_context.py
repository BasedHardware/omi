from datetime import datetime
from types import ModuleType, SimpleNamespace
import asyncio
import sys

import pytest


class _FakeHTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _identity_dependency(value=None):
    return value


_fake_fastapi = ModuleType('fastapi')
setattr(_fake_fastapi, 'HTTPException', _FakeHTTPException)
setattr(_fake_fastapi, 'Depends', _identity_dependency)
setattr(_fake_fastapi, 'Security', _identity_dependency)
setattr(_fake_fastapi, 'Request', type('Request', (), {}))
_fake_fastapi_security = ModuleType('fastapi.security')
setattr(_fake_fastapi_security, 'APIKeyHeader', lambda *args, **kwargs: None)
setattr(_fake_fastapi_security, 'HTTPBearer', lambda *args, **kwargs: None)
setattr(_fake_fastapi_security, 'HTTPAuthorizationCredentials', object)
sys.modules.setdefault('fastapi', _fake_fastapi)
sys.modules.setdefault('fastapi.security', _fake_fastapi_security)
_fake_firebase_admin = ModuleType('firebase_admin')
setattr(_fake_firebase_admin, 'auth', SimpleNamespace(verify_id_token=lambda _token: {'uid': 'unused'}))
sys.modules.setdefault('firebase_admin', _fake_firebase_admin)

from fastapi import HTTPException

_fake_client = ModuleType('database._client')
setattr(_fake_client, 'db', SimpleNamespace())
sys.modules['database._client'] = _fake_client

import database.mcp_api_key as mcp_api_key_db
from dependencies import get_mcp_api_key_auth, get_mcp_v17_default_memory_read_context
from utils.mcp_memories import McpV17VerifiedAuth, build_mcp_v17_default_memory_read_context
from utils.memory.v17_product_authorization import authorize_v17_external_default_memory_read


class _FakeDoc:
    def __init__(self, data, doc_id='doc-key-id'):
        self._data = data
        self.id = doc_id
        self.reference = SimpleNamespace(updated=[])
        self.reference.update = lambda payload: self.reference.updated.append(payload)

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    def __init__(self, docs):
        self._docs = docs

    def where(self, *_args, **_kwargs):
        return self

    def limit(self, _limit):
        return self

    def stream(self):
        return list(self._docs)


class _FakeDB:
    def __init__(self, docs):
        self._docs = docs

    def collection(self, name):
        assert name == 'mcp_api_keys'
        return _FakeQuery(self._docs)


class _FakeRedis:
    def __init__(self, cached=None):
        self.cached = cached
        self.cached_writes = []

    def get_cached_mcp_api_key_auth_context(self, _hashed_key):
        return self.cached

    def cache_mcp_api_key_auth_context(self, hashed_key, user_id, scopes=None, key_id=None, app_id=None):
        payload = {'hashed_key': hashed_key, 'user_id': user_id, 'scopes': scopes, 'key_id': key_id, 'app_id': app_id}
        self.cached_writes.append(payload)
        self.cached = {key: value for key, value in payload.items() if key != 'hashed_key'}

    def get_cached_mcp_api_key_user_id(self, _hashed_key):
        return None

    def cache_mcp_api_key(self, _hashed_key, _user_id):
        raise AssertionError('new auth-context cache should be used after Firestore lookup')


class _GrantStateRead:
    def __init__(self, state):
        self.state = state
        self.reason = 'ok'
        self.source_path = 'users/u1/memory_control/v17_app_key_memory_grants'


def _grant_reader(*, uid, db_client):
    assert uid == 'u1'
    assert db_client == 'fake-db'
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
    fake_doc = _FakeDoc({'id': 'legacy-key', 'user_id': 'u1', 'hashed_key': 'hashed', 'name': 'legacy'})
    fake_redis = _FakeRedis()
    monkeypatch.setattr(mcp_api_key_db, 'hash_api_key', lambda secret: 'hashed')
    monkeypatch.setattr(mcp_api_key_db, 'db', _FakeDB([fake_doc]))
    monkeypatch.setattr(mcp_api_key_db, 'redis_db', fake_redis)

    assert mcp_api_key_db.get_user_id_by_api_key('omi_mcp_secret') == 'u1'
    auth = mcp_api_key_db.get_user_and_scopes_by_api_key('omi_mcp_secret')

    assert auth == {'user_id': 'u1', 'scopes': None, 'key_id': 'legacy-key', 'app_id': None}
    assert fake_redis.cached_writes == [
        {'hashed_key': 'hashed', 'user_id': 'u1', 'scopes': None, 'key_id': 'legacy-key', 'app_id': None}
    ]

    context = build_mcp_v17_default_memory_read_context(
        McpV17VerifiedAuth(
            uid=auth['user_id'], app_id=auth['app_id'], key_id=auth['key_id'], scopes=tuple(auth['scopes'] or ())
        )
    )
    decision = authorize_v17_external_default_memory_read(
        context, db_client='fake-db', read_app_key_grants_state=_grant_reader
    )
    assert decision.allowed is False
    assert decision.reason == 'missing_app_or_key_identity'


def test_persisted_mcp_app_key_scopes_build_verified_v17_context_without_archive(monkeypatch):
    fake_doc = _FakeDoc(
        {
            'id': 'key-1',
            'user_id': 'u1',
            'hashed_key': 'hashed',
            'app_id': 'mcp-api',
            'scopes': ['memories.read', 'goals.read'],
        }
    )
    monkeypatch.setattr(mcp_api_key_db, 'hash_api_key', lambda secret: 'hashed')
    monkeypatch.setattr(mcp_api_key_db, 'db', _FakeDB([fake_doc]))
    monkeypatch.setattr(mcp_api_key_db, 'redis_db', _FakeRedis())

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key('omi_mcp_secret')
    assert auth == {'user_id': 'u1', 'scopes': ['memories.read', 'goals.read'], 'key_id': 'key-1', 'app_id': 'mcp-api'}

    context = build_mcp_v17_default_memory_read_context(
        McpV17VerifiedAuth(
            uid=auth['user_id'], app_id=auth['app_id'], key_id=auth['key_id'], scopes=tuple(auth['scopes'])
        )
    )
    decision = authorize_v17_external_default_memory_read(
        context, db_client='fake-db', read_app_key_grants_state=_grant_reader
    )

    assert decision.allowed is True
    assert decision.context.consumer == 'mcp'
    assert decision.context.surface == 'mcp_default_memory_read'
    assert decision.policy.archive_capability is False


def test_mcp_auth_dependency_preserves_uid_scope_identity_shape(monkeypatch):
    monkeypatch.setattr(
        mcp_api_key_db,
        'get_user_and_scopes_by_api_key',
        lambda token: {'user_id': 'u1', 'scopes': ['memories.read'], 'key_id': 'key-1', 'app_id': 'mcp-api'},
    )

    auth = asyncio.run(get_mcp_api_key_auth('Bearer omi_mcp_secret'))
    context = asyncio.run(get_mcp_v17_default_memory_read_context(auth))

    assert auth.uid == 'u1'
    assert auth.scopes == ['memories.read']
    assert auth.key_id == 'key-1'
    assert auth.app_id == 'mcp-api'
    assert context.uid == 'u1'
    assert context.consumer == 'mcp'
    assert context.app_id == 'mcp-api'
    assert context.key_id == 'key-1'
    assert context.scopes == ('memories.read',)


def test_mcp_v17_dependency_fails_closed_without_persisted_memories_read_scope(monkeypatch):
    monkeypatch.setattr(
        mcp_api_key_db,
        'get_user_and_scopes_by_api_key',
        lambda token: {'user_id': 'u1', 'scopes': [], 'key_id': 'key-1', 'app_id': 'mcp-api'},
    )

    auth = asyncio.run(get_mcp_api_key_auth('Bearer omi_mcp_secret'))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_mcp_v17_default_memory_read_context(auth))

    assert exc.value.status_code == 403
    assert 'memories.read' in exc.value.detail
