import hashlib
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import anthropic
import httpx
from cachetools import TTLCache
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import tiktoken

from models.structured import Structured
from utils.byok import get_byok_key
from utils.llm.usage_tracker import get_usage_callback

logger = logging.getLogger(__name__)

_usage_callback = get_usage_callback()

# ---------------------------------------------------------------------------
# BYOK (Bring Your Own Key)
#
# Per-request feature that substitutes the user's own API key.
# For get_llm() callers: resolved inline — no wrapper class needed.
# For module-level singletons (anthropic_client, embeddings): proxy classes
# provide lazy resolution since there's no request context at import time.
# ---------------------------------------------------------------------------

# Google's OpenAI-compatible endpoint — used only for BYOK users who bring their
# own AI Studio API key. Platform calls use ChatGoogleGenerativeAI (native SDK).
_GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class _AnthropicClientProxy:
    """Forwards every attribute to the appropriate anthropic.AsyncAnthropic for the request."""

    __slots__ = ('_default',)

    def __init__(self, default: anthropic.AsyncAnthropic):
        object.__setattr__(self, '_default', default)

    def _resolve(self) -> anthropic.AsyncAnthropic:
        byok = get_byok_key('anthropic')
        if byok:
            return _cached_anthropic(byok)
        return self._default

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)


class _OpenAIEmbeddingsProxy:
    """Transparent proxy for OpenAIEmbeddings that uses BYOK OpenAI when set."""

    __slots__ = ('_model', '_default', '_ctor_kwargs')

    def __init__(self, model: str, default: OpenAIEmbeddings, ctor_kwargs: Dict[str, Any]):
        object.__setattr__(self, '_model', model)
        object.__setattr__(self, '_default', default)
        object.__setattr__(self, '_ctor_kwargs', ctor_kwargs)

    def _resolve(self) -> OpenAIEmbeddings:
        byok = get_byok_key('openai')
        if byok:
            cache_key = f"emb:{self._model}:{_hash_key(byok)}"
            inst = _openai_cache.get(cache_key)
            if inst is None:
                inst = OpenAIEmbeddings(model=self._model, api_key=byok, **self._ctor_kwargs)
                _openai_cache[cache_key] = inst
            return inst
        return self._default

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)


_BYOK_CACHE_MAX_SIZE = 256
_BYOK_CACHE_TTL_SECONDS = 3600  # 1 hour

_openai_cache: TTLCache = TTLCache(maxsize=_BYOK_CACHE_MAX_SIZE, ttl=_BYOK_CACHE_TTL_SECONDS)
_anthropic_cache: TTLCache = TTLCache(maxsize=_BYOK_CACHE_MAX_SIZE, ttl=_BYOK_CACHE_TTL_SECONDS)


def _hash_key(api_key: str) -> str:
    """Derive a safe cache key from an API key. Never store raw keys in memory."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def _cached_openai_chat(model: str, api_key: str, ctor_kwargs: Dict[str, Any]) -> ChatOpenAI:
    cache_key = f"{model}:{_hash_key(api_key)}:{hash(frozenset((k, repr(v)) for k, v in ctor_kwargs.items()))}"
    inst = _openai_cache.get(cache_key)
    if inst is None:
        inst = ChatOpenAI(model=model, api_key=api_key, **ctor_kwargs)
        _openai_cache[cache_key] = inst
    return inst


def _cached_anthropic(api_key: str) -> anthropic.AsyncAnthropic:
    cache_key = _hash_key(api_key)
    inst = _anthropic_cache.get(cache_key)
    if inst is None:
        inst = anthropic.AsyncAnthropic(api_key=api_key)
        _anthropic_cache[cache_key] = inst
    return inst


def _create_byok_client(
    model: str, provider: str, byok_key: str, streaming: bool = False, feature: str = ''
) -> Optional[ChatOpenAI]:
    """Create a ChatOpenAI using the user's BYOK key. Returns None if BYOK not supported for this provider."""
    kwargs: Dict[str, Any] = {'callbacks': [_usage_callback]}
    if model == 'gpt-5.1':
        kwargs['extra_body'] = {"prompt_cache_retention": "24h"}
    if streaming:
        kwargs['streaming'] = True
        kwargs['stream_options'] = {"include_usage": True}

    if provider == 'openai':
        return _cached_openai_chat(model, byok_key, kwargs)

    if provider == 'gemini':
        return _cached_openai_chat(model, byok_key, {**kwargs, 'base_url': _GEMINI_OPENAI_BASE_URL})

    if provider == 'openrouter':
        # Gemini-based OpenRouter models reroute to Gemini direct via BYOK
        if model.startswith('gemini'):
            temp = _OPENROUTER_TEMPERATURES.get(feature)
            if temp is not None:
                kwargs['temperature'] = temp
            return _cached_openai_chat(model, byok_key, {**kwargs, 'base_url': _GEMINI_OPENAI_BASE_URL})
        return None  # Non-Gemini OpenRouter: no BYOK support

    return None


# Anthropic client for chat agent (module-level, BYOK-aware)
_default_anthropic_client = anthropic.AsyncAnthropic()  # uses ANTHROPIC_API_KEY env var
anthropic_client = _AnthropicClientProxy(_default_anthropic_client)


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    """Kept as a factory for callers that prefer explicit routing over the module proxy."""
    return anthropic_client._resolve()


def get_openai_chat(model: str, **kwargs) -> ChatOpenAI:
    """Explicit factory; equivalent to using the module-level proxies."""
    byok = get_byok_key('openai')
    if byok:
        return _cached_openai_chat(model, byok, kwargs)
    return ChatOpenAI(model=model, **kwargs)


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
    'persona_chat': 0.8,
    'persona_chat_premium': 0.8,
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


# ---------------------------------------------------------------------------
# Client factories — provider-specific, cached per (model, streaming, provider)
# Each factory creates and caches a plain ChatOpenAI using Omi's default keys.
# BYOK resolution happens inline in get_llm() at request time.
# ---------------------------------------------------------------------------

_llm_cache: Dict[tuple, Any] = {}


def _get_or_create_openai_llm(model_name: str, streaming: bool = False) -> ChatOpenAI:
    """Get or create a cached ChatOpenAI for an OpenAI model."""
    key = (model_name, streaming, 'openai')
    if key not in _llm_cache:
        kwargs: Dict[str, Any] = {'callbacks': [_usage_callback]}
        if model_name == 'gpt-5.1':
            kwargs['extra_body'] = {"prompt_cache_retention": "24h"}
        if streaming:
            kwargs['streaming'] = True
            kwargs['stream_options'] = {"include_usage": True}
        _llm_cache[key] = ChatOpenAI(model=model_name, **kwargs)
    return _llm_cache[key]


def _get_or_create_openrouter_llm(
    model_name: str, streaming: bool = False, temperature: Optional[float] = None
) -> ChatOpenAI:
    """Get or create a cached ChatOpenAI for an OpenRouter model.

    Model names in the profile are bare (e.g. 'gemini-3-flash-preview').
    OpenRouter API requires vendor prefix (e.g. 'google/gemini-3-flash-preview').
    """
    # OpenRouter requires vendor-prefixed model names for Google models.
    api_model = f'google/{model_name}' if model_name.startswith('gemini') else model_name
    key = (model_name, streaming, 'openrouter', temperature)
    if key not in _llm_cache:
        kwargs: Dict[str, Any] = {
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
        _llm_cache[key] = ChatOpenAI(model=api_model, **kwargs)
    return _llm_cache[key]


def _get_or_create_gemini_llm(model_name: str, streaming: bool = False) -> BaseChatModel:
    """Get or create a cached ChatGoogleGenerativeAI for a Gemini model via native SDK.

    Routing priority:
      1. USE_VERTEX_AI=true + GOOGLE_CLOUD_PROJECT → Vertex AI (ADC, paid quota, ~34% savings with EDP)
      2. GEMINI_API_KEY set → AI Studio (paid-tier key, no OpenAI-compat rate limits)
      3. Neither → placeholder that fails at invoke time (unit tests)

    Vertex AI requires explicit opt-in via USE_VERTEX_AI=true because GOOGLE_CLOUD_PROJECT
    is already set for Firestore and the service account may lack Vertex AI permissions.

    BYOK users still go through the OpenAI-compat endpoint via _create_byok_client().
    """
    key = (model_name, streaming, 'gemini')
    if key not in _llm_cache:
        use_vertex = os.environ.get('USE_VERTEX_AI', '').lower() == 'true'
        gcp_project = os.environ.get('GOOGLE_CLOUD_PROJECT', '') if use_vertex else ''
        gemini_key = os.environ.get('GEMINI_API_KEY', '')
        kwargs: Dict[str, Any] = {'callbacks': [_usage_callback]}
        if streaming:
            kwargs['streaming'] = True

        if gcp_project:
            # Vertex AI — explicit opt-in, uses ADC (GOOGLE_APPLICATION_CREDENTIALS)
            gcp_location = os.environ.get('GCP_LOCATION', 'us-central1')
            _llm_cache[key] = ChatGoogleGenerativeAI(
                model=model_name, project=gcp_project, location=gcp_location, **kwargs
            )
        elif gemini_key:
            # AI Studio — uses API key, paid-tier quota
            kwargs['google_api_key'] = gemini_key
            _llm_cache[key] = ChatGoogleGenerativeAI(model=model_name, **kwargs)
        else:
            # No credentials — constructable placeholder, fails at invoke time
            logger.warning('No USE_VERTEX_AI or GEMINI_API_KEY — Gemini calls will fail at invoke time')
            _llm_cache[key] = ChatOpenAI(
                model=model_name, api_key='not-set', base_url=_GEMINI_OPENAI_BASE_URL, **kwargs
            )
    return _llm_cache[key]


def _get_default_client(model: str, provider: str, streaming: bool, feature: str) -> BaseChatModel:
    """Get the cached default client for a model/provider combo."""
    if provider == 'openrouter':
        temp = _OPENROUTER_TEMPERATURES.get(feature)
        return _get_or_create_openrouter_llm(model, streaming, temp)
    if provider == 'gemini':
        return _get_or_create_gemini_llm(model, streaming)
    return _get_or_create_openai_llm(model, streaming)


def _effective_byok_provider(model: str, provider: str) -> str:
    """Map provider to the actual BYOK key type needed (Gemini-based OpenRouter → Gemini key)."""
    if provider == 'openrouter' and model.startswith('gemini'):
        return 'gemini'
    return provider


def get_llm(feature: str, streaming: bool = False, cache_key: Optional[str] = None) -> BaseChatModel:
    """Get the LLM client for a feature based on the active Model QoS profile.

    Works for OpenAI, Gemini, and OpenRouter features. Returns a BaseChatModel
    (ChatOpenAI for OpenAI/OpenRouter, ChatGoogleGenerativeAI for Gemini).
    All share the same interface: .invoke(), .ainvoke(), .stream(), .with_structured_output().
    For Anthropic/Perplexity, use get_model(feature) to get the model string.

    Args:
        feature: Feature name (e.g. 'conv_action_items', 'persona_chat').
        streaming: Whether to return a streaming-enabled client.
        cache_key: Optional prompt cache routing key (OpenAI gpt-5.4/5.4-mini only).

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

    model, provider = _get_model_config(feature)

    if provider == 'anthropic':
        raise ValueError(
            f"Feature '{feature}' resolved to Anthropic model '{model}' — use get_model() with anthropic_client"
        )
    if provider == 'perplexity':
        raise ValueError(
            f"Feature '{feature}' resolved to Perplexity model '{model}' — use get_model() with Perplexity HTTP client"
        )

    # Log structured output compatibility when feature resolves to Gemini
    if feature in _STRUCTURED_OUTPUT_FEATURES and provider == 'gemini':
        logger.debug(
            'QoS structured_output on gemini: feature=%s model=%s profile=%s', feature, model, _active_profile_name
        )

    # BYOK resolution — if the user provided their own key, create a per-request client.
    # When a BYOK QoS profile is configured, upgrade model selection for BYOK users.
    byok_provider = _effective_byok_provider(model, provider)
    byok_key = get_byok_key(byok_provider)

    if byok_key and _byok_profile:
        # Try upgrading to BYOK profile's model selection
        byok_model, byok_prov = _byok_profile.get(feature, (model, provider))
        byok_prov_eff = _effective_byok_provider(byok_model, byok_prov)
        byok_key_for_profile = get_byok_key(byok_prov_eff)
        if byok_key_for_profile:
            logger.debug('BYOK QoS upgrade: feature=%s %s/%s→%s/%s', feature, model, provider, byok_model, byok_prov)
            model, provider = byok_model, byok_prov
            byok_key = byok_key_for_profile

    if byok_key:
        byok_client = _create_byok_client(model, provider, byok_key, streaming, feature)
        result = byok_client if byok_client is not None else _get_default_client(model, provider, streaming, feature)
    else:
        result = _get_default_client(model, provider, streaming, feature)

    if cache_key and model in _CACHE_KEY_MODELS:
        return result.bind(prompt_cache_key=cache_key)
    return result


def get_qos_info() -> Dict[str, Dict[str, str]]:
    """Return full feature→(model, provider) mapping for the active profile (debugging/monitoring)."""
    info: Dict[str, Dict[str, str]] = {}
    all_features = set(_active_profile.keys()) | set(_PINNED_FEATURES.keys())
    for feature in sorted(all_features):
        model, provider = _get_model_config(feature)
        info[feature] = {
            'model': model,
            'profile': _active_profile_name,
            'provider': provider,
        }
    return info


# Startup logging — log active profile so cost issues are traceable.
logger.info('Model QoS profile=%s (%d features)', _active_profile_name, len(_active_profile))
for _feat, (_model, _provider) in sorted(_active_profile.items()):
    logger.info('  QoS %s: %s [%s]', _feat, _model, _provider)
logger.info('BYOK QoS profile=%s', _byok_profile_name)

# Log structured output features on Gemini for compatibility monitoring
_so_gemini = {f for f in _STRUCTURED_OUTPUT_FEATURES if _active_profile.get(f, _DEFAULT_CONFIG)[1] == 'gemini'}
if _so_gemini:
    logger.info('Structured output features on Gemini: %s', ', '.join(sorted(_so_gemini)))


# ---------------------------------------------------------------------------
# Anthropic — model resolved from active QoS profile
# ---------------------------------------------------------------------------
ANTHROPIC_AGENT_MODEL = get_model('chat_agent')
ANTHROPIC_AGENT_COMPLEX_MODEL = get_model('chat_agent')


# ---------------------------------------------------------------------------
# Legacy module-level alias (kept for test compatibility).
# Production code should use get_llm(feature) exclusively.
# ---------------------------------------------------------------------------
llm_mini = ChatOpenAI(model='gpt-4.1-mini', callbacks=[_usage_callback])

# ---------------------------------------------------------------------------
# Embeddings, parser, utilities
# ---------------------------------------------------------------------------
_embeddings_default = OpenAIEmbeddings(model="text-embedding-3-large")
embeddings = _OpenAIEmbeddingsProxy(
    model="text-embedding-3-large",
    default=_embeddings_default,
    ctor_kwargs={},
)
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

    Prefers the per-request BYOK Gemini key; falls back to the process-wide
    env key so non-BYOK callers behave exactly as before.
    """
    api_key = get_byok_key('gemini') or os.environ.get('GEMINI_API_KEY', '')
    url = 'https://generativelanguage.googleapis.com/v1beta/models/embedding-001:embedContent'
    payload = {
        'model': 'models/embedding-001',
        'content': {'parts': [{'text': text}]},
        'taskType': 'RETRIEVAL_QUERY',
    }
    headers = {'x-goog-api-key': api_key, 'Content-Type': 'application/json'}
    resp = httpx.post(url, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()['embedding']['values']
