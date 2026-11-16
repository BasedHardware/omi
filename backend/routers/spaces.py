"""Default-off HTTP transport for space-scoped cell synchronization."""

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from config import spaces_sync_api
from database.cells import serving
from database.cells._validation import validate_address, validate_id
from database.cells.errors import CellContentionExhausted, CellSpaceUnavailable
from database.cells.feed import CursorAhead, ResyncRequired
from database.cells.mutations import apply_space_mutation, SpaceMutationConflictError, SpaceMutationNotFoundError
from database.directory import router as directory_router
from models.space_sync import (
    SpaceChangesResponse,
    SpaceCursorRequest,
    SpaceCursorResponse,
    SpaceMutationConflictResponse,
    SpaceMutationRequest,
    SpaceMutationResponse,
    SpaceSnapshotResponse,
)
from utils.other import endpoints as auth
from utils.product_metrics import record_product_event

logger = logging.getLogger(__name__)


def _require_enabled():
    if not spaces_sync_api.enabled():
        raise HTTPException(503, detail={'code': 'spaces_sync_api_disabled', 'retryable': False})


class _EnabledSpaceRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def admitted(request: Request):
            # FastAPI parses bodies before dependencies. Check admission before
            # entering that handler so dark POSTs never even receive the body.
            _require_enabled()
            return await handler(request)

        return admitted


router = APIRouter(route_class=_EnabledSpaceRoute)


def _directory_unavailable():
    return HTTPException(503, detail={'code': 'directory_routing_unavailable', 'retryable': True})


def _serving_space(sid: str, uid: str):
    _require_enabled()
    try:
        validate_id(sid)
    except ValueError as error:
        raise HTTPException(404, detail='Space not found') from error
    # The pilot serves personal spaces only, even if another uid has an owner role.
    if sid != uid:
        raise HTTPException(404, detail='Space not found')
    try:
        if not directory_router.routing_active():
            raise _directory_unavailable()
        directory = directory_router.directory_store()
        space = directory.get_space(sid)
        # Owner-only until shared-space role policy lands (W7); a 'member' row grants no sync access.
        member = directory.is_active_owner(sid, uid) if space else False
    except Exception as error:
        raise _directory_unavailable() from error
    if space is None or not member:
        raise HTTPException(404, detail='Space not found')
    if space.cell == 'firestore':
        raise HTTPException(503, detail={'code': 'space_not_cell_served', 'retryable': False})
    cell = getattr(space, 'cell', None)  # Validate malformed driver results at this boundary.
    if not isinstance(cell, str) or cell != serving.CELL_LABEL:
        raise _directory_unavailable()
    return space


@contextmanager
def _cell_errors():
    try:
        yield
    except ResyncRequired as error:
        raise HTTPException(
            425,
            detail=dict(
                code='resync_required',
                reason='cursor_below_floor',
                floor=error.floor,
                epoch=error.epoch,
            ),
        ) from error
    except CursorAhead as error:
        raise HTTPException(
            425,
            detail=dict(
                code='resync_required',
                reason='cursor_ahead_of_head',
                head=error.head,
                epoch=error.epoch,
            ),
        ) from error
    except CellSpaceUnavailable as error:
        raise HTTPException(503, detail={'code': error.code, 'retryable': True}) from error
    except CellContentionExhausted as error:
        raise HTTPException(503, detail={'code': 'cell_contention', 'retryable': True}) from error
    except HTTPException:
        raise
    except Exception as error:
        # Dial/configuration/pool failures can precede the store's typed fence.
        # Exception messages/tracebacks may include document values or SQL args.
        logger.error('Space sync cell operation failed: exception_type=%s', type(error).__name__)
        raise HTTPException(503, detail={'code': 'cell_space_unavailable', 'retryable': True}) from error


def _page_signature(sid: str, since: int, after: list[str]) -> str:
    secret = os.getenv('ENCRYPTION_SECRET', '').encode()
    if len(secret) < 32:
        raise HTTPException(503, detail={'code': 'snapshot_signing_unavailable', 'retryable': False})
    payload = json.dumps(['spaces:snapshot:v1', sid, since, *after], separators=(',', ':')).encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _encode_page_token(token: str, sid: str, since: int) -> str:
    # Store tokens remain internal keysets; the HTTP envelope proves a snapshot was started.
    after = json.loads(base64.b64decode(token, validate=True))
    return base64.b64encode(json.dumps([*after, _page_signature(sid, since, after)]).encode()).decode()


def _decode_page_token(token: str | None, sid: str, since: int) -> tuple[str, str] | None:
    if token is None:
        return None
    try:
        if len(token) > 8192:
            raise ValueError('page token too long')
        after = json.loads(base64.b64decode(token, validate=True))
        if not isinstance(after, list) or len(after) != 3:
            raise ValueError('invalid page token')
        validate_address(*after[:2])
        if not hmac.compare_digest(_page_signature(sid, since, after[:2]), after[2]):
            raise ValueError('invalid page token signature')
        return after[0], after[1]
    except (ValueError, TypeError, UnicodeError, binascii.Error) as error:
        raise HTTPException(422, detail='Invalid page token') from error


def _snapshot_uid(
    sid: str,
    since: int = Query(0, ge=0),
    page_token: str | None = None,
    uid: str = Depends(auth.get_current_user_uid),
) -> str:
    try:
        after = _decode_page_token(page_token, sid, since)
    except HTTPException:
        # Invalid tokens must consume the start budget, never the paging allowance.
        auth.check_rate_limit_inline(uid, 'spaces:snapshot')
        raise
    auth.check_rate_limit_inline(uid, 'spaces:snapshot_page' if after is not None else 'spaces:snapshot')
    return uid


@router.get('/v1/spaces/{sid}/changes', tags=['spaces'], response_model=SpaceChangesResponse)
def changes(
    sid: str,
    cursor: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'spaces:changes')),
):
    _serving_space(sid, uid)
    with _cell_errors():
        page = serving.cell_store().pull(sid, cursor=cursor, limit=limit, now=time.time())
    return dict(
        entries=[asdict(entry) for entry in page.entries],
        rows=[row for row in page.rows.values() if row is not None],
        next_cursor=page.next_cursor,
        head=page.head,
        epoch=page.epoch,
    )


@router.get('/v1/spaces/{sid}/snapshot', tags=['spaces'], response_model=SpaceSnapshotResponse)
def snapshot(
    sid: str,
    limit: int = Query(200, ge=1, le=500),
    since: int = Query(0, ge=0),
    page_token: str | None = None,
    uid: str = Depends(_snapshot_uid),
):
    """Set the post-snapshot cursor to page 1's head, never the last page's head.
    Restart the snapshot if epoch changes between pages; then pull from that
    first head to catch concurrent updates, including rows on earlier pages.
    Apply rows and deletion entries on every page, including snapshot?since.
    """
    _serving_space(sid, uid)
    after = _decode_page_token(page_token, sid, since)
    with _cell_errors():
        page = asdict(serving.cell_store().snapshot(sid, after=after, limit=limit, since=since, now=time.time()))
        if page['next_page_token'] is not None:
            page['next_page_token'] = _encode_page_token(page['next_page_token'], sid, since)
        return page


@router.post(
    '/v1/spaces/{sid}/mutations',
    tags=['spaces'],
    response_model=SpaceMutationResponse,
    responses={409: {'model': SpaceMutationConflictResponse}},
)
def mutations(
    sid: str,
    request: SpaceMutationRequest,
    http_request: Request,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'spaces:mutations')),
):
    _serving_space(sid, uid)
    with _cell_errors():
        try:
            response, replayed = apply_space_mutation(
                serving.cell_store(),
                sid,
                actor_uid=uid,
                entity=request.entity,
                entity_id=request.entity_id,
                client_mutation_id=request.client_mutation_id,
                base_revision=request.base_revision,
                operation=request.operation.model_dump(mode='python'),
                now=time.time(),
            )
        except SpaceMutationNotFoundError as error:
            raise HTTPException(404, detail='Entity not found') from error
        except SpaceMutationConflictError as error:
            record_product_event('space_sync_mutation', request=http_request, outcome='conflict')
            conflict = SpaceMutationConflictResponse.model_validate(error.response)
            return JSONResponse(status_code=409, content=conflict.model_dump(mode='json'))
    record_product_event('space_sync_mutation', request=http_request, outcome='replayed' if replayed else 'applied')
    return response


@router.post('/v1/spaces/{sid}/cursors', tags=['spaces'], response_model=SpaceCursorResponse)
def cursors(
    sid: str,
    request: SpaceCursorRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'spaces:cursors')),
):
    _serving_space(sid, uid)
    with _cell_errors():
        store = serving.cell_store()
        store.set_cursor(sid, request.device_id, last_seq=request.last_seq, now=time.time())
        # One read keeps the persisted monotonic cursor, head and epoch consistent,
        # including an advance or purge racing this acknowledgement.
        with store.pool.connection() as conn:
            state = conn.execute(
                'SELECT c.last_seq, h.next_seq, h.epoch FROM sync_cursors c '
                'JOIN space_heads h USING (space_id) '
                'WHERE c.space_id=%s AND c.device_id=%s AND NOT h.tombstoned',
                (sid, request.device_id),
            ).fetchone()
        if state is None:
            raise CellSpaceUnavailable(sid)
    return dict(status='ok', last_seq=state[0], head=state[1], epoch=state[2])
