"""Real HTTP + Firestore transactions, using only a loopback demo-project emulator.

FIRESTORE_EMULATOR_HOST=127.0.0.1:18485 PYTHONPATH=backend backend/.venv/bin/python -m pytest \
    backend/tests/integration/test_mcp_client_refresh_firestore.py -q
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from threading import Event, Lock, Thread
from unittest.mock import MagicMock
from urllib.parse import parse_qs
import uuid

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import httpx
import pytest

from models.mcp_client import McpCredentialError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import _client, mcp_client_credentials as credentials, redis_db
from models.app import ChatTool
from routers import apps as apps_router
from utils.retrieval.tools import app_tools
from utils import mcp_token_refresh

pytestmark = pytest.mark.integration
PROJECT = 'demo-omi-mcp-refresh'


@pytest.fixture
def live_connection(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('requires a loopback Firestore emulator; no cloud fallback')
    client = firestore.Client(project=PROJECT, credentials=AnonymousCredentials())
    app_id = 'mcp-refresh-' + uuid.uuid4().hex
    ref = client.collection('plugins_data').document(app_id)
    state = {'generation': 0, 'clock': 0, 'expires': 0, 'reads': 0, 'refreshes': 0, 'reject': False}
    lock = Lock()
    begun, release = Event(), Event()
    release.set()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never print Authorization headers or token request bodies.

        def reply(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if self.path == '/token':
                begun.set()
                if not release.wait(5):
                    return self.reply(503, {'error': 'test_barrier_timeout'})
                request = parse_qs(raw.decode())
                with lock:
                    state['refreshes'] += 1
                    if state['reject'] or request.get('refresh_token') != [f"refresh-{state['generation']}"]:
                        return self.reply(400, {'error': 'invalid_grant'})
                    state['generation'] += 1
                    state['expires'] = state['clock'] + 30
                    return self.reply(
                        200,
                        {
                            'access_token': f"access-{state['generation']}",
                            'refresh_token': f"refresh-{state['generation']}",
                            'expires_in': 30,
                        },
                    )
            if self.path != '/mcp':
                return self.reply(404, {})
            with lock:
                if (
                    self.headers.get('Authorization') != f"Bearer access-{state['generation']}"
                    or state['clock'] >= state['expires']
                ):
                    return self.reply(401, {'error': 'expired'})
            rpc = json.loads(raw)
            method = rpc.get('method')
            result = {}
            if method == 'initialize':
                result = {
                    'protocolVersion': '2025-03-26',
                    'capabilities': {'tools': {}},
                    'serverInfo': {'name': 'local-refresh-test', 'version': '1'},
                }
            elif method == 'tools/call':
                saved = ref.get().to_dict()['external_integration']['mcp_oauth_tokens']
                with lock:
                    if saved['refresh_token'] != f"refresh-{state['generation']}":
                        return self.reply(409, {'error': 'credentials_not_saved_before_tool'})
                    state['reads'] += 1
                    result = {'content': [{'type': 'text', 'text': f"fresh check {state['reads']}"}]}
            elif method == 'tools/list':
                result = {
                    'tools': [
                        {
                            'name': 'check',
                            'description': 'harmless check',
                            'inputSchema': {'type': 'object', 'properties': {}},
                        }
                    ]
                }
            return self.reply(200 if 'id' in rpc else 202, {'jsonrpc': '2.0', 'id': rpc.get('id'), 'result': result})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    tokens = {
        'access_token': 'access-0',
        'refresh_token': 'refresh-0',
        'token_endpoint': origin + '/token',
        'client_id': 'test-client',
    }
    ref.set(
        {
            'id': app_id,
            'uid': 'synthetic-owner',
            'external_integration': {'mcp_server_url': origin + '/mcp', 'mcp_oauth_tokens': tokens, 'keep': 'metadata'},
        }
    )
    monkeypatch.setattr(_client, '_firestore_client', client)
    monkeypatch.setattr(redis_db, 'delete_app_cache_by_id', MagicMock())
    monkeypatch.setattr(app_tools, 'is_app_webhook_disabled', lambda _: False)
    monkeypatch.setattr(app_tools, 'record_app_webhook_success', MagicMock())
    monkeypatch.setattr(app_tools, 'record_app_webhook_failure', MagicMock(return_value=0))
    monkeypatch.setattr(app_tools, '_handle_app_webhook_disable', MagicMock())
    monkeypatch.setattr(app_tools, 'get_webhook_circuit_breaker', MagicMock(return_value=MagicMock()))

    def tool():
        loaded = ref.get().to_dict()['external_integration']['mcp_oauth_tokens']
        return app_tools.create_app_tool(
            ChatTool(name='check', description='check', endpoint='', is_mcp=True),
            app_id,
            'Test',
            mcp_server_url=origin + '/mcp',
            mcp_oauth_tokens=loaded,
        )

    yield client, ref, origin + '/mcp', tokens, state, begun, release, tool
    release.set()
    server.shutdown()
    server.server_close()
    thread.join(5)
    ref.delete()
    client.close()


@pytest.mark.asyncio
async def test_real_http_rotation_survives_reconstructed_tools_beyond_issuer_grace(live_connection):
    _, ref, _, _, state, _, _, tool = live_connection
    for generation in range(1, 4):
        state['clock'] += 120  # Deterministic issuer clock, beyond the 60-second grace risk.
        result = await tool().ainvoke({})
        assert f'fresh check {generation}' in result
        saved = ref.get().to_dict()['external_integration']
        assert saved['mcp_oauth_tokens']['refresh_token'] == f'refresh-{generation}'
        assert saved['keep'] == 'metadata'
    assert state['refreshes'] == 3 and state['reads'] == 3


@pytest.mark.asyncio
async def test_eight_concurrent_tools_share_one_real_refresh(live_connection):
    _, ref, _, _, state, begun, release, tool = live_connection
    tools = [tool() for _ in range(8)]
    release.clear()
    tasks = [asyncio.create_task(item.ainvoke({})) for item in tools]
    try:
        async with asyncio.timeout(5):
            while not begun.is_set():
                await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)  # Let the other workers observe the occupied durable claim.
    finally:
        release.set()
    results = await asyncio.gather(*tasks)
    assert all('fresh check' in result for result in results), results
    assert state['refreshes'] == 1 and state['reads'] == 8
    assert ref.get().to_dict()['mcp_oauth_refresh'] is None


def test_independent_firestore_clients_admit_only_one_refresh_owner(live_connection):
    _, ref, url, tokens, _, _, _, _ = live_connection

    def acquire(index):
        independent = firestore.Client(project=PROJECT, credentials=AnonymousCredentials())
        try:
            return credentials.claim_refresh(
                ref.id, url, tokens, 'access-0', str(index), firestore_client=independent
            ).state
        finally:
            independent.close()

    with ThreadPoolExecutor(max_workers=8) as workers:
        states = list(workers.map(acquire, range(8)))
    assert states.count('claimed') == 1 and states.count('busy') == 7


@pytest.mark.parametrize('mutation', ['delete', 'reconnect', 'takeover'])
def test_real_transaction_fences_late_refresh_writes(live_connection, mutation):
    client, ref, url, tokens, _, _, _, _ = live_connection
    credentials.claim_refresh(ref.id, url, tokens, 'access-0', 'old', now=100, firestore_client=client)
    if mutation == 'delete':
        ref.delete()
    elif mutation == 'reconnect':
        ref.update({'external_integration.mcp_oauth_tokens': {**tokens, 'access_token': 'reconnected'}})
    else:
        assert (
            credentials.claim_refresh(ref.id, url, tokens, 'access-0', 'new', now=161, firestore_client=client).state
            == 'claimed'
        )
    before = deepcopy(ref.get().to_dict())
    with pytest.raises(McpCredentialError):
        credentials.complete_refresh(
            ref.id, url, tokens, 'old', {**tokens, 'access_token': 'late'}, now=162, firestore_client=client
        )
    assert ref.get().to_dict() == before


@pytest.mark.asyncio
async def test_revoked_refresh_does_not_execute_the_tool(live_connection):
    _, ref, _, tokens, state, _, _, tool = live_connection
    state['reject'] = True
    result = await tool().ainvoke({})
    assert 'Error' in result
    assert state['refreshes'] == 1 and state['reads'] == 0
    assert ref.get().to_dict()['external_integration']['mcp_oauth_tokens'] == tokens


def test_real_refresh_endpoint_persists_each_rotation_before_discovery(live_connection, monkeypatch):
    _, ref, _, _, state, _, _, _ = live_connection
    monkeypatch.setattr(apps_router, 'delete_app_cache_by_id', MagicMock())
    app = FastAPI()
    app.include_router(apps_router.router)
    app.dependency_overrides[apps_router.auth.get_current_user_uid] = lambda: 'synthetic-owner'
    with TestClient(app) as client:
        for generation in range(1, 3):
            state['clock'] += 120
            response = client.post(f'/v1/apps/{ref.id}/mcp/refresh')
            assert response.status_code == 200, response.text
            assert response.json() == {'tools_count': 1, 'tool_names': ['check']}
            saved = ref.get().to_dict()
            assert saved['external_integration']['mcp_oauth_tokens']['refresh_token'] == f'refresh-{generation}'
            assert saved['external_integration']['keep'] == 'metadata'
            assert saved['chat_tools'][0]['name'] == 'check'


@pytest.mark.parametrize('mutation', ['delete', 'reconnect', 'takeover'])
@pytest.mark.asyncio
async def test_in_flight_provider_response_cannot_overwrite_a_changed_connection(live_connection, mutation):
    client, ref, url, tokens, state, begun, release, tool = live_connection
    item = tool()
    release.clear()
    task = asyncio.create_task(item.ainvoke({}))
    try:
        async with asyncio.timeout(5):
            while not begun.is_set():
                await asyncio.sleep(0.01)
        if mutation == 'delete':
            ref.delete()
        elif mutation == 'reconnect':
            ref.update(
                {
                    'external_integration.mcp_oauth_tokens': {
                        **tokens,
                        'access_token': 'reconnected',
                        'refresh_token': 'reconnected',
                    }
                }
            )
        else:
            # Move only the test lease clock, without waiting a production minute.
            ref.update({'mcp_oauth_refresh.expires_at': 0})
            assert (
                credentials.claim_refresh(ref.id, url, tokens, 'access-0', 'successor', firestore_client=client).state
                == 'claimed'
            )
        before = deepcopy(ref.get().to_dict())
    finally:
        release.set()
    result = await asyncio.wait_for(task, 5)
    assert 'Error' in result
    assert state['refreshes'] == 1 and state['reads'] == 0
    after = ref.get().to_dict()
    if mutation == 'reconnect':
        # Failed old owners may release their own lease, never the new credentials.
        assert after['external_integration'] == before['external_integration']
    else:
        assert after == before


@pytest.mark.asyncio
async def test_explicit_discovery_and_normal_tools_share_one_in_flight_refresh(live_connection, monkeypatch):
    _, ref, _, _, state, begun, release, tool = live_connection
    monkeypatch.setattr(apps_router, 'delete_app_cache_by_id', MagicMock())
    app = FastAPI()
    app.include_router(apps_router.router)
    app.dependency_overrides[apps_router.auth.get_current_user_uid] = lambda: 'synthetic-owner'
    release.clear()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local-test') as client:
        tasks = [
            asyncio.create_task(client.post(f'/v1/apps/{ref.id}/mcp/refresh')),
            asyncio.create_task(tool().ainvoke({})),
        ]
        try:
            async with asyncio.timeout(5):
                while not begun.is_set():
                    await asyncio.sleep(0.01)
            await asyncio.sleep(0.1)
        finally:
            release.set()
        response, result = await asyncio.wait_for(asyncio.gather(*tasks), 5)
    assert response.status_code == 200, response.text
    assert response.json() == {'tools_count': 1, 'tool_names': ['check']}
    assert 'fresh check' in result
    assert state['refreshes'] == 1 and state['reads'] == 1
    saved = ref.get().to_dict()
    assert saved['external_integration']['mcp_oauth_tokens']['refresh_token'] == 'refresh-1'
    assert saved['chat_tools'][0]['name'] == 'check'
    assert saved['mcp_oauth_refresh'] is None


@pytest.mark.asyncio
async def test_storage_failure_after_real_issuer_rotation_does_not_execute_the_tool(
    live_connection, monkeypatch, caplog
):
    _, ref, _, tokens, state, _, _, tool = live_connection
    monkeypatch.setattr(
        mcp_token_refresh, 'complete_refresh', MagicMock(side_effect=RuntimeError('private-storage-error'))
    )
    result = await tool().ainvoke({})
    assert 'Error' in result and 'private-storage-error' not in result + caplog.text
    assert state['refreshes'] == 1 and state['reads'] == 0
    saved = ref.get().to_dict()
    assert saved['external_integration']['mcp_oauth_tokens'] == tokens
    assert saved['mcp_oauth_refresh'] is None
