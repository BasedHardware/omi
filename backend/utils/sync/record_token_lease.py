"""Request-scoped custody fences; no upload state survives in a process cache.

The fence's lifetime belongs to the storage work, not to the request
(SCA-3748). Every fenced storage step runs on its executor thread to its real
outcome, and only a worker-side completion releases the token: after the
request has closed the fence and every started step has settled, it removes
the request's temp files and runs ``finish`` with the true storage outcome.
Cancelling the request never releases the token. A step that never started is
abandoned. Every fenced commit starts within ``CUSTODY_STORAGE_BUDGET_SECONDS``
of begin and is bounded, so lease-expiry repair cannot race a live writer even
if the process dies before completion.
"""

import asyncio
import contextvars
from concurrent.futures import Executor, Future, InvalidStateError, ThreadPoolExecutor
from contextvars import ContextVar
from functools import wraps
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, ParamSpec, TypedDict, TypeVar

from fastapi import HTTPException
from starlette.responses import Response

from config import record_seal_rules as lease
from database import record_custody_append, record_token_lease_metrics, record_audio
from utils.executors import db_executor, sync_executor, run_blocking

logger = logging.getLogger(__name__)

Settled = Callable[[Future], None]


class _Fence:
    """One request's custody token, released only by its own workers.

    Thread-safe. Steps settle on worker threads (or on the cancelling thread
    for a step that never started). Completion runs once, on ``db_executor``,
    when the fence is closed and no step is pending.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending = 0
        self._closed = False
        self._scheduled = False
        self._began = False
        self._cleanups: list[tuple[Callable[..., Any], tuple[Any, ...]]] = []
        self._outcome: Future[bool] = Future()
        self._context: contextvars.Context | None = None
        self._uid: str | None = None
        self._cid: str | None = None
        self._verdict: bool | None = None
        self._no_append = False
        self.session: str | None = None
        self.deadline: float | None = None
        self.committed = False
        self.late = False

    def begin(self, session: str, deadline: float) -> None:
        with self._lock:
            self._began = True
            self.session = session
            self.deadline = deadline

    def has_work(self, state: 'UploadState') -> bool:
        with self._lock:
            return bool(self._pending or self._cleanups or self.session or state.get('session'))

    def start(
        self,
        executor: Executor,
        fn: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        bounded: bool,
        settled: Settled | None,
    ) -> Future:
        context = contextvars.copy_context()
        deadline = self.deadline if bounded else None

        def call() -> Any:
            if deadline is None:
                return fn(*args, **kwargs)
            with lease.bound_custody_writes(deadline):
                lease.check_custody_write_deadline()
                return fn(*args, **kwargs)

        with self._lock:
            if self._closed:
                raise RuntimeError('custody fence already closed')
            self._pending += 1
        try:
            future = executor.submit(context.run, call)
        except BaseException:
            with self._lock:
                self._pending -= 1
            raise
        future.add_done_callback(lambda done: self._settle(done, settled))
        return future

    def _settle(self, done: Future, settled: Settled | None) -> None:
        with self._lock:
            try:
                if settled is not None:
                    settled(done)
            finally:
                self._pending -= 1
                ready = self._claim()
        if ready:
            self._schedule()

    def begin_settled(self, done: Future) -> None:
        # Begin never ran, or answered inside one transaction with no token of
        # ours. A begin that raised may have committed: finish reconciles it.
        if done.cancelled() or (done.exception() is None and not done.result()):
            self.session = None

    def archive_settled(self, done: Future) -> None:
        if not done.cancelled() and done.exception() is None and done.result():
            self.committed = True

    def observed(self, observation: dict[str, bool]) -> Settled:
        def settled(done: Future) -> None:
            if observation.get('late'):
                self.late = True

        return settled

    def defer(self, cleanup: Callable[..., Any], args: tuple[Any, ...], state: 'UploadState') -> bool:
        """Hand temp-file cleanup to completion while a worker may still read them."""
        with self._lock:
            if self._closed or not (self._pending or self.session or state.get('session')):
                return False
            self._cleanups.append((cleanup, args))
            return True

    def close(self, state: 'UploadState', verdict: bool | None) -> 'Future[bool]':
        """No further steps. ``verdict`` is a live response's acceptance; None if cancelled."""
        with self._lock:
            if not self._closed:
                self._closed = True
                if not self._began:
                    self.session = state.get('session')
                self._uid, self._cid = state.get('uid'), state.get('cid')
                self._verdict = verdict
                self._no_append = bool(state.get('no_append'))
                self.late |= bool(state.get('late_observed'))
                self._context = contextvars.copy_context()
            ready = self._claim()
        if ready:
            self._schedule()
        return self._outcome

    def _claim(self) -> bool:
        if self._closed and not self._pending and not self._scheduled:
            self._scheduled = True
            return True
        return False

    def _schedule(self) -> None:
        assert self._context is not None
        try:
            db_executor.submit(self._context.run, self._complete)
        except Exception as error:
            # Shutdown: the temp files still go. The token waits for lease
            # expiry and repair, which no bounded writer can outlive.
            self._run_cleanups()
            logger.warning('event=record_token_lease_completion outcome=deferred_to_lease')
            self._publish(error=error)

    def _run_cleanups(self) -> None:
        cleanups, self._cleanups = self._cleanups, []
        for cleanup, args in cleanups:
            try:
                cleanup(*args)
            except Exception as error:
                logger.warning(
                    'event=record_token_lease_cleanup outcome=failed exception_type=%s', type(error).__name__
                )

    def _complete(self) -> None:
        # Every started storage step has settled: nothing reads the temp files.
        self._run_cleanups()
        try:
            finished = self._finish()
        except Exception as error:
            if self._verdict is None:
                # A cancelled request has no response to fail; its token waits
                # for lease expiry and repair.
                logger.warning(
                    'event=record_token_lease_completion outcome=unavailable exception_type=%s', type(error).__name__
                )
            self._publish(error=error)
        else:
            self._publish(value=finished)

    def _finish(self) -> bool:
        session = self.session
        if not session:
            return False
        assert self._uid is not None and self._cid is not None  # A fence always has a resolved target.
        # A live request accepts exactly what its response acknowledged. A
        # cancelled one records what storage durably committed: no ACK was sent
        # and the phone retries idempotently (create-only objects).
        accepted = self._verdict if self._verdict is not None else self.committed and not self._no_append
        try:
            record_custody_append.finish(self._uid, self._cid, session, accepted=accepted, late_observed=self.late)
        except record_custody_append.RecordCustodyFenceLost:
            if not accepted:
                raise
            record_custody_append.recover_committed(self._uid, self._cid, session)
            logger.warning('event=record_token_lease_completion outcome=recovered_lost_fence')
        return True

    def _publish(self, *, value: bool = False, error: BaseException | None = None) -> None:
        try:
            if error is None:
                self._outcome.set_result(value)
            else:
                self._outcome.set_exception(error)
        except InvalidStateError:
            pass  # The live request was cancelled while waiting; nobody reads it.


class UploadState(TypedDict, total=False):
    uid: str
    cid: str
    session: str
    durable: bool
    no_append: bool
    late_observed: bool
    fence: _Fence


P = ParamSpec('P')
R = TypeVar('R', bound=Response)
Archive = Callable[[str, list[str], dict[str, Any]], list[str]]
_upload: ContextVar[UploadState | None] = ContextVar('record_custody_upload', default=None)


def accepted_response(response: Response | None) -> bool:
    if response is None or not 200 <= response.status_code < 300:
        return False
    # A capped upload deliberately answers 202/failed so the WAL retries. It
    # is a refusal, not a durable append acceptance.
    return json.loads(bytes(response.body)).get('status') != 'failed'


def _fence(state: UploadState) -> _Fence:
    fence = state.get('fence')
    if fence is None:
        fence = state['fence'] = _Fence()
    return fence


def _owns_work(state: UploadState) -> bool:
    fence = state.get('fence')
    return bool(state.get('session') or (fence is not None and fence.has_work(state)))


async def _fenced(
    state: UploadState,
    executor: Executor,
    fn: Callable[..., Any],
    *args: Any,
    bounded: bool = True,
    settled: Settled | None = None,
    **kwargs: Any,
) -> Any:
    """Run one step the fence outlives. A cancel abandons it only if not started."""
    future = _fence(state).start(executor, fn, args, kwargs, bounded=bounded, settled=settled)
    return await asyncio.wrap_future(future)


async def _close(state: UploadState, response: Response | None) -> None:
    """A live request's completion: wait for the worker's real outcome, answer from it."""
    accepted = bool(state.get('durable') and accepted_response(response))
    try:
        finished = False
        if _owns_work(state):
            finished = await asyncio.wrap_future(_fence(state).close(state, accepted))
        if finished:
            if accepted_response(response) and not state.get('durable') and not state.get('no_append'):
                raise HTTPException(status_code=503, detail='Retain local audio until durable custody is available')
        elif accepted and state.get('late_observed'):
            record_token_lease_metrics.LATE_APPEND.inc()
    except Exception as error:
        logger.warning(
            'event=record_token_lease_completion outcome=unavailable exception_type=%s', type(error).__name__
        )
        if not state.get('no_append'):
            raise HTTPException(status_code=503, detail='Retain local audio and retry custody admission') from error


def _hand_off(state: UploadState) -> None:
    """A cancelled request: never awaits, never releases. Its workers complete."""
    if _owns_work(state):
        _fence(state).close(state, None)


def custody_upload(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(fn)
    async def run(*args: P.args, **kwargs: P.kwargs) -> R:
        if lease.token_lease_mode() == 'off':
            return await fn(*args, **kwargs)
        state: UploadState = {}
        token = _upload.set(state)
        try:
            try:
                response = await fn(*args, **kwargs)
            except Exception:
                await _close(state, None)
                raise
            except BaseException:
                # Cancelled (asyncio, AnyIO scope, shutdown): no response will
                # be delivered, and a repeated cancel must not interrupt us, so
                # nothing here awaits. Started workers settle, then complete.
                _hand_off(state)
                raise
            await _close(state, response)
            return response
        finally:
            _upload.reset(token)

    return run


async def begin_upload(uid: str, cid: str | None, job_id: str, *, recording_session_id: str | None = None) -> None:
    state = _upload.get()
    if state is None:
        return
    if not cid and recording_session_id:
        cid = await run_blocking(db_executor, record_custody_append.resolve_target, uid, cid, recording_session_id)
    # An unresolved session preserves the pre-existing archive/admission path;
    # it cannot create a custody append for an unknown conversation.
    if not isinstance(cid, str) or not cid:
        return
    state.update(uid=uid, cid=cid)
    if not lease.token_lease_serving(uid):
        return
    # Retain the exact candidate even if the commit response is lost.
    session = state['session'] = 'custody:' + job_id
    fence = _fence(state)
    # The storage budget starts before begin stamps the token's lease.
    fence.begin(session, time.monotonic() + lease.CUSTODY_STORAGE_BUDGET_SECONDS)
    try:
        acquired = await _fenced(
            state,
            db_executor,
            record_custody_append.begin,
            uid,
            cid,
            session,
            bounded=False,
            settled=fence.begin_settled,
        )
    except Exception as error:
        raise HTTPException(status_code=503, detail='Retain local audio and retry custody admission') from error
    if not acquired:
        state.pop('session')


def stored(paths: Sequence[str], archives: Sequence[str]) -> None:
    state = _upload.get()
    if state is not None and paths and not archives:
        state['no_append'] = True
    # A nonempty selected subset is a real durable append. Deliberately
    # unselected files retain the route's original admission semantics.
    if state is not None and archives:
        state['durable'] = True


def handoff_committed() -> None:
    """A separate all-file protocol owns this 202, its revision and pending work.

    Clear this wrapper's optional fence as unaccepted; it must neither require
    its cohort archive nor rearm the live partial/provider coordinator.
    """
    state = _upload.get()
    if state is not None:
        state['no_append'] = True
        state['durable'] = False


def after_storage(cleanup: Callable[..., Any], *args: Any) -> None:
    """Run route cleanup (temp files) now, or on the fence's worker once storage settled.

    Synchronous, so a repeated cancel cannot interrupt it. Without a custody
    fence (off, shadow, serve 0%) cleanup runs inline exactly as before.
    """
    state = _upload.get()
    fence = state.get('fence') if state is not None else None
    if state is None or fence is None or not fence.defer(cleanup, args, state):
        cleanup(*args)


async def storage_step(executor: ThreadPoolExecutor, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """One owner storage write (e.g. a late-WAL retained copy) the fence must outlive."""
    state = _upload.get()
    if state is None or not state.get('session'):
        return await run_blocking(executor, fn, *args, **kwargs)
    return await _fenced(state, executor, fn, *args, **kwargs)


async def _renew_after_append(uid: str, cid: str, state: UploadState | None) -> None:
    observed: dict[str, bool] = {}
    kwargs: dict[str, Any] = dict(
        source='custody_append',
        session=state.get('session') if state is not None else None,
        late_observation=observed,
    )
    if state is not None and state.get('session'):
        fence = _fence(state)
        await _fenced(
            state,
            db_executor,
            record_audio.renew_record_token_lease,
            uid,
            cid,
            settled=fence.observed(observed),
            **kwargs,
        )
    else:
        await run_blocking(db_executor, record_audio.renew_record_token_lease, uid, cid, **kwargs)
    if state is not None and observed.get('late'):
        # Keep every durable file's observation even if another append reopens
        # the row before this request finishes. Acceptance/receipt counts once.
        state['late_observed'] = True


async def archive(fn: Archive, uid: str, paths: list[str], metadata: dict[str, Any]) -> list[str]:
    state = _upload.get()
    cid = state.get('cid') if state is not None else None
    if not state or not state.get('session'):
        archived = await run_blocking(sync_executor, fn, uid, paths, metadata)
        if archived and cid:
            await _renew_after_append(uid, cid, state)
        return archived
    assert cid is not None  # The exact upload fence was acquired for this target.
    fence = _fence(state)
    archived = []
    for path in paths:
        # A cancelled request leaves a started worker to commit; the fence
        # records its true outcome before finish (SCA-3748).
        committed = await _fenced(state, sync_executor, fn, uid, [path], metadata, settled=fence.archive_settled)
        archived.extend(committed)
        # Only a completed durable file append is a signal. The transactional
        # heartbeat helper coalesces open custody tokens to lease/2; no timer.
        if committed:
            await _renew_after_append(uid, cid, state)
    return archived


def owns_upload(uid: str, cid: str) -> bool:
    state = _upload.get()
    return bool(state and state.get('session') and (state.get('uid'), state.get('cid')) == (uid, cid))
