"""One route-entry budget, bounded uploads and cancellation-safe ASGI disconnects."""

import asyncio
import json

import anyio
from collections.abc import Awaitable
from typing import Any, TypeVar

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.requests import ClientDisconnect

REQUEST_TIMEOUT_SECONDS = 90.0
UPLOAD_TIMEOUT_SECONDS = 30.0
UPLOAD_IDLE_SECONDS = 10.0
MAX_BODY_BYTES = 5 * 1024 * 1024
CANCEL_GRACE_SECONDS = 1.0
T = TypeVar('T')
_cleanup_tasks: set[asyncio.Task] = set()


class ClientDisconnected(Exception):
    pass


class UploadTimeout(Exception):
    pass


async def read_body(request: Request, *, max_bytes: int = MAX_BODY_BYTES) -> bytes:
    length = request.headers.get('content-length')
    if length is not None:
        if not length.isascii() or not length.isdigit():
            raise HTTPException(status_code=400, detail='Content-Length must be a non-negative integer')
        if int(length) > max_bytes:
            raise HTTPException(status_code=413, detail='Request body is too large')
    body = bytearray()
    iterator = request.stream().__aiter__()
    try:
        async with asyncio.timeout(UPLOAD_TIMEOUT_SECONDS):
            while True:
                try:
                    async with asyncio.timeout(UPLOAD_IDLE_SECONDS):
                        chunk = await anext(iterator)
                except StopAsyncIteration:
                    break
                if len(body) + len(chunk) > max_bytes:
                    raise HTTPException(status_code=413, detail='Request body is too large')
                body.extend(chunk)
    except TimeoutError as exc:
        raise UploadTimeout from exc
    return bytes(body)


async def _wait_for_disconnect(request: Request) -> None:
    # Only after the upload is drained. is_disconnected() cancels its receive
    # before BaseHTTPMiddleware's task-group checkpoint can deliver a message;
    # that poll also swallows cancellation during watcher cleanup.
    while (await request.receive())['type'] != 'http.disconnect':
        pass


def _retain_cleanup(task: asyncio.Task) -> None:
    _cleanup_tasks.add(task)

    def finished(done: asyncio.Task) -> None:
        _cleanup_tasks.discard(done)
        if not done.cancelled():
            done.exception()

    task.add_done_callback(finished)


async def _drain(*tasks: asyncio.Task) -> bool:
    for task in tasks:
        task.cancel()

    async def drain() -> bool:
        _, pending = await asyncio.wait(tasks, timeout=CANCEL_GRACE_SECONDS)
        for task in tasks:
            if task in pending:
                task.cancel()
                _retain_cleanup(task)
            elif not task.cancelled():
                task.exception()
        return not pending

    cleanup = asyncio.create_task(drain(), name='desktop-gemini-cleanup')
    _retain_cleanup(cleanup)
    # Shield both AnyIO level cancellation (StreamingResponse task groups) and
    # asyncio edge cancellation. An interrupted owner leaves a retained, bounded
    # cleanup task that still cancels/retrieves every child.
    with anyio.CancelScope(shield=True):
        return await asyncio.shield(cleanup)


async def cancel_on_disconnect(request: Request, awaitable: Awaitable[T]) -> T:
    if getattr(getattr(request, 'state', None), 'desktop_proxy_lifetime_active', False):
        return await awaitable

    async def work() -> T:
        return await awaitable

    task = asyncio.create_task(work(), name='desktop-gemini-work')
    disconnect = asyncio.create_task(_wait_for_disconnect(request), name='desktop-gemini-disconnect')
    try:
        done, _ = await asyncio.wait((task, disconnect), return_when=asyncio.FIRST_COMPLETED)
        if disconnect in done:
            await disconnect
            raise ClientDisconnected
        return await task
    finally:
        await _drain(task, disconnect)


def _deadline_outcome(phase: str) -> str:
    if phase == 'upload':
        return 'upload_timeout'
    if phase in {'authorization', 'validation', 'reservation', 'metering', 'routing', 'credential'}:
        return 'pre_provider_deadline'
    return 'provider_timeout'


def deadline_response(telemetry: Any, *, outcome: str, status: int = 504) -> JSONResponse:
    telemetry.fail_request(outcome=outcome, status_code=status, retryable=False, phase=telemetry.phase)
    return JSONResponse(
        status_code=status,
        headers={
            'X-Request-Id': telemetry.request_id,
            'X-Omi-Request-Id': telemetry.request_id,
            'X-Omi-Provider': telemetry.provider,
            'X-Omi-Error-Class': outcome,
            'X-Omi-Failure-Phase': telemetry.phase,
            'X-Omi-Retryable': 'false',
        },
        content={'error': outcome, 'request_id': telemetry.request_id, 'retryable': False},
    )


async def run_request(request: Request, handler: Any, telemetry: Any):
    """Include upload, dependencies, admission, provider and buffered response reads."""
    deadline = getattr(telemetry, 'request_deadline', asyncio.get_running_loop().time() + REQUEST_TIMEOUT_SECONDS)
    telemetry.request_deadline = deadline

    async def work():
        telemetry.phase = 'upload'
        # Cache the bounded body before auth/admission so the disconnect reader
        # never competes with an upload reader, even while dependencies stall.
        body = await read_body(request)
        delivered = False

        async def replay_body():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return await request.receive()

        bounded_request = Request(request.scope, receive=replay_body)
        telemetry.phase = 'authorization'

        async def invoke():
            request.state.desktop_proxy_lifetime_active = True
            try:
                return await handler(bounded_request)
            finally:
                request.state.desktop_proxy_lifetime_active = False

        return await cancel_on_disconnect(request, invoke())

    task = asyncio.create_task(work(), name='desktop-gemini-request')
    try:
        done, _ = await asyncio.wait((task,), timeout=max(0, deadline - asyncio.get_running_loop().time()))
        if not done:
            outcome = _deadline_outcome(telemetry.phase)
            # Classify before cancellation reaches provider-specific finally/except
            # blocks, which otherwise mistake our deadline for client cancellation.
            return deadline_response(telemetry, outcome=outcome)
        return await task
    except UploadTimeout:
        return deadline_response(telemetry, outcome='upload_timeout')
    except (ClientDisconnected, ClientDisconnect):
        return deadline_response(telemetry, outcome='client_cancelled', status=499)
    except asyncio.CancelledError:
        telemetry.complete(outcome='client_cancelled', status_code=499, retryable=False, phase=telemetry.phase)
        raise
    finally:
        await _drain(task)


async def _close_stream_after(task: asyncio.Task | None, iterator) -> None:
    if task is not None:
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if not task.done():
                raise
        except Exception:
            pass
    close = getattr(iterator, 'aclose', None)
    if close is not None:
        async with asyncio.timeout(CANCEL_GRACE_SECONDS):
            await close()


async def _finish_stream(task: asyncio.Task | None, iterator) -> None:
    # Retain closure until the active read/send has stopped. Never race aclose
    # against an anext that ignored cancellation; the response owner still ends
    # promptly while its retained cleanup owns the straggler.
    async def drain_and_close():
        if task is not None:
            await _drain(task)
        await _close_stream_after(task, iterator)

    # Schedule both stages before the first cancellable await by the owner.
    cleanup = asyncio.create_task(drain_and_close(), name='desktop-gemini-stream-close')
    _retain_cleanup(cleanup)
    with anyio.CancelScope(shield=True):
        await asyncio.wait((cleanup,), timeout=CANCEL_GRACE_SECONDS)


class DeadlinedStreamingResponse(StreamingResponse):
    """Supervise response iteration AND send/backpressure with the entry budget."""

    def __init__(self, response: StreamingResponse, telemetry: Any) -> None:
        super().__init__(response.body_iterator, status_code=response.status_code, background=response.background)
        self.raw_headers = response.raw_headers
        self.telemetry = telemetry

    async def __call__(self, scope, receive, send) -> None:
        telemetry = self.telemetry
        started = False
        finished = False

        class ResponseDeadline(Exception):
            pass

        async def guarded_send(message):
            nonlocal started, finished
            if asyncio.get_running_loop().time() >= telemetry.request_deadline:
                raise ResponseDeadline
            await send(message)
            if message['type'] == 'http.response.start':
                started = True
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                finished = True

        async def expired_response():
            telemetry.fail_request(outcome='provider_timeout', status_code=504, retryable=False, phase='body')
            if not started:
                await deadline_response(telemetry, outcome='provider_timeout')(scope, receive, send)
                return
            event = {
                'error': 'provider_timeout',
                'phase': 'body',
                'request_id': telemetry.request_id,
                'retryable': False,
            }
            await send(
                {
                    'type': 'http.response.body',
                    'body': ('\n\ndata: ' + json.dumps(event, separators=(',', ':')) + '\n\n').encode(),
                    'more_body': False,
                }
            )

        # A task can finish inside asyncio.wait(timeout=0), so never dispatch
        # an already-expired stream. Check every send too, including ready chunks.
        remaining = telemetry.request_deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            try:
                async with asyncio.timeout(CANCEL_GRACE_SECONDS):
                    await expired_response()
            finally:
                await _finish_stream(None, self.body_iterator)
            return
        task = asyncio.create_task(super().__call__(scope, receive, guarded_send), name='desktop-gemini-stream')
        try:
            done, _ = await asyncio.wait((task,), timeout=remaining)
            if done:
                try:
                    await task
                    if not finished:
                        telemetry.fail_request(outcome='client_cancelled', status_code=499, phase='client_disconnect')
                    else:
                        telemetry.complete(
                            outcome='success', status_code=self.status_code, retryable=False, phase='body'
                        )
                    return
                except* ResponseDeadline:
                    pass
            if finished:
                return
            telemetry.fail_request(outcome='provider_timeout', status_code=504, retryable=False, phase='body')
            if await _drain(task):
                # Headers may be committed. The final error send is bounded too.
                async with asyncio.timeout(CANCEL_GRACE_SECONDS):
                    await expired_response()
        except (asyncio.CancelledError, ClientDisconnect):
            if not finished:
                telemetry.fail_request(
                    outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect'
                )
            raise
        except TimeoutError:
            pass
        finally:
            await _finish_stream(task, self.body_iterator)


class DesktopProxyDeadlineMiddleware:
    """Outermost Gemini-only ASGI owner, including BaseHTTPMiddleware sends."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        path = scope.get('path', '')
        if (
            scope['type'] != 'http'
            or scope.get('method') != 'POST'
            or not path.startswith(('/v1/proxy/gemini/', '/v1/proxy/gemini-stream/'))
        ):
            await self.app(scope, receive, send)
            return
        from utils.llm.desktop_gemini_telemetry import get_proxy_telemetry

        telemetry = get_proxy_telemetry(Request(scope, receive), streaming='/gemini-stream/' in path)
        telemetry.identify(path.split('/gemini-stream/' if '/gemini-stream/' in path else '/gemini/', 1)[-1])
        telemetry.request_deadline = asyncio.get_running_loop().time() + REQUEST_TIMEOUT_SECONDS
        telemetry.defer_terminal = True
        telemetry.phase = 'authorization'
        started = False
        is_sse = False
        fixed_length = False
        finished = False
        status = 500
        override = None
        upload_drained = asyncio.Event()
        disconnected = asyncio.Event()

        class ResponseDeadline(Exception):
            pass

        async def guarded_send(message):
            nonlocal started, status, is_sse, fixed_length, finished
            # Older ASGI servers silently discard sends after disconnect. Let
            # the receive owner observe a queued disconnect before committing.
            await asyncio.sleep(0)
            if disconnected.is_set():
                raise ClientDisconnect
            if asyncio.get_running_loop().time() >= telemetry.request_deadline:
                raise ResponseDeadline
            if message['type'] == 'http.response.start':
                status = message['status']
                headers = dict(message.get('headers', []))
                is_sse = b'text/event-stream' in headers.get(b'content-type', b'')
                fixed_length = b'content-length' in headers
            try:
                await send(message)
            except* OSError as errors:
                raise ClientDisconnect from errors
            if disconnected.is_set():
                raise ClientDisconnect
            if message['type'] == 'http.response.start':
                started = True
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                finished = True

        async def watch_disconnect():
            await upload_drained.wait()
            while (await receive())['type'] != 'http.disconnect':
                pass
            # Uvicorn also returns http.disconnect after successful completion.
            if not finished:
                disconnected.set()

        async def invoke():
            telemetry.phase = 'upload'
            try:
                body = await read_body(Request(scope, receive))
            except UploadTimeout:
                await deadline_response(telemetry, outcome='upload_timeout')(scope, receive, guarded_send)
                return
            except HTTPException as exc:
                telemetry.fail_request(outcome='validation_rejected', status_code=exc.status_code, phase='upload')
                await JSONResponse({'detail': exc.detail}, status_code=exc.status_code)(scope, receive, guarded_send)
                return
            delivered = False
            upload_drained.set()

            async def replay_body():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': body, 'more_body': False}
                await disconnected.wait()
                return {'type': 'http.disconnect'}

            telemetry.phase = 'authorization'
            await self.app(scope, replay_body, guarded_send)

        task = asyncio.create_task(invoke(), name='desktop-gemini-asgi')
        watcher = asyncio.create_task(watch_disconnect(), name='desktop-gemini-asgi-disconnect')
        try:
            remaining = max(0, telemetry.request_deadline - asyncio.get_running_loop().time())
            done, _ = await asyncio.wait((task, watcher), timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
            if watcher in done:
                await watcher
            if disconnected.is_set() and not finished:
                override = dict(outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect')
                telemetry.fail_request(
                    outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect'
                )
                return
            if task in done:
                expired = client_disconnected = False
                try:
                    await task
                except* ClientDisconnect:
                    client_disconnected = True
                except* ResponseDeadline:
                    expired = True
                if client_disconnected and not finished:
                    override = dict(
                        outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect'
                    )
                    return
                if not expired:
                    return
            if finished:
                return
            phase = telemetry.phase
            outcome = _deadline_outcome(phase)
            override = dict(outcome=outcome, status_code=504, retryable=False, phase=phase)
            # Classify an outstanding attempt before cancellation reaches the
            # route. A known provider result remains immutable via complete().
            telemetry.fail_request(outcome=outcome, status_code=504, retryable=False, phase=phase)
            stopped = await _drain(task)
            if not started or stopped:
                async with asyncio.timeout(CANCEL_GRACE_SECONDS):
                    if not started:
                        await deadline_response(telemetry, outcome=outcome)(scope, receive, send)
                    elif not fixed_length:
                        # A partially delivered fixed-length response must be
                        # aborted, not completed with missing bytes.
                        event = {
                            'error': outcome,
                            'phase': phase,
                            'request_id': telemetry.request_id,
                            'retryable': False,
                        }
                        try:
                            await send(
                                {
                                    'type': 'http.response.body',
                                    'body': (
                                        ('\n\ndata: ' + json.dumps(event, separators=(',', ':')) + '\n\n').encode()
                                        if is_sse
                                        else b''
                                    ),
                                    'more_body': False,
                                }
                            )
                        except (OSError, RuntimeError):
                            pass
        except (asyncio.CancelledError, ClientDisconnect):
            if not finished:
                override = dict(outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect')
            raise
        except TimeoutError:
            pass
        except Exception:
            if override is None and not finished:
                override = dict(outcome='internal_error', status_code=500, retryable=False, phase=telemetry.phase)
            raise
        finally:
            telemetry.flush_terminal(**(override or {}))
            if not telemetry.completed:
                telemetry.complete(
                    outcome='success' if status < 400 else 'authorization_rejected',
                    status_code=status,
                    retryable=False,
                    phase=telemetry.phase,
                )
            await _drain(task, watcher)
