"""Authenticated, fail-closed frame-request queue endpoints.

The queue delivers metadata only. A desktop device receives bounded requests
through screen sync, claims them, and uploads pixels through the owner-fenced
multipart route; conversation deletion owns permanent attached evidence.
"""

from __future__ import annotations

import time
from io import BytesIO
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from database.frame_requests import (
    acknowledge_frame_storage_cleanup,
    attach_frame_request_to_conversation,
    enqueue_frame_request,
    get_frame_request,
    list_pending_frame_requests,
    reconcile_ambiguous_frame_upload,
    reserve_frame_promotion_copy,
    reserve_frame_storage_cleanup,
    transition_frame_request,
)
from models.frame_request import (
    CreateFrameRequest,
    FrameRequest,
    FrameRequestBatch,
    FrameRequestEnvelope,
    FrameRequestPromotion,
    FrameRequestState,
    FrameRequestStateUpdate,
)
from utils.executors import db_executor, run_blocking, storage_executor
from utils.integration_telemetry import emit_posthog_event
from utils.other.endpoints import get_current_user_uid, with_rate_limit
from utils.retrieval.frame_request_authority import authorize
from utils.retrieval.frame_request_storage import (
    PERMANENT_STORAGE_PREFIX,
    TEMPORARY_STORAGE_PREFIX,
    copy_frame_request_pixels_to_permanent,
    delete_frame_request_pixels,
    download_frame_request_pixels,
    upload_frame_request_pixels,
)

router = APIRouter()
_ALLOWED_IMAGE_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
_MAX_IMAGE_PIXELS = 25_000_000
_MAX_EGRESS_DIMENSION = 1920
_MAX_EGRESS_PIXELS = 2_500_000


def _validated_image_content_type(payload: bytes) -> str:
    """Decode enough image structure to reject spoofed or decompression-bomb uploads."""

    try:
        with Image.open(BytesIO(payload)) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            image.verify()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=415, detail="frame_upload_invalid_image") from exc
    if image_format not in _ALLOWED_IMAGE_FORMATS:
        raise HTTPException(status_code=415, detail="frame_upload_unsupported_image")
    if width < 1 or height < 1 or width * height > _MAX_IMAGE_PIXELS:
        raise HTTPException(status_code=413, detail="frame_upload_dimensions_too_large")
    return _ALLOWED_IMAGE_FORMATS[image_format]


def _canonicalize_frame_image(payload: bytes) -> bytes:
    """Strip metadata and bound the exact bytes persisted and sent to vision."""
    try:
        with Image.open(BytesIO(payload)) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            width, height = image.size
            scale = min(
                1.0,
                _MAX_EGRESS_DIMENSION / max(width, height),
                (_MAX_EGRESS_PIXELS / (width * height)) ** 0.5,
            )
            if scale < 1.0:
                image = image.resize(
                    (max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS
                )
            if image.mode not in {"RGB", "L"}:
                if "A" in image.getbands():
                    background = Image.new("RGB", image.size, "white")
                    background.paste(image, mask=image.getchannel("A"))
                    image = background
                else:
                    image = image.convert("RGB")
            output = BytesIO()
            image.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=415, detail="frame_upload_invalid_image") from exc


def _record_frame_lifecycle(
    uid: str,
    event: str,
    *,
    state: FrameRequestState,
    started: float,
    byte_count: int = 0,
) -> None:
    """Emit content-free bounded outcome/latency telemetry."""

    elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
    latency = "0_100ms" if elapsed_ms <= 100 else "101_1000ms" if elapsed_ms <= 1000 else "1000ms_plus"
    size = "0" if byte_count <= 0 else "1_1mb" if byte_count <= 1024 * 1024 else "1mb_plus"
    emit_posthog_event(
        uid,
        event,
        {
            "state": state.value,
            "latency_bucket": latency,
            "byte_bucket": size,
            "surface": "frame_request",
        },
    )


async def _authorize(uid: str, account_generation: int) -> None:
    try:
        await run_blocking(db_executor, authorize, uid, account_generation)
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="frame_requests_unavailable") from exc


async def _reconcile_uploaded_object(
    uid: str,
    request_id: str,
    *,
    device_id: str,
    account_generation: int,
    storage_id: str,
    byte_count: int,
    content_type: str | None,
) -> FrameRequest | None:
    try:
        return await run_blocking(
            db_executor,
            reconcile_ambiguous_frame_upload,
            uid,
            request_id,
            device_id=device_id,
            account_generation=account_generation,
            storage_id=storage_id,
            byte_count=byte_count,
            content_type=content_type,
        )
    except Exception:  # noqa: BLE001 - ambiguous commit must preserve pixels on any storage/DB failure
        # A failed read/reconcile cannot prove ownership or terminality. Keep
        # the object for the independent retry worker rather than deleting it.
        return None


@router.post("/v1/frame-requests", response_model=FrameRequestEnvelope)
async def create_frame_request(
    request: CreateFrameRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "frame_requests:write")),
) -> FrameRequestEnvelope:
    started = time.monotonic()
    await _authorize(uid, request.account_generation)
    try:
        frame_request, deduplicated = await run_blocking(
            db_executor,
            enqueue_frame_request,
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


@router.get("/v1/frame-requests/status/{request_id}", response_model=FrameRequestEnvelope)
async def get_frame_request_status(
    request_id: str,
    account_generation: int = Query(default=0, ge=0),
    uid: str = Depends(with_rate_limit(get_current_user_uid, "frame_requests:read")),
) -> FrameRequestEnvelope:
    """Return honest owner-scoped lifecycle state without exposing pixels."""

    await _authorize(uid, account_generation)
    try:
        frame_request = await run_blocking(db_executor, get_frame_request, uid, request_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="frame_request_not_found") from exc
    if frame_request.account_generation != account_generation:
        raise HTTPException(status_code=404, detail="frame_request_not_found")
    return FrameRequestEnvelope(request=frame_request)


@router.get(
    "/v1/frame-requests/temporary/{request_id}/image",
    response_class=Response,
    responses={
        200: {
            "content": {
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                "image/png": {"schema": {"type": "string", "format": "binary"}},
                "image/webp": {"schema": {"type": "string", "format": "binary"}},
            }
        }
    },
)
async def consume_temporary_frame_request_image(
    request_id: str,
    account_generation: int = Query(default=0, ge=0),
    uid: str = Depends(with_rate_limit(get_current_user_uid, "frame_requests:read")),
) -> Response:
    """Read one uploaded, unattached temporary frame for JIT vision.

    Conversation evidence is deliberately excluded: permanent images remain
    reachable only through the conversation-owned endpoint. This read neither
    promotes nor extends the temporary request's at-most-seven-day expiry.
    """

    started = time.monotonic()
    await _authorize(uid, account_generation)
    try:
        frame_request = await run_blocking(db_executor, get_frame_request, uid, request_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="frame_request_not_found") from exc
    if frame_request.account_generation != account_generation or frame_request.conversation_id is not None:
        raise HTTPException(status_code=404, detail="frame_request_not_found")
    if frame_request.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="frame_request_expired")
    if frame_request.state != FrameRequestState.uploaded or not frame_request.storage_id:
        raise HTTPException(status_code=409, detail=f"frame_request_{frame_request.state.value}")
    try:
        payload = await run_blocking(
            storage_executor,
            download_frame_request_pixels,
            uid,
            frame_request.storage_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail="frame_request_pixels_unavailable") from exc
    _record_frame_lifecycle(
        uid,
        "frame_request_pixels_consumed",
        state=frame_request.state,
        started=started,
        byte_count=frame_request.byte_count,
    )
    return Response(content=payload, media_type=frame_request.content_type or "image/jpeg")


@router.get("/v1/frame-requests/pending", response_model=FrameRequestBatch)
async def get_pending_frame_requests(
    device_id: str = Query(min_length=1, max_length=256),
    account_generation: int = Query(default=0, ge=0),
    limit: int = Query(default=32, ge=1, le=32),
    uid: str = Depends(with_rate_limit(get_current_user_uid, "frame_requests:read")),
) -> FrameRequestBatch:
    await _authorize(uid, account_generation)
    try:
        rows = await run_blocking(
            db_executor,
            list_pending_frame_requests,
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
    started = time.monotonic()
    await _authorize(uid, update.account_generation)
    try:
        frame_request = await run_blocking(
            db_executor,
            transition_frame_request,
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
    _record_frame_lifecycle(
        uid,
        "frame_request_state_transition",
        state=frame_request.state,
        started=started,
        byte_count=frame_request.byte_count,
    )
    return FrameRequestEnvelope(request=frame_request)


@router.post("/v1/frame-requests/{request_id}/upload", response_model=FrameRequestEnvelope)
async def upload_frame_request(
    request_id: str,
    device_id: str,
    account_generation: int,
    file: UploadFile = File(...),  # noqa: B008 - FastAPI injection contract
    uid: str = Depends(with_rate_limit(get_current_user_uid, "frame_requests:upload")),
) -> FrameRequestEnvelope:
    """Store an owner-authorized pixel and then commit its bounded metadata."""

    started = time.monotonic()
    await _authorize(uid, account_generation)
    declared_content_type = file.content_type
    if not declared_content_type or declared_content_type.lower() not in set(_ALLOWED_IMAGE_FORMATS.values()):
        raise HTTPException(status_code=415, detail="frame_upload_requires_image")
    payload = await file.read(10 * 1024 * 1024 + 1)
    if len(payload) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="frame_upload_too_large")
    _validated_image_content_type(payload)
    payload = _canonicalize_frame_image(payload)
    content_type = "image/jpeg"
    storage_id = f"{TEMPORARY_STORAGE_PREFIX}{uuid4().hex}"
    try:
        await run_blocking(
            storage_executor,
            upload_frame_request_pixels,
            uid,
            storage_id,
            payload,
            content_type,
        )
    except Exception:
        # The object was not handed to Firestore yet, so a failed storage write
        # is safe to clean up.
        await run_blocking(storage_executor, delete_frame_request_pixels, uid, storage_id)
        raise

    try:
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
        # Transition failures are commit-ambiguous, even for typed validation
        # errors. Keep the object and let reconciliation/retention converge.
        reconciled = await _reconcile_uploaded_object(
            uid,
            request_id,
            device_id=device_id,
            account_generation=account_generation,
            storage_id=storage_id,
            byte_count=len(payload),
            content_type=content_type,
        )
        if (
            reconciled
            and reconciled.storage_id == storage_id
            and reconciled.state
            in {
                FrameRequestState.uploaded,
                FrameRequestState.attached,
            }
        ):
            return FrameRequestEnvelope(request=reconciled)
        raise HTTPException(status_code=404, detail="frame_request_not_found") from exc
    except PermissionError as exc:
        reconciled = await _reconcile_uploaded_object(
            uid,
            request_id,
            device_id=device_id,
            account_generation=account_generation,
            storage_id=storage_id,
            byte_count=len(payload),
            content_type=content_type,
        )
        if (
            reconciled
            and reconciled.storage_id == storage_id
            and reconciled.state
            in {
                FrameRequestState.uploaded,
                FrameRequestState.attached,
            }
        ):
            return FrameRequestEnvelope(request=reconciled)
        raise HTTPException(status_code=403, detail="frame_request_owner_mismatch") from exc
    except ValueError as exc:
        reconciled = await _reconcile_uploaded_object(
            uid,
            request_id,
            device_id=device_id,
            account_generation=account_generation,
            storage_id=storage_id,
            byte_count=len(payload),
            content_type=content_type,
        )
        if (
            reconciled
            and reconciled.storage_id == storage_id
            and reconciled.state
            in {
                FrameRequestState.uploaded,
                FrameRequestState.attached,
            }
        ):
            return FrameRequestEnvelope(request=reconciled)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        # A Firestore transaction can have committed while the client observed
        # a transport error. Never delete an object on an ambiguous commit: a
        # scheduled owner-scoped cleanup/reconciliation pass may remove an
        # object only after proving that metadata does not reference it.
        reconciled = await _reconcile_uploaded_object(
            uid,
            request_id,
            device_id=device_id,
            account_generation=account_generation,
            storage_id=storage_id,
            byte_count=len(payload),
            content_type=content_type,
        )
        if (
            reconciled
            and reconciled.storage_id == storage_id
            and reconciled.state
            in {
                FrameRequestState.uploaded,
                FrameRequestState.attached,
            }
        ):
            _record_frame_lifecycle(
                uid,
                "frame_request_uploaded",
                state=reconciled.state,
                started=started,
                byte_count=reconciled.byte_count,
            )
            return FrameRequestEnvelope(request=reconciled)
        raise
    _record_frame_lifecycle(
        uid,
        "frame_request_uploaded",
        state=frame_request.state,
        started=started,
        byte_count=frame_request.byte_count,
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
    await _authorize(uid, promotion.account_generation)
    try:
        # Fast idempotent read path avoids even starting a transaction for a
        # row already known to be permanent. The transaction below remains the
        # authority for the uploaded -> attached race.
        existing = await run_blocking(db_executor, get_frame_request, uid, request_id)
        if existing.account_generation != promotion.account_generation or existing.device_id != promotion.device_id:
            raise PermissionError("frame request owner or account generation mismatch")
        if existing.conversation_id != promotion.conversation_id:
            raise PermissionError("conversation ownership mismatch")
        if existing.state == FrameRequestState.attached:
            if existing.storage_id:
                await run_blocking(db_executor, acknowledge_frame_storage_cleanup, uid, existing.storage_id)
            _record_frame_lifecycle(uid, "frame_request_attached", state=existing.state, started=started)
            return FrameRequestEnvelope(request=existing)
        if existing.state != FrameRequestState.uploaded or not existing.storage_id:
            raise ValueError("only uploaded frame requests may be promoted")
        permanent_storage_id = f"{PERMANENT_STORAGE_PREFIX}{request_id.removeprefix('frame-')}"
        await run_blocking(
            db_executor,
            reserve_frame_promotion_copy,
            uid,
            request_id,
            permanent_storage_id,
        )
        await run_blocking(
            storage_executor,
            copy_frame_request_pixels_to_permanent,
            uid,
            existing.storage_id,
            permanent_storage_id,
        )
        await run_blocking(
            db_executor,
            reserve_frame_storage_cleanup,
            uid,
            request_id,
            existing.storage_id,
        )
        # The frame row, photo metadata, and one-keyframe invariant are one
        # Firestore transaction. This makes concurrent promotion idempotent:
        # one caller wins and the retry observes the committed attached row.
        frame_request = await run_blocking(
            db_executor,
            attach_frame_request_to_conversation,
            uid,
            request_id,
            device_id=promotion.device_id,
            account_generation=promotion.account_generation,
            conversation_id=promotion.conversation_id,
            permanent_storage_id=permanent_storage_id,
        )
        # The attached row now references the permanent object. Temporary
        # deletion is idempotent; a failure is retried by its durable receipt.
        try:
            await run_blocking(storage_executor, delete_frame_request_pixels, uid, existing.storage_id)
        except Exception:
            pass
        else:
            await run_blocking(db_executor, acknowledge_frame_storage_cleanup, uid, existing.storage_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="frame_request_not_found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="frame_request_owner_mismatch") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _record_frame_lifecycle(uid, "frame_request_attached", state=frame_request.state, started=started)
    return FrameRequestEnvelope(request=frame_request)


__all__ = ["router"]
