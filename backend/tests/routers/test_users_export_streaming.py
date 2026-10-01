import asyncio
import threading
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import users as users_router
from utils.other.timeout import TimeoutMiddleware


def _app_with_export_router() -> FastAPI:
    app = FastAPI()
    app.include_router(users_router.router)
    app.dependency_overrides[users_router.auth.get_current_user_uid] = lambda: 'uid1'
    return app


def test_export_stream_param_defaults_to_legacy_iterator(monkeypatch):
    iter_export = MagicMock(return_value=iter(['{"ok": true}\n']))
    iter_streaming = MagicMock(return_value=iter(['{"stream": true}\n']))
    monkeypatch.setattr(users_router, 'iter_user_data_export', iter_export)
    monkeypatch.setattr(users_router, 'iter_user_data_export_streaming', iter_streaming)

    response = users_router.export_all_user_data(uid='uid1')

    iter_export.assert_called_once_with('uid1')
    iter_streaming.assert_not_called()
    assert 'x-accel-buffering' not in response.headers


def test_export_stream_true_uses_streaming_iterator_and_headers(monkeypatch):
    iter_export = MagicMock()
    iter_streaming = MagicMock(return_value=iter(['{"ok": true}\n']))
    monkeypatch.setattr(users_router, 'iter_user_data_export', iter_export)
    monkeypatch.setattr(users_router, 'iter_user_data_export_streaming', iter_streaming)

    response = users_router.export_all_user_data(stream=True, uid='uid1')

    iter_streaming.assert_called_once_with('uid1')
    iter_export.assert_not_called()
    assert response.media_type == 'application/json'
    assert response.headers['content-disposition'] == 'attachment; filename="omi-export.json"'
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-accel-buffering'] == 'no'

    async def _consume():
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk)
        return ''.join(parts)

    assert asyncio.run(_consume()) == '{"ok": true}\n'


def test_export_stream_route_returns_completion_suffix(monkeypatch):
    monkeypatch.setattr(
        users_router,
        'iter_user_data_export_streaming',
        MagicMock(return_value=iter(['{\n', '  "chat_messages": [\n\n  ]\n', ',\n  "export_complete": true\n}\n'])),
    )
    app = _app_with_export_router()

    response = TestClient(app).get('/v1/users/export?stream=true')

    assert response.status_code == 200
    assert response.headers['x-accel-buffering'] == 'no'
    assert response.text.endswith(',\n  "export_complete": true\n}\n')


def test_export_route_without_stream_param_uses_legacy_path(monkeypatch):
    iter_export = MagicMock(return_value=iter(['{"ok": true}\n']))
    iter_streaming = MagicMock()
    monkeypatch.setattr(users_router, 'iter_user_data_export', iter_export)
    monkeypatch.setattr(users_router, 'iter_user_data_export_streaming', iter_streaming)
    app = _app_with_export_router()

    response = TestClient(app).get('/v1/users/export')

    assert response.status_code == 200
    iter_export.assert_called_once_with('uid1')
    iter_streaming.assert_not_called()


def test_streaming_export_commits_headers_before_blocked_user_reads():
    read_started = threading.Event()
    release_read = threading.Event()

    def _gated_export(uid):
        yield '{\n'
        read_started.set()
        assert release_read.wait(timeout=10), 'test gate never released'
        yield '  "profile": {},\n  "chat_messages": [\n\n  ]\n'
        yield ',\n  "export_complete": true\n}\n'

    app = _app_with_export_router()
    app.add_middleware(TimeoutMiddleware, methods_timeout={'GET': 0.5})
    original = users_router.iter_user_data_export_streaming
    users_router.iter_user_data_export_streaming = _gated_export  # type: ignore[assignment]
    sent = []
    headers_sent = asyncio.Event()
    request_delivered = False
    receive_gate = asyncio.Event()

    async def receive():
        nonlocal request_delivered
        if not request_delivered:
            request_delivered = True
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await receive_gate.wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        sent.append(message)
        if message['type'] == 'http.response.start':
            headers_sent.set()

    scope = {
        'type': 'http',
        'http_version': '1.1',
        'asgi': {'version': '3.0'},
        'method': 'GET',
        'scheme': 'http',
        'path': '/v1/users/export',
        'raw_path': b'/v1/users/export',
        'query_string': b'stream=true',
        'headers': [],
        'client': ('127.0.0.1', 12345),
        'server': ('testserver', 80),
        'app': app,
    }

    async def drive():
        task = asyncio.create_task(app(scope, receive, send))
        await asyncio.wait_for(headers_sent.wait(), timeout=10)
        assert not release_read.is_set()
        release_read.set()
        await asyncio.wait_for(task, timeout=10)
        receive_gate.set()

    try:
        asyncio.run(drive())
    finally:
        users_router.iter_user_data_export_streaming = original

    assert read_started.is_set()
    start = next(m for m in sent if m['type'] == 'http.response.start')
    assert start['status'] == 200
    headers = dict(start['headers'])
    assert headers[b'x-accel-buffering'] == b'no'
    body = b''.join(m.get('body', b'') for m in sent if m['type'] == 'http.response.body')
    assert body.endswith(',\n  "export_complete": true\n}\n'.encode())
