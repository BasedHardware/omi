import json
import os
import sys
from types import ModuleType
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ['MCP_OAUTH_CHATGPT_CLIENT_SECRET'] = 'client-secret'
os.environ['MCP_OAUTH_CHATGPT_REDIRECT_URIS'] = 'https://chatgpt.com/connector_platform_oauth_redirect'
os.environ['MCP_OAUTH_PUBLIC_REDIRECT_URIS'] = 'https://chatgpt.com/connector_platform_oauth_redirect'


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


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
            self._collection._docs[self.id].update(data)
        else:
            self._collection._docs[self.id] = dict(data)

    def update(self, data):
        self._collection._docs.setdefault(self.id, {}).update(data)


class _Query:
    def __init__(self, collection, field, expected):
        self._collection = collection
        self._field = field
        self._expected = expected

    def stream(self):
        for doc_id, data in self._collection._docs.items():
            if data.get(self._field) == self._expected:
                yield _DocSnapshot(_DocReference(self._collection, doc_id), data)


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


sys.modules['google'] = _AutoMockModule('google')
google_cloud = _AutoMockModule('google.cloud')
firestore_module = _AutoMockModule('google.cloud.firestore')
firestore_module.transactional = lambda fn: fn
google_cloud.firestore = firestore_module
sys.modules['google.cloud'] = google_cloud
sys.modules['google.cloud.firestore'] = firestore_module
database_client = ModuleType('database._client')
database_client.db = _DB()
sys.modules['database._client'] = database_client

from database import mcp_oauth


def test_authorization_code_exchange_issues_scoped_tokens_and_rejects_reuse():
    client = mcp_oauth.get_client('omi')
    assert mcp_oauth.verify_client_secret(client, 'client-secret')
    assert mcp_oauth.verify_client_auth(client, 'client-secret')
    assert mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector_platform_oauth_redirect')

    scopes = mcp_oauth.normalize_scopes('memories.read conversations.read', client)
    verifier = 'a' * 64
    grant = mcp_oauth.create_or_update_grant('user-1', 'omi', mcp_oauth.MCP_RESOURCE_URL, scopes)
    code = mcp_oauth.issue_authorization_code(
        'user-1',
        grant['id'],
        'omi',
        'https://chatgpt.com/connector_platform_oauth_redirect',
        mcp_oauth.MCP_RESOURCE_URL,
        scopes,
        mcp_oauth.pkce_s256(verifier),
    )

    token_pair = mcp_oauth.exchange_authorization_code_for_tokens(
        code, 'omi', 'https://chatgpt.com/connector_platform_oauth_redirect', mcp_oauth.MCP_RESOURCE_URL, verifier
    )
    assert token_pair['access_token'].startswith('omi_oat_')
    assert (
        mcp_oauth.exchange_authorization_code_for_tokens(
            code, 'omi', 'https://chatgpt.com/connector_platform_oauth_redirect', mcp_oauth.MCP_RESOURCE_URL, verifier
        )
        is None
    )

    auth_context = mcp_oauth.validate_access_token(token_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL)
    assert auth_context['uid'] == 'user-1'
    assert auth_context['scopes'] == ['conversations.read', 'memories.read']


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


def test_chatgpt_prod_client_uses_public_pkce_exchange(monkeypatch):
    redirect_uri = 'https://chatgpt.com/connector/oauth/OUbdUMlL15Ct'
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_CLIENT_ID', 'omi-chatgpt-prod')
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_CLIENT_SECRET', 'configured-but-not-sent-by-chatgpt')
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_REDIRECT_URIS', redirect_uri)
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


def test_chatgpt_dynamic_connector_redirect_prefix_is_constrained(monkeypatch):
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_CLIENT_ID', 'omi-chatgpt-prod')
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_REDIRECT_URIS', 'https://chatgpt.com/connector_platform_oauth_redirect')
    monkeypatch.delenv('MCP_OAUTH_CHATGPT_TOKEN_AUTH_METHOD', raising=False)
    monkeypatch.setattr(mcp_oauth, 'DEFAULT_CLIENT_ID', 'omi-chatgpt-prod')

    client = mcp_oauth.get_client('omi-chatgpt-prod')

    assert mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector_platform_oauth_redirect')
    assert mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/omi-review-smoke/callback')
    assert mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/OUbdUMlL15Ct')
    assert not mcp_oauth.validate_redirect_uri(
        client, 'https://chatgpt.com/connector/oauth/omi-review-smoke/callback?next=https://evil.test'
    )
    assert not mcp_oauth.validate_redirect_uri(
        client, 'https://chatgpt.com/connector/oauth/omi-review-smoke/callback#frag'
    )
    assert not mcp_oauth.validate_redirect_uri(client, 'http://chatgpt.com/connector/oauth/omi-review-smoke/callback')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://evil.test/connector/oauth/omi-review-smoke/callback')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth.evil/callback')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/../callback')
    assert not mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/%2e%2e/callback')


def test_chatgpt_dev_client_uses_public_pkce_exchange(monkeypatch):
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_CLIENT_ID', 'omi')
    monkeypatch.setenv('MCP_OAUTH_CHATGPT_REDIRECT_URIS', 'https://chatgpt.com/connector_platform_oauth_redirect')
    monkeypatch.delenv('MCP_OAUTH_CHATGPT_TOKEN_AUTH_METHOD', raising=False)
    monkeypatch.setattr(mcp_oauth, 'DEFAULT_CLIENT_ID', 'omi')

    client = mcp_oauth.get_client('omi-chatgpt-dev')

    assert client['id'] == 'omi-chatgpt-dev'
    assert client['token_endpoint_auth_method'] == 'none'
    assert mcp_oauth.verify_client_auth(client, None)
    assert not mcp_oauth.verify_client_auth(client, 'unexpected-secret')
    assert mcp_oauth.validate_redirect_uri(client, 'https://chatgpt.com/connector/oauth/dev-test/callback')


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

    assert mcp_oauth.normalize_scopes(requested_scopes, mcp_oauth.get_client('omi')) == sorted(requested_scopes.split())
    assert mcp_oauth.normalize_scopes(requested_scopes, mcp_oauth.get_client('omi-mcp-public')) == sorted(
        requested_scopes.split()
    )


def test_refresh_token_rotates_and_old_refresh_reuse_revokes_grant():
    scopes = ['memories.read']
    grant = mcp_oauth.create_or_update_grant('user-2', 'omi', mcp_oauth.MCP_RESOURCE_URL, scopes)
    first_pair = mcp_oauth.issue_token_pair(grant, scopes=scopes)

    second_pair = mcp_oauth.rotate_refresh_token(first_pair['refresh_token'], 'omi', mcp_oauth.MCP_RESOURCE_URL)
    assert second_pair['refresh_token'] != first_pair['refresh_token']
    assert mcp_oauth.validate_access_token(second_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL)['uid'] == 'user-2'

    assert mcp_oauth.rotate_refresh_token(first_pair['refresh_token'], 'omi', mcp_oauth.MCP_RESOURCE_URL) is None
    assert mcp_oauth.validate_access_token(second_pair['access_token'], mcp_oauth.MCP_RESOURCE_URL) is None

    new_grant = mcp_oauth.create_or_update_grant('user-2', 'omi', mcp_oauth.MCP_RESOURCE_URL, scopes)
    assert new_grant['id'] != grant['id']
    assert mcp_oauth.rotate_refresh_token(second_pair['refresh_token'], 'omi', mcp_oauth.MCP_RESOURCE_URL) is None


def test_revoke_user_grant_invalidates_tokens():
    scopes = ['memories.read']
    grant = mcp_oauth.create_or_update_grant('user-3', 'omi', mcp_oauth.MCP_RESOURCE_URL, scopes)
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
