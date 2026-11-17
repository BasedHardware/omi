"""Exercise the installed SDK transports, not permissive provider mocks."""

import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
from types import SimpleNamespace

import aiohttp
import httpx
import pytest
from pinecone.config.openapi_configuration import Configuration

from database.summary_vector_transport import SummaryVectorIndex
from utils.llm import summary_embeddings as clients


@contextmanager
def failing_server(delay):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            self.rfile.read(int(self.headers['Content-Length']))
            time.sleep(delay)
            try:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b'{"message":"synthetic retryable failure"}')
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01})
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(1)


@pytest.mark.parametrize('stall', [False, True])
def test_real_pinecone_transport_one_attempt_and_cancellation(monkeypatch, stall):
    active = []
    request = aiohttp.ClientSession._request

    async def tracked(self, *args, **kwargs):
        active.append(True)
        try:
            return await request(self, *args, **kwargs)
        finally:
            active.pop()

    monkeypatch.setattr(aiohttp.ClientSession, '_request', tracked)
    with failing_server(0.3 if stall else 0) as (host, calls):
        original = Configuration()
        base = SimpleNamespace(_config=SimpleNamespace(api_key='synthetic', host=host), _openapi_config=original)
        started = time.monotonic()
        with pytest.raises(Exception):
            SummaryVectorIndex(base).query(_request_timeout=0.1 if stall else 1, vector=[0.1], namespace='ns2', top_k=1)
        elapsed = time.monotonic() - started
        assert len(calls) == 1
        assert not active
        assert original.retries is None
        if stall:
            assert elapsed < 0.2  # deadline plus one per-request timeout


@pytest.mark.parametrize('gateway', [False, True])
@pytest.mark.parametrize('stall', [False, True])
def test_real_embedding_sdk_one_attempt_no_key_fallback_and_deadline(monkeypatch, gateway, stall):
    calls = []
    active = []

    async def respond(request):
        calls.append(request)
        active.append(True)
        try:
            if stall:
                await asyncio.sleep(10)
            return httpx.Response(429, json={'error': {'message': 'synthetic retryable failure', 'type': 'rate_limit'}})
        finally:
            active.pop()

    real_client = httpx.AsyncClient

    class client(real_client):
        def __init__(self, **kwargs):
            transport = kwargs.pop('transport')
            assert transport._pool._retries == 0
            super().__init__(**kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic')
    monkeypatch.setattr(clients.httpx, 'AsyncClient', client)
    monkeypatch.setattr(clients, '_require_client_budget', lambda *args, **kwargs: None)
    monkeypatch.setattr(clients, 'get_byok_key', lambda *args: None)
    monkeypatch.setattr(clients, '_embeddings_gateway_mode', lambda: gateway)
    from utils.llm import gateway_client

    monkeypatch.setattr(gateway_client, '_gateway_headers', lambda **kwargs: {})
    monkeypatch.setattr(gateway_client, 'get_llm_gateway_base_url', lambda: 'https://synthetic.invalid')
    started = time.monotonic()
    duration = 0.3 if stall else 2
    with pytest.raises(Exception):
        clients.embed_query_once('garden', deadline_monotonic=started + duration)
    assert len(calls) == 1
    assert not active
    assert 0 < calls[0].extensions['timeout']['read'] <= duration
    if stall:
        assert time.monotonic() - started < duration * 2
