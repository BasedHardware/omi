"""Exercise reserved-capacity waits and size-safe Luna recovery without provider IO."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from config.dream_agent import Caps, FULL_CONTEXT_WINDOW
from config.vertex_reservations import State
from llm_gateway.gateway import executor
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.errors import GatewayError
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion
from llm_gateway.gateway.providers import (
    FakeChatCompletionProvider,
    ProviderFailure,
    VertexGeminiProvider,
    fake_success_response,
)
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.gateway.schemas import FailureClass
from models.dream_agent import Plan
from utils import dream_agent, dream_prompt, dream_transport

UID = 'synthetic-gateway-full-owner'
# Official model limits, verified 2026-10-13:
# https://developers.openai.com/api/docs/models/gpt-6-luna
# The repo's 272000-token cost-card threshold is pricing, not a context maximum.
LUNA_CONTEXT_WINDOW = 1050000


@pytest.fixture
def full_gateway(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_CONTEXT_MODE', 'full')
    monkeypatch.setenv('DREAM_AGENT_FULL_CONTEXT_UIDS', UID)
    monkeypatch.setattr(executor, 'monotonic', lambda: 100.0)
    config = load_gateway_config(prod_mode=True)
    credentials = build_omi_managed_credential_context(ServiceCaller(name='backend'))
    monkeypatch.setattr(dream_transport.dream_capacity, 'available_model', AsyncMock(return_value='synthetic-reserved'))
    monkeypatch.setattr(dream_transport.dream_capacity, 'mark_saturated', AsyncMock())
    monkeypatch.setattr(dream_transport, 'llm_gateway_headers', lambda **k: {})
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_base_url', lambda: 'https://synthetic.invalid')
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))
    return config, credentials


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [FailureClass.RESERVED_CAPACITY_UNAVAILABLE, FailureClass.PROVIDER_429_OMI_PAID])
async def test_full_reservation_exhaustion_is_capacity_wait_without_luna(full_gateway, monkeypatch, failure):
    config, credentials = full_gateway
    gemini = FakeChatCompletionProvider([ProviderFailure(failure)])
    luna = FakeChatCompletionProvider()
    registry = ProviderRegistry({'gemini': gemini, 'openai': luna})

    async def post(url, *, json, **kwargs):
        resolved = resolve_chat_completion_route(config, json)
        try:
            await execute_chat_completion(resolved, credentials, registry)
        except GatewayError as exc:
            return httpx.Response(503, request=httpx.Request('POST', url), json={'error': exc.to_error_dict()})
        pytest.fail('exhausted reserved capacity silently recovered')

    monkeypatch.setattr(dream_transport, 'get_llm_gateway_client', lambda: SimpleNamespace(post=post))
    caps = Caps().for_uid(UID)
    sink = {'tokens': 0}
    with pytest.raises(dream_transport.CapacityWait):
        await dream_agent.plan_pass(UID, {}, caps, usage_sink=sink)
    assert len(gemini.calls) == 1 and gemini.calls[0].timeout_ms == 480000
    assert not luna.calls
    assert sink['tokens'] == 0 and sink['usage_unknown'] is False


@pytest.mark.asyncio
async def test_full_request_rejection_recovery_fits_luna_without_shrinking(full_gateway, monkeypatch):
    config, credentials = full_gateway
    # Exercise a near-hard-bound request, larger than bounded mode can admit.
    records = {'memory_items/synthetic': {'content': 'q' * 1000000}}
    caps = Caps().for_uid(UID)
    assert dream_prompt.fits_full(records, caps)
    messages = dream_prompt.full_mount(caps).messages(dream_prompt.full_evidence_message(records, caps))
    hard_bound = dream_transport.input_ceiling(messages, Plan.model_json_schema()) + caps.completion_tokens
    assert hard_bound <= FULL_CONTEXT_WINDOW < LUNA_CONTEXT_WINDOW
    monkeypatch.setenv('DREAM_AGENT_FULL_CONTEXT_TOKENS', '999999999')
    assert Caps().for_uid(UID).tokens == FULL_CONTEXT_WINDOW < LUNA_CONTEXT_WINDOW
    resolved = resolve_chat_completion_route(
        config,
        {
            'model': dream_transport.MAIN_LANE,
            'messages': messages,
            'max_completion_tokens': caps.completion_tokens,
            'response_format': {
                'type': 'json_schema',
                'json_schema': {'name': 'Plan', 'schema': Plan.model_json_schema()},
            },
        },
    )
    gemini = FakeChatCompletionProvider([ProviderFailure(FailureClass.PROVIDER_INVALID_REQUEST)])
    fallback = resolved.active_route.fallbacks[0]
    assert fallback.provider == 'openai' and fallback.model == 'gpt-6-luna'
    luna = FakeChatCompletionProvider([fake_success_response(fallback, content='{}')])
    result = await execute_chat_completion(resolved, credentials, ProviderRegistry({'gemini': gemini, 'openai': luna}))
    assert result.selected_model == 'gpt-6-luna' and result.fallback_used
    assert len(gemini.calls) == len(luna.calls) == 1
    assert luna.calls[0].request['messages'] == messages
    assert luna.calls[0].request['max_completion_tokens'] == 32768
    assert gemini.calls[0].timeout_ms == luna.calls[0].timeout_ms == 480000
    assert resolved.active_route.provider_options['reserved_capacity_only'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('model', ['gemini-2.5-flash', 'gemini-3.8-flash'])
async def test_full_thinking_reaches_actual_reserved_model_without_changing_bounded(full_gateway, monkeypatch, model):
    config, credentials = full_gateway
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                'modelVersion': model,
                'trafficType': 'PROVISIONED_THROUGHPUT',
                'candidates': [{'content': {'parts': [{'text': '{}'}]}, 'finishReason': 'STOP'}],
                'usageMetadata': {
                    'promptTokenCount': 10,
                    'candidatesTokenCount': 2,
                    'thoughtsTokenCount': 3,
                    'totalTokenCount': 15,
                },
            },
        )

    provider = VertexGeminiProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        access_token_supplier=AsyncMock(return_value='synthetic-token'),
    )

    async def refresh(*args):
        provider._reservation_states = {model: State.ACTIVE}

    monkeypatch.setattr(provider, '_refresh_reservations', refresh)
    monkeypatch.setattr(provider._reservations, 'record', AsyncMock())
    monkeypatch.setattr(provider._reservations, 'note_request', lambda *args: None)
    registry = ProviderRegistry({'gemini': provider})
    try:
        for full in (True, False):
            payload = {
                'model': dream_transport.MAIN_LANE,
                'messages': [{'role': 'user', 'content': 'Synthetic'}],
                'max_completion_tokens': 32768,
            }
            if full:
                payload.update(reasoning_effort='high', google={'thinking_config': {'thinking_budget': 16384}})
            resolved = resolve_chat_completion_route(config, payload)
            await execute_chat_completion(resolved, credentials, registry)
            request = seen[-1]
            assert model + ':generateContent' in str(request.url)
            assert request.headers['X-Vertex-AI-LLM-Request-Type'] == 'dedicated'
            wire = json.loads(request.content)
            expected = (
                ({'thinkingLevel': 'high'} if model == 'gemini-3.8-flash' else {'thinkingBudget': 16384})
                if full
                else ({'thinkingLevel': 'low'} if model == 'gemini-3.8-flash' else {'thinkingBudget': 0})
            )
            assert wire['generationConfig']['thinkingConfig'] == expected
            assert '_dream_thinking_budget' not in wire
            assert resolved.active_route.provider_options['reserved_capacity_only'] is True
        assert len(seen) == 2
        assert provider._thinking_budget_context.get() is None
    finally:
        await provider.aclose()
