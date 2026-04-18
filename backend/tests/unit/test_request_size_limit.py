"""Verify the RequestSizeLimitMiddleware rejects oversized bodies early
(via Content-Length) with 413 and passes legitimate traffic through.
"""

from __future__ import annotations

import os
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils.other.request_size_limit import RequestSizeLimitMiddleware


def _app(cap: int):
    """Build a tiny app with the middleware at the configured cap."""
    # The middleware reads the cap from env at import time, so we monkeypatch
    # the module-level constant.
    import utils.other.request_size_limit as mod

    with mock.patch.object(mod, '_MAX_REQUEST_BYTES', cap):
        app = FastAPI()
        app.add_middleware(RequestSizeLimitMiddleware)

        @app.post('/echo')
        async def echo(request_body: dict):
            return request_body

        yield app


def test_rejects_oversized_request():
    import utils.other.request_size_limit as mod

    with mock.patch.object(mod, '_MAX_REQUEST_BYTES', 100):
        app = FastAPI()
        app.add_middleware(RequestSizeLimitMiddleware)

        @app.post('/echo')
        async def echo(body: dict = None):
            return {'ok': True}

        client = TestClient(app)
        # Send a 200-byte body but cap is 100
        big = {'x': 'a' * 200}
        resp = client.post('/echo', json=big)
        assert resp.status_code == 413, resp.text
        assert 'exceeds' in resp.json()['detail']


def test_accepts_small_request():
    import utils.other.request_size_limit as mod

    with mock.patch.object(mod, '_MAX_REQUEST_BYTES', 10_000):
        app = FastAPI()
        app.add_middleware(RequestSizeLimitMiddleware)

        @app.post('/echo')
        async def echo(body: dict):
            return body

        client = TestClient(app)
        resp = client.post('/echo', json={'hello': 'world'})
        assert resp.status_code == 200
        assert resp.json() == {'hello': 'world'}


def test_rejects_malformed_content_length():
    import utils.other.request_size_limit as mod

    with mock.patch.object(mod, '_MAX_REQUEST_BYTES', 10_000):
        app = FastAPI()
        app.add_middleware(RequestSizeLimitMiddleware)

        @app.post('/echo')
        async def echo():
            return {}

        client = TestClient(app)
        resp = client.post(
            '/echo',
            content=b'x',
            headers={'Content-Length': 'not-a-number', 'Content-Type': 'application/json'},
        )
        assert resp.status_code == 400


def test_no_content_length_passes():
    """Streaming / chunked requests (no Content-Length) pass through; per-
    endpoint logic is responsible for size tracking in that path."""
    import utils.other.request_size_limit as mod

    with mock.patch.object(mod, '_MAX_REQUEST_BYTES', 100):
        app = FastAPI()
        app.add_middleware(RequestSizeLimitMiddleware)

        @app.get('/ping')
        async def ping():
            return {'pong': True}

        client = TestClient(app)
        # GET with no body — no Content-Length — should pass
        resp = client.get('/ping')
        assert resp.status_code == 200
