"""Request lifetime tests use real ASGI receive/cancellation boundaries."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import Response, StreamingResponse

from utils.byok import BYOKMiddleware
from utils.llm import desktop_proxy_lifetime as lifetime

from routers import desktop_proxy


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
    monkeypatch.setattr(lifetime, 'REQUEST_TIMEOUT_SECONDS', 0.08)
    monkeypatch.setattr(lifetime, 'UPLOAD_IDLE_SECONDS', 0.025)
    monkeypatch.setattr(lifetime, 'UPLOAD_TIMEOUT_SECONDS', 0.05)
    app = FastAPI()
    app.add_middleware(BYOKMiddleware)
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
    done, _ = await asyncio.wait((task,), timeout=0.25)
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
    await asyncio.wait_for(stopped.wait(), timeout=0.2)
    assert child.done()
    # The retained drain also retrieves exceptions from abandoned tasks.
    await asyncio.sleep(0)
    assert not lifetime._cleanup_tasks
