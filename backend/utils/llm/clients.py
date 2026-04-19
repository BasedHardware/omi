import logging
import os
from typing import Any, Dict, List, Optional

import anthropic
import httpx
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import tiktoken

from models.structured import Structured
from utils.llm.usage_tracker import get_usage_callback

logger = logging.getLogger(__name__)

_usage_callback = get_usage_callback()

# ---------------------------------------------------------------------------
# Model QoS Profile System
#
# Each profile maps every feature to a specific model. Features span multiple
# providers (OpenAI, Anthropic, OpenRouter, Perplexity). Within a profile,
# each feature gets the model appropriate for that cost/quality level.
#
# Global switch:     MODEL_QOS=premium        (selects entire profile)
# Per-feature:       MODEL_QOS_CHAT_AGENT=claude-haiku-3.5  (overrides one feature)
#
# Two profiles:
#   max     — current production behavior (default)
#   premium — cost-saving alternative with cheaper models
# ---------------------------------------------------------------------------

MODEL_QOS_PROFILES: Dict[str, Dict[str, str]] = {
    'premium': {
        # OpenAI — conversation processing (gpt-5.4-mini for quality, gpt-4.1-nano for simple)
        'conv_action_items': 'gpt-5.4-mini',
        'conv_structure': 'gpt-5.4-mini',
        'conv_app_result': 'gpt-5.4-mini',
        'conv_app_select': 'gpt-4.1-nano',
        'conv_folder': 'gpt-4.1-nano',
        'conv_discard': 'gpt-4.1-nano',
        'daily_summary': 'gpt-5.4-mini',
        'daily_summary_simple': 'gpt-4.1-nano',
        'external_structure': 'gpt-4.1-nano',
        # OpenAI — memories & knowledge
        'memories': 'gpt-4.1-nano',
        'learnings': 'gpt-5.4-mini',
        'memory_conflict': 'gpt-4.1-nano',
        'memory_category': 'gpt-4.1-nano',
        'knowledge_graph': 'gpt-4.1-nano',
        # OpenAI — chat (gpt-5.4 for user-facing, gpt-4.1-nano for extraction)
        'chat_responses': 'gpt-5.4',
        'chat_extraction': 'gpt-4.1-nano',
        'chat_graph': 'gpt-5.4-mini',
        'session_titles': 'gpt-4.1-nano',
        # OpenAI — features
        'goals': 'gpt-4.1-nano',
        'goals_advice': 'gpt-5.4',
        'notifications': 'gpt-5.4-mini',
        'proactive_notification': 'gpt-4.1-nano',
        'followup': 'gpt-4.1-nano',
        'smart_glasses': 'gpt-4.1-nano',
        'onboarding': 'gpt-4.1-nano',
        'app_generator': 'gpt-5.4',
        'app_integration': 'gpt-4.1-nano',
        'persona_clone': 'gpt-5.4-mini',
        'trends': 'gpt-4.1-nano',
        # Anthropic (chat_agent only — used via get_model() + anthropic_client)
        'chat_agent': 'claude-sonnet-4-6',
        # OpenAI — persona & analysis (consolidated from OpenRouter to direct OpenAI)
        'persona_chat': 'gpt-4.1-nano',
        'persona_chat_premium': 'gpt-5.4-mini',
        'wrapped_analysis': 'gpt-5.4-mini',
        # Perplexity
        'web_search': 'sonar-pro',
    },
    'max': {
        # OpenAI — conversation processing (gpt-5.4 flagship, gpt-5.4-mini for simple)
        'conv_action_items': 'gpt-5.4',
        'conv_structure': 'gpt-5.4',
        'conv_app_result': 'gpt-5.4',
        'conv_app_select': 'gpt-5.4-mini',
        'conv_folder': 'gpt-5.4-mini',
        'conv_discard': 'gpt-5.4-mini',
        'daily_summary': 'gpt-5.4',
        'daily_summary_simple': 'gpt-5.4-mini',
        'external_structure': 'gpt-5.4-mini',
        # OpenAI — memories & knowledge
        'memories': 'gpt-5.4-mini',
        'learnings': 'gpt-5.4-mini',
        'memory_conflict': 'gpt-5.4-mini',
        'memory_category': 'gpt-5.4-mini',
        'knowledge_graph': 'gpt-5.4-mini',
        # OpenAI — chat (gpt-5.4 for user-facing, gpt-5.4-mini for extraction)
        'chat_responses': 'gpt-5.4',
        'chat_extraction': 'gpt-5.4-mini',
        'chat_graph': 'gpt-5.4-mini',
        'session_titles': 'gpt-5.4-mini',
        # OpenAI — features
        'goals': 'gpt-5.4-mini',
        'goals_advice': 'gpt-5.4',
        'notifications': 'gpt-5.4',
        'proactive_notification': 'gpt-5.4-mini',
        'followup': 'gpt-5.4-mini',
        'smart_glasses': 'gpt-5.4-mini',
        'onboarding': 'gpt-5.4-mini',
        'app_generator': 'gpt-5.4',
        'app_integration': 'gpt-5.4-mini',
        'persona_clone': 'gpt-5.4',
        'trends': 'gpt-5.4-mini',
        # Anthropic (chat_agent only — used via get_model() + anthropic_client)
        'chat_agent': 'claude-sonnet-4-6',
        # OpenAI — persona & analysis (consolidated from OpenRouter to direct OpenAI)
        'persona_chat': 'gpt-5.4-mini',
        'persona_chat_premium': 'gpt-5.4-mini',
        'wrapped_analysis': 'gpt-5.4-mini',
        # Perplexity
        'web_search': 'sonar-pro',
    },
}

# Pinned features — model is fixed regardless of profile or env override.
_PINNED_FEATURES: Dict[str, str] = {
    'fair_use': 'gpt-5.1',
}

# Resolve active profile once at startup (kai: OnceLock/singleton pattern).
_active_profile_name = os.environ.get('MODEL_QOS', 'max').strip().lower()
if _active_profile_name not in MODEL_QOS_PROFILES:
    logger.warning('MODEL_QOS=%s is not a valid profile, falling back to max', _active_profile_name)
    _active_profile_name = 'max'
_active_profile = MODEL_QOS_PROFILES[_active_profile_name]

# Provider detection from model name — provider depends on profile, not feature.
# A feature like persona_chat may be OpenRouter in premium but OpenAI in max.
_ANTHROPIC_ONLY_FEATURES = {'chat_agent'}  # always Anthropic, used via get_model() + anthropic_client
_PERPLEXITY_ONLY_FEATURES = {'web_search'}  # always Perplexity, used via get_model() + HTTP client


def _classify_provider(model: str) -> str:
    """Classify provider from model name. Provider follows the model, not the feature."""
    if '/' in model:
        return 'openrouter'
    if model.startswith('claude'):
        return 'anthropic'
    if model.startswith('sonar'):
        return 'perplexity'
    return 'openai'


# Feature-specific client config (temperature, headers — orthogonal to model choice).
# Only applied when a feature resolves to an OpenRouter model.
_OPENROUTER_TEMPERATURES: Dict[str, float] = {
    'persona_chat': 0.8,
    'persona_chat_premium': 0.8,
    'wrapped_analysis': 0.7,
}

# Models that support OpenAI prompt caching (prompt_cache_key routing).
_CACHE_KEY_MODELS = {'gpt-5.1', 'gpt-5.2', 'gpt-5.4', 'gpt-5.4-mini'}


def get_model(feature: str) -> str:
    """Get the model name for a feature from the active Model QoS profile.

    Resolution order: pinned > per-feature env override > active profile > fallback.

    Args:
        feature: Feature name (e.g. 'conv_action_items', 'chat_agent').

    Returns:
        Model name string (e.g. 'gpt-4.1-mini', 'claude-sonnet-4-6').

    Override via env var:
        MODEL_QOS_CHAT_AGENT=claude-haiku-3.5
        MODEL_QOS_CONV_STRUCTURE=gpt-5.1
    """
    if feature in _PINNED_FEATURES:
        return _PINNED_FEATURES[feature]
    env_key = f'MODEL_QOS_{feature.upper()}'
    override = os.environ.get(env_key, '').strip()
    if override:
        # Warn if override model doesn't match the feature's expected provider
        profile_model = _active_profile.get(feature, 'gpt-4.1-mini')
        expected_provider = _classify_provider(profile_model)
        override_provider = _classify_provider(override)
        if expected_provider != override_provider:
            logger.warning(
                'QoS override %s=%s (provider: %s) may be invalid — feature %s expects %s',
                env_key,
                override,
                override_provider,
                feature,
                expected_provider,
            )
        return override
    return _active_profile.get(feature, 'gpt-4.1-mini')


# ---------------------------------------------------------------------------
# Client factories — provider-specific, cached per (model, streaming, provider)
# ---------------------------------------------------------------------------

_llm_cache: Dict[tuple, Any] = {}


def _get_or_create_openai_llm(model_name: str, streaming: bool = False) -> ChatOpenAI:
    """Get or create a ChatOpenAI instance for an OpenAI model."""
    key = (model_name, streaming, 'openai')
    if key not in _llm_cache:
        kwargs: Dict[str, Any] = {'model': model_name, 'callbacks': [_usage_callback]}
        if model_name == 'gpt-5.1':
            kwargs['extra_body'] = {"prompt_cache_retention": "24h"}
        if streaming:
            kwargs['streaming'] = True
            kwargs['stream_options'] = {"include_usage": True}
        _llm_cache[key] = ChatOpenAI(**kwargs)
    return _llm_cache[key]


def _get_or_create_openrouter_llm(
    model_name: str, streaming: bool = False, temperature: Optional[float] = None
) -> ChatOpenAI:
    """Get or create a ChatOpenAI instance for an OpenRouter model."""
    key = (model_name, streaming, 'openrouter', temperature)
    if key not in _llm_cache:
        kwargs: Dict[str, Any] = {
            'model': model_name,
            'api_key': os.environ.get('OPENROUTER_API_KEY'),
            'base_url': "https://openrouter.ai/api/v1",
            'default_headers': {"X-Title": "Omi Chat"},
            'callbacks': [_usage_callback],
        }
        if temperature is not None:
            kwargs['temperature'] = temperature
        if streaming:
            kwargs['streaming'] = True
            kwargs['stream_options'] = {"include_usage": True}
        _llm_cache[key] = ChatOpenAI(**kwargs)
    return _llm_cache[key]


def get_llm(feature: str, streaming: bool = False, cache_key: Optional[str] = None) -> ChatOpenAI:
    """Get the LLM client for a feature based on the active Model QoS profile.

    Works for OpenAI and OpenRouter features (returns ChatOpenAI).
    For Anthropic/Perplexity, use get_model(feature) to get the model string.

    Args:
        feature: Feature name (e.g. 'conv_action_items', 'persona_chat').
        streaming: Whether to return a streaming-enabled client.
        cache_key: Optional prompt cache routing key (OpenAI gpt-5.1 only).

    Usage:
        llm = get_llm('conv_action_items', cache_key='omi-extract-actions')
        response = llm.invoke(prompt)

        llm_stream = get_llm('chat_responses', streaming=True)
        response = llm_stream.invoke(prompt, {'callbacks': callbacks})
    """
    if feature in _ANTHROPIC_ONLY_FEATURES:
        raise ValueError(
            f"Feature '{feature}' is Anthropic — use get_model('{feature}') with anthropic_client instead of get_llm()"
        )
    if feature in _PERPLEXITY_ONLY_FEATURES:
        raise ValueError(
            f"Feature '{feature}' is Perplexity — use get_model('{feature}') with the Perplexity HTTP client instead of get_llm()"
        )

    model = get_model(feature)
    provider = _classify_provider(model)

    # Reject models that can't be served via ChatOpenAI (Anthropic direct, Perplexity)
    if provider == 'anthropic':
        raise ValueError(
            f"Feature '{feature}' resolved to Anthropic model '{model}' — use get_model() with anthropic_client"
        )
    if provider == 'perplexity':
        raise ValueError(
            f"Feature '{feature}' resolved to Perplexity model '{model}' — use get_model() with Perplexity HTTP client"
        )

    if provider == 'openrouter':
        temp = _OPENROUTER_TEMPERATURES.get(feature)
        return _get_or_create_openrouter_llm(model, streaming, temp)

    llm = _get_or_create_openai_llm(model, streaming)
    if cache_key and model in _CACHE_KEY_MODELS:
        return llm.bind(prompt_cache_key=cache_key)
    return llm


def get_qos_info() -> Dict[str, Dict[str, str]]:
    """Return full feature→model mapping for the active profile (debugging/monitoring)."""
    info: Dict[str, Dict[str, str]] = {}
    all_features = set(_active_profile.keys()) | set(_PINNED_FEATURES.keys())
    for feature in sorted(all_features):
        model = get_model(feature)
        info[feature] = {
            'model': model,
            'profile': _active_profile_name,
            'provider': _classify_provider(model),
        }
    return info


# Startup logging (kai: log active profile so cost issues are traceable).
logger.info('Model QoS profile=%s (%d features)', _active_profile_name, len(_active_profile))
for _feat, _model in sorted(_active_profile.items()):
    _resolved = get_model(_feat)
    if _resolved != _model:
        logger.info('  QoS %s: %s (override, profile default: %s)', _feat, _resolved, _model)
    else:
        logger.info('  QoS %s: %s', _feat, _resolved)


# ---------------------------------------------------------------------------
# Anthropic client — model resolved from active QoS profile
# ---------------------------------------------------------------------------
anthropic_client = anthropic.AsyncAnthropic()  # uses ANTHROPIC_API_KEY env var

ANTHROPIC_AGENT_MODEL = get_model('chat_agent')
ANTHROPIC_AGENT_COMPLEX_MODEL = get_model('chat_agent')


# ---------------------------------------------------------------------------
# Legacy model instances (for callsites not yet wired through get_llm)
#
# These are kept for backward compatibility. New code should use
# get_llm(feature) or get_model(feature) instead.
# ---------------------------------------------------------------------------
llm_mini = ChatOpenAI(model='gpt-4.1-mini', callbacks=[_usage_callback])
llm_mini_stream = ChatOpenAI(
    model='gpt-4.1-mini',
    streaming=True,
    stream_options={"include_usage": True},
    callbacks=[_usage_callback],
)
llm_high = ChatOpenAI(model='o4-mini', callbacks=[_usage_callback])
llm_medium = ChatOpenAI(model='gpt-5.2', callbacks=[_usage_callback])
llm_medium_stream = ChatOpenAI(
    model='gpt-5.2',
    streaming=True,
    stream_options={"include_usage": True},
    callbacks=[_usage_callback],
)
llm_medium_experiment = ChatOpenAI(
    model='gpt-5.1',
    extra_body={"prompt_cache_retention": "24h"},
    callbacks=[_usage_callback],
)
llm_persona_mini_stream = ChatOpenAI(
    temperature=0.8,
    model="google/gemini-flash-1.5-8b",
    api_key=os.environ.get('OPENROUTER_API_KEY'),
    base_url="https://openrouter.ai/api/v1",
    default_headers={"X-Title": "Omi Chat"},
    streaming=True,
    stream_options={"include_usage": True},
    callbacks=[_usage_callback],
)
llm_persona_medium_stream = ChatOpenAI(
    temperature=0.8,
    model="anthropic/claude-3.5-sonnet",
    api_key=os.environ.get('OPENROUTER_API_KEY'),
    base_url="https://openrouter.ai/api/v1",
    default_headers={"X-Title": "Omi Chat"},
    streaming=True,
    stream_options={"include_usage": True},
    callbacks=[_usage_callback],
)

# Gemini models for large context analysis
llm_gemini_flash = ChatOpenAI(
    temperature=0.7,
    model="google/gemini-3-flash-preview",
    api_key=os.environ.get('OPENROUTER_API_KEY'),
    base_url="https://openrouter.ai/api/v1",
    default_headers={"X-Title": "Omi Wrapped"},
    callbacks=[_usage_callback],
)

# ---------------------------------------------------------------------------
# Embeddings, parser, utilities
# ---------------------------------------------------------------------------
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
parser = PydanticOutputParser(pydantic_object=Structured)

encoding = tiktoken.encoding_for_model('gpt-4')


def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    num_tokens = len(encoding.encode(string))
    return num_tokens


def generate_embedding(content: str) -> List[float]:
    return embeddings.embed_documents([content])[0]


def gemini_embed_query(text: str) -> List[float]:
    """Embed a query using Gemini embedding-001 (3072-dim) for screen activity search.

    Uses RETRIEVAL_QUERY task type to match the RETRIEVAL_DOCUMENT embeddings
    generated by the desktop app.
    """
    api_key = os.environ.get('GEMINI_API_KEY', '')
    url = f'https://generativelanguage.googleapis.com/v1beta/models/embedding-001:embedContent?key={api_key}'
    payload = {
        'model': 'models/embedding-001',
        'content': {'parts': [{'text': text}]},
        'taskType': 'RETRIEVAL_QUERY',
    }
    resp = httpx.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()['embedding']['values']
