import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from utils.other.endpoints import get_current_user_uid

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

    def storage_id(self) -> str:
        return f"{self.client_device_id}-{self.id}" if self.client_device_id else str(self.id)


class ScreenActivitySyncRequest(BaseModel):
    rows: list[ScreenActivityRow]


@router.post("/v1/screen-activity/sync")
def retire_screen_activity_sync(
    request: ScreenActivitySyncRequest,
    uid: str = Depends(get_current_user_uid),
) -> dict[str, int]:
    """Tombstone for the retired screen-activity sync route. Stores nothing, ever.

    LIFECYCLE: one-time
    DELETE-AFTER: https://github.com/BasedHardware/omi/issues/11018

    The shipped desktop client treats only HTTP 200 as success and never
    advances its cursor otherwise. It has no terminal-status handling, no
    max-attempt limit, and no server-driven kill switch, so a 404/410 makes it
    re-POST the *same* OCR batch every five minutes forever: more transmitted
    screen text and more battery burn than before the change, on installs that
    cannot be updated. Returning 200 with the released response shape lets
    those clients advance past their backlog and go quiet.

    `request` is accepted only so a released app-client contract keeps its body
    and response schema (FastAPI still validates both, which lets an
    un-updated client drain); the body is then discarded and never read,
    parsed, logged, or written: no Firestore document, no Pinecone vector, no
    log line derived from the payload. Nothing is stored, so the response's
    released `0 synced` counts are always zero. This endpoint is a drain, not
    a sink.

    This does not fully close the egress — the un-updated client that transmits
    the OCR payload is still answered. Only a client that stops uploading does
    that, which is why this is temporary and paired with a client change.
    """
    del request
    logger.info("Discarding retired screen-activity sync payload uid=%s", uid)
    return {"synced": 0, "last_id": 0}
