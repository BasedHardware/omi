"""MCP retry/callback integration: real local HTTP, Redis and Firestore transactions.

Run with a loopback FIRESTORE_EMULATOR_HOST via test.sh (integration marker).
The OAuth/MCP provider is synthetic; Firebase login and external provider-console
configuration are not exercised. No cloud credentials or user data are accepted.
"""

import asyncio
import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import httpx
import pytest
import redis
from fastapi import FastAPI
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import apps as apps_db, redis_db
from routers import apps as apps_router

pytestmark = pytest.mark.integration

SYNTHETIC_CALLBACK = 'http://omi.test/v1/apps/mcp/callback'


@pytest.fixture
def local_redis():
    binary = shutil.which('redis-server')
    assert binary, 'Install local redis-server before running this integration check'
    with tempfile.TemporaryDirectory(prefix='omi-mcp-oauth-', dir='/tmp') as temporary:
        socket = temporary + '/redis.sock'
        process = subprocess.Popen(
            [binary, '--port', '0', '--unixsocket', socket, '--save', '', '--appendonly', 'no'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        client = redis.Redis(unix_socket_path=socket, socket_timeout=2)
        try:
            deadline = time.monotonic() + 5
            while True:
                try:
                    if client.ping():
                        break
                except redis.ConnectionError:
                    assert time.monotonic() < deadline, 'Local Redis did not start'
                    time.sleep(0.02)
            yield client
        finally:
            client.close()
            process.terminate()
            process.wait(timeout=5)


@pytest.fixture
def oauth_provider():
    state: dict[str, Any] = {'codes': {}, 'tokens': set(), 'hold': None}
    entered, release = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def send_json(self, status, value):
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == '/.well-known/oauth-authorization-server':
                self.send_json(
                    200,
                    {'authorization_endpoint': state['origin'] + '/authorize', 'scopes_supported': ['read']},
                )
                return
            if parsed.path == '/authorize':
                query = parse_qs(parsed.query)
                assert query['client_id'] == ['synthetic-client']
                if query.get('redirect_uri') != [SYNTHETIC_CALLBACK]:
                    self.send_json(400, {'error': 'invalid_redirect_uri'})
                    return
                assert query['code_challenge_method'] == ['S256']
                code = uuid4().hex
                state['codes'][code] = query['code_challenge'][0]
                self.send_response(302)
                self.send_header(
                    'Location', SYNTHETIC_CALLBACK + '?' + urlencode({'code': code, 'state': query['state'][0]})
                )
                self.end_headers()
                return
            self.send_error(404)

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            if self.path == '/token':
                form = parse_qs(body.decode())
                code = form['code'][0]
                challenge = state['codes'].pop(code, None)
                actual = base64.urlsafe_b64encode(hashlib.sha256(form['code_verifier'][0].encode()).digest())
                if challenge != actual.rstrip(b'=').decode():
                    self.send_json(400, {'error': 'invalid_grant'})
                    return
                if state['hold'] == code:
                    entered.set()
                    assert release.wait(10), 'Held token exchange was not released'
                access = 'synthetic-access-' + code
                state['tokens'].add(access)
                self.send_json(200, {'access_token': access, 'refresh_token': 'synthetic-refresh-' + code})
                return
            if self.path == '/mcp':
                if self.headers.get('Authorization', '').removeprefix('Bearer ') not in state['tokens']:
                    self.send_json(401, {'error': 'unauthorized'})
                    return
                rpc = json.loads(body)
                if rpc['method'] == 'notifications/initialized':
                    self.send_response(202)
                    self.end_headers()
                    return
                result = {'protocolVersion': '2025-03-26', 'capabilities': {}}
                if rpc['method'] == 'tools/list':
                    result = {'tools': [{'name': 'synthetic_read', 'description': 'Local QA', 'inputSchema': {}}]}
                self.send_json(200, {'jsonrpc': '2.0', 'id': rpc['id'], 'result': result})
                return
            self.send_error(404)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    state['origin'] = f'http://127.0.0.1:{server.server_port}'
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield state, entered, release
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


@pytest.mark.parametrize(
    'redirect_uri',
    ['https://example.test/other-callback', SYNTHETIC_CALLBACK + '\r\nX-Injected: true'],
)
def test_local_provider_rejects_unregistered_redirects(oauth_provider, redirect_uri):
    provider, _, _ = oauth_provider
    response = httpx.get(
        provider['origin'] + '/authorize',
        params={
            'client_id': 'synthetic-client',
            'redirect_uri': redirect_uri,
            'code_challenge_method': 'S256',
            'code_challenge': 'synthetic-challenge',
            'state': 'synthetic-state',
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert response.json() == {'error': 'invalid_redirect_uri'}
    assert 'Location' not in response.headers
    assert not provider['codes']


def test_local_provider_encodes_state_in_fixed_callback(oauth_provider):
    provider, _, _ = oauth_provider
    state = 'synthetic\r\nX-Injected: true&next=other'
    response = httpx.get(
        provider['origin'] + '/authorize',
        params={
            'client_id': 'synthetic-client',
            'redirect_uri': SYNTHETIC_CALLBACK,
            'code_challenge_method': 'S256',
            'code_challenge': 'synthetic-challenge',
            'state': state,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers['Location']
    assert location.startswith(SYNTHETIC_CALLBACK + '?')
    assert '\r' not in location and '\n' not in location
    assert 'X-Injected' not in response.headers
    query = parse_qs(urlsplit(location).query)
    assert query['state'] == [state]
    assert list(provider['codes']) == query['code']


def test_retry_callback_pkce_replay_and_supersession_on_local_services(local_redis, oauth_provider, monkeypatch):
    assert os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:'))
    database = firestore.Client(project='demo-mcp-' + uuid4().hex[:12], credentials=AnonymousCredentials())
    provider, entered, release = oauth_provider
    app_id, uid = 'synthetic-app', 'synthetic-owner'
    ref = database.collection(apps_db.apps_collection).document(app_id)
    ref.set(
        {
            'id': app_id,
            'uid': uid,
            'status': 'pending_mcp_auth',
            'external_integration': {
                'mcp_server_url': provider['origin'] + '/mcp',
                'setup_completed_url': 'https://example.test/unchanged',
                'mcp_oauth_tokens': {
                    'client_id': 'synthetic-client',
                    'redirect_uri': SYNTHETIC_CALLBACK,
                    'token_endpoint': provider['origin'] + '/token',
                    'code_verifier': 'synthetic-original-verifier',
                },
            },
        }
    )
    monkeypatch.setattr(redis_db, 'r', local_redis)
    monkeypatch.setattr(apps_router, 'get_app_by_id_db', lambda _app_id: ref.get().to_dict())
    monkeypatch.setattr(
        apps_router, 'set_mcp_code_verifier', partial(apps_db.set_mcp_code_verifier, firestore_client=database)
    )
    monkeypatch.setattr(
        apps_router,
        'complete_mcp_oauth_authorization',
        partial(apps_db.complete_mcp_oauth_authorization, firestore_client=database),
    )
    api = FastAPI()
    api.include_router(apps_router.router)
    api.dependency_overrides[apps_router.auth.get_current_user_uid] = lambda: uid

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url='http://omi.test') as client:

            async def begin():
                response = await client.post(f'/v1/apps/{app_id}/mcp/authorize')
                assert response.status_code == 200
                async with httpx.AsyncClient() as browser:
                    redirect = await browser.get(response.json()['auth_url'], follow_redirects=False)
                assert redirect.status_code == 302
                return redirect.headers['Location']

            old_url = await begin()
            provider['hold'] = parse_qs(urlsplit(old_url).query)['code'][0]
            old = asyncio.create_task(client.get(old_url))
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                latest_url = await begin()
                verifier = ref.get().to_dict()['external_integration']['mcp_oauth_tokens']['code_verifier']
                latest = await client.get(latest_url)
                assert latest.status_code == 200 and 'Connected!' in latest.text
                saved = ref.get().to_dict()
            finally:
                release.set()
                retired = await old
            assert retired.status_code == 409 and 'superseded' in retired.text
            assert ref.get().to_dict() == saved
            tokens = saved['external_integration']['mcp_oauth_tokens']
            assert tokens['code_verifier'] == verifier
            assert tokens['access_token'].endswith(parse_qs(urlsplit(latest_url).query)['code'][0])
            assert saved['external_integration']['setup_completed_url'] == 'https://example.test/unchanged'
            assert len(saved['chat_tools']) == 1
            assert redis_db.get_enabled_apps(uid) == [app_id]
            assert (await client.get(latest_url)).status_code == 400

            # An older URL arriving only after PKCE rotation fails at the real
            # HTTP provider and must leave the existing working grant intact.
            stale_url = await begin()
            pending_url = await begin()
            pending = ref.get().to_dict()
            assert (await client.get(stale_url)).status_code == 502
            assert ref.get().to_dict() == pending
            assert redis_db.get_enabled_apps(uid) == [app_id]
            pending_state = parse_qs(urlsplit(pending_url).query)['state'][0]
            assert 0 < local_redis.ttl('mcp_oauth_state:' + pending_state) <= 600
            # Simulate expiry by removing only this disposable local state.
            local_redis.delete('mcp_oauth_state:' + pending_state)
            assert (await client.get(pending_url)).status_code == 400
            assert ref.get().to_dict() == pending
            api.dependency_overrides[apps_router.auth.get_current_user_uid] = lambda: 'not-the-owner'
            assert (await client.post(f'/v1/apps/{app_id}/mcp/authorize')).status_code == 403

    try:
        asyncio.run(scenario())
    finally:
        database.close()
