"""Compatible admission responses for clients recovering retained sync audio."""

from typing import Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse


def sync_content_in_progress_response(job_id: Optional[str]) -> JSONResponse:
    # Shipped clients keep the 409/Retry-After contract. New clients follow the
    # current owner instead of repeatedly posting the same audio bytes.
    return JSONResponse(
        status_code=409,
        headers={'Retry-After': '10'},
        content={
            'code': 'sync_content_in_progress',
            'detail': 'The same audio is already processing',
            'job_id': job_id,
            'poll_after_ms': 10000,
        },
    )


def sync_finalization_retrying() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail='Sync recovery finalization is retrying; local audio remains available.',
        headers={'Retry-After': '10'},
    )
