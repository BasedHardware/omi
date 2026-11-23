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

from unittest.mock import AsyncMock  # noqa: E402

import httpx  # noqa: E402
import openai  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from routers import conversations_v3_tasks as route  # noqa: E402
from utils.conversations.v3 import backfill, service  # noqa: E402
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


# ---------------------------------------------------------------------------
# The Cloud Tasks builder routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_route_answers_provider_5xx_as_retryable(monkeypatch):
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=provider_502()))

    with pytest.raises(HTTPException) as raised:
        await route.reconcile(route.ReconcileRequest(uid='u'), _retry=0)

    assert_retryable(raised.value)


@pytest.mark.asyncio
async def test_reconcile_route_keeps_a_non_provider_failure_loud(monkeypatch):
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=ValueError('bug')))

    with pytest.raises(ValueError):
        await route.reconcile(route.ReconcileRequest(uid='u'), _retry=0)


@pytest.mark.asyncio
async def test_reconcile_route_kill_switch_restores_the_original_failure(monkeypatch):
    monkeypatch.setenv(RETRYABLE_PROVIDER_FAILURE_SWITCH, 'off')
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=provider_502()))

    with pytest.raises(openai.InternalServerError):
        await route.reconcile(route.ReconcileRequest(uid='u'), _retry=0)


@pytest.mark.asyncio
async def test_backfill_route_answers_provider_5xx_as_retryable(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_BACKFILL', 'on')
    monkeypatch.setattr(backfill, 'run_step', AsyncMock(side_effect=provider_502()))
    body = route.BackfillRequest(uid='u', run_id='run-1', partition=0)

    with pytest.raises(HTTPException) as raised:
        await route.run_backfill(body, _retry=0)

    assert_retryable(raised.value)
