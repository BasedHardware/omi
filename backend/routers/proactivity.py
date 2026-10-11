"""Authenticated feed and one outcome endpoint for every v2 client."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from config.proactivity_v2 import ProactivityDenied, utc_now
from database import proactivity as ledger
from models.proactivity import ProactivityFeedResponse, ProactivityOutcomeRequest, ProactivityOutcomeResponse
from utils import proactivity, proactivity_flags
from utils.executors import db_executor, run_blocking
from utils.other import endpoints as auth

router = APIRouter()
logger = logging.getLogger(__name__)
Owner = Annotated[str, Depends(auth.with_rate_limit(auth.get_current_user_uid, 'proactivity:api'))]


def _http_error(exc: Exception) -> HTTPException:
    reason = exc.reason if isinstance(exc, ProactivityDenied) else 'unavailable'
    code = {'not_found': 404, 'expired': 404, 'event_conflict': 409, 'invalid_cursor': 422, 'invalid_outcome': 422}.get(
        reason, 503
    )
    return HTTPException(status_code=code, detail=reason)


@router.get('/v1/proactivity/feed', response_model=ProactivityFeedResponse, operation_id='get_proactivity_feed')
async def get_proactivity_feed(
    uid: Owner, limit: int = Query(20, ge=1, le=50), cursor: str = Query('', max_length=1024)
):
    try:
        enabled = await run_blocking(db_executor, proactivity_flags.enabled, uid)
        if not enabled:
            return ProactivityFeedResponse(
                enabled=False, items=[], next_cursor='', has_more=False, server_time=utc_now()
            )
        items, next_cursor, more = await run_blocking(
            db_executor, ledger.list_feed, uid=uid, limit=limit, cursor=cursor
        )
        decoded = [proactivity.decode_feed_item(uid, item) for item in items]
        return ProactivityFeedResponse(
            enabled=True, items=decoded, next_cursor=next_cursor, has_more=more, server_time=utc_now()
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post(
    '/v1/proactivity/items/{item_id}/outcomes',
    response_model=ProactivityOutcomeResponse,
    operation_id='record_proactivity_outcome',
)
async def record_proactivity_outcome(item_id: str, data: ProactivityOutcomeRequest, uid: Owner):
    try:
        result = await run_blocking(
            db_executor,
            ledger.record_outcome,
            uid=uid,
            item_id=item_id,
            event_id=str(data.event_id),
            action=data.action,
            surface=data.surface,
            channel=data.channel,
        )
        return ProactivityOutcomeResponse(**result)
    except Exception as exc:
        raise _http_error(exc) from exc
