"""Request-scoped custody fences; no upload state survives in a process cache."""

from contextvars import ContextVar
from functools import wraps
import json
import logging
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
    session: str
    durable: bool
    no_append: bool
    late_observed: bool


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


def custody_upload(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(fn)
    async def run(*args: P.args, **kwargs: P.kwargs) -> R:
        if lease.token_lease_mode() == 'off':
            return await fn(*args, **kwargs)
        state: UploadState = {}
        token = _upload.set(state)
        response: Response | None = None
        try:
            result = await fn(*args, **kwargs)
            response = result
            return result
        finally:
            try:
                accepted = bool(state.get('durable') and accepted_response(response))
                session = state.get('session')
                if session:
                    assert 'uid' in state and 'cid' in state  # A fence always has a resolved target.
                    try:
                        await run_blocking(
                            db_executor,
                            record_custody_append.finish,
                            state['uid'],
                            state['cid'],
                            session,
                            accepted=accepted,
                            late_observed=bool(state.get('late_observed')),
                        )
                    except record_custody_append.RecordCustodyFenceLost:
                        if not accepted:
                            raise
                        await run_blocking(
                            db_executor,
                            record_custody_append.recover_committed,
                            state['uid'],
                            state['cid'],
                            session,
                        )
                        logger.warning('event=record_token_lease_completion outcome=recovered_lost_fence')
                    if accepted_response(response) and not state.get('durable') and not state.get('no_append'):
                        raise HTTPException(
                            status_code=503, detail='Retain local audio until durable custody is available'
                        )
                elif accepted and state.get('late_observed'):
                    record_token_lease_metrics.LATE_APPEND.inc()
            except Exception as error:
                logger.warning(
                    'event=record_token_lease_completion outcome=unavailable exception_type=%s', type(error).__name__
                )
                if not state.get('no_append'):
                    raise HTTPException(
                        status_code=503, detail='Retain local audio and retry custody admission'
                    ) from error
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
    state['session'] = 'custody:' + job_id
    try:
        acquired = await run_blocking(db_executor, record_custody_append.begin, uid, cid, state['session'])
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


async def _renew_after_append(uid: str, cid: str, state: UploadState | None) -> None:
    observed: dict[str, bool] = {}
    await run_blocking(
        db_executor,
        record_audio.renew_record_token_lease,
        uid,
        cid,
        source='custody_append',
        session=state.get('session') if state is not None else None,
        late_observation=observed,
    )
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
        committed = await run_blocking(sync_executor, fn, uid, [path], metadata)
        archived.extend(committed)
        # Only a completed durable file append is a signal. The transactional
        # heartbeat helper coalesces open custody tokens to lease/2; no timer.
        if committed:
            await _renew_after_append(uid, cid, state)
    return archived


def owns_upload(uid: str, cid: str) -> bool:
    state = _upload.get()
    return bool(state and state.get('session') and (state.get('uid'), state.get('cid')) == (uid, cid))
