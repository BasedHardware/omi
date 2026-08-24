import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from database.frame_requests import list_pending_frame_requests
from database.screen_activity import (
    normalize_screen_activity_timestamp,
    upsert_screen_activity,
)
from database.vector_db import upsert_screen_activity_vectors
from testing.parity_pack_v0.live_capture import SurfaceParityCapture
from utils.executors import db_executor, run_blocking
from utils.other.endpoints import get_current_user_uid, with_rate_limit
from utils.observability.fallback import record_fallback
from utils.retrieval.frame_request_authority import decision_for
from utils.retrieval.frame_request_storage import delete_frame_request_pixels
from utils.subscription import grants_cloud_screen_vectors, is_desktop_trial_paywalled

logger = logging.getLogger(__name__)
router = APIRouter()


class ScreenActivityRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    timestamp: str
    app_name: str = Field(default="", alias="appName")
    window_title: str = Field(default="", alias="windowTitle")
    ocr_text: str = Field(default="", alias="ocrText")
    device_name: str | None = Field(default=None, alias="deviceName")
    client_device_id: str | None = Field(default=None, alias="clientDeviceId")
    embedding: list[float] | None = None

    @field_validator("timestamp")
    @classmethod
    def canonicalize_timestamp(cls, value: str) -> str:
        return normalize_screen_activity_timestamp(value)

    def storage_id(self) -> str:
        return f"{self.client_device_id}-{self.id}" if self.client_device_id else str(self.id)


class ScreenActivitySyncRequest(BaseModel):
    account_generation: int = Field(default=0, ge=0)
    rows: list[ScreenActivityRow]


class FrameRequestDelivery(BaseModel):
    """Metadata-only queue item delivered to the owning desktop device."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    device_id: str
    account_generation: int
    conversation_id: str | None = None
    screenshot_id: str | None = None
    state: str
    expires_at: str


class ScreenActivitySyncResponse(BaseModel):
    """Additive sync response; old clients decode the two required fields."""

    model_config = ConfigDict(extra="forbid")

    synced: int
    last_id: int
    frame_requests: list[FrameRequestDelivery] | None = None


async def _authorized_desktop_user(
    uid: str = Depends(with_rate_limit(get_current_user_uid, "frame_requests:read")),
) -> str:
    if await run_blocking(db_executor, is_desktop_trial_paywalled, uid, "desktop"):
        raise HTTPException(status_code=402, detail="trial_expired")
    return uid


def _parity_screen_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep screen capture text-only and bounded; never retain embeddings/video."""
    return [
        {
            "timestamp": str(row.get("timestamp") or ""),
            "app_name": str(row.get("appName") or "")[:512],
            "window_title": str(row.get("windowTitle") or "")[:2048],
            "ocr_text": str(row.get("ocrText") or "")[:8192],
        }
        for row in rows[:100]
    ]


@router.post("/v1/screen-activity/sync", response_model=ScreenActivitySyncResponse, response_model_exclude_none=True)
async def sync_screen_activity(
    request: ScreenActivitySyncRequest, uid: str = Depends(_authorized_desktop_user)
) -> ScreenActivitySyncResponse:
    if len(request.rows) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 rows per batch")
    if not request.rows:
        return {"synced": 0, "last_id": 0}
    rows = [{**row.model_dump(by_alias=True), "storageId": row.storage_id()} for row in request.rows]
    parity_capture = SurfaceParityCapture.from_environ(
        principal_id=uid,
        session_id=f"{rows[0]['storageId']}:{rows[-1]['storageId']}",
        surface="screen",
        source="desktop_screen_activity_sync",
        provider_lane="screen",
        route_or_model="screen-activity-sync",
        request={"row_count": len(rows), "has_embeddings": any(row.get("embedding") for row in rows)},
    )
    parity_capture.observe("client", {"type": "screen_activity_rows", "rows": _parity_screen_rows(rows)})
    try:
        try:
            written = await run_blocking(db_executor, upsert_screen_activity, uid, rows)
        except Exception as exc:
            logger.exception("Screen activity Firestore write failed for uid=%s", uid)
            raise HTTPException(status_code=500, detail="Firestore write failed") from exc
        # The vector is the expensive half of a synced row and its only server-side purpose is
        # semantic screen search, which is a paid desktop capability. Gate it here rather than on
        # the client: the client cannot be trusted to know its own entitlement, and the row is
        # still stored either way, so a later upgrade can backfill vectors from the stored text.
        embedded_rows = (
            [row for row in rows if row.get("embedding")]
            if await run_blocking(db_executor, grants_cloud_screen_vectors, uid)
            else []
        )
        if embedded_rows:
            try:
                await run_blocking(db_executor, upsert_screen_activity_vectors, uid, embedded_rows)
            except Exception:
                logger.exception("Screen activity vector write failed for uid=%s", uid)
        response_payload: dict[str, Any] = {"synced": written, "last_id": max(row.id for row in request.rows)}
        # Frame requests are an additive, default-off response field.  Route
        # them only to the exact device that supplied this sync batch and keep
        # the payload metadata-only: no image bytes, URLs, or OCR are returned.
        device_id = request.rows[0].client_device_id
        same_device_batch = bool(device_id) and all(row.client_device_id == device_id for row in request.rows)
        decision = decision_for(uid)
        if decision.enabled and decision.account_generation == request.account_generation and same_device_batch:
            try:
                pending = await run_blocking(
                    db_executor,
                    list_pending_frame_requests,
                    uid,
                    device_id=device_id,
                    account_generation=request.account_generation,
                    cleanup_storage=lambda storage_id: delete_frame_request_pixels(uid, storage_id),
                )
                response_payload["frame_requests"] = [
                    FrameRequestDelivery(
                        request_id=item.request_id,
                        device_id=item.device_id,
                        account_generation=item.account_generation,
                        conversation_id=item.conversation_id,
                        screenshot_id=item.screenshot_id,
                        state=item.state.value,
                        expires_at=item.expires_at.isoformat(),
                    ).model_dump(mode="json")
                    for item in pending
                ]
            except Exception:
                # Queue delivery must never turn a successful screen sync into
                # a 500.  The device will retry on its next sync; details stay
                # in the private log rather than telemetry.
                logger.exception("Frame-request delivery failed for uid=%s", uid)
                record_fallback(
                    component="other",
                    from_mode="frame-request-queue",
                    to_mode="screen-sync-retry",
                    reason="enqueue_failed",
                    outcome="degraded",
                    log=logger,
                )
        elif decision.enabled and not same_device_batch:
            record_fallback(
                component="other",
                from_mode="frame-request-queue",
                to_mode="screen-sync-retry",
                reason="policy",
                outcome="degraded",
                log=logger,
            )
        response = ScreenActivitySyncResponse.model_validate(response_payload)
        parity_capture.observe(
            "inbound",
            {"type": "screen_activity_sync_result", **response.model_dump(mode="json", exclude_none=True)},
        )
        return response
    finally:
        parity_capture.persist()
