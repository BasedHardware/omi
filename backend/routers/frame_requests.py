"""Authenticated, fail-closed frame-request queue endpoints.

The queue delivers metadata only. A desktop device receives bounded requests
through screen sync, claims them, and uploads pixels through the owner-fenced
multipart route; conversation deletion owns permanent attached evidence.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from uuid import uuid4

import database.conversations as conversations_db

from database.frame_requests import (
    enqueue_frame_request,
    get_frame_request,
    list_pending_frame_requests,
    transition_frame_request,
)
from models.frame_request import (
    CreateFrameRequest,
    FrameRequest,
    FrameRequestBatch,
    FrameRequestEnvelope,
    FrameRequestStateUpdate,
    FrameRequestPromotion,
    FrameRequestState,
)
from utils.other.endpoints import get_current_user_uid, with_rate_limit
from utils.retrieval.frame_request_authority import authorize
from utils.retrieval.frame_request_storage import delete_frame_request_pixels, upload_frame_request_pixels

router = APIRouter()


def _authorize(uid: str, account_generation: int) -> None:
    try:
        authorize(uid, account_generation)
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="frame_requests_unavailable") from exc


@router.post("/v1/frame-requests", response_model=FrameRequestEnvelope)
async def create_frame_request(
    request: CreateFrameRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "frame_requests:write")),
) -> FrameRequestEnvelope:
    _authorize(uid, request.account_generation)
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
    uid: str = Depends(with_rate_limit(get_current_user_uid, "frame_requests:read")),
) -> FrameRequestBatch:
    _authorize(uid, account_generation)
    try:
        rows = list_pending_frame_requests(
            uid,
            device_id=device_id,
            account_generation=account_generation,
            limit=limit,
            cleanup_storage=lambda storage_id: delete_frame_request_pixels(uid, storage_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FrameRequestBatch(requests=rows)


@router.post("/v1/frame-requests/{request_id}/state", response_model=FrameRequestEnvelope)
async def update_frame_request_state(
    request_id: str,
    update: FrameRequestStateUpdate,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "frame_requests:write")),
) -> FrameRequestEnvelope:
    _authorize(uid, update.account_generation)
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
            cleanup_storage=lambda storage_id: delete_frame_request_pixels(uid, storage_id),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="frame_request_not_found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="frame_request_owner_mismatch") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FrameRequestEnvelope(request=frame_request)


@router.post("/v1/frame-requests/{request_id}/upload", response_model=FrameRequestEnvelope)
async def upload_frame_request(
    request_id: str,
    device_id: str,
    account_generation: int,
    file: UploadFile = File(...),
    uid: str = Depends(with_rate_limit(get_current_user_uid, "frame_requests:upload")),
) -> FrameRequestEnvelope:
    """Store an owner-authorized pixel and then commit its bounded metadata."""

    _authorize(uid, account_generation)
    content_type = file.content_type
    if not content_type or not content_type.lower().startswith("image/"):
        raise HTTPException(status_code=415, detail="frame_upload_requires_image")
    payload = await file.read(10 * 1024 * 1024 + 1)
    if len(payload) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="frame_upload_too_large")
    storage_id = f"frame-{uuid4().hex}"
    try:
        upload_frame_request_pixels(uid, storage_id, payload, content_type)
        frame_request = transition_frame_request(
            uid,
            request_id,
            next_state=FrameRequestState.uploaded,
            device_id=device_id,
            account_generation=account_generation,
            storage_id=storage_id,
            byte_count=len(payload),
            content_type=content_type,
        )
    except KeyError as exc:
        delete_frame_request_pixels(uid, storage_id)
        raise HTTPException(status_code=404, detail="frame_request_not_found") from exc
    except PermissionError as exc:
        delete_frame_request_pixels(uid, storage_id)
        raise HTTPException(status_code=403, detail="frame_request_owner_mismatch") from exc
    except ValueError as exc:
        delete_frame_request_pixels(uid, storage_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        # Metadata commit failure must not orphan the just-uploaded pixels.
        delete_frame_request_pixels(uid, storage_id)
        raise
    return FrameRequestEnvelope(request=frame_request)


@router.post("/v1/frame-requests/{request_id}/promote", response_model=FrameRequestEnvelope)
async def promote_frame_request(
    request_id: str,
    promotion: FrameRequestPromotion,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "frame_requests:write")),
) -> FrameRequestEnvelope:
    """Promote uploaded pixels into conversation-lifetime photo evidence."""

    _authorize(uid, promotion.account_generation)
    request: FrameRequest | None = None
    photo_stored = False
    ownership_verified = False
    try:
        # The transition owns the authoritative conversation id.  Writing the
        # stable photo id first makes retries idempotent; a failed state commit
        # removes both metadata and object below.
        request = get_frame_request(uid, request_id)
        if request.account_generation != promotion.account_generation or request.device_id != promotion.device_id:
            raise PermissionError("frame request owner or account generation mismatch")
        if request.conversation_id != promotion.conversation_id:
            raise PermissionError("conversation ownership mismatch")
        ownership_verified = True
        if not request.storage_id:
            raise ValueError("only uploaded frame requests may be promoted")
        photo = conversations_db.ConversationPhoto(
            id=request_id,
            base64="",
            storage_id=request.storage_id,
            content_type=request.content_type,
            description="Just-in-time frame evidence",
        )
        if not conversations_db.store_conversation_photos(uid, promotion.conversation_id, [photo]):
            raise KeyError("conversation not found")
        photo_stored = True
        frame_request = transition_frame_request(
            uid,
            request_id,
            next_state=FrameRequestState.attached,
            device_id=promotion.device_id,
            account_generation=promotion.account_generation,
        )
    except KeyError as exc:
        if photo_stored and request:
            conversations_db.delete_conversation_photo(uid, promotion.conversation_id, request.request_id)
        if ownership_verified and request and request.storage_id:
            delete_frame_request_pixels(uid, request.storage_id)
        raise HTTPException(status_code=404, detail="frame_request_not_found") from exc
    except PermissionError as exc:
        if photo_stored and request:
            conversations_db.delete_conversation_photo(uid, promotion.conversation_id, request.request_id)
        if ownership_verified and request and request.storage_id:
            delete_frame_request_pixels(uid, request.storage_id)
        raise HTTPException(status_code=403, detail="frame_request_owner_mismatch") from exc
    except ValueError as exc:
        if photo_stored and request:
            conversations_db.delete_conversation_photo(uid, promotion.conversation_id, request.request_id)
        if ownership_verified and request and request.storage_id:
            delete_frame_request_pixels(uid, request.storage_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        if photo_stored and request:
            conversations_db.delete_conversation_photo(uid, promotion.conversation_id, request.request_id)
        if ownership_verified and request and request.storage_id:
            delete_frame_request_pixels(uid, request.storage_id)
        raise
    return FrameRequestEnvelope(request=frame_request)


__all__ = ["router"]
