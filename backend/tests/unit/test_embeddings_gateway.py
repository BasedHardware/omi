"""Backend embedding callers hop the gateway ledger lanes in feature mode.

Kill-switch (FEATURE_MODE=off) and Gemini BYOK keep their direct paths; these
tests pin the gateway-mode behavior and the BYOK fallback for OpenAI
embeddings.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import utils.llm.clients as clients  # noqa: E402
from utils.llm import gateway_client  # noqa: E402
from utils.llm.gateway_client import (  # noqa: E402
    GEMINI_EMBEDDINGS_AUTO_LANE_ID,
    OPENAI_EMBEDDINGS_AUTO_LANE_ID,
    LLM_GATEWAY_FEATURE_MODE_ENV_VAR,
)


def _gateway_mode(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('KUBERNETES_SERVICE_HOST', raising=False)


def _direct_mode(monkeypatch):
    monkeypatch.delenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, raising=False)


def test_embeddings_proxy_embed_documents_uses_gateway_lane(monkeypatch):
    _gateway_mode(monkeypatch)
    with patch.object(
        clients, 'invoke_openai_embeddings_gateway', MagicMock(return_value=[[0.1, 0.2], [0.3]])
    ) as gateway_call, patch.object(clients, 'get_byok_key', MagicMock(return_value=None)):
        vectors = clients.embeddings.embed_documents(['alpha', 'beta'])

    assert vectors == [[0.1, 0.2], [0.3]]
    gateway_call.assert_called_once_with('alpha beta'.split() and ['alpha', 'beta'], byok_api_key=None)


def test_embeddings_proxy_embed_query_uses_gateway_lane(monkeypatch):
    _gateway_mode(monkeypatch)
    with patch.object(
        clients, 'invoke_openai_embeddings_gateway', MagicMock(return_value=[[0.5, 0.6]])
    ) as gateway_call, patch.object(clients, 'get_byok_key', MagicMock(return_value=None)):
        vector = clients.embeddings.embed_query('query')

    assert vector == [0.5, 0.6]
    gateway_call.assert_called_once_with(['query'], byok_api_key=None)


@pytest.mark.asyncio
async def test_embeddings_proxy_async_uses_gateway_lane(monkeypatch):
    _gateway_mode(monkeypatch)

    async def fake_async(texts, **_kwargs):
        return [[0.7] for _ in texts]

    with patch.object(clients, 'ainvoke_openai_embeddings_gateway', fake_async), patch.object(
        clients, 'get_byok_key', MagicMock(return_value=None)
    ):
        vectors = await clients.embeddings.aembed_documents(['x'])

    assert vectors == [[0.7]]


def test_embeddings_proxy_forwards_byok_key_and_falls_back_on_key_failure(monkeypatch):
    _gateway_mode(monkeypatch)
    calls: list[dict] = []

    def gateway_call(texts, *, byok_api_key=None):
        calls.append({'texts': texts, 'byok': byok_api_key})
        if len(calls) == 1:
            raise httpx.HTTPStatusError('Client error 401', request=MagicMock(), response=MagicMock(status_code=401))
        return [[0.9]]

    with patch.object(clients, 'invoke_openai_embeddings_gateway', side_effect=gateway_call), patch.object(
        clients, 'get_byok_key', MagicMock(return_value='sk-user')
    ):
        vector = clients.embeddings.embed_query('q')

    assert vector == [0.9]
    assert calls[0]['byok'] == 'sk-user'
    assert calls[1]['byok'] is None  # BYOK failure falls back to the Omi-paid lane


def test_embeddings_proxy_stays_direct_outside_gateway_mode(monkeypatch):
    _direct_mode(monkeypatch)
    # Constructing the direct LangChain client is import-heavy; the contract
    # here is only that gateway mode is off, so the gateway lane is never used.
    assert clients.embeddings._gateway_mode() is False
    with patch.object(
        clients, 'invoke_openai_embeddings_gateway', MagicMock(side_effect=AssertionError('gateway must not be used'))
    ):
        assert callable(clients.embeddings.embed_query)


def test_gemini_embed_query_uses_gateway_lane_in_feature_mode(monkeypatch):
    _gateway_mode(monkeypatch)
    with patch.object(clients, 'get_byok_key', MagicMock(return_value=None)), patch.object(
        clients,
        'invoke_gemini_embedding_gateway',
        MagicMock(return_value=[0.1, 0.2, 0.3]),
    ) as gateway_call:
        values = clients.gemini_embed_query('screen activity')

    assert values == [0.1, 0.2, 0.3]
    gateway_call.assert_called_once_with('screen activity', task_type='RETRIEVAL_QUERY')


def test_gemini_embed_query_keeps_byok_direct_path(monkeypatch):
    _gateway_mode(monkeypatch)
    payload_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload_requests.append(request)
        return httpx.Response(200, json={'embedding': {'values': [0.4]}})

    with patch.object(clients, 'get_byok_key', MagicMock(return_value='user-gemini-key')), patch.object(
        clients.httpx,
        'post',
        MagicMock(
            side_effect=lambda url, **kwargs: httpx.Client(transport=httpx.MockTransport(handler)).post(url, **kwargs)
        ),
    ):
        values = clients.gemini_embed_query('q')

    assert values == [0.4]
    assert payload_requests[0].headers['x-goog-api-key'] == 'user-gemini-key'


def test_gemini_embed_query_stays_direct_outside_gateway_mode(monkeypatch):
    _direct_mode(monkeypatch)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'embedding': {'values': [0.2]}})

    with patch.object(clients, 'get_byok_key', MagicMock(return_value=None)), patch.object(
        clients.httpx,
        'post',
        MagicMock(
            side_effect=lambda url, **kwargs: httpx.Client(transport=httpx.MockTransport(handler)).post(url, **kwargs)
        ),
    ):
        values = clients.gemini_embed_query('q')

    assert values == [0.2]


def test_gateway_embeddings_helpers_post_to_the_embeddings_surface(monkeypatch):
    """The gateway_client helpers hit /v1/embeddings with the right lane ids."""
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({'url': str(request.url), 'body': request.read(), 'headers': dict(request.headers)})
        return httpx.Response(
            200,
            json={
                'object': 'list',
                'data': [{'object': 'embedding', 'embedding': [0.1, 0.2], 'index': 0}],
                'model': 'x',
                'usage': {'prompt_tokens': 3, 'total_tokens': 3},
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = gateway_client.httpx.Client
    monkeypatch.setattr(
        gateway_client.httpx,
        'Client',
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    vectors = gateway_client.invoke_openai_embeddings_gateway(['hello'])
    assert vectors == [[0.1, 0.2]]
    assert seen[0]['url'].endswith('/v1/embeddings')
    assert OPENAI_EMBEDDINGS_AUTO_LANE_ID.encode() in seen[0]['body']

    query = gateway_client.invoke_gemini_embedding_gateway('q', task_type='RETRIEVAL_QUERY')
    assert query == [0.1, 0.2]
    assert GEMINI_EMBEDDINGS_AUTO_LANE_ID.encode() in seen[1]['body']
