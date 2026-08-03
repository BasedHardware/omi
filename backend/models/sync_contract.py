"""OpenAPI response contracts for the asynchronous local-file sync route."""

from pydantic import BaseModel


class SyncRequestValidationErrorResponse(BaseModel):
    """FastAPI's multipart/request validation shape for sync input failures."""

    detail: list[dict[str, object]]


class SyncRecoveryWindowExceededResponse(BaseModel):
    code: str
    detail: str
    lane: str | None = None


SYNC_LOCAL_FILES_V2_RESPONSES = {
    422: {
        'model': SyncRecoveryWindowExceededResponse | SyncRequestValidationErrorResponse,
        'description': 'Automatic recovery window exceeded or malformed request',
    }
}
