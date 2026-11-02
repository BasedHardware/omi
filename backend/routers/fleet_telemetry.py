"""Firebase-authenticated, bounded fleet summaries. No event-level persistence."""

import asyncio
import json
from functools import lru_cache
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.exceptions import RedisError
from starlette.requests import ClientDisconnect

from config.fleet_telemetry import MAX_BYTES, FleetValidationError, validate_summary
from database.redis_db import create_bounded_redis_client, reserve_rate_limit
from utils.executors import critical_executor, db_executor, run_blocking
from utils.observability.fleet import record_summary, reject
from utils.other.endpoints import get_current_user_uid

router = APIRouter()


def deny(reason: str, status: int = 422, headers: dict[str, str] | None = None) -> NoReturn:
    reject(reason)
    raise HTTPException(status_code=status, detail={'code': reason}, headers=headers)


@lru_cache(maxsize=1)
def limiter_client():
    return create_bounded_redis_client(1.0)


def enforce_limit(uid):
    try:
        allowed, _, reset = reserve_rate_limit(uid, 'telemetry:fleet', 12, 3600, redis_client=limiter_client())
    except RedisError:
        # This optional sink fails closed. Do not turn a Redis outage into hot ingest.
        deny('limiter_unavailable', 503, {'Retry-After': '60'})
    if not allowed:
        deny('rate_limited', 429, {'Retry-After': str(max(1, reset))})


async def read_summary(request):
    if request.headers.get('content-encoding', 'identity').strip().lower() != 'identity':
        deny('invalid_schema', 415)
    declared = request.headers.get('content-length')
    if declared is not None:
        try:
            length = int(declared)
        except ValueError:
            deny('invalid_schema', 400)
        if length < 0:
            deny('invalid_schema', 400)
        if length > MAX_BYTES:
            deny('too_large', 413)
    raw = bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(raw) + len(chunk) > MAX_BYTES:
                    deny('too_large', 413)
                raw.extend(chunk)
    except (TimeoutError, ClientDisconnect):
        deny('body_timeout', 408)
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):
        deny('invalid_schema')


def validate_and_record(payload):
    try:
        summary, clamped = validate_summary(payload)
    except (FleetValidationError, ValueError, OverflowError) as error:
        deny(error.reason if isinstance(error, FleetValidationError) else 'invalid_schema')
    record_summary(summary)
    return {'schema_version': 1, 'accepted': True, 'clamped': clamped}


@router.post('/v1/telemetry/fleet', tags=['telemetry'])
async def fleet_summary(request: Request, uid: str = Depends(get_current_user_uid)):
    await run_blocking(critical_executor, enforce_limit, uid)
    payload = await read_summary(request)
    return await run_blocking(db_executor, validate_and_record, payload)
