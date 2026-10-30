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

from database.outbox import Outbox, OutboxKind, outbox_for
from utils.batch_pipeline.provider_stt import ProviderSttConsumer
from utils.executors import run_blocking, sync_executor
from utils.workers.consumer import Result, http_response, run_push

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
    result = await run_blocking(sync_executor, run_delivery, body['row_id'], body['wake_token'])
    return http_response(result)
