"""Hermetic OAuth/MCP wire contracts: real client, coordinator and strict storage.

Only the external HTTP boundary is replaced by httpx.MockTransport. No socket,
cloud credentials, or production transport/coordinator methods are stubbed.
"""

import asyncio
from copy import deepcopy
import json
from urllib.parse import parse_qs
from unittest.mock import MagicMock

import httpx
import pytest

from database import _client, redis_db
from models.app import ChatTool
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import mcp_token_refresh
from utils.retrieval.tools import app_tools

ORIGIN = 'https://peer.example'
PRIVATE = 'private-issuer-response'


class EventStream(httpx.AsyncByteStream):
    def __init__(self, messages):
        self.messages = messages

    async def __aiter__(self):
        yield b'event: endpoint\ndata: /messages\n\n'
        while True:
            yield await self.messages.get()


@pytest.fixture
def wire_connection(monkeypatch):
    tokens = {
        'access_token': 'access-0',
        'refresh_token': 'refresh-0',
        'token_endpoint': ORIGIN + '/token',
        'client_id': 'client',
        'client_secret': 'synthetic-secret',
    }
    store = StrictFirestore()
    state = {'generation': 0, 'expired': True, 'reject': False, 'tool_error': False, 'refreshes': 0, 'reads': 0}
    streams = []
    requests = []
    monkeypatch.setattr(_client, '_firestore_client', store)
    monkeypatch.setattr(redis_db, 'delete_app_cache_by_id', MagicMock())
    for name in ['record_app_webhook_success', 'record_app_webhook_failure', '_handle_app_webhook_disable']:
        monkeypatch.setattr(app_tools, name, MagicMock(return_value=0))
    monkeypatch.setattr(app_tools, 'is_app_webhook_disabled', lambda _: False)
    monkeypatch.setattr(app_tools, 'get_webhook_circuit_breaker', MagicMock(return_value=MagicMock()))

    def respond(request):
        requests.append((request.method, request.url.path))
        if request.url.path == '/token':
            form = parse_qs(request.content.decode())
            assert form == {
                'grant_type': ['refresh_token'],
                'refresh_token': [f"refresh-{state['generation']}"],
                'client_id': ['client'],
                'client_secret': ['synthetic-secret'],
            }
            state['refreshes'] += 1
            if state['reject']:
                return httpx.Response(400, json={'error': 'invalid_grant', 'error_description': PRIVATE})
            state['generation'] += 1
            state['expired'] = False
            return httpx.Response(
                200,
                json={
                    'access_token': f"access-{state['generation']}",
                    'refresh_token': f"refresh-{state['generation']}",
                    'expires_in': 30,
                },
            )
        if state['expired'] or request.headers.get('Authorization') != f"Bearer access-{state['generation']}":
            return httpx.Response(401, json={'error': PRIVATE})
        if request.method == 'GET' and request.url.path == '/sse':
            messages = asyncio.Queue()
            streams.append(messages)
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=EventStream(messages))
        assert request.url.path in ('/http', '/messages')
        rpc = json.loads(request.content)
        result = {}
        if rpc['method'] == 'initialize':
            result = {
                'protocolVersion': '2025-03-26',
                'capabilities': {'tools': {}},
                'serverInfo': {'name': 'peer', 'version': '1'},
            }
        elif rpc['method'] == 'tools/call':
            assert rpc['params'] == {'name': 'check', 'arguments': {}}
            saved = store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens']
            assert saved['refresh_token'] == f"refresh-{state['generation']}", 'tool ran before durable save'
            state['reads'] += 1
            result = {
                'content': [{'type': 'text', 'text': 'business rejection' if state['tool_error'] else 'wire success'}],
                'isError': state['tool_error'],
            }
        response = {'jsonrpc': '2.0', 'id': rpc.get('id'), 'result': result}
        if request.url.path == '/messages':
            if 'id' in rpc:
                streams[-1].put_nowait(f'event: message\ndata: {json.dumps(response)}\n\n'.encode())
            return httpx.Response(202)
        return httpx.Response(200 if 'id' in rpc else 202, json=response)

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, 'AsyncClient', lambda **kwargs: client_class(transport=httpx.MockTransport(respond), **kwargs)
    )

    def tool(transport='streamable_http'):
        endpoint = ORIGIN + ('/sse' if transport == 'sse' else '/http')
        key = ('plugins_data', 'app')
        if key not in store.rows:
            store.rows[key] = {
                'external_integration': {'mcp_server_url': endpoint, 'mcp_oauth_tokens': deepcopy(tokens)}
            }
        loaded = deepcopy(store.rows[key]['external_integration']['mcp_oauth_tokens'])
        return app_tools.create_app_tool(
            ChatTool(name='check', description='check', endpoint=endpoint, is_mcp=True, transport=transport),
            'app',
            'Test',
            mcp_server_url=endpoint,
            mcp_oauth_tokens=loaded,
        )

    return store, state, requests, tool


@pytest.mark.parametrize('transport', ['streamable_http', 'sse'])
@pytest.mark.asyncio
async def test_real_wire_rotation_survives_reconstruction_and_preconstructed_siblings(wire_connection, transport):
    store, state, requests, tool = wire_connection
    first, sibling = tool(transport), tool(transport)
    assert 'wire success' in await first.ainvoke({})
    assert 'wire success' in await sibling.ainvoke({})
    assert state['refreshes'] == 1 and state['reads'] == 2
    for generation in (2, 3):
        state['expired'] = True
        assert 'wire success' in await tool(transport).ainvoke({})
        assert (
            store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens']['refresh_token']
            == f'refresh-{generation}'
        )
    assert state['refreshes'] == 3 and state['reads'] == 4
    assert requests.count(('POST', '/token')) == 3
    assert store.rows[('plugins_data', 'app')]['mcp_oauth_refresh'] is None


@pytest.mark.parametrize('transport', ['streamable_http', 'sse'])
@pytest.mark.asyncio
async def test_real_wire_rejected_refresh_has_no_tool_execution_or_provider_leak(wire_connection, transport, caplog):
    store, state, _, tool = wire_connection
    item = tool(transport)
    before = deepcopy(store.rows[('plugins_data', 'app')]['external_integration'])
    state['reject'] = True
    result = await item.ainvoke({})
    assert 'Error' in result and PRIVATE not in result + caplog.text
    assert state['refreshes'] == 1 and state['reads'] == 0
    assert store.rows[('plugins_data', 'app')]['external_integration'] == before
    assert store.rows[('plugins_data', 'app')]['mcp_oauth_refresh'] is None


@pytest.mark.parametrize('transport', ['streamable_http', 'sse'])
@pytest.mark.asyncio
async def test_real_wire_persistence_failure_prevents_any_fresh_tool_execution(
    wire_connection, monkeypatch, transport, caplog
):
    store, state, _, tool = wire_connection
    item = tool(transport)
    before = deepcopy(store.rows[('plugins_data', 'app')]['external_integration'])
    monkeypatch.setattr(mcp_token_refresh, 'complete_refresh', MagicMock(side_effect=RuntimeError(PRIVATE)))
    result = await item.ainvoke({})
    assert 'Error' in result and PRIVATE not in result + caplog.text
    assert state['refreshes'] == 1 and state['reads'] == 0
    assert store.rows[('plugins_data', 'app')]['external_integration'] == before


@pytest.mark.parametrize('transport', ['streamable_http', 'sse'])
@pytest.mark.asyncio
async def test_real_wire_business_error_keeps_rotation_and_does_not_refresh_again(wire_connection, transport):
    store, state, _, tool = wire_connection
    item = tool(transport)
    state['tool_error'] = True
    assert 'MCP tool failed' in await item.ainvoke({})
    state['tool_error'] = False
    assert 'wire success' in await tool(transport).ainvoke({})
    assert state['refreshes'] == 1 and state['reads'] == 2
    assert (
        store.rows[('plugins_data', 'app')]['external_integration']['mcp_oauth_tokens']['refresh_token'] == 'refresh-1'
    )


@pytest.mark.parametrize('transport', ['streamable_http', 'sse'])
@pytest.mark.asyncio
async def test_real_wire_valid_token_has_no_refresh_transaction_or_cache_write(wire_connection, transport):
    store, state, requests, tool = wire_connection
    state['expired'] = False
    assert 'wire success' in await tool(transport).ainvoke({})
    assert state['refreshes'] == 0 and state['reads'] == 1
    assert ('POST', '/token') not in requests and not store.transactions
    redis_db.delete_app_cache_by_id.assert_not_called()
