"""Contract tests for the gateway's OpenAI-shaped /v1/embeddings surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from fastapi.testclient import TestClient
import pytest

from llm_gateway.gateway.accounting import ProviderResponseMetadata, ProviderUsage
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import ProviderFailure, ProviderResponse
from llm_gateway.gateway.schemas import FailureClass, ProviderRef
from llm_gateway.main import app
from llm_gateway.routers import dependencies, embeddings as embeddings_router

OPENAI_EMBEDDINGS_LANE = 'omi:auto:openai-embeddings'
GEMINI_EMBEDDINGS_LANE = 'omi:auto:gemini-embeddings'


@dataclass
class FakeEmbeddingProvider:
    responses: list[ProviderResponse] = field(default_factory=list)
    failures: list[ProviderFailure] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create_embedding(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials,
        timeout_ms: int,
    ) -> ProviderResponse:
        self.calls.append({'request': dict(request), 'provider_ref': provider_ref, 'timeout_ms': timeout_ms})
        if self.failures:
            raise self.failures.pop(0)
        return self.responses.pop(0)


def _ok_usage_response(vectors: list[list[float]], *, prompt_tokens: int = 12) -> ProviderResponse:
    return ProviderResponse(
        response={
            'object': 'list',
            'data': [
                {'object': 'embedding', 'embedding': vector, 'index': index} for index, vector in enumerate(vectors)
            ],
            'model': 'text-embedding-3-large',
            'usage': {'prompt_tokens': prompt_tokens, 'total_tokens': prompt_tokens},
        },
        accounting=ProviderResponseMetadata(
            usage=ProviderUsage(prompt_tokens=prompt_tokens, uncached_input_tokens=prompt_tokens)
        ),
    )


def _install_provider(provider, provider_name: str = 'openai') -> None:
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({provider_name: provider})


def auth_headers() -> dict[str, str]:
    return {'x-omi-service-caller': 'backend', 'authorization': 'Bearer shared-secret'}


def _auth_configured(monkeypatch) -> None:
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')


def test_embeddings_requires_service_auth(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = TestClient(app).post('/v1/embeddings', json={'model': OPENAI_EMBEDDINGS_LANE, 'input': 'x'})

    assert response.status_code == 401


def test_embeddings_success_returns_openai_shape_and_records_accounting(monkeypatch):
    _auth_configured(monkeypatch)
    provider = FakeEmbeddingProvider(responses=[_ok_usage_response([[0.1, 0.2], [0.3, 0.4]])])
    recorded: list[dict] = []
    _install_provider(provider)
    try:
        with TestClient(app) as client:
            original = embeddings_router.schedule_attempt_trace
            embeddings_router.schedule_attempt_trace = lambda context, trace: recorded.append(
                {'context': context, 'trace': trace}
            )
            try:
                response = client.post(
                    '/v1/embeddings',
                    json={'model': OPENAI_EMBEDDINGS_LANE, 'input': ['alpha', 'beta']},
                    headers=auth_headers(),
                )
            finally:
                embeddings_router.schedule_attempt_trace = original
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body['object'] == 'list'
    assert [item['index'] for item in body['data']] == [0, 1]
    assert body['data'][1]['embedding'] == [0.3, 0.4]
    # The provider saw the lane's configured model, not the lane id.
    assert provider.calls[0]['request']['model'] == 'text-embedding-3-large'
    assert provider.calls[0]['request']['input'] == ['alpha', 'beta']
    # Accounting helper invoked: one attempt trace with the provider usage.
    assert len(recorded) == 1
    assert recorded[0]['context'].api_surface == 'openai_embeddings'
    attempts = recorded[0]['trace'].attempts
    assert len(attempts) == 1
    assert attempts[0].usage is not None and attempts[0].usage.prompt_tokens == 12


def test_embeddings_gemini_lane_forwards_task_type_and_title(monkeypatch):
    _auth_configured(monkeypatch)
    provider = FakeEmbeddingProvider(responses=[_ok_usage_response([[0.5]])])
    _install_provider(provider, provider_name='gemini')
    try:
        response = TestClient(app).post(
            '/v1/embeddings',
            json={
                'model': GEMINI_EMBEDDINGS_LANE,
                'input': 'screen activity query',
                'task_type': 'RETRIEVAL_QUERY',
                'title': 'session',
            },
            headers=auth_headers(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    request = provider.calls[0]['request']
    assert request['model'] == 'gemini-embedding-001'
    assert request['task_type'] == 'RETRIEVAL_QUERY'
    assert request['title'] == 'session'


def test_embeddings_rejects_unknown_parameters(monkeypatch):
    _auth_configured(monkeypatch)
    response = TestClient(app).post(
        '/v1/embeddings',
        json={'model': OPENAI_EMBEDDINGS_LANE, 'input': 'x', 'encoding_format': 'float'},
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()['error']['param'] == 'encoding_format'


def test_embeddings_rejects_chat_lane_ids(monkeypatch):
    _auth_configured(monkeypatch)
    response = TestClient(app).post(
        '/v1/embeddings',
        json={'model': 'omi:auto:chat-agent', 'input': 'x'},
        headers=auth_headers(),
    )

    assert response.status_code in {400, 404}


def test_embeddings_provider_failure_maps_to_gateway_error(monkeypatch):
    _auth_configured(monkeypatch)
    provider = FakeEmbeddingProvider(
        failures=[ProviderFailure(FailureClass.PROVIDER_429_OMI_PAID)],
    )
    _install_provider(provider)
    try:
        response = TestClient(app).post(
            '/v1/embeddings',
            json={'model': OPENAI_EMBEDDINGS_LANE, 'input': 'x'},
            headers=auth_headers(),
        )
    finally:
        app.dependency_overrides.clear()

    # Omi-paid provider throttling maps through the gateway's provider-failure
    # contract (502), exactly like the chat-completions surface; only BYOK
    # throttle classes surface as 429.
    assert response.status_code == 502
    assert response.json()['error']['code'] == 'provider_failure'
