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
    _ANTHROPIC_ONLY_FEATURES,
    _CACHE_KEY_MODELS,
    _PERPLEXITY_ONLY_FEATURES,
    _PINNED_FEATURES,
    _active_profile,
    _active_profile_name,
    _classify_provider,
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

    def test_premium_profile_is_default(self):
        assert _active_profile_name == 'premium'

    def test_profiles_cover_expected_providers(self):
        """Each profile should have features across expected providers."""
        for profile_name, profile in MODEL_QOS_PROFILES.items():
            providers = {_classify_provider(model) for model in profile.values()}
            assert 'openai' in providers, f'{profile_name} missing OpenAI models'
            assert 'anthropic' in providers, f'{profile_name} missing Anthropic models'
            assert 'perplexity' in providers, f'{profile_name} missing Perplexity models'
        # Both profiles keep OpenRouter for wrapped_analysis
        for profile_name in MODEL_QOS_PROFILES:
            providers = {_classify_provider(m) for m in MODEL_QOS_PROFILES[profile_name].values()}
            assert 'openrouter' in providers, f'{profile_name} should have OpenRouter (wrapped_analysis)'

    def test_premium_profile_models(self):
        """Premium uses gpt-5.4-mini for flagship, gpt-4.1-mini for quality-sensitive, gpt-4.1-nano for simple."""
        premium = MODEL_QOS_PROFILES['premium']
        # Flagship features use gpt-5.4-mini
        assert premium['conv_structure'] == 'gpt-5.4-mini'
        assert premium['chat_responses'] == 'gpt-5.4-mini'
        assert premium['goals_advice'] == 'gpt-5.4-mini'
        # Quality-sensitive features use gpt-4.1-mini
        assert premium['memories'] == 'gpt-4.1-mini'
        assert premium['chat_extraction'] == 'gpt-4.1-mini'
        assert premium['chat_graph'] == 'gpt-4.1-mini'
        assert premium['external_structure'] == 'gpt-4.1-mini'
        assert premium['memory_conflict'] == 'gpt-4.1-mini'
        assert premium['knowledge_graph'] == 'gpt-4.1-mini'
        assert premium['goals'] == 'gpt-4.1-mini'
        assert premium['proactive_notification'] == 'gpt-4.1-mini'
        # Simple features use gpt-4.1-nano
        assert premium['conv_app_select'] == 'gpt-4.1-nano'
        assert premium['session_titles'] == 'gpt-4.1-nano'
        assert premium['followup'] == 'gpt-4.1-nano'
        # Unchanged
        assert premium['chat_agent'] == 'claude-sonnet-4-6'
        assert premium['web_search'] == 'sonar-pro'
        # Persona uses direct OpenAI API
        assert premium['persona_chat'] == 'gpt-4.1-nano'
        assert premium['persona_chat_premium'] == 'gpt-5.4-mini'

    def test_max_profile_models(self):
        """Max uses gpt-5.4 flagship, gpt-4.1-mini for cheap tasks, production-grade models."""
        max_prof = MODEL_QOS_PROFILES['max']
        # Flagship uses gpt-5.4
        assert max_prof['chat_responses'] == 'gpt-5.4'
        assert max_prof['goals_advice'] == 'gpt-5.4'
        assert max_prof['app_generator'] == 'gpt-5.4'
        assert max_prof['conv_action_items'] == 'gpt-5.4'
        assert max_prof['conv_structure'] == 'gpt-5.4'
        assert max_prof['daily_summary'] == 'gpt-5.4'
        assert max_prof['persona_clone'] == 'gpt-5.4'
        assert max_prof['notifications'] == 'gpt-5.4'
        # Cheap tasks use gpt-4.1-mini
        assert max_prof['conv_app_select'] == 'gpt-4.1-mini'
        assert max_prof['memories'] == 'gpt-4.1-mini'
        assert max_prof['learnings'] == 'o4-mini'
        assert max_prof['chat_graph'] == 'gpt-4.1'
        # Persona uses direct OpenAI API
        assert max_prof['persona_chat'] == 'gpt-4.1-nano'
        assert max_prof['persona_chat_premium'] == 'gpt-5.4-mini'
        # OpenRouter for wrapped_analysis only
        assert max_prof['wrapped_analysis'] == 'google/gemini-3-flash-preview'
        # Anthropic & Perplexity unchanged
        assert max_prof['chat_agent'] == 'claude-sonnet-4-6'
        assert max_prof['web_search'] == 'sonar-pro'

    def test_max_profile_model_variants(self):
        """Max profile uses 9 distinct model IDs."""
        max_prof = MODEL_QOS_PROFILES['max']
        distinct_models = set(max_prof.values())
        expected = {
            'gpt-5.4',
            'gpt-4.1-mini',
            'gpt-4.1',
            'o4-mini',
            'gpt-4.1-nano',
            'gpt-5.4-mini',
            'claude-sonnet-4-6',
            'google/gemini-3-flash-preview',
            'sonar-pro',
        }
        assert distinct_models == expected

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

    def test_persona_chat_returns_model_string(self):
        model = get_model('persona_chat')
        assert len(model) > 0  # May be OpenAI (max) or OpenRouter (premium)

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
        # Both use gpt-4.1-mini in premium profile (quality-sensitive)
        llm1 = get_llm('memories')
        llm2 = get_llm('goals')
        assert llm1 is llm2

    def test_different_models_return_different_instances(self):
        # memories=gpt-4.1-mini, conv_structure=gpt-5.4-mini in premium
        llm1 = get_llm('memories')
        llm2 = get_llm('conv_structure')
        assert llm1 is not llm2

    def test_streaming_returns_different_instance(self):
        llm = get_llm('conv_action_items')
        llm_stream = get_llm('conv_action_items', streaming=True)
        assert llm is not llm_stream

    def test_persona_chat_returns_client(self):
        # persona_chat is gpt-4.1-nano (OpenAI) in both profiles
        llm = get_llm('persona_chat', streaming=True)
        assert hasattr(llm, 'invoke')

    def test_cache_key_applied_for_cacheable_model(self):
        # conv_structure uses gpt-5.4-mini (premium) or gpt-5.4 (max), both in _CACHE_KEY_MODELS
        llm_with_key = get_llm('conv_structure', cache_key='omi-test-key')
        llm_without_key = get_llm('conv_structure')
        assert llm_with_key is not llm_without_key
        assert hasattr(llm_with_key, 'invoke')

    def test_cache_key_ignored_for_non_cacheable_model(self, monkeypatch):
        # Override to a model not in _CACHE_KEY_MODELS
        monkeypatch.setenv('MODEL_QOS_MEMORIES', 'gpt-4.1-nano')
        llm_with_key = get_llm('memories', cache_key='omi-test-key')
        llm_without_key = get_llm('memories')
        assert llm_with_key is llm_without_key

    def test_cache_key_ignored_after_override_to_non_cacheable(self, monkeypatch):
        monkeypatch.setenv('MODEL_QOS_CONV_STRUCTURE', 'gpt-4.1-mini')
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

    def test_cache_key_models_contains_expected(self):
        assert 'gpt-5.4' in _CACHE_KEY_MODELS
        assert 'gpt-5.4-mini' in _CACHE_KEY_MODELS


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
        assert info['web_search']['provider'] == 'perplexity'
        assert info['conv_action_items']['provider'] == 'openai'
        # persona_chat uses direct OpenAI API in both profiles
        assert info['persona_chat']['provider'] == 'openai'
        # wrapped_analysis uses OpenRouter in both profiles
        assert info['wrapped_analysis']['provider'] == 'openrouter'

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
    """Verify provider detection from model name and feature routing."""

    def test_classify_provider_openai(self):
        assert _classify_provider('gpt-5.4') == 'openai'
        assert _classify_provider('gpt-5.4-mini') == 'openai'
        assert _classify_provider('gpt-4.1-nano') == 'openai'
        assert _classify_provider('o4-mini') == 'openai'

    def test_classify_provider_anthropic(self):
        assert _classify_provider('claude-sonnet-4-6') == 'anthropic'
        assert _classify_provider('claude-haiku-3.5') == 'anthropic'

    def test_classify_provider_openrouter(self):
        assert _classify_provider('google/gemini-flash-1.5-8b') == 'openrouter'
        assert _classify_provider('anthropic/claude-3.5-sonnet') == 'openrouter'

    def test_classify_provider_perplexity(self):
        assert _classify_provider('sonar-pro') == 'perplexity'
        assert _classify_provider('sonar') == 'perplexity'

    def test_chat_agent_is_anthropic_only(self):
        assert 'chat_agent' in _ANTHROPIC_ONLY_FEATURES

    def test_web_search_is_perplexity_only(self):
        assert 'web_search' in _PERPLEXITY_ONLY_FEATURES

    def test_persona_chat_uses_openai_in_both_profiles(self):
        """Persona chat features use direct OpenAI API in both profiles."""
        for profile_name in ['max', 'premium']:
            prof = MODEL_QOS_PROFILES[profile_name]
            assert _classify_provider(prof['persona_chat']) == 'openai', f'{profile_name} persona_chat'
            assert _classify_provider(prof['persona_chat_premium']) == 'openai', f'{profile_name} persona_chat_premium'

    def test_wrapped_analysis_uses_openrouter_in_both_profiles(self):
        """wrapped_analysis uses OpenRouter (gemini-3-flash-preview) in both profiles."""
        for profile_name in ['max', 'premium']:
            prof = MODEL_QOS_PROFILES[profile_name]
            assert _classify_provider(prof['wrapped_analysis']) == 'openrouter', f'{profile_name} wrapped_analysis'

    def test_conv_features_are_openai(self):
        max_prof = MODEL_QOS_PROFILES['max']
        for feature in ['conv_action_items', 'conv_structure', 'conv_app_result', 'conv_app_select']:
            assert _classify_provider(max_prof[feature]) == 'openai'


class TestProviderSafetyGuard:
    """Verify get_llm() rejects Anthropic/Perplexity features and cross-provider overrides."""

    def test_get_llm_rejects_anthropic_only_feature(self):
        with pytest.raises(ValueError, match='Anthropic'):
            get_llm('chat_agent')

    def test_get_llm_rejects_perplexity_only_feature(self):
        with pytest.raises(ValueError, match='Perplexity'):
            get_llm('web_search')

    def test_get_llm_rejects_claude_model_override(self, monkeypatch):
        """Env override to a claude model is rejected — can't serve via ChatOpenAI."""
        monkeypatch.setenv('MODEL_QOS_CONV_ACTION_ITEMS', 'claude-haiku-3.5')
        with pytest.raises(ValueError, match='Anthropic'):
            get_llm('conv_action_items')

    def test_get_llm_rejects_sonar_model_override(self, monkeypatch):
        """Env override to a sonar model is rejected — can't serve via ChatOpenAI."""
        monkeypatch.setenv('MODEL_QOS_CONV_STRUCTURE', 'sonar-pro')
        with pytest.raises(ValueError, match='Perplexity'):
            get_llm('conv_structure')


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


class TestProfileSelectionAtImportTime:
    """Verify MODEL_QOS env var selects the correct profile at module load time."""

    def test_premium_profile_selected_via_env(self):
        """MODEL_QOS=premium should select premium profile at import time."""
        import subprocess

        result = subprocess.run(
            [
                'python3',
                '-c',
                (
                    "import sys; from unittest.mock import MagicMock; "
                    "[sys.modules.setdefault(m, MagicMock()) for m in "
                    "['firebase_admin','firebase_admin.firestore','google.cloud.firestore',"
                    "'google.cloud.firestore_v1','google.cloud.firestore_v1.base_query',"
                    "'database','database._client','database.llm_usage']]; "
                    "import os; os.environ['OPENAI_API_KEY']='sk-test'; "
                    "os.environ['ANTHROPIC_API_KEY']='sk-ant-test'; "
                    "os.environ['MODEL_QOS']='premium'; "
                    "from utils.llm.clients import _active_profile_name; "
                    "assert _active_profile_name == 'premium', f'Expected premium, got {_active_profile_name}'"
                ),
            ],
            capture_output=True,
            text=True,
            cwd=str(os.path.join(os.path.dirname(__file__), '..', '..')),
        )
        assert result.returncode == 0, f"premium profile test failed: {result.stderr}"

    def test_invalid_profile_falls_back_to_premium(self):
        """MODEL_QOS=bogus should fall back to premium profile."""
        import subprocess

        result = subprocess.run(
            [
                'python3',
                '-c',
                (
                    "import sys; from unittest.mock import MagicMock; "
                    "[sys.modules.setdefault(m, MagicMock()) for m in "
                    "['firebase_admin','firebase_admin.firestore','google.cloud.firestore',"
                    "'google.cloud.firestore_v1','google.cloud.firestore_v1.base_query',"
                    "'database','database._client','database.llm_usage']]; "
                    "import os; os.environ['OPENAI_API_KEY']='sk-test'; "
                    "os.environ['ANTHROPIC_API_KEY']='sk-ant-test'; "
                    "os.environ['MODEL_QOS']='bogus'; "
                    "from utils.llm.clients import _active_profile_name; "
                    "assert _active_profile_name == 'premium', f'Expected premium fallback, got {_active_profile_name}'"
                ),
            ],
            capture_output=True,
            text=True,
            cwd=str(os.path.join(os.path.dirname(__file__), '..', '..')),
        )
        assert result.returncode == 0, f"invalid profile fallback test failed: {result.stderr}"


class TestExpandedCallsiteCoverage:
    """Verify all wired files use get_llm/get_model with correct feature keys."""

    def _read_source(self, rel_path: str) -> str:
        from pathlib import Path

        backend_dir = Path(__file__).resolve().parent.parent.parent
        return (backend_dir / rel_path).read_text()

    def test_conversation_processing_all_keys(self):
        import re

        source = self._read_source("utils/llm/conversation_processing.py")
        calls = re.findall(r"get_llm\('(\w+)'", source)
        for key in [
            'conv_folder',
            'conv_discard',
            'conv_action_items',
            'conv_structure',
            'conv_app_result',
            'conv_app_select',
            'daily_summary',
        ]:
            assert key in calls, f"Missing get_llm('{key}') in conversation_processing.py"
        assert calls.count('conv_structure') >= 2, "conv_structure should appear at least twice"
        assert calls.count('conv_app_select') == 2, "conv_app_select should appear exactly twice"

    def test_memories_all_keys(self):
        import re

        source = self._read_source("utils/llm/memories.py")
        calls = re.findall(r"get_llm\('(\w+)'", source)
        for key in ['memories', 'learnings', 'memory_category', 'memory_conflict']:
            assert key in calls, f"Missing get_llm('{key}') in memories.py"
        assert calls.count('memories') == 2, "memories should appear exactly twice"

    def test_knowledge_graph_all_keys(self):
        import re

        source = self._read_source("utils/llm/knowledge_graph.py")
        calls = re.findall(r"get_llm\('(\w+)'", source)
        assert calls.count('knowledge_graph') == 2, "knowledge_graph should appear exactly twice"

    def test_followup_key(self):
        source = self._read_source("utils/llm/followup.py")
        assert "get_llm('followup')" in source

    def test_trends_key(self):
        source = self._read_source("utils/llm/trends.py")
        assert "get_llm('trends')" in source

    def test_chat_py_all_keys(self):
        import re

        source = self._read_source("utils/llm/chat.py")
        calls = re.findall(r"get_llm\('(\w+)'", source)
        assert 'chat_responses' in calls
        assert 'chat_extraction' in calls

    def test_persona_py_all_keys(self):
        import re

        source = self._read_source("utils/llm/persona.py")
        calls = re.findall(r"get_llm\('(\w+)'", source)
        assert 'persona_clone' in calls
        assert calls.count('persona_clone') >= 4, "persona_clone should appear in multiple clone functions"
        # Dynamic persona_chat/persona_chat_premium routing via feature variable
        assert "get_llm(feature" in source, "persona.py should pass dynamic feature for chat routing"

    def test_goals_py_all_keys(self):
        import re

        source = self._read_source("utils/llm/goals.py")
        calls = re.findall(r"get_llm\('(\w+)'", source)
        assert 'goals' in calls, "Missing get_llm('goals') in goals.py"
        assert 'goals_advice' in calls, "Missing get_llm('goals_advice') in goals.py"

    def test_notifications_py_key(self):
        import re

        source = self._read_source("utils/llm/notifications.py")
        calls = re.findall(r"get_llm\('(\w+)'", source)
        assert 'notifications' in calls

    def test_app_generator_py_all_keys(self):
        import re

        source = self._read_source("utils/llm/app_generator.py")
        calls = re.findall(r"get_llm\('(\w+)'", source)
        assert 'app_generator' in calls
        assert 'app_integration' in calls
        assert calls.count('app_integration') >= 2, "app_integration should appear in multiple functions"

    def test_graph_py_key(self):
        import re

        source = self._read_source("utils/retrieval/graph.py")
        calls = re.findall(r"get_llm\('(\w+)'", source)
        assert 'chat_graph' in calls

    def test_perplexity_tools_key(self):
        import re

        source = self._read_source("utils/retrieval/tools/perplexity_tools.py")
        calls = re.findall(r"get_model\('(\w+)'", source)
        assert 'web_search' in calls

    def test_chat_sessions_router_key(self):
        source = self._read_source("routers/chat_sessions.py")
        assert "get_llm('session_titles')" in source

    def test_apps_router_key(self):
        source = self._read_source("routers/apps.py")
        assert "get_llm('app_integration')" in source

    def test_app_integrations_key(self):
        source = self._read_source("utils/app_integrations.py")
        assert "get_llm('app_integration')" in source

    def test_external_integrations_all_keys(self):
        import re

        source = self._read_source("utils/llm/external_integrations.py")
        calls = re.findall(r"get_llm\('(\w+)'", source)
        assert 'external_structure' in calls
        assert calls.count('external_structure') >= 2, "external_structure should appear at least twice"
        assert 'daily_summary_simple' in calls, "Missing get_llm('daily_summary_simple') in external_integrations.py"
        assert 'daily_summary' in calls, "Missing get_llm('daily_summary') in external_integrations.py"

    def test_proactive_notification_key(self):
        import re

        source = self._read_source("utils/llm/proactive_notification.py")
        calls = re.findall(r"get_llm\('(\w+)'", source)
        assert 'proactive_notification' in calls
        assert calls.count('proactive_notification') >= 4, "proactive_notification should appear in 4 functions"

    def test_generate_2025_key(self):
        import re

        source = self._read_source("utils/wrapped/generate_2025.py")
        calls = re.findall(r"get_llm\('(\w+)'", source)
        assert 'wrapped_analysis' in calls

    def test_onboarding_key(self):
        source = self._read_source("utils/onboarding.py")
        assert "get_llm('onboarding')" in source

    def test_no_legacy_llm_mini_invocations_in_wired_files(self):
        """No wired file should still call llm_mini.invoke or llm_medium_experiment.invoke."""
        wired_files = [
            "utils/llm/chat.py",
            "utils/llm/conversation_processing.py",
            "utils/llm/memories.py",
            "utils/llm/knowledge_graph.py",
            "utils/llm/proactive_notification.py",
            "utils/llm/external_integrations.py",
            "utils/llm/goals.py",
            "utils/llm/notifications.py",
            "utils/llm/persona.py",
            "utils/llm/followup.py",
            "utils/llm/app_generator.py",
            "utils/llm/trends.py",
            "utils/onboarding.py",
            "utils/retrieval/graph.py",
        ]
        for path in wired_files:
            source = self._read_source(path)
            assert 'llm_mini.invoke' not in source, f"{path} still uses llm_mini.invoke"
            assert 'llm_medium_experiment.invoke' not in source, f"{path} still uses llm_medium_experiment.invoke"
            assert 'llm_high.invoke' not in source, f"{path} still uses llm_high.invoke"


class TestOverrideWarningLog:
    """Verify override warnings fire when provider doesn't match."""

    def test_warns_on_cross_provider_override(self, monkeypatch, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger='utils.llm.clients'):
            monkeypatch.setenv('MODEL_QOS_CONV_ACTION_ITEMS', 'google/gemini-flash-1.5-8b')
            result = get_model('conv_action_items')
            assert result == 'google/gemini-flash-1.5-8b'
        assert any('may be invalid' in r.message for r in caplog.records), "Expected cross-provider override warning"

    def test_no_warning_on_same_provider_override(self, monkeypatch, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger='utils.llm.clients'):
            monkeypatch.setenv('MODEL_QOS_CONV_ACTION_ITEMS', 'gpt-4.1-mini')
            result = get_model('conv_action_items')
            assert result == 'gpt-4.1-mini'
        assert not any(
            'may be invalid' in r.message for r in caplog.records
        ), "No warning expected for same-provider override"


class TestRuntimeProviderRouting:
    """Verify get_llm() routes to correct client factory based on resolved model."""

    def test_persona_chat_routes_to_openai(self):
        """persona_chat uses direct OpenAI API — should route to OpenAI, not OpenRouter."""
        llm = get_llm('persona_chat')
        base_url = getattr(llm, 'openai_api_base', None) or ''
        assert 'openrouter' not in base_url

    def test_override_to_openrouter_model_routes_to_openrouter(self, monkeypatch):
        """If an override sets an OpenRouter model, get_llm should route via OpenRouter."""
        monkeypatch.setenv('MODEL_QOS_PERSONA_CHAT', 'google/gemini-flash-1.5-8b')
        llm = get_llm('persona_chat')
        base_url = getattr(llm, 'openai_api_base', None) or ''
        assert 'openrouter' in base_url

    def test_openrouter_temperature_applied_via_get_llm(self, monkeypatch):
        """When get_llm routes to OpenRouter, _OPENROUTER_TEMPERATURES config is applied."""
        from utils.llm.clients import _OPENROUTER_TEMPERATURES

        # Override persona_chat to an OpenRouter model to test temperature routing
        monkeypatch.setenv('MODEL_QOS_PERSONA_CHAT', 'google/gemini-flash-1.5-8b')
        llm = get_llm('persona_chat')
        expected_temp = _OPENROUTER_TEMPERATURES.get('persona_chat')
        assert expected_temp == 0.8, "persona_chat should have temp 0.8 in config"
        assert llm.temperature == expected_temp, "get_llm should apply _OPENROUTER_TEMPERATURES"
