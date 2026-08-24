"""Authenticated, fail-closed frame-request queue endpoints.

The queue delivers metadata only. A desktop device receives bounded requests
through screen sync, claims them, and uploads pixels through the owner-fenced
multipart route; conversation deletion owns permanent attached evidence.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from uuid import uuid4
import time

import database.conversations as conversations_db

from database.frame_requests import (
    enqueue_frame_request,
    get_frame_request,
    list_attached_frame_requests,
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
from utils.executors import db_executor, run_blocking, storage_executor
from utils.retrieval.frame_request_authority import authorize
from utils.retrieval.frame_request_storage import delete_frame_request_pixels, upload_frame_request_pixels
from utils.retrieval.frame_request_policy import FRAME_REQUEST_MAX_BYTES_PER_CONVERSATION
from utils.integration_telemetry import emit_posthog_event

router = APIRouter()


def _record_frame_lifecycle(
    uid: str, event: str, *, state: FrameRequestState, started: float, byte_count: int = 0
) -> None:
    """Emit content-free bounded outcome/latency telemetry."""

    elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
    latency = "0_100ms" if elapsed_ms <= 100 else "101_1000ms" if elapsed_ms <= 1000 else "1000ms_plus"
    size = "0" if byte_count <= 0 else "1_1mb" if byte_count <= 1024 * 1024 else "1mb_plus"
    emit_posthog_event(
        uid,
        event,
        {"state": state.value, "latency_bucket": latency, "byte_bucket": size, "surface": "frame_request"},
    )


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
    started = time.monotonic()
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
    _record_frame_lifecycle(
        uid,
        "frame_request_enqueued" if not deduplicated else "frame_request_deduplicated",
        state=frame_request.state,
        started=started,
    )
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

    started = time.monotonic()
    _authorize(uid, account_generation)
    content_type = file.content_type
    if not content_type or not content_type.lower().startswith("image/"):
        raise HTTPException(status_code=415, detail="frame_upload_requires_image")
    payload = await file.read(10 * 1024 * 1024 + 1)
    if len(payload) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="frame_upload_too_large")
    storage_id = f"frame-{uuid4().hex}"
    try:
        await run_blocking(storage_executor, upload_frame_request_pixels, uid, storage_id, payload, content_type)
        frame_request = await run_blocking(
            db_executor,
            transition_frame_request,
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
        await run_blocking(storage_executor, delete_frame_request_pixels, uid, storage_id)
        raise HTTPException(status_code=404, detail="frame_request_not_found") from exc
    except PermissionError as exc:
        await run_blocking(storage_executor, delete_frame_request_pixels, uid, storage_id)
        raise HTTPException(status_code=403, detail="frame_request_owner_mismatch") from exc
    except ValueError as exc:
        await run_blocking(storage_executor, delete_frame_request_pixels, uid, storage_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        # Known pre-commit upload failures can remove their temporary object;
        # promotion intentionally uses a different no-cleanup ambiguity rule.
        await run_blocking(storage_executor, delete_frame_request_pixels, uid, storage_id)
        raise
    _record_frame_lifecycle(
        uid, "frame_request_uploaded", state=frame_request.state, started=started, byte_count=frame_request.byte_count
    )
    return FrameRequestEnvelope(request=frame_request)


@router.post("/v1/frame-requests/{request_id}/promote", response_model=FrameRequestEnvelope)
async def promote_frame_request(
    request_id: str,
    promotion: FrameRequestPromotion,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "frame_requests:write")),
) -> FrameRequestEnvelope:
    """Promote uploaded pixels into conversation-lifetime photo evidence."""

    started = time.monotonic()
    _authorize(uid, promotion.account_generation)
    request: FrameRequest | None = None
    try:
        # Read before writing so a completed request is a true idempotent
        # retry.  In particular, never run cleanup after observing ``attached``:
        # the metadata and object are now conversation-lifetime evidence.
        request = get_frame_request(uid, request_id)
        if request.account_generation != promotion.account_generation or request.device_id != promotion.device_id:
            raise PermissionError("frame request owner or account generation mismatch")
        if request.conversation_id != promotion.conversation_id:
            raise PermissionError("conversation ownership mismatch")
        if request.state == FrameRequestState.attached:
            _record_frame_lifecycle(uid, "frame_request_attached", state=request.state, started=started)
            return FrameRequestEnvelope(request=request)
        if request.state != FrameRequestState.uploaded:
            raise ValueError("only uploaded frame requests may be promoted")
        if not request.storage_id:
            raise ValueError("only uploaded frame requests may be promoted")
        attached = list_attached_frame_requests(uid, promotion.conversation_id)
        if any(item.request_id != request_id for item in attached):
            raise ValueError("conversation already has permanent frame evidence")
        if sum(item.byte_count for item in attached) + request.byte_count > FRAME_REQUEST_MAX_BYTES_PER_CONVERSATION:
            raise ValueError("conversation frame evidence byte budget exceeded")
        photo = conversations_db.ConversationPhoto(
            id=request_id,
            base64="",
            storage_id=request.storage_id,
            content_type=request.content_type,
            description="Just-in-time frame evidence",
        )
        if not conversations_db.store_conversation_photos(uid, promotion.conversation_id, [photo]):
            raise KeyError("conversation not found")
        try:
            frame_request = transition_frame_request(
                uid,
                request_id,
                next_state=FrameRequestState.attached,
                device_id=promotion.device_id,
                account_generation=promotion.account_generation,
            )
        except ValueError:
            # Another promotion may have won the state race after this request
            # wrote the stable photo id.  Re-read and accept only the exact
            # attached outcome; all other failures remain retryable.  The
            # exception could be raised after Firestore committed, so cleanup
            # here would risk deleting permanent evidence.
            current = get_frame_request(uid, request_id)
            if current.state == FrameRequestState.attached and current.conversation_id == promotion.conversation_id:
                _record_frame_lifecycle(uid, "frame_request_attached", state=current.state, started=started)
                return FrameRequestEnvelope(request=current)
            raise
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="frame_request_not_found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="frame_request_owner_mismatch") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _record_frame_lifecycle(uid, "frame_request_attached", state=frame_request.state, started=started)
    return FrameRequestEnvelope(request=frame_request)


__all__ = ["router"]
