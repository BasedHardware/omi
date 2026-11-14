"""Operator-only, aggregate-only reads over the C1 in-flight ledger.

Two routes, both behind the same service-OIDC gate as the batch worker RPC:

- ``GET /v2/pipeline-ledger/census`` returns exact **fleet-global** counts by
  stage, stuck-past-deadline counts, the Home-visible share on the real-speech
  denominator, coverage and per-end-type latency. It never returns a uid,
  conversation id, title, transcript or audio path. The fleet-global read is the
  documented exception to the C1 owner-scoped helper and goes through
  ``pipeline_ledger.iter_global_window``.
- ``GET /v2/pipeline-ledger/explain/{conversation_id}`` returns one
  operator-supplied conversation's ledger transition list. It is for a human
  debugging one row, never for the ramp decision.

``explain`` is an **operator capability**, not a caller-scoped read: the
service-OIDC gate authenticates the census invoker service account, not an
individual owner, so any holder of that token can name any owner. The owner is
an explicit required binding and the audit log records only a hash of it.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from database import pipeline_ledger_census
from utils.conversations import pipeline_ledger_metrics
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)


def verify_census(request: Request) -> None:
    """Service-OIDC gate; unset env means this service is not a census target."""
    from utils.cloud_tasks import verify_configured_cloud_tasks_oidc

    audience = os.getenv('PIPELINE_LEDGER_CENSUS_AUDIENCE', '').strip()
    invoker = os.getenv('PIPELINE_LEDGER_CENSUS_INVOKER_SA', '').strip()
    verify_configured_cloud_tasks_oidc(request, audience=audience, invoker_sa=invoker, log_failure=False)


router = APIRouter(prefix='/v2/pipeline-ledger', dependencies=[Depends(verify_census)])


def _parse_time(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        parsed = None
    if parsed is not None:
        if not math.isfinite(parsed):
            raise HTTPException(status_code=422, detail='start and end must be finite')
        return parsed
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=422, detail='start and end must be ISO-8601 or epoch seconds') from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def _owner(uid: str) -> str:
    if not uid or len(uid) > 128 or '/' in uid:
        raise HTTPException(status_code=422, detail='uid is required')
    return uid


@router.get('/census', include_in_schema=False)
async def get_census(
    start: str = Query(...),
    end: str = Query(...),
) -> Any:
    start_epoch, end_epoch = _parse_time(start), _parse_time(end)
    if end_epoch <= start_epoch:
        raise HTTPException(status_code=422, detail='end must be after start')
    try:
        result = await run_blocking(
            db_executor,
            pipeline_ledger_census.census,
            start_epoch,
            end_epoch,
        )
    except pipeline_ledger_census.pipeline_ledger.LedgerWindowTruncated:
        raise HTTPException(status_code=503, detail='ledger window truncated; fail closed') from None
    except pipeline_ledger_census.CensusSchemaMismatch:
        raise HTTPException(status_code=503, detail='ledger schema mismatch; fail closed') from None
    pipeline_ledger_metrics.refresh_gauges(result)
    result['window'] = {'start': start_epoch, 'end': end_epoch, 'seconds': end_epoch - start_epoch}
    return JSONResponse(result)


@router.get('/explain/{conversation_id}', include_in_schema=False)
async def get_explain(
    conversation_id: str,
    uid: str = Query(..., min_length=1, max_length=128),
) -> Any:
    owner = _owner(uid)
    if not conversation_id or len(conversation_id) > 128 or '/' in conversation_id:
        raise HTTPException(status_code=422, detail='conversation_id is required')
    result = await run_blocking(db_executor, pipeline_ledger_census.explain, owner, conversation_id)
    if result is None:
        raise HTTPException(status_code=404, detail='ledger row not found')
    logger.info(
        'event=pipeline_ledger_explain conversation=%s owner=%s',
        hashlib.sha256(conversation_id.encode()).hexdigest()[:8],
        hashlib.sha256(owner.encode()).hexdigest()[:8],
    )
    return JSONResponse(result)
