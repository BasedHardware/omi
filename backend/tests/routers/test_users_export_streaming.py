import asyncio
import threading
from unittest.mock import ANY, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import users as users_router
from services.users import data_export, data_export_response
from utils.other.portability_read import (
    PortabilityReadCancelled,
    PortabilityReadContext,
    check_portability_read,
)
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

    iter_export.assert_called_once_with('uid1', read_context=ANY)
    iter_streaming.assert_not_called()
    assert 'x-accel-buffering' not in response.headers


def test_export_stream_true_uses_streaming_iterator_and_headers(monkeypatch):
    iter_export = MagicMock()
    iter_streaming = MagicMock(return_value=iter(['{"ok": true}\n']))
    monkeypatch.setattr(users_router, 'iter_user_data_export', iter_export)
    monkeypatch.setattr(users_router, 'iter_user_data_export_streaming', iter_streaming)

    response = users_router.export_all_user_data(stream=True, uid='uid1')

    iter_streaming.assert_called_once_with('uid1', read_context=ANY)
    iter_export.assert_not_called()
    assert response.media_type == 'application/json'
    assert response.headers['content-disposition'] == 'attachment; filename="omi-export.json"'
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-accel-buffering'] == 'no'


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
    iter_export.assert_called_once_with('uid1', read_context=ANY)
    iter_streaming.assert_not_called()


def test_streaming_export_commits_headers_before_blocked_user_reads():
    read_started = threading.Event()
    release_read = threading.Event()

    def _gated_export(uid, **_kwargs):
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


def _export_scope(spec_version: str) -> dict:
    return {
        'type': 'http',
        'http_version': '1.1',
        'asgi': {'version': '3.0', 'spec_version': spec_version},
        'method': 'GET',
        'scheme': 'http',
        'path': '/v1/users/export',
        'raw_path': b'/v1/users/export',
        'query_string': b'stream=true',
        'headers': [],
        'client': ('127.0.0.1', 12345),
        'server': ('testserver', 80),
    }


def _receive_with_disconnect(disconnect_gate: threading.Event | None = None):
    request_delivered = False

    async def receive():
        nonlocal request_delivered
        if not request_delivered:
            request_delivered = True
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        if disconnect_gate is not None:
            assert await asyncio.to_thread(disconnect_gate.wait, 10)
        return {'type': 'http.disconnect'}

    return receive


@pytest.mark.parametrize('spec_version', ['2.0', '2.4'])
def test_disconnect_after_first_chunk_stops_user_reads(monkeypatch, spec_version):
    reads = []
    closes = []
    context_seen = []

    def _factory(uid, read_context=None):
        context_seen.append(read_context)

        def _gen():
            try:
                yield '{\n'
                reads.append('read-1')
                yield '  "profile": {},\n  "chat_messages": [\n\n  ]\n'
                yield ',\n  "export_complete": true\n}\n'
            finally:
                closes.append(True)

        return _gen()

    monkeypatch.setattr(users_router, 'iter_user_data_export_streaming', _factory)
    app = _app_with_export_router()
    sent = []
    first_body_sent = threading.Event()

    async def _receive():
        nonlocal_marker = getattr(_receive, 'delivered', False)
        if not nonlocal_marker:
            _receive.delivered = True
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await asyncio.to_thread(first_body_sent.wait, 10)
        return {'type': 'http.disconnect'}

    async def send(message):
        sent.append(message)
        if message['type'] == 'http.response.body':
            first_body_sent.set()
            await asyncio.wait_for(asyncio.to_thread(context_seen[0].cancelled.wait), timeout=10)

    async def drive():
        await asyncio.wait_for(app(_export_scope(spec_version), _receive, send), timeout=10)

    asyncio.run(drive())

    assert reads == []
    assert closes == [True]
    assert context_seen and context_seen[0].cancelled.is_set()
    body = b''.join(m.get('body', b'') for m in sent if m['type'] == 'http.response.body')
    assert b'export_complete' not in body


@pytest.mark.parametrize('spec_version', ['2.0', '2.4'])
def test_disconnect_during_blocked_read_cancels_context_and_closes_source(monkeypatch, spec_version):
    read_started = threading.Event()
    release_read = threading.Event()
    reads = []
    closes = []
    read_errors = []
    captured_contexts = []

    def _conversations(_uid, *, include_discarded=True):
        try:
            yield {'id': 'conv1'}
            reads.append('read-1')
            read_started.set()
            assert release_read.wait(timeout=10), 'test gate never released'
            check_portability_read()
            reads.append('read-2')
            yield {'id': 'conv2'}
        except BaseException as exc:
            read_errors.append(exc)
            raise
        finally:
            closes.append('conversations')

    monkeypatch.setattr(data_export.conversations_db, 'iter_all_conversations', MagicMock(side_effect=_conversations))
    monkeypatch.setattr(data_export, 'get_user_profile', MagicMock(return_value={}))
    monkeypatch.setattr(data_export, 'get_people', MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, 'iter_all_action_items', MagicMock(return_value=iter([])))
    monkeypatch.setattr(
        data_export,
        'MemoryService',
        MagicMock(return_value=MagicMock(iter_portability_export_memories=MagicMock(return_value=iter([])))),
    )
    monkeypatch.setattr(data_export, '_iter_user_subcollection', MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export, '_iter_user_nested_subcollection', MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.conversations_db, 'iter_all_conversation_photos', MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.chat_db, 'iter_all_messages', MagicMock(return_value=iter([])))

    original_context = PortabilityReadContext
    monkeypatch.setattr(
        data_export_response,
        'PortabilityReadContext',
        lambda **kwargs: captured_contexts.append(original_context(**kwargs)) or captured_contexts[-1],
    )
    app = _app_with_export_router()
    sent = []
    first_body_sent = asyncio.Event()

    async def send(message):
        sent.append(message)
        if message['type'] == 'http.response.body':
            first_body_sent.set()

    async def drive():
        task = asyncio.create_task(
            app(_export_scope(spec_version), _receive_with_disconnect(disconnect_gate=read_started), send)
        )
        await asyncio.wait_for(first_body_sent.wait(), timeout=10)
        assert await asyncio.to_thread(captured_contexts[0].cancelled.wait, 10)
        release_read.set()
        await asyncio.wait_for(task, timeout=10)

    asyncio.run(drive())

    assert reads == ['read-1']
    assert len(read_errors) == 1
    assert isinstance(read_errors[0], PortabilityReadCancelled)
    assert closes == ['conversations']
    assert captured_contexts[0].cancelled.is_set()
    body = b''.join(m.get('body', b'') for m in sent if m['type'] == 'http.response.body')
    assert b'export_complete' not in body


def test_header_send_failure_cancels_and_closes_source(monkeypatch):
    captured = []

    class _Source:
        def __init__(self):
            self.closed = False

        def __iter__(self):
            return self

        def __next__(self):
            return '{\n'

        def close(self):
            self.closed = True

    source = _Source()

    def _factory(uid, read_context=None):
        captured.append(read_context)
        return source

    monkeypatch.setattr(users_router, 'iter_user_data_export_streaming', _factory)
    app = _app_with_export_router()

    async def receive():
        await asyncio.Event().wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        raise RuntimeError('transport closed')

    async def drive():
        with pytest.raises(RuntimeError, match='transport closed'):
            await asyncio.wait_for(app(_export_scope('2.4'), receive, send), timeout=10)

    asyncio.run(drive())

    assert source.closed
    assert captured[0].cancelled.is_set()


def test_body_send_failure_cancels_and_closes_source(monkeypatch):
    captured = []
    closes = []

    def _factory(uid, read_context=None):
        captured.append(read_context)

        def _gen():
            try:
                yield '{\n'
                yield '  "profile": {}\n'
            finally:
                closes.append(True)

        return _gen()

    monkeypatch.setattr(users_router, 'iter_user_data_export_streaming', _factory)
    app = _app_with_export_router()
    sent = []

    async def receive():
        await asyncio.Event().wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        sent.append(message)
        if len([m for m in sent if m['type'] == 'http.response.body']) == 2:
            raise RuntimeError('transport closed')

    async def drive():
        with pytest.raises(RuntimeError, match='transport closed'):
            await asyncio.wait_for(app(_export_scope('2.4'), receive, send), timeout=10)

    asyncio.run(drive())

    assert closes == [True]
    assert captured[0].cancelled.is_set()


def test_completed_stream_closes_source_exactly_once(monkeypatch):
    captured = []
    closes = []

    def _factory(uid, read_context=None):
        captured.append(read_context)

        def _gen():
            try:
                yield '{\n'
                yield ',\n  "export_complete": true\n}\n'
            finally:
                closes.append(True)

        return _gen()

    monkeypatch.setattr(users_router, 'iter_user_data_export_streaming', _factory)
    app = _app_with_export_router()
    sent = []

    async def receive():
        await asyncio.Event().wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        sent.append(message)

    async def drive():
        await asyncio.wait_for(app(_export_scope('2.4'), receive, send), timeout=10)

    asyncio.run(drive())

    assert closes == [True]
    assert not captured[0].cancelled.is_set()
    body = b''.join(m.get('body', b'') for m in sent if m['type'] == 'http.response.body')
    assert body.endswith(',\n  "export_complete": true\n}\n'.encode())


def test_source_error_closes_iterator_without_completion(monkeypatch):
    closes = []

    def _factory(uid, read_context=None):
        def _gen():
            try:
                yield '{\n'
                raise RuntimeError('read failed mid-export')
            finally:
                closes.append(True)

        return _gen()

    monkeypatch.setattr(users_router, 'iter_user_data_export_streaming', _factory)
    app = _app_with_export_router()
    sent = []
    never_disconnect = asyncio.Event()

    async def receive():
        await never_disconnect.wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        sent.append(message)

    async def drive():
        with pytest.raises(RuntimeError, match='read failed mid-export'):
            await asyncio.wait_for(app(_export_scope('2.4'), receive, send), timeout=10)

    asyncio.run(drive())

    assert closes == [True]
    body = b''.join(m.get('body', b'') for m in sent if m['type'] == 'http.response.body')
    assert b'export_complete' not in body
