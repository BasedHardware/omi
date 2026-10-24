"""Rotating MCP credentials must survive reconstructed tools and failed tool retries."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest

from database import _client, redis_db, mcp_client_credentials
from models.app import ChatTool
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import mcp_client, mcp_token_refresh
from utils.retrieval.tools import app_tools


@pytest.fixture
def connection(monkeypatch):
    tokens = {
        'access_token': 'access-0',
        'refresh_token': 'refresh-0',
        'token_endpoint': 'https://issuer.example/token',
        'client_id': 'client',
    }
    row = {
        'id': 'app',
        'external_integration': {'mcp_server_url': 'https://mcp.example/http', 'mcp_oauth_tokens': tokens},
    }
    store = StrictFirestore({('plugins_data', 'app'): row})
    monkeypatch.setattr(_client, '_firestore_client', store)
    monkeypatch.setattr(redis_db, 'delete_app_cache_by_id', MagicMock())
    monkeypatch.setattr(app_tools, 'is_app_webhook_disabled', lambda _: False)
    monkeypatch.setattr(app_tools, 'record_app_webhook_success', MagicMock())
    monkeypatch.setattr(app_tools, 'record_app_webhook_failure', MagicMock(return_value=0))
    monkeypatch.setattr(app_tools, '_handle_app_webhook_disable', MagicMock())
    monkeypatch.setattr(app_tools, 'get_webhook_circuit_breaker', MagicMock(return_value=MagicMock()))
    authority = {'generation': 0, 'expired': True, 'fail_tool': False}

    async def refresh(endpoint, refresh_token, client_id, client_secret=None):
        assert refresh_token == f"refresh-{authority['generation']}", 'stale rotating refresh token reused'
        authority['generation'] += 1
        authority['expired'] = False
        return {
            'access_token': f"access-{authority['generation']}",
            'refresh_token': f"refresh-{authority['generation']}",
            'expires_in': '1',
        }

    async def initialize(url, access_token=None):
        if authority['expired'] or access_token != f"access-{authority['generation']}":
            raise PermissionError('expired')
        return None

    async def post(url, payload, access_token=None, session_id=None):
        await initialize(url, access_token)
        if authority['fail_tool']:
            raise RuntimeError('tool retry failed')
        return {'result': {'content': [{'type': 'text', 'text': 'fresh result'}]}}, None

    async def sse(url, tool_name, arguments, access_token=None):
        await initialize(url, access_token)
        return (await post(url, {}, access_token))[0]

    monkeypatch.setattr(mcp_client, 'refresh_oauth_token', AsyncMock(side_effect=refresh))
    monkeypatch.setattr(mcp_client, '_initialize_session', initialize)
    monkeypatch.setattr(mcp_client, '_mcp_post', post)
    monkeypatch.setattr(mcp_client, '_call_tool_via_sse', sse)

    def tool(transport='streamable_http'):
        loaded = deepcopy(store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens'])
        return app_tools.create_app_tool(
            ChatTool(name='check', description='check', endpoint='', is_mcp=True, transport=transport),
            'app',
            'Test',
            mcp_server_url='https://mcp.example/http',
            mcp_oauth_tokens=loaded,
        )

    return store, authority, tool


@pytest.mark.parametrize('transport', ['streamable_http', 'sse'])
@pytest.mark.asyncio
async def test_rotating_credentials_survive_later_tool_reconstruction(connection, transport):
    store, authority, tool = connection
    for generation in range(1, 4):
        authority['expired'] = True  # A new turn after the issuer's access-token lifetime.
        result = await tool(transport).ainvoke({})
        assert 'fresh result' in result
        saved = store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens']
        assert saved['refresh_token'] == f'refresh-{generation}'
        assert saved['access_token'] == f'access-{generation}'


@pytest.mark.parametrize('transport', ['streamable_http', 'sse'])
@pytest.mark.asyncio
async def test_rotated_credentials_are_saved_even_when_the_tool_retry_fails(connection, transport):
    store, authority, tool = connection
    authority['fail_tool'] = True
    result = await tool(transport).ainvoke({})
    assert 'Error' in result or 'error' in result
    assert (
        store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens']['refresh_token'] == 'refresh-1'
    )


@pytest.mark.asyncio
async def test_preconstructed_sibling_reuses_the_durable_rotated_token(connection):
    store, authority, tool = connection
    first, sibling = tool(), tool()
    assert 'fresh result' in await first.ainvoke({})
    assert 'fresh result' in await sibling.ainvoke({})
    assert authority['generation'] == 1
    authority['expired'] = True
    store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens']['expires_at'] = 0
    assert 'fresh result' in await tool().ainvoke({})
    assert authority['generation'] == 2


@pytest.mark.asyncio
async def test_lost_persistence_prevents_the_external_tool_retry(connection, monkeypatch, caplog):
    store, _, tool = connection

    def fail(*_):
        raise RuntimeError('provider-secret-must-not-escape')

    monkeypatch.setattr(mcp_token_refresh, 'complete_refresh', fail)
    post = AsyncMock()
    monkeypatch.setattr(mcp_client, '_mcp_post', post)
    result = await tool().ainvoke({})
    assert 'Error' in result
    assert 'provider-secret-must-not-escape' not in result + caplog.text
    post.assert_not_awaited()
    row = store.rows[('plugins_data', 'app')]
    assert row['external_integration']['mcp_oauth_tokens']['refresh_token'] == 'refresh-0'
    assert row['mcp_oauth_refresh'] is None


@pytest.mark.asyncio
async def test_revoked_refresh_does_not_retry_the_tool_or_expose_provider_data(connection, monkeypatch, caplog):
    store, _, tool = connection
    monkeypatch.setattr(mcp_client, 'refresh_oauth_token', AsyncMock(side_effect=RuntimeError('provider-secret')))
    post = AsyncMock()
    monkeypatch.setattr(mcp_client, '_mcp_post', post)
    result = await tool().ainvoke({})
    assert 'Error' in result and 'provider-secret' not in result + caplog.text
    post.assert_not_awaited()
    assert (
        store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens']['refresh_token'] == 'refresh-0'
    )


@pytest.mark.asyncio
async def test_busy_refresh_wait_is_bounded_and_does_not_issue_another_token_request(connection, monkeypatch):
    store, _, tool = connection
    tokens = store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens']
    mcp_client_credentials.claim_refresh(
        'app', 'https://mcp.example/http', tokens, 'access-0', 'other', firestore_client=store
    )
    monkeypatch.setattr(mcp_token_refresh, 'REFRESH_WAIT_SECONDS', 0)
    result = await tool().ainvoke({})
    assert 'Error' in result
    mcp_client.refresh_oauth_token.assert_not_awaited()
    assert store.rows[('plugins_data', 'app')]['mcp_oauth_refresh']['owner'] == 'other'


@pytest.mark.asyncio
async def test_cancellation_keeps_the_in_flight_refresh_fenced(connection, monkeypatch):
    store, _, tool = connection
    begun = asyncio.Event()

    async def pending(*_):
        begun.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(mcp_client, 'refresh_oauth_token', pending)
    task = asyncio.create_task(tool().ainvoke({}))
    await begun.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    row = store.rows[('plugins_data', 'app')]
    assert row['mcp_oauth_refresh']['expires_at'] > 0
    claim = mcp_client_credentials.claim_refresh(
        'app',
        'https://mcp.example/http',
        row['external_integration']['mcp_oauth_tokens'],
        'access-0',
        'other',
        firestore_client=store,
    )
    assert claim.state == 'busy'
