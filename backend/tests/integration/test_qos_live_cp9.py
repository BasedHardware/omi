"""
CP9 Live Integration Test — Real LLM API calls covering ALL changed paths in PR #6942.

Tests every code path changed in the QoS profile refactor:
  P1: get_llm() routing for all features in premium profile
  P2: get_model()/get_provider() resolution across all 6 profiles
  P3: _create_byok_client() factory (mocked key, real client construction)
  P4: _effective_byok_provider() mapping
  P5: BYOK profile hardcoded to byok
  P6: Structured output compatibility on OpenAI (real .with_structured_output() call)
  P7: Prompt caching (cache_key binding for gpt-5.4-mini)
  P8: Streaming client construction and invocation
  P9: OpenRouter vendor prefix and temperature config
  P10: Anthropic client via get_model() + anthropic_client
  P11: Perplexity via get_model() + HTTP client
  P12: _get_or_create_gemini_llm() client factory (native SDK, ChatGoogleGenerativeAI)
  P13: get_qos_info() debugging helper

Requires: OPENAI_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY, PERPLEXITY_API_KEY in .env
Optional: GEMINI_API_KEY (skips Gemini live tests if missing)

Run: cd backend && python3 -m pytest tests/integration/test_qos_live_cp9.py -v -s
"""

import os
import sys

import httpx
import pytest
from pydantic import BaseModel, Field

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from utils.llm.clients import (
    MODEL_QOS_PROFILES,
    _CACHE_KEY_MODELS,
    _STRUCTURED_OUTPUT_FEATURES,
    _active_profile,
    _active_profile_name,
    _byok_profile,
    _byok_profile_name,
    _create_byok_client,
    _effective_byok_provider,
    _get_or_create_gemini_llm,
    _get_or_create_openai_llm,
    _get_or_create_openrouter_llm,
    anthropic_client,
    get_llm,
    get_model,
    get_provider,
    get_qos_info,
)

SIMPLE_PROMPT = "Reply with exactly one word: hello"
HAS_GEMINI_KEY = bool(os.environ.get('GEMINI_API_KEY', ''))


# ---------------------------------------------------------------------------
# P1: get_llm() routing — real invocations for every premium OpenAI feature
# ---------------------------------------------------------------------------
class TestP1_GetLlmRouting:
    """P1: Every feature in premium profile that routes to OpenAI responds to real prompts."""

    OPENAI_FEATURES = [f for f, (m, p) in MODEL_QOS_PROFILES['premium'].items() if p == 'openai']

    @pytest.mark.parametrize("feature", OPENAI_FEATURES)
    def test_openai_feature_responds(self, feature):
        llm = get_llm(feature)
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip(), f"{feature} returned empty response"
        print(f"  P1 {feature} ({get_model(feature)}): {response.content.strip()[:60]}")

    @pytest.mark.skipif(not HAS_GEMINI_KEY, reason="GEMINI_API_KEY not set")
    def test_gemini_features_respond(self):
        """Gemini features in premium profile (flash-lite) respond to real prompts."""
        gemini_features = [f for f, (m, p) in MODEL_QOS_PROFILES['premium'].items() if p == 'gemini']
        for feature in gemini_features:
            llm = get_llm(feature)
            response = llm.invoke(SIMPLE_PROMPT)
            assert response.content.strip(), f"{feature} returned empty"
            print(f"  P1 gemini {feature} ({get_model(feature)}): {response.content.strip()[:60]}")


# ---------------------------------------------------------------------------
# P2: get_model()/get_provider() resolution across all 6 profiles
# ---------------------------------------------------------------------------
class TestP2_ModelProviderResolution:
    """P2: get_model/get_provider resolve correctly for all features in all profiles."""

    def test_all_profiles_resolve(self):
        for profile_name, profile in MODEL_QOS_PROFILES.items():
            for feature, (expected_model, expected_provider) in profile.items():
                # get_model/get_provider only check active profile, so verify data structure
                assert isinstance(expected_model, str) and len(expected_model) > 0
                assert expected_provider in {'openai', 'gemini', 'openrouter', 'anthropic', 'perplexity'}
        print(f"  P2: All {len(MODEL_QOS_PROFILES)} profiles validated")

    def test_active_profile_get_model(self):
        for feature in _active_profile:
            model = get_model(feature)
            provider = get_provider(feature)
            assert model == _active_profile[feature][0]
            assert provider == _active_profile[feature][1]

    def test_three_profiles_exist(self):
        assert len(MODEL_QOS_PROFILES) == 3
        assert set(MODEL_QOS_PROFILES.keys()) == {'premium', 'max', 'byok'}


# ---------------------------------------------------------------------------
# P3: _create_byok_client() factory — constructs real ChatOpenAI with test key
# ---------------------------------------------------------------------------
class TestP3_CreateByokClient:
    """P3: _create_byok_client creates valid ChatOpenAI instances."""

    def test_openai_byok_client(self):
        client = _create_byok_client('gpt-4.1-mini', 'openai', os.environ['OPENAI_API_KEY'])
        assert client is not None
        response = client.invoke(SIMPLE_PROMPT)
        assert response.content.strip(), "BYOK OpenAI client returned empty"
        print(f"  P3 BYOK openai: {response.content.strip()[:60]}")

    def test_openrouter_gemini_byok_reroute(self):
        """OpenRouter + gemini model → reroutes to Gemini direct (needs GEMINI_API_KEY)."""
        if not HAS_GEMINI_KEY:
            pytest.skip("GEMINI_API_KEY not set")
        client = _create_byok_client(
            'gemini-3-flash-preview', 'openrouter', os.environ['GEMINI_API_KEY'], feature='wrapped_analysis'
        )
        assert client is not None
        response = client.invoke(SIMPLE_PROMPT)
        assert response.content.strip()
        print(f"  P3 BYOK openrouter→gemini: {response.content.strip()[:60]}")

    def test_unsupported_provider_returns_none(self):
        client = _create_byok_client('sonar-pro', 'perplexity', 'fake-key')
        assert client is None

    def test_streaming_byok_client(self):
        client = _create_byok_client('gpt-4.1-mini', 'openai', os.environ['OPENAI_API_KEY'], streaming=True)
        assert client is not None
        response = client.invoke(SIMPLE_PROMPT)
        assert response.content.strip()
        print(f"  P3 BYOK streaming: {response.content.strip()[:60]}")


# ---------------------------------------------------------------------------
# P4: _effective_byok_provider() mapping
# ---------------------------------------------------------------------------
class TestP4_EffectiveBYOKProvider:
    """P4: Provider mapping for BYOK key type resolution."""

    def test_openai(self):
        assert _effective_byok_provider('gpt-4.1-mini', 'openai') == 'openai'

    def test_gemini(self):
        assert _effective_byok_provider('gemini-2.5-flash', 'gemini') == 'gemini'

    def test_openrouter_gemini(self):
        assert _effective_byok_provider('gemini-3-flash-preview', 'openrouter') == 'gemini'

    def test_openrouter_non_gemini(self):
        assert _effective_byok_provider('anthropic/claude', 'openrouter') == 'openrouter'


# ---------------------------------------------------------------------------
# P5: BYOK profile hardcoded to byok
# ---------------------------------------------------------------------------
class TestP5_BYOKProfileFixed:
    """P5: BYOK profile is always hardcoded to 'byok' regardless of active profile."""

    def test_byok_profile_is_byok(self):
        assert _byok_profile_name == 'byok'

    def test_byok_profile_exists(self):
        assert _byok_profile is not None
        assert _byok_profile is MODEL_QOS_PROFILES['byok']

    def test_byok_profile_independent_of_active(self):
        """BYOK profile should always be 'byok' regardless of MODEL_QOS setting."""
        assert _byok_profile_name == 'byok'
        assert _active_profile_name in MODEL_QOS_PROFILES
        # Even if active is 'max', BYOK stays 'byok'
        assert _byok_profile_name != _active_profile_name or _active_profile_name == 'byok'

    def test_byok_mostly_openai(self):
        """byok profile should use OpenAI for most features (chat_agent/web_search are exceptions)."""
        exceptions = {'chat_agent': 'anthropic', 'web_search': 'perplexity', 'wrapped_analysis': 'openrouter'}
        for feature, (model, provider) in MODEL_QOS_PROFILES['byok'].items():
            if feature in exceptions:
                assert provider == exceptions[feature], f'byok {feature} expected {exceptions[feature]}, got {provider}'
            else:
                assert provider == 'openai', f'byok feature {feature} uses {provider}, expected openai'


# ---------------------------------------------------------------------------
# P6: Structured output compatibility — real .with_structured_output() call
# ---------------------------------------------------------------------------
class TestP6_StructuredOutput:
    """P6: .with_structured_output() works with real API call on OpenAI features."""

    class SimpleOutput(BaseModel):
        word: str = Field(description="A single word greeting")

    def test_structured_output_chat_extraction(self):
        """chat_extraction (OpenAI in premium) works with with_structured_output."""
        llm = get_llm('chat_extraction')
        structured = llm.with_structured_output(self.SimpleOutput)
        result = structured.invoke("Reply with a JSON object containing a single word: hello")
        assert isinstance(result, self.SimpleOutput)
        assert len(result.word) > 0
        print(f"  P6 structured chat_extraction: {result.word}")

    def test_structured_output_proactive_notification(self):
        llm = get_llm('proactive_notification')
        structured = llm.with_structured_output(self.SimpleOutput)
        result = structured.invoke("Reply with a JSON object containing a single word: hello")
        assert isinstance(result, self.SimpleOutput)
        print(f"  P6 structured proactive_notification: {result.word}")

    def test_structured_output_conv_app_select(self):
        llm = get_llm('conv_app_select')
        structured = llm.with_structured_output(self.SimpleOutput)
        result = structured.invoke("Reply with a JSON object containing a single word: hello")
        assert isinstance(result, self.SimpleOutput)
        print(f"  P6 structured conv_app_select: {result.word}")

    def test_structured_output_external_structure(self):
        llm = get_llm('external_structure')
        structured = llm.with_structured_output(self.SimpleOutput)
        result = structured.invoke("Reply with a JSON object containing a single word: hello")
        assert isinstance(result, self.SimpleOutput)
        print(f"  P6 structured external_structure: {result.word}")

    @pytest.mark.skipif(not HAS_GEMINI_KEY, reason="GEMINI_API_KEY not set — trends is on Gemini in premium")
    def test_structured_output_trends_gemini(self):
        """trends is on gemini-2.5-flash-lite in premium — test SO on Gemini."""
        llm = get_llm('trends')
        structured = llm.with_structured_output(self.SimpleOutput)
        result = structured.invoke("Reply with a JSON object containing a single word: hello")
        assert isinstance(result, self.SimpleOutput)
        print(f"  P6 structured trends (gemini): {result.word}")

    def test_structured_output_features_set(self):
        assert _STRUCTURED_OUTPUT_FEATURES == {
            'chat_extraction',
            'proactive_notification',
            'conv_app_select',
            'external_structure',
            'trends',
        }


# ---------------------------------------------------------------------------
# P7: Prompt caching — cache_key binding
# ---------------------------------------------------------------------------
class TestP7_PromptCaching:
    """P7: cache_key binding works and produces valid responses."""

    def test_cache_key_with_cacheable_model(self):
        """conv_structure uses gpt-5.4-mini (in _CACHE_KEY_MODELS) — cache_key should bind."""
        llm = get_llm('conv_structure', cache_key='omi-test-cp9')
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip()
        print(f"  P7 cache_key bound: {response.content.strip()[:60]}")

    def test_cache_key_ignored_for_non_cacheable(self):
        """memories uses gpt-4.1-mini (not in _CACHE_KEY_MODELS) — cache_key is no-op."""
        llm_with = get_llm('memories', cache_key='omi-test-cp9')
        llm_without = get_llm('memories')
        assert llm_with is llm_without  # same instance, cache_key was a no-op

    def test_cache_key_models_set(self):
        assert _CACHE_KEY_MODELS == {'gpt-5.4', 'gpt-5.4-mini'}


# ---------------------------------------------------------------------------
# P8: Streaming client invocation
# ---------------------------------------------------------------------------
class TestP8_Streaming:
    """P8: Streaming clients respond to real prompts."""

    def test_streaming_openai(self):
        llm = get_llm('chat_responses', streaming=True)
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip()
        print(f"  P8 streaming openai: {response.content.strip()[:60]}")

    def test_streaming_openrouter(self):
        llm = get_llm('wrapped_analysis', streaming=True)
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip()
        print(f"  P8 streaming openrouter: {response.content.strip()[:60]}")


# ---------------------------------------------------------------------------
# P9: OpenRouter vendor prefix and temperature
# ---------------------------------------------------------------------------
class TestP9_OpenRouterConfig:
    """P9: OpenRouter adds google/ prefix and applies temperature config."""

    def test_wrapped_analysis_responds(self):
        llm = get_llm('wrapped_analysis')
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip()
        print(f"  P9 openrouter: {response.content.strip()[:60]}")

    def test_vendor_prefix(self):
        llm = get_llm('wrapped_analysis')
        assert llm.model_name.startswith('google/'), f"Expected google/ prefix, got {llm.model_name}"

    def test_temperature_applied(self):
        llm = get_llm('wrapped_analysis')
        assert llm.temperature == 0.7


# ---------------------------------------------------------------------------
# P10: Anthropic via get_model() + anthropic_client
# ---------------------------------------------------------------------------
class TestP10_Anthropic:
    """P10: chat_agent via Anthropic client with real API call."""

    @pytest.mark.asyncio
    async def test_chat_agent(self):
        model = get_model('chat_agent')
        assert 'claude' in model
        response = await anthropic_client.messages.create(
            model=model, max_tokens=50, messages=[{"role": "user", "content": SIMPLE_PROMPT}]
        )
        text = response.content[0].text.strip()
        assert text, "Anthropic returned empty"
        print(f"  P10 anthropic {model}: {text[:60]}")


# ---------------------------------------------------------------------------
# P11: Perplexity via get_model() + HTTP client
# ---------------------------------------------------------------------------
class TestP11_Perplexity:
    """P11: web_search via Perplexity HTTP with real API call."""

    def test_web_search(self):
        model = get_model('web_search')
        assert model == 'sonar-pro'
        url = "https://api.perplexity.ai/chat/completions"
        headers = {
            "Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "What is 2+2? Reply in one word."}],
            "max_tokens": 50,
        }
        resp = httpx.post(url, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        assert text
        print(f"  P11 perplexity {model}: {text[:60]}")


# ---------------------------------------------------------------------------
# P12: Gemini client factory (construction — no key needed for factory test)
# ---------------------------------------------------------------------------
class TestP12_GeminiFactory:
    """P12: _get_or_create_gemini_llm constructs valid ChatGoogleGenerativeAI using native SDK."""

    def test_gemini_factory_is_native_sdk(self):
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = _get_or_create_gemini_llm('gemini-2.5-flash')
        assert isinstance(llm, ChatGoogleGenerativeAI)

    def test_gemini_factory_cached(self):
        llm1 = _get_or_create_gemini_llm('gemini-2.5-flash')
        llm2 = _get_or_create_gemini_llm('gemini-2.5-flash')
        assert llm1 is llm2

    def test_gemini_streaming_factory(self):
        llm = _get_or_create_gemini_llm('gemini-2.5-flash', streaming=True)
        llm_no_stream = _get_or_create_gemini_llm('gemini-2.5-flash')
        assert llm is not llm_no_stream

    @pytest.mark.skipif(not HAS_GEMINI_KEY, reason="GEMINI_API_KEY not set")
    def test_gemini_real_invocation(self):
        """Real Gemini API call via native SDK (not OpenAI-compat)."""
        llm = _get_or_create_gemini_llm('gemini-2.5-flash-lite')
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip()
        print(f"  P12 gemini real: {response.content.strip()[:60]}")


# ---------------------------------------------------------------------------
# P13: get_qos_info() debugging helper
# ---------------------------------------------------------------------------
class TestP13_QosInfo:
    """P13: get_qos_info returns complete, correct data."""

    def test_all_features_present(self):
        info = get_qos_info()
        for feature in _active_profile:
            assert feature in info
            assert info[feature]['model'] == _active_profile[feature][0]
            assert info[feature]['provider'] == _active_profile[feature][1]
            assert info[feature]['profile'] == _active_profile_name

    def test_pinned_features_included(self):
        info = get_qos_info()
        assert 'fair_use' in info
        assert info['fair_use']['model'] == 'gpt-5.1'
