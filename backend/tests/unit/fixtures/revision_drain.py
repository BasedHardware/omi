"""Hermetic Cloud Run revision-drain harness for ASGI apps.

Cloud Run semantics modelled here:

- An instance stays alive only while it has in-flight requests. A request is
  in flight until its final response body chunk is sent; anything the ASGI app
  does after that (FastAPI ``BackgroundTasks``) is outside the request.
- On revision replacement the old revision stops admitting requests, in-flight
  requests drain (bounded by the request timeout), then the idle instance gets
  SIGTERM, a grace period (~10 s in production, scaled down here), then SIGKILL.
- Work that outlives its request -- ``start_background_task``,
  ``asyncio.create_task``, ``asyncio.ensure_future``, ``submit_with_context``,
  executor submits, ``BackgroundTasks`` -- is not protected by that drain.

The harness drives the app with a minimal in-process ASGI client (no sockets,
no cloud) and attributes every asyncio task and ``ThreadPoolExecutor.submit``
created while a request is running to that request, via a context variable that
tasks and ``run_blocking``/``submit_with_context`` already propagate. When a
request's response completes, each child still running is classified
``fire_and_forget``; children already finished are ``request_scoped``.

Threads cannot be killed in-process. At SIGKILL executor work still running is
reported ``killed`` and ``harness.killed`` is set; fakes that model the paid or
durable boundary can call ``harness.checkpoint()`` to stop like a dead process
would, instead of committing effects afterwards.

Usage::

    async with RevisionDrainHarness(app) as harness:
        request = harness.request('POST', '/route', json={...})
        report = await harness.replace_revision(grace_seconds=0.05)
    assert not report.lost
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

REQUEST = 'request'
TASK = 'task'
EXECUTOR = 'executor'
POST_RESPONSE = 'post_response'

REQUEST_SCOPED = 'request_scoped'
FIRE_AND_FORGET = 'fire_and_forget'

COMPLETED = 'completed'
FAILED = 'failed'
CANCELLED = 'cancelled'
KILLED = 'killed'

_CURRENT_UNIT: contextvars.ContextVar['WorkUnit | None'] = contextvars.ContextVar('revision_drain_unit', default=None)


class RevisionDraining(RuntimeError):
    """The old revision no longer admits requests; Cloud Run routes them elsewhere."""


class ProcessKilled(BaseException):
    """Raised by ``RevisionDrainHarness.checkpoint`` after SIGKILL (a dead process commits nothing)."""


@dataclass
class DrainResponse:
    status_code: int
    headers: list[tuple[bytes, bytes]]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


@dataclass(eq=False)
class WorkUnit:
    kind: str
    label: str
    parent: 'WorkUnit | None' = None
    handle: Any = None
    scope: str | None = None
    outcome: str | None = None
    response: DrainResponse | None = None
    children: list['WorkUnit'] = field(default_factory=list)
    response_done: asyncio.Event | None = None
    is_origin: bool = False
    post_response_recorded: bool = False

    @property
    def name(self) -> str:
        if self.kind == TASK and isinstance(self.handle, asyncio.Task):
            return self.handle.get_name()
        return self.label

    @property
    def done(self) -> bool:
        if self.kind == REQUEST:
            return self.outcome is not None
        return self.handle is not None and self.handle.done()


@dataclass(frozen=True)
class UnitReport:
    name: str
    kind: str
    scope: str
    outcome: str
    parent: str | None

    @property
    def lost(self) -> bool:
        """Fire-and-forget work still running at SIGKILL: the 2026-10-18 failure shape."""
        return self.scope == FIRE_AND_FORGET and self.outcome == KILLED

    @property
    def unprotected(self) -> bool:
        """Outlived its request: survived only if it beat the grace period."""
        return self.scope == FIRE_AND_FORGET


@dataclass(frozen=True)
class DrainReport:
    units: tuple[UnitReport, ...]

    @property
    def lost(self) -> list[UnitReport]:
        return [unit for unit in self.units if unit.lost]

    @property
    def survived_by_luck(self) -> list[UnitReport]:
        return [unit for unit in self.units if unit.unprotected and unit.outcome != KILLED]

    @property
    def killed_requests(self) -> list[UnitReport]:
        return [unit for unit in self.units if unit.kind == REQUEST and unit.outcome == KILLED]

    def named(self, fragment: str) -> list[UnitReport]:
        return [unit for unit in self.units if fragment in unit.name]

    def one(self, fragment: str) -> UnitReport:
        matches = [unit for unit in self.units if unit.name == fragment] or self.named(fragment)
        assert len(matches) == 1, f'expected one unit matching {fragment!r}:\n{self.format()}'
        return matches[0]

    def format(self) -> str:
        rows = [f'{u.kind:<13} {u.scope:<15} {u.outcome:<10} {u.name} (parent={u.parent})' for u in self.units]
        return '\n'.join(rows) or '(no work)'

    def assert_no_lost_work(self) -> None:
        assert not self.lost, f'fire-and-forget work killed at SIGKILL:\n{self.format()}'


def _callable_name(fn: Any, args: tuple) -> str:
    """Best-effort name through MonitoredThreadPoolExecutor/_tracked, partial and Context.run wrappers."""
    for _ in range(8):
        if isinstance(fn, functools.partial):
            fn, args = fn.func, fn.args
            continue
        name = getattr(fn, '__name__', '')
        owner = getattr(fn, '__self__', None)
        if name == '_tracked' and args:
            # The executor wrapper carries task-label and start-event metadata
            # before the wrapped callable's arguments.
            fn, args = args[0], args[3:]
            continue
        if name == 'run' and args and isinstance(owner, contextvars.Context):
            fn, args = args[0], args[1:]
            continue
        break
    return getattr(fn, '__qualname__', None) or getattr(fn, '__name__', None) or repr(fn)


class RevisionDrainHarness:
    def __init__(self, app: Callable, *, host: str = 'revision.test'):
        self.app = app
        self.host = host
        self.admitting = True
        self.killed = threading.Event()
        self.units: list[WorkUnit] = []
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._previous_factory: Any = None
        self._original_submit: Any = None
        self._request_tasks: list[asyncio.Task] = []

    async def __aenter__(self) -> 'RevisionDrainHarness':
        self._loop = asyncio.get_running_loop()
        self._previous_factory = self._loop.get_task_factory()
        self._loop.set_task_factory(self._task_factory)
        self._original_submit = ThreadPoolExecutor.submit
        harness, original = self, self._original_submit

        def submit(executor, fn, /, *args, **kwargs):
            future = original(executor, fn, *args, **kwargs)
            harness._record(EXECUTOR, _callable_name(fn, args), future, _CURRENT_UNIT.get())
            return future

        ThreadPoolExecutor.submit = submit  # type: ignore[method-assign]
        return self

    async def __aexit__(self, *exc_info) -> None:
        ThreadPoolExecutor.submit = self._original_submit  # type: ignore[method-assign]
        assert self._loop is not None
        self._loop.set_task_factory(self._previous_factory)
        leftovers = [t for t in self._request_tasks if not t.done()]
        leftovers += [u.handle for u in self.units if u.kind in (TASK, POST_RESPONSE) and not u.handle.done()]
        for task in leftovers:
            task.cancel()
        if leftovers:
            await asyncio.wait(leftovers, timeout=1)

    # -- attribution -------------------------------------------------------

    def _task_factory(self, loop, coro, **kwargs):
        if self._previous_factory is not None:
            task = self._previous_factory(loop, coro, **kwargs)
        else:
            task = asyncio.Task(coro, loop=loop, **kwargs)
        context = kwargs.get('context')
        parent = context.get(_CURRENT_UNIT) if context is not None else _CURRENT_UNIT.get()
        self._record(TASK, '', task, parent)
        return task

    def _record(self, kind: str, label: str, handle: Any, parent: WorkUnit | None) -> None:
        if parent is None or self.killed.is_set():
            return  # Only work spawned inside an observed request or origin is attributed.
        unit = WorkUnit(kind=kind, label=label, parent=parent, handle=handle)
        with self._lock:
            if parent.is_origin or parent.outcome is not None:
                unit.scope = FIRE_AND_FORGET  # Spawned after the response, or by a non-request origin.
            parent.children.append(unit)
            self.units.append(unit)
        handle.add_done_callback(lambda done: self._settle(unit, done))

    def _settle(self, unit: WorkUnit, handle: Any) -> None:
        with self._lock:
            if unit.outcome is not None:
                return  # Already killed; a zombie thread finishing later changes nothing.
            if handle.cancelled():
                unit.outcome = CANCELLED
            elif handle.exception() is not None:
                unit.outcome = KILLED if isinstance(handle.exception(), ProcessKilled) else FAILED
            else:
                unit.outcome = COMPLETED

    def _close_request(self, unit: WorkUnit, outcome: str) -> None:
        with self._lock:
            if unit.outcome is not None:
                return
            unit.outcome = outcome
            for child in unit.children:
                if child.scope is None:
                    child.scope = REQUEST_SCOPED if child.handle.done() else FIRE_AND_FORGET
        if (
            outcome == COMPLETED
            and unit.handle is not None
            and not unit.handle.done()
            and not unit.post_response_recorded
        ):
            # The final body chunk was sent while the ASGI call is still running
            # (FastAPI BackgroundTasks): record the post-response work now, not
            # at replacement time -- it may complete or raise first, and a
            # later `handle.done()` check would miss it entirely.
            unit.post_response_recorded = True
            self._record(POST_RESPONSE, f'post-response {unit.label}', unit.handle, unit)
        assert unit.response_done is not None
        unit.response_done.set()

    # -- traffic -----------------------------------------------------------

    def request(self, method: str, path: str, *, json: Any = None, headers: dict[str, str] | None = None) -> WorkUnit:
        """Start a request; returns its unit (``await harness.response(unit)`` for the response)."""
        if not self.admitting:
            raise RevisionDraining(path)
        unit = WorkUnit(kind=REQUEST, label=f'{method} {path}', scope=REQUEST_SCOPED)
        unit.response_done = asyncio.Event()
        self.units.append(unit)
        body = b'' if json is None else _json_bytes(json)
        task = asyncio.get_running_loop().create_task(self._serve(unit, method, path, body, headers or {}))
        unit.handle = task
        self._request_tasks.append(task)
        return unit

    async def response(self, unit: WorkUnit) -> DrainResponse:
        assert unit.response_done is not None
        await unit.response_done.wait()
        assert unit.response is not None, f'{unit.label} ended {unit.outcome} without a response'
        return unit.response

    def background_origin(self, label: str) -> contextvars.Token:
        """Attribute work spawned from the current context to a non-request origin (startup loops).

        Everything it spawns is fire-and-forget by definition. Reset with ``_CURRENT_UNIT.reset(token)``
        or use ``harness.origin(label)`` as a context manager.
        """
        origin = WorkUnit(kind='origin', label=label, is_origin=True)
        return _CURRENT_UNIT.set(origin)

    def origin(self, label: str):
        harness = self

        class _Origin:
            def __enter__(self):
                self.token = harness.background_origin(label)

            def __exit__(self, *exc_info):
                _CURRENT_UNIT.reset(self.token)

        return _Origin()

    async def _serve(self, unit: WorkUnit, method: str, path: str, body: bytes, headers: dict[str, str]) -> None:
        _CURRENT_UNIT.set(unit)
        status: dict[str, Any] = {}
        chunks: list[bytes] = []
        delivered = False
        raw_path, _, query = path.partition('?')
        scope = {
            'type': 'http',
            'asgi': {'version': '3.0', 'spec_version': '2.3'},
            'http_version': '1.1',
            'method': method,
            'scheme': 'http',
            'path': raw_path,
            'raw_path': raw_path.encode(),
            'query_string': query.encode(),
            'root_path': '',
            'headers': [(b'host', self.host.encode()), (b'content-length', str(len(body)).encode())]
            + ([(b'content-type', b'application/json')] if body else [])
            + [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            'client': ('127.0.0.1', 50000),
            'server': (self.host, 80),
            'state': {},
        }

        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            assert unit.response_done is not None
            await unit.response_done.wait()
            return {'type': 'http.disconnect'}

        async def send(message):
            if message['type'] == 'http.response.start':
                status['code'] = message['status']
                status['headers'] = list(message.get('headers', []))
            elif message['type'] == 'http.response.body':
                chunks.append(message.get('body', b''))
                if not message.get('more_body', False):
                    unit.response = DrainResponse(status['code'], status['headers'], b''.join(chunks))
                    self._close_request(unit, COMPLETED)

        try:
            await self.app(scope, receive, send)
        except asyncio.CancelledError:
            self._close_request(unit, KILLED)
            raise
        except ProcessKilled:
            self._close_request(unit, KILLED)
        except Exception:
            self._close_request(unit, FAILED)  # Starlette already sent its 500; keep the task quiet.
        else:
            self._close_request(unit, FAILED)  # No-op when the response completed.

    # -- revision replacement ---------------------------------------------

    def checkpoint(self) -> None:
        """Call from fakes at a durable/paid boundary: a SIGKILLed process commits nothing."""
        if self.killed.is_set():
            raise ProcessKilled()

    async def replace_revision(
        self,
        *,
        drain_timeout: float = 2.0,
        grace_seconds: float = 0.05,
        on_sigterm: Callable[[], Awaitable[Any]] | None = None,
    ) -> DrainReport:
        """Stop admitting, drain in-flight requests, SIGTERM, wait the grace period, SIGKILL."""
        self.admitting = False
        requests = [u for u in self.units if u.kind == REQUEST]
        waits = [asyncio.ensure_future(u.response_done.wait()) for u in requests if u.response_done is not None]
        if waits:
            await asyncio.wait(waits, timeout=drain_timeout)
            for waiter in waits:
                waiter.cancel()
        for unit in requests:
            if unit.outcome is None:
                unit.handle.cancel()  # Exceeded the request timeout; Cloud Run kills it.
                self._close_request(unit, KILLED)
            elif not unit.post_response_recorded and not unit.handle.done():
                # Response sent, ASGI call still running (FastAPI BackgroundTasks): outside the request.
                # Usually already recorded eagerly at final-chunk time (see _close_request); this is
                # the belt-and-suspenders path for requests completed while we were draining others.
                unit.post_response_recorded = True
                self._record(POST_RESPONSE, f'post-response {unit.label}', unit.handle, unit)

        if on_sigterm is not None:
            await on_sigterm()
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline and any(not u.done for u in self.units if u.kind != REQUEST):
            await asyncio.sleep(0.005)

        for unit in self.units:
            if unit.kind != REQUEST and unit.handle.done():
                self._settle(unit, unit.handle)  # Done callbacks may still be queued on the loop.
        self.killed.set()
        doomed = []
        with self._lock:
            for unit in self.units:
                if unit.kind == REQUEST or unit.handle.done():
                    continue
                unit.outcome = KILLED
                if unit.scope is None:
                    unit.scope = FIRE_AND_FORGET
                unit.handle.cancel()  # Threads keep running in-process; checkpoint() models their death.
                if isinstance(unit.handle, asyncio.Task):
                    doomed.append(unit.handle)
        if doomed:
            await asyncio.wait(doomed, timeout=1)
        return self.report()

    def report(self) -> DrainReport:
        with self._lock:
            return DrainReport(
                tuple(
                    UnitReport(
                        name=unit.name,
                        kind=unit.kind,
                        scope=unit.scope or REQUEST_SCOPED,
                        outcome=unit.outcome or 'running',
                        parent=unit.parent.label if unit.parent is not None else None,
                    )
                    for unit in self.units
                )
            )


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload).encode()


__all__ = [
    'COMPLETED',
    'DrainReport',
    'DrainResponse',
    'EXECUTOR',
    'FIRE_AND_FORGET',
    'KILLED',
    'POST_RESPONSE',
    'ProcessKilled',
    'REQUEST',
    'REQUEST_SCOPED',
    'RevisionDrainHarness',
    'RevisionDraining',
    'TASK',
    'UnitReport',
]
