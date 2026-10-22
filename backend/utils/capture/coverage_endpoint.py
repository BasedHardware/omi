"""Authenticated, bounded and rate-limited read of committed capture coverage."""

from fastapi import APIRouter, Depends, HTTPException, Query

from models.capture_coverage import AdmitResult, CaptureKey, FrameRange
from utils.capture.coverage import query
from utils.executors import db_executor, run_blocking
from utils.other import endpoints as auth

router = APIRouter()


def _limit(uid):
    from database.redis_db import check_rate_limit

    try:
        allowed, _, retry = check_rate_limit(uid, 'capture_coverage:query', 60, 60)
    except Exception as error:
        raise HTTPException(503, 'Coverage rate limiter unavailable') from error
    if not allowed:
        raise HTTPException(429, 'Coverage query rate exceeded', headers={'Retry-After': str(retry)})


@router.get('/v2/capture-coverage', response_model=AdmitResult)
async def get_capture_coverage(
    capture_root: str = Query(..., min_length=1, max_length=256),
    start: list[int] = Query(..., min_length=1, max_length=32),
    end: list[int] = Query(..., min_length=1, max_length=32),
    channel: str = Query('default', min_length=1, max_length=256),
    clock_epoch: str = Query('default', min_length=1, max_length=256),
    device_id: str | None = Query(None, min_length=1, max_length=256),
    recording_session_id: str | None = Query(None, min_length=1, max_length=256),
    uid: str = Depends(auth.get_current_user_uid),
) -> AdmitResult:
    await run_blocking(db_executor, _limit, uid)
    if len(start) != len(end):
        raise HTTPException(422, 'Capture range endpoints must be paired')
    try:
        key = CaptureKey(
            capture_root=capture_root,
            channel=channel,
            clock_epoch=clock_epoch,
            device_id=device_id,
            recording_session_id=recording_session_id,
        )
        ranges = [FrameRange(start=a, end=b) for a, b in zip(start, end)]
        return await run_blocking(db_executor, query, uid, key, ranges)
    except ValueError as error:
        raise HTTPException(422, 'Invalid or excessive capture ranges') from error
