"""Contract tests for the gateway's decision-model surface (/v1/systemone, #14835)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

import httpx
import pytest
from fastapi.testclient import TestClient

from config.jev_decisions import JEV_AUTO_LANE_ID, JEV_GATEWAY_REQUEST_MS, JEV_MODEL
from llm_gateway.gateway.accounting import ProviderResponseMetadata, ProviderUsage
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider, ProviderFailure, ProviderResponse
from llm_gateway.gateway.schemas import FailureClass, ProviderRef, Surface
from llm_gateway.main import app
from llm_gateway.routers import dependencies, systemone as systemone_router

QUESTIONS = {'worth_keeping': {'type': 'noul', 'instructions': 'Keep it?', 'criteria': {'true': 'yes', 'false': 'no'}}}
ANSWER_BODY = {
    'model': 'typesafe/jev-1.13-20260917',
    'answers': {'worth_keeping': {'type': 'noul', 'noul': 0.3}},
    'usage': {'input_tokens': 21, 'output_tokens': 2},
}


@dataclass
class FakeSystemOneProvider:
    failures: list[ProviderFailure] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create_systemone(
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
        return ProviderResponse(
            response=ANSWER_BODY,
            accounting=ProviderResponseMetadata(usage=ProviderUsage(prompt_tokens=21, uncached_input_tokens=21)),
        )


def _post(body: dict[str, Any], provider: FakeSystemOneProvider | None = None):
    if provider is not None:
        app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry(
            {'openrouter': provider}
        )
    try:
        return TestClient(app).post(
            '/v1/systemone',
            json=body,
            headers={'x-omi-service-caller': 'backend', 'authorization': 'Bearer shared-secret'},
        )
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _service_auth(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')


def test_lane_is_pinned_to_one_jev_version_with_one_attempt_and_no_fallback():
    config = load_gateway_config(prod_mode=True)
    lane = config.lanes[JEV_AUTO_LANE_ID]
    route = config.route_artifacts[lane.active_route]

    assert lane.surface == Surface.OPENROUTER_SYSTEMONE
    assert (route.primary.provider, route.primary.model) == ('openrouter', JEV_MODEL)
    assert route.fallbacks == [] and route.retry.max_attempts == 1
    assert route.timeouts.request_ms == JEV_GATEWAY_REQUEST_MS
    assert lane.last_known_good == lane.active_route


def test_requires_service_auth():
    response = TestClient(app).post('/v1/systemone', json={'model': JEV_AUTO_LANE_ID})

    assert response.status_code == 401


def test_success_passes_typed_answers_through_and_records_accounting():
    provider = FakeSystemOneProvider()
    recorded: list[Any] = []
    original = systemone_router.schedule_attempt_trace
    systemone_router.schedule_attempt_trace = lambda context, trace: recorded.append((context, trace))
    try:
        response = _post({'model': JEV_AUTO_LANE_ID, 'state': 'synthetic', 'questions': QUESTIONS}, provider)
    finally:
        systemone_router.schedule_attempt_trace = original

    assert response.status_code == 200
    assert response.json() == ANSWER_BODY
    (call,) = provider.calls
    assert call['provider_ref'].model == JEV_MODEL
    assert call['request'] == {'state': 'synthetic', 'questions': QUESTIONS}
    assert call['timeout_ms'] == JEV_GATEWAY_REQUEST_MS
    ((context, trace),) = recorded
    assert context.api_surface == 'openrouter_systemone'
    assert trace.attempts[0].usage.prompt_tokens == 21


@pytest.mark.parametrize(
    ('body', 'param'),
    [
        ({'model': JEV_AUTO_LANE_ID, 'questions': QUESTIONS}, 'state'),
        ({'model': JEV_AUTO_LANE_ID, 'state': 's', 'questions': {}}, 'questions'),
        ({'model': JEV_AUTO_LANE_ID, 'state': 's', 'questions': QUESTIONS, 'temperature': 0}, 'temperature'),
        (
            {'model': JEV_AUTO_LANE_ID, 'state': 's', 'questions': {'q': {'type': 'boolean', 'instructions': 'x'}}},
            'questions.q.type',
        ),
        (
            {'model': JEV_AUTO_LANE_ID, 'state': 's', 'questions': {'q': {'type': 'choice', 'instructions': 'x'}}},
            'questions.q.criteria',
        ),
        (
            {
                'model': JEV_AUTO_LANE_ID,
                'state': 's',
                'questions': {'q': {'type': 'score', 'instructions': 'x', 'criteria': ['only one']}},
            },
            'questions.q.criteria',
        ),
        ({'model': JEV_AUTO_LANE_ID, 'state': 'x' * 96_001, 'questions': QUESTIONS}, 'state'),
    ],
)
def test_invalid_requests_are_rejected_before_the_provider(body, param):
    provider = FakeSystemOneProvider()

    response = _post(body, provider)

    assert response.status_code == 400
    assert response.json()['error']['param'] == param
    assert provider.calls == []


def test_other_lanes_and_provider_model_names_are_not_routes():
    assert _post({'model': 'omi:auto:chat-agent', 'state': 's', 'questions': QUESTIONS}).status_code in {400, 404}
    assert _post({'model': JEV_MODEL, 'state': 's', 'questions': QUESTIONS}).status_code in {400, 404}


def test_provider_failure_maps_to_the_gateway_provider_failure_contract():
    provider = FakeSystemOneProvider(failures=[ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT)])

    response = _post({'model': JEV_AUTO_LANE_ID, 'state': 's', 'questions': QUESTIONS}, provider)

    assert response.status_code in {502, 504}
    assert len(provider.calls) == 1  # no gateway retry; the caller owns its one retry


def _openrouter_provider(handler) -> OpenAICompatibleChatCompletionProvider:
    return OpenAICompatibleChatCompletionProvider(
        api_key_env='OPENROUTER_API_KEY',
        base_url='https://openrouter.ai/api/v1',
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def _call(provider: OpenAICompatibleChatCompletionProvider) -> ProviderResponse:
    return await provider.create_systemone(
        {'state': 'synthetic', 'questions': QUESTIONS},
        provider_ref=ProviderRef(provider='openrouter', model=JEV_MODEL),
        credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
        timeout_ms=2500,
    )


@pytest.mark.asyncio
async def test_provider_posts_the_pinned_model_to_openrouter_systemone(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-openrouter-key')
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=ANSWER_BODY)

    result = await _call(_openrouter_provider(handler))

    (request,) = seen
    assert str(request.url) == 'https://openrouter.ai/api/v1/systemone'
    assert request.headers['authorization'] == 'Bearer test-openrouter-key'
    assert json.loads(request.content) == {'model': JEV_MODEL, 'state': 'synthetic', 'questions': QUESTIONS}
    assert result.response == ANSWER_BODY
    assert result.accounting.usage.prompt_tokens == 21
    assert result.accounting.usage.output_tokens == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('status', 'body', 'failure_class'),
    [
        (429, {'error': 'rate limited'}, FailureClass.PROVIDER_429_OMI_PAID),
        (503, {'error': 'unavailable'}, FailureClass.PROVIDER_5XX_OMI_PAID),
        (200, {'model': JEV_MODEL, 'answers': {}}, FailureClass.PROVIDER_5XX_OMI_PAID),
    ],
)
async def test_provider_failures_are_classified(monkeypatch, status, body, failure_class):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-openrouter-key')

    with pytest.raises(ProviderFailure) as excinfo:
        await _call(_openrouter_provider(lambda request: httpx.Response(status, json=body)))

    assert excinfo.value.failure_class == failure_class
