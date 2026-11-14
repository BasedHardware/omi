"""Batch provider-STT route ``POST /v2/batch-pipeline/provider-stt/run`` (contracts (a), (d)).

A Cloud Tasks wake ``pst-{row_id}-{wake_token}`` for one ``provider_stt`` outbox row. The row is the only state.
Responses follow contract (d): 200 for every consumed delivery, 409 ``retry`` for expected retries, 400 for a
malformed task, 500 only for an unexpected exception. Never 429 or 503.

Mounted once in ``main.py`` by lane 1 after #22388's ``main.py`` edit reaches integration.
"""

import os
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from config.batch_pipeline import merge_head_wait_seconds, provider_merge_membership_enabled
from database.outbox import Outbox, OutboxKind, outbox_for
from utils.batch_pipeline.provider_drain import OwnerDrainCoalescer
from utils.batch_pipeline.provider_stt import ProviderSttConsumer
from utils.batch_pipeline.serving import serving_for_stage
from utils.executors import run_blocking, sync_executor
from utils.sync.stage import current_stage
from utils.workers.consumer import Result, http_response, run_push, run_push_async

ROUTE = '/v2/batch-pipeline/provider-stt/run'
_BOUNDED_ID = 128


def verify_provider_stt_task(request: Request) -> int:
    from utils.cloud_tasks import verify_configured_cloud_tasks_oidc

    audience = (
        os.getenv('PROVIDER_STT_TASKS_OIDC_AUDIENCE', '').strip()
        or os.getenv('PROVIDER_STT_TASKS_HANDLER_URL', '').strip()
    )
    return verify_configured_cloud_tasks_oidc(
        request, audience=audience, invoker_sa=os.getenv('SYNC_TASKS_INVOKER_SA', '').strip()
    )


router = APIRouter()


def _bounded(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= _BOUNDED_ID and '/' not in value


def _malformed() -> JSONResponse:
    return JSONResponse(status_code=400, content={'status': 'malformed'})


def run_delivery(
    row_id: str, wake_token: str, *, consumer: ProviderSttConsumer | None = None, outbox: Outbox | None = None
) -> Result:
    return run_push(
        consumer or ProviderSttConsumer(),
        outbox or outbox_for(OutboxKind.PROVIDER_STT),
        row_id,
        wake_token,
        now=time.time(),
    )


async def _run_sync(fn, *args, **kwargs):
    return await run_blocking(sync_executor, fn, *args, **kwargs)


async def _drain_owner(owner_id: str) -> None:
    service = await _run_sync(serving_for_stage, current_stage())
    await service.drain_settled_async(owner_id)


# Per process; created on first use so importing this router constructs nothing.
_owner_drains: OwnerDrainCoalescer | None = None


def wake_owner_merge(owner_id: str) -> None:
    """The settled-unit hook: one coalesced ordered-merge drain for the owner (kill-switched)."""
    global _owner_drains
    if not provider_merge_membership_enabled():
        return
    if _owner_drains is None:
        _owner_drains = OwnerDrainCoalescer(_drain_owner, head_wait=merge_head_wait_seconds)
    _owner_drains.request(owner_id)


async def run_delivery_async(
    row_id: str, wake_token: str, *, consumer: ProviderSttConsumer | None = None, outbox: Outbox | None = None
) -> Result:
    """The serving delivery: store/GCS/VAD work on the sync executor, the vendor call awaited on the
    event loop (Velma batch is synchronous-only, so its open request must not hold a thread)."""
    return await run_push_async(
        consumer or ProviderSttConsumer(settled=wake_owner_merge),
        outbox or await _run_sync(outbox_for, OutboxKind.PROVIDER_STT),
        row_id,
        wake_token,
        now=time.time(),
        run_sync=_run_sync,
    )


@router.post(ROUTE, include_in_schema=False)
async def run_provider_stt(request: Request, _retry_count: int = Depends(verify_provider_stt_task)):
    try:
        body = await request.json()
    except ValueError:
        return _malformed()
    if (
        not isinstance(body, dict)
        or set(body) != {'kind', 'row_id', 'wake_token'}
        or body['kind'] != OutboxKind.PROVIDER_STT.value
        or not _bounded(body['row_id'])
        or not _bounded(body['wake_token'])
    ):
        return _malformed()
    return http_response(await run_delivery_async(body['row_id'], body['wake_token']))
