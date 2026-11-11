"""Compatibility stubs for the retired v2 proactivity producers.

# LIFECYCLE: one-time
# DELETE-AFTER: the proactivity ledger/budget retirement follow-up (one release
# after this PR): the real-time mentor and commitment follow-up producers were
# deleted, and these routes stay only so already-shipped app/desktop clients
# keep decoding responses instead of erroring during the compat window. Remove
# the routes, then the ledger, budget authority, redis and flags.

The feed always reports `enabled=false` with no items, and outcomes are a
recorded no-op, matching the wire contract the released clients were built
against.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from config.proactivity_v2 import utc_now
from models.proactivity import ProactivityFeedResponse, ProactivityOutcomeRequest, ProactivityOutcomeResponse
from utils.other import endpoints as auth

router = APIRouter()
logger = logging.getLogger(__name__)
Owner = Annotated[str, Depends(auth.with_rate_limit(auth.get_current_user_uid, 'proactivity:api'))]


@router.get(
    '/v1/proactivity/feed',
    response_model=ProactivityFeedResponse,
    operation_id='get_proactivity_feed',
    deprecated=True,
)
def get_proactivity_feed(
    uid: Owner,
    # Declared so released clients' query strings stay inside the request
    # contract during the compat window; a stubbed feed has nothing to page.
    limit: int = Query(20, ge=1, le=50),
    cursor: str = Query('', max_length=1024),
):
    del uid, limit, cursor
    return ProactivityFeedResponse(enabled=False, items=[], next_cursor='', has_more=False, server_time=utc_now())


@router.post(
    '/v1/proactivity/items/{item_id}/outcomes',
    response_model=ProactivityOutcomeResponse,
    operation_id='record_proactivity_outcome',
    deprecated=True,
)
def record_proactivity_outcome(item_id: str, data: ProactivityOutcomeRequest, uid: Owner):
    del data, uid  # Accepted and acknowledged; no producer items remain to record against.
    return ProactivityOutcomeResponse(item_id=item_id, recorded=False, acted_24h=False, negative=False)
