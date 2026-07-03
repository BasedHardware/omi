from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
import pytest

from utils.llm import clients, gateway_shadow
from utils.llm import providers
from utils.llm.gateway_client import DEFAULT_LLM_GATEWAY_URL, get_llm_gateway_base_url
from utils.llm.gateway_client import (
    LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR,
    LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE_ENV_VAR,
    LLM_GATEWAY_FEATURE_MODE_ENV_VAR,
    LLM_GATEWAY_URL_ENV_VAR,
    feature_auto_lane_id,
    raise_if_gateway_feature_mode_blocks_direct_model_surface,
    should_route_features_through_gateway,
)
from utils.llm.clients import get_llm_gateway_chat_structured


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
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://gateway.internal:8080/')
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'service-token')
    monkeypatch.setattr(providers, 'ChatOpenAI', FakeChatOpenAI)
    original_cache = dict(providers._llm_cache)
    providers._llm_cache.clear()

    try:
        result = get_llm_gateway_chat_structured()

        assert isinstance(result, FakeChatOpenAI)
        assert captured['model'] == 'omi:auto:chat-structured'
        assert captured['base_url'] == 'http://gateway.internal:8080/v1'
        assert captured['request_timeout'] == 35.0
        assert captured['default_headers']['X-Omi-Service-Caller'] == 'backend'
        assert captured['default_headers']['Authorization'] == 'Bearer service-token'
    finally:
        providers._llm_cache.clear()
        providers._llm_cache.update(original_cache)


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

    def fake_gateway(lane_id, streaming=False, options=None):
        captured['lane_id'] = lane_id
        captured['streaming'] = streaming
        return gateway

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setattr(clients, 'get_or_create_omi_gateway_llm', fake_gateway)

    result = clients.get_llm('conv_discard', streaming=True).invoke('hello')

    assert result.content == 'gateway response'
    assert captured == {'lane_id': feature_auto_lane_id('conv_discard'), 'streaming': True}


def test_get_llm_feature_gateway_mode_blocks_byok_direct_bypass(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.delenv(LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR, raising=False)
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.setattr(clients, 'get_byok_key', lambda provider: 'sk-test-byok' if provider == 'openai' else None)

    try:
        clients.get_llm('conv_discard')
    except RuntimeError as exc:
        assert 'get_llm.conv_discard.byok' in str(exc)
    else:
        raise AssertionError('expected gateway mode to block BYOK direct bypass')


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
    except RuntimeError as exc:
        assert 'file_chat.openai_files' in str(exc)
    else:
        raise AssertionError('expected direct model surface to be blocked')


def test_gateway_feature_mode_allows_acknowledged_direct_exception(monkeypatch):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv(LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR, 'true')
    monkeypatch.delenv('K_SERVICE', raising=False)

    raise_if_gateway_feature_mode_blocks_direct_model_surface('file_chat.openai_files')


@pytest.mark.asyncio
async def test_app_icon_generation_uses_legacy_provider_when_gateway_feature_mode_off(monkeypatch):
    from utils.llm import app_generator

    monkeypatch.setattr(app_generator, 'should_route_features_through_gateway', lambda: False)
    monkeypatch.setattr(app_generator, '_generate_app_icon_via_openai', lambda _prompt: b'legacy-image')

    def fail_gateway(**_kwargs):
        raise AssertionError('gateway image generation should not run with feature mode off')

    monkeypatch.setattr(app_generator, 'generate_image_via_gateway', fail_gateway)

    assert await app_generator.generate_app_icon('Name', 'Description', 'other') == b'legacy-image'


@pytest.mark.asyncio
async def test_perplexity_tool_uses_legacy_provider_when_gateway_feature_mode_off(monkeypatch):
    perplexity_tools = _load_perplexity_tools()

    monkeypatch.setattr(perplexity_tools, 'should_route_features_through_gateway', lambda: False)
    monkeypatch.setattr(perplexity_tools, '_perplexity_legacy_search', lambda _query: _async_return('legacy-search'))
    monkeypatch.setattr(perplexity_tools, '_perplexity_gateway_search', lambda _query: _raise_gateway_called())

    assert await perplexity_tools.perplexity_web_search_tool.coroutine('query') == 'legacy-search'


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


def _load_perplexity_tools():
    module_path = Path(__file__).parents[2] / 'utils' / 'retrieval' / 'tools' / 'perplexity_tools.py'
    spec = importlib.util.spec_from_file_location('perplexity_tools_under_test', module_path)
    assert spec is not None and spec.loader is not None
    perplexity_tools = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(perplexity_tools)
    return perplexity_tools


async def _async_return(value):
    return value


async def _raise_gateway_called():
    raise AssertionError('gateway web search should not run with feature mode off')
