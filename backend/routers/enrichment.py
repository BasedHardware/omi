"""Enrichment consumer route ``POST /v2/enrichment/run`` (contracts (a), (d)).

A Cloud Tasks wake for one ``sync_reprocess_outbox`` row. The row is the state: the task carries only
``{"kind", "key", "task_token"}``, the same payload the legacy ``/v2/sync-jobs/run`` binding delivers, so
rows bound to either handler drain (contract (b) invariant 7). Responses follow contract (d) only:
200 for consumed deliveries, 409 ``retry`` for expected retries, 400 for a malformed task, and 500 only for
an unexpected exception.
"""

import logging
import os
import re
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from utils.executors import postprocess_executor, run_blocking
from utils.workers.consumer import http_response, run_push

router = APIRouter()
logger = logging.getLogger(__name__)

_KINDS = {'enrichment', 'sync_reprocess'}


def _audience() -> str:
    handler = os.getenv('ENRICHMENT_TASKS_HANDLER_URL', '').strip()
    return os.getenv('ENRICHMENT_TASKS_OIDC_AUDIENCE', '').strip() or handler


def verify_enrichment_task(request: Request) -> int:
    """OIDC for the enrichment queue's invoker; the audience is the enrichment handler (TaskEdge ``enrichment``)."""
    from utils.cloud_tasks import verify_configured_cloud_tasks_oidc

    invoker = os.getenv('ENRICHMENT_TASKS_INVOKER_SA', '').strip() or os.getenv('SYNC_TASKS_INVOKER_SA', '').strip()
    return verify_configured_cloud_tasks_oidc(request, audience=_audience(), invoker_sa=invoker)


def _task(payload: object) -> tuple[str, str] | None:
    if not isinstance(payload, dict) or set(payload) != {'kind', 'key', 'task_token'}:
        return None
    key, token = payload.get('key'), payload.get('task_token')
    if payload.get('kind') not in _KINDS or not isinstance(key, str) or not isinstance(token, str):
        return None
    if not re.fullmatch('[0-9a-f]{64}', key) or not re.fullmatch('[0-9a-f]{32}', token):
        return None
    return key, token


def consume(key: str, token: str):
    """One push delivery through the enrichment consumer; shared with the legacy sync-jobs handler."""
    from database.outbox_firestore import ENRICHMENT_OUTBOX
    from utils.enrichment.consumer import EnrichmentConsumer

    return run_push(EnrichmentConsumer(ENRICHMENT_OUTBOX), ENRICHMENT_OUTBOX, key, token, now=time.time())


@router.post('/v2/enrichment/run', include_in_schema=False)
async def run_enrichment_task(request: Request, _retry_count: int = Depends(verify_enrichment_task)):
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    task = _task(payload)
    if task is None:
        return JSONResponse(status_code=400, content={'status': 'invalid_enrichment_task'})
    from utils.enrichment import outbox

    if not outbox.owns_runtime():
        return JSONResponse(status_code=200, content={'status': 'foreign_runtime'})
    result = await run_blocking(postprocess_executor, consume, *task)
    return http_response(result)


def maintain(now: float) -> dict[str, int]:
    """One maintenance pass: re-wake lost obligations, then admit overdue first-summary debt (C4).

    Both halves are safe beside the legacy sequencer sweep: the outbox sweep is per-row CAS and the
    summary-debt tick holds its own cursor lease, so a second owner never double-admits.
    """
    from database.outbox_firestore import ENRICHMENT_OUTBOX
    from services import summary_debt_repair

    swept = ENRICHMENT_OUTBOX.sweep(now=now)
    counts = {
        'rewoken': swept.rewoken,
        'discarded': swept.discarded,
        'sweep_errors': swept.errors,
        'provider_stt_rewoken': 0,
        'provider_stt_discarded': 0,
        'provider_stt_sweep_errors': 0,
        'summary_debt_scanned': 0,
        'summary_debt_admitted': 0,
        'summary_debt_errors': 0,
    }
    # C8 provider-STT units rely on this sweep when a post-commit wake is lost (contract (b),
    # invariant 4); it shares the enrichment maintenance schedule (M3 review). Its own failure
    # never blocks the enrichment half.
    try:
        from database.outbox import OutboxKind, outbox_for

        provider = outbox_for(OutboxKind.PROVIDER_STT).sweep(now=now)
        counts.update(
            provider_stt_rewoken=provider.rewoken,
            provider_stt_discarded=provider.discarded,
            provider_stt_sweep_errors=provider.errors,
        )
    except Exception as error:
        logger.error('event=provider_stt_sweep outcome=error exception_type=%s', type(error).__name__)
        counts['provider_stt_sweep_errors'] = 1
    try:
        summary = summary_debt_repair.tick(now=now)
    except Exception as error:
        logger.error('event=summary_debt_repair outcome=error exception_type=%s', type(error).__name__)
        summary = {'scanned': 0, 'admitted': 0, 'errors': 1}
    counts.update(
        summary_debt_scanned=summary['scanned'],
        summary_debt_admitted=summary['admitted'],
        summary_debt_errors=summary['errors'],
    )
    return counts


@router.post('/v2/enrichment/sweep', include_in_schema=False)
async def sweep_enrichment(_retry_count: int = Depends(verify_enrichment_task)):
    """Cloud Scheduler ``enrichment-maintenance`` (*/2): 200 with counts; partial errors are counted, not 5xx."""
    from utils.enrichment import outbox

    if not outbox.owns_runtime():
        return JSONResponse(status_code=200, content={'status': 'foreign_runtime'})
    counts = await run_blocking(postprocess_executor, maintain, time.time())
    return JSONResponse(status_code=200, content={'status': 'swept', 'counts': counts})
