"""Authenticated, fail-closed frame-request queue endpoints.

The first slice exposes only the metadata queue.  A desktop device receives
bounded requests through screen sync and reports lifecycle metadata back.  No
route accepts image bytes; the existing authenticated upload/storage path owns
pixels and conversation deletion owns permanent attached evidence.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from database.frame_requests import (
    enqueue_frame_request,
    list_pending_frame_requests,
    transition_frame_request,
)
from models.frame_request import (
    CreateFrameRequest,
    FrameRequestBatch,
    FrameRequestEnvelope,
    FrameRequestStateUpdate,
)
from utils.other.endpoints import get_current_user_uid
from utils.retrieval.frame_request_policy import local_frame_requests_enabled

router = APIRouter()


def _require_local_gate() -> None:
    # This gate is intentionally a local/dev seam while the backend PostHog
    # rollout authority is stacked.  Unset or malformed state must not expose
    # queue behavior in released revisions.
    if not local_frame_requests_enabled():
        raise HTTPException(status_code=404, detail="frame_requests_unavailable")


@router.post("/v1/frame-requests", response_model=FrameRequestEnvelope)
async def create_frame_request(
    request: CreateFrameRequest,
    uid: str = Depends(get_current_user_uid),
) -> FrameRequestEnvelope:
    _require_local_gate()
    try:
        frame_request, deduplicated = enqueue_frame_request(
            uid,
            device_id=request.device_id,
            account_generation=request.account_generation,
            dedupe_key=request.dedupe_key,
            conversation_id=request.conversation_id,
            screenshot_id=request.screenshot_id,
            requested_ttl_seconds=request.requested_ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FrameRequestEnvelope(request=frame_request, deduplicated=deduplicated)


@router.get("/v1/frame-requests/pending", response_model=FrameRequestBatch)
async def get_pending_frame_requests(
    device_id: str = Query(min_length=1, max_length=256),
    account_generation: int = Query(default=0, ge=0),
    limit: int = Query(default=32, ge=1, le=32),
    uid: str = Depends(get_current_user_uid),
) -> FrameRequestBatch:
    _require_local_gate()
    try:
        rows = list_pending_frame_requests(uid, device_id=device_id, account_generation=account_generation, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FrameRequestBatch(requests=rows)


@router.post("/v1/frame-requests/{request_id}/state", response_model=FrameRequestEnvelope)
async def update_frame_request_state(
    request_id: str,
    update: FrameRequestStateUpdate,
    uid: str = Depends(get_current_user_uid),
) -> FrameRequestEnvelope:
    _require_local_gate()
    try:
        frame_request = transition_frame_request(
            uid,
            request_id,
            next_state=update.state,
            device_id=update.device_id,
            account_generation=update.account_generation,
            terminal_reason=update.terminal_reason,
            storage_id=update.storage_id,
            byte_count=update.byte_count,
            content_type=update.content_type,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="frame_request_not_found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="frame_request_owner_mismatch") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FrameRequestEnvelope(request=frame_request)


__all__ = ["router"]
