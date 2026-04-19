"""Tests for Model QoS profile system in utils/llm/clients.py."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Pre-mock heavy deps before any imports touch them
# ---------------------------------------------------------------------------
_HEAVY_MOCKS = {
    'firebase_admin': MagicMock(),
    'firebase_admin.firestore': MagicMock(),
    'google.cloud.firestore': MagicMock(),
    'google.cloud.firestore_v1': MagicMock(),
    'google.cloud.firestore_v1.base_query': MagicMock(),
    'database': MagicMock(),
    'database._client': MagicMock(),
    'database.llm_usage': MagicMock(),
}

for _mod, _mock in _HEAVY_MOCKS.items():
    sys.modules.setdefault(_mod, _mock)

# Set required env vars before importing clients
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-key-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'sk-ant-test-fake-key')

# Now import the module under test
from utils.llm.clients import (
    MODEL_QOS_PROFILES,
    _ANTHROPIC_FEATURES,
    _CACHE_KEY_MODELS,
    _OPENROUTER_FEATURES,
    _PERPLEXITY_FEATURES,
    _PINNED_FEATURES,
    _active_profile,
    _active_profile_name,
    _get_or_create_openai_llm,
    _get_or_create_openrouter_llm,
    _llm_cache,
    get_llm,
    get_model,
    get_qos_info,
)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestModelQosProfiles:
    """Verify profile structure and completeness."""

    def test_two_profiles_exist(self):
        assert set(MODEL_QOS_PROFILES.keys()) == {'premium', 'max'}

    def test_all_profiles_have_same_features(self):
        premium_features = set(MODEL_QOS_PROFILES['premium'].keys())
        max_features = set(MODEL_QOS_PROFILES['max'].keys())
        assert premium_features == max_features

    def test_max_profile_is_default(self):
        assert _active_profile_name == 'max'

    def test_profiles_cover_all_providers(self):
        """Each profile should have features across all 4 providers."""
        for profile_name, profile in MODEL_QOS_PROFILES.items():
            features = set(profile.keys())
            has_openai = bool(features - _OPENROUTER_FEATURES - _ANTHROPIC_FEATURES - _PERPLEXITY_FEATURES)
            has_anthropic = bool(features & _ANTHROPIC_FEATURES)
            has_openrouter = bool(features & _OPENROUTER_FEATURES)
            has_perplexity = bool(features & _PERPLEXITY_FEATURES)
            assert has_openai, f'{profile_name} missing OpenAI features'
            assert has_anthropic, f'{profile_name} missing Anthropic features'
            assert has_openrouter, f'{profile_name} missing OpenRouter features'
            assert has_perplexity, f'{profile_name} missing Perplexity features'

    def test_premium_profile_uses_cheaper_models(self):
        """Premium profile should use cheaper models than max for most features."""
        premium = MODEL_QOS_PROFILES['premium']
        max_prof = MODEL_QOS_PROFILES['max']
        # conv_structure: premium uses gpt-4.1-mini, max uses gpt-5.1
        assert premium['conv_structure'] == 'gpt-4.1-mini'
        assert max_prof['conv_structure'] == 'gpt-5.1'
        # chat_agent: premium uses haiku, max uses sonnet
        assert 'haiku' in premium['chat_agent']
        assert 'sonnet' in max_prof['chat_agent']

    def test_max_profile_matches_current_behavior(self):
        """Max profile should match current production model assignments."""
        max_prof = MODEL_QOS_PROFILES['max']
        assert max_prof['conv_action_items'] == 'gpt-5.1'
        assert max_prof['conv_structure'] == 'gpt-5.1'
        assert max_prof['chat_responses'] == 'gpt-5.2'
        assert max_prof['chat_agent'] == 'claude-sonnet-4-6'
        assert max_prof['persona_chat'] == 'google/gemini-flash-1.5-8b'
        assert max_prof['wrapped_analysis'] == 'google/gemini-3-flash-preview'
        assert max_prof['web_search'] == 'sonar-pro'

    def test_new_features_present(self):
        """Verify newly added features exist in both profiles."""
        new_features = [
            'conv_folder',
            'conv_discard',
            'daily_summary_simple',
            'external_structure',
            'learnings',
            'chat_graph',
            'proactive_notification',
        ]
        for feature in new_features:
            for profile_name, profile in MODEL_QOS_PROFILES.items():
                assert feature in profile, f'{feature} missing from {profile_name}'


class TestGetModel:
    """Verify get_model() resolution: pinned > env override > profile > fallback."""

    def test_returns_profile_default(self):
        assert get_model('conv_action_items') == MODEL_QOS_PROFILES[_active_profile_name]['conv_action_items']

    def test_env_override_takes_precedence(self, monkeypatch):
        monkeypatch.setenv('MODEL_QOS_CONV_ACTION_ITEMS', 'gpt-5.1')
        assert get_model('conv_action_items') == 'gpt-5.1'

    def test_env_override_with_anthropic_model(self, monkeypatch):
        monkeypatch.setenv('MODEL_QOS_CHAT_AGENT', 'claude-haiku-3.5')
        assert get_model('chat_agent') == 'claude-haiku-3.5'

    def test_empty_env_override_falls_back_to_profile(self, monkeypatch):
        monkeypatch.setenv('MODEL_QOS_CONV_ACTION_ITEMS', '')
        assert get_model('conv_action_items') == _active_profile['conv_action_items']

    def test_unknown_feature_falls_back_to_gpt41_mini(self):
        assert get_model('totally_unknown_feature') == 'gpt-4.1-mini'

    def test_pinned_feature_ignores_profile(self):
        assert get_model('fair_use') == 'gpt-5.1'

    def test_pinned_feature_ignores_env_override(self, monkeypatch):
        monkeypatch.setenv('MODEL_QOS_FAIR_USE', 'gpt-4.1-nano')
        assert get_model('fair_use') == 'gpt-5.1'

    def test_anthropic_feature_returns_model_string(self):
        model = get_model('chat_agent')
        assert 'claude' in model

    def test_openrouter_feature_returns_model_string(self):
        model = get_model('persona_chat')
        assert '/' in model  # OpenRouter models have provider/model format

    def test_perplexity_feature_returns_model_string(self):
        model = get_model('web_search')
        assert 'sonar' in model


class TestGetLlm:
    """Verify get_llm() returns correct client instances."""

    def test_returns_chatOpenAI_for_openai_feature(self):
        llm = get_llm('conv_action_items')
        assert hasattr(llm, 'invoke')

    def test_caches_instances_same_feature(self):
        llm1 = get_llm('conv_action_items')
        llm2 = get_llm('conv_action_items')
        assert llm1 is llm2

    def test_different_features_same_model_share_instance(self):
        # Both default to gpt-4.1-mini in max profile
        llm1 = get_llm('memories')
        llm2 = get_llm('goals')
        assert llm1 is llm2

    def test_different_models_return_different_instances(self):
        # memories=gpt-4.1-mini, conv_structure=gpt-5.1 in max
        llm1 = get_llm('memories')
        llm2 = get_llm('conv_structure')
        assert llm1 is not llm2

    def test_streaming_returns_different_instance(self):
        llm = get_llm('conv_action_items')
        llm_stream = get_llm('conv_action_items', streaming=True)
        assert llm is not llm_stream

    def test_openrouter_feature_returns_client(self):
        llm = get_llm('persona_chat', streaming=True)
        assert hasattr(llm, 'invoke')

    def test_cache_key_applied_for_gpt51(self):
        llm_with_key = get_llm('conv_structure', cache_key='omi-test-key')
        llm_without_key = get_llm('conv_structure')
        assert llm_with_key is not llm_without_key
        assert hasattr(llm_with_key, 'invoke')

    def test_cache_key_ignored_for_non_gpt51(self):
        llm_with_key = get_llm('memories', cache_key='omi-test-key')
        llm_without_key = get_llm('memories')
        assert llm_with_key is llm_without_key

    def test_cache_key_ignored_after_override_to_non_cacheable(self, monkeypatch):
        monkeypatch.setenv('MODEL_QOS_CONV_STRUCTURE', 'gpt-4.1-nano')
        llm_with_key = get_llm('conv_structure', cache_key='omi-test-key')
        llm_without_key = get_llm('conv_structure')
        assert llm_with_key is llm_without_key

    def test_new_features_return_clients(self):
        """New features should return valid LLM clients."""
        for feature in [
            'conv_folder',
            'conv_discard',
            'daily_summary_simple',
            'external_structure',
            'learnings',
            'chat_graph',
            'proactive_notification',
        ]:
            llm = get_llm(feature)
            assert hasattr(llm, 'invoke'), f'{feature} did not return a valid client'


class TestGetOrCreateLlmBehavioral:
    """Verify client construction behavior."""

    def test_creates_instance_once_per_model(self):
        saved = dict(_llm_cache)
        _llm_cache.clear()
        try:
            inst1 = _get_or_create_openai_llm('gpt-4.1-mini')
            inst2 = _get_or_create_openai_llm('gpt-4.1-mini')
            assert inst1 is inst2
        finally:
            _llm_cache.clear()
            _llm_cache.update(saved)

    def test_gpt51_constructor_receives_extra_body(self):
        from unittest.mock import patch as _patch

        saved = dict(_llm_cache)
        _llm_cache.clear()
        captured_kwargs = {}

        try:
            from langchain_openai import ChatOpenAI as RealChatOpenAI

            original_init = RealChatOpenAI.__init__

            def capturing_init(self, **kwargs):
                captured_kwargs.update(kwargs)
                original_init(self, **kwargs)

            with _patch.object(RealChatOpenAI, '__init__', capturing_init):
                _get_or_create_openai_llm('gpt-5.1')

            assert 'extra_body' in captured_kwargs, "gpt-5.1 must receive extra_body kwarg"
            assert captured_kwargs['extra_body'] == {"prompt_cache_retention": "24h"}
        finally:
            _llm_cache.clear()
            _llm_cache.update(saved)

    def test_non_gpt51_constructor_no_extra_body(self):
        from unittest.mock import patch as _patch

        saved = dict(_llm_cache)
        _llm_cache.clear()
        captured_kwargs = {}

        try:
            from langchain_openai import ChatOpenAI as RealChatOpenAI

            original_init = RealChatOpenAI.__init__

            def capturing_init(self, **kwargs):
                captured_kwargs.update(kwargs)
                original_init(self, **kwargs)

            with _patch.object(RealChatOpenAI, '__init__', capturing_init):
                _get_or_create_openai_llm('gpt-4.1-mini')

            assert 'extra_body' not in captured_kwargs
        finally:
            _llm_cache.clear()
            _llm_cache.update(saved)

    def test_streaming_instance_has_streaming_flag(self):
        from unittest.mock import patch as _patch

        saved = dict(_llm_cache)
        _llm_cache.clear()
        captured_kwargs = {}

        try:
            from langchain_openai import ChatOpenAI as RealChatOpenAI

            original_init = RealChatOpenAI.__init__

            def capturing_init(self, **kwargs):
                captured_kwargs.update(kwargs)
                original_init(self, **kwargs)

            with _patch.object(RealChatOpenAI, '__init__', capturing_init):
                _get_or_create_openai_llm('gpt-4.1-mini', streaming=True)

            assert captured_kwargs.get('streaming') is True
            assert captured_kwargs.get('stream_options') == {"include_usage": True}
        finally:
            _llm_cache.clear()
            _llm_cache.update(saved)


class TestOpenRouterClient:
    """Verify OpenRouter client construction."""

    def test_openrouter_instance_has_base_url(self):
        from unittest.mock import patch as _patch

        saved = dict(_llm_cache)
        _llm_cache.clear()
        captured_kwargs = {}

        try:
            from langchain_openai import ChatOpenAI as RealChatOpenAI

            original_init = RealChatOpenAI.__init__

            def capturing_init(self, **kwargs):
                captured_kwargs.update(kwargs)
                original_init(self, **kwargs)

            with _patch.object(RealChatOpenAI, '__init__', capturing_init):
                _get_or_create_openrouter_llm('google/gemini-flash-1.5-8b', temperature=0.8)

            assert captured_kwargs['base_url'] == "https://openrouter.ai/api/v1"
            assert captured_kwargs['temperature'] == 0.8
            assert 'X-Title' in captured_kwargs.get('default_headers', {})
        finally:
            _llm_cache.clear()
            _llm_cache.update(saved)


class TestCacheKeySafety:
    """Verify cache_key is only applied when the model supports it."""

    def test_cache_key_models_contains_gpt51(self):
        assert 'gpt-5.1' in _CACHE_KEY_MODELS


class TestGetQosInfo:
    """Verify debugging helper."""

    def test_contains_all_profile_features(self):
        info = get_qos_info()
        for feature in _active_profile:
            assert feature in info
            assert 'model' in info[feature]
            assert 'profile' in info[feature]
            assert 'provider' in info[feature]

    def test_contains_pinned_features(self):
        info = get_qos_info()
        for feature in _PINNED_FEATURES:
            assert feature in info

    def test_provider_classification_correct(self):
        info = get_qos_info()
        assert info['chat_agent']['provider'] == 'anthropic'
        assert info['persona_chat']['provider'] == 'openrouter'
        assert info['web_search']['provider'] == 'perplexity'
        assert info['conv_action_items']['provider'] == 'openai'

    def test_reflects_env_override(self, monkeypatch):
        monkeypatch.setenv('MODEL_QOS_CONV_ACTION_ITEMS', 'o4-mini')
        info = get_qos_info()
        assert info['conv_action_items']['model'] == 'o4-mini'


class TestPinnedFeatures:
    """Verify pinned features are immutable."""

    def test_fair_use_pinned_to_gpt51(self):
        assert _PINNED_FEATURES['fair_use'] == 'gpt-5.1'

    def test_pinned_survives_profile_switch(self):
        # Even if profile doesn't list fair_use, it should resolve to pinned value
        assert get_model('fair_use') == 'gpt-5.1'


class TestProviderClassification:
    """Verify features are assigned to correct providers."""

    def test_chat_agent_is_anthropic(self):
        assert 'chat_agent' in _ANTHROPIC_FEATURES

    def test_persona_chat_is_openrouter(self):
        assert 'persona_chat' in _OPENROUTER_FEATURES
        assert 'persona_chat_premium' in _OPENROUTER_FEATURES

    def test_web_search_is_perplexity(self):
        assert 'web_search' in _PERPLEXITY_FEATURES

    def test_wrapped_analysis_is_openrouter(self):
        assert 'wrapped_analysis' in _OPENROUTER_FEATURES

    def test_conv_features_are_openai(self):
        for feature in ['conv_action_items', 'conv_structure', 'conv_apps']:
            assert feature not in _ANTHROPIC_FEATURES
            assert feature not in _OPENROUTER_FEATURES
            assert feature not in _PERPLEXITY_FEATURES


class TestProviderSafetyGuard:
    """Verify get_llm() rejects Anthropic/Perplexity features."""

    def test_get_llm_rejects_anthropic_feature(self):
        with pytest.raises(ValueError, match='Anthropic'):
            get_llm('chat_agent')

    def test_get_llm_rejects_perplexity_feature(self):
        with pytest.raises(ValueError, match='Perplexity'):
            get_llm('web_search')


class TestAnthropicModelExports:
    """Verify ANTHROPIC_AGENT_MODEL is backed by profile."""

    def test_anthropic_agent_model_matches_profile(self):
        from utils.llm.clients import ANTHROPIC_AGENT_MODEL

        assert ANTHROPIC_AGENT_MODEL == get_model('chat_agent')

    def test_anthropic_agent_model_is_string(self):
        from utils.llm.clients import ANTHROPIC_AGENT_MODEL

        assert isinstance(ANTHROPIC_AGENT_MODEL, str)
        assert len(ANTHROPIC_AGENT_MODEL) > 0


class TestRollbackScenario:
    """Verify model can be switched via env var for rollback."""

    def test_override_conv_action_items_to_gpt51(self, monkeypatch):
        monkeypatch.setenv('MODEL_QOS_CONV_ACTION_ITEMS', 'gpt-5.1')
        assert get_model('conv_action_items') == 'gpt-5.1'

    def test_override_chat_agent_to_haiku(self, monkeypatch):
        monkeypatch.setenv('MODEL_QOS_CHAT_AGENT', 'claude-haiku-3.5')
        assert get_model('chat_agent') == 'claude-haiku-3.5'

    def test_override_persona_to_different_model(self, monkeypatch):
        monkeypatch.setenv('MODEL_QOS_PERSONA_CHAT', 'anthropic/claude-3.5-sonnet')
        assert get_model('persona_chat') == 'anthropic/claude-3.5-sonnet'
