"""
L1 Integration Test — Real LLM calls for ALL features in premium profile.

Tests every feature path with a real API call to find compatibility flaws.
For get_llm() features: invoke() with a simple prompt.
For Anthropic/Perplexity: uses their native clients.

Run: cd backend && python3 -m pytest tests/integration/test_qos_all_features_l1.py -v -s
"""

import os
import sys
import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

from utils.llm.clients import (
    MODEL_QOS_PROFILES,
    get_model,
    get_llm,
    get_provider,
    _active_profile_name,
    anthropic_client,
)

SIMPLE_PROMPT = "Reply with exactly one word: hello"

# Features that can't use get_llm() — need their own client
_ANTHROPIC_FEATURES = {'chat_agent'}
_PERPLEXITY_FEATURES = {'web_search'}
_SKIP_GET_LLM = _ANTHROPIC_FEATURES | _PERPLEXITY_FEATURES


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
# Premium profile — all features
# ---------------------------------------------------------------------------
class TestPremiumAllFeatures:
    """Test every feature in the premium profile with real LLM calls."""

    ALL_FEATURES = sorted(MODEL_QOS_PROFILES['premium'].keys())
    GET_LLM_FEATURES = [f for f in ALL_FEATURES if f not in _SKIP_GET_LLM]

    @pytest.mark.parametrize("feature", GET_LLM_FEATURES)
    def test_premium_get_llm_feature(self, feature):
        """Test that get_llm() features in premium profile respond to real prompts."""
        if _active_profile_name != 'premium':
            pytest.skip("MODEL_QOS is not premium")
        model = get_model(feature)
        provider = get_provider(feature)
        llm = get_llm(feature)
        response = llm.invoke(SIMPLE_PROMPT)
        text = response.content.strip() if hasattr(response, 'content') else str(response).strip()
        assert text, f"FAIL {feature} ({model}/{provider}) returned empty"
        print(f"  PASS {feature}: {model} [{provider}] -> {text[:60]}")

    @pytest.mark.asyncio
    async def test_premium_chat_agent(self):
        """Test chat_agent via Anthropic client."""
        if _active_profile_name != 'premium':
            pytest.skip("MODEL_QOS is not premium")
        model = get_model('chat_agent')
        response = await anthropic_client.messages.create(
            model=model,
            max_tokens=50,
            messages=[{"role": "user", "content": SIMPLE_PROMPT}],
        )
        text = response.content[0].text.strip()
        assert text, f"FAIL chat_agent ({model}) returned empty"
        print(f"  PASS chat_agent: {model} [anthropic] -> {text[:60]}")

    def test_premium_web_search(self):
        """Test web_search via Perplexity."""
        if _active_profile_name != 'premium':
            pytest.skip("MODEL_QOS is not premium")
        model = get_model('web_search')
        text = call_perplexity(model, "What is 2+2? Reply in one word.")
        assert text.strip(), f"FAIL web_search ({model}) returned empty"
        print(f"  PASS web_search: {model} [perplexity] -> {text.strip()[:60]}")


# ---------------------------------------------------------------------------
# Premium profile — streaming variants
# ---------------------------------------------------------------------------
class TestPremiumStreaming:
    """Test streaming works for key features in premium profile."""

    STREAMING_FEATURES = ['chat_responses', 'wrapped_analysis']

    @pytest.mark.parametrize("feature", STREAMING_FEATURES)
    def test_premium_streaming(self, feature):
        if _active_profile_name != 'premium':
            pytest.skip("MODEL_QOS is not premium")
        model = get_model(feature)
        provider = get_provider(feature)
        llm = get_llm(feature, streaming=True)
        response = llm.invoke(SIMPLE_PROMPT)
        text = response.content.strip() if hasattr(response, 'content') else str(response).strip()
        assert text, f"FAIL streaming {feature} ({model}/{provider}) returned empty"
        print(f"  PASS streaming {feature}: {model} [{provider}] -> {text[:60]}")


# ---------------------------------------------------------------------------
# Cross-profile comparison — verify feature parity
# ---------------------------------------------------------------------------
class TestProfileFeatureParity:
    """Verify all profiles have the same feature set."""

    def test_same_features_as_max(self):
        premium_features = set(MODEL_QOS_PROFILES['premium'].keys())
        max_features = set(MODEL_QOS_PROFILES['max'].keys())
        missing_in_max = premium_features - max_features
        extra_in_max = max_features - premium_features
        assert not missing_in_max, f"Features in premium but missing in max: {missing_in_max}"
        assert not extra_in_max, f"Features in max but missing in premium: {extra_in_max}"

    def test_same_features_as_byok(self):
        premium_features = set(MODEL_QOS_PROFILES['premium'].keys())
        byok_features = set(MODEL_QOS_PROFILES['byok'].keys())
        missing_in_byok = premium_features - byok_features
        extra_in_byok = byok_features - premium_features
        assert not missing_in_byok, f"Features in premium but missing in byok: {missing_in_byok}"
        assert not extra_in_byok, f"Features in byok but missing in premium: {extra_in_byok}"
