import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from database.screen_activity import normalize_screen_activity_timestamp, upsert_screen_activity
from database.vector_db import upsert_screen_activity_vectors
from utils.executors import db_executor, run_blocking
from utils.other.endpoints import get_current_user_uid
from utils.subscription import grants_cloud_screen_vectors
from utils.subscription import is_desktop_trial_paywalled
from testing.parity_pack_v0.live_capture import SurfaceParityCapture

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
    rows: list[ScreenActivityRow]


async def _authorized_desktop_user(uid: str = Depends(get_current_user_uid)) -> str:
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


@router.post("/v1/screen-activity/sync")
async def sync_screen_activity(
    request: ScreenActivitySyncRequest, uid: str = Depends(_authorized_desktop_user)
) -> dict[str, int]:
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
        response = {"synced": written, "last_id": max(row.id for row in request.rows)}
        parity_capture.observe("inbound", {"type": "screen_activity_sync_result", **response})
        return response
    finally:
        parity_capture.persist()
