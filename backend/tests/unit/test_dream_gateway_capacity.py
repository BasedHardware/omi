"""Exercise reserved-capacity waits and size-safe Luna recovery without provider IO."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from config.dream_agent import Caps, FULL_CONTEXT_WINDOW
from llm_gateway.gateway import executor
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.errors import GatewayError
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion
from llm_gateway.gateway.providers import FakeChatCompletionProvider, ProviderFailure, fake_success_response
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
    assert luna.calls[0].request['max_completion_tokens'] == 16000
    assert gemini.calls[0].timeout_ms == luna.calls[0].timeout_ms == 480000
    assert resolved.active_route.provider_options['reserved_capacity_only'] is True
