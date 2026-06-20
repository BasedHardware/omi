"""Model/profile configuration for backend LLM feature routing.

This module is the source of truth for feature → (model, provider) routing.
Provider-specific client construction lives in ``providers.py``; callers should
continue to use ``clients.get_llm(feature)``.
"""

import logging
import os
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model QoS Profile System
#
# Each profile maps every feature to a (model, provider) tuple.
# The profile is the SINGLE SOURCE OF TRUTH for both model and provider.
# Provider is never inferred from model name — it is declared explicitly.
#
# This means the same model can be hosted by different providers:
#   feature_a: ('gemini-2.5-flash', 'gemini')      → Google direct
#   feature_b: ('gemini-2.5-flash', 'openrouter')   → OpenRouter
#
# Global switch:     MODEL_QOS=premium        (selects entire profile)
#
# Profiles:
#   premium  — maximize cost savings while preserving 80% of max quality
#   max      — 100% quality, best models available, no cost optimization
#   byok     — same models as max (BYOK users pay their own API costs)
# ---------------------------------------------------------------------------

MODEL_QOS_PROFILES: Dict[str, Dict[str, Tuple[str, str]]] = {
    # -----------------------------------------------------------------------
    # premium — maximize cost savings while preserving 80% of max quality.
    # Uses gpt-5.4-mini (not gpt-5.4) for core features, gpt-4.1-mini (not gpt-4.1)
    # for quality-sensitive tasks, gpt-4.1-nano for simple routing/classification,
    # and Gemini flash-lite for low-complexity free-text (titles, followups, onboarding).
    # -----------------------------------------------------------------------
    'premium': {
        # OpenAI — conversation processing
        'conv_action_items': ('gpt-5.4-mini', 'openai'),
        'conv_structure': ('gpt-5.4-mini', 'openai'),
        'conv_app_result': ('gpt-5.4-mini', 'openai'),
        'conv_app_select': ('gpt-4.1-nano', 'openai'),
        'conv_folder': ('gpt-4.1-nano', 'openai'),
        'conv_discard': ('gpt-4.1-nano', 'openai'),
        'daily_summary': ('gpt-5.4-mini', 'openai'),
        'daily_summary_simple': ('gpt-4.1-nano', 'openai'),
        'external_structure': ('gpt-4.1-mini', 'openai'),
        # OpenAI — memories & knowledge
        'memories': ('gpt-4.1-mini', 'openai'),
        'learnings': ('gpt-5.4-mini', 'openai'),
        'memory_conflict': ('gpt-4.1-mini', 'openai'),
        'memory_category': ('gpt-4.1-nano', 'openai'),
        'knowledge_graph': ('gpt-4.1-mini', 'openai'),
        # OpenAI — chat
        'chat_responses': ('gpt-5.4-mini', 'openai'),
        'chat_extraction': ('gpt-4.1-mini', 'openai'),
        'chat_graph': ('gpt-4.1-mini', 'openai'),
        'session_titles': ('gemini-2.5-flash-lite', 'gemini'),
        # Features
        'goals': ('gpt-4.1-mini', 'openai'),
        'goals_advice': ('gpt-5.4-mini', 'openai'),
        'notifications': ('gpt-5.4-mini', 'openai'),
        'proactive_notification': ('gpt-4.1-mini', 'openai'),
        'followup': ('gemini-2.5-flash-lite', 'gemini'),
        'smart_glasses': ('gpt-4.1-nano', 'openai'),
        'openglass': ('gpt-4.1-mini', 'openai'),
        'onboarding': ('gemini-2.5-flash-lite', 'gemini'),
        'app_generator': ('gpt-5.4-mini', 'openai'),
        'app_integration': ('gemini-2.5-flash-lite', 'gemini'),
        'persona_clone': ('gpt-5.4-mini', 'openai'),
        'trends': ('gemini-2.5-flash-lite', 'gemini'),
        # Anthropic (used via get_model() + anthropic_client)
        'chat_agent': ('claude-sonnet-4-6', 'anthropic'),
        # Persona
        'persona_chat': ('gpt-4.1-nano', 'openai'),
        'persona_chat_premium': ('gpt-5.4-mini', 'openai'),
        # OpenRouter
        'wrapped_analysis': ('gemini-3-flash-preview', 'openrouter'),
        # Perplexity
        'web_search': ('sonar-pro', 'perplexity'),
    },
    # -----------------------------------------------------------------------
    # max — 100% quality, best models available, no cost optimization.
    # Uses gpt-5.4 for all core features, o4-mini for reasoning (learnings),
    # gpt-4.1 for chat graph. Pure OpenAI for highest accuracy.
    # -----------------------------------------------------------------------
    'max': {
        # OpenAI — conversation processing
        'conv_action_items': ('gpt-5.4', 'openai'),
        'conv_structure': ('gpt-5.4', 'openai'),
        'conv_app_result': ('gpt-5.4', 'openai'),
        'conv_app_select': ('gpt-4.1-mini', 'openai'),
        'conv_folder': ('gpt-4.1-mini', 'openai'),
        'conv_discard': ('gpt-4.1-mini', 'openai'),
        'daily_summary': ('gpt-5.4', 'openai'),
        'daily_summary_simple': ('gpt-4.1-mini', 'openai'),
        'external_structure': ('gpt-4.1-mini', 'openai'),
        # OpenAI — memories & knowledge
        'memories': ('gpt-4.1-mini', 'openai'),
        'learnings': ('o4-mini', 'openai'),
        'memory_conflict': ('gpt-4.1-mini', 'openai'),
        'memory_category': ('gpt-4.1-mini', 'openai'),
        'knowledge_graph': ('gpt-4.1-mini', 'openai'),
        # OpenAI — chat
        'chat_responses': ('gpt-5.4', 'openai'),
        'chat_extraction': ('gpt-4.1-mini', 'openai'),
        'chat_graph': ('gpt-4.1', 'openai'),
        'session_titles': ('gpt-4.1-mini', 'openai'),
        # Features
        'goals': ('gpt-4.1-mini', 'openai'),
        'goals_advice': ('gpt-5.4', 'openai'),
        'notifications': ('gpt-5.4', 'openai'),
        'proactive_notification': ('gpt-4.1-mini', 'openai'),
        'followup': ('gpt-4.1-mini', 'openai'),
        'smart_glasses': ('gpt-4.1-mini', 'openai'),
        'openglass': ('gpt-4.1-mini', 'openai'),
        'onboarding': ('gpt-4.1-mini', 'openai'),
        'app_generator': ('gpt-5.4', 'openai'),
        'app_integration': ('gpt-4.1-mini', 'openai'),
        'persona_clone': ('gpt-5.4', 'openai'),
        'trends': ('gpt-4.1-mini', 'openai'),
        # Anthropic
        'chat_agent': ('claude-sonnet-4-6', 'anthropic'),
        # Persona
        'persona_chat': ('gpt-4.1-nano', 'openai'),
        'persona_chat_premium': ('gpt-5.4-mini', 'openai'),
        # OpenRouter
        'wrapped_analysis': ('gemini-3-flash-preview', 'openrouter'),
        # Perplexity
        'web_search': ('sonar-pro', 'perplexity'),
    },
    # -----------------------------------------------------------------------
    # byok — same models as max. BYOK users pay their own API costs so they
    # get the same best-quality routing as max subscribers.
    # -----------------------------------------------------------------------
    'byok': {
        # OpenAI — conversation processing
        'conv_action_items': ('gpt-5.4', 'openai'),
        'conv_structure': ('gpt-5.4', 'openai'),
        'conv_app_result': ('gpt-5.4', 'openai'),
        'conv_app_select': ('gpt-4.1-mini', 'openai'),
        'conv_folder': ('gpt-4.1-mini', 'openai'),
        'conv_discard': ('gpt-4.1-mini', 'openai'),
        'daily_summary': ('gpt-5.4', 'openai'),
        'daily_summary_simple': ('gpt-4.1-mini', 'openai'),
        'external_structure': ('gpt-4.1-mini', 'openai'),
        # OpenAI — memories & knowledge
        'memories': ('gpt-4.1-mini', 'openai'),
        'learnings': ('o4-mini', 'openai'),
        'memory_conflict': ('gpt-4.1-mini', 'openai'),
        'memory_category': ('gpt-4.1-mini', 'openai'),
        'knowledge_graph': ('gpt-4.1-mini', 'openai'),
        # OpenAI — chat
        'chat_responses': ('gpt-5.4', 'openai'),
        'chat_extraction': ('gpt-4.1-mini', 'openai'),
        'chat_graph': ('gpt-4.1', 'openai'),
        'session_titles': ('gpt-4.1-mini', 'openai'),
        # Features
        'goals': ('gpt-4.1-mini', 'openai'),
        'goals_advice': ('gpt-5.4', 'openai'),
        'notifications': ('gpt-5.4', 'openai'),
        'proactive_notification': ('gpt-4.1-mini', 'openai'),
        'followup': ('gpt-4.1-mini', 'openai'),
        'smart_glasses': ('gpt-4.1-mini', 'openai'),
        'openglass': ('gpt-4.1-mini', 'openai'),
        'onboarding': ('gpt-4.1-mini', 'openai'),
        'app_generator': ('gpt-5.4', 'openai'),
        'app_integration': ('gpt-4.1-mini', 'openai'),
        'persona_clone': ('gpt-5.4', 'openai'),
        'trends': ('gpt-4.1-mini', 'openai'),
        # Anthropic
        'chat_agent': ('claude-sonnet-4-6', 'anthropic'),
        # Persona
        'persona_chat': ('gpt-4.1-nano', 'openai'),
        'persona_chat_premium': ('gpt-5.4-mini', 'openai'),
        # OpenRouter
        'wrapped_analysis': ('gemini-3-flash-preview', 'openrouter'),
        # Perplexity
        'web_search': ('sonar-pro', 'perplexity'),
    },
}

# Pinned features — (model, provider) fixed regardless of profile or env override.
_PINNED_FEATURES: Dict[str, Tuple[str, str]] = {
    'fair_use': ('gpt-5.1', 'openai'),
}

# Resolve active profile once at startup.
_active_profile_name = os.environ.get('MODEL_QOS', 'premium').strip().lower()
if _active_profile_name not in MODEL_QOS_PROFILES:
    logger.warning('MODEL_QOS=%s is not a valid profile, falling back to premium', _active_profile_name)
    _active_profile_name = 'premium'
_active_profile = MODEL_QOS_PROFILES[_active_profile_name]

# BYOK QoS — all BYOK users get routed to 'byok' profile (top-tier all-OpenAI).
# BYOK users pay their own API costs, so we give them maximum quality models.
_byok_profile_name = 'byok'
_byok_profile = MODEL_QOS_PROFILES[_byok_profile_name]

# Features that can't go through get_llm() (non-ChatOpenAI providers).
_ANTHROPIC_ONLY_FEATURES = {'chat_agent'}
_PERPLEXITY_ONLY_FEATURES = {'web_search'}


# Feature-specific client config (temperature, headers — orthogonal to model choice).
# Only applied when a feature resolves to an OpenRouter model.
_OPENROUTER_TEMPERATURES: Dict[str, float] = {
    'wrapped_analysis': 0.7,
}

# Models that support OpenAI prompt caching (prompt_cache_key routing).
_CACHE_KEY_MODELS = {'gpt-5.4', 'gpt-5.4-mini'}

# Features that call .with_structured_output() — logged when resolving to Gemini for compat monitoring.
_STRUCTURED_OUTPUT_FEATURES = {
    'chat_extraction',
    'proactive_notification',
    'conv_app_select',
    'external_structure',
    'trends',
}

_DEFAULT_CONFIG: Tuple[str, str] = ('gpt-4.1-mini', 'openai')


def _get_model_config(feature: str) -> Tuple[str, str]:
    """Get the (model, provider) tuple for a feature. Internal — used by get_llm/get_model/get_provider.

    Resolution order: pinned > active profile > fallback.
    """
    if feature in _PINNED_FEATURES:
        return _PINNED_FEATURES[feature]
    return _active_profile.get(feature, _DEFAULT_CONFIG)


def get_model(feature: str) -> str:
    """Get the model name for a feature from the active Model QoS profile.

    Resolution order: pinned > active profile > fallback.

    Args:
        feature: Feature name (e.g. 'conv_action_items', 'chat_agent').

    Returns:
        Model name string (e.g. 'gpt-4.1-mini', 'claude-sonnet-4-6').
    """
    return _get_model_config(feature)[0]


def get_provider(feature: str) -> str:
    """Get the provider for a feature from the active Model QoS profile.

    Returns:
        Provider string: 'openai', 'gemini', 'openrouter', 'anthropic', 'perplexity'.
    """
    return _get_model_config(feature)[1]


def get_route_options(feature: str, model: str, provider: str) -> Dict[str, object]:
    """Return provider/model construction options for a resolved route."""

    options: Dict[str, object] = {}
    if model == 'gpt-5.1':
        options['extra_body'] = {"prompt_cache_retention": "24h"}
    if provider == 'openrouter':
        temperature = _OPENROUTER_TEMPERATURES.get(feature)
        if temperature is not None:
            options['temperature'] = temperature
    if provider == 'gemini':
        # Mechanical Gemini-routed features do not need paid thinking tokens.
        options['thinking_budget'] = 0
    return options


def supports_prompt_cache(model: str) -> bool:
    return model in _CACHE_KEY_MODELS


def is_structured_output_feature(feature: str) -> bool:
    return feature in _STRUCTURED_OUTPUT_FEATURES


def is_anthropic_only_feature(feature: str) -> bool:
    return feature in _ANTHROPIC_ONLY_FEATURES


def is_perplexity_only_feature(feature: str) -> bool:
    return feature in _PERPLEXITY_ONLY_FEATURES


def get_active_profile_name() -> str:
    return _active_profile_name


def get_active_profile() -> Dict[str, Tuple[str, str]]:
    return _active_profile


def get_all_configured_features() -> set[str]:
    return set(_active_profile.keys()) | set(_PINNED_FEATURES.keys())


def get_default_config() -> Tuple[str, str]:
    return _DEFAULT_CONFIG


def get_byok_profile() -> Dict[str, Tuple[str, str]]:
    return _byok_profile


def get_byok_profile_name() -> str:
    return _byok_profile_name
