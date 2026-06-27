"""
L1 Integration Test — Real LLM API calls for Omi QoS profiles.

Tests that get_model() and get_llm() resolve correctly AND that the resolved
models respond to real prompts. Each test sends a minimal prompt and verifies
a non-empty response.

Default profile is premium. Set MODEL_QOS=max to test max profile.

Requires: OPENAI_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY, PERPLEXITY_API_KEY, GEMINI_API_KEY in .env.
Run: cd backend && python3 -m pytest tests/integration/test_qos_real_llm.py -v -s
"""

import os
import sys
import httpx
import pytest

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Load .env before importing clients
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from utils.llm.clients import (
    MODEL_QOS_PROFILES,
    get_model,
    get_llm,
    get_provider,
    get_qos_info,
    _active_profile_name,
    anthropic_client,
    ANTHROPIC_AGENT_MODEL,
)

SIMPLE_PROMPT = "Reply with exactly one word: hello"
HAS_GEMINI_KEY = bool(os.environ.get('GEMINI_API_KEY', ''))


# ---------------------------------------------------------------------------
# Helper: call Perplexity via HTTP (same pattern as perplexity_tools.py)
# ---------------------------------------------------------------------------
def call_perplexity(model: str, prompt: str) -> str:
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 50,
    }
    resp = httpx.post(url, json=body, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Premium profile — gpt-5.4-mini features (flagship tier)
# ---------------------------------------------------------------------------
class TestPremiumFlagship:
    """Test gpt-5.4-mini features in premium profile respond to real prompts."""

    FLAGSHIP_FEATURES = [
        'conv_action_items',
        'conv_structure',
        'conv_app_result',
        'daily_summary',
        'learnings',
        'chat_responses',
        'goals_advice',
        'notifications',
        'app_generator',
        'persona_clone',
        'persona_chat_premium',
    ]

    @pytest.mark.parametrize("feature", FLAGSHIP_FEATURES)
    def test_flagship_feature_responds(self, feature):
        model = get_model(feature)
        assert model == 'gpt-5.4-mini', f"{feature} should be gpt-5.4-mini in premium, got {model}"
        llm = get_llm(feature)
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip(), f"{feature} ({model}) returned empty response"
        print(f"  {feature} ({model}): {response.content.strip()[:60]}")


# ---------------------------------------------------------------------------
# Premium profile — gpt-4.1-mini features (quality-sensitive tier)
# ---------------------------------------------------------------------------
class TestPremiumMini:
    """Test gpt-4.1-mini features in premium profile respond to real prompts."""

    MINI_FEATURES = [
        'external_structure',
        'memories',
        'memory_conflict',
        'knowledge_graph',
        'chat_extraction',
        'chat_graph',
        'goals',
        'proactive_notification',
    ]

    @pytest.mark.parametrize("feature", MINI_FEATURES)
    def test_mini_feature_responds(self, feature):
        model = get_model(feature)
        assert model == 'gpt-4.1-mini', f"{feature} should be gpt-4.1-mini in premium, got {model}"
        llm = get_llm(feature)
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip(), f"{feature} ({model}) returned empty response"
        print(f"  {feature} ({model}): {response.content.strip()[:60]}")


# ---------------------------------------------------------------------------
# Premium profile — gpt-4.1-nano features (simple tasks tier)
# ---------------------------------------------------------------------------
class TestPremiumNano:
    """Test gpt-4.1-nano features in premium profile respond to real prompts."""

    NANO_FEATURES = [
        'conv_app_select',
        'conv_folder',
        'conv_discard',
        'smart_glasses',
        'persona_chat',
        'daily_summary_simple',
        'memory_category',
    ]

    @pytest.mark.parametrize("feature", NANO_FEATURES)
    def test_nano_feature_responds(self, feature):
        model = get_model(feature)
        assert model == 'gpt-4.1-nano', f"{feature} should be gpt-4.1-nano in premium, got {model}"
        llm = get_llm(feature)
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip(), f"{feature} ({model}) returned empty response"
        print(f"  {feature} ({model}): {response.content.strip()[:60]}")


# ---------------------------------------------------------------------------
# Premium profile — gpt-4.1-mini features (vision/openglass)
# ---------------------------------------------------------------------------
class TestPremiumVision:
    """Test gpt-4.1-mini vision-capable features in premium profile."""

    def test_openglass_feature_responds(self):
        model = get_model('openglass')
        assert model == 'gpt-4.1-mini', f"openglass should be gpt-4.1-mini, got {model}"
        llm = get_llm('openglass')
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip(), f"openglass ({model}) returned empty response"
        print(f"  openglass ({model}): {response.content.strip()[:60]}")


# ---------------------------------------------------------------------------
# Premium profile — gemini-2.5-flash-lite features (free-text cost optimization)
# ---------------------------------------------------------------------------
class TestPremiumGemini:
    """Test gemini-2.5-flash-lite features in premium profile respond to real prompts."""

    GEMINI_FEATURES = [
        'session_titles',
        'followup',
        'onboarding',
        'app_integration',
        'trends',
    ]

    @pytest.mark.skipif(not HAS_GEMINI_KEY, reason="GEMINI_API_KEY not set")
    @pytest.mark.parametrize("feature", GEMINI_FEATURES)
    def test_gemini_feature_responds(self, feature):
        model = get_model(feature)
        assert model == 'gemini-2.5-flash-lite', f"{feature} should be gemini-2.5-flash-lite in premium, got {model}"
        llm = get_llm(feature)
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip(), f"{feature} ({model}) returned empty response"
        print(f"  {feature} ({model}): {response.content.strip()[:60]}")


# ---------------------------------------------------------------------------
# Premium profile — OpenRouter (only wrapped_analysis)
# ---------------------------------------------------------------------------
class TestPremiumOpenRouter:
    """Test OpenRouter feature responds."""

    def test_wrapped_analysis(self):
        model = get_model('wrapped_analysis')
        assert model == 'gemini-3-flash-preview'
        llm = get_llm('wrapped_analysis')
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip(), f"wrapped_analysis ({model}) returned empty response"
        print(f"  wrapped_analysis ({model}): {response.content.strip()[:60]}")


# ---------------------------------------------------------------------------
# Premium profile — Anthropic (via get_model + anthropic_client)
# ---------------------------------------------------------------------------
class TestPremiumAnthropic:
    """Test chat_agent via Anthropic client (get_model, not get_llm)."""

    @pytest.mark.asyncio
    async def test_chat_agent_anthropic(self):
        model = get_model('chat_agent')
        assert model == 'claude-sonnet-4-6', f"chat_agent should be claude-sonnet-4-6, got {model}"
        assert model == ANTHROPIC_AGENT_MODEL

        response = await anthropic_client.messages.create(
            model=model,
            max_tokens=50,
            messages=[{"role": "user", "content": SIMPLE_PROMPT}],
        )
        text = response.content[0].text.strip()
        assert text, f"chat_agent ({model}) returned empty response"
        print(f"  chat_agent ({model}): {text[:60]}")


# ---------------------------------------------------------------------------
# Premium profile — Perplexity (via get_model + HTTP client)
# ---------------------------------------------------------------------------
class TestPremiumPerplexity:
    """Test web_search via Perplexity HTTP client (get_model, not get_llm)."""

    def test_web_search_perplexity(self):
        model = get_model('web_search')
        assert model == 'sonar-pro', f"web_search should be sonar-pro, got {model}"
        text = call_perplexity(model, "What is 2+2? Reply in one word.")
        assert text.strip(), f"web_search ({model}) returned empty response"
        print(f"  web_search ({model}): {text.strip()[:60]}")


# ---------------------------------------------------------------------------
# Profile routing verification
# ---------------------------------------------------------------------------
class TestProfileRouting:
    """Verify get_qos_info returns correct provider classification for all features."""

    def test_all_features_have_valid_provider(self):
        info = get_qos_info()
        valid_providers = {'openai', 'anthropic', 'openrouter', 'perplexity', 'gemini'}
        for feature, details in info.items():
            assert details['provider'] in valid_providers, f"{feature}: invalid provider {details['provider']}"
            print(f"  {feature}: {details['model']} ({details['provider']})")

    def test_active_profile_is_premium(self):
        assert _active_profile_name == 'premium'

    def test_premium_profile_has_expected_variant_count(self):
        distinct = {model for model, _provider in MODEL_QOS_PROFILES['premium'].values()}
        assert len(distinct) == 7, f"Expected 7 variants in premium, got {len(distinct)}: {distinct}"

    def test_max_profile_has_expected_variant_count(self):
        distinct = {model for model, _provider in MODEL_QOS_PROFILES['max'].values()}
        assert len(distinct) == 9, f"Expected 9 variants in max, got {len(distinct)}: {distinct}"

    def test_byok_profile_has_expected_variant_count(self):
        distinct = {model for model, _provider in MODEL_QOS_PROFILES['byok'].values()}
        assert len(distinct) == 9, f"Expected 9 variants in byok, got {len(distinct)}: {distinct}"


# ---------------------------------------------------------------------------
# Streaming support — verify streaming clients work
# ---------------------------------------------------------------------------
class TestStreamingClients:
    """Test that streaming clients respond to real prompts."""

    def test_streaming_openai(self):
        llm = get_llm('chat_responses', streaming=True)
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip(), "Streaming chat_responses returned empty"
        print(f"  streaming chat_responses: {response.content.strip()[:60]}")

    def test_streaming_openrouter(self):
        llm = get_llm('wrapped_analysis', streaming=True)
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip(), "Streaming wrapped_analysis returned empty"
        print(f"  streaming wrapped_analysis: {response.content.strip()[:60]}")


# ---------------------------------------------------------------------------
# Cache key — verify prompt cache binding works with real API
# ---------------------------------------------------------------------------
class TestCacheKeyReal:
    """Test that cache_key binding still produces valid responses."""

    def test_cache_key_with_gpt54_mini(self):
        llm = get_llm('conv_action_items', cache_key='omi-test-integration')
        response = llm.invoke(SIMPLE_PROMPT)
        assert response.content.strip(), "cache_key conv_action_items returned empty"
        print(f"  cache_key conv_action_items: {response.content.strip()[:60]}")
