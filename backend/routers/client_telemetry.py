"""Authenticated client telemetry ingest and admin aggregate reads.

POST /v1/telemetry/client/batches derives the owner from the Firebase bearer
token. GET /v1/telemetry/client/aggregates requires the backend admin key
(X-Admin-Key), the same gate the admin proxy uses after verifyAdmin. Ordinary
user tokens cannot read aggregates. Migration flags default off and do not
turn this collector on or off; parent activation is separate.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from config.client_telemetry import MAX_REQUEST_BYTES, QUERY_CHANNELS, TelemetryContractError
from database.client_telemetry import accept_batch, query_is_stale, recent_owner_ids
from database.client_telemetry_ops import (
    channel_roster,
    enroll_channel,
    purge_expired_observations,
    seal_settled_day,
)
from utils.client_telemetry_metrics import record_ingest
from utils.executors import db_executor, run_blocking
from utils.other.endpoints import get_current_user_uid

logger = logging.getLogger(__name__)

router = APIRouter()


def _error(error: TelemetryContractError) -> HTTPException:
    headers = None
    if error.retry_after is not None:
        headers = {"Retry-After": str(error.retry_after)}
    return HTTPException(
        status_code=error.status,
        detail={"code": error.code, "message": error.message},
        headers=headers,
    )


def _verify_admin(presented: str | None) -> None:
    expected = os.environ.get("ADMIN_KEY", "")
    if not expected or presented is None or not hmac.compare_digest(presented, expected):
        record_ingest("forbidden")
        raise HTTPException(
            status_code=403,
            detail={"code": "telemetry_forbidden", "message": "admin key required"},
        )


async def _raw_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            size = int(declared)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={"code": "telemetry_invalid", "message": "content-length is not an integer"},
            )
        if size > MAX_REQUEST_BYTES:
            record_ingest("too_large")
            raise HTTPException(
                status_code=413,
                detail={"code": "telemetry_too_large", "message": "request exceeds 128 KiB"},
            )
    raw = await request.body()
    if len(raw) > MAX_REQUEST_BYTES:
        record_ingest("too_large")
        raise HTTPException(
            status_code=413,
            detail={"code": "telemetry_too_large", "message": "request exceeds 128 KiB"},
        )
    return raw


@router.post("/v1/telemetry/client/batches", tags=["telemetry"])
async def post_client_telemetry_batch(request: Request, uid: str = Depends(get_current_user_uid)) -> Any:
    raw = await _raw_body(request)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        record_ingest("invalid")
        raise HTTPException(
            status_code=422,
            detail={"code": "telemetry_invalid", "message": "request body is not valid JSON"},
        )
    try:
        result = await run_blocking(db_executor, accept_batch, uid, payload)
        note_roster_hint(uid)
    except TelemetryContractError as error:
        record_ingest(_metric_for(error))
        raise _error(error) from error
    if result.get("status") == 409:
        record_ingest("conflict")
        raise HTTPException(
            status_code=409,
            detail={"code": "telemetry_conflict", "message": result.get("message", "event payload conflict")},
        )
    record_ingest("accepted")
    logger.info(
        "client telemetry batch owner=%s accepted=%s duplicate=%s",
        uid,
        result.get("accepted_count"),
        result.get("duplicate_count"),
    )
    return {
        "schema_version": 1,
        "batch_id": result["batch_id"],
        "accepted_count": result["accepted_count"],
        "duplicate_count": result["duplicate_count"],
    }


@router.get("/v1/telemetry/client/aggregates", tags=["telemetry"])
async def get_client_telemetry_aggregates(
    days: int = Query(..., ge=1, le=90),
    channel: str = Query(...),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    x_admin_user: str | None = Header(default=None, alias="X-Admin-User"),
) -> Any:
    _verify_admin(x_admin_key)
    if channel not in QUERY_CHANNELS:
        raise HTTPException(
            status_code=422,
            detail={"code": "telemetry_invalid", "message": "channel must be production, beta, or all"},
        )
    actor = None
    if x_admin_user:
        actor = hashlib.sha256(x_admin_user.encode("utf-8")).hexdigest()[:8]
        logger.info("client telemetry aggregate read admin=%s days=%s channel=%s", actor, days, channel)
    try:
        payload, stale = await run_blocking(db_executor, _query_aggregates_classified, days, channel)
    except TelemetryContractError as error:
        record_ingest(_metric_for(error))
        raise _error(error) from error
    if stale:
        record_ingest("stale")
        logger.warning("client telemetry aggregate coverage is stale days=%s channel=%s", days, channel)
    return JSONResponse(payload)


def _query_aggregates_classified(days: int, channel: str) -> tuple[dict[str, Any], bool]:
    """Query with the durable channel roster when one has been seeded.

    No roster documents yet -> behave exactly like the unclassified query
    (feed stays `partial` honestly). With a roster -> unmatched actors are
    excluded and classification completeness is enforced by the query layer.
    """
    roster = channel_roster(_roster_owners())
    return query_is_stale(days=days, channel=channel, channel_by_actor=roster)


_ROSTER_HINTS: set[str] = set()


def _roster_owners() -> set[str]:
    """Owners worth a roster lookup: recent ingests plus explicitly enrolled ids."""
    owners = set(_ROSTER_HINTS)
    owners.update(recent_owner_ids())
    return owners


def note_roster_hint(owner: str) -> None:
    """Ingest path hints the query side which owners are active."""
    if owner.strip():
        _ROSTER_HINTS.add(owner)
        if len(_ROSTER_HINTS) > 512:
            _ROSTER_HINTS.clear()


def _metric_for(error: TelemetryContractError) -> str:
    if error.status == 429:
        return "rate_limited"
    if error.status == 409:
        return "conflict"
    if error.status == 413:
        return "too_large"
    if error.code == "telemetry_query_truncated":
        return "truncated"
    if error.status == 503:
        return "unavailable"
    return "invalid"


@router.post("/v1/telemetry/client/ops/seal-day", tags=["telemetry"])
async def post_seal_day(
    request: Request,
    x_admin_key: str | None = Header(default=None),
) -> Any:
    """Cron-invocable rollup sealing for settled UTC days. Admin key required."""
    _verify_admin(x_admin_key)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    day = payload.get("day") if isinstance(payload, dict) else None
    if not isinstance(day, str):
        raise HTTPException(
            status_code=422,
            detail={"code": "telemetry_invalid", "message": "body must carry day: YYYY-MM-DD"},
        )
    try:
        receipt = await run_blocking(db_executor, seal_settled_day, day)
    except TelemetryContractError as error:
        record_ingest(_metric_for(error))
        raise _error(error) from error
    record_ingest("sealed")
    return JSONResponse(receipt)


@router.post("/v1/telemetry/client/ops/purge-expired", tags=["telemetry"])
async def post_purge_expired(
    request: Request,
    x_admin_key: str | None = Header(default=None),
) -> Any:
    """Cron-invocable durable retention cleanup. Admin key required."""
    _verify_admin(x_admin_key)
    try:
        removed = await run_blocking(db_executor, purge_expired_observations)
    except TelemetryContractError as error:
        record_ingest(_metric_for(error))
        raise _error(error) from error
    record_ingest("purged")
    return JSONResponse({"purged": removed})


@router.post("/v1/telemetry/client/ops/enroll-channel", tags=["telemetry"])
async def post_enroll_channel(
    request: Request,
    x_admin_key: str | None = Header(default=None),
) -> Any:
    """Seed the durable channel roster for one owner. Admin key required."""
    _verify_admin(x_admin_key)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    owner = payload.get("owner") if isinstance(payload, dict) else None
    channel = payload.get("channel") if isinstance(payload, dict) else None
    if not isinstance(owner, str) or not isinstance(channel, str):
        raise HTTPException(
            status_code=422,
            detail={"code": "telemetry_invalid", "message": "body must carry owner and channel"},
        )
    try:
        document = await run_blocking(db_executor, enroll_channel, owner, channel)
    except TelemetryContractError as error:
        record_ingest(_metric_for(error))
        raise _error(error) from error
    record_ingest("enrolled")
    return JSONResponse(document)
