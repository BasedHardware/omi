"""Retrying an MCP connection must not reuse a consumed or expired authorization.

`add_mcp_server` returns an authorization URL whose state is single-use (GETDEL at the
callback) and expires after `MCP_OAUTH_STATE_EXPIRY_SECONDS`. A client retry that reopened
that URL could never recover. `authorize_mcp_server` issues a new state and PKCE pair for
the same registration (same app and OAuth client) and stores only the new verifier.
No live services: Redis, Firestore and provider discovery are in-memory fakes.
"""

import asyncio
import copy
import os
from typing import Any
from urllib.parse import parse_qs, urlsplit

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from database import apps as apps_db  # noqa: E402
from routers import apps as apps_router  # noqa: E402
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore  # noqa: E402
from utils import mcp_client  # noqa: E402


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def setex(self, key, ttl, value):
        self.store[key] = value

    def getdel(self, key):
        return self.store.pop(key, None)


def _registered(uid='owner') -> dict[str, Any]:
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
    state: dict[str, Any] = {'app': _registered(), 'updates': [], 'cache_cleared': [], 'meta': {}}
    state['meta'] = {'authorization_endpoint': 'https://auth.example.test/authorize', 'scopes_supported': ['read']}

    async def _passthrough(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def _discover(_url):
        return state['meta']

    def _update(update):
        state['updates'].append(update)
        state['app'] = {**state['app'], **update}

    def _set_verifier(app_id, verifier):
        # Field-path semantics: only the nested verifier changes.
        state['updates'].append({'code_verifier': verifier})
        state['app']['external_integration']['mcp_oauth_tokens']['code_verifier'] = verifier

    def _complete(app_id, uid, tokens, server_url, tools):
        path = (apps_db.apps_collection, app_id)
        database = StrictFirestore({path: state['app']})
        committed = apps_db.complete_mcp_oauth_authorization(
            app_id, uid, tokens, server_url, tools, firestore_client=database
        )
        state['app'] = database.rows[path]
        return committed

    monkeypatch.setattr(apps_router, 'run_blocking', _passthrough)
    monkeypatch.setattr(apps_router, 'get_app_by_id_db', lambda _app_id: copy.deepcopy(state['app']))
    monkeypatch.setattr(apps_router, 'discover_oauth_metadata', _discover)
    monkeypatch.setattr(apps_router, 'update_app_in_db', _update)
    monkeypatch.setattr(apps_router, 'set_mcp_code_verifier', _set_verifier)
    monkeypatch.setattr(apps_router, 'complete_mcp_oauth_authorization', _complete)
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


def test_a_retry_never_erases_tokens_a_callback_saved_during_discovery(route, monkeypatch):
    """Reviewer reproduction: the callback commits tokens while the retry awaits discovery."""

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def discover(_url):
            entered.set()
            await release.wait()
            return route['meta']

        async def exchange(*_args, **_kwargs):
            return {'access_token': 'synthetic-access', 'refresh_token': 'synthetic-refresh', 'expires_in': 3600}

        async def tools(*_args, **_kwargs):
            return []

        # Real Firestore reads return independent snapshots, not shared mutable dicts.
        monkeypatch.setattr(apps_router, 'get_app_by_id_db', lambda _id: copy.deepcopy(route['app']))
        monkeypatch.setattr(apps_router, 'discover_oauth_metadata', discover)
        monkeypatch.setattr(apps_router, 'consume_mcp_oauth_state', lambda _state: ('app-1', 'owner'))
        monkeypatch.setattr(apps_router, 'exchange_oauth_code', exchange)
        monkeypatch.setattr(apps_router, 'discover_mcp_tools', tools)
        monkeypatch.setattr(apps_router, 'enable_app', lambda *_args: None)

        retry = asyncio.create_task(apps_router.authorize_mcp_server('app-1', uid='owner'))
        await entered.wait()
        callback = await apps_router.mcp_oauth_callback(code='synthetic-code', state='synthetic-state')
        assert callback.status_code == 200
        release.set()
        assert (await retry)['auth_url'].startswith('https://auth.example.test/authorize?')
        tokens = route['app']['external_integration']['mcp_oauth_tokens']
        assert route['app']['status'] == 'approved'
        assert tokens.get('access_token') == 'synthetic-access'
        assert tokens.get('refresh_token') == 'synthetic-refresh'

    asyncio.run(scenario())


@pytest.mark.parametrize('held_stage', ['exchange', 'discovery'])
@pytest.mark.parametrize('finish_latest', [False, True])
def test_an_old_callback_cannot_overwrite_a_retry_or_its_completed_tokens(
    route, monkeypatch, held_stage, finish_latest
):
    """Exercise both provider awaits with real single-use state and the commit helper."""

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        enabled = []

        async def exchange(_endpoint, code, *_args, **_kwargs):
            if code == 'old-code' and held_stage == 'exchange':
                entered.set()
                await release.wait()
            return {'access_token': code + '-access', 'refresh_token': code + '-refresh'}

        async def tools(_url, token):
            if token == 'old-code-access' and held_stage == 'discovery':
                entered.set()
                await release.wait()
            return []

        monkeypatch.setattr(apps_router, 'exchange_oauth_code', exchange)
        monkeypatch.setattr(apps_router, 'discover_mcp_tools', tools)
        monkeypatch.setattr(apps_router, 'enable_app', lambda uid, app_id: enabled.append((uid, app_id)))

        original_state = mcp_client.create_mcp_oauth_state('app-1', 'owner')
        old = asyncio.create_task(apps_router.mcp_oauth_callback(code='old-code', state=original_state))
        await entered.wait()
        retry = await apps_router.authorize_mcp_server('app-1', uid='owner')
        latest_verifier = route['app']['external_integration']['mcp_oauth_tokens']['code_verifier']
        new_state = _query(retry['auth_url'])['state']
        if finish_latest:
            new = await apps_router.mcp_oauth_callback(code='new-code', state=new_state)
            assert new.status_code == 200
        committed = copy.deepcopy(route['app'])
        release.set()
        assert (await old).status_code == 409
        assert route['app'] == committed
        tokens = route['app']['external_integration']['mcp_oauth_tokens']
        assert tokens['code_verifier'] == latest_verifier
        if finish_latest:
            assert tokens['access_token'] == 'new-code-access'
            assert tokens['refresh_token'] == 'new-code-refresh'
            assert enabled == [('owner', 'app-1')]
            assert (await apps_router.mcp_oauth_callback(code='new-code', state=new_state)).status_code == 400
        else:
            assert 'access_token' not in tokens
            assert enabled == []

    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['retry', 'owner', 'deleted'])
def test_atomic_commit_rejects_retired_authority_without_writes(change):
    app = _registered()
    captured = copy.deepcopy(app['external_integration']['mcp_oauth_tokens'])
    captured['access_token'] = 'synthetic-access'
    path = (apps_db.apps_collection, 'app-1')
    if change == 'retry':
        app['external_integration']['mcp_oauth_tokens']['code_verifier'] = 'new-verifier'
    elif change == 'owner':
        app['uid'] = 'different-owner'
    database = StrictFirestore({path: app} if change != 'deleted' else {})
    before = copy.deepcopy(database.rows)
    assert not apps_db.complete_mcp_oauth_authorization(
        'app-1', 'owner', captured, 'https://mcp.example.test/mcp', [], firestore_client=database
    )
    assert database.rows == before
    assert database.transactions[0].updates == []


def test_atomic_commit_preserves_other_current_integration_fields():
    app = _registered()
    app['external_integration']['setup_completed_url'] = 'https://example.test/setup'
    app['description'] = 'Unrelated current description'
    tokens = {**app['external_integration']['mcp_oauth_tokens'], 'access_token': 'synthetic-access'}
    path = (apps_db.apps_collection, 'app-1')
    database = StrictFirestore({path: app})
    assert apps_db.complete_mcp_oauth_authorization(
        'app-1', 'owner', tokens, 'https://mcp.example.test/resolved', [], firestore_client=database
    )
    saved = database.rows[path]
    assert saved['external_integration']['setup_completed_url'] == 'https://example.test/setup'
    assert saved['description'] == app['description']
    assert saved['status'] == 'approved'
