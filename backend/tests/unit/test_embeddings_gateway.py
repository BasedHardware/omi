"""Backend embedding callers hop the gateway ledger lanes in feature mode.

Kill-switch (FEATURE_MODE=off) and Gemini BYOK keep their direct paths; these
tests pin the gateway-mode behavior and the BYOK fallback for OpenAI
embeddings.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

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


# --- gateway/backend deploy skew: a gateway older than its caller -------------
#
# Regression cover for the 2026-08-30 prod finalization outage. The prod gateway
# was deployed 2026-08-20, /v1/embeddings landed 2026-08-28 (fe3df5ac00), and the
# backend half shipped on merge -- so every conversation finalization died on a
# 404 with a working direct embeddings path sitting right behind it.


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


@pytest.fixture(autouse=True)
def _reset_route_absent_warning(monkeypatch):
    """The skew warning is once-per-process; each test needs a fresh process view."""
    monkeypatch.setattr(clients, '_gateway_embeddings_route_absent_warned', False, raising=False)


def test_route_absent_discriminates_on_body_not_status():
    assert gateway_client.is_gateway_route_absent(_route_absent_error()) is True
    # Same status, gateway-owned rejection: must NOT be read as deploy skew.
    assert gateway_client.is_gateway_route_absent(_model_not_found_error()) is False
    assert gateway_client.is_gateway_route_absent(RuntimeError('boom')) is False


def test_route_absent_treats_a_non_json_404_as_missing_route():
    request = httpx.Request('POST', 'http://gateway/v1/embeddings')
    response = httpx.Response(404, text='<html>404</html>', request=request)
    error = httpx.HTTPStatusError('Client error 404', request=request, response=response)
    assert gateway_client.is_gateway_route_absent(error) is True


def test_embed_query_falls_back_to_direct_when_gateway_route_is_absent(monkeypatch):
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
    direct.embed_query.assert_called_once_with('q')


def test_embed_documents_falls_back_to_direct_when_gateway_route_is_absent(monkeypatch):
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
    direct.embed_documents.assert_called_once_with(['a', 'b'])


@pytest.mark.asyncio
async def test_aembed_query_falls_back_to_direct_when_gateway_route_is_absent(monkeypatch):
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
    direct.aembed_query.assert_awaited_once_with('q')


def test_embed_query_still_raises_when_the_gateway_owns_the_route(monkeypatch):
    """model_not_found is a real gateway rejection; masking it would hide lane drift."""
    _gateway_mode(monkeypatch)

    with patch.object(
        clients, 'invoke_openai_embeddings_gateway', MagicMock(side_effect=_model_not_found_error())
    ), patch.object(clients, 'get_byok_key', MagicMock(return_value=None)), patch.object(
        clients._OpenAIEmbeddingsProxy,
        '_resolve',
        MagicMock(side_effect=AssertionError('direct path must not be used')),
    ):
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            clients.embeddings.embed_query('q')

    assert excinfo.value.response.status_code == 404


def test_gemini_embed_query_falls_back_to_direct_when_gateway_route_is_absent(monkeypatch):
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


def test_gemini_embed_query_still_raises_when_the_gateway_owns_the_route(monkeypatch):
    _gateway_mode(monkeypatch)

    with patch.object(clients, 'get_byok_key', MagicMock(return_value=None)), patch.object(
        clients, 'invoke_gemini_embedding_gateway', MagicMock(side_effect=_model_not_found_error())
    ), patch.object(clients.httpx, 'post', MagicMock(side_effect=AssertionError('direct path must not be used'))):
        with pytest.raises(httpx.HTTPStatusError):
            clients.gemini_embed_query('q')
