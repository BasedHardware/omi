import json
import os
from datetime import timedelta
from pathlib import Path
from types import ModuleType

import pytest

from testing.import_isolation import load_module_fresh, stub_modules
from utils.mcp_memories import McpVerifiedAuth, build_mcp_default_memory_read_context
from utils.memory.product_authorization import authorize_memory_external_default_memory_read

_BACKEND = Path(__file__).resolve().parents[2]

os.environ['MCP_OAUTH_CHATGPT_CLIENT_ID'] = 'omi-chatgpt-prod'
os.environ['MCP_OAUTH_CHATGPT_CLIENT_SECRET'] = 'client-secret'
os.environ['MCP_OAUTH_CHATGPT_REDIRECT_URIS'] = 'https://chatgpt.com/connector_platform_oauth_redirect'
os.environ['MCP_OAUTH_PUBLIC_REDIRECT_URIS'] = 'https://chatgpt.com/connector_platform_oauth_redirect'


class _DocSnapshot:
    def __init__(self, reference, data=None):
        self.reference = reference
        self.id = reference.id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class _DocReference:
    def __init__(self, collection, doc_id):
        self._collection = collection
        self.id = doc_id

    def get(self, transaction=None):
        return _DocSnapshot(self, self._collection._docs.get(self.id))

    def set(self, data, merge=False):
        if merge and self.id in self._collection._docs:
            _deep_merge(self._collection._docs[self.id], data)
        else:
            self._collection._docs[self.id] = dict(data)

    def update(self, data):
        self._collection._docs.setdefault(self.id, {}).update(data)

    def delete(self):
        self._collection._docs.pop(self.id, None)


class _Query:
    def __init__(self, collection, field, expected):
        self._collection = collection
        self._field = field
        self._expected = expected

    def stream(self):
        for doc_id, data in self._collection._docs.items():
            if data.get(self._field) == self._expected:
                yield _DocSnapshot(_DocReference(self._collection, doc_id), data)


def _deep_merge(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


class _Collection:
    def __init__(self):
        self._docs = {}

    def document(self, doc_id):
        return _DocReference(self, doc_id)

    def where(self, field, op, expected):
        assert op == '=='
        return _Query(self, field, expected)


class _DB:
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        self._collections.setdefault(name, _Collection())
        return self._collections[name]

    def transaction(self):
        return _Transaction()


class _Transaction:
    def update(self, ref, data):
        ref.update(data)

    def set(self, ref, data, merge=False):
        ref.set(data, merge=merge)


@pytest.fixture(scope="module", autouse=True)
def _mcp_oauth_module():
    """Load ``database.mcp_oauth`` fresh against a stubbed firestore chain.

    ``database.mcp_oauth`` decorates its transaction helpers with
    ``@firestore.transactional`` at import time. The real decorator requires a
    live Firestore ``Transaction`` object (it reads ``_read_only`` /
    ``_max_attempts`` and calls ``_commit``), which is incompatible with the
    in-memory ``_Transaction`` these tests use. We therefore stub
    ``google.cloud.firestore`` with an identity ``transactional`` and re-exec the
    module via ``load_module_fresh`` so the decorator is a no-op, then swap ``db``
    for the in-memory ``_DB``. The freshly loaded module is published as the
    ``mcp_oauth`` global so the existing test bodies resolve to it unchanged. See
    ``backend/docs/test_isolation.md`` (reserve ``stub_modules`` finder case).
    """
    google_pkg = ModuleType("google")
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []  # type: ignore[attr-defined]
    firestore_stub = ModuleType("google.cloud.firestore")
    firestore_stub.transactional = lambda fn: fn

    fakes = {
        "google": google_pkg,
        "google.cloud": google_cloud_pkg,
        "google.cloud.firestore": firestore_stub,
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "database.mcp_oauth",
            os.path.join(str(_BACKEND), "database", "mcp_oauth.py"),
        )
        module.db = _DB()
        globals()["mcp_oauth"] = module
        yield module


def test_authorization_code_exchange_issues_scoped_tokens_and_rejects_reuse():
    client = mcp_oauth.get_client('omi-chatgpt-prod')
    assert client['token_endpoint_auth_method'] == 'none'
    assert mcp_oauth.verify_client_auth(client, None)
    assert not mcp_oauth.verify_client_auth(client, 'client-secret')
    assert mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector_platform_oauth_redirect')

    scopes = mcp_oauth.normalize_scopes('memories.read conversations.read', client)
    verifier = 'a' * 64
    grant = mcp_oauth.create_or_update_grant('user-1', 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, scopes)
    code = mcp_oauth.issue_authorization_code(
        'user-1',
        grant['id'],
        'omi-chatgpt-prod',
        'https://chatgpt.com/connector_platform_oauth_redirect',
        mcp_oauth.MCP_RESOURCE_URL,
        scopes,
        mcp_oauth.pkce_s256(verifier),
    )

    token_pair = mcp_oauth.exchange_authorization_code_for_tokens(
        code,
        'omi-chatgpt-prod',
        'https://chatgpt.com/connector_platform_oauth_redirect',
        mcp_oauth.MCP_RESOURCE_URL,
        verifier,
    )
    assert token_pair['access_token'].startswith('omi_oat_')
    assert (
        mcp_oauth.exchange_authorization_code_for_tokens(
            code,
            'omi-chatgpt-prod',
            'https://chatgpt.com/connector_platform_oauth_redirect',
            mcp_oauth.MCP_RESOURCE_URL,
            verifier,
        )
        is None
    )

    auth_context = mcp_oauth.validate_access_token(token_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL)
    assert auth_context['uid'] == 'user-1'
    assert auth_context['scopes'] == ['conversations.read', 'memories.read']


def test_consent_transaction_creates_grant_and_code_together():
    uid = 'atomic-consent-user'
    scopes = ['memories.read']

    grant, code = mcp_oauth.create_grant_and_authorization_code_if_allowed(
        uid,
        'omi-chatgpt-prod',
        'https://chatgpt.com/connector_platform_oauth_redirect',
        mcp_oauth.MCP_RESOURCE_URL,
        scopes,
        mcp_oauth.pkce_s256('c' * 64),
    )

    assert grant['uid'] == uid
    code_doc = mcp_oauth.db.collection('mcp_oauth_authorization_codes').document(mcp_oauth.hash_secret(code)).get()
    assert code_doc.to_dict()['grant_id'] == grant['id']

    memory_grant_doc = (
        mcp_oauth.db.collection(f'users/{uid}/memory_control').document('app_key_memory_grants').get().to_dict()
    )
    memory_grant = memory_grant_doc['grants']['mcp']['apps']['omi-chatgpt-prod']['keys'][grant['id']]
    assert memory_grant == {
        'enabled': True,
        'scopes': ['memories.read'],
        'default_read': True,
        'archive_read': False,
        'write': False,
    }

    authorization = authorize_memory_external_default_memory_read(
        build_mcp_default_memory_read_context(
            McpVerifiedAuth(
                uid=uid,
                app_id='omi-chatgpt-prod',
                key_id=grant['id'],
                scopes=tuple(scopes),
            )
        ),
        db_client=mcp_oauth.db,
    )
    assert authorization.allowed is True


def test_access_token_validation_backfills_memory_grant_for_existing_oauth_consent():
    uid = 'existing-oauth-user'
    scopes = ['memories.read', 'memories.write']
    grant = mcp_oauth.create_or_update_grant(uid, 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, scopes)
    token_pair = mcp_oauth.issue_token_pair(grant, scopes=scopes)

    memory_grant_ref = mcp_oauth.db.collection(f'users/{uid}/memory_control').document('app_key_memory_grants')
    memory_grant_ref.set(
        {
            'grants': {
                'mcp': {
                    'apps': {
                        'other-client': {
                            'keys': {
                                'other-grant': {
                                    'enabled': False,
                                    'scopes': [],
                                    'default_read': False,
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

    auth_context = mcp_oauth.validate_access_token(token_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL)

    assert auth_context['grant_id'] == grant['id']
    memory_grants = memory_grant_ref.get().to_dict()['grants']['mcp']['apps']
    repaired = memory_grants['omi-chatgpt-prod']['keys'][grant['id']]
    assert repaired == {
        'enabled': True,
        'scopes': ['memories.read', 'memories.write'],
        'default_read': True,
        'archive_read': False,
        'write': True,
    }
    assert memory_grants['other-client']['keys']['other-grant']['enabled'] is False


@pytest.mark.parametrize(
    ('stored_entry', 'expected_reason'),
    [
        (
            {
                'enabled': False,
                'scopes': ['memories.read'],
                'default_read': True,
                'archive_read': False,
                'write': False,
            },
            'app_key_scope_grant_disabled',
        ),
        (
            {
                'enabled': True,
                'scopes': [],
                'default_read': False,
                'archive_read': False,
                'write': False,
            },
            'missing_persisted_scope_memories.read',
        ),
        ({'enabled': 'invalid'}, 'malformed_app_key_scope_grant'),
    ],
    ids=['disabled', 'narrowed', 'malformed'],
)
def test_access_token_backfill_never_overwrites_existing_memory_control_state(stored_entry, expected_reason):
    uid = f"controlled-oauth-{expected_reason}"
    grant = mcp_oauth.create_or_update_grant(uid, 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, ['memories.read'])
    token_pair = mcp_oauth.issue_token_pair(grant, scopes=['memories.read'])
    memory_grant_ref = mcp_oauth.db.collection(f'users/{uid}/memory_control').document('app_key_memory_grants')
    state = memory_grant_ref.get().to_dict()
    state['grants']['mcp']['apps']['omi-chatgpt-prod']['keys'][grant['id']] = stored_entry
    memory_grant_ref.set(state)

    auth_context = mcp_oauth.validate_access_token(token_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL)

    assert auth_context is not None
    persisted = memory_grant_ref.get().to_dict()
    assert persisted['grants']['mcp']['apps']['omi-chatgpt-prod']['keys'][grant['id']] == stored_entry
    authorization = authorize_memory_external_default_memory_read(
        build_mcp_default_memory_read_context(
            McpVerifiedAuth(
                uid=uid,
                app_id='omi-chatgpt-prod',
                key_id=grant['id'],
                scopes=('memories.read',),
            )
        ),
        db_client=mcp_oauth.db,
    )
    assert authorization.allowed is False
    assert authorization.reason == expected_reason


def test_access_token_backfill_does_not_repair_a_malformed_memory_control_parent():
    uid = 'malformed-memory-control-parent'
    grant = mcp_oauth.create_or_update_grant(uid, 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, ['memories.read'])
    token_pair = mcp_oauth.issue_token_pair(grant, scopes=['memories.read'])
    memory_grant_ref = mcp_oauth.db.collection(f'users/{uid}/memory_control').document('app_key_memory_grants')
    memory_grant_ref.set({'grants': 'malformed'})

    assert mcp_oauth.validate_access_token(token_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL) is not None
    assert memory_grant_ref.get().to_dict() == {'grants': 'malformed'}


def test_reconsent_does_not_reenable_a_disabled_memory_control_grant():
    uid = 'disabled-oauth-reconsent-user'
    scopes = ['memories.read']
    grant, _ = mcp_oauth.create_grant_and_authorization_code_if_allowed(
        uid,
        'omi-chatgpt-prod',
        'https://chatgpt.com/connector_platform_oauth_redirect',
        mcp_oauth.MCP_RESOURCE_URL,
        scopes,
        mcp_oauth.pkce_s256('r' * 64),
    )
    memory_grant_ref = mcp_oauth.db.collection(f'users/{uid}/memory_control').document('app_key_memory_grants')
    state = memory_grant_ref.get().to_dict()
    stored_grant = state['grants']['mcp']['apps']['omi-chatgpt-prod']['keys'][grant['id']]
    stored_grant['enabled'] = False
    memory_grant_ref.set(state)

    renewed_grant, _ = mcp_oauth.create_grant_and_authorization_code_if_allowed(
        uid,
        'omi-chatgpt-prod',
        'https://chatgpt.com/connector_platform_oauth_redirect',
        mcp_oauth.MCP_RESOURCE_URL,
        scopes,
        mcp_oauth.pkce_s256('s' * 64),
    )

    assert renewed_grant['id'] == grant['id']
    persisted = memory_grant_ref.get().to_dict()['grants']['mcp']['apps']['omi-chatgpt-prod']['keys'][grant['id']]
    assert persisted['enabled'] is False


_MISSING = object()


@pytest.mark.parametrize(
    ('record', 'field', 'value'),
    [
        ('token', 'uid', _MISSING),
        ('token', 'uid', ''),
        ('token', 'client_id', _MISSING),
        ('token', 'client_id', 7),
        ('token', 'grant_id', _MISSING),
        ('token', 'grant_id', ''),
        ('token', 'resource', _MISSING),
        ('token', 'resource', 'https://attacker.example/mcp'),
        ('token', 'scopes', _MISSING),
        ('token', 'scopes', 'memories.read'),
        ('token', 'scopes', []),
        ('token', 'scopes', ['memories.read', 'memories.read']),
        ('token', 'scopes', ['memories.archive.read']),
        ('token', 'expires_at', _MISSING),
        ('token', 'expires_at', 'expired'),
        ('token', 'revoked_at', 'revoked'),
        ('grant', '__document__', _MISSING),
        ('grant', 'uid', _MISSING),
        ('grant', 'uid', 'other-user'),
        ('grant', 'client_id', _MISSING),
        ('grant', 'client_id', 'other-client'),
        ('grant', 'id', _MISSING),
        ('grant', 'id', 'other-grant'),
        ('grant', 'resource', _MISSING),
        ('grant', 'resource', 'https://other.example/mcp'),
        ('grant', 'scopes', _MISSING),
        ('grant', 'scopes', []),
        ('grant', 'scopes', ['conversations.read']),
        ('grant', 'status', 'revoked'),
        ('grant', 'revoked_at', 'revoked'),
        ('grant', 'expires_at', 'expired'),
    ],
)
def test_access_token_validation_rejects_malformed_or_mismatched_token_grant_pairs(record, field, value):
    uid = f'strict-token-{record}-{field}-{abs(hash(repr(value)))}'
    grant = mcp_oauth.create_or_update_grant(uid, 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, ['memories.read'])
    token_pair = mcp_oauth.issue_token_pair(grant, scopes=['memories.read'])
    token_ref = mcp_oauth.db.collection('mcp_oauth_access_tokens').document(
        mcp_oauth.hash_secret(token_pair['access_token'])
    )
    grant_ref = mcp_oauth.db.collection('mcp_oauth_grants').document(grant['id'])
    target_ref = token_ref if record == 'token' else grant_ref

    if field == '__document__':
        target_ref.delete()
    else:
        target = target_ref.get().to_dict()
        if value is _MISSING:
            target.pop(field, None)
        elif value == 'expired':
            target[field] = mcp_oauth._now() - timedelta(seconds=1)
        elif value == 'revoked':
            target[field] = mcp_oauth._now()
        else:
            target[field] = value
        target_ref.set(target)

    assert mcp_oauth.validate_access_token(token_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL) is None
    token_ref.delete()
    grant_ref.delete()
    mcp_oauth.db.collection(f'users/{uid}/memory_control').document('app_key_memory_grants').delete()


def test_oauth_memory_grant_never_carries_archive_capability():
    uid = 'oauth-no-archive-user'
    scopes = ['memories.read', 'memories.write']
    grant = mcp_oauth.create_or_update_grant(uid, 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, scopes)
    token_pair = mcp_oauth.issue_token_pair(grant, scopes=scopes)

    auth_context = mcp_oauth.validate_access_token(token_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL)
    persisted = (
        mcp_oauth.db.collection(f'users/{uid}/memory_control')
        .document('app_key_memory_grants')
        .get()
        .to_dict()['grants']['mcp']['apps']['omi-chatgpt-prod']['keys'][grant['id']]
    )

    assert auth_context is not None
    assert auth_context['scopes'] == scopes
    assert persisted['archive_read'] is False
    authorization = authorize_memory_external_default_memory_read(
        build_mcp_default_memory_read_context(
            McpVerifiedAuth(
                uid=uid,
                app_id='omi-chatgpt-prod',
                key_id=grant['id'],
                scopes=tuple(auth_context['scopes']),
            )
        ),
        db_client=mcp_oauth.db,
    )
    assert authorization.allowed is True
    assert authorization.policy.archive_capability is False


def test_consent_transaction_rejects_deletion_marker_without_oauth_writes():
    uid = 'deleting-consent-user'
    mcp_oauth.db.collection('account_deletions').document(uid).set({'wipe_status': 'pending'})

    with pytest.raises(mcp_oauth.AccountDeletionAccessBlocked):
        mcp_oauth.create_grant_and_authorization_code_if_allowed(
            uid,
            'omi-chatgpt-prod',
            'https://chatgpt.com/connector_platform_oauth_redirect',
            mcp_oauth.MCP_RESOURCE_URL,
            ['memories.read'],
            mcp_oauth.pkce_s256('d' * 64),
        )

    assert all(doc['uid'] != uid for doc in mcp_oauth.db.collection('mcp_oauth_grants')._docs.values())
    assert all(doc['uid'] != uid for doc in mcp_oauth.db.collection('mcp_oauth_authorization_codes')._docs.values())


def test_public_client_uses_pkce_without_shared_secret():
    client = mcp_oauth.get_client('omi-mcp-public')
    assert client['token_endpoint_auth_method'] == 'none'
    assert mcp_oauth.verify_client_auth(client, None)
    assert not mcp_oauth.verify_client_auth(client, 'unexpected-secret')
    assert mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector_platform_oauth_redirect')

    scopes = mcp_oauth.normalize_scopes('memories.read', client)
    verifier = 'b' * 64
    grant = mcp_oauth.create_or_update_grant('user-public', 'omi-mcp-public', mcp_oauth.MCP_RESOURCE_URL, scopes)
    code = mcp_oauth.issue_authorization_code(
        'user-public',
        grant['id'],
        'omi-mcp-public',
        'https://chatgpt.com/connector_platform_oauth_redirect',
        mcp_oauth.MCP_RESOURCE_URL,
        scopes,
        mcp_oauth.pkce_s256(verifier),
    )

    token_pair = mcp_oauth.exchange_authorization_code_for_tokens(
        code,
        'omi-mcp-public',
        'https://chatgpt.com/connector_platform_oauth_redirect',
        mcp_oauth.MCP_RESOURCE_URL,
        verifier,
    )
    assert token_pair['access_token'].startswith('omi_oat_')
    assert (
        mcp_oauth.validate_access_token(token_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL)['uid'] == 'user-public'
    )


def test_delete_user_oauth_credentials_removes_unconsumed_authorization_codes():
    grant = mcp_oauth.create_or_update_grant(
        'deleted-user', 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, ['memories.read']
    )
    mcp_oauth.issue_authorization_code(
        'deleted-user',
        grant['id'],
        'omi-chatgpt-prod',
        'https://chatgpt.com/connector_platform_oauth_redirect',
        mcp_oauth.MCP_RESOURCE_URL,
        ['memories.read'],
        mcp_oauth.pkce_s256('d' * 64),
    )
    mcp_oauth.issue_authorization_code(
        'other-user',
        'other-grant',
        'omi-chatgpt-prod',
        'https://chatgpt.com/connector_platform_oauth_redirect',
        mcp_oauth.MCP_RESOURCE_URL,
        ['memories.read'],
        mcp_oauth.pkce_s256('e' * 64),
    )

    mcp_oauth.delete_user_oauth_credentials('deleted-user')

    codes = mcp_oauth.db.collection('mcp_oauth_authorization_codes')._docs
    assert all(code['uid'] != 'deleted-user' for code in codes.values())
    assert any(code['uid'] == 'other-user' for code in codes.values())


def test_chatgpt_prod_client_uses_public_pkce_exchange(monkeypatch):
    redirect_uri = 'https://chatgpt.com/connector/oauth/omi-review-smoke/callback'
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_CLIENT_ID', 'omi-chatgpt-prod')
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_CLIENT_SECRET', 'configured-but-not-sent-by-chatgpt')
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_REDIRECT_URIS', 'https://chatgpt.com/connector_platform_oauth_redirect')
    monkeypatch.delenv('MCP_OAUTH_CHATGPT_TOKEN_AUTH_METHOD', raising=False)
    monkeypatch.setattr(mcp_oauth, 'DEFAULT_CLIENT_ID', 'omi-chatgpt-prod')

    client = mcp_oauth.get_client('omi-chatgpt-prod')
    assert client['token_endpoint_auth_method'] == 'none'
    assert mcp_oauth.verify_client_auth(client, None)
    assert not mcp_oauth.verify_client_auth(client, 'unexpected-secret')
    assert mcp_oauth.validate_redirect_uri(client, redirect_uri)

    scopes = mcp_oauth.normalize_scopes(
        (
            'memories.read memories.write conversations.read action_items.read action_items.write '
            'goals.read chat.read screen_activity.read people.read'
        ),
        client,
    )
    verifier = 'c' * 64
    grant = mcp_oauth.create_or_update_grant('chatgpt-reviewer', 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, scopes)
    code = mcp_oauth.issue_authorization_code(
        'chatgpt-reviewer',
        grant['id'],
        'omi-chatgpt-prod',
        redirect_uri,
        mcp_oauth.MCP_RESOURCE_URL,
        scopes,
        mcp_oauth.pkce_s256(verifier),
    )

    token_pair = mcp_oauth.exchange_authorization_code_for_tokens(
        code, 'omi-chatgpt-prod', redirect_uri, mcp_oauth.MCP_RESOURCE_URL, verifier
    )
    assert token_pair['access_token'].startswith('omi_oat_')
    assert token_pair['scope'] == ' '.join(scopes)


def test_chatgpt_dev_client_uses_public_pkce_exchange(monkeypatch):
    redirect_uri = 'https://chatgpt.com/connector/oauth/dev-test'
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_CLIENT_ID', 'omi')
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_CLIENT_SECRET', 'legacy-dev-secret')
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_REDIRECT_URIS', redirect_uri)
    monkeypatch.delenv('MCP_OAUTH_PUBLIC_REDIRECT_URIS', raising=False)
    monkeypatch.delenv('MCP_OAUTH_CHATGPT_TOKEN_AUTH_METHOD', raising=False)
    monkeypatch.setattr(mcp_oauth, 'DEFAULT_CLIENT_ID', 'omi')

    client = mcp_oauth.get_client('omi-chatgpt-dev')
    assert client is not None
    assert client['token_endpoint_auth_method'] == 'none'
    assert mcp_oauth.verify_client_auth(client, None)
    assert not mcp_oauth.verify_client_auth(client, 'unexpected-secret')
    assert mcp_oauth.validate_redirect_uri(client, redirect_uri)


def test_chatgpt_prod_client_is_registered_without_legacy_env_override():
    client = mcp_oauth.get_client('omi-chatgpt-prod')

    assert client['id'] == 'omi-chatgpt-prod'
    assert client['token_endpoint_auth_method'] == 'none'
    assert mcp_oauth.verify_client_auth(client, None)
    assert mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector_platform_oauth_redirect')
    assert mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/omi-review-smoke/callback')


def test_chatgpt_prod_redirect_prefix_rejects_bypass_attempts(monkeypatch):
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_CLIENT_ID', 'omi-chatgpt-prod')
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_REDIRECT_URIS', 'https://chatgpt.com/connector_platform_oauth_redirect')
    monkeypatch.delenv('MCP_OAUTH_CHATGPT_TOKEN_AUTH_METHOD', raising=False)
    monkeypatch.setattr(mcp_oauth, 'DEFAULT_CLIENT_ID', 'omi-chatgpt-prod')

    client = mcp_oauth.get_client('omi-chatgpt-prod')
    assert mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/omi-review-smoke/callback')
    assert not mcp_oauth.validate_redirect_uri(
        client, 'https://chatgpt.com/connector/oauth/omi-review-smoke/callback?next=x'
    )
    assert not mcp_oauth.validate_redirect_uri(
        client, 'https://chatgpt.com/connector/oauth/omi-review-smoke/callback#token'
    )
    assert not mcp_oauth.validate_redirect_uri(client, 'http://chatgpt.com/connector/oauth/omi-review-smoke/callback')
    assert not mcp_oauth.validate_redirect_uri(
        client, 'https://chatgpt.com.evil.test/connector/oauth/omi-review-smoke/callback'
    )
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauthish/omi-review-smoke')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/./callback')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/../callback')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/%2e%2e/callback')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/%2F/callback')


def test_chatgpt_prod_configured_client_keeps_dynamic_connector_callback_prefix():
    collection = mcp_oauth.db.collection('mcp_oauth_clients')
    original_docs = dict(collection._docs)
    try:
        collection.document('omi-chatgpt-prod').set(
            {
                'id': 'omi-chatgpt-prod',
                'name': 'ChatGPT',
                'allowed_redirect_uris': ['https://chatgpt.com/connector/oauth/OUbdUMlL15Ct'],
                'allowed_resources': [mcp_oauth.MCP_RESOURCE_URL],
                'allowed_scopes': mcp_oauth.SUPPORTED_SCOPES,
                'token_endpoint_auth_method': 'none',
                'client_secret_hash': '',
            }
        )

        client = mcp_oauth.get_client('omi-chatgpt-prod')

        assert mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/new-custom-app-id')
        assert mcp_oauth.validate_resource(client, mcp_oauth.MCP_RESOURCE_URL)
        assert mcp_oauth.validate_resource(client, mcp_oauth.BETA_MCP_RESOURCE_URL)
        assert not mcp_oauth.validate_resource(client, 'https://attacker.example/v1/mcp/sse')
        assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/new-custom-app-id?x=1')
        assert not mcp_oauth.validate_redirect_uri(
            client, 'https://chatgpt.com.evil.test/connector/oauth/new-custom-app-id'
        )
    finally:
        collection._docs = original_docs


def test_claude_prod_client_is_registered_for_cloud_connector_callback():
    client = mcp_oauth.get_client('omi-claude-prod')

    assert client['id'] == 'omi-claude-prod'
    assert client['token_endpoint_auth_method'] == 'none'
    assert mcp_oauth.verify_client_auth(client, None)
    assert not mcp_oauth.verify_client_auth(client, 'unexpected-secret')
    assert mcp_oauth.validate_resource(client, mcp_oauth.BETA_MCP_RESOURCE_URL)
    assert mcp_oauth.validate_redirect_uri(client, 'https://claude.ai/api/mcp/auth_callback')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://claude.ai/api/mcp/auth_callback?next=x')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://example.com/api/mcp/auth_callback')


def test_chatgpt_token_auth_method_env_can_force_confidential_client(monkeypatch):
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_CLIENT_ID', 'omi-chatgpt-prod')
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_CLIENT_SECRET', 'client-secret')
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_TOKEN_AUTH_METHOD', 'client_secret_post')
    monkeypatch.setattr(mcp_oauth, 'DEFAULT_CLIENT_ID', 'omi-chatgpt-prod')

    client = mcp_oauth.get_client('omi-chatgpt-prod')
    assert client['token_endpoint_auth_method'] == 'client_secret_post'
    assert mcp_oauth.verify_client_auth(client, 'client-secret')
    assert not mcp_oauth.verify_client_auth(client, None)


def test_public_client_rejects_unregistered_redirect_uri():
    client = mcp_oauth.get_client('omi-mcp-public')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://example.com/oauth/callback')


def test_public_client_refresh_token_rotates_without_shared_secret():
    client = mcp_oauth.get_client('omi-mcp-public')
    assert mcp_oauth.verify_client_auth(client, None)

    scopes = ['memories.read']
    grant = mcp_oauth.create_or_update_grant(
        'user-public-refresh', 'omi-mcp-public', mcp_oauth.MCP_RESOURCE_URL, scopes
    )
    first_pair = mcp_oauth.issue_token_pair(grant, scopes=scopes)

    second_pair = mcp_oauth.rotate_refresh_token(
        first_pair['refresh_token'], 'omi-mcp-public', mcp_oauth.MCP_RESOURCE_URL
    )
    assert second_pair['refresh_token'] != first_pair['refresh_token']
    assert (
        mcp_oauth.rotate_refresh_token(first_pair['refresh_token'], 'other-client', mcp_oauth.MCP_RESOURCE_URL) is None
    )


def test_generic_env_client_registry_supports_additional_connectors(monkeypatch):
    monkeypatch.setenv(
        'MCP_OAUTH_CLIENTS_JSON',
        json.dumps(
            [
                {
                    'client_id': 'claude-test',
                    'client_type': 'public',
                    'redirect_uris': ['https://claude.ai/api/mcp/auth_callback'],
                    'scopes': ['memories.read'],
                }
            ]
        ),
    )

    client = mcp_oauth.get_client('claude-test')
    assert client['token_endpoint_auth_method'] == 'none'
    assert client['allowed_scopes'] == ['memories.read']
    assert mcp_oauth.validate_redirect_uri(client, 'https://claude.ai/api/mcp/auth_callback')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector_platform_oauth_redirect')


def test_generic_env_client_registry_supports_redirect_uri_prefixes(monkeypatch):
    monkeypatch.setenv(
        'MCP_OAUTH_CLIENTS_JSON',
        json.dumps(
            [
                {
                    'client_id': 'connector-prefix-test',
                    'client_type': 'public',
                    'redirect_uri_prefixes': ['https://chatgpt.com/connector/oauth/'],
                    'scopes': ['memories.read'],
                }
            ]
        ),
    )

    client = mcp_oauth.get_client('connector-prefix-test')
    assert mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/user-connector')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/user-connector?code=1')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth//user-connector')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/../evil')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/%2e%2e/evil')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/%2F/evil')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauthish/user-connector')


def test_generic_env_client_rejects_string_public_flag(monkeypatch):
    monkeypatch.setenv(
        'MCP_OAUTH_CLIENTS_JSON',
        json.dumps(
            [
                {
                    'client_id': 'misconfigured-public',
                    'public': 'false',
                    'redirect_uris': ['https://example.com/callback'],
                }
            ]
        ),
    )

    assert mcp_oauth.get_client('misconfigured-public') is None


def test_default_clients_can_request_all_supported_tool_scopes():
    requested_scopes = ' '.join(
        [
            'memories.read',
            'memories.write',
            'conversations.read',
            'action_items.read',
            'action_items.write',
            'goals.read',
            'chat.read',
            'screen_activity.read',
            'people.read',
        ]
    )

    assert mcp_oauth.normalize_scopes(requested_scopes, mcp_oauth.get_client('omi-chatgpt-prod')) == sorted(
        requested_scopes.split()
    )
    assert mcp_oauth.normalize_scopes(requested_scopes, mcp_oauth.get_client('omi-mcp-public')) == sorted(
        requested_scopes.split()
    )


def test_legacy_omi_client_id_is_not_registered_by_default():
    assert mcp_oauth.get_client('omi') is None


def test_refresh_token_rotates_and_old_refresh_reuse_revokes_grant():
    scopes = ['memories.read']
    grant = mcp_oauth.create_or_update_grant('user-2', 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, scopes)
    first_pair = mcp_oauth.issue_token_pair(grant, scopes=scopes)

    second_pair = mcp_oauth.rotate_refresh_token(
        first_pair['refresh_token'], 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL
    )
    assert second_pair['refresh_token'] != first_pair['refresh_token']
    assert mcp_oauth.validate_access_token(second_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL)['uid'] == 'user-2'

    assert (
        mcp_oauth.rotate_refresh_token(first_pair['refresh_token'], 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL)
        is None
    )
    assert mcp_oauth.validate_access_token(second_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL) is None

    new_grant = mcp_oauth.create_or_update_grant('user-2', 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, scopes)
    assert new_grant['id'] != grant['id']
    assert (
        mcp_oauth.rotate_refresh_token(second_pair['refresh_token'], 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL)
        is None
    )


def test_revoke_user_grant_invalidates_tokens():
    scopes = ['memories.read']
    grant = mcp_oauth.create_or_update_grant('user-3', 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, scopes)
    token_pair = mcp_oauth.issue_token_pair(grant, scopes=scopes)

    assert len(mcp_oauth.list_user_grants('user-3')) == 1
    assert mcp_oauth.revoke_user_grant('other-user', grant['id']) is False
    assert mcp_oauth.revoke_user_grant('user-3', grant['id']) is True
    assert mcp_oauth.validate_access_token(token_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL) is None


def test_pkce_rejects_malformed_values():
    assert not mcp_oauth.validate_pkce_challenge('short', 'S256')
    assert not mcp_oauth.validate_pkce_challenge('a' * 43, 'plain')
    try:
        mcp_oauth.pkce_s256('ümlaut')
    except ValueError:
        pass
    else:
        raise AssertionError('non-ASCII verifier should fail closed')


def test_authorization_code_exchange_with_omitted_resource_keeps_stored_audience():
    """RFC 8707 (https://datatracker.ietf.org/doc/html/rfc8707#section-2): the
    resource indicator is optional; when the token request omits it, the code's
    stored audience stays bound — while a wrong explicit value still fails."""
    client = mcp_oauth.get_client('omi-chatgpt-prod')
    scopes = mcp_oauth.normalize_scopes('memories.read', client)
    verifier = 'b' * 64
    grant = mcp_oauth.create_or_update_grant('user-omit', 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, scopes)

    def issue_code():
        return mcp_oauth.issue_authorization_code(
            'user-omit',
            grant['id'],
            'omi-chatgpt-prod',
            'https://chatgpt.com/connector_platform_oauth_redirect',
            mcp_oauth.MCP_RESOURCE_URL,
            scopes,
            mcp_oauth.pkce_s256(verifier),
        )

    assert (
        mcp_oauth.exchange_authorization_code_for_tokens(
            issue_code(),
            'omi-chatgpt-prod',
            'https://chatgpt.com/connector_platform_oauth_redirect',
            'https://wrong.example/v1/mcp/sse',
            verifier,
        )
        is None
    )

    token_pair = mcp_oauth.exchange_authorization_code_for_tokens(
        issue_code(),
        'omi-chatgpt-prod',
        'https://chatgpt.com/connector_platform_oauth_redirect',
        None,
        verifier,
    )
    auth_context = mcp_oauth.validate_access_token(token_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL)
    assert auth_context['uid'] == 'user-omit'


def test_refresh_rotation_with_omitted_resource_keeps_stored_audience():
    scopes = ['memories.read']
    grant = mcp_oauth.create_or_update_grant(
        'user-omit-refresh', 'omi-chatgpt-prod', mcp_oauth.MCP_RESOURCE_URL, scopes
    )
    token_pair = mcp_oauth.issue_token_pair(grant, scopes=scopes)

    assert (
        mcp_oauth.rotate_refresh_token(
            token_pair['refresh_token'], 'omi-chatgpt-prod', 'https://wrong.example/v1/mcp/sse'
        )
        is None
    )

    rotated = mcp_oauth.rotate_refresh_token(token_pair['refresh_token'], 'omi-chatgpt-prod', None)
    auth_context = mcp_oauth.validate_access_token(rotated['access_token'], mcp_oauth.MCP_RESOURCE_URL)
    assert auth_context['uid'] == 'user-omit-refresh'
