import hashlib
import logging
import os
from typing import Any, Dict, List, Optional

import anthropic
import httpx
from cachetools import TTLCache
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import tiktoken

from models.structured_extraction import StructuredExtraction
from utils.byok import get_byok_key
from utils.llm.model_config import (
    MODEL_QOS_PROFILES,
    _ANTHROPIC_ONLY_FEATURES,
    _DEFAULT_CONFIG,
    _OPENROUTER_TEMPERATURES,
    _PERPLEXITY_ONLY_FEATURES,
    _PINNED_FEATURES,
    _STRUCTURED_OUTPUT_FEATURES,
    _active_profile,
    _active_profile_name,
    _byok_profile,
    _byok_profile_name,
    get_active_profile,
    get_active_profile_name,
    get_all_configured_features,
    get_byok_profile,
    get_byok_profile_name,
    get_default_config,
    get_model,
    get_provider,
    get_route_options,
    is_anthropic_only_feature,
    is_perplexity_only_feature,
    is_structured_output_feature,
    supports_cache_retention,
    supports_prompt_cache,
    _get_model_config,
)
from utils.llm.providers import (
    ChatGoogleGenerativeAI,  # backward-compat re-export (was here pre-refactor)
    GEMINI_OPENAI_BASE_URL,
    get_default_client,
    get_or_create_gemini_llm as _get_or_create_gemini_llm,
    get_or_create_openai_compatible_llm,
    _llm_cache,
)

try:
    from utils.llm.providers import get_or_create_omi_gateway_llm
except ImportError as exc:
    if exc.name != 'utils.llm.providers' and 'get_or_create_omi_gateway_llm' not in str(exc):
        raise

    def get_or_create_omi_gateway_llm(*_args, **_kwargs):
        raise RuntimeError('Omi gateway LangChain client is unavailable')


try:
    from utils.llm.gateway_client import (
        BACKGROUND_CHAT_EXTRACTION_TIMEOUT_SECONDS,
        CHAT_STRUCTURED_AUTO_LANE_ID,
        feature_auto_lane_id,
        raise_if_gateway_feature_mode_blocks_direct_model_surface,
        should_route_features_through_gateway,
    )
except ImportError as exc:
    if exc.name != 'utils.llm.gateway_client':
        raise

    BACKGROUND_CHAT_EXTRACTION_TIMEOUT_SECONDS = 35.0
    CHAT_STRUCTURED_AUTO_LANE_ID = 'omi:auto:chat-structured'

    def feature_auto_lane_id(feature: str) -> str:
        return f"omi:auto:{feature.replace('_', '-')}"

    def should_route_features_through_gateway() -> bool:
        return False

    def raise_if_gateway_feature_mode_blocks_direct_model_surface(_surface: str) -> None:
        return None


try:
    from utils.llm.gateway_shadow import maybe_wrap_dev_gateway_shadow
except ImportError as exc:
    if exc.name != 'utils.llm.gateway_shadow':
        raise

    def maybe_wrap_dev_gateway_shadow(*, legacy_model, **_kwargs):
        return legacy_model


from utils.llm.usage_tracker import get_usage_callback

logger = logging.getLogger(__name__)

_usage_callback = get_usage_callback()
_GEMINI_OPENAI_BASE_URL = GEMINI_OPENAI_BASE_URL

# ---------------------------------------------------------------------------
# BYOK (Bring Your Own Key)
#
# Per-request feature that substitutes the user's own API key.
# For get_llm() callers: resolved inline — no wrapper class needed.
# For module-level singletons (anthropic_client, embeddings): proxy classes
# provide lazy resolution since there's no request context at import time.
# ---------------------------------------------------------------------------


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

    @staticmethod
    def _is_key_failure(e: Exception) -> bool:
        # A user's BYOK OpenAI key being out of quota / invalid / rate-limited must not
        # silently break memory search (it would return empty). Detect those and fall
        # back to Omi's key instead. Heuristic on the error text — embeddings have no
        # typed error here, and a false positive only means one extra default-key call.
        s = str(e).lower()
        return any(
            k in s
            for k in (
                'insufficient_quota',
                'exceeded your current quota',
                'invalid_api_key',
                'incorrect api key',
                'invalid api key',
                'model_not_found',
                'does not have access to model',
                'permissiondeniederror',
                'permission denied',
                '403 forbidden',
                'error code: 403',
                'rate_limit',
                ' 429',
                ' 401',
            )
        )

    def embed_query(self, text: str) -> List[float]:
        inst = self._resolve()
        try:
            return inst.embed_query(text)
        except Exception as e:
            if inst is not self._default and self._is_key_failure(e):
                logger.warning("BYOK OpenAI embeddings failed (%s); falling back to Omi key", type(e).__name__)
                return self._default.embed_query(text)
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        inst = self._resolve()
        try:
            return inst.embed_documents(texts)
        except Exception as e:
            if inst is not self._default and self._is_key_failure(e):
                logger.warning("BYOK OpenAI embeddings failed (%s); falling back to Omi key", type(e).__name__)
                return self._default.embed_documents(texts)
            raise

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
        inst = anthropic.AsyncAnthropic(api_key=api_key, timeout=120.0, max_retries=1)
        _anthropic_cache[cache_key] = inst
    return inst


def _create_byok_client(
    model: str, provider: str, byok_key: str, streaming: bool = False, feature: str = ''
) -> Optional[ChatOpenAI]:
    """Create a ChatOpenAI using the user's BYOK key. Returns None if BYOK not supported for this provider."""
    kwargs: Dict[str, Any] = {'callbacks': [_usage_callback], 'request_timeout': 120, 'max_retries': 1}
    if supports_cache_retention(model):
        kwargs['extra_body'] = {"prompt_cache_retention": "24h"}
    if streaming:
        kwargs['streaming'] = True
        kwargs['stream_options'] = {"include_usage": True}

    if provider == 'openai':
        return _cached_openai_chat(model, byok_key, kwargs)

    if provider == 'gemini':
        return _cached_openai_chat(model, byok_key, {**kwargs, 'base_url': GEMINI_OPENAI_BASE_URL})

    if provider == 'openrouter':
        # Gemini-based OpenRouter models reroute to Gemini direct via BYOK
        if model.startswith('gemini'):
            route_options = get_route_options(feature, model, provider)
            if 'temperature' in route_options:
                kwargs['temperature'] = route_options['temperature']
            return _cached_openai_chat(model, byok_key, {**kwargs, 'base_url': GEMINI_OPENAI_BASE_URL})
        return None  # Non-Gemini OpenRouter: no BYOK support

    return None


# Anthropic client for chat agent (module-level, BYOK-aware)
_default_anthropic_client = anthropic.AsyncAnthropic(timeout=120.0, max_retries=1)
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
# Model QoS and provider routing
# ---------------------------------------------------------------------------


def _effective_byok_provider(model: str, provider: str) -> str:
    """Map provider to the actual BYOK key type needed (Gemini-based OpenRouter → Gemini key)."""
    if provider == 'openrouter' and model.startswith('gemini'):
        return 'gemini'
    return provider


# Compatibility wrappers for tests and legacy imports. New provider construction
# lives in providers.py.
def _get_or_create_openai_llm(model_name: str, streaming: bool = False) -> ChatOpenAI:
    options: Dict[str, Any] = {}
    if supports_cache_retention(model_name):
        options['extra_body'] = {"prompt_cache_retention": "24h"}
    return get_or_create_openai_compatible_llm('openai', model_name, streaming, options)


def _get_or_create_openrouter_llm(
    model_name: str, streaming: bool = False, temperature: Optional[float] = None
) -> ChatOpenAI:
    options: Dict[str, Any] = {}
    if temperature is not None:
        options['temperature'] = temperature
    return get_or_create_openai_compatible_llm('openrouter', model_name, streaming, options)


def get_llm(feature: str, streaming: bool = False, cache_key: Optional[str] = None) -> BaseChatModel:
    """Get the LLM client for a feature based on the active Model QoS profile.

    Works for OpenAI, Gemini, OpenRouter, and other registered OpenAI-compatible
    providers. Returns a BaseChatModel. For Anthropic/Perplexity, use
    get_model(feature) to get the model string and the provider-specific client.
    """
    gateway_feature_mode = should_route_features_through_gateway()

    if is_anthropic_only_feature(feature) and not gateway_feature_mode:
        raise ValueError(
            f"Feature '{feature}' is Anthropic — use get_model('{feature}') with anthropic_client instead of get_llm()"
        )
    if is_perplexity_only_feature(feature) and not gateway_feature_mode:
        raise ValueError(
            f"Feature '{feature}' is Perplexity — use get_model('{feature}') with the Perplexity HTTP client instead of get_llm()"
        )

    model, provider = _get_model_config(feature)

    if provider == 'anthropic' and not gateway_feature_mode:
        raise ValueError(
            f"Feature '{feature}' resolved to Anthropic model '{model}' — use get_model() with anthropic_client"
        )
    if provider == 'perplexity' and not gateway_feature_mode:
        raise ValueError(
            f"Feature '{feature}' resolved to Perplexity model '{model}' — use get_model() with Perplexity HTTP client"
        )

    if is_structured_output_feature(feature) and provider == 'gemini':
        logger.debug(
            'QoS structured_output on gemini: feature=%s model=%s profile=%s',
            feature,
            model,
            get_active_profile_name(),
        )

    byok_provider = _effective_byok_provider(model, provider)
    byok_key = get_byok_key(byok_provider)
    byok_profile = get_byok_profile()

    if byok_key and byok_profile:
        byok_model, byok_prov = byok_profile.get(feature, (model, provider))
        byok_prov_eff = _effective_byok_provider(byok_model, byok_prov)
        byok_key_for_profile = get_byok_key(byok_prov_eff)
        if byok_key_for_profile:
            logger.debug('BYOK QoS upgrade: feature=%s %s/%s→%s/%s', feature, model, provider, byok_model, byok_prov)
            model, provider = byok_model, byok_prov
            byok_key = byok_key_for_profile

    if byok_key and gateway_feature_mode:
        raise_if_gateway_feature_mode_blocks_direct_model_surface(f'get_llm.{feature}.byok')

    if byok_key:
        byok_client = _create_byok_client(model, provider, byok_key, streaming, feature)
        result = (
            byok_client
            if byok_client is not None
            else get_default_client(model, provider, streaming, get_route_options(feature, model, provider))
        )
    elif gateway_feature_mode:
        result = get_or_create_omi_gateway_llm(feature_auto_lane_id(feature), streaming)
    else:
        result = get_default_client(model, provider, streaming, get_route_options(feature, model, provider))

    result = maybe_wrap_dev_gateway_shadow(
        feature=feature,
        model=model,
        provider=provider,
        streaming=streaming,
        legacy_model=result,
    )

    if cache_key and supports_prompt_cache(model):
        return result.bind(prompt_cache_key=cache_key)
    return result


def get_llm_gateway_chat_structured(
    streaming: bool = False,
    cache_key: Optional[str] = None,
    request_timeout: float | None = None,
) -> BaseChatModel:
    """Return the gateway chat-structured lane as a LangChain chat model.

    Use this for shadow/eval comparisons that must preserve the existing
    LangChain prompt and parser chain shape. Live feature routing should still
    go through ``get_llm(feature)`` until an explicit rollout promotes the
    gateway provider for that feature.
    """

    result = get_or_create_omi_gateway_llm(
        CHAT_STRUCTURED_AUTO_LANE_ID,
        streaming,
        options={
            'request_timeout': (
                request_timeout if request_timeout is not None else BACKGROUND_CHAT_EXTRACTION_TIMEOUT_SECONDS
            )
        },
    )
    if cache_key:
        return result.bind(prompt_cache_key=cache_key)
    return result


def get_qos_info() -> Dict[str, Dict[str, str]]:
    """Return full feature→(model, provider) mapping for the active profile (debugging/monitoring)."""
    info: Dict[str, Dict[str, str]] = {}
    all_features = get_all_configured_features()
    for feature in sorted(all_features):
        model, provider = _get_model_config(feature)
        info[feature] = {
            'model': model,
            'profile': get_active_profile_name(),
            'provider': provider,
        }
    return info


# Startup logging — log active profile so cost issues are traceable.
_active_profile = get_active_profile()
logger.info('Model QoS profile=%s (%d features)', get_active_profile_name(), len(_active_profile))
for _feat, (_model, _provider) in sorted(_active_profile.items()):
    logger.info('  QoS %s: %s [%s]', _feat, _model, _provider)
logger.info('BYOK QoS profile=%s', get_byok_profile_name())

_so_gemini = {f for f in _active_profile if is_structured_output_feature(f) and _get_model_config(f)[1] == 'gemini'}
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
llm_mini = ChatOpenAI(model='gpt-4.1-mini', callbacks=[_usage_callback], request_timeout=120, max_retries=1)

# ---------------------------------------------------------------------------
# Embeddings, parser, utilities
# ---------------------------------------------------------------------------
_embeddings_default = OpenAIEmbeddings(model="text-embedding-3-large")
embeddings = _OpenAIEmbeddingsProxy(
    model="text-embedding-3-large",
    default=_embeddings_default,
    ctor_kwargs={},
)
parser = PydanticOutputParser(pydantic_object=StructuredExtraction)

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
