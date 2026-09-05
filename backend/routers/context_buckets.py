"""Context bucket sync and read APIs shared by every consumer of screen-derived work memory."""

import logging

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query

import database.account_cutover as account_cutover_db
import database.context_buckets as context_buckets_db
from models.context_bucket import (
    ContextBucketPurgeReport,
    ContextBucketPurgeRequest,
    ContextBucketSyncReport,
    ContextBucketSyncRequest,
    ContextFact,
)
from utils.other import endpoints as auth
from utils.other.endpoints import get_current_user_uid

logger = logging.getLogger(__name__)
router = APIRouter()
AccountGenerationHeader = Annotated[int, Header(alias='X-Account-Generation', ge=0)]


def _resolve_account_generation(uid: str, claimed_generation: int) -> int:
    """Reject a generation the caller asserted but the account does not hold.

    Generation is the fence that keeps a superseded incarnation's context out of
    the current one. Taking it from a client header on trust lets a caller read
    the previous incarnation back, or pin writes into a generation nothing reads
    and nothing sweeps.
    """

    actual = account_cutover_db.get_account_cutover_record(uid).account_generation
    if actual != claimed_generation:
        raise HTTPException(status_code=409, detail='Account generation mismatch')
    return actual


@router.post('/v1/context-buckets/sync', tags=['context_buckets'], response_model=ContextBucketSyncReport)
def sync_context_buckets(
    request: ContextBucketSyncRequest,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(auth.with_rate_limit(get_current_user_uid, 'context_buckets:sync')),
) -> ContextBucketSyncReport:
    """Publish validated facts from a capture device.

    The device owns capture; this route only accepts the facts its local validator
    already accepted. Screen content itself never arrives here.
    """

    report = context_buckets_db.sync_context_buckets(
        uid, request, account_generation=_resolve_account_generation(uid, account_generation)
    )
    # Sweep here rather than on a schedule: this is the recurring per-device call,
    # so expiry collection rides a round trip the device is already paying for.
    # Bounded per call, so a backlog drains over passes instead of stalling one.
    try:
        context_buckets_db.collect_expired_context_facts(uid)
    except Exception as error:
        logger.warning(f'expired context fact collection failed for one sync: {error}')
    return report


@router.get('/v1/context-buckets/facts', tags=['context_buckets'], response_model=list[ContextFact])
def list_context_facts(
    account_generation: AccountGenerationHeader,
    minimum_confidence: float = Query(default=0, ge=0, le=1),
    limit: int = Query(default=200, ge=1, le=500),
    uid: str = Depends(get_current_user_uid),
) -> list[ContextFact]:
    """Flat fact read for prompt assembly and other cross-surface consumers."""

    return context_buckets_db.list_context_facts(
        uid,
        account_generation=_resolve_account_generation(uid, account_generation),
        minimum_confidence=minimum_confidence,
        limit=limit,
    )


@router.post('/v1/context-buckets/purge', tags=['context_buckets'], response_model=ContextBucketPurgeReport)
def purge_context_buckets(
    request: ContextBucketPurgeRequest,
    uid: str = Depends(auth.with_rate_limit(get_current_user_uid, 'context_buckets:purge')),
) -> ContextBucketPurgeReport:
    """Delete synced copies when a device stops retaining a bucket locally.

    Purge ignores account generation so a device can always retract what it published.
    """

    return context_buckets_db.purge_context_buckets(uid, request.bucket_ids)
