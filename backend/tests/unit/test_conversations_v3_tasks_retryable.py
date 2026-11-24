"""A provider 5xx on the v3 outline path must not surface as an unhandled 500.

Live prod signature (ro-prod, 2026-11-19, group ``CIqco6zElomJFg``, 243 events/24h):

    openai.InternalServerError: Error code: 502 - {'error': {'message':
    'provider request failed: provider_5xx_omi_paid', ...}}
    raised from utils/conversations/v3/models.py outline
    through utils/executors.py _tracked to the ASGI handler

The Cloud Tasks builder routes are the request boundary for that call. They now
answer the existing retryable contract (503 + ``Retry-After`` + the typed detail
code) so the queue retries the task; a non-provider failure keeps its loud 500.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import asyncio  # noqa: E402
import logging  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

import httpx  # noqa: E402
import openai  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException, Request  # noqa: E402

from routers import conversations_v3_tasks as route  # noqa: E402
from utils.conversations.processing_metrics import RETRYABLE_PROCESSING_RESPONSES_TOTAL  # noqa: E402
from utils.conversations.v3 import backfill, request_log_trace_id, service  # noqa: E402
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
async def test_reconcile_route_answers_provider_5xx_as_retryable(monkeypatch, reconcile_request):
    async def fail(_uid):
        assert request_log_trace_id() == 'a' * 32
        raise provider_502()

    monkeypatch.setattr(service, 'reconcile', fail)

    with pytest.raises(HTTPException) as raised:
        await route.reconcile(route.ReconcileRequest(uid='u'), reconcile_request, _retry=0)

    assert_retryable(raised.value)
    assert request_log_trace_id() == '-'


@pytest.mark.asyncio
async def test_reconcile_route_keeps_a_non_provider_failure_loud(monkeypatch, reconcile_request):
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=ValueError('bug')))

    with pytest.raises(ValueError):
        await route.reconcile(route.ReconcileRequest(uid='u'), reconcile_request, _retry=0)


@pytest.mark.asyncio
async def test_reconcile_route_kill_switch_restores_the_original_failure(monkeypatch, reconcile_request):
    monkeypatch.setenv(RETRYABLE_PROVIDER_FAILURE_SWITCH, 'off')
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=provider_502()))

    with pytest.raises(openai.InternalServerError):
        await route.reconcile(route.ReconcileRequest(uid='u'), reconcile_request, _retry=0)


@pytest.mark.asyncio
async def test_reconcile_route_re_raises_an_already_typed_answer(monkeypatch, reconcile_request):
    """The composition boundary already recorded its metric; do not remap it."""
    typed = HTTPException(status_code=503, detail=RETRYABLE_CONVERSATION_PROCESSING_ERROR_DETAIL)
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=typed))

    with pytest.raises(HTTPException) as raised:
        await route.reconcile(route.ReconcileRequest(uid='u'), reconcile_request, _retry=0)

    assert raised.value is typed


@pytest.mark.asyncio
async def test_reconcile_route_does_not_override_a_typed_non_retryable_answer(monkeypatch, reconcile_request):
    typed = HTTPException(status_code=500, detail='deliberate')
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=typed))

    with pytest.raises(HTTPException) as raised:
        await route.reconcile(route.ReconcileRequest(uid='u'), reconcile_request, _retry=0)

    assert raised.value is typed


@pytest.mark.asyncio
async def test_backfill_route_answers_provider_5xx_as_retryable(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_BACKFILL', 'on')
    monkeypatch.setattr(backfill, 'run_step', AsyncMock(side_effect=provider_502()))
    body = route.BackfillRequest(uid='u', run_id='run-1', partition=0)

    with pytest.raises(HTTPException) as raised:
        await route.run_backfill(body, _retry=0)

    assert_retryable(raised.value)


@pytest.mark.asyncio
async def test_backfill_route_keeps_owner_busy_as_its_own_503(monkeypatch):
    """BackfillRetry must keep its own answer, not be remapped as a provider fault."""
    monkeypatch.setenv('CONVERSATIONS_V3_BACKFILL', 'on')
    monkeypatch.setattr(backfill, 'run_step', AsyncMock(side_effect=backfill.BackfillRetry('busy')))
    body = route.BackfillRequest(uid='u', run_id='run-1', partition=0)

    with pytest.raises(HTTPException) as raised:
        await route.run_backfill(body, _retry=0)

    assert raised.value.status_code == 503
    assert raised.value.detail == 'Owner busy; retry'


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
