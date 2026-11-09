"""Request-scoped custody fences; no upload state survives in a process cache."""

from contextvars import ContextVar
from functools import wraps
import json
import logging

from fastapi import HTTPException

from config import record_seal_rules as lease
from database import record_custody_append, record_token_lease_metrics, record_audio
from utils.executors import db_executor, sync_executor, run_blocking

logger = logging.getLogger(__name__)
_upload = ContextVar('record_custody_upload', default=None)


def accepted_response(response):
    if response is None or not 200 <= response.status_code < 300:
        return False
    # A capped upload deliberately answers 202/failed so the WAL retries. It
    # is a refusal, not a durable append acceptance.
    return json.loads(response.body).get('status') != 'failed'


def custody_upload(fn):
    @wraps(fn)
    async def run(*args, **kwargs):
        if lease.token_lease_mode() == 'off':
            return await fn(*args, **kwargs)
        state = {}
        token = _upload.set(state)
        response = None
        try:
            response = await fn(*args, **kwargs)
            return response
        finally:
            try:
                accepted = bool(state.get('durable') and accepted_response(response))
                if state.get('session'):
                    try:
                        await run_blocking(
                            db_executor,
                            record_custody_append.finish,
                            state['uid'],
                            state['cid'],
                            state['session'],
                            accepted=accepted,
                        )
                    except record_custody_append.RecordCustodyFenceLost:
                        if not accepted:
                            raise
                        await run_blocking(
                            db_executor,
                            record_custody_append.recover_committed,
                            state['uid'],
                            state['cid'],
                            state['session'],
                        )
                        logger.warning('event=record_token_lease_completion outcome=recovered_lost_fence')
                    if accepted_response(response) and not state.get('durable') and not state.get('no_append'):
                        raise HTTPException(
                            status_code=503, detail='Retain local audio until durable custody is available'
                        )
                elif accepted and state.get('shadow_late'):
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


async def begin_upload(uid, cid, job_id):
    state = _upload.get()
    if state is None or not isinstance(cid, str) or not cid:
        return
    state.update(uid=uid, cid=cid)
    if not lease.token_lease_serving(uid):
        state['shadow_late'] = await run_blocking(db_executor, record_custody_append.late_snapshot, uid, cid)
        return
    # Retain the exact candidate even if the commit response is lost.
    state['session'] = 'custody:' + job_id
    try:
        acquired = await run_blocking(db_executor, record_custody_append.begin, uid, cid, state['session'])
    except Exception as error:
        raise HTTPException(status_code=503, detail='Retain local audio and retry custody admission') from error
    if not acquired:
        state.pop('session')


def stored(paths, archives):
    state = _upload.get()
    if state is not None and paths and not archives:
        state['no_append'] = True
    if state is not None and paths and len(paths) == len(archives):
        state['durable'] = True


async def archive(fn, uid, paths, metadata):
    state = _upload.get()
    if not state or not state.get('session'):
        archived = await run_blocking(sync_executor, fn, uid, paths, metadata)
        if archived and state and state.get('cid'):
            await run_blocking(
                db_executor, record_audio.renew_record_token_lease, uid, state['cid'], source='custody_append'
            )
        return archived
    archived = []
    for path in paths:
        committed = await run_blocking(sync_executor, fn, uid, [path], metadata)
        archived.extend(committed)
        # Only a completed durable file append is a signal. The transactional
        # heartbeat helper coalesces all open producers to lease/2; no timer.
        if committed:
            await run_blocking(
                db_executor, record_audio.renew_record_token_lease, uid, state['cid'], source='custody_append'
            )
    return archived


def owns_upload(uid, cid):
    state = _upload.get()
    return bool(state and state.get('session') and (state.get('uid'), state.get('cid')) == (uid, cid))
