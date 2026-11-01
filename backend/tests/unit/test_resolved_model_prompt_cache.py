"""Provider fields follow the actual BYOK route, including gateway auto-lane clients."""

from types import SimpleNamespace

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from utils import byok
from utils.llm import clients, conversation_processing, working_observations
from utils.llm.gateway_client import GatewayContextChatOpenAI
from utils.llm.model_config import LUNA_MODEL
from utils.llm.prompt_cache import EXPLICIT_CACHE_OPTIONS, model_supports_explicit_cache


@pytest.fixture(scope='module')
def sdk_models():
    return {
        'gateway': GatewayContextChatOpenAI(model='omi:auto:conversation-notes', api_key='fake'),
        'anthropic': ChatAnthropic(model='claude-sonnet-4-6', api_key='fake'),
        'openai': ChatOpenAI(model=LUNA_MODEL, api_key='fake'),
    }


@pytest.mark.parametrize(
    'feature', ['conv_structure', 'conv_action_items', 'conv_app_result', 'chat_agent', 'memory_l1']
)
@pytest.mark.parametrize(
    'keys,profile_provider,expected',
    [
        ({}, None, True),
        ({'deepgram': 'fake'}, None, True),
        ({'openai': 'fake'}, 'openai', True),
        ({'openai': 'fake', 'anthropic': 'fake'}, 'openai', True),
        ({'anthropic': 'fake'}, 'anthropic', False),
        ({'openai': 'fake', 'anthropic': 'fake'}, 'anthropic', False),
    ],
)
def test_get_llm_filters_options_after_full_byok_resolution(
    monkeypatch, sdk_models, feature, keys, profile_provider, expected
):
    monkeypatch.setattr(clients, 'should_route_features_through_gateway', lambda: True)
    monkeypatch.setattr(clients, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(clients, '_get_model_config', lambda feature: (LUNA_MODEL, 'openai'))
    profile_model = LUNA_MODEL if profile_provider == 'openai' else 'claude-sonnet-4-6'
    monkeypatch.setattr(
        clients, 'get_byok_profile', lambda: {feature: (profile_model, profile_provider)} if profile_provider else None
    )
    monkeypatch.setattr(clients, 'get_or_create_omi_gateway_llm', lambda *a, **k: sdk_models['gateway'])
    monkeypatch.setattr(clients, 'get_or_create_omi_gateway_llm_for_byok', lambda *a, **k: sdk_models['gateway'])
    monkeypatch.setattr(clients, '_create_byok_client', lambda model, provider, *a, **k: sdk_models[provider])
    token = byok._byok_ctx.set(keys)
    try:
        model = clients.get_llm(feature, prompt_cache_options=EXPLICIT_CACHE_OPTIONS)
    finally:
        byok._byok_ctx.reset(token)
    # The chat mount binds tools after factory cache options; neither identity
    # nor options may be lost through LangChain's second binding.
    model = model.bind(tools=[])
    assert model_supports_explicit_cache(model) is expected
    bound_options = getattr(model, 'kwargs', {}).get('extra_body', {}).get('prompt_cache_options')
    assert bound_options == (EXPLICIT_CACHE_OPTIONS if expected else None)
    # Cached SDK clients must not retain another request's resolved identity.
    assert sdk_models['gateway'].metadata is None
    assert sdk_models['anthropic'].metadata is None


@pytest.mark.parametrize(
    'model_name,expected',
    [(LUNA_MODEL, True), ('gpt-5.6-sol', True), ('claude-sonnet-4-6', False), ('gemini-2.5-pro', False), ('', False)],
)
def test_memory_l1_breakpoint_follows_injected_model(monkeypatch, model_name, expected):
    captured = []
    model = SimpleNamespace(
        model_name=model_name,
        invoke=lambda messages: captured.append(messages) or SimpleNamespace(content='{"items": []}'),
    )
    monkeypatch.setenv('OMI_LLM_GPT56_EXPLICIT_CACHE_ENABLED', 'true')
    working_observations.extract_l1_memory_archive_items_from_text(
        uid='test',
        source_id='test',
        source_type='voice_transcript',
        text='We discussed the project and next steps.',
        llm=model,
        persist_route_outcomes=False,
        prompt_cache_enabled=True,
    )
    assert ('prompt_cache_breakpoint' in str(captured)) is expected


def test_deepgram_key_does_not_disable_conversation_cache_opt_out(monkeypatch):
    monkeypatch.setattr(conversation_processing, 'should_route_features_through_gateway', lambda: True)
    monkeypatch.setenv('OMI_LLM_GPT56_EXPLICIT_CACHE_ENABLED', 'true')
    token = byok._byok_ctx.set({'deepgram': 'fake'})
    try:
        assert conversation_processing._gpt56_explicit_cache_enabled()
    finally:
        byok._byok_ctx.reset(token)
