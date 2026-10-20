"""OpenAPI response contracts for the asynchronous local-file sync route."""

from pydantic import BaseModel


class SyncRequestValidationErrorResponse(BaseModel):
    """FastAPI's multipart/request validation shape for sync input failures."""

    detail: list[dict[str, object]]


class SyncRecoveryWindowExceededResponse(BaseModel):
    code: str
    detail: str
    lane: str | None = None


class SyncContentInProgressResponse(BaseModel):
    """A duplicate upload follows its live owner; older servers omit hints."""

    code: str
    detail: str = 'The same audio is already processing'
    job_id: str | None = None
    poll_after_ms: int | None = None


SYNC_LOCAL_FILES_V2_RESPONSES = {
    409: {
        'model': SyncContentInProgressResponse,
        'description': 'The same audio is already processing; follow its owner when present',
    },
    422: {
        'model': SyncRecoveryWindowExceededResponse | SyncRequestValidationErrorResponse,
        'description': 'Automatic recovery window exceeded or malformed request',
    },
}
