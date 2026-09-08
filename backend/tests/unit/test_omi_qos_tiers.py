"""Tests for Model QoS profile system in utils/llm/clients.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from utils.llm.model_config import UnknownLLMFeature

# ---------------------------------------------------------------------------
# Isolated load of utils.llm.clients against in-memory langchain stubs.
# Stubs live only inside the module fixture (never at import/collection).
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Names previously imported at module top from utils.llm.clients. Bound from the
# freshly loaded module object inside `_qos_isolated_clients` so tests keep using
# the same bare names without seeing a process-global clients import.
_CLIENTS_EXPORTS = (
    'MODEL_QOS_PROFILES',
    '_ANTHROPIC_ONLY_FEATURES',
    '_PERPLEXITY_ONLY_FEATURES',
    '_PINNED_FEATURES',
    '_STRUCTURED_OUTPUT_FEATURES',
    '_active_profile',
    '_active_profile_name',
    '_byok_profile',
    '_byok_profile_name',
    '_effective_byok_provider',
    '_get_or_create_gemini_llm',
    '_get_or_create_openai_llm',
    '_get_or_create_openrouter_llm',
    '_llm_cache',
    'get_llm',
    'get_model',
    'get_provider',
    'get_qos_info',
    'supports_cache_retention',
    'supports_prompt_cache',
)

_STUB_LEAK_NAMES = (
    'langchain_core',
    'langchain_openai',
    'anthropic',
    'tiktoken',
    'utils.byok',
    'firebase_admin',
)


class _BaseCallbackHandler:
    pass


class _LLMResult:
    pass


class _BaseChatModel:
    def invoke(self, *_args, **_kwargs):
        return MagicMock()

    async def ainvoke(self, *_args, **_kwargs):
        return MagicMock()

    def stream(self, *_args, **_kwargs):
        return iter(())

    def with_structured_output(self, *_args, **_kwargs):
        return self

    def bind(self, **kwargs):
        bound = self.__class__(**self._constructor_kwargs)
        bound.bound_kwargs = kwargs
        return bound


class _ChatOpenAI(_BaseChatModel):
    def __init__(self, **kwargs):
        self._constructor_kwargs = dict(kwargs)
        self.model_name = kwargs.get('model')
        self.model = self.model_name
        self.temperature = kwargs.get('temperature')
        self.openai_api_base = kwargs.get('base_url', '')


class _ChatGoogleGenerativeAI(_BaseChatModel):
    def __init__(self, **kwargs):
        self._constructor_kwargs = dict(kwargs)
        self.model_name = kwargs.get('model')
        self.model = self.model_name


class _ChatAnthropic(_BaseChatModel):
    def __init__(self, **kwargs):
        self._constructor_kwargs = dict(kwargs)
        self.model_name = kwargs.get('model')
        self.model = self.model_name


class _OpenAIEmbeddings:
    def __init__(self, **_kwargs):
        pass

    def embed_query(self, _text):
        return [0.0]

    def embed_documents(self, texts):
        return [[0.0] for _text in texts]


class _PydanticOutputParser:
    def __init__(self, **kwargs):
        self.pydantic_object = kwargs.get('pydantic_object')


class _Encoding:
    def encode(self, text):
        return list(text)


class _AsyncAnthropic:
    def __init__(self, **_kwargs):
        pass


def _stub_mod(name: str, **attrs) -> ModuleType:
    module = ModuleType(name)
    for attr, value in attrs.items():
        setattr(module, attr, value)
    return module


def _stub_pkg(name: str) -> AutoMockModule:
    module = AutoMockModule(name)
    module.__path__ = []  # type: ignore[attr-defined]
    return module


def _qos_fakes() -> dict[str, ModuleType | None]:
    tiktoken_mod = _stub_mod('tiktoken')
    tiktoken_mod.encoding_for_model = MagicMock(return_value=_Encoding())
    byok = _stub_mod(
        'utils.byok',
        get_byok_key=MagicMock(return_value=None),
        get_byok_llm_provider=MagicMock(return_value=None),
        get_byok_uid=MagicMock(return_value=None),
    )
    return {
        'anthropic': _stub_mod('anthropic', AsyncAnthropic=_AsyncAnthropic),
        'langchain_core': _stub_pkg('langchain_core'),
        'langchain_core.callbacks': _stub_mod('langchain_core.callbacks', BaseCallbackHandler=_BaseCallbackHandler),
        'langchain_core.outputs': _stub_mod('langchain_core.outputs', LLMResult=_LLMResult),
        'langchain_core.language_models': _stub_mod('langchain_core.language_models', BaseChatModel=_BaseChatModel),
        'langchain_core.output_parsers': _stub_mod(
            'langchain_core.output_parsers', PydanticOutputParser=_PydanticOutputParser
        ),
        'langchain_openai': _stub_mod('langchain_openai', ChatOpenAI=_ChatOpenAI, OpenAIEmbeddings=_OpenAIEmbeddings),
        'langchain_google_genai': _stub_mod('langchain_google_genai', ChatGoogleGenerativeAI=_ChatGoogleGenerativeAI),
        'langchain_anthropic': _stub_mod('langchain_anthropic', ChatAnthropic=_ChatAnthropic),
        'tiktoken': tiktoken_mod,
        'utils.byok': byok,
        'firebase_admin': _stub_pkg('firebase_admin'),
        'firebase_admin.firestore': AutoMockModule('firebase_admin.firestore'),
        'google.cloud.firestore': AutoMockModule('google.cloud.firestore'),
        'google.cloud.firestore_v1': AutoMockModule('google.cloud.firestore_v1'),
        'google.cloud.firestore_v1.base_query': AutoMockModule('google.cloud.firestore_v1.base_query'),
        'database._client': AutoMockModule('database._client'),
        'database.llm_usage': AutoMockModule('database.llm_usage'),
        # Reload against the langchain stubs above; a cached real providers/usage_tracker
        # would keep the real ChatOpenAI class and break isinstance checks vs stubs.
        'utils.llm.providers': None,
        'utils.llm.usage_tracker': None,
    }


def _module_has_file(mod: object) -> bool:
    file_attr = getattr(mod, '__file__', None)
    return isinstance(file_attr, str) and bool(file_attr)


def _assert_no_qos_stub_leak(prior: dict[str, ModuleType | None]) -> None:
    """After teardown, named deps are restored; no *new* fileless stubs remain.

    ``tests/conftest.py`` installs a ``tiktoken`` ModuleType stub (no ``__file__``)
    for the whole session. Restoring that exact object is not a leak from this file.
    """
    leaked = []
    for name in _STUB_LEAK_NAMES:
        mod = sys.modules.get(name)
        expected = prior.get(name)
        if mod is not expected:
            leaked.append(
                f'{name} not restored (was {type(expected).__name__ if expected else None}, '
                f'now {type(mod).__name__ if mod else None})'
            )
            continue
        if mod is None or _module_has_file(mod):
            continue
        if expected is not None and not _module_has_file(expected):
            continue
        leaked.append(f'{name} ({type(mod).__name__})')
    assert not leaked, f'stub modules leaked into sys.modules: {", ".join(leaked)}'


def _clients_subprocess_script(assertion: str) -> str:
    lines = [
        "import os",
        "import sys",
        "from unittest.mock import MagicMock",
        "for module_name in [",
        "    'anthropic',",
        "    'cachetools',",
        "    'firebase_admin',",
        "    'firebase_admin.firestore',",
        "    'google.cloud.firestore',",
        "    'google.cloud.firestore_v1',",
        "    'google.cloud.firestore_v1.base_query',",
        "    'langchain_core',",
        "    'langchain_core.callbacks',",
        "    'langchain_core.language_models',",
        "    'langchain_core.output_parsers',",
        "    'langchain_core.outputs',",
        "    'langchain_google_genai',",
        "    'langchain_anthropic',",
        "    'langchain_openai',",
        "    'tiktoken',",
        "    'database',",
        "    'database._client',",
        "    'database.llm_usage',",
        "    'models.structured_extraction',",
        "    'prometheus_client',",
        "]:",
        "    sys.modules.setdefault(module_name, MagicMock())",
        "os.environ['OPENAI_API_KEY'] = 'sk-test'",
        "os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-test'",
        *assertion.splitlines(),
    ]
    return "\n".join(lines) + "\n"


@pytest.fixture(scope='module', autouse=True)
def _qos_isolated_clients():
    """Load ``utils.llm.clients`` fresh against langchain stubs; restore sys.modules after.

    Yield stays inside ``stub_modules`` so in-test ``from langchain_openai import ChatOpenAI``
    and ``import utils.llm.clients`` see the stub/fresh objects. Teardown restores the
    process so later-collected files never observe a bare ``langchain_core`` package.
    """
    os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-key-for-unit-tests')
    os.environ.setdefault('ANTHROPIC_API_KEY', 'sk-ant-test-fake-key')
    prior = {name: sys.modules.get(name) for name in _STUB_LEAK_NAMES}
    with stub_modules(_qos_fakes()):
        clients = load_module_fresh(
            'utils.llm.clients',
            os.path.join(str(BACKEND_DIR), 'utils', 'llm', 'clients.py'),
        )
        g = globals()
        for name in _CLIENTS_EXPORTS:
            g[name] = getattr(clients, name)
        yield clients
    _assert_no_qos_stub_leak(prior)


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
            assert 'perplexity' in providers, f'{profile_name} missing Perplexity models'
            assert 'openrouter' in providers, f'{profile_name} should have OpenRouter (wrapped_analysis)'
        # OpenAI-based profiles must have OpenAI provider
        for name in ('premium', 'max', 'byok'):
            providers = {p for _m, p in MODEL_QOS_PROFILES[name].values()}
            assert 'openai' in providers, f'{name} missing OpenAI models'
        # Premium profile must have Gemini provider
        providers = {p for _m, p in MODEL_QOS_PROFILES['premium'].values()}
        assert 'gemini' in providers, 'premium should have Gemini direct models'

    def test_all_profiles_use_the_authorized_two_tier_openai_map(self):
        luna_features = {
            'conv_action_items',
            'wake_word_adjudication',
            'conv_structure',
            'conv_app_result',
            'daily_summary',
            'external_structure',
            'memories',
            'x_memory_extraction_flex',
            'learnings',
            'memory_conflict',
            'memory_conflict_flex',
            'knowledge_graph',
            'memory_l1',
            'memory_l2',
            'memory_l2_flex',
            'chat_responses',
            'chat_extraction',
            'chat_graph',
            'goals',
            'goals_advice',
            'notifications',
            'proactive_notification',
            'what_matters_now',
            'openglass',
            'app_generator',
            'persona_clone',
            'persona_chat_premium',
            'desktop_proactive_reasoning',
            'file_chat_vision',
            'file_chat_documents',
            'chat_agent',
        }
        nano_features = {
            'conv_app_select',
            'conv_folder',
            'conv_discard',
            'daily_summary_simple',
            'memory_category',
            'smart_glasses',
            'persona_chat',
            'desktop_proactive_extraction',
        }
        expected_openai = {
            **{feature: ('gpt-5.6-luna', 'openai') for feature in luna_features},
            **{feature: ('gpt-5-nano', 'openai') for feature in nano_features},
        }

        for profile_name, profile in MODEL_QOS_PROFILES.items():
            openai_routes = {feature: route for feature, route in profile.items() if route[1] == 'openai'}
            assert openai_routes == expected_openai, f'{profile_name} OpenAI routes differ from the two-tier map'

        premium = MODEL_QOS_PROFILES['premium']
        assert premium['session_titles'] == ('gemini-2.5-flash-lite', 'gemini')
        assert premium['followup'] == ('gemini-2.5-flash-lite', 'gemini')
        assert premium['onboarding'] == ('gemini-2.5-flash-lite', 'gemini')
        assert premium['app_integration'] == ('gemini-2.5-flash-lite', 'gemini')
        assert premium['trends'] == ('gemini-2.5-flash-lite', 'gemini')
        assert premium['chat_agent'] == ('gpt-5.6-luna', 'openai')
        assert premium['web_search'] == ('sonar-pro', 'perplexity')

    def test_max_profile_model_variants(self):
        """Max profile is constrained to the two approved OpenAI text models."""
        max_prof = MODEL_QOS_PROFILES['max']
        distinct_models = {model for model, _provider in max_prof.values()}
        expected = {
            'gpt-5.6-luna',
            'gpt-5-nano',
            'gemini-2.5-flash-lite',
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
            'wake_word_adjudication',
        ]
        for feature in new_features:
            for profile_name, profile in MODEL_QOS_PROFILES.items():
                assert feature in profile, f'{feature} missing from {profile_name}'


class TestGetModel:
    """Verify get_model() resolution: pinned > env override > profile. Unknown features raise."""

    def test_returns_profile_default(self):
        assert get_model('conv_action_items') == MODEL_QOS_PROFILES[_active_profile_name]['conv_action_items'][0]

    def test_unknown_feature_falls_back_to_luna(self):
        """Fail closed: never a silent fall-through to luna."""
        with pytest.raises(UnknownLLMFeature):
            get_model('totally_unknown_feature')

    def test_pinned_feature_ignores_profile(self):
        assert get_model('fair_use') == 'gpt-5.6-luna'

    def test_chat_agent_returns_luna(self):
        model = get_model('chat_agent')
        assert model == 'gpt-5.6-luna'

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
        # Both use Luna in the two-tier premium profile.
        llm1 = get_llm('memories')
        llm2 = get_llm('goals')
        assert llm1 is llm2

    def test_different_models_return_different_instances(self):
        llm1 = get_llm('memories')
        llm2 = get_llm('persona_chat')
        assert llm1 is not llm2

    def test_foreground_timeout_does_not_share_cached_client(self):
        # Both resolve to Luna in premium, but conv_structure carries
        # FOREGROUND_REQUEST_TIMEOUT_SECONDS and request_timeout is part of the
        # client cache key.
        llm1 = get_llm('memories')
        llm2 = get_llm('conv_structure')
        assert llm1 is not llm2

    def test_streaming_returns_different_instance(self):
        llm = get_llm('conv_action_items')
        llm_stream = get_llm('conv_action_items', streaming=True)
        assert llm is not llm_stream

    def test_persona_chat_returns_client(self):
        # persona_chat is gpt-5-nano (OpenAI) in all profiles.
        llm = get_llm('persona_chat', streaming=True)
        assert hasattr(llm, 'invoke')

    def test_cache_key_applied_for_cacheable_model(self):
        # conv_structure uses Luna, which supports prompt-cache routing.
        llm_with_key = get_llm('conv_structure', cache_key='omi-test-key')
        llm_without_key = get_llm('conv_structure')
        assert llm_with_key is not llm_without_key
        assert hasattr(llm_with_key, 'invoke')

    def test_cache_key_ignored_for_non_cacheable_model(self):
        # followup uses Gemini in the premium profile, which does not support OpenAI prompt_cache_key.
        llm_with_key = get_llm('followup', cache_key='omi-test-key')
        llm_without_key = get_llm('followup')
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

    @pytest.mark.parametrize('model_name', ['gpt-5.1', 'gpt-4.1-mini'])
    def test_openai_constructor_applies_cache_retention_by_capability(self, model_name):
        """The production constructor receives retention only for supported model families."""
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
                _get_or_create_openai_llm(model_name)

            if supports_cache_retention(model_name):
                assert captured_kwargs['extra_body'] == {"prompt_cache_retention": "24h"}
            else:
                assert 'extra_body' not in captured_kwargs
            assert 'prompt_cache_key' not in captured_kwargs.get('model_kwargs', {})
        finally:
            _llm_cache.clear()
            _llm_cache.update(saved)

    def test_explicit_cache_options_are_sent_in_extra_body_without_a_cache_key(self):
        """Explicit mode reaches the wire even when the request opts out of cache writes."""
        from unittest.mock import patch as _patch

        import utils.llm.clients as clients_mod

        captured: dict = {}

        class _Recorder:
            def bind(self, **kwargs):
                captured.update(kwargs)
                return self

        options = {'mode': 'explicit', 'ttl': '30m'}
        with _patch.object(clients_mod, 'should_route_features_through_gateway', return_value=True), _patch.object(
            clients_mod, 'get_or_create_omi_gateway_llm', return_value=_Recorder()
        ), _patch.object(clients_mod, 'maybe_wrap_dev_gateway_shadow', return_value=_Recorder()):
            clients_mod.get_llm('conv_structure', prompt_cache_options=options)

        assert 'prompt_cache_options' not in captured, 'must not be bound as a named argument'
        assert captured['extra_body'] == {'prompt_cache_options': options}

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
        assert supports_prompt_cache('gpt-5.6-luna')
        assert not supports_cache_retention('gpt-5.6-luna')
        assert not supports_prompt_cache('claude-sonnet-4-6')


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
        assert info['chat_agent']['provider'] == 'openai'
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
        assert get_provider('chat_agent') == 'openai'
        assert get_provider('web_search') == 'perplexity'
        assert get_provider('wrapped_analysis') == 'openrouter'
        assert get_provider('followup') == 'gemini'


class TestPinnedFeatures:
    """Verify pinned features are immutable."""

    def test_fair_use_pinned_to_luna(self):
        assert _PINNED_FEATURES['fair_use'] == ('gpt-5.6-luna', 'openai')

    def test_pinned_survives_profile_switch(self):
        # Even if profile doesn't list fair_use, it should resolve to pinned value
        assert get_model('fair_use') == 'gpt-5.6-luna'


class TestProviderClassification:
    """Verify provider routing from profile entries."""

    def test_chat_agent_is_not_anthropic_only(self):
        assert 'chat_agent' not in _ANTHROPIC_ONLY_FEATURES
        assert _ANTHROPIC_ONLY_FEATURES == set()

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

    def test_get_llm_accepts_chat_agent(self):
        llm = get_llm('chat_agent')
        assert hasattr(llm, 'invoke')

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
                sys.executable,
                '-c',
                _clients_subprocess_script(
                    "os.environ['MODEL_QOS'] = 'premium'\n"
                    "from utils.llm.clients import _active_profile_name\n"
                    "assert _active_profile_name == 'premium', f'Expected premium, got {_active_profile_name}'"
                ),
            ],
            capture_output=True,
            text=True,
            cwd=str(BACKEND_DIR),
        )
        assert result.returncode == 0, f"premium profile test failed: {result.stderr}"

    def test_invalid_profile_falls_back_to_premium(self):
        """MODEL_QOS=bogus should fall back to premium profile."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                '-c',
                _clients_subprocess_script(
                    "os.environ['MODEL_QOS'] = 'bogus'\n"
                    "from utils.llm.clients import _active_profile_name\n"
                    "assert _active_profile_name == 'premium', "
                    "f'Expected premium fallback, got {_active_profile_name}'"
                ),
            ],
            capture_output=True,
            text=True,
            cwd=str(BACKEND_DIR),
        )
        assert result.returncode == 0, f"invalid profile fallback test failed: {result.stderr}"


class TestExpandedCallsiteCoverage:
    """Verify all wired files use get_llm/get_model with correct feature keys."""

    def _read_source(self, rel_path: str) -> str:
        from pathlib import Path

        backend_dir = Path(__file__).resolve().parent.parent.parent
        return (backend_dir / rel_path).read_text(encoding='utf-8')

    def test_conversation_processing_all_keys(self):
        import re

        source = self._read_source("utils/llm/conversation_processing.py")
        calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
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
        calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
        for key in ['memories', 'learnings', 'memory_category', 'memory_conflict']:
            assert key in calls, f"Missing get_llm('{key}') in memories.py"
        # 4th call site: the daily-sweep summary agent reuses the same memories QoS route.
        assert calls.count('memories') == 4, "memories should appear exactly four times"

    def test_knowledge_graph_all_keys(self):
        import re

        source = self._read_source("utils/llm/knowledge_graph.py")
        calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
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
        calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
        assert 'chat_responses' in calls
        assert 'chat_extraction' in calls

    def test_persona_py_all_keys(self):
        import re

        source = self._read_source("utils/llm/persona.py")
        calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
        assert 'persona_clone' in calls
        assert calls.count('persona_clone') >= 4, "persona_clone should appear in multiple clone functions"
        # Dynamic persona_chat/persona_chat_premium routing via feature variable
        assert "get_llm(feature" in source, "persona.py should pass dynamic feature for chat routing"

    def test_goals_py_all_keys(self):
        import re

        source = self._read_source("utils/llm/goals.py")
        calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
        assert 'goals' in calls, "Missing get_llm('goals') in goals.py"
        assert 'goals_advice' in calls, "Missing get_llm('goals_advice') in goals.py"

    def test_notifications_py_key(self):
        import re

        source = self._read_source("utils/llm/notifications.py")
        calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
        assert 'notifications' in calls

    def test_app_generator_py_all_keys(self):
        import re

        source = self._read_source("utils/llm/app_generator.py")
        calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
        assert 'app_generator' in calls
        assert 'app_integration' in calls
        assert calls.count('app_integration') >= 2, "app_integration should appear in multiple functions"

    def test_graph_py_key(self):
        import re

        source = self._read_source("utils/retrieval/graph.py")
        calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
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
        calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
        assert 'external_structure' in calls
        assert calls.count('external_structure') >= 2, "external_structure should appear at least twice"
        assert 'daily_summary_simple' in calls, "Missing get_llm('daily_summary_simple') in external_integrations.py"
        assert 'daily_summary' in calls, "Missing get_llm('daily_summary') in external_integrations.py"

    def test_proactive_notification_key(self):
        import re

        source = self._read_source("utils/llm/proactive_notification.py")
        calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
        assert 'proactive_notification' in calls
        assert calls.count('proactive_notification') >= 4, "proactive_notification should appear in 4 functions"

    def test_generate_2025_key(self):
        import re

        source = self._read_source("utils/wrapped/generate_2025.py")
        calls = re.findall(r"get_llm\(\s*'(\w+)'", source)
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
        """openglass (vision) should route to OpenAI Luna."""
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


class TestBYOKEmbeddingsProxy:
    def test_model_access_403_falls_back_to_default_embeddings(self, monkeypatch):
        """BYOK OpenAI projects can reject text-embedding-3-large with model_not_found."""
        import utils.llm.clients as mod

        class _FailingBYOKEmbeddings:
            def embed_documents(self, _texts):
                raise RuntimeError(
                    "openai.PermissionDeniedError: Error code: 403 - project does not have access "
                    "to model text-embedding-3-large; code: model_not_found"
                )

            def embed_query(self, _text):
                raise RuntimeError(
                    "openai.PermissionDeniedError: Error code: 403 - project does not have access "
                    "to model text-embedding-3-large; code: model_not_found"
                )

        default = MagicMock()
        default.embed_documents.return_value = [[0.1, 0.2]]
        default.embed_query.return_value = [0.1, 0.2]

        monkeypatch.setattr(mod, 'get_byok_key', lambda provider: 'sk-byok' if provider == 'openai' else None)
        monkeypatch.setattr(mod, 'OpenAIEmbeddings', lambda **_kwargs: _FailingBYOKEmbeddings())
        mod._openai_cache.clear()

        proxy = mod._OpenAIEmbeddingsProxy(
            model='text-embedding-3-large',
            default=default,
            ctor_kwargs={},
        )

        assert proxy.embed_documents(['hello']) == [[0.1, 0.2]]
        assert proxy.embed_query('hello') == [0.1, 0.2]
        default.embed_documents.assert_called_once_with(['hello'])
        default.embed_query.assert_called_once_with('hello')


class TestBYOKProfile:
    """Verify BYOK QoS profile structure and model selections."""

    def test_byok_all_openai_except_special(self):
        """BYOK preserves the non-OpenAI specialty routes from the common profile."""
        bk = MODEL_QOS_PROFILES['byok']
        for feature, (model, provider) in bk.items():
            if feature in (
                'web_search',
                'wrapped_analysis',
                'translation',
                'session_titles',
                'followup',
                'onboarding',
                'app_integration',
                'trends',
                'screen_frame_judge',
            ):
                continue
            assert provider == 'openai', f'byok {feature} should be openai, got {provider}'

    def test_byok_model_variants(self):
        """BYOK uses the same constrained model set as max."""
        bk = MODEL_QOS_PROFILES['byok']
        distinct = {model for model, _p in bk.values()}
        expected = {
            'gpt-5.6-luna',
            'gpt-5-nano',
            'gemini-2.5-flash-lite',
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
                sys.executable,
                '-c',
                _clients_subprocess_script(
                    "os.environ['MODEL_QOS'] = 'max'\n"
                    "from utils.llm.clients import _byok_profile_name, _byok_profile\n"
                    "assert _byok_profile_name == 'byok', f'Expected byok, got {_byok_profile_name}'\n"
                    "assert _byok_profile is not None"
                ),
            ],
            capture_output=True,
            text=True,
            cwd=str(BACKEND_DIR),
        )
        assert result.returncode == 0, f"byok profile test failed: {result.stderr}"


class TestEffectiveBYOKProvider:
    """Verify _effective_byok_provider maps providers correctly."""

    def test_openai_passthrough(self):
        assert _effective_byok_provider('gpt-4.1-mini', 'openai') == 'openai'

    def test_gemini_passthrough(self):
        assert _effective_byok_provider('gemini-2.5-flash', 'gemini') == 'gemini'

    def test_openrouter_gemini_uses_openrouter_key(self):
        assert _effective_byok_provider('gemini-3-flash-preview', 'openrouter') == 'openrouter'

    def test_openrouter_non_gemini_stays_openrouter(self):
        assert _effective_byok_provider('anthropic/claude-3.5-sonnet', 'openrouter') == 'openrouter'

    def test_anthropic_passthrough(self):
        assert _effective_byok_provider('claude-sonnet-4-6', 'anthropic') == 'anthropic'

    def test_perplexity_passthrough(self):
        assert _effective_byok_provider('sonar-pro', 'perplexity') == 'perplexity'


class TestStructuredOutputFeatureTracking:
    """Verify structured output feature set matches actual usage."""

    def test_expected_features_tracked(self):
        expected = {
            'chat_extraction',
            'proactive_notification',
            'desktop_proactive_extraction',
            'desktop_proactive_reasoning',
            'translation',
            'conv_app_select',
            'external_structure',
            'screen_frame_judge',
            'trends',
            'what_matters_now',
        }
        assert _STRUCTURED_OUTPUT_FEATURES == expected

    def test_tracked_features_exist_in_all_profiles(self):
        for feature in _STRUCTURED_OUTPUT_FEATURES:
            for profile_name, profile in MODEL_QOS_PROFILES.items():
                assert feature in profile, f'{feature} missing from {profile_name}'

    def test_premium_gemini_structured_output(self):
        """In premium profile, translation, trends, and screen_frame_judge use structured output on Gemini."""
        premium = MODEL_QOS_PROFILES['premium']
        gemini_so = {f for f in _STRUCTURED_OUTPUT_FEATURES if premium[f][1] == 'gemini'}
        assert gemini_so == {
            'translation',
            'trends',
            'screen_frame_judge',
        }, f'Expected translation, trends, and screen_frame_judge on Gemini SO in premium, got {gemini_so}'

    def test_byok_no_gemini_structured_output(self):
        """BYOK routes structured output to OpenAI except managed translation/trends/screen_frame_judge."""
        profile = MODEL_QOS_PROFILES['byok']
        for feature in _STRUCTURED_OUTPUT_FEATURES:
            if feature in {'translation', 'trends', 'screen_frame_judge'}:
                assert profile[feature] == ('gemini-2.5-flash-lite', 'gemini')
                continue
            assert profile[feature][1] == 'openai', f'byok {feature} should be openai, got {profile[feature][1]}'


class TestGeminiThinkingBudget:
    """thinking_budget is a native google-genai SDK param — it must never reach the OpenAI-compat fallback.

    Regression for the pusher crash: pusher has no GEMINI_API_KEY/USE_VERTEX_AI, so the Gemini client
    resolves to the ChatOpenAI OpenAI-compat fallback. Passing thinking_budget there leaks it into
    model_kwargs and crashes at invoke ("Completions.parse() got an unexpected keyword argument
    'thinking_budget'"), disabling trends/memory-discard for all users.
    """

    def test_openai_compat_fallback_omits_thinking_budget(self):
        from unittest.mock import patch as _patch

        saved = dict(_llm_cache)
        _llm_cache.clear()
        captured = {}

        def fake_openai(*args, **kwargs):
            captured.update(kwargs)
            return MagicMock()

        try:
            with _patch.dict(os.environ, {'GEMINI_API_KEY': '', 'USE_VERTEX_AI': ''}), _patch(
                'utils.llm.clients.ChatOpenAI', side_effect=fake_openai
            ), _patch('utils.llm.clients.ChatGoogleGenerativeAI', side_effect=lambda *a, **k: MagicMock()):
                _get_or_create_gemini_llm('gemini-2.5-flash-lite', thinking_budget=0)
            assert 'thinking_budget' not in captured, 'thinking_budget must not reach the ChatOpenAI fallback'
        finally:
            _llm_cache.clear()
            _llm_cache.update(saved)

    def test_native_gemini_receives_thinking_budget(self):
        from unittest.mock import patch as _patch

        saved = dict(_llm_cache)
        _llm_cache.clear()
        captured = {}

        def fake_genai(*args, **kwargs):
            captured.update(kwargs)
            return MagicMock()

        try:
            with _patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key', 'USE_VERTEX_AI': ''}), _patch(
                'utils.llm.providers.ChatGoogleGenerativeAI', side_effect=fake_genai
            ), _patch('utils.llm.providers.ChatOpenAI', side_effect=lambda *a, **k: MagicMock()):
                _get_or_create_gemini_llm('gemini-2.5-flash-lite', thinking_budget=0)
            assert captured.get('thinking_budget') == 0, 'native ChatGoogleGenerativeAI must receive thinking_budget'
        finally:
            _llm_cache.clear()
            _llm_cache.update(saved)

    def test_non_25_model_omits_thinking_budget(self):
        from unittest.mock import patch as _patch

        saved = dict(_llm_cache)
        _llm_cache.clear()
        captured = {}

        def fake_genai(*args, **kwargs):
            captured.update(kwargs)
            return MagicMock()

        try:
            with _patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key', 'USE_VERTEX_AI': ''}), _patch(
                'utils.llm.providers.ChatGoogleGenerativeAI', side_effect=fake_genai
            ), _patch('utils.llm.providers.ChatOpenAI', side_effect=lambda *a, **k: MagicMock()):
                _get_or_create_gemini_llm('gemini-3-flash-preview', thinking_budget=0)
            assert 'thinking_budget' not in captured, 'thinking_budget only applies to gemini-2.5* models'
        finally:
            _llm_cache.clear()
            _llm_cache.update(saved)

    def test_structured_output_route_omits_thinking_budget(self):
        from utils.llm.model_config import get_route_options

        opts = get_route_options('trends', 'gemini-2.5-flash-lite', 'gemini')
        assert 'thinking_budget' not in opts

    def test_non_structured_gemini_route_sets_thinking_budget_zero(self):
        from utils.llm.model_config import get_route_options

        opts = get_route_options('chat', 'gemini-2.5-flash-lite', 'gemini')
        assert opts.get('thinking_budget') == 0
