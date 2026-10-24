"""Retrying an MCP connection must not reuse a consumed or expired authorization.

`add_mcp_server` returns an authorization URL whose state is single-use (GETDEL at the
callback) and expires after `MCP_OAUTH_STATE_EXPIRY_SECONDS`. A client retry that reopened
that URL could never recover. `authorize_mcp_server` issues a new state and PKCE pair for
the same registration (same app and OAuth client) and stores only the new verifier.
No live services: Redis, Firestore and provider discovery are in-memory fakes.
"""

import asyncio
import os
from urllib.parse import parse_qs, urlsplit

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from routers import apps as apps_router  # noqa: E402
from utils import mcp_client  # noqa: E402


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def setex(self, key, ttl, value):
        self.store[key] = value

    def getdel(self, key):
        return self.store.pop(key, None)


def _registered(uid='owner'):
    return {
        'id': 'app-1',
        'uid': uid,
        'status': 'pending_mcp_auth',
        'external_integration': {
            'mcp_server_url': 'https://mcp.example.test/mcp',
            'mcp_oauth_tokens': {
                'client_id': 'client-1',
                'client_secret': None,
                'token_endpoint': 'https://auth.example.test/token',
                'redirect_uri': 'https://api.example.test/v1/apps/mcp/callback',
                'code_verifier': 'original-verifier',
            },
        },
    }


@pytest.fixture
def route(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(mcp_client.redis_db, 'r', redis)
    state = {'app': _registered(), 'updates': [], 'cache_cleared': [], 'meta': {}}
    state['meta'] = {'authorization_endpoint': 'https://auth.example.test/authorize', 'scopes_supported': ['read']}

    async def _passthrough(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def _discover(_url):
        return state['meta']

    def _update(update):
        state['updates'].append(update)
        state['app'] = {**state['app'], **update}

    monkeypatch.setattr(apps_router, 'run_blocking', _passthrough)
    monkeypatch.setattr(apps_router, 'get_app_by_id_db', lambda _app_id: state['app'])
    monkeypatch.setattr(apps_router, 'discover_oauth_metadata', _discover)
    monkeypatch.setattr(apps_router, 'update_app_in_db', _update)
    monkeypatch.setattr(apps_router, 'delete_app_cache_by_id', lambda app_id: state['cache_cleared'].append(app_id))
    state['redis'] = redis
    return state


def _query(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_each_retry_gets_fresh_state_and_pkce_for_the_same_registration(route):
    first = asyncio.run(apps_router.authorize_mcp_server('app-1', uid='owner'))['auth_url']
    first_verifier = route['app']['external_integration']['mcp_oauth_tokens']['code_verifier']
    second = asyncio.run(apps_router.authorize_mcp_server('app-1', uid='owner'))['auth_url']
    second_verifier = route['app']['external_integration']['mcp_oauth_tokens']['code_verifier']

    q1, q2 = _query(first), _query(second)
    assert first.startswith('https://auth.example.test/authorize?') and second.startswith(
        'https://auth.example.test/authorize?'
    )
    assert q1['client_id'] == q2['client_id'] == 'client-1'
    assert q1['redirect_uri'] == 'https://api.example.test/v1/apps/mcp/callback'
    assert q1['state'] != q2['state'] and q1['code_challenge'] != q2['code_challenge']
    assert 'original-verifier' not in (first_verifier, second_verifier) and first_verifier != second_verifier
    # Each issued state is a single-use server record bound to this app and owner.
    assert mcp_client.consume_mcp_oauth_state(q2['state']) == ('app-1', 'owner')
    assert mcp_client.consume_mcp_oauth_state(q2['state']) is None
    # Registration identity is unchanged: same app, same OAuth client and endpoints.
    tokens = route['app']['external_integration']['mcp_oauth_tokens']
    assert tokens['client_id'] == 'client-1' and tokens['token_endpoint'] == 'https://auth.example.test/token'
    assert route['app']['external_integration']['mcp_server_url'] == 'https://mcp.example.test/mcp'
    assert route['cache_cleared'] == ['app-1', 'app-1']


def test_only_the_owner_can_reauthorize(route):
    with pytest.raises(HTTPException) as error:
        asyncio.run(apps_router.authorize_mcp_server('app-1', uid='someone-else'))
    assert error.value.status_code == 403
    assert route['updates'] == [] and route['redis'].store == {}


def test_a_server_without_oauth_registration_is_rejected(route):
    route['app'] = {**_registered(), 'external_integration': {'mcp_server_url': 'https://mcp.example.test/mcp'}}
    with pytest.raises(HTTPException) as error:
        asyncio.run(apps_router.authorize_mcp_server('app-1', uid='owner'))
    assert error.value.status_code == 422
    assert route['updates'] == [] and route['redis'].store == {}


def test_unavailable_provider_metadata_issues_no_state(route):
    route['meta'] = None
    with pytest.raises(HTTPException) as error:
        asyncio.run(apps_router.authorize_mcp_server('app-1', uid='owner'))
    assert error.value.status_code == 502
    assert route['updates'] == [] and route['redis'].store == {}
    assert route['app']['external_integration']['mcp_oauth_tokens']['code_verifier'] == 'original-verifier'
