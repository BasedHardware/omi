"""Context bucket sync and read APIs shared by every consumer of screen-derived work memory."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

import database.context_buckets as context_buckets_db
from models.context_bucket import (
    ContextBucketPurgeReport,
    ContextBucketPurgeRequest,
    ContextBucketSyncReport,
    ContextBucketSyncRequest,
    ContextFact,
)
from utils.other.endpoints import get_current_user_uid

router = APIRouter()
AccountGenerationHeader = Annotated[int, Header(alias='X-Account-Generation', ge=0)]


@router.post('/v1/context-buckets/sync', tags=['context_buckets'], response_model=ContextBucketSyncReport)
def sync_context_buckets(
    request: ContextBucketSyncRequest,
    account_generation: AccountGenerationHeader,
    uid: str = Depends(get_current_user_uid),
) -> ContextBucketSyncReport:
    """Publish validated facts from a capture device.

    The device owns capture; this route only accepts the facts its local validator
    already accepted. Screen content itself never arrives here.
    """

    return context_buckets_db.sync_context_buckets(uid, request, account_generation=account_generation)


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
        account_generation=account_generation,
        minimum_confidence=minimum_confidence,
        limit=limit,
    )


@router.post('/v1/context-buckets/purge', tags=['context_buckets'], response_model=ContextBucketPurgeReport)
def purge_context_buckets(
    request: ContextBucketPurgeRequest,
    uid: str = Depends(get_current_user_uid),
) -> ContextBucketPurgeReport:
    """Delete synced copies when a device stops retaining a bucket locally.

    Purge ignores account generation so a device can always retract what it published.
    """

    return context_buckets_db.purge_context_buckets(uid, request.bucket_ids)
