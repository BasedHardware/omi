"""Request-scoped custody fences; no upload state survives in a process cache."""

import asyncio
from concurrent.futures import Future
import contextvars
from contextvars import ContextVar
from functools import wraps
import json
import logging
import threading
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, ParamSpec, TypedDict, TypeVar

from fastapi import HTTPException
from starlette.responses import Response

from config import record_seal_rules as lease
from database import record_custody_append, record_token_lease_metrics, record_audio
from utils.executors import db_executor, sync_executor, run_blocking

logger = logging.getLogger(__name__)


class UploadState(TypedDict, total=False):
    uid: str
    cid: str
    job_id: str
    session: str
    durable: bool
    no_append: bool
    late_observed: bool
    fence: '_Custody'


P = ParamSpec('P')
R = TypeVar('R', bound=Response)
T = TypeVar('T')
Archive = Callable[[str, list[str], dict[str, Any]], list[str]]
_upload: ContextVar[UploadState | None] = ContextVar('record_custody_upload', default=None)


def _submit(executor: Any, fn: Callable[..., T], *args: Any) -> 'Future[T]':
    """Start a custody step on a worker thread; no event loop object owns it."""
    return executor.submit(contextvars.copy_context().run, fn, *args)


async def _wait(future: 'Future[T]') -> T:
    """Await a worker-thread step. Cancellation abandons the wait, never the step.

    Unlike ``run_in_executor``, nothing chains a cancelled waiter back to the
    concurrent future, so a step still queued behind a busy pool is not dropped
    when its request, or its whole event loop, is cancelled.
    """
    loop = asyncio.get_running_loop()
    waiter = loop.create_future()

    def resolve(done: 'Future[T]') -> None:
        if waiter.done():
            return
        if done.cancelled():
            # Only a pool shutdown cancels a queued step; the process is exiting.
            waiter.set_exception(RuntimeError('custody step cancelled by executor shutdown'))
        elif (error := done.exception()) is not None:
            waiter.set_exception(error)
        else:
            waiter.set_result(done.result())

    def settled(done: 'Future[T]') -> None:
        try:
            loop.call_soon_threadsafe(resolve, done)
        except RuntimeError:
            pass  # The loop is gone; the step itself already completed.

    future.add_done_callback(settled)
    try:
        return await waiter
    finally:
        if waiter.cancelled():
            # Nobody reads an abandoned step's result; its owner already logged it.
            future.add_done_callback(lambda done: done.cancelled() or done.exception())


class _Custody:
    """One request's custody fence: begin, per-file archive commits, then finish.

    Every blocking step runs on a worker thread, and whichever thread settles
    the last outstanding step also runs ``finish`` with the true outcome. The
    request coroutine only submits steps and awaits their results. Cancelling
    it, a second cancellation, an AnyIO scope, or shutting down its event loop
    abandons those waits but never a step and never the finish:

    - a cancelled ``begin`` still settles; its thread then clears the token;
    - a cancelled archive still commits; only then is the fence finished, with
      ``accepted=True`` when it committed, so a Pusher drain or seal never sees
      the fence cleared while the new bytes may still land;
    - nothing is left queued on the event loop for its shutdown to cancel.

    Process death is the only way a token outlives its request; it then exits by
    its own lease lapse, like a crashed pod's.
    """

    def __init__(self, uid: str, cid: str, session: str, *, held: bool | None = None) -> None:
        self.uid, self.cid, self.session = uid, cid, session
        self._lock = threading.Lock()
        self._held = held  # None while begin may still commit.
        self._archiving = 0  # Archive commits started and not yet returned.
        self._committed = False  # Some archive commit stored a durable object.
        self._late = False
        self._handed_off = False
        # Set once by the request: its decided (accepted, late) or None if abandoned.
        self._outcome: tuple[bool, bool] | None = None
        self._decided = False
        self._claimed = False
        self.done: Future[None] = Future()

    @property
    def held(self) -> bool:
        return bool(self._held)

    # -- worker-thread steps -------------------------------------------------

    def _acquire(self) -> bool:
        held = True  # A raised commit may still have landed.
        try:
            held = record_custody_append.begin(self.uid, self.cid, self.session)
            return held
        finally:
            with self._lock:
                self._held = held
            self._settle()

    def _archive(self, fn: Archive, uid: str, path: str, metadata: dict[str, Any]) -> tuple[list[str], bool]:
        try:
            committed = fn(uid, [path], metadata)
            observed: dict[str, bool] = {}
            if committed:
                with self._lock:
                    self._committed = True
                # Only a completed durable file append is a signal. The
                # transactional heartbeat helper coalesces open custody tokens
                # to lease/2; no timer.
                record_audio.renew_record_token_lease(
                    uid,
                    self.cid,
                    source='custody_append',
                    session=self.session,
                    late_observation=observed,
                )
                if observed.get('late'):
                    with self._lock:
                        self._late = True
            return committed, bool(observed.get('late'))
        finally:
            with self._lock:
                self._archiving -= 1
            self._settle()

    def _settle(self) -> None:
        with self._lock:
            ready = self._claim()
        if ready:
            self._finish()

    def _claim(self) -> bool:
        # Caller holds the lock. Finish exactly once, and only when no step can
        # still change the outcome or the token.
        if self._claimed or not self._decided or self._held is None or self._archiving:
            return False
        self._claimed = True
        return True

    def _finish(self) -> None:
        try:
            if self._held:
                with self._lock:
                    if self._outcome is None:
                        # Abandoned request: the archive outcome is the truth.
                        accepted, late = self._committed and not self._handed_off, self._late
                    else:
                        accepted, late = self._outcome
                        late |= self._late
                try:
                    record_custody_append.finish(
                        self.uid, self.cid, self.session, accepted=accepted, late_observed=late
                    )
                except record_custody_append.RecordCustodyFenceLost:
                    if not accepted:
                        raise
                    record_custody_append.recover_committed(self.uid, self.cid, self.session)
                    logger.warning('event=record_token_lease_completion outcome=recovered_lost_fence')
                if self._outcome is None:
                    logger.info('event=record_token_lease_completion outcome=abandoned_cleared accepted=%s', accepted)
        except BaseException as error:
            logger.warning(
                'event=record_token_lease_completion outcome=unavailable abandoned=%s exception_type=%s',
                self._outcome is None,
                type(error).__name__,
            )
            self.done.set_exception(error)
        else:
            self.done.set_result(None)

    # -- request side ----------------------------------------------------------

    async def acquire(self) -> bool:
        try:
            future = _submit(db_executor, self._acquire)
        except Exception:
            with self._lock:
                self._held = False  # Never started: no token can exist.
            raise
        return await _wait(future)

    async def archive(self, fn: Archive, uid: str, path: str, metadata: dict[str, Any]) -> tuple[list[str], bool]:
        with self._lock:
            self._archiving += 1
        try:
            future = _submit(sync_executor, self._archive, fn, uid, path, metadata)
        except Exception:
            with self._lock:
                self._archiving -= 1
            raise
        return await _wait(future)

    def hand_off(self) -> None:
        with self._lock:
            self._handed_off = True

    def decide(self, outcome: tuple[bool, bool] | None) -> None:
        """Record the request's outcome (None: abandoned) and finish if settled.

        Synchronous, so it completes even inside a cancelled ``finally``. When a
        step is still running, that step's thread runs finish instead.
        """
        with self._lock:
            if self._decided:
                return
            self._decided, self._outcome = True, outcome
            ready = self._claim()
        if not ready:
            return
        try:
            _submit(db_executor, self._finish)
        except Exception as error:
            # Only a shut-down pool refuses work: the token exits by lease lapse.
            logger.warning(
                'event=record_token_lease_completion outcome=unavailable abandoned=%s exception_type=%s',
                outcome is None,
                type(error).__name__,
            )
            self.done.set_exception(error)


def _custody(state: UploadState | None) -> '_Custody | None':
    """The request's fence, or None when no custody token may exist for it."""
    session = state.get('session') if state is not None else None
    if state is None or not session:
        return None
    fence = state.get('fence')
    if fence is None:
        # A session without a recorded acquisition was acquired by the caller.
        assert 'uid' in state and 'cid' in state  # A fence always has a resolved target.
        fence = state['fence'] = _Custody(state['uid'], state['cid'], session, held=True)
    return fence


def accepted_response(response: Response | None) -> bool:
    if response is None or not 200 <= response.status_code < 300:
        return False
    # A capped upload deliberately answers 202/failed so the WAL retries. It
    # is a refusal, not a durable append acceptance.
    return json.loads(bytes(response.body)).get('status') != 'failed'


async def _complete(state: UploadState, fence: '_Custody | None', response: Response | None) -> None:
    try:
        accepted = bool(state.get('durable') and accepted_response(response))
        if fence is not None:
            await _wait(fence.done)
            if fence.held and accepted_response(response) and not state.get('durable') and not state.get('no_append'):
                raise HTTPException(status_code=503, detail='Retain local audio until durable custody is available')
        elif accepted and state.get('late_observed'):
            record_token_lease_metrics.LATE_APPEND.inc()
    except Exception as error:
        logger.warning(
            'event=record_token_lease_completion outcome=unavailable exception_type=%s', type(error).__name__
        )
        if not state.get('no_append'):
            raise HTTPException(status_code=503, detail='Retain local audio and retry custody admission') from error


def custody_upload(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(fn)
    async def run(*args: P.args, **kwargs: P.kwargs) -> R:
        state: UploadState = {}
        token = _upload.set(state)
        response: Response | None = None
        abandoned = True
        try:
            try:
                result = await fn(*args, **kwargs)
            except Exception:
                abandoned = False
                raise
            abandoned = False
            response = result
            return result
        finally:
            try:
                fence = _custody(state)
                if fence is not None:
                    if abandoned:
                        # Cancelled (or shut down) before deciding: hand the
                        # outcome to the custody threads and wait for nothing.
                        fence.decide(None)
                    else:
                        accepted = bool(state.get('durable') and accepted_response(response))
                        fence.decide((accepted, bool(state.get('late_observed'))))
                if not abandoned:
                    # A repeated cancellation (or an AnyIO scope) interrupts
                    # only this wait; the finish already runs on its thread.
                    await _complete(state, fence, response)
            finally:
                _upload.reset(token)

    return run


async def begin_upload(uid: str, cid: str | None, job_id: str, *, recording_session_id: str | None = None) -> None:
    state = _upload.get()
    if state is None:
        return
    # Keep the job identity even while the target is unknown: record routing
    # may resolve the same session later and must fence it under this request.
    state['job_id'] = job_id
    if not cid and recording_session_id:
        cid = await run_blocking(db_executor, record_custody_append.resolve_target, uid, cid, recording_session_id)
    # An unresolved session preserves the pre-existing archive/admission path;
    # it cannot create a custody append for an unknown conversation. If record
    # routing resolves it later, ``bind_upload_target`` applies this same gate.
    if not isinstance(cid, str) or not cid:
        return
    await bind_upload_target(uid, cid)


async def bind_upload_target(uid: str, cid: str) -> None:
    """Apply the custody gate the first time this upload's record target is known.

    Admission and record routing share one target decision. Sync admission
    calls this when it can resolve the target up front; record routing calls it
    again once it resolves the target itself, because a recording session can
    register between the two reads. The first caller checks the kill switch and
    acquires the fence. Later callers with the same target are no-ops, and a
    different target is refused, so no request reaches record routing unfenced.
    """
    state = _upload.get()
    if state is None or not cid:
        return
    bound = state.get('cid')
    if bound is not None:
        if (state.get('uid'), bound) != (uid, cid):
            raise HTTPException(status_code=503, detail='Retain local audio; upload target changed during admission')
        return
    state.update(uid=uid, cid=cid)
    if lease.token_lease_killed():
        # Kill switch: no unfenced append exists to fall back to. Refuse before
        # any storage write; the phone retains its audio and retries later.
        raise HTTPException(status_code=503, detail='Retain local audio; record custody is paused')
    job_id = state.get('job_id')
    if not job_id:
        # A custody request always begins before it routes. Without its job
        # identity there is no exact fence to acquire, so refuse rather than
        # route this target unfenced.
        raise HTTPException(status_code=503, detail='Retain local audio and retry custody admission')
    # Retain the exact candidate even if the commit response is lost.
    state['session'] = 'custody:' + job_id
    # The fence owns its cleanup: if this request is cancelled while begin is
    # still committing, the worker thread finishes the token itself.
    fence = state['fence'] = _Custody(uid, cid, state['session'])
    try:
        acquired = await fence.acquire()
    except Exception as error:
        raise HTTPException(status_code=503, detail='Retain local audio and retry custody admission') from error
    if not acquired:
        # Refused (sync opt-out or an ineligible owner): no token exists.
        state.pop('session')
        state.pop('fence')


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
        fence = _custody(state)
        if fence is not None:
            fence.hand_off()


async def _renew_after_append(uid: str, cid: str, state: UploadState | None) -> None:
    observed: dict[str, bool] = {}
    await run_blocking(
        db_executor,
        record_audio.renew_record_token_lease,
        uid,
        cid,
        source='custody_append',
        session=None,
        late_observation=observed,
    )
    if state is not None and observed.get('late'):
        # Keep every durable file's observation even if another append reopens
        # the row before this request finishes. Acceptance/receipt counts once.
        state['late_observed'] = True


async def archive(fn: Archive, uid: str, paths: list[str], metadata: dict[str, Any]) -> list[str]:
    state = _upload.get()
    cid = state.get('cid') if state is not None else None
    fence = _custody(state)
    if fence is None:
        archived = await run_blocking(sync_executor, fn, uid, paths, metadata)
        if archived and cid:
            await _renew_after_append(uid, cid, state)
        return archived
    assert state is not None
    archived = []
    for path in paths:
        # Each file commits, and renews its fence, on the custody's own thread.
        committed, late = await fence.archive(fn, uid, path, metadata)
        archived.extend(committed)
        if late:
            state['late_observed'] = True
    return archived


def owns_upload(uid: str, cid: str) -> bool:
    state = _upload.get()
    return bool(state and state.get('session') and (state.get('uid'), state.get('cid')) == (uid, cid))
