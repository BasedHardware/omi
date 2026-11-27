"""A provider 5xx on the v3 outline path must not surface as an unhandled 500.

Live prod signature (ro-prod, 2026-11-19, group ``CIqco6zElomJFg``, 243 events/24h):

    openai.InternalServerError: Error code: 502 - {'error': {'message':
    'provider request failed: provider_5xx_omi_paid', ...}}
    raised from utils/conversations/v3/models.py outline
    through utils/executors.py _tracked to the ASGI handler

The Cloud Tasks builder routes are the request boundary for that call. They
answer the task-target contract (409 ``retry_response``); only the synchronous
mobile caller receives 503 + ``Retry-After``.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import asyncio  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

import httpx  # noqa: E402
import openai  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException, Request  # noqa: E402
from google.api_core.exceptions import Aborted, InvalidArgument  # noqa: E402

from database.conversations_v3_fence import ProcessingPersistenceFenced  # noqa: E402
from database.firestore_transaction_retry import FirestoreContentionExhausted  # noqa: E402
from routers import conversations_v3_tasks as route  # noqa: E402
from utils.conversations.processing_metrics import RETRYABLE_PROCESSING_RESPONSES_TOTAL  # noqa: E402
from utils.conversations.v3 import (  # noqa: E402
    Conflict,
    backfill,
    metrics,
    request_log_trace_id,
    service,
)
from utils.executors import start_background_task  # noqa: E402
from utils.llm.gateway_error_contract import (  # noqa: E402
    RETRYABLE_CONVERSATION_PROCESSING_ERROR_CODE,
    RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL,
    RETRYABLE_PROVIDER_FAILURE_SWITCH,
    retryable_provider_failure_http_exception,
)

_REQUEST = httpx.Request('POST', 'https://provider.invalid/v1/chat/completions')


def provider_502() -> openai.InternalServerError:
    """The exact class and status prod logged for the outline burst."""
    response = httpx.Response(502, request=_REQUEST)
    return openai.InternalServerError('provider request failed: provider_5xx_omi_paid', response=response, body=None)


def assert_retryable(mapped: HTTPException) -> None:
    assert mapped.status_code == 503
    assert mapped.detail == RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL
    assert mapped.detail['code'] == RETRYABLE_CONVERSATION_PROCESSING_ERROR_CODE
    assert mapped.headers['Retry-After'] == '2'


def assert_task_retry(response, reason: str) -> None:
    assert response.status_code == 409
    assert json.loads(response.body) == {'status': 'retry', 'reason': reason}
    assert 'retry-after' not in response.headers


def retryable_response_metric_total() -> float:
    return sum(child._value.get() for child in RETRYABLE_PROCESSING_RESPONSES_TOTAL._metrics.values())


# ---------------------------------------------------------------------------
# The boundary adapter
# ---------------------------------------------------------------------------


def test_provider_5xx_maps_to_the_retryable_contract():
    mapped = retryable_provider_failure_http_exception(provider_502(), route='conversations_v3_reconcile')

    assert mapped is not None
    assert_retryable(mapped)


def test_non_provider_failure_is_not_mapped():
    """A programming error must keep its loud 500, not become a retryable 503."""
    assert retryable_provider_failure_http_exception(ValueError('bug'), route='conversations_v3_reconcile') is None


def test_kill_switch_restores_the_original_failure(monkeypatch):
    monkeypatch.setenv(RETRYABLE_PROVIDER_FAILURE_SWITCH, 'off')

    assert retryable_provider_failure_http_exception(provider_502(), route='conversations_v3_reconcile') is None


def test_mapped_route_records_the_registered_metric_label():
    """The internal route labels must stay registered, not collapse to 'other'."""
    metric = RETRYABLE_PROCESSING_RESPONSES_TOTAL.labels(
        failure_class='provider_status', route='conversations_v3_reconcile'
    )
    before = metric._value.get()

    mapped = retryable_provider_failure_http_exception(provider_502(), route='conversations_v3_reconcile')

    assert mapped is not None
    assert metric._value.get() == before + 1


# ---------------------------------------------------------------------------
# The Cloud Tasks builder routes
# ---------------------------------------------------------------------------


@pytest.fixture
def reconcile_request():
    return Request({'type': 'http', 'headers': [(b'x-cloud-trace-context', b'a' * 32 + b'/42')]})


@pytest.mark.asyncio
async def test_reconcile_route_answers_provider_5xx_as_task_retry(monkeypatch, reconcile_request):
    async def fail(_uid, *, background):
        assert background is True
        assert request_log_trace_id() == 'a' * 32
        raise provider_502()

    monkeypatch.setattr(service, 'reconcile', fail)

    response = await route.reconcile(route.ReconcileRequest(uid='u'), reconcile_request, _retry=0)

    assert_task_retry(response, 'dependency_warming')
    assert request_log_trace_id() == '-'


@pytest.mark.asyncio
async def test_reconcile_route_keeps_a_non_provider_failure_loud(monkeypatch, reconcile_request):
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=ValueError('bug')))

    with pytest.raises(ValueError):
        await route.reconcile(route.ReconcileRequest(uid='u'), reconcile_request, _retry=0)


@pytest.mark.asyncio
async def test_reconcile_route_answers_owner_busy_as_a_locked_task_retry(monkeypatch, reconcile_request):
    monkeypatch.setattr(service, 'reconcile', AsyncMock(return_value='busy'))
    body = route.ReconcileRequest(uid='u', trigger='native_manual_ready')

    response = await route.reconcile(body, reconcile_request, _retry=0)

    assert_task_retry(response, 'locked')


@pytest.mark.asyncio
async def test_reconcile_route_kill_switch_restores_the_original_failure(monkeypatch, reconcile_request):
    monkeypatch.setenv(RETRYABLE_PROVIDER_FAILURE_SWITCH, 'off')
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=provider_502()))

    with pytest.raises(openai.InternalServerError):
        await route.reconcile(route.ReconcileRequest(uid='u'), reconcile_request, _retry=0)


@pytest.mark.asyncio
async def test_reconcile_route_translates_an_already_typed_retry_answer(monkeypatch, reconcile_request):
    """Translate the typed mobile retry answer without recording its metric twice."""
    typed = HTTPException(status_code=503, detail=RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL)
    typed.__cause__ = provider_502()
    before = retryable_response_metric_total()
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=typed))

    response = await route.reconcile(route.ReconcileRequest(uid='u'), reconcile_request, _retry=0)

    assert_task_retry(response, 'dependency_warming')
    assert retryable_response_metric_total() == before


@pytest.mark.asyncio
async def test_reconcile_route_does_not_override_a_typed_non_retryable_answer(monkeypatch, reconcile_request):
    typed = HTTPException(status_code=500, detail='deliberate')
    typed.__cause__ = provider_502()
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=typed))

    with pytest.raises(HTTPException) as raised:
        await route.reconcile(route.ReconcileRequest(uid='u'), reconcile_request, _retry=0)

    assert raised.value is typed


@pytest.mark.asyncio
async def test_backfill_route_answers_provider_5xx_as_task_retry(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_BACKFILL', 'on')
    monkeypatch.setattr(backfill, 'run_step', AsyncMock(side_effect=provider_502()))
    body = route.BackfillRequest(uid='u', run_id='run-1', partition=0)
    metric = RETRYABLE_PROCESSING_RESPONSES_TOTAL.labels(
        failure_class='provider_status', route='conversations_v3_backfill'
    )
    before = metric._value.get()

    response = await route.run_backfill(body, _retry=0)

    assert_task_retry(response, 'dependency_warming')
    assert metric._value.get() == before + 1


@pytest.mark.asyncio
async def test_backfill_route_keeps_owner_busy_as_a_locked_task_retry(monkeypatch):
    """BackfillRetry must keep its own answer, not be remapped as a provider fault."""
    monkeypatch.setenv('CONVERSATIONS_V3_BACKFILL', 'on')
    monkeypatch.setattr(backfill, 'run_step', AsyncMock(side_effect=backfill.BackfillRetry('busy')))
    body = route.BackfillRequest(uid='u', run_id='run-1', partition=0)

    response = await route.run_backfill(body, _retry=0)

    assert_task_retry(response, 'locked')


@pytest.mark.asyncio
async def test_backfill_route_translates_an_already_typed_retry_answer(monkeypatch):
    """Translate the boundary's typed mobile answer without a second metric."""
    monkeypatch.setenv('CONVERSATIONS_V3_BACKFILL', 'on')
    typed = HTTPException(status_code=503, detail=RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL)
    typed.__cause__ = provider_502()
    before = retryable_response_metric_total()
    monkeypatch.setattr(backfill, 'run_step', AsyncMock(side_effect=typed))
    body = route.BackfillRequest(uid='u', run_id='run-1', partition=0)

    response = await route.run_backfill(body, _retry=0)

    assert_task_retry(response, 'dependency_warming')
    assert retryable_response_metric_total() == before


@pytest.mark.asyncio
async def test_backfill_route_does_not_override_a_typed_non_retryable_answer(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_BACKFILL', 'on')
    typed = HTTPException(status_code=500, detail='deliberate')
    typed.__cause__ = provider_502()
    monkeypatch.setattr(backfill, 'run_step', AsyncMock(side_effect=typed))
    body = route.BackfillRequest(uid='u', run_id='run-1', partition=0)

    with pytest.raises(HTTPException) as raised:
        await route.run_backfill(body, _retry=0)

    assert raised.value is typed


@pytest.mark.asyncio
async def test_backfill_route_kill_switch_restores_the_original_failure(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_BACKFILL', 'on')
    monkeypatch.setenv(RETRYABLE_PROVIDER_FAILURE_SWITCH, 'off')
    monkeypatch.setattr(backfill, 'run_step', AsyncMock(side_effect=provider_502()))
    body = route.BackfillRequest(uid='u', run_id='run-1', partition=0)

    with pytest.raises(openai.InternalServerError):
        await route.run_backfill(body, _retry=0)


# ---------------------------------------------------------------------------
# The shared background-task done callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['v3-paid-work', 'v3-reconcile-open'])
async def test_opted_in_background_task_logs_a_provider_fault_as_a_bounded_warning(caplog, name):
    """The v3 outline tasks own a queue retry; their done callback must not
    log the provider body at ERROR (which Error Reporting would group)."""
    caplog.set_level(logging.WARNING)

    async def fail():
        raise provider_502()

    task = start_background_task(fail(), name=name, bounded_provider_failure=True)
    with pytest.raises(openai.InternalServerError):
        await task
    await asyncio.sleep(0.01)  # let the done callback run

    assert any(
        record.levelno == logging.WARNING and 'transient provider failure' in record.getMessage()
        for record in caplog.records
    )
    assert not any(
        record.levelno == logging.ERROR and 'background_task failed' in record.getMessage() for record in caplog.records
    )
    assert 'provider_5xx_omi_paid' not in caplog.text


@pytest.mark.asyncio
async def test_background_task_keeps_a_provider_fault_loud_without_the_opt_in(caplog):
    """A fire-and-forget task with no queue retry keeps its loud ERROR."""
    caplog.set_level(logging.WARNING)

    async def fail():
        raise provider_502()

    task = start_background_task(fail(), name='other-background-work')
    with pytest.raises(openai.InternalServerError):
        await task
    await asyncio.sleep(0.01)

    assert any(
        record.levelno == logging.ERROR and 'background_task failed' in record.getMessage() for record in caplog.records
    )


@pytest.mark.asyncio
async def test_opted_in_background_task_keeps_a_non_provider_failure_loud(caplog):
    caplog.set_level(logging.WARNING)

    async def fail():
        raise ValueError('bug')

    task = start_background_task(fail(), name='v3-paid-work', bounded_provider_failure=True)
    with pytest.raises(ValueError):
        await task
    await asyncio.sleep(0.01)

    assert any(
        record.levelno == logging.ERROR and 'background_task failed' in record.getMessage() for record in caplog.records
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'kind,reason',
    [
        ('transaction_contention', 'dependency_warming'),
        ('transaction_expired', 'dependency_warming'),
        ('transaction_retry_deadline', 'dependency_warming'),
        ('processing_source_changed', 'persistence_fenced'),
        ('v3_processing_not_completed', 'persistence_fenced'),
    ],
)
async def test_reconcile_counts_expected_task_retries(monkeypatch, reconcile_request, kind, reason):
    if kind.startswith('transaction_'):
        error = FirestoreContentionExhausted(
            'retry budget exhausted',
            reason='deadline_exhausted' if kind == 'transaction_retry_deadline' else 'attempts_exhausted',
        )
        error.__cause__ = (
            Aborted('cross-transaction contention')
            if kind != 'transaction_expired'
            else InvalidArgument('The referenced transaction has expired or is no longer valid')
        )
    else:
        error = Conflict(kind) if kind == 'processing_source_changed' else ProcessingPersistenceFenced(kind)
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=error))
    count = metrics.RACES.labels(kind)
    before = count._value.get()
    body = route.ReconcileRequest(uid='u')

    response = await route.reconcile(body, reconcile_request, _retry=1)
    assert response.status_code == 409
    assert response.body == b'{"status":"retry","reason":"' + reason.encode() + b'"}'
    assert count._value.get() == before + 1

    monkeypatch.setenv('CONVERSATIONS_V3_RECONCILE_RETRY_RESPONSE', 'off')
    with pytest.raises(type(error)):
        await route.reconcile(body, reconcile_request, _retry=1)
    assert count._value.get() == before + 1


@pytest.mark.asyncio
@pytest.mark.parametrize('handled', [False, True])
async def test_summary_lease_release_preserves_only_propagating_failure(monkeypatch, reconcile_request, handled):
    row = {'id': 'c', 'v3_process_pending': True}
    failure = service.FinalizationOwnedElsewhere() if handled else ValueError('unexpected processing failure')

    async def run(_executor, func, *_args):
        if func is service.pending_processing:
            return [row]
        if func is service.leases.acquire:
            return 'token'
        if func is service._load_processing_row:
            return row
        assert func is service.leases.release
        raise FirestoreContentionExhausted('release contention')

    async def reconcile(uid, *, background):
        assert background is True
        return await service.drain_processing(uid)

    monkeypatch.setattr(service, 'run_blocking', run)
    monkeypatch.setattr(service, '_process_leased', AsyncMock(side_effect=failure))
    monkeypatch.setattr(service, 'reconcile', reconcile)

    if handled:
        response = await route.reconcile(route.ReconcileRequest(uid='u'), reconcile_request, _retry=0)
        assert response.status_code == 409
        assert response.body == b'{"status":"retry","reason":"dependency_warming"}'
    else:
        with pytest.raises(ValueError) as raised:
            await route.reconcile(route.ReconcileRequest(uid='u'), reconcile_request, _retry=0)
        assert raised.value is failure
