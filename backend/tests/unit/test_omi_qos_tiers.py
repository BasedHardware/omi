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
    _STRUCTURED_OUTPUT_FEATURES,
    _active_profile,
    _active_profile_name,
    _byok_profile,
    _byok_profile_name,
    _effective_byok_provider,
    _get_or_create_gemini_llm,
    _get_or_create_openai_llm,
    _get_or_create_openrouter_llm,
    _llm_cache,
    get_llm,
    get_model,
    get_provider,
    get_qos_info,
)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestModelQosProfiles:
    """Verify profile structure and completeness."""

    def test_three_profiles_exist(self):
        assert set(MODEL_QOS_PROFILES.keys()) == {'premium', 'max', 'byok'}

    def test_all_profiles_have_same_features(self):
        feature_sets = {name: set(profile.keys()) for name, profile in MODEL_QOS_PROFILES.items()}
        reference = feature_sets['premium']
        for name, features in feature_sets.items():
            assert features == reference, f'{name} features differ from premium: {features ^ reference}'

    def test_premium_profile_is_default(self):
        assert _active_profile_name == 'premium'

    def test_profiles_cover_expected_providers(self):
        """Each profile should have features across expected providers."""
        for profile_name, profile in MODEL_QOS_PROFILES.items():
            providers = {provider for _model, provider in profile.values()}
            assert 'anthropic' in providers, f'{profile_name} missing Anthropic models'
            assert 'perplexity' in providers, f'{profile_name} missing Perplexity models'
            assert 'openrouter' in providers, f'{profile_name} should have OpenRouter (wrapped_analysis)'
        # OpenAI-based profiles must have OpenAI provider
        for name in ('premium', 'max', 'byok'):
            providers = {p for _m, p in MODEL_QOS_PROFILES[name].values()}
            assert 'openai' in providers, f'{name} missing OpenAI models'
        # Premium profile must have Gemini provider
        providers = {p for _m, p in MODEL_QOS_PROFILES['premium'].values()}
        assert 'gemini' in providers, 'premium should have Gemini direct models'

    def test_premium_profile_models(self):
        """Premium uses gpt-5.4-mini for flagship, gpt-4.1-mini for quality-sensitive, gemini for free-text."""
        premium = MODEL_QOS_PROFILES['premium']
        # Flagship features use gpt-5.4-mini on openai
        assert premium['conv_structure'] == ('gpt-5.4-mini', 'openai')
        assert premium['chat_responses'] == ('gpt-5.4-mini', 'openai')
        assert premium['goals_advice'] == ('gpt-5.4-mini', 'openai')
        # Quality-sensitive features use gpt-4.1-mini on openai
        assert premium['memories'] == ('gpt-4.1-mini', 'openai')
        assert premium['chat_extraction'] == ('gpt-4.1-mini', 'openai')
        assert premium['chat_graph'] == ('gpt-4.1-mini', 'openai')
        assert premium['external_structure'] == ('gpt-4.1-mini', 'openai')
        assert premium['memory_conflict'] == ('gpt-4.1-mini', 'openai')
        assert premium['knowledge_graph'] == ('gpt-4.1-mini', 'openai')
        assert premium['goals'] == ('gpt-4.1-mini', 'openai')
        assert premium['proactive_notification'] == ('gpt-4.1-mini', 'openai')
        # Simple features use gpt-4.1-nano on openai
        assert premium['conv_app_select'] == ('gpt-4.1-nano', 'openai')
        # Vision features use gpt-4.1-mini on openai
        assert premium['openglass'] == ('gpt-4.1-mini', 'openai')
        # Free-text features use Gemini 2.5 Flash-Lite on gemini provider
        assert premium['session_titles'] == ('gemini-2.5-flash-lite', 'gemini')
        assert premium['followup'] == ('gemini-2.5-flash-lite', 'gemini')
        assert premium['onboarding'] == ('gemini-2.5-flash-lite', 'gemini')
        # Simple classification uses gpt-4.1-nano on openai
        assert premium['memory_category'] == ('gpt-4.1-nano', 'openai')
        assert premium['daily_summary_simple'] == ('gpt-4.1-nano', 'openai')
        assert premium['app_integration'] == ('gemini-2.5-flash-lite', 'gemini')
        assert premium['trends'] == ('gemini-2.5-flash-lite', 'gemini')
        # Anthropic & Perplexity with explicit provider
        assert premium['chat_agent'] == ('claude-sonnet-4-6', 'anthropic')
        assert premium['web_search'] == ('sonar-pro', 'perplexity')
        # Persona uses direct OpenAI API
        assert premium['persona_chat'] == ('gpt-4.1-nano', 'openai')
        assert premium['persona_chat_premium'] == ('gpt-5.4-mini', 'openai')

    def test_max_profile_models(self):
        """Max uses gpt-5.4 flagship, gpt-4.1-mini for cheap tasks, production-grade models."""
        max_prof = MODEL_QOS_PROFILES['max']
        # Flagship uses gpt-5.4 on openai
        assert max_prof['chat_responses'] == ('gpt-5.4', 'openai')
        assert max_prof['goals_advice'] == ('gpt-5.4', 'openai')
        assert max_prof['app_generator'] == ('gpt-5.4', 'openai')
        assert max_prof['conv_action_items'] == ('gpt-5.4', 'openai')
        assert max_prof['conv_structure'] == ('gpt-5.4', 'openai')
        assert max_prof['daily_summary'] == ('gpt-5.4', 'openai')
        assert max_prof['persona_clone'] == ('gpt-5.4', 'openai')
        assert max_prof['notifications'] == ('gpt-5.4', 'openai')
        # Cheap tasks use gpt-4.1-mini on openai
        assert max_prof['conv_app_select'] == ('gpt-4.1-mini', 'openai')
        assert max_prof['memories'] == ('gpt-4.1-mini', 'openai')
        assert max_prof['learnings'] == ('o4-mini', 'openai')
        assert max_prof['chat_graph'] == ('gpt-4.1', 'openai')
        # Persona uses direct OpenAI API
        assert max_prof['persona_chat'] == ('gpt-4.1-nano', 'openai')
        assert max_prof['persona_chat_premium'] == ('gpt-5.4-mini', 'openai')
        # OpenRouter for wrapped_analysis with explicit provider
        assert max_prof['wrapped_analysis'] == ('gemini-3-flash-preview', 'openrouter')
        # Anthropic & Perplexity with explicit provider
        assert max_prof['chat_agent'] == ('claude-sonnet-4-6', 'anthropic')
        assert max_prof['web_search'] == ('sonar-pro', 'perplexity')

    def test_max_profile_model_variants(self):
        """Max profile uses 9 distinct model IDs."""
        max_prof = MODEL_QOS_PROFILES['max']
        distinct_models = {model for model, _provider in max_prof.values()}
        expected = {
            'gpt-5.4',
            'gpt-4.1-mini',
            'gpt-4.1',
            'o4-mini',
            'gpt-4.1-nano',
            'gpt-5.4-mini',
            'claude-sonnet-4-6',
            'gemini-3-flash-preview',
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
        assert get_model('conv_action_items') == MODEL_QOS_PROFILES[_active_profile_name]['conv_action_items'][0]

    def test_unknown_feature_falls_back_to_gpt41_mini(self):
        assert get_model('totally_unknown_feature') == 'gpt-4.1-mini'

    def test_pinned_feature_ignores_profile(self):
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

    def test_cache_key_ignored_for_non_cacheable_model(self):
        # memories uses gpt-4.1-mini which is not in _CACHE_KEY_MODELS
        llm_with_key = get_llm('memories', cache_key='omi-test-key')
        llm_without_key = get_llm('memories')
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
        # Gemini features use gemini provider
        assert info['followup']['provider'] == 'gemini'

    def test_get_provider_matches_profile(self):
        """get_provider() returns the explicit provider from the profile."""
        assert get_provider('conv_action_items') == 'openai'
        assert get_provider('chat_agent') == 'anthropic'
        assert get_provider('web_search') == 'perplexity'
        assert get_provider('wrapped_analysis') == 'openrouter'
        assert get_provider('followup') == 'gemini'


class TestPinnedFeatures:
    """Verify pinned features are immutable."""

    def test_fair_use_pinned_to_gpt51(self):
        assert _PINNED_FEATURES['fair_use'] == ('gpt-5.1', 'openai')

    def test_pinned_survives_profile_switch(self):
        # Even if profile doesn't list fair_use, it should resolve to pinned value
        assert get_model('fair_use') == 'gpt-5.1'


class TestProviderClassification:
    """Verify provider routing from profile entries."""

    def test_chat_agent_is_anthropic_only(self):
        assert 'chat_agent' in _ANTHROPIC_ONLY_FEATURES

    def test_web_search_is_perplexity_only(self):
        assert 'web_search' in _PERPLEXITY_ONLY_FEATURES

    def test_persona_chat_uses_openai_in_both_profiles(self):
        """Persona chat features use direct OpenAI API in both profiles."""
        for profile_name in ['max', 'premium']:
            prof = MODEL_QOS_PROFILES[profile_name]
            assert prof['persona_chat'][1] == 'openai', f'{profile_name} persona_chat'
            assert prof['persona_chat_premium'][1] == 'openai', f'{profile_name} persona_chat_premium'

    def test_wrapped_analysis_uses_openrouter_in_both_profiles(self):
        """wrapped_analysis uses OpenRouter (gemini-3-flash-preview) in both profiles."""
        for profile_name in ['max', 'premium']:
            prof = MODEL_QOS_PROFILES[profile_name]
            assert prof['wrapped_analysis'][1] == 'openrouter', f'{profile_name} wrapped_analysis'

    def test_conv_features_are_openai(self):
        max_prof = MODEL_QOS_PROFILES['max']
        for feature in ['conv_action_items', 'conv_structure', 'conv_app_result', 'conv_app_select']:
            assert max_prof[feature][1] == 'openai'


class TestProviderSafetyGuard:
    """Verify get_llm() rejects Anthropic/Perplexity features and cross-provider overrides."""

    def test_get_llm_rejects_anthropic_only_feature(self):
        with pytest.raises(ValueError, match='Anthropic'):
            get_llm('chat_agent')

    def test_get_llm_rejects_perplexity_only_feature(self):
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


class TestRuntimeProviderRouting:
    """Verify get_llm() routes to correct client factory based on resolved model."""

    def test_persona_chat_routes_to_openai(self):
        """persona_chat uses direct OpenAI API — should route to OpenAI, not OpenRouter."""
        llm = get_llm('persona_chat')
        base_url = getattr(llm, 'openai_api_base', None) or ''
        assert 'openrouter' not in base_url

    def test_gemini_feature_routes_correctly(self):
        """Free-text features on gemini-2.5-flash-lite should route to Gemini (native SDK or fallback)."""
        llm = get_llm('followup')
        if os.environ.get('GEMINI_API_KEY'):
            from langchain_google_genai import ChatGoogleGenerativeAI

            assert isinstance(
                llm, ChatGoogleGenerativeAI
            ), f'followup should be ChatGoogleGenerativeAI, got {type(llm)}'
        else:
            # No key — falls back to ChatOpenAI placeholder pointing at Gemini endpoint
            assert hasattr(llm, 'invoke')

    def test_openglass_routes_to_openai(self):
        """openglass (vision) should route to OpenAI gpt-4.1-mini."""
        llm = get_llm('openglass')
        # get_llm() eagerly resolves; result is a ChatOpenAI routed to OpenAI
        base_url = getattr(llm, 'openai_api_base', None) or ''
        assert 'openrouter' not in base_url
        assert 'generativelanguage.googleapis.com' not in base_url

    def test_openrouter_temperature_applied_via_get_llm(self):
        """When get_llm routes to OpenRouter, _OPENROUTER_TEMPERATURES config is applied."""
        from utils.llm.clients import _OPENROUTER_TEMPERATURES

        llm = get_llm('wrapped_analysis')
        expected_temp = _OPENROUTER_TEMPERATURES.get('wrapped_analysis')
        assert expected_temp == 0.7, "wrapped_analysis should have temp 0.7 in config"
        assert llm.temperature == expected_temp, "get_llm should apply _OPENROUTER_TEMPERATURES"

    def test_openrouter_adds_vendor_prefix_for_gemini_models(self):
        """Profile stores bare model name; OpenRouter factory must add google/ prefix for API calls."""
        llm = get_llm('wrapped_analysis')
        default = getattr(llm, '_default', llm)
        assert default.model_name.startswith('google/'), f"Expected google/ prefix, got {default.model_name}"


class TestBYOKWrapperArchitecture:
    """Verify get_llm() eagerly resolves BYOK and returns proper ChatOpenAI instances."""

    def test_get_llm_returns_base_chat_model(self):
        """get_llm() must eagerly resolve BYOK and return a BaseChatModel (Runnable), not a wrapper."""
        from langchain_core.language_models import BaseChatModel
        from langchain_openai import ChatOpenAI

        # OpenAI feature — always ChatOpenAI
        llm_openai = get_llm('conv_structure')
        assert isinstance(llm_openai, ChatOpenAI), 'OpenAI get_llm must return ChatOpenAI'

        # Gemini feature — ChatGoogleGenerativeAI (with key) or ChatOpenAI fallback (no key)
        llm_gemini = get_llm('followup')
        assert isinstance(llm_gemini, BaseChatModel), 'Gemini get_llm must return BaseChatModel'

        # OpenRouter feature — always ChatOpenAI
        llm_or = get_llm('wrapped_analysis')
        assert isinstance(llm_or, ChatOpenAI), 'OpenRouter get_llm must return ChatOpenAI'

    def test_no_legacy_llm_medium_or_llm_large(self):
        """Dead legacy instances must not exist in clients module."""
        import utils.llm.clients as mod

        for name in [
            'llm_medium',
            'llm_large',
            'llm_high',
            'llm_agent',
            'llm_gemini_flash',
            'llm_mini_stream',
            'llm_medium_stream',
            'llm_large_stream',
            'llm_high_stream',
            'llm_agent_stream',
            'llm_medium_experiment',
        ]:
            assert not hasattr(mod, name), f'{name} should have been removed from clients.py'


class TestBYOKProfile:
    """Verify BYOK QoS profile structure and model selections."""

    def test_byok_all_openai_except_special(self):
        """byok routes all features to OpenAI except chat_agent/web_search/wrapped_analysis."""
        bk = MODEL_QOS_PROFILES['byok']
        for feature, (model, provider) in bk.items():
            if feature in ('chat_agent', 'web_search', 'wrapped_analysis'):
                continue
            assert provider == 'openai', f'byok {feature} should be openai, got {provider}'

    def test_byok_model_variants(self):
        """byok uses same 9 distinct models as max."""
        bk = MODEL_QOS_PROFILES['byok']
        distinct = {model for model, _p in bk.values()}
        expected = {
            'gpt-5.4',
            'gpt-5.4-mini',
            'gpt-4.1',
            'gpt-4.1-mini',
            'gpt-4.1-nano',
            'o4-mini',
            'claude-sonnet-4-6',
            'gemini-3-flash-preview',
            'sonar-pro',
        }
        assert distinct == expected

    def test_byok_has_same_features_as_premium(self):
        """BYOK profile must cover the same feature set as premium."""
        premium_features = set(MODEL_QOS_PROFILES['premium'].keys())
        byok_features = set(MODEL_QOS_PROFILES['byok'].keys())
        assert byok_features == premium_features, f'byok features differ: {byok_features ^ premium_features}'


class TestBYOKProfileFixed:
    """Verify BYOK QoS profile is always 'byok'."""

    def test_byok_profile_is_byok(self):
        assert _byok_profile_name == 'byok'

    def test_byok_profile_exists(self):
        assert _byok_profile is not None
        assert _byok_profile is MODEL_QOS_PROFILES['byok']

    def test_byok_profile_via_subprocess(self):
        """Verify byok is set regardless of MODEL_QOS value."""
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
                    "os.environ['MODEL_QOS']='max'; "
                    "from utils.llm.clients import _byok_profile_name, _byok_profile; "
                    "assert _byok_profile_name == 'byok', f'Expected byok, got {_byok_profile_name}'; "
                    "assert _byok_profile is not None"
                ),
            ],
            capture_output=True,
            text=True,
            cwd=str(os.path.join(os.path.dirname(__file__), '..', '..')),
        )
        assert result.returncode == 0, f"byok profile test failed: {result.stderr}"


class TestEffectiveBYOKProvider:
    """Verify _effective_byok_provider maps providers correctly."""

    def test_openai_passthrough(self):
        assert _effective_byok_provider('gpt-4.1-mini', 'openai') == 'openai'

    def test_gemini_passthrough(self):
        assert _effective_byok_provider('gemini-2.5-flash', 'gemini') == 'gemini'

    def test_openrouter_gemini_maps_to_gemini(self):
        assert _effective_byok_provider('gemini-3-flash-preview', 'openrouter') == 'gemini'

    def test_openrouter_non_gemini_stays_openrouter(self):
        assert _effective_byok_provider('anthropic/claude-3.5-sonnet', 'openrouter') == 'openrouter'

    def test_anthropic_passthrough(self):
        assert _effective_byok_provider('claude-sonnet-4-6', 'anthropic') == 'anthropic'

    def test_perplexity_passthrough(self):
        assert _effective_byok_provider('sonar-pro', 'perplexity') == 'perplexity'


class TestStructuredOutputFeatureTracking:
    """Verify structured output feature set matches actual usage."""

    def test_expected_features_tracked(self):
        expected = {'chat_extraction', 'proactive_notification', 'conv_app_select', 'external_structure', 'trends'}
        assert _STRUCTURED_OUTPUT_FEATURES == expected

    def test_tracked_features_exist_in_all_profiles(self):
        for feature in _STRUCTURED_OUTPUT_FEATURES:
            for profile_name, profile in MODEL_QOS_PROFILES.items():
                assert feature in profile, f'{feature} missing from {profile_name}'

    def test_premium_gemini_structured_output(self):
        """In premium profile, only 'trends' uses structured_output on Gemini."""
        premium = MODEL_QOS_PROFILES['premium']
        gemini_so = {f for f in _STRUCTURED_OUTPUT_FEATURES if premium[f][1] == 'gemini'}
        assert gemini_so == {'trends'}, f'Expected only trends on Gemini SO in premium, got {gemini_so}'

    def test_byok_no_gemini_structured_output(self):
        """BYOK profile routes all structured output features to OpenAI (no Gemini compat risk)."""
        profile = MODEL_QOS_PROFILES['byok']
        for feature in _STRUCTURED_OUTPUT_FEATURES:
            assert profile[feature][1] == 'openai', f'byok {feature} should be openai, got {profile[feature][1]}'
