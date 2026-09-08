from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
import pytest

from utils.llm import clients, gateway_shadow, gateway_serving, model_config
from utils.llm import providers
from utils.llm.gateway_client import DEFAULT_LLM_GATEWAY_URL, GatewayContextChatOpenAI, get_llm_gateway_base_url
from utils.llm.gateway_client import (
    LLM_CHAT_AGENT_ROUTE_ENV_VAR,
    LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR,
    LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR,
    LLM_GATEWAY_APP_PLATFORM_HEADER,
    LLM_GATEWAY_FEATURE_MODE_ENV_VAR,
    LLM_GATEWAY_URL_ENV_VAR,
    GatewayDirectModelSurfaceBlocked,
    feature_auto_lane_id,
    get_chat_agent_route,
    llm_gateway_headers,
    raise_if_gateway_feature_mode_blocks_direct_model_surface,
    should_route_chat_agent_through_gateway,
    should_route_features_through_gateway,
)
from utils.llm.clients import get_llm_gateway_chat_structured
from utils.llm.usage_tracker import reset_usage_context, set_usage_context
import httpx


class FakeChatModel(BaseChatModel):
    name: str
    calls: list

    @property
    def _llm_type(self) -> str:
        return f'fake-{self.name}'

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append({'messages': messages, 'kwargs': kwargs})
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=f'{self.name} response'))])

    def with_structured_output(self, schema, *, include_raw: bool = False, **kwargs: Any):
        return FakeStructuredRunnable(self.name, self.calls)


class FakeStructuredRunnable(Runnable):
    def __init__(self, name: str, calls: list):
        self.name = name
        self.calls = calls

    def invoke(self, input: Any, config=None, **kwargs: Any) -> dict[str, str]:
        self.calls.append({'input': input, 'kwargs': kwargs})
        return {'result': self.name}


def test_llm_gateway_base_url_defaults_to_local_service(monkeypatch):
    monkeypatch.delenv('OMI_LLM_GATEWAY_URL', raising=False)

    assert get_llm_gateway_base_url() == DEFAULT_LLM_GATEWAY_URL


def test_llm_gateway_base_url_uses_repo_local_env_config(monkeypatch):
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', ' http://llm-gateway.internal:8080/ ')

    assert get_llm_gateway_base_url() == 'http://llm-gateway.internal:8080'


def test_gateway_langchain_client_uses_internal_gateway_base_url_and_auth(monkeypatch):
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://gateway.internal:8080/')
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'service-token')
    original_cache = dict(providers._llm_cache)
    providers._llm_cache.clear()

    try:
        result = get_llm_gateway_chat_structured()

        assert isinstance(result, GatewayContextChatOpenAI)
        assert result.model_name == 'omi:auto:chat-structured'
        assert str(result.openai_api_base) == 'http://gateway.internal:8080/v1'
        assert result.request_timeout == 35.0
        assert result.default_headers['X-Omi-Service-Caller'] == 'backend'
        assert result.default_headers['Authorization'] == 'Bearer service-token'
    finally:
        providers._llm_cache.clear()
        providers._llm_cache.update(original_cache)


def test_gateway_langchain_client_injects_request_scoped_usage_attribution() -> None:
    model = GatewayContextChatOpenAI(
        model='omi:auto:chat-structured',
        api_key='gateway-test',
        base_url='http://gateway.internal:8080/v1',
        omi_gateway_feature='fallback_feature',
    )
    token = set_usage_context('user-123', 'conversation_processing')
    try:
        payload = model._get_request_payload([HumanMessage(content='hello')])
    finally:
        reset_usage_context(token)

    assert payload['extra_headers']['X-Omi-User-Uid'] == 'user-123'
    assert payload['extra_headers']['X-Omi-LLM-Feature'] == 'conversation_processing'
    assert payload['metadata']['omi_feature'] == 'conversation_processing'


def test_get_llm_dev_shadow_wraps_legacy_and_submits_gateway(monkeypatch):
    submitted = []
    captured_gateway_options = {}
    legacy = FakeChatModel(name='legacy', calls=[])
    gateway = FakeChatModel(name='gateway', calls=[])

    def immediate_submit(_executor, fn, *args, **kwargs):
        submitted.append(fn.__name__)
        fn(*args, **kwargs)

    monkeypatch.setenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, 'true')
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.setattr(clients, 'get_default_client', lambda *args, **kwargs: legacy)

    def fake_gateway(*args, **kwargs):
        captured_gateway_options.update(kwargs.get('options') or {})
        return gateway

    monkeypatch.setattr(gateway_shadow, 'get_or_create_omi_gateway_llm', fake_gateway)
    monkeypatch.setattr(gateway_shadow, 'submit_with_context', immediate_submit)

    result = clients.get_llm('conv_discard').invoke('hello')

    assert result.content == 'legacy response'
    assert len(legacy.calls) == 1
    assert len(gateway.calls) == 1
    assert captured_gateway_options['request_timeout'] == 35.0
    assert submitted == ['_run_sync_shadow']


def test_get_llm_dev_shadow_wraps_structured_output(monkeypatch):
    submitted = []
    legacy = FakeChatModel(name='legacy', calls=[])
    gateway = FakeChatModel(name='gateway', calls=[])

    def immediate_submit(_executor, fn, *args, **kwargs):
        submitted.append(fn.__name__)
        fn(*args, **kwargs)

    monkeypatch.setenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, 'true')
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.setattr(clients, 'get_default_client', lambda *args, **kwargs: legacy)
    monkeypatch.setattr(gateway_shadow, 'get_or_create_omi_gateway_llm', lambda *args, **kwargs: gateway)
    monkeypatch.setattr(gateway_shadow, 'submit_with_context', immediate_submit)

    result = clients.get_llm('chat_extraction').with_structured_output(dict).invoke('hello')

    assert result == {'result': 'legacy'}
    assert legacy.calls == [{'input': 'hello', 'kwargs': {}}]
    assert gateway.calls == [{'input': 'hello', 'kwargs': {}}]
    assert submitted == ['_run_sync_shadow']


def test_get_llm_dev_shadow_is_disabled_for_prod_like_runtime(monkeypatch):
    legacy = FakeChatModel(name='legacy', calls=[])

    monkeypatch.setenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, 'true')
    monkeypatch.setenv('K_SERVICE', 'prod-omi-backend')
    monkeypatch.setattr(clients, 'get_default_client', lambda *args, **kwargs: legacy)

    result = clients.get_llm('conv_discard')

    assert result is legacy


def test_get_llm_feature_gateway_mode_uses_generated_auto_lane(monkeypatch):
    captured = {}
    gateway = FakeChatModel(name='gateway', calls=[])
    legacy = FakeChatModel(name='legacy', calls=[])

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured['lane_id'] = lane_id
        captured['streaming'] = streaming
        captured['feature'] = feature
        return gateway

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, raising=False)
    monkeypatch.setattr(clients, 'get_or_create_omi_gateway_llm', fake_gateway)
    monkeypatch.setattr(clients, 'get_default_client', lambda *args, **kwargs: legacy)

    result = clients.get_llm('conv_discard', streaming=True).invoke('hello')

    assert result.content == 'gateway response'
    assert captured == {'lane_id': feature_auto_lane_id('conv_discard'), 'streaming': True, 'feature': 'conv_discard'}
    assert len(gateway.calls) == 1
    assert legacy.calls == []


def test_memory_l2_gateway_mode_uses_luna_auto_lane_without_direct_fallback(monkeypatch):
    captured = {}
    gateway = FakeChatModel(name='gateway', calls=[])
    legacy = FakeChatModel(name='legacy', calls=[])

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured['lane_id'] = lane_id
        captured['streaming'] = streaming
        captured['feature'] = feature
        return gateway

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, raising=False)
    monkeypatch.setattr(clients, 'get_or_create_omi_gateway_llm', fake_gateway)
    monkeypatch.setattr(clients, 'get_default_client', lambda *args, **kwargs: legacy)

    result = clients.get_llm('memory_l2').invoke('promote this memory')

    assert result.content == 'gateway response'
    assert captured == {'lane_id': 'omi:auto:memory-l2', 'streaming': False, 'feature': 'memory_l2'}
    assert len(gateway.calls) == 1
    assert legacy.calls == []


def test_get_llm_forwards_an_explicit_gateway_transport_timeout(monkeypatch):
    captured = {}

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(lane_id=lane_id, streaming=streaming, options=options, feature=feature)
        return FakeChatModel(name="gateway", calls=[])

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, "gateway")
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.delenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, raising=False)
    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm", fake_gateway)

    clients.get_llm("memory_l2", request_timeout=20.0)

    assert captured == {
        "lane_id": "omi:auto:memory-l2",
        "streaming": False,
        "options": {"request_timeout": 20.0},
        "feature": "memory_l2",
    }


def test_get_llm_gives_a_user_waiting_feature_the_foreground_deadline(monkeypatch):
    """Without this the lane keeps the 15s background first-byte deadline and the user loses the
    summary: prod 2026-08-19 (conv_structure, daily_summary) and 2026-09-04 (conv_app_result, 31%
    of app-selected reprocesses). The deadline belongs to the feature, not to the call site."""
    captured = {}

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(lane_id=lane_id, options=options, feature=feature)
        return FakeChatModel(name="gateway", calls=[])

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, "gateway")
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.delenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, raising=False)
    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm", fake_gateway)

    clients.get_llm("conv_app_result")

    assert captured["lane_id"] == "omi:auto:conv-app-result"
    assert captured["options"] == {"request_timeout": model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS}


def test_get_llm_leaves_a_background_feature_on_the_gateway_transport_deadline(monkeypatch):
    """The bounded transport deadline stays the default for everything else."""
    captured = {}

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured.update(lane_id=lane_id, options=options, feature=feature)
        return FakeChatModel(name="gateway", calls=[])

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, "gateway")
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.delenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, raising=False)
    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm", fake_gateway)

    clients.get_llm("conv_folder")

    assert captured["options"] is None


def test_get_llm_gives_a_byok_user_the_same_feature_deadline(monkeypatch):
    """A BYOK request runs the same prompt on the same lane, so it gets the same deadline."""
    captured = {}

    def fake_byok_gateway(lane_id, *, provider, api_key, streaming=False, options=None, feature=None):
        captured.update(lane_id=lane_id, provider=provider, options=options, feature=feature)
        return FakeChatModel(name="gateway-byok", calls=[])

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, "gateway")
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.delenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, raising=False)
    monkeypatch.setattr(clients, "get_or_create_omi_gateway_llm_for_byok", fake_byok_gateway)
    monkeypatch.setattr(clients, "get_byok_profile", lambda: None)
    monkeypatch.setattr(clients, "get_byok_key", lambda provider: "sk-user-key" if provider == "openai" else None)

    clients.get_llm("conv_app_result")

    assert captured["lane_id"] == "omi:auto:conv-app-result"
    assert captured["options"] == {"request_timeout": model_config.FOREGROUND_REQUEST_TIMEOUT_SECONDS}


def test_get_llm_feature_gateway_mode_fails_closed_on_transport_failure(monkeypatch):
    legacy = FakeChatModel(name='legacy', calls=[])

    class FailingGateway(FakeChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            raise httpx.ConnectError('connection refused')

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, raising=False)
    monkeypatch.setattr(
        clients, 'get_or_create_omi_gateway_llm', lambda *args, **kwargs: FailingGateway(name='gateway', calls=[])
    )
    monkeypatch.setattr(clients, 'get_default_client', lambda *args, **kwargs: legacy)
    with pytest.raises(httpx.ConnectError):
        clients.get_llm('conv_discard').invoke('hello')

    assert legacy.calls == []


def test_gateway_serving_does_not_fallback_on_gateway_configuration_503():

    request = httpx.Request('POST', 'http://gateway/v1/chat/completions')
    response = httpx.Response(503, request=request)
    error = httpx.HTTPStatusError('gateway route configuration failed', request=request, response=response)

    assert gateway_serving.is_gateway_transport_failure(error) is False


def test_get_llm_feature_gateway_mode_routes_byok_through_gateway_only(monkeypatch):
    captured: dict[str, object] = {}
    legacy = FakeChatModel(name='byok', calls=[])

    def fake_gateway(lane_id, *, provider, api_key, **_kwargs):
        captured['lane_id'] = lane_id
        captured['provider'] = provider
        captured['api_key'] = api_key
        return FakeChatModel(name='gateway-byok', calls=[])

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, raising=False)
    monkeypatch.setattr(clients, 'get_byok_key', lambda provider: 'sk-test-byok' if provider == 'openai' else None)
    monkeypatch.setattr(clients, 'get_or_create_omi_gateway_llm_for_byok', fake_gateway)
    monkeypatch.setattr(clients, '_create_byok_client', lambda *args, **kwargs: legacy)

    result = clients.get_llm('conv_discard').invoke('hello')

    assert result.content == 'gateway-byok response'
    assert captured == {
        'lane_id': feature_auto_lane_id('conv_discard'),
        'provider': 'openai',
        'api_key': 'sk-test-byok',
    }
    assert legacy.calls == []


def test_get_llm_feature_gateway_mode_bypasses_lane_for_provider_switch(monkeypatch):
    """Provider-switched BYOK must bypass the feature's fixed gateway lane.

    The gateway lane for a feature is pinned to the feature's default provider
    (e.g. conv_discard → openai). When the user's BYOK enrollment selects a
    different provider (e.g. OpenRouter-only), forwarding that key to the fixed
    lane makes the gateway reject the request with missing_byok_key. Route such
    requests through the direct BYOK client instead.
    """
    legacy = FakeChatModel(name='byok-direct', calls=[])

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, raising=False)
    monkeypatch.setattr(
        clients,
        'get_byok_key',
        lambda provider: 'sk-test-openrouter' if provider == 'openrouter' else None,
    )

    def fail_gateway(*_args, **_kwargs):
        raise AssertionError('gateway lane must be bypassed for a provider-switched BYOK call')

    monkeypatch.setattr(clients, 'get_or_create_omi_gateway_llm_for_byok', fail_gateway)
    monkeypatch.setattr(clients, '_create_byok_client', lambda *args, **kwargs: legacy)

    result = clients.get_llm('conv_discard').invoke('hello')

    assert result.content == 'byok-direct response'


def test_get_llm_uses_feature_profile_when_multiple_byok_keys_are_present(monkeypatch):
    legacy = FakeChatModel(name='byok-direct', calls=[])
    captured = {}

    monkeypatch.setattr(
        clients,
        'get_byok_key',
        lambda provider: {'openrouter': 'sk-test-openrouter', 'openai': 'sk-test-openai'}.get(provider),
    )
    monkeypatch.setattr(clients, 'should_route_features_through_gateway', lambda: False)

    def create_client(*args, **kwargs):
        captured['args'] = args
        captured['kwargs'] = kwargs
        return legacy

    monkeypatch.setattr(clients, '_create_byok_client', create_client)

    clients.get_llm('conv_discard')

    assert legacy.name == 'byok-direct'
    assert captured['args'][:2] == ('gpt-5-nano', 'openai')
    assert captured['args'][2] == 'sk-test-openai'


def test_get_llm_falls_back_to_openrouter_when_profile_key_is_missing(monkeypatch):
    legacy = FakeChatModel(name='byok-direct', calls=[])
    captured = {}

    monkeypatch.setattr(
        clients,
        'get_byok_key',
        lambda provider: 'sk-test-openrouter' if provider == 'openrouter' else None,
    )
    monkeypatch.setattr(clients, 'should_route_features_through_gateway', lambda: False)

    def create_client(*args, **kwargs):
        captured['args'] = args
        captured['kwargs'] = kwargs
        return legacy

    monkeypatch.setattr(clients, '_create_byok_client', create_client)

    clients.get_llm('conv_discard')

    assert legacy.name == 'byok-direct'
    assert captured['args'][:2] == ('gemini-2.5-flash-lite', 'openrouter')
    assert captured['args'][2] == 'sk-test-openrouter'


def test_gateway_feature_mode_is_blocked_in_prod_without_explicit_allow(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('K_SERVICE', 'omi-backend')
    monkeypatch.delenv(LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR, raising=False)

    try:
        should_route_features_through_gateway()
    except RuntimeError as exc:
        assert LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR in str(exc)
    else:
        raise AssertionError('expected prod gateway feature mode to require explicit allow env')


def test_gateway_feature_mode_is_blocked_in_non_dev_cloud_stage_without_explicit_allow(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'staging')
    monkeypatch.delenv(LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR, raising=False)

    try:
        should_route_features_through_gateway()
    except RuntimeError as exc:
        assert LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR in str(exc)
    else:
        raise AssertionError('expected non-dev gateway feature mode to require explicit allow env')


def test_gateway_feature_mode_is_blocked_in_kubernetes_without_explicit_dev_stage(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('KUBERNETES_SERVICE_HOST', '10.0.0.1')
    monkeypatch.delenv(LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR, raising=False)
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    monkeypatch.delenv('ENVIRONMENT', raising=False)
    monkeypatch.delenv('APP_ENV', raising=False)
    monkeypatch.delenv('K_SERVICE', raising=False)

    try:
        should_route_features_through_gateway()
    except RuntimeError as exc:
        assert LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR in str(exc)
    else:
        raise AssertionError('expected unstaged Kubernetes gateway feature mode to require explicit allow env')


def test_gateway_feature_mode_allows_kubernetes_with_explicit_dev_stage(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('KUBERNETES_SERVICE_HOST', '10.0.0.1')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv(LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR, raising=False)

    assert should_route_features_through_gateway() is True


def test_gateway_feature_mode_in_prod_requires_gateway_url(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv(LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR, 'true')
    monkeypatch.setenv('K_SERVICE', 'omi-backend')
    monkeypatch.delenv(LLM_GATEWAY_URL_ENV_VAR, raising=False)

    try:
        should_route_features_through_gateway()
    except RuntimeError as exc:
        assert LLM_GATEWAY_URL_ENV_VAR in str(exc)
    else:
        raise AssertionError('expected prod gateway feature mode to require gateway url')


def test_gateway_feature_mode_blocks_direct_exception_surfaces(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.delenv(LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR, raising=False)
    monkeypatch.delenv('K_SERVICE', raising=False)

    try:
        raise_if_gateway_feature_mode_blocks_direct_model_surface('file_chat.openai_files')
    except GatewayDirectModelSurfaceBlocked as exc:
        assert 'file_chat.openai_files' in str(exc)
        assert exc.error_code == 'file_chat_gateway_blocked'
        assert exc.surface == 'file_chat.openai_files'
    else:
        raise AssertionError('expected direct model surface to be blocked')


def test_gateway_feature_mode_allows_acknowledged_direct_exception(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv(LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR, 'true')
    monkeypatch.delenv('K_SERVICE', raising=False)

    raise_if_gateway_feature_mode_blocks_direct_model_surface('file_chat.openai_files')


@pytest.mark.asyncio
async def test_app_icon_generation_always_uses_gateway(monkeypatch):
    from utils.llm import app_generator

    captured = {}

    def gateway(**kwargs):
        captured.update(kwargs)
        return {'data': [{'b64_json': 'aWNvbg=='}]}

    monkeypatch.setattr(app_generator, 'generate_image_via_gateway', gateway)

    assert await app_generator.generate_app_icon('Name', 'Description', 'other') == b'icon'
    # The images API rejects `response_format` (400 unknown_parameter) and no longer serves
    # dall-e-3 (400 invalid_value), which made every app-icon generation a 500. Ask for a model
    # and size/quality pair the gateway rate card prices, and let it return base64 by default.
    assert captured['model'] == 'gpt-image-1'
    assert captured['quality'] == 'medium'
    assert captured['size'] == '1024x1024'
    assert 'response_format' not in captured


@pytest.mark.asyncio
async def test_perplexity_tool_always_uses_gateway(monkeypatch):
    perplexity_tools = _load_perplexity_tools()

    monkeypatch.setattr(perplexity_tools, '_perplexity_gateway_search', lambda _query: _async_return('gateway-search'))

    assert await perplexity_tools.perplexity_web_search_tool.coroutine('query') == 'gateway-search'


def test_perplexity_gateway_response_preserves_top_level_citations():
    perplexity_tools = _load_perplexity_tools()

    formatted = perplexity_tools._format_perplexity_response(
        {
            'choices': [{'message': {'content': 'answer'}}],
            'citations': [{'title': 'Source title', 'url': 'https://example.com/source'}],
        }
    )

    assert 'answer' in formatted
    assert 'Source title' in formatted
    assert 'https://example.com/source' in formatted


def test_get_llm_chat_agent_uses_generated_auto_lane_in_gateway_mode(monkeypatch):
    captured = {}
    gateway = FakeChatModel(name='gateway', calls=[])
    legacy = FakeChatModel(name='legacy', calls=[])

    def fake_gateway(lane_id, streaming=False, options=None, *, feature=None):
        captured['lane_id'] = lane_id
        captured['streaming'] = streaming
        captured['feature'] = feature
        return gateway

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv(LLM_CHAT_AGENT_ROUTE_ENV_VAR, 'luna')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, raising=False)
    monkeypatch.setattr(clients, 'get_or_create_omi_gateway_llm', fake_gateway)
    monkeypatch.setattr(clients, 'get_default_client', lambda *args, **kwargs: legacy)

    result = clients.get_llm('chat_agent', streaming=True)

    assert result is gateway
    assert captured == {
        'lane_id': feature_auto_lane_id('chat_agent'),
        'streaming': True,
        'feature': 'chat_agent',
    }
    assert captured['lane_id'] == 'omi:auto:chat-agent'
    assert legacy.calls == []


def test_get_llm_chat_agent_kill_switch_stays_on_direct_openai(monkeypatch):
    captured = {}
    gateway = FakeChatModel(name='gateway', calls=[])
    legacy = FakeChatModel(name='legacy', calls=[])

    def fake_gateway(*args, **kwargs):
        captured['used_gateway'] = True
        return gateway

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv(LLM_CHAT_AGENT_ROUTE_ENV_VAR, 'direct')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv(gateway_shadow.DEV_SHADOW_ALL_ENABLED_ENV, raising=False)
    monkeypatch.setattr(clients, 'get_or_create_omi_gateway_llm', fake_gateway)
    monkeypatch.setattr(clients, 'get_default_client', lambda *args, **kwargs: legacy)

    result = clients.get_llm('chat_agent', streaming=True)

    assert result is legacy
    assert captured == {}


def test_chat_agent_route_direct_while_feature_mode_gateway(monkeypatch):
    """Chat can stay direct while other features use the gateway."""
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv(LLM_CHAT_AGENT_ROUTE_ENV_VAR, 'direct')
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('KUBERNETES_SERVICE_HOST', raising=False)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')

    assert should_route_features_through_gateway() is True
    assert get_chat_agent_route() == 'direct'
    assert should_route_chat_agent_through_gateway() is False


def test_chat_agent_route_gateway_requires_feature_mode(monkeypatch):
    monkeypatch.setenv(LLM_CHAT_AGENT_ROUTE_ENV_VAR, 'gateway')
    monkeypatch.delenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, raising=False)
    monkeypatch.delenv('K_SERVICE', raising=False)

    assert get_chat_agent_route() == 'gateway'
    assert should_route_chat_agent_through_gateway() is False


def test_chat_agent_route_gateway_with_feature_mode(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv(LLM_CHAT_AGENT_ROUTE_ENV_VAR, 'luna')  # alias
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('K_SERVICE', raising=False)

    assert get_chat_agent_route() == 'gateway'
    assert should_route_chat_agent_through_gateway() is True


def test_chat_agent_route_invalid_raises(monkeypatch):
    monkeypatch.setenv(LLM_CHAT_AGENT_ROUTE_ENV_VAR, 'not-a-route')
    try:
        get_chat_agent_route()
    except RuntimeError as exc:
        assert LLM_CHAT_AGENT_ROUTE_ENV_VAR in str(exc)
    else:
        raise AssertionError('expected invalid chat agent route to raise')


def _load_perplexity_tools():
    module_path = Path(__file__).parents[2] / 'utils' / 'retrieval' / 'tools' / 'perplexity_tools.py'
    spec = importlib.util.spec_from_file_location('perplexity_tools_under_test', module_path)
    assert spec is not None and spec.loader is not None
    perplexity_tools = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(perplexity_tools)
    return perplexity_tools


async def _async_return(value):
    return value


def test_llm_gateway_headers_sends_app_platform_when_known() -> None:
    headers = llm_gateway_headers(feature='chat_agent', platform=' Desktop ')

    assert headers[LLM_GATEWAY_APP_PLATFORM_HEADER] == 'desktop'
    assert headers['X-Omi-LLM-Feature'] == 'chat_agent'
    for platform in ('mobile', 'web'):
        assert llm_gateway_headers(feature='chat_agent', platform=platform)[LLM_GATEWAY_APP_PLATFORM_HEADER] == platform


def test_llm_gateway_headers_omits_app_platform_when_unknown() -> None:
    """Callers that do not know the platform must not send a guessed value."""
    assert LLM_GATEWAY_APP_PLATFORM_HEADER not in llm_gateway_headers(feature='chat_agent')
    assert LLM_GATEWAY_APP_PLATFORM_HEADER not in llm_gateway_headers(feature='chat_agent', platform=None)
    assert LLM_GATEWAY_APP_PLATFORM_HEADER not in llm_gateway_headers(feature='chat_agent', platform='   ')


def test_llm_gateway_headers_never_forward_client_supplied_junk_platform() -> None:
    """A client-controlled header value must not reach an outbound header verbatim."""
    for junk in ('nintendo-switch', 'desktop\nX-Injected: 1', 'デスクトップ', 'desktop; drop table'):
        assert LLM_GATEWAY_APP_PLATFORM_HEADER not in llm_gateway_headers(feature='chat_agent', platform=junk)
