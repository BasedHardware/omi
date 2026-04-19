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
        # OpenAI — conversation processing
        'conv_action_items': 'gpt-4.1-nano',
        'conv_structure': 'gpt-4.1-mini',
        'conv_app_result': 'gpt-4.1-nano',
        'conv_app_select': 'gpt-4.1-nano',
        'conv_folder': 'gpt-4.1-nano',
        'conv_discard': 'gpt-4.1-nano',
        'daily_summary': 'gpt-4.1-mini',
        'daily_summary_simple': 'gpt-4.1-nano',
        'external_structure': 'gpt-4.1-nano',
        # OpenAI — memories & knowledge
        'memories': 'gpt-4.1-nano',
        'learnings': 'gpt-4.1-mini',
        'memory_conflict': 'gpt-4.1-nano',
        'memory_category': 'gpt-4.1-nano',
        'knowledge_graph': 'gpt-4.1-nano',
        # OpenAI — chat
        'chat_responses': 'gpt-4.1-mini',
        'chat_extraction': 'gpt-4.1-nano',
        'chat_graph': 'gpt-4.1-mini',
        'session_titles': 'gpt-4.1-nano',
        # OpenAI — features
        'goals': 'gpt-4.1-nano',
        'goals_advice': 'gpt-4.1-mini',
        'notifications': 'gpt-4.1-mini',
        'proactive_notification': 'gpt-4.1-nano',
        'followup': 'gpt-4.1-nano',
        'smart_glasses': 'gpt-4.1-nano',
        'onboarding': 'gpt-4.1-nano',
        'app_generator': 'gpt-4.1-mini',
        'app_integration': 'gpt-4.1-nano',
        'persona_clone': 'gpt-4.1-mini',
        'trends': 'gpt-4.1-nano',
        # Anthropic
        'chat_agent': 'claude-haiku-3.5',
        # OpenRouter
        'persona_chat': 'google/gemini-flash-1.5-8b',
        'persona_chat_premium': 'google/gemini-flash-1.5-8b',
        'wrapped_analysis': 'google/gemini-flash-1.5-8b',
        # Perplexity
        'web_search': 'sonar',
    },
    'max': {
        # OpenAI — conversation processing
        'conv_action_items': 'gpt-5.1',
        'conv_structure': 'gpt-5.1',
        'conv_app_result': 'gpt-5.1',
        'conv_app_select': 'gpt-4.1-mini',
        'conv_folder': 'gpt-4.1-mini',
        'conv_discard': 'gpt-4.1-mini',
        'daily_summary': 'gpt-5.1',
        'daily_summary_simple': 'gpt-4.1-mini',
        'external_structure': 'gpt-4.1-mini',
        # OpenAI — memories & knowledge
        'memories': 'gpt-4.1-mini',
        'learnings': 'o4-mini',
        'memory_conflict': 'gpt-4.1-mini',
        'memory_category': 'gpt-4.1-mini',
        'knowledge_graph': 'gpt-4.1-mini',
        # OpenAI — chat
        'chat_responses': 'gpt-5.2',
        'chat_extraction': 'gpt-4.1-mini',
        'chat_graph': 'gpt-4.1',
        'session_titles': 'gpt-4.1-mini',
        # OpenAI — features
        'goals': 'gpt-4.1-mini',
        'goals_advice': 'gpt-5.2',
        'notifications': 'gpt-5.2',
        'proactive_notification': 'gpt-4.1-mini',
        'followup': 'gpt-4.1-mini',
        'smart_glasses': 'gpt-4.1-mini',
        'onboarding': 'gpt-4.1-mini',
        'app_generator': 'gpt-5.2',
        'app_integration': 'gpt-4.1-mini',
        'persona_clone': 'gpt-5.1',
        'trends': 'gpt-4.1-mini',
        # Anthropic
        'chat_agent': 'claude-sonnet-4-6',
        # OpenRouter
        'persona_chat': 'google/gemini-flash-1.5-8b',
        'persona_chat_premium': 'anthropic/claude-3.5-sonnet',
        'wrapped_analysis': 'google/gemini-3-flash-preview',
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

# Provider classification (fixed per feature, not overridable).
_OPENROUTER_FEATURES = {'persona_chat', 'persona_chat_premium', 'wrapped_analysis'}
_ANTHROPIC_FEATURES = {'chat_agent'}
_PERPLEXITY_FEATURES = {'web_search'}

# Feature-specific client config (temperature, headers — orthogonal to model choice).
_OPENROUTER_TEMPERATURES: Dict[str, float] = {
    'persona_chat': 0.8,
    'persona_chat_premium': 0.8,
    'wrapped_analysis': 0.7,
}

# Models that support OpenAI prompt caching (prompt_cache_key routing).
_CACHE_KEY_MODELS = {'gpt-5.1'}


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
        # Warn if override model doesn't match the feature's provider expectations
        if feature in _ANTHROPIC_FEATURES and not override.startswith('claude'):
            logger.warning('QoS override %s=%s may be invalid — feature %s is Anthropic', env_key, override, feature)
        elif feature in _PERPLEXITY_FEATURES and not override.startswith('sonar'):
            logger.warning('QoS override %s=%s may be invalid — feature %s is Perplexity', env_key, override, feature)
        elif feature in _OPENROUTER_FEATURES and '/' not in override:
            logger.warning(
                'QoS override %s=%s may be invalid — feature %s is OpenRouter (expected org/model)',
                env_key,
                override,
                feature,
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
    if feature in _ANTHROPIC_FEATURES:
        raise ValueError(
            f"Feature '{feature}' is Anthropic — use get_model('{feature}') with anthropic_client instead of get_llm()"
        )
    if feature in _PERPLEXITY_FEATURES:
        raise ValueError(
            f"Feature '{feature}' is Perplexity — use get_model('{feature}') with the Perplexity HTTP client instead of get_llm()"
        )

    model = get_model(feature)

    if feature in _OPENROUTER_FEATURES:
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
        provider = (
            'anthropic'
            if feature in _ANTHROPIC_FEATURES
            else (
                'openrouter'
                if feature in _OPENROUTER_FEATURES
                else 'perplexity' if feature in _PERPLEXITY_FEATURES else 'openai'
            )
        )
        info[feature] = {
            'model': get_model(feature),
            'profile': _active_profile_name,
            'provider': provider,
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
