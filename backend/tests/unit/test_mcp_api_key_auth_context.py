from types import SimpleNamespace
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
from utils.mcp_memories import McpVerifiedAuth, build_mcp_default_memory_read_context
from utils.memory.product_authorization import authorize_memory_external_default_memory_read


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
    def __init__(self, docs, account_deletion=None):
        self._docs = docs
        self.grant_sets = []
        # None means no account_deletions/{uid} marker at all — the state every
        # live account is in.
        self.account_deletion = account_deletion
        self.deletion_reads = []

    def collection(self, name):
        if name == 'users':
            return _FakeUsersCollection(self)
        if name == 'account_deletions':
            return _FakeAccountDeletionCollection(self)
        assert name == 'mcp_api_keys'
        return _FakeQuery(self._docs)


class _FakeAccountDeletionCollection:
    def __init__(self, parent):
        self.parent = parent

    def document(self, uid):
        self.parent.deletion_reads.append(f'account_deletions/{uid}')
        return _FakeAccountDeletionDoc(self.parent.account_deletion)


class _FakeAccountDeletionDoc:
    def __init__(self, payload):
        self._payload = payload

    def get(self):
        payload = self._payload
        return SimpleNamespace(exists=payload is not None, to_dict=lambda: dict(payload or {}))


class _FakeUsersCollection:
    def __init__(self, parent):
        self.parent = parent

    def document(self, user_id):
        return _FakeUserDoc(self.parent, user_id)


class _FakeUserDoc:
    def __init__(self, parent, user_id):
        self.parent = parent
        self.user_id = user_id

    def collection(self, name):
        return _FakeGrantCollection(self.parent, self.user_id, name)

    def get(self):
        return SimpleNamespace(exists=getattr(self.parent, 'user_exists', True))


class _FakeGrantCollection:
    def __init__(self, parent, user_id, collection_name):
        self.parent = parent
        self.user_id = user_id
        self.collection_name = collection_name

    def document(self, doc_id):
        return _FakeGrantDoc(self.parent, self.user_id, self.collection_name, doc_id)


class _FakeGrantDoc:
    def __init__(self, parent, user_id, collection_name, doc_id):
        self.parent = parent
        self.user_id = user_id
        self.collection_name = collection_name
        self.doc_id = doc_id

    def set(self, payload, merge=False):
        self.parent.grant_sets.append((self.user_id, self.collection_name, self.doc_id, payload, merge))

    def get(self):
        return SimpleNamespace(exists=False, to_dict=lambda: {})


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
    fake_doc = _FakeDoc(
        {'id': 'legacy-key', 'user_id': 'u1', 'hashed_key': 'hashed', 'name': 'legacy'},
        doc_id='legacy-key',
    )
    fake_redis = _FakeRedis()
    fake_db = _FakeDB([fake_doc])
    monkeypatch.setattr(mcp_api_key_db, 'hash_api_key', lambda secret: 'hashed')
    monkeypatch.setattr(mcp_api_key_db, '_db', lambda: fake_db)
    monkeypatch.setattr(mcp_api_key_db, 'redis_db', fake_redis)

    assert mcp_api_key_db.get_user_id_by_api_key('omi_mcp_secret') == 'u1'
    auth = mcp_api_key_db.get_user_and_scopes_by_api_key('omi_mcp_secret')

    assert auth['user_id'] == 'u1'
    assert auth['key_id'] == 'legacy-key'
    assert auth['app_id'] == 'mcp-api'
    assert 'memories.read' in auth['scopes']
    assert 'memories.write' in auth['scopes']
    assert fake_db.grant_sets
    assert fake_redis.cached_writes[-1]['key_id'] == 'legacy-key'
    assert fake_redis.cached_writes[-1]['app_id'] == 'mcp-api'

    context = build_mcp_default_memory_read_context(
        McpVerifiedAuth(
            uid=auth['user_id'], app_id=auth['app_id'], key_id=auth['key_id'], scopes=tuple(auth['scopes'] or ())
        )
    )
    decision = authorize_memory_external_default_memory_read(
        context, db_client='fake-db', read_app_key_grants_state=_grant_reader
    )
    assert decision.allowed is False
    assert decision.reason == 'missing_app_key_scope_grant'


def test_persisted_mcp_app_key_scopes_build_verified_memory_context_without_archive(monkeypatch):
    fake_doc = _FakeDoc(
        {
            'id': 'key-1',
            'user_id': 'u1',
            'hashed_key': 'hashed',
            'app_id': 'mcp-api',
            'scopes': ['memories.read', 'goals.read'],
        },
        doc_id='key-1',
    )
    fake_db = _FakeDB([fake_doc])
    monkeypatch.setattr(mcp_api_key_db, 'hash_api_key', lambda secret: 'hashed')
    monkeypatch.setattr(mcp_api_key_db, '_db', lambda: fake_db)
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
        context, db_client='fake-db', read_app_key_grants_state=_grant_reader
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

    auth = asyncio.run(get_mcp_api_key_auth('Bearer omi_mcp_secret'))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_mcp_memory_default_memory_read_context(auth))

    assert exc.value.status_code == 403
    assert 'memories.read' in exc.value.detail


class _CreateDB:
    """Minimal Firestore stub for create_mcp_key: records the persisted doc."""

    def __init__(self):
        self.set_calls = []
        self.document_calls = []
        self.grant_sets = []

    def collection(self, name):
        if name == 'users':
            return _FakeUsersCollection(self)
        assert name == 'mcp_api_keys'
        return _CreateCollection(self)

    def document(self, path):
        return _CreateGrantDoc(self, path)


class _CreateCollection:
    def __init__(self, parent):
        self.parent = parent

    def document(self, _doc_id):
        return _CreateDoc(self.parent)


class _CreateDoc:
    def __init__(self, parent):
        self.parent = parent

    def set(self, doc):
        self.parent.set_calls.append(doc)


class _CreateGrantDoc:
    def __init__(self, parent, path):
        self.parent = parent
        self.path = path

    def set(self, doc, merge=False):
        self.parent.document_calls.append((self.path, doc, merge))


def test_create_mcp_key_seeds_default_memory_scopes(monkeypatch):
    """Newly minted MCP keys must seed scopes and the matching grant."""
    monkeypatch.setattr(mcp_api_key_db, 'generate_api_key', lambda: ('raw', 'hashed', 'omi_mcp_xxxx'))
    fake_db = _CreateDB()
    monkeypatch.setattr(mcp_api_key_db, '_db', lambda: fake_db)

    raw_key, api_key_data = mcp_api_key_db.create_mcp_key('u1', 'desktop-key')

    assert raw_key == 'raw'
    assert 'memories.read' in api_key_data.scopes
    assert 'memories.write' in api_key_data.scopes
    assert api_key_data.app_id == 'mcp-api'
    persisted = fake_db.set_calls[0]
    assert 'memories.read' in persisted['scopes']
    assert 'memories.write' in persisted['scopes']
    assert persisted['app_id'] == 'mcp-api'
    assert fake_db.grant_sets[0][0:3] == ('u1', 'memory_control', 'app_key_memory_grants')
    grant_doc = fake_db.grant_sets[0][3]
    seeded_grant = grant_doc['grants']['mcp']['apps']['mcp-api']['keys'][api_key_data.id]
    assert seeded_grant['scopes'] == ['memories.read', 'memories.write']
    assert seeded_grant['default_read'] is True
    assert seeded_grant['write'] is True
    assert fake_db.grant_sets[0][4] is True


def test_create_mcp_key_explicit_none_scopes_mints_legacy_key(monkeypatch):
    """Explicit scopes=None still mints a full-access MCP key."""
    monkeypatch.setattr(mcp_api_key_db, 'generate_api_key', lambda: ('raw', 'hashed', 'omi_mcp_xxxx'))
    fake_db = _CreateDB()
    monkeypatch.setattr(mcp_api_key_db, '_db', lambda: fake_db)

    _raw_key, api_key_data = mcp_api_key_db.create_mcp_key('u1', 'legacy-key', scopes=None)

    assert 'memories.read' in api_key_data.scopes
    assert fake_db.set_calls[0]['scopes'] == api_key_data.scopes
    assert fake_db.grant_sets


# ---------------------------------------------------------------------------
# Account-deletion gate
#
# The gate keys on the top-level account_deletions marker, NOT on the presence
# of the users/{uid} root document. Nothing creates that root document at
# signup — record_user_platform is a throttled telemetry side-effect that
# returns early without an X-App-Platform header — and Firestore reports a
# parent holding only subcollections as non-existent. Keying on it 401'd every
# key belonging to a curl/third-party/Linux principal, permanently.
# ---------------------------------------------------------------------------


def _key_doc():
    return _FakeDoc(
        {
            'id': 'key-1',
            'user_id': 'u1',
            'hashed_key': 'hashed',
            'app_id': 'mcp-api',
            'scopes': ['memories.read'],
        },
        doc_id='key-1',
    )


def test_legacy_principal_without_a_user_root_document_still_authenticates(monkeypatch):
    """Legacy-principal guard for the fail-closed deletion gate.

    An existing key whose owner never wrote a users/{uid} root field must keep
    working: no root doc is the normal state for anyone whose traffic never
    carried X-App-Platform.
    """
    fake_db = _FakeDB([_key_doc()], account_deletion=None)
    fake_db.user_exists = False  # users/{uid} root document absent
    monkeypatch.setattr(mcp_api_key_db, 'hash_api_key', lambda secret: 'hashed')
    monkeypatch.setattr(mcp_api_key_db, '_db', lambda: fake_db)
    monkeypatch.setattr(mcp_api_key_db, 'redis_db', _FakeRedis())

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key('omi_mcp_secret')

    assert auth is not None
    assert auth['user_id'] == 'u1'
    assert fake_db.deletion_reads == ['account_deletions/u1']


def test_key_is_rejected_once_a_deletion_marker_owns_the_account(monkeypatch):
    fake_db = _FakeDB([_key_doc()], account_deletion={'wipe_status': 'running'})
    monkeypatch.setattr(mcp_api_key_db, 'hash_api_key', lambda secret: 'hashed')
    monkeypatch.setattr(mcp_api_key_db, '_db', lambda: fake_db)
    monkeypatch.setattr(mcp_api_key_db, 'redis_db', _FakeRedis())

    assert mcp_api_key_db.get_user_and_scopes_by_api_key('omi_mcp_secret') is None


def test_a_cancelled_deletion_does_not_revoke_the_key(monkeypatch):
    """cancelled/billing_failed mean the account still exists and can sign in."""
    fake_db = _FakeDB([_key_doc()], account_deletion={'wipe_status': 'cancelled'})
    monkeypatch.setattr(mcp_api_key_db, 'hash_api_key', lambda secret: 'hashed')
    monkeypatch.setattr(mcp_api_key_db, '_db', lambda: fake_db)
    monkeypatch.setattr(mcp_api_key_db, 'redis_db', _FakeRedis())

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key('omi_mcp_secret')

    assert auth is not None and auth['user_id'] == 'u1'


def test_deletion_gate_runs_before_the_cached_auth_context_is_returned(monkeypatch):
    """A key cached just before the purge must not survive for the cache TTL."""
    cached = {
        'user_id': 'u1',
        'scopes': sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
        'key_id': 'key-1',
        'app_id': 'mcp-api',
        'auth_context_version': mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION,
    }
    fake_db = _FakeDB([], account_deletion={'wipe_status': 'completed'})
    monkeypatch.setattr(mcp_api_key_db, 'hash_api_key', lambda secret: 'hashed')
    monkeypatch.setattr(mcp_api_key_db, '_db', lambda: fake_db)
    monkeypatch.setattr(mcp_api_key_db, 'redis_db', _FakeRedis(cached=cached))

    assert mcp_api_key_db.get_user_and_scopes_by_api_key('omi_mcp_secret') is None
    assert fake_db.deletion_reads == ['account_deletions/u1']
