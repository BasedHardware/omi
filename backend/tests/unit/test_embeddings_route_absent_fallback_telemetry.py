"""Regression test: an embeddings deploy-skew degrade must be countable.

Production evidence (2026-08-30/31, Loop S sensor + GCP logs): the prod LLM
gateway (deployed 2026-08-20) predates the ``/v1/embeddings`` route
(2026-08-28, #12337), so every embeddings call 404s and the proxy degrades to
the direct path (#12444). That degrade branch changes provider and loses the
gateway ledger row, but it never called ``record_fallback`` — violating the
repo-wide contract in ``docs/agents/fallback-telemetry.md`` and
``backend/AGENTS.md`` rule 10 ("a branch that changes mode MUST call
``record_fallback``; do not invent per-domain counters"). The sibling
gateway-lane degrade in file chat (#12449,
``_record_gateway_file_chat_fallback``) already records; this file pins the
same contract for the embeddings surface.

The distinction under test is deliberately two-sided:

1. Every route-absent degrade — all four OpenAI embedding methods plus
   ``gemini_embed_query`` — increments ``omi_fallback_total`` with the
   surface's lane labels, so operators can see how much embeddings traffic
   and ledger spend is bypassing the gateway while the skew lasts.
2. The narrative ERROR log stays once per process (the skew holds until the
   gateway is redeployed; the gateway's own access log counts the 404s), and
   a gateway that *owns* the route (typed ``model_not_found``) still raises
   without any fallback telemetry, so lane misconfiguration is never masked
   as deploy skew.

Failure-Class: FC-ship-before-required-route — the violated contract is the
same one #12444 declared (client route shipped before the serving gateway),
but this instance is the observability half: a mode-changing degrade that
leaves no shared-telemetry trail. Instance fix within the existing class,
guard surface = these behavioral tests on the real proxy seam.
"""

from __future__ import annotations

import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault('OPENAI_API_KEY', '***')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgu4RZv')

import utils.llm.clients as clients  # noqa: E402
from utils.llm.gateway_client import LLM_GATEWAY_FEATURE_MODE_ENV_VAR  # noqa: E402
from utils.observability import fallback as fallback_mod  # noqa: E402


class _FakeCounterChild:
    def __init__(self, parent, labels):
        self.parent = parent
        self.labels = labels

    def inc(self, amount: float = 1.0):
        self.parent.increments.append((self.labels, amount))


class _FakeCounter:
    def __init__(self):
        self.increments: list[tuple[dict[str, str], float]] = []

    def labels(self, **labels):
        return _FakeCounterChild(self, labels)


def _gateway_mode(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('KUBERNETES_SERVICE_HOST', raising=False)


def _route_absent_error() -> httpx.HTTPStatusError:
    """A 404 shaped like Starlette's answer for a path the app never registered."""
    request = httpx.Request('POST', 'http://gateway/v1/embeddings')
    response = httpx.Response(404, json={'detail': 'Not Found'}, request=request)
    return httpx.HTTPStatusError('Client error 404', request=request, response=response)


def _model_not_found_error() -> httpx.HTTPStatusError:
    """A 404 the gateway itself emits: it owns the route, it rejected the lane."""
    request = httpx.Request('POST', 'http://gateway/v1/embeddings')
    response = httpx.Response(
        404,
        json={'error': {'message': 'unknown model', 'type': 'api_error', 'code': 'model_not_found'}},
        request=request,
    )
    return httpx.HTTPStatusError('Client error 404', request=request, response=response)


@pytest.fixture
def fallback_counter(monkeypatch):
    counter = _FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)
    return counter


@pytest.fixture(autouse=True)
def _reset_route_absent_warning(monkeypatch):
    monkeypatch.setattr(clients, '_gateway_embeddings_route_absent_warned', False, raising=False)


def test_embed_query_degrade_records_fallback_telemetry(monkeypatch, fallback_counter):
    _gateway_mode(monkeypatch)
    direct = MagicMock()
    direct.embed_query.return_value = [0.7, 0.8]

    with patch.object(
        clients, 'invoke_openai_embeddings_gateway', MagicMock(side_effect=_route_absent_error())
    ), patch.object(clients, 'get_byok_key', MagicMock(return_value=None)), patch.object(
        clients._OpenAIEmbeddingsProxy, '_resolve', MagicMock(return_value=direct)
    ):
        vector = clients.embeddings.embed_query('q')

    assert vector == [0.7, 0.8]
    assert fallback_counter.increments == [
        (
            {
                'component': 'llm_gateway',
                'from_mode': 'gateway_embeddings',
                'to_mode': 'direct_embeddings',
                'reason': 'capability_mismatch',
                'outcome': 'degraded',
            },
            1.0,
        )
    ]


def test_embed_documents_degrade_records_fallback_telemetry(monkeypatch, fallback_counter):
    _gateway_mode(monkeypatch)
    direct = MagicMock()
    direct.embed_documents.return_value = [[0.1], [0.2]]

    with patch.object(
        clients, 'invoke_openai_embeddings_gateway', MagicMock(side_effect=_route_absent_error())
    ), patch.object(clients, 'get_byok_key', MagicMock(return_value=None)), patch.object(
        clients._OpenAIEmbeddingsProxy, '_resolve', MagicMock(return_value=direct)
    ):
        vectors = clients.embeddings.embed_documents(['a', 'b'])

    assert vectors == [[0.1], [0.2]]
    assert fallback_counter.increments[0][0]['from_mode'] == 'gateway_embeddings'
    assert fallback_counter.increments[0][0]['to_mode'] == 'direct_embeddings'
    assert fallback_counter.increments[0][0]['outcome'] == 'degraded'


@pytest.mark.asyncio
async def test_aembed_query_degrade_records_fallback_telemetry(monkeypatch, fallback_counter):
    _gateway_mode(monkeypatch)
    direct = MagicMock()
    direct.aembed_query = AsyncMock(return_value=[0.3, 0.4])

    with patch.object(
        clients, 'ainvoke_openai_embeddings_gateway', AsyncMock(side_effect=_route_absent_error())
    ), patch.object(clients, 'get_byok_key', MagicMock(return_value=None)), patch.object(
        clients._OpenAIEmbeddingsProxy, '_resolve', MagicMock(return_value=direct)
    ):
        vector = await clients.embeddings.aembed_query('q')

    assert vector == [0.3, 0.4]
    assert fallback_counter.increments[0][0]['component'] == 'llm_gateway'
    assert fallback_counter.increments[0][0]['reason'] == 'capability_mismatch'


def test_every_degrade_counts_even_after_the_process_log_fired(monkeypatch, fallback_counter, caplog):
    """The metric must count every degrade; only the narrative log is once-per-process.

    In prod the skew holds for hours and the proxy degrades thousands of times
    an hour. A once-per-process counter would hide that volume — the exact
    blind spot ``omi_fallback_total`` exists to surface.
    """
    _gateway_mode(monkeypatch)
    direct = MagicMock()
    direct.embed_query.return_value = [0.1]

    def gateway_refuses(texts, **_kwargs):
        raise _route_absent_error()

    with patch.object(
        clients, 'invoke_openai_embeddings_gateway', MagicMock(side_effect=gateway_refuses)
    ), patch.object(clients, 'get_byok_key', MagicMock(return_value=None)), patch.object(
        clients._OpenAIEmbeddingsProxy, '_resolve', MagicMock(return_value=direct)
    ):
        with caplog.at_level(logging.ERROR, logger=clients.logger.name):
            for _ in range(3):
                assert clients.embeddings.embed_query('q') == [0.1]

    error_logs = [r for r in caplog.records if 'serves no /v1/embeddings route' in r.message]
    assert len(error_logs) == 1, 'narrative log stays once per process'
    assert len(fallback_counter.increments) == 3, 'metric fires per degrade'


def test_gemini_embed_query_degrade_records_fallback_telemetry(monkeypatch, fallback_counter):
    _gateway_mode(monkeypatch)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'embedding': {'values': [0.6]}})

    with patch.object(clients, 'get_byok_key', MagicMock(return_value=None)), patch.object(
        clients, 'invoke_gemini_embedding_gateway', MagicMock(side_effect=_route_absent_error())
    ), patch.object(
        clients.httpx,
        'post',
        MagicMock(
            side_effect=lambda url, **kwargs: httpx.Client(transport=httpx.MockTransport(handler)).post(url, **kwargs)
        ),
    ):
        values = clients.gemini_embed_query('screen activity')

    assert values == [0.6]
    assert fallback_counter.increments[0][0]['from_mode'] == 'gateway_embeddings'
    assert fallback_counter.increments[0][0]['to_mode'] == 'direct_embeddings'


def test_gateway_owned_rejection_records_no_fallback(monkeypatch, fallback_counter):
    """A typed model_not_found must raise without telemetry: masking lane drift as a
    counted degrade would corrupt the deploy-skew signal these labels carry."""
    _gateway_mode(monkeypatch)

    with patch.object(
        clients, 'invoke_openai_embeddings_gateway', MagicMock(side_effect=_model_not_found_error())
    ), patch.object(clients, 'get_byok_key', MagicMock(return_value=None)):
        with pytest.raises(httpx.HTTPStatusError):
            clients.embeddings.embed_query('q')

    assert fallback_counter.increments == []


def test_healthy_gateway_path_records_no_fallback(monkeypatch, fallback_counter):
    """The ledger lane staying up is the happy path — no mode change, no telemetry."""
    _gateway_mode(monkeypatch)

    with patch.object(clients, 'invoke_openai_embeddings_gateway', MagicMock(return_value=[[0.5, 0.6]])), patch.object(
        clients, 'get_byok_key', MagicMock(return_value=None)
    ):
        vector = clients.embeddings.embed_query('query')

    assert vector == [0.5, 0.6]
    assert fallback_counter.increments == []


def test_byok_key_failure_keeps_its_existing_fallback_labels(monkeypatch, fallback_counter):
    """The BYOK→Omi-key degrade predates this change; it must keep firing exactly one
    event per failure (not zero, and not the route-absent labels)."""
    _gateway_mode(monkeypatch)
    calls: list[dict] = []

    def gateway_call(texts, *, byok_api_key=None):
        calls.append({'texts': texts, 'byok': byok_api_key})
        if len(calls) == 1:
            raise httpx.HTTPStatusError('Client error 401', request=MagicMock(), response=MagicMock(status_code=401))
        return [[0.9]]

    with patch.object(clients, 'invoke_openai_embeddings_gateway', MagicMock(side_effect=gateway_call)), patch.object(
        clients, 'get_byok_key', MagicMock(return_value='sk-user')
    ):
        vector = clients.embeddings.embed_query('q')

    assert vector == [0.9]
    # No route-absent degrade happened: the gateway owned and answered the call.
    assert all(inc[0]['from_mode'] != 'gateway_embeddings' for inc in fallback_counter.increments)
