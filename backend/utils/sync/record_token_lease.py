"""Request-scoped custody fences; no upload state survives in a process cache."""

import asyncio
import contextvars
from contextvars import ContextVar
from functools import wraps
import json
import logging
import threading
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import Executor
from typing import Any, ParamSpec, TypedDict, TypeVar

import anyio
from fastapi import HTTPException
from starlette.responses import Response

from config import record_seal_rules as lease
from database import record_custody_append, record_token_lease_metrics, record_audio
from utils.executors import db_executor, sync_executor, run_blocking, track_executor_future

logger = logging.getLogger(__name__)


class _Unsettled(RuntimeError):
    """A fenced step never ran or outlived its bound; its token waits for lease expiry."""


class _Step:
    """One blocking custody step whose real outcome the persisted fence must outlive.

    Cancelling the awaiting coroutine never cancels a step that has started: the
    worker thread runs to its true outcome and only then marks the step settled.
    A step that has not started is abandoned atomically, so it can no longer
    touch storage. Settlement is thread-level. The executor future is never
    awaited, so a caller's cancel (or loop teardown) cannot cancel it; only
    executor shutdown can, which abandons a step that never started.
    """

    def __init__(
        self,
        executor: Executor,
        fn: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        abandonable: bool,
    ):
        self._loop = asyncio.get_running_loop()
        self._gate = threading.Lock()
        self._phase = 'queued'  # queued -> running, or queued -> abandoned
        self._abandonable = abandonable
        self._outcome: tuple[bool, Any] | None = None
        self.settled: asyncio.Future[None] = self._loop.create_future()
        context = contextvars.copy_context()

        def call() -> Any:
            return context.run(self._run, fn, args, kwargs)

        try:
            submission = self._loop.run_in_executor(executor, call)
        except Exception as error:  # e.g. the executor already shut down
            self._phase = 'abandoned'
            self._outcome = (False, error)
            self._settle()
            return
        track_executor_future(executor, submission)
        submission.add_done_callback(self._submission_ended)

    def _run(self, fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        with self._gate:
            if self._phase != 'queued':
                raise _Unsettled('abandoned before it started')
            self._phase = 'running'
        try:
            value = fn(*args, **kwargs)
        except BaseException as error:
            self._finish((False, error))
            raise
        self._finish((True, value))
        return value

    def _finish(self, outcome: tuple[bool, Any]) -> None:
        self._outcome = outcome
        try:
            self._loop.call_soon_threadsafe(self._settle)
        except RuntimeError:
            pass  # The loop has closed; nobody is left to wait.

    def _settle(self) -> None:
        if not self.settled.done():
            self.settled.set_result(None)

    def _submission_ended(self, submission: asyncio.Future) -> None:
        error = None if submission.cancelled() else submission.exception()
        with self._gate:
            if self._phase != 'queued':
                return
            # The worker can never start now: executor shutdown cancelled it.
            self._phase = 'abandoned'
            if error is not None:
                self._outcome = (False, error)
        self._settle()

    def abandon(self) -> None:
        with self._gate:
            if self._phase != 'queued' or not self._abandonable:
                return
            self._phase = 'abandoned'
        self._settle()

    def result(self) -> Any:
        if self._outcome is None:
            raise _Unsettled('custody step never ran')
        ok, value = self._outcome
        if ok:
            return value
        raise value


class UploadState(TypedDict, total=False):
    uid: str
    cid: str
    # A token begin may have committed, until begin answers. Only a confirmed
    # session is ownership; a candidate is reconciled, never trusted.
    candidate: str
    session: str
    durable: bool
    no_append: bool
    late_observed: bool
    steps: list[_Step]
    settle_deadline: float
    unsettled: bool
    cancelled: bool


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


async def _wait_settled(state: UploadState, steps: Sequence[_Step]) -> bool:
    """Wait through any cancellation until every step settled; never raises it.

    A cancellation that arrives meanwhile is recorded for the wrapper to
    re-raise. Returns False only after the custody lease bound, when the
    persisted token must stay for lease expiry and repair.
    """
    loop = asyncio.get_running_loop()
    deadline = state.setdefault('settle_deadline', loop.time() + lease.custody_token_lease_seconds())
    # AnyIO re-delivers a scope cancel on every await; shield the wait from it.
    with anyio.CancelScope(shield=True):
        while True:
            for step in steps:
                step.abandon()
            pending = [step.settled for step in steps if not step.settled.done()]
            if not pending:
                return True
            remaining = deadline - loop.time()
            if remaining <= 0:
                return False
            try:
                await asyncio.wait(pending, timeout=remaining)
            except asyncio.CancelledError:
                state['cancelled'] = True
    return False  # Unreachable: the shielded scope above is never itself cancelled.


async def _fenced(state: UploadState, executor: Executor, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run one step the fence owns; a cancelled caller leaves it to settle."""
    step = _Step(executor, fn, args, kwargs, abandonable=True)
    state.setdefault('steps', []).append(step)
    await asyncio.shield(step.settled)
    return step.result()


async def settle_upload() -> None:
    """Hold the caller until every fenced worker settled, e.g. before temp cleanup.

    Never raises a cancellation; the custody wrapper re-raises one after finish.
    """
    state = _upload.get()
    steps = state.get('steps') if state is not None else None
    if state is None or state.get('unsettled') or not steps:
        return
    if not await _wait_settled(state, steps):
        state['unsettled'] = True


async def settle_then(cleanup: Callable[..., None], *args: Any) -> None:
    """Run route cleanup (temp files) only after every fenced worker settled.

    A cancelled request's started archive worker may still read those files.
    Never raises a cancellation; the custody wrapper re-raises it after finish.
    """
    try:
        await settle_upload()
    finally:
        cleanup(*args)


async def _complete(state: UploadState, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    # Completion is never abandoned: a cancelled request still clears its fence.
    step = _Step(db_executor, fn, args, kwargs, abandonable=False)
    if not await _wait_settled(state, [step]):
        raise _Unsettled('custody completion did not settle')
    return step.result()


def _finish_session(state: UploadState, uid: str, cid: str, session: str, accepted: bool) -> bool:
    # Read on the worker as finish starts: a cancel that arrived first means the
    # response was never delivered, so it can never become an accepted receipt.
    return record_custody_append.finish(
        uid,
        cid,
        session,
        accepted=accepted and not state.get('cancelled'),
        late_observed=bool(state.get('late_observed')),
    )


async def _close(state: UploadState, response: Response | None) -> None:
    try:
        await settle_upload()
        if state.get('unsettled'):
            # A worker may still commit audio. Clearing now would let a seal
            # miss it; the persisted token waits for lease expiry and repair.
            raise _Unsettled('custody worker outlived its lease')
        accepted = bool(state.get('durable') and accepted_response(response))
        session = state.get('session')
        candidate = state.get('candidate')
        if session:
            assert 'uid' in state and 'cid' in state  # A fence always has a resolved target.
            try:
                await _complete(state, _finish_session, state, state['uid'], state['cid'], session, accepted)
            except record_custody_append.RecordCustodyFenceLost:
                if not accepted:
                    raise
                await _complete(state, record_custody_append.recover_committed, state['uid'], state['cid'], session)
                logger.warning('event=record_token_lease_completion outcome=recovered_lost_fence')
            if accepted_response(response) and not state.get('durable') and not state.get('no_append'):
                raise HTTPException(status_code=503, detail='Retain local audio until durable custody is available')
        elif candidate:
            # Begin may have committed without answering. Clear that exact token;
            # the request's own response is unchanged by this reconciliation.
            assert 'uid' in state and 'cid' in state
            try:
                await _complete(
                    state, record_custody_append.finish, state['uid'], state['cid'], candidate, accepted=False
                )
            except Exception as error:
                logger.warning(
                    'event=record_token_lease_completion outcome=candidate_unreconciled exception_type=%s',
                    type(error).__name__,
                )
        elif accepted and state.get('late_observed'):
            record_token_lease_metrics.LATE_APPEND.inc()
    except Exception as error:
        logger.warning(
            'event=record_token_lease_completion outcome=unavailable exception_type=%s', type(error).__name__
        )
        # A cancelled request has no response to replace; its cancel propagates.
        if not state.get('cancelled') and not state.get('no_append'):
            raise HTTPException(status_code=503, detail='Retain local audio and retry custody admission') from error


def custody_upload(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(fn)
    async def run(*args: P.args, **kwargs: P.kwargs) -> R:
        if lease.token_lease_mode() == 'off':
            return await fn(*args, **kwargs)
        state: UploadState = {}
        token = _upload.set(state)
        response: Response | None = None
        interrupted = False
        try:
            result = await fn(*args, **kwargs)
            response = result
            return result
        except asyncio.CancelledError:
            # The client is gone, but a started archive worker is not. The
            # fence clears only after it settles, with its true outcome.
            interrupted = state['cancelled'] = True
            raise
        finally:
            try:
                await _close(state, response)
            finally:
                _upload.reset(token)
            if state.get('cancelled') and not interrupted:
                raise asyncio.CancelledError()

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
    # Retain the exact candidate even if the commit response is lost or the
    # request is cancelled while begin is in flight.
    candidate = state['candidate'] = 'custody:' + job_id
    try:
        acquired = await _fenced(state, db_executor, record_custody_append.begin, uid, cid, candidate)
    except Exception as error:
        raise HTTPException(status_code=503, detail='Retain local audio and retry custody admission') from error
    if acquired:
        state['session'] = candidate
    else:
        # Begin answered inside one transaction that saw no token of ours.
        state.pop('candidate')


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


async def _renew_after_append(uid: str, cid: str, state: UploadState | None) -> None:
    observed: dict[str, bool] = {}
    kwargs = dict(
        source='custody_append',
        session=state.get('session') if state is not None else None,
        late_observation=observed,
    )
    if state is not None and state.get('session'):
        await _fenced(state, db_executor, record_audio.renew_record_token_lease, uid, cid, **kwargs)
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
    archived = []
    for path in paths:
        # A cancelled request leaves a started worker to commit; the fence
        # waits for it before finish (SCA-3748).
        committed = await _fenced(state, sync_executor, fn, uid, [path], metadata)
        archived.extend(committed)
        # Only a completed durable file append is a signal. The transactional
        # heartbeat helper coalesces open custody tokens to lease/2; no timer.
        if committed:
            await _renew_after_append(uid, cid, state)
    return archived


def owns_upload(uid: str, cid: str) -> bool:
    state = _upload.get()
    return bool(state and state.get('session') and (state.get('uid'), state.get('cid')) == (uid, cid))
