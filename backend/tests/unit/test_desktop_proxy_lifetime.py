"""Request lifetime tests use real ASGI receive/cancellation boundaries."""

import asyncio
import ast
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import Response, StreamingResponse

from utils.byok import BYOKMiddleware
from utils.llm import desktop_proxy_lifetime as lifetime

from routers import desktop_proxy


def test_main_installs_deadline_outside_other_middlewares():
    tree = ast.parse((Path(__file__).parents[2] / 'main.py').read_text())
    middleware = [
        node.value.args[0].id
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == 'add_middleware'
        and isinstance(node.value.args[0], ast.Name)
    ]
    assert middleware[-1] == 'DesktopProxyDeadlineMiddleware'
    assert middleware.index('TimeoutMiddleware') < middleware.index('ExternalListMetricsMiddleware')
    assert 'BYOKMiddleware' in middleware


@pytest.mark.asyncio
async def test_real_middleware_disconnect_polling_completes():
    app = FastAPI()
    app.add_middleware(BaseHTTPMiddleware, dispatch=lambda request, call_next: call_next(request))
    completed = asyncio.Event()

    @app.post('/')
    async def endpoint(request: Request):
        await request.body()

        async def provider():
            return 'done'

        assert await desktop_proxy._cancel_on_disconnect(request, provider()) == 'done'
        completed.set()
        return {'ok': True}

    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': b'{}', 'more_body': False}
        await asyncio.Event().wait()

    async def send(message):
        pass

    task = asyncio.create_task(
        app(
            {
                'type': 'http',
                'asgi': {'version': '3.0'},
                'method': 'POST',
                'path': '/',
                'query_string': b'',
                'headers': [],
            },
            receive,
            send,
        )
    )
    done, _ = await asyncio.wait([task], timeout=3.0)
    for _ in range(5):
        if task.done():
            break
        task.cancel()
        await asyncio.sleep(0)
    assert completed.is_set(), 'real middleware polling swallowed cancellation and held a completed provider open'
    assert task in done
    await task


@pytest.mark.asyncio
async def test_real_middleware_disconnect_cancels_provider():
    app = FastAPI()
    app.add_middleware(BYOKMiddleware)
    disconnected = asyncio.Event()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    @app.post('/')
    async def endpoint(request: Request):
        await request.body()

        async def provider():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        try:
            await desktop_proxy._cancel_on_disconnect(request, provider())
        except desktop_proxy.ClientDisconnected:
            return {'cancelled': True}

    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': b'{}', 'more_body': False}
        await disconnected.wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        pass

    task = asyncio.create_task(
        app(
            {
                'type': 'http',
                'asgi': {'version': '3.0'},
                'method': 'POST',
                'path': '/',
                'query_string': b'',
                'headers': [],
            },
            receive,
            send,
        )
    )
    await started.wait()
    disconnected.set()
    done, _ = await asyncio.wait([task], timeout=3.0)
    cancelled_before_cleanup = cancelled.is_set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert cancelled_before_cleanup, 'BYOK BaseHTTPMiddleware hides disconnect from is_disconnected polling'
    assert task in done


@pytest.fixture
def lifetime_app(monkeypatch):
    """Real route wrapper + BYOK middleware; only business/provider IO is fake."""
    monkeypatch.setattr(lifetime, 'REQUEST_TIMEOUT_SECONDS', 2.0)
    monkeypatch.setattr(lifetime, 'UPLOAD_IDLE_SECONDS', 0.5)
    monkeypatch.setattr(lifetime, 'UPLOAD_TIMEOUT_SECONDS', 0.8)
    app = FastAPI()
    app.add_middleware(BYOKMiddleware)
    app.add_middleware(lifetime.DesktopProxyDeadlineMiddleware)
    app.include_router(desktop_proxy.router)

    async def identity():
        return 'synthetic-test-user'

    app.dependency_overrides[desktop_proxy._authorized_desktop_user] = identity
    monkeypatch.setattr(desktop_proxy, '_enforce_managed_plan_gate', AsyncMock())
    monkeypatch.setattr(desktop_proxy, 'should_refuse', AsyncMock(return_value=False))

    async def meter(uid, path, model, action):
        return path

    monkeypatch.setattr(desktop_proxy, '_meter_server_request', meter)
    monkeypatch.setattr(desktop_proxy, 'get_byok_key', lambda _: None)
    return app


def terminals(capsys):
    return [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith('{') and 'desktop_gemini_proxy_terminal' in line
    ]


async def call_asgi(app, receive):
    messages = []

    async def send(message):
        messages.append(message)

    await app(
        {
            'type': 'http',
            'asgi': {'version': '3.0', 'spec_version': '2.3'},
            'http_version': '1.1',
            'scheme': 'http',
            'server': ('test', 80),
            'client': ('test', 1),
            'method': 'POST',
            'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
            'query_string': b'',
            'headers': [],
        },
        receive,
        send,
    )
    return messages


def body_then_wait(body=b'{"contents":[{"parts":[{"text":"synthetic"}]}]}'):
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        await asyncio.Event().wait()

    return receive


@pytest.mark.asyncio
@pytest.mark.parametrize('trickle', [False, True])
async def test_upload_idle_and_total_limits(lifetime_app, capsys, trickle):
    async def receive():
        if trickle:
            await asyncio.sleep(0.005)
            return {'type': 'http.request', 'body': b' ', 'more_body': True}
        await asyncio.Event().wait()

    messages = await call_asgi(lifetime_app, receive)
    start = next(m for m in messages if m['type'] == 'http.response.start')
    assert start['status'] == 504
    assert dict(start['headers'])[b'x-omi-retryable'] == b'false'
    events = terminals(capsys)
    assert [(e['outcome'], e['phase']) for e in events] == [('upload_timeout', 'upload')]


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['authorization', 'reservation', 'metering'])
async def test_deadline_includes_pre_provider_work(lifetime_app, monkeypatch, capsys, phase):
    cancelled = asyncio.Event()

    async def stalled(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    if phase == 'authorization':
        lifetime_app.dependency_overrides[desktop_proxy._authorized_desktop_user] = stalled

        # FastAPI inspects dependency signatures, so use a zero-argument seam.
        async def auth():
            return await stalled()

        lifetime_app.dependency_overrides[desktop_proxy._authorized_desktop_user] = auth
    else:
        monkeypatch.setattr(
            desktop_proxy, 'should_refuse' if phase == 'reservation' else '_meter_server_request', stalled
        )
    messages = await call_asgi(lifetime_app, body_then_wait())
    start = next(m for m in messages if m['type'] == 'http.response.start')
    assert start['status'] == 504
    assert dict(start['headers'])[b'x-omi-error-class'] == b'pre_provider_deadline'
    assert cancelled.is_set()
    assert [(e['outcome'], e['phase']) for e in terminals(capsys)] == [('pre_provider_deadline', phase)]


@pytest.mark.asyncio
async def test_provider_trickle_cannot_extend_route_deadline(lifetime_app, monkeypatch, capsys):
    closed = asyncio.Event()

    class Trickle(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                await asyncio.sleep(0.005)
                yield b' '

        async def aclose(self):
            closed.set()

    async def transport(request):
        return httpx.Response(200, stream=Trickle())

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:

        async def provider(*args, **kwargs):
            kwargs['telemetry'].phase = 'gateway'
            telemetry = kwargs['telemetry']
            telemetry.phase = 'gateway'
            result = await client.post('https://provider.invalid/test')
            return Response(result.content)

        monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)
        messages = await call_asgi(lifetime_app, body_then_wait())
    assert next(m for m in messages if m['type'] == 'http.response.start')['status'] == 504
    assert closed.is_set()
    assert [e['outcome'] for e in terminals(capsys)] == ['provider_timeout']


@pytest.mark.asyncio
async def test_route_disconnect_cancels_provider_once(lifetime_app, monkeypatch, capsys):
    started, disconnected, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def provider(*args, **kwargs):
        kwargs['telemetry'].phase = 'gateway'
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)
    read_body = body_then_wait()
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return await read_body()
        await disconnected.wait()
        return {'type': 'http.disconnect'}

    task = asyncio.create_task(call_asgi(lifetime_app, receive))
    await started.wait()
    disconnected.set()
    await task
    assert cancelled.is_set()
    assert [e['outcome'] for e in terminals(capsys)] == ['client_cancelled']


@pytest.mark.asyncio
async def test_completed_provider_emits_exactly_one_terminal(lifetime_app, monkeypatch, capsys):
    async def provider(*args, **kwargs):
        kwargs['telemetry'].phase = 'gateway'
        telemetry = kwargs['telemetry']
        telemetry.complete(outcome='success', status_code=200, retryable=False, phase='gateway')
        return Response(b'{"candidates":[{"content":{"parts":[{"text":"ok"}]},"finishReason":"STOP"}]}')

    monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)
    messages = await call_asgi(lifetime_app, body_then_wait())
    assert next(m for m in messages if m['type'] == 'http.response.start')['status'] == 200
    assert [e['outcome'] for e in terminals(capsys)] == ['success']


@pytest.mark.asyncio
async def test_upload_disconnect_is_terminal(lifetime_app, capsys):
    async def receive():
        return {'type': 'http.disconnect'}

    await call_asgi(lifetime_app, receive)
    assert [e['outcome'] for e in terminals(capsys)] == ['client_cancelled']


@pytest.mark.asyncio
async def test_stream_consumption_shares_entry_deadline(lifetime_app, monkeypatch, capsys):
    closed = asyncio.Event()

    async def chunks():
        try:
            while True:
                await asyncio.sleep(0.005)
                yield b'data: {}\n\n'
        finally:
            closed.set()

    async def provider(*args, **kwargs):
        kwargs['telemetry'].phase = 'gateway'
        return StreamingResponse(chunks(), media_type='text/event-stream')

    monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)
    messages = await call_asgi(lifetime_app, body_then_wait())
    assert any(b'"error":"provider_timeout"' in m.get('body', b'') for m in messages)
    assert closed.is_set()
    assert [e['outcome'] for e in terminals(capsys)] == ['provider_timeout']


@pytest.mark.asyncio
async def test_platform_cancellation_has_one_terminal_and_drains_work(lifetime_app, monkeypatch, capsys):
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def provider(*args, **kwargs):
        kwargs['telemetry'].phase = 'gateway'
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)
    task = asyncio.create_task(call_asgi(lifetime_app, body_then_wait()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()
    assert [e['outcome'] for e in terminals(capsys)] == ['client_cancelled']


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'failure_class,expected_status,retryable',
    [
        ('timeout_before_output', 504, 'false'),
        ('provider_5xx_omi_paid', 503, 'true'),
    ],
)
async def test_gateway_typed_timeout_does_not_authorize_replay(
    lifetime_app, monkeypatch, capsys, failure_class, expected_status, retryable
):
    gateway = desktop_proxy.desktop_gemini_gateway

    async def failure(*args, **kwargs):
        raise gateway._gateway_error(
            httpx.Response(
                503,
                json={
                    'error': {'code': 'provider_failure', 'failure_class': failure_class, 'message': 'provider failure'}
                },
            )
        )

    monkeypatch.setattr(gateway, 'gateway_desktop_chat', failure)
    messages = await call_asgi(lifetime_app, body_then_wait())
    start = next(m for m in messages if m['type'] == 'http.response.start')
    assert start['status'] == expected_status
    assert dict(start['headers'])[b'x-omi-retryable'] == retryable.encode()
    assert [e['outcome'] for e in terminals(capsys)] == [
        'provider_timeout' if expected_status == 504 else 'provider_unavailable'
    ]


@pytest.mark.asyncio
async def test_response_backpressure_cannot_hold_stream_open(lifetime_app, monkeypatch, capsys):
    closed = asyncio.Event()

    async def chunks():
        try:
            yield b'data: {}\n\n'
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def provider(*args, **kwargs):
        kwargs['telemetry'].phase = 'gateway'
        return StreamingResponse(chunks(), media_type='text/event-stream')

    monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)
    # No middleware here: backpressure must reach the actual streaming response
    # rather than BaseHTTPMiddleware's buffered in-memory response channel.
    app = lifetime_app
    app.user_middleware.clear()
    monkeypatch.setattr(lifetime, 'CANCEL_GRACE_SECONDS', 0.01)

    async def send(message):
        if message['type'] == 'http.response.body':
            await asyncio.Event().wait()

    scope = {
        'type': 'http',
        'asgi': {'version': '3.0', 'spec_version': '2.4'},
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'query_string': b'',
        'headers': [],
    }
    task = asyncio.create_task(app(scope, body_then_wait(), send))
    done, _ = await asyncio.wait((task,), timeout=3.0)
    assert task in done
    await task
    assert closed.is_set()
    assert [e['outcome'] for e in terminals(capsys)] == ['provider_timeout']


@pytest.mark.asyncio
async def test_repeated_cancellation_cannot_interrupt_owned_cleanup(monkeypatch):
    monkeypatch.setattr(lifetime, 'CANCEL_GRACE_SECONDS', 0.02)
    first_cancel, stopped = asyncio.Event(), asyncio.Event()

    async def resistant():
        try:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                first_cancel.set()
                await asyncio.Event().wait()
        finally:
            stopped.set()

    child = asyncio.create_task(resistant())
    await asyncio.sleep(0)
    owner = asyncio.create_task(lifetime._drain(child))
    await first_cancel.wait()
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner
    await asyncio.wait_for(stopped.wait(), timeout=1.0)
    assert child.done()
    # The retained drain also retrieves exceptions from abandoned tasks.
    await asyncio.sleep(0)
    assert not lifetime._cleanup_tasks


@pytest.mark.asyncio
async def test_stream_cancel_before_iteration_emits_terminal(lifetime_app, monkeypatch, capsys):
    entered = asyncio.Event()
    app = lifetime_app
    app.user_middleware.clear()

    async def provider(*args, **kwargs):
        kwargs['telemetry'].phase = 'gateway'

        async def chunks():
            yield b'data: {}\n\n'

        return StreamingResponse(chunks(), media_type='text/event-stream')

    monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)

    async def send(message):
        if message['type'] == 'http.response.start':
            entered.set()
            await asyncio.Event().wait()

    scope = {
        'type': 'http',
        'asgi': {'version': '3.0', 'spec_version': '2.4'},
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'query_string': b'',
        'headers': [],
    }
    task = asyncio.create_task(app(scope, body_then_wait(), send))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [e['outcome'] for e in terminals(capsys)] == ['client_cancelled']


@pytest.mark.asyncio
async def test_stream_double_cancel_closes_suspended_iterator(monkeypatch):
    from utils.llm.desktop_gemini_telemetry import ProxyTelemetry

    entered, closed = asyncio.Event(), asyncio.Event()

    async def chunks():
        try:
            yield b'data: {}\n\n'
        finally:
            closed.set()

    telemetry = ProxyTelemetry(Request({'type': 'http', 'headers': []}), streaming=True)
    telemetry.request_deadline = asyncio.get_running_loop().time() + 10
    response = lifetime.DeadlinedStreamingResponse(StreamingResponse(chunks()), telemetry)

    async def send(message):
        if message['type'] == 'http.response.body':
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(response({'type': 'http', 'asgi': {'spec_version': '2.4'}}, body_then_wait(), send))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(closed.wait(), timeout=3.0)


@pytest.mark.asyncio
async def test_stream_timeout_starts_a_new_sse_frame(lifetime_app, monkeypatch, capsys):
    async def provider(*args, **kwargs):
        kwargs['telemetry'].phase = 'gateway'

        async def chunks():
            yield b'data: {"partial"'
            await asyncio.Event().wait()

        return StreamingResponse(chunks(), media_type='text/event-stream')

    monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)
    messages = await call_asgi(lifetime_app, body_then_wait())
    wire = b''.join(m.get('body', b'') for m in messages)
    frames = wire.split(b'\n\n')
    assert json.loads(frames[-2].removeprefix(b'data: '))['error'] == 'provider_timeout'
    assert [e['outcome'] for e in terminals(capsys)] == ['provider_timeout']


@pytest.fixture
def production_lifetime_app(lifetime_app):
    import desktop_backend

    app = desktop_backend._build_app()
    app.dependency_overrides.update(lifetime_app.dependency_overrides)
    return app


@pytest.mark.asyncio
async def test_production_stack_bounds_real_outward_send(production_lifetime_app, monkeypatch, capsys):
    app = production_lifetime_app
    assert app.user_middleware[0].cls is lifetime.DesktopProxyDeadlineMiddleware
    assert any(m.cls is BYOKMiddleware for m in app.user_middleware)
    monkeypatch.setattr(lifetime, 'CANCEL_GRACE_SECONDS', 0.01)
    entered = asyncio.Event()

    async def provider(*args, **kwargs):
        kwargs['telemetry'].phase = 'gateway'
        telemetry = kwargs['telemetry']
        telemetry.phase = 'gateway'
        telemetry.complete(outcome='success', status_code=200, retryable=False, phase='gateway')
        return Response(b'{"candidates":[{"content":{"parts":[{"text":"ok"}]},"finishReason":"STOP"}]}')

    monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)

    async def send(message):
        if message['type'] == 'http.response.body':
            entered.set()
            await asyncio.Event().wait()

    scope = {
        'type': 'http',
        'asgi': {'version': '3.0', 'spec_version': '2.4'},
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'query_string': b'',
        'headers': [],
    }
    task = asyncio.create_task(app(scope, body_then_wait(), send))
    await entered.wait()
    assert not terminals(capsys), 'provider success must wait for outward delivery'
    done, _ = await asyncio.wait((task,), timeout=3.0)
    assert task in done
    await task
    assert [e['outcome'] for e in terminals(capsys)] == ['provider_timeout']


@pytest.mark.asyncio
async def test_deadline_aborts_incomplete_content_length(production_lifetime_app, monkeypatch, capsys):
    app = production_lifetime_app
    monkeypatch.setattr(lifetime, 'CANCEL_GRACE_SECONDS', 0.01)

    async def provider(*args, **kwargs):
        kwargs['telemetry'].phase = 'gateway'
        kwargs['telemetry'].complete(outcome='success', status_code=200, retryable=False, phase='gateway')
        return Response(b'{"synthetic":"body"}')

    monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)
    declared, body_calls = None, 0

    async def send(message):
        nonlocal declared, body_calls
        if message['type'] == 'http.response.start':
            declared = int(dict(message['headers'])[b'content-length'])
        elif message['type'] == 'http.response.body':
            body_calls += 1
            if body_calls == 1:
                await asyncio.Event().wait()
            if not message.get('more_body', False) and len(message.get('body', b'')) < declared:
                raise RuntimeError('Response content shorter than Content-Length')

    scope = {
        'type': 'http',
        'asgi': {'version': '3.0', 'spec_version': '2.4'},
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'query_string': b'',
        'headers': [],
    }
    await app(scope, body_then_wait(), send)
    assert body_calls == 1, 'do not send an invalid empty completion after fixed-length headers'
    assert [e['outcome'] for e in terminals(capsys)] == ['provider_timeout']


@pytest.mark.asyncio
@pytest.mark.parametrize('grouped', [False, True])
async def test_production_send_disconnect_is_not_internal_error(production_lifetime_app, monkeypatch, capsys, grouped):
    app = production_lifetime_app

    async def provider(*args, **kwargs):
        kwargs['telemetry'].phase = 'gateway'
        kwargs['telemetry'].complete(outcome='success', status_code=200, retryable=False, phase='gateway')
        return Response(b'{"synthetic":"body"}')

    monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)

    async def send(message):
        if message['type'] == 'http.response.body':
            if grouped:
                raise ExceptionGroup('synthetic disconnect', [OSError('synthetic socket closed')])
            raise OSError('synthetic socket closed')

    scope = {
        'type': 'http',
        'asgi': {'version': '3.0', 'spec_version': '2.4'},
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'query_string': b'',
        'headers': [],
    }
    await app(scope, body_then_wait(), send)
    assert [e['outcome'] for e in terminals(capsys)] == ['client_cancelled']


@pytest.mark.asyncio
async def test_retained_straggler_cannot_suppress_typed_deadline(monkeypatch, capsys):
    from utils.llm.desktop_gemini_telemetry import get_proxy_telemetry

    monkeypatch.setattr(lifetime, 'REQUEST_TIMEOUT_SECONDS', 0.03)
    monkeypatch.setattr(lifetime, 'CANCEL_GRACE_SECONDS', 0.01)
    release, completed = asyncio.Event(), asyncio.Event()
    messages = []

    async def app(scope, receive, send):
        request = Request(scope, receive)
        await request.body()
        get_proxy_telemetry(request, streaming=False).phase = 'gateway'
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue
        try:
            await Response(b'late')(scope, receive, send)
        finally:
            completed.set()

    async def send(message):
        messages.append(message)

    scope = {
        'type': 'http',
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'headers': [],
    }
    try:
        await lifetime.DesktopProxyDeadlineMiddleware(app)(scope, body_then_wait(), send)
        start = next(m for m in messages if m['type'] == 'http.response.start')
        assert start['status'] == 504
        assert dict(start['headers'])[b'x-omi-retryable'] == b'false'
        assert [e['outcome'] for e in terminals(capsys)] == ['provider_timeout']
    finally:
        release.set()
        await asyncio.wait_for(completed.wait(), timeout=3.0)
    assert sum(m['type'] == 'http.response.start' for m in messages) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('outer', [False, True])
async def test_unsent_headers_do_not_suppress_typed_timeout(monkeypatch, capsys, outer):
    from utils.llm.desktop_gemini_telemetry import ProxyTelemetry, get_proxy_telemetry

    monkeypatch.setattr(lifetime, 'REQUEST_TIMEOUT_SECONDS', 0.2)
    monkeypatch.setattr(lifetime, 'CANCEL_GRACE_SECONDS', 0.02)
    messages = []
    starts = 0

    async def send(message):
        nonlocal starts
        if message['type'] == 'http.response.start':
            starts += 1
            if starts == 1:
                await asyncio.Event().wait()
        messages.append(message)

    scope = {
        'type': 'http',
        'asgi': {'spec_version': '2.4'},
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'headers': [],
    }
    if outer:

        async def app(scope, receive, send):
            get_proxy_telemetry(Request(scope, receive), streaming=False).phase = 'gateway'
            await Response(b'provider response')(scope, receive, send)

        owner = lifetime.DesktopProxyDeadlineMiddleware(app)
    else:

        async def chunks():
            yield b'data: {}\n\n'

        state = ProxyTelemetry(Request(scope), streaming=True)
        state.phase = 'body'
        state.request_deadline = asyncio.get_running_loop().time() + 0.2
        owner = lifetime.DeadlinedStreamingResponse(StreamingResponse(chunks()), state)
    await owner(scope, body_then_wait(), send)
    assert [m['status'] for m in messages if m['type'] == 'http.response.start'] == [504]
    assert dict(messages[0]['headers'])[b'x-omi-retryable'] == b'false'
    assert [e['outcome'] for e in terminals(capsys)] == ['provider_timeout']


@pytest.mark.asyncio
async def test_outer_deadline_settles_attempt_before_route_cancellation(monkeypatch, capsys):
    from utils.llm import desktop_gemini_telemetry as tm
    from utils.llm.managed_spend_ledger import build_managed_attempt_event

    monkeypatch.setattr(lifetime, 'REQUEST_TIMEOUT_SECONDS', 0.2)
    monkeypatch.setattr(lifetime, 'CANCEL_GRACE_SECONDS', 0.02)
    attempts = []
    monkeypatch.setattr(tm, 'schedule_managed_attempt', attempts.append)

    async def app(scope, receive, send):
        state = tm.get_proxy_telemetry(Request(scope, receive), streaming=False)
        state.uid = 'synthetic-user'
        state.phase = 'connect'
        state.note_dispatch(tm.UpstreamRoute('https://provider.invalid', {}, {}, 'ai_studio', 'server', 'us'))
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            state.complete(outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect')
            raise

    messages = []

    async def send(message):
        messages.append(message)

    scope = {
        'type': 'http',
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'headers': [],
    }
    await lifetime.DesktopProxyDeadlineMiddleware(app)(scope, body_then_wait(), send)
    assert len(attempts) == 1
    row = build_managed_attempt_event(attempts[0]).as_dict()
    assert row['outcome'] == 'error'
    assert row['error_class'] == 'provider_timeout'
    assert [e['outcome'] for e in terminals(capsys)] == ['provider_timeout']
    assert messages[0]['status'] == 504


@pytest.mark.asyncio
async def test_simultaneous_success_and_disconnect_preserves_provider_not_request(monkeypatch, capsys):
    from utils.llm import desktop_gemini_telemetry as tm
    from utils.llm.managed_spend_ledger import build_managed_attempt_event

    monkeypatch.setattr(lifetime, 'REQUEST_TIMEOUT_SECONDS', 2.0)
    attempts = []
    monkeypatch.setattr(tm, 'schedule_managed_attempt', attempts.append)
    provider_done = asyncio.Event()
    sent = False
    messages = []

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': b'{}', 'more_body': False}
        await provider_done.wait()
        return {'type': 'http.disconnect'}

    async def app(scope, receive, send):
        request = Request(scope, receive)
        state = tm.get_proxy_telemetry(request, streaming=False)
        state.uid = 'synthetic-user'

        async def handler(request):
            state.phase = 'body'
            state.note_dispatch(tm.UpstreamRoute('https://provider.invalid', {}, {}, 'ai_studio', 'server', 'us'))
            state.complete(outcome='success', status_code=200, retryable=False, upstream_status=200, phase='body')
            provider_done.set()
            return Response(b'success')

        response = await lifetime.run_request(request, handler, state)
        await response(scope, receive, send)

    async def send(message):
        messages.append(message)

    scope = {
        'type': 'http',
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'headers': [],
    }
    await lifetime.DesktopProxyDeadlineMiddleware(app)(scope, receive, send)
    assert not messages, 'the outer owner must not send on a disconnected transport'
    assert len(attempts) == 1
    assert build_managed_attempt_event(attempts[0]).as_dict()['outcome'] == 'success'
    events = terminals(capsys)
    assert [(e['outcome'], e['status_code'], e['upstream_status']) for e in events] == [('client_cancelled', 499, 200)]


@pytest.mark.asyncio
@pytest.mark.parametrize('outer', [False, True])
@pytest.mark.parametrize('cancel', [False, True])
async def test_completed_delivery_survives_cleanup_cancellation(monkeypatch, capsys, outer, cancel):
    from starlette.background import BackgroundTask
    from utils.llm import desktop_gemini_telemetry as tm
    from utils.llm.managed_spend_ledger import build_managed_attempt_event

    budget = 10.0 if cancel else 1.0
    monkeypatch.setattr(lifetime, 'REQUEST_TIMEOUT_SECONDS', budget)
    monkeypatch.setattr(lifetime, 'CANCEL_GRACE_SECONDS', 0.02)
    attempts = []
    monkeypatch.setattr(tm, 'schedule_managed_attempt', attempts.append)
    delivered, cleanup_started = asyncio.Event(), asyncio.Event()

    async def cleanup():
        cleanup_started.set()
        await asyncio.Event().wait()

    scope = {
        'type': 'http',
        'asgi': {'spec_version': '2.4'},
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'headers': [],
    }
    state = tm.get_proxy_telemetry(Request(scope), streaming=not outer)
    state.uid = 'synthetic-user'
    state.defer_terminal = True
    state.request_deadline = asyncio.get_running_loop().time() + budget
    state.phase = 'body'
    state.note_dispatch(tm.UpstreamRoute('https://provider.invalid', {}, {}, 'ai_studio', 'server', 'us'))
    state.complete(outcome='success', status_code=200, retryable=False, upstream_status=200, phase='body')

    async def chunks():
        yield b'success'

    async def app(scope, receive, send):
        await Response(b'success', background=BackgroundTask(cleanup))(scope, receive, send)

    owner = (
        lifetime.DesktopProxyDeadlineMiddleware(app)
        if outer
        else lifetime.DeadlinedStreamingResponse(StreamingResponse(chunks(), background=BackgroundTask(cleanup)), state)
    )

    async def send(message):
        if message['type'] == 'http.response.body' and not message.get('more_body', False):
            delivered.set()

    task = asyncio.create_task(owner(scope, body_then_wait(), send))
    await asyncio.wait_for(delivered.wait(), timeout=3)
    await asyncio.wait_for(cleanup_started.wait(), timeout=3)
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await asyncio.wait_for(task, timeout=3)
    if not outer:
        state.flush_terminal()
    assert [(e['outcome'], e['status_code']) for e in terminals(capsys)] == [('success', 200)]
    assert len(attempts) == 1
    assert build_managed_attempt_event(attempts[0]).as_dict()['outcome'] == 'success'


@pytest.mark.asyncio
@pytest.mark.parametrize('silent_return', [False, True])
async def test_disconnect_during_delivery_has_one_receive_owner(lifetime_app, monkeypatch, capsys, silent_return):
    from utils.llm import desktop_gemini_telemetry as tm
    from utils.llm.managed_spend_ledger import build_managed_attempt_event

    attempts = []
    monkeypatch.setattr(tm, 'schedule_managed_attempt', attempts.append)
    disconnected, sending = asyncio.Event(), asyncio.Event()
    sent = False
    receiving = False

    async def receive():
        nonlocal sent, receiving
        assert not receiving, 'only the outer owner may receive from the server'
        receiving = True
        try:
            if not sent:
                sent = True
                return {'type': 'http.request', 'body': b'{}', 'more_body': False}
            await disconnected.wait()
            return {'type': 'http.disconnect'}
        finally:
            receiving = False

    async def provider(*args, **kwargs):
        state = kwargs['telemetry']
        state.uid = 'synthetic-user'
        state.note_dispatch(tm.UpstreamRoute('https://provider.invalid', {}, {}, 'ai_studio', 'server', 'us'))
        state.complete(outcome='success', status_code=200, retryable=False, phase='gateway')
        return Response(b'success')

    monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)

    async def send(message):
        if message['type'] == 'http.response.body':
            sending.set()
            if silent_return:
                # Uvicorn 0.30.5 returns normally after a socket disconnect.
                disconnected.set()
                await asyncio.sleep(0)
                return
            await asyncio.Event().wait()

    scope = {
        'type': 'http',
        'asgi': {'spec_version': '2.3'},
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'query_string': b'',
        'headers': [],
    }
    task = asyncio.create_task(lifetime_app(scope, receive, send))
    await asyncio.wait_for(sending.wait(), timeout=3)
    disconnected.set()
    await asyncio.wait_for(task, timeout=1)
    assert [(e['outcome'], e['status_code']) for e in terminals(capsys)] == [('client_cancelled', 499)]
    assert len(attempts) == 1
    assert build_managed_attempt_event(attempts[0]).as_dict()['outcome'] == 'success'


@pytest.mark.asyncio
async def test_disconnect_during_byok_validation_cancels_before_route(lifetime_app, monkeypatch, capsys):
    from utils import byok

    validating, disconnected, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    sent = False

    async def validate(*args, **kwargs):
        validating.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(byok, 'run_blocking', validate)

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': b'{}', 'more_body': False}
        await disconnected.wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        raise AssertionError('disconnected authorization must not deliver a response')

    scope = {
        'type': 'http',
        'asgi': {'spec_version': '2.3'},
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'query_string': b'',
        'headers': [(b'x-byok-gemini', b'synthetic'), (b'authorization', b'Bearer synthetic')],
    }
    task = asyncio.create_task(lifetime_app(scope, receive, send))
    await asyncio.wait_for(validating.wait(), timeout=3)
    disconnected.set()
    await asyncio.wait_for(task, timeout=1)
    assert cancelled.is_set()
    assert [(e['outcome'], e['status_code']) for e in terminals(capsys)] == [('client_cancelled', 499)]


@pytest.mark.asyncio
async def test_server_completion_disconnect_does_not_undo_delivery(lifetime_app, monkeypatch, capsys):
    completed = asyncio.Event()
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': b'{}', 'more_body': False}
        await completed.wait()
        return {'type': 'http.disconnect'}

    async def provider(*args, **kwargs):
        kwargs['telemetry'].complete(outcome='success', status_code=200, retryable=False, phase='gateway')
        return Response(b'success')

    monkeypatch.setattr(desktop_proxy, '_proxy_via_gateway', provider)

    async def send(message):
        if message['type'] == 'http.response.body' and not message.get('more_body', False):
            completed.set()

    # Exercise the actual completion wakeup, as Uvicorn does on its final send.
    scope = {
        'type': 'http',
        'asgi': {'spec_version': '2.3'},
        'method': 'POST',
        'path': '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        'query_string': b'',
        'headers': [],
    }
    await lifetime_app(scope, receive, send)
    assert [(e['outcome'], e['status_code']) for e in terminals(capsys)] == [('success', 200)]
