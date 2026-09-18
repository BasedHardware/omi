# ruff: noqa: F401
import hashlib
import logging
import os
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional

import anthropic
import httpx
from cachetools import TTLCache
from langchain_anthropic import ChatAnthropic

try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError:

    class BaseCallbackHandler:
        pass


from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import tiktoken

from models.structured_extraction import StructuredExtraction
from utils.byok import get_byok_key
from utils.llm.byok_errors import handle_llm_error
from utils.observability.fallback import record_fallback
from utils.llm.model_config import (
    MODEL_QOS_PROFILES,
    _ANTHROPIC_ONLY_FEATURES,
    _OPENROUTER_TEMPERATURES,
    _PERPLEXITY_ONLY_FEATURES,
    _PINNED_FEATURES,
    _STRUCTURED_OUTPUT_FEATURES,
    _active_profile,
    _active_profile_name,
    _byok_profile,
    _byok_profile_name,
    feature_request_timeout,
    get_active_profile,
    get_active_profile_name,
    get_all_configured_features,
    get_byok_profile,
    get_byok_profile_name,
    get_model,
    get_provider,
    get_route_options,
    is_anthropic_only_feature,
    is_perplexity_only_feature,
    is_structured_output_feature,
    supports_cache_retention,
    supports_prompt_cache,
    _get_model_config,
)  # noqa: F401 - legacy clients-module QoS re-exports
from utils.llm.providers import (
    ChatGoogleGenerativeAI,
    GEMINI_OPENAI_BASE_URL,
    get_default_client,
    get_or_create_gemini_llm as _get_or_create_gemini_llm,
    get_or_create_openai_compatible_llm,
    _llm_cache,
)  # noqa: F401 - legacy clients-module provider re-exports

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
        ainvoke_openai_embeddings_gateway,
        feature_auto_lane_id,
        invoke_gemini_embedding_gateway,
        invoke_openai_embeddings_gateway,
        is_gateway_route_absent,
        raise_if_gateway_feature_mode_blocks_direct_model_surface,
        should_route_chat_agent_through_gateway,
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

    def should_route_chat_agent_through_gateway() -> bool:
        return False

    def raise_if_gateway_feature_mode_blocks_direct_model_surface(_surface: str) -> None:
        return None

    def is_gateway_route_absent(_error: object) -> bool:
        return False

    def invoke_openai_embeddings_gateway(*_args, **_kwargs):
        raise RuntimeError('Omi gateway embeddings client is unavailable')

    async def ainvoke_openai_embeddings_gateway(*_args, **_kwargs):
        raise RuntimeError('Omi gateway embeddings client is unavailable')

    def invoke_gemini_embedding_gateway(*_args, **_kwargs):
        raise RuntimeError('Omi gateway embeddings client is unavailable')


try:
    from utils.llm.gateway_byok import get_or_create_omi_gateway_llm_for_byok
except ImportError:

    def get_or_create_omi_gateway_llm_for_byok(*_args, **_kwargs):
        raise RuntimeError('BYOK gateway LangChain client is unavailable')


try:
    from utils.llm.gateway_anthropic import get_gateway_anthropic_client
except ImportError:

    def get_gateway_anthropic_client(*, byok_api_key=None):
        raise RuntimeError('Omi gateway Anthropic client is unavailable')


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


class _LLMErrorCallback(BaseCallbackHandler):
    """LangChain callback that tags provider errors with platform/BYOK source."""

    def __init__(self, provider: str, model: str = '', feature: str = ''):
        self.provider = provider
        self.model = model
        self.feature = feature

    def on_llm_error(self, error: BaseException, **kwargs) -> None:
        if isinstance(error, Exception):
            handle_llm_error(error, self.provider, feature=self.feature, model=self.model)


_llm_error_callbacks = {}


def _get_llm_error_callback(provider: str, model: str = '', feature: str = '') -> _LLMErrorCallback:
    key = (provider, model, feature)
    if key not in _llm_error_callbacks:
        _llm_error_callbacks[key] = _LLMErrorCallback(provider, model=model, feature=feature)
    return _llm_error_callbacks[key]


def _with_llm_callbacks(kwargs: Dict[str, Any], provider: str, model: str = '', feature: str = '') -> Dict[str, Any]:
    result = dict(kwargs)
    callbacks = list(result.get('callbacks') or [])
    if _usage_callback not in callbacks:
        callbacks.append(_usage_callback)
    error_callback = _get_llm_error_callback(provider, model=model, feature=feature)
    if error_callback not in callbacks:
        callbacks.append(error_callback)
    result['callbacks'] = callbacks
    return result


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

    def __init__(self, default: Optional[anthropic.AsyncAnthropic] = None):
        object.__setattr__(self, '_default', default)

    def _default_client(self) -> anthropic.AsyncAnthropic:
        default = self._default
        if default is None:
            default = anthropic.AsyncAnthropic(timeout=120.0, max_retries=1)
            object.__setattr__(self, '_default', default)
        return default

    def _resolve(self) -> anthropic.AsyncAnthropic:
        byok = get_byok_key('anthropic')
        # Only pin Anthropic Messages through the gateway when agentic chat is
        # itself on the gateway route. FEATURE_MODE alone must not force the
        # Anthropic Messages client onto omi:auto:chat-agent (surface mismatch
        # with the Luna/OpenAI lane).
        if should_route_chat_agent_through_gateway():
            return get_gateway_anthropic_client(byok_api_key=byok)
        if byok:
            return _cached_anthropic(byok)
        return self._default_client()

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)


def get_direct_anthropic_client(*, byok_api_key: str | None = None) -> anthropic.AsyncAnthropic:
    """Return Anthropic without consulting the feature gateway switch.

    Desktop chat has a legacy Anthropic fallback for BYOK and specialist model
    requests. Calling the module-level proxy there would re-enter the managed
    gateway whenever the global feature flag is enabled.
    """
    if byok_api_key:
        return _cached_anthropic(byok_api_key)
    return anthropic_client._default_client()


_gateway_embeddings_route_absent_warned = False


def _warn_gateway_embeddings_route_absent(operation: str) -> None:
    """Report gateway/backend deploy skew: one metric per degrade, one log per process.

    The fallback telemetry fires on every degrade (``backend/AGENTS.md`` rule
    10 / ``docs/agents/fallback-telemetry.md``: a branch that changes mode MUST
    call ``record_fallback``), because ``omi_fallback_total`` is how operators
    see how much embeddings traffic and ledger spend is bypassing the gateway
    while the skew lasts. The narrative ERROR log stays once per process: the
    condition holds until the gateway is redeployed, the callers behind it run
    thousands of embeddings an hour, and the gateway's own access log keeps
    counting the 404s, so nothing is lost by not repeating ourselves there.
    """
    global _gateway_embeddings_route_absent_warned
    record_fallback(
        component='llm_gateway',
        from_mode='gateway_embeddings',
        to_mode='direct_embeddings',
        reason='capability_mismatch',
        outcome='degraded',
        log=logger,
    )
    if _gateway_embeddings_route_absent_warned:
        return
    _gateway_embeddings_route_absent_warned = True
    logger.error(
        'LLM gateway serves no /v1/embeddings route: the deployed gateway predates this backend. '
        'Falling back to direct embeddings; gateway ledger accounting is lost for embeddings until '
        'the gateway is redeployed. operation=%s',
        operation,
    )


class _OpenAIEmbeddingsProxy:
    """Transparent proxy for OpenAIEmbeddings that uses BYOK OpenAI when set."""

    __slots__ = ('_model', '_default', '_ctor_kwargs')
    _METHODS_TO_WRAP = {'embed_documents', 'aembed_documents', 'embed_query', 'aembed_query'}

    def __init__(self, model: str, default: Optional[OpenAIEmbeddings], ctor_kwargs: Dict[str, Any]):
        object.__setattr__(self, '_model', model)
        object.__setattr__(self, '_default', default)
        object.__setattr__(self, '_ctor_kwargs', ctor_kwargs)

    def _default_client(self) -> OpenAIEmbeddings:
        default = self._default
        if default is None:
            default = OpenAIEmbeddings(model=self._model, **self._ctor_kwargs)
            object.__setattr__(self, '_default', default)
        return default

    def _resolve(self) -> OpenAIEmbeddings:
        byok = get_byok_key('openai')
        if byok:
            cache_key = f"emb:{self._model}:{_hash_key(byok)}"
            inst = _openai_cache.get(cache_key)
            if inst is None:
                inst = OpenAIEmbeddings(model=self._model, api_key=byok, **self._ctor_kwargs)
                _openai_cache[cache_key] = inst
            return inst
        return self._default_client()

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

    def _gateway_mode(self) -> bool:
        """Whether embeddings hop the gateway ledger lane.

        A misconfigured prod rollout raises RuntimeError; embeddings are
        load-bearing for memory/vector search, so that degrades to the direct
        kill-switch path instead of failing closed.
        """
        try:
            return should_route_features_through_gateway()
        except RuntimeError:
            return False

    def _is_gateway_key_failure(self, error: Exception) -> bool:
        if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in {401, 403, 429}:
            return True
        return self._is_key_failure(error)

    def _reraise_unless_route_absent(self, error: Exception, operation: str) -> None:
        """Swallow only "this gateway has no embeddings route" so the caller
        falls through to the direct path; re-raise everything else.

        A gateway deployed before this backend 404s the route, and embeddings
        are load-bearing for memory and vector search -- without this, that
        skew fails every conversation finalization instead of costing us the
        gateway ledger row. This is the same availability-over-accounting
        trade ``_gateway_mode`` already makes for a misconfigured rollout,
        applied to the one skew it could not see: a healthy gateway that is
        simply older than its client.
        """
        if not is_gateway_route_absent(error):
            raise error
        _warn_gateway_embeddings_route_absent(operation)

    def _gateway_embed_texts(self, texts: List[str]) -> List[List[float]]:
        byok = get_byok_key('openai')
        try:
            return invoke_openai_embeddings_gateway(texts, byok_api_key=byok)
        except Exception as e:
            if byok:
                handle_llm_error(e, 'openai', feature='embeddings', model=self._model, operation='embed_documents')
                if self._is_gateway_key_failure(e):
                    logger.warning(
                        "BYOK gateway OpenAI embeddings failed (%s); falling back to Omi key", type(e).__name__
                    )
                    return invoke_openai_embeddings_gateway(texts)
            raise

    async def _agateway_embed_texts(self, texts: List[str]) -> List[List[float]]:
        byok = get_byok_key('openai')
        try:
            return await ainvoke_openai_embeddings_gateway(texts, byok_api_key=byok)
        except Exception as e:
            if byok:
                handle_llm_error(e, 'openai', feature='embeddings', model=self._model, operation='aembed_documents')
                if self._is_gateway_key_failure(e):
                    logger.warning(
                        "BYOK gateway OpenAI embeddings failed (%s); falling back to Omi key", type(e).__name__
                    )
                    return await ainvoke_openai_embeddings_gateway(texts)
            raise

    def embed_query(self, text: str) -> List[float]:
        if self._gateway_mode():
            try:
                return self._gateway_embed_texts([text])[0]
            except Exception as e:
                self._reraise_unless_route_absent(e, 'embed_query')
        inst = self._resolve()
        try:
            return inst.embed_query(text)
        except Exception as e:
            if inst is not self._default:
                handle_llm_error(e, 'openai', feature='embeddings', model=self._model, operation='embed_query')
                if self._is_key_failure(e):
                    logger.warning("BYOK OpenAI embeddings failed (%s); falling back to Omi key", type(e).__name__)
                    return self._default_client().embed_query(text)
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if self._gateway_mode():
            try:
                return self._gateway_embed_texts(texts)
            except Exception as e:
                self._reraise_unless_route_absent(e, 'embed_documents')
        inst = self._resolve()
        try:
            return inst.embed_documents(texts)
        except Exception as e:
            if inst is not self._default:
                handle_llm_error(e, 'openai', feature='embeddings', model=self._model, operation='embed_documents')
                if self._is_key_failure(e):
                    logger.warning("BYOK OpenAI embeddings failed (%s); falling back to Omi key", type(e).__name__)
                    return self._default_client().embed_documents(texts)
            raise

    async def aembed_query(self, text: str) -> List[float]:
        if self._gateway_mode():
            try:
                return (await self._agateway_embed_texts([text]))[0]
            except Exception as e:
                self._reraise_unless_route_absent(e, 'aembed_query')
        inst = self._resolve()
        try:
            return await inst.aembed_query(text)
        except Exception as e:
            if inst is not self._default:
                handle_llm_error(e, 'openai', feature='embeddings', model=self._model, operation='aembed_query')
                if self._is_key_failure(e):
                    logger.warning("BYOK OpenAI embeddings failed (%s); falling back to Omi key", type(e).__name__)
                    return await self._default_client().aembed_query(text)
            raise

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        if self._gateway_mode():
            try:
                return await self._agateway_embed_texts(texts)
            except Exception as e:
                self._reraise_unless_route_absent(e, 'aembed_documents')
        inst = self._resolve()
        try:
            return await inst.aembed_documents(texts)
        except Exception as e:
            if inst is not self._default:
                handle_llm_error(e, 'openai', feature='embeddings', model=self._model, operation='aembed_documents')
                if self._is_key_failure(e):
                    logger.warning("BYOK OpenAI embeddings failed (%s); falling back to Omi key", type(e).__name__)
                    return await self._default_client().aembed_documents(texts)
            raise

    def __getattr__(self, name: str):
        inst = self._resolve()
        attr = getattr(inst, name)
        if name not in self._METHODS_TO_WRAP or not callable(attr):
            return attr
        if name.startswith('a'):

            async def _wrapped_async(*args, **kwargs):
                try:
                    return await attr(*args, **kwargs)
                except Exception as e:
                    if inst is not self._default:
                        handle_llm_error(e, 'openai', feature='embeddings', model=self._model, operation=name)
                        if self._is_key_failure(e):
                            logger.warning(
                                "BYOK OpenAI embeddings failed (%s); falling back to Omi key", type(e).__name__
                            )
                            return await getattr(self._default_client(), name)(*args, **kwargs)
                    raise

            return _wrapped_async

        def _wrapped(*args, **kwargs):
            try:
                return attr(*args, **kwargs)
            except Exception as e:
                if inst is not self._default:
                    handle_llm_error(e, 'openai', feature='embeddings', model=self._model, operation=name)
                    if self._is_key_failure(e):
                        logger.warning("BYOK OpenAI embeddings failed (%s); falling back to Omi key", type(e).__name__)
                        return getattr(self._default_client(), name)(*args, **kwargs)
                raise

        return _wrapped


_BYOK_CACHE_MAX_SIZE = 256
_BYOK_CACHE_TTL_SECONDS = 3600  # 1 hour

_openai_cache: TTLCache = TTLCache(maxsize=_BYOK_CACHE_MAX_SIZE, ttl=_BYOK_CACHE_TTL_SECONDS)
_anthropic_cache: TTLCache = TTLCache(maxsize=_BYOK_CACHE_MAX_SIZE, ttl=_BYOK_CACHE_TTL_SECONDS)
_anthropic_chat_cache: TTLCache = TTLCache(maxsize=_BYOK_CACHE_MAX_SIZE, ttl=_BYOK_CACHE_TTL_SECONDS)


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


def _cached_anthropic_chat(model: str, api_key: str, ctor_kwargs: Dict[str, Any]) -> ChatAnthropic:
    cache_key = f"{model}:{_hash_key(api_key)}:{hash(frozenset((k, repr(v)) for k, v in ctor_kwargs.items()))}"
    inst = _anthropic_chat_cache.get(cache_key)
    if inst is None:
        inst = ChatAnthropic(model=model, api_key=api_key, **ctor_kwargs)
        _anthropic_chat_cache[cache_key] = inst
    return inst


def _create_byok_client(
    model: str, provider: str, byok_key: str, streaming: bool = False, feature: str = ''
) -> Optional[BaseChatModel]:
    """Create a ChatOpenAI using the user's BYOK key. Returns None if BYOK not supported for this provider."""
    callback_provider = _effective_byok_provider(model, provider)
    kwargs: Dict[str, Any] = _with_llm_callbacks(
        {'request_timeout': 120, 'max_retries': 1}, callback_provider, model=model, feature=feature
    )
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
        route_options = get_route_options(feature, model, provider)
        if 'temperature' in route_options:
            kwargs['temperature'] = route_options['temperature']
        routed_model = f'google/{model}' if model.startswith('gemini') else model
        return _cached_openai_chat(
            routed_model,
            byok_key,
            {**kwargs, 'base_url': 'https://openrouter.ai/api/v1', 'default_headers': {'X-Title': 'Omi Chat'}},
        )

    if provider == 'anthropic':
        anthropic_kwargs = dict(kwargs)
        anthropic_kwargs['timeout'] = anthropic_kwargs.pop('request_timeout')
        # stream_options is an OpenAI-only transport knob; ChatAnthropic would
        # silently forward it into model_kwargs, so strip it before construction.
        anthropic_kwargs.pop('stream_options', None)
        return _cached_anthropic_chat(model, byok_key, anthropic_kwargs)

    return None


# Anthropic client for chat agent (module-level, BYOK-aware).
# The proxy constructs the provider client at its first use so importing a
# deployable entrypoint never needs provider credentials.
anthropic_client = _AnthropicClientProxy()


def get_openai_chat(model: str, **kwargs) -> ChatOpenAI:
    """Explicit factory; equivalent to using the module-level proxies."""
    kwargs = _with_llm_callbacks(kwargs, 'openai', model=model)
    byok = get_byok_key('openai')
    if byok:
        return _cached_openai_chat(model, byok, kwargs)
    return ChatOpenAI(model=model, **kwargs)


# ---------------------------------------------------------------------------
# Model QoS and provider routing
# ---------------------------------------------------------------------------


def _effective_byok_provider(model: str, provider: str) -> str:
    """Return the credential provider required by the resolved route."""
    return provider


def _byok_fallback_model(provider: str) -> str:
    if provider == 'openai':
        return 'gpt-4o-mini'
    if provider in {'gemini', 'openrouter'}:
        return 'gemini-2.5-flash-lite'
    if provider == 'anthropic':
        return 'claude-sonnet-4-6'
    return ''


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


def get_llm(
    feature: str,
    streaming: bool = False,
    cache_key: Optional[str] = None,
    prompt_cache_options: Optional[dict[str, str]] = None,
    request_timeout: float | None = None,
    max_retries: int | None = None,
) -> BaseChatModel:
    """Get the LLM client for a feature based on the active Model QoS profile.

    Works for OpenAI, Gemini, OpenRouter, and other registered OpenAI-compatible
    providers. Returns a BaseChatModel. For Anthropic/Perplexity, use
    get_model(feature) to get the model string and the provider-specific client.
    """
    gateway_feature_mode = should_route_features_through_gateway()
    # Chat-agent has its own kill switch. FEATURE_MODE=gateway plus
    # CHAT_AGENT_ROUTE=direct must stay on direct OpenAI/Luna, not the gateway lane
    # and not a leftover Anthropic Messages client.
    route_through_gateway = (
        should_route_chat_agent_through_gateway() if feature == 'chat_agent' else gateway_feature_mode
    )

    if is_anthropic_only_feature(feature) and not gateway_feature_mode:
        raise ValueError(
            f"Feature '{feature}' is Anthropic — use get_model('{feature}') with anthropic_client instead of get_llm()"
        )
    if is_perplexity_only_feature(feature) and not gateway_feature_mode:
        raise ValueError(
            f"Feature '{feature}' is Perplexity — use get_model('{feature}') with the Perplexity HTTP client instead of get_llm()"
        )

    if request_timeout is None:
        # The deadline is a property of the feature, not of the call site: a feature that
        # summarizes a whole conversation while a user waits cannot answer inside the
        # background gateway transport deadline. Three separate call-site fixes proved that
        # leaving this to each caller loses the user's summary (see model_config).
        request_timeout = feature_request_timeout(feature)

    model, provider = _get_model_config(feature)
    # The feature lane (feature_auto_lane_id) is pinned to the feature's
    # resolved provider. When BYOK selection below switches providers, the
    # gateway lane for this feature still routes to the original provider, so a
    # provider-switched BYOK request must bypass the fixed lane and use the
    # direct client — the gateway would otherwise reject the forwarded key
    # with missing_byok_key. Keep the pre-selection provider to detect the switch.
    lane_provider = _effective_byok_provider(model, provider)

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

    byok_profile = get_byok_profile()
    byok_key = None
    byok_provider = _effective_byok_provider(model, provider)

    if byok_profile:
        profile_model, profile_provider = byok_profile.get(feature, (model, provider))
        profile_key = get_byok_key(_effective_byok_provider(profile_model, profile_provider))
        if profile_key:
            model, provider, byok_key = profile_model, profile_provider, profile_key
            byok_provider = _effective_byok_provider(model, provider)
        else:
            byok_key = get_byok_key(byok_provider)
    else:
        byok_key = get_byok_key(byok_provider)

    if not byok_key:
        # Gemini and Anthropic have direct BYOK clients — do not override
        feature_has_direct_byok = byok_provider in ('gemini', 'anthropic')
        if not feature_has_direct_byok:
            preferred_openrouter_key = get_byok_key('openrouter')
            if preferred_openrouter_key:
                model = _byok_fallback_model('openrouter')
                provider = 'openrouter'
                byok_provider = 'openrouter'
                byok_key = preferred_openrouter_key

    if not byok_key:
        configured_provider = provider
        for candidate in ('openrouter', 'openai', 'gemini', 'anthropic'):
            candidate_key = get_byok_key(candidate)
            if candidate_key:
                provider = candidate
                byok_provider = candidate
                byok_key = candidate_key
                model = _byok_fallback_model(candidate)
                record_fallback(
                    component='other',
                    from_mode=configured_provider,
                    to_mode=candidate,
                    reason='byok',
                    outcome='recovered',
                    log=logger,
                )
                break

    if byok_key and byok_profile:
        byok_model, byok_prov = byok_profile.get(feature, (model, provider))
        byok_prov_eff = _effective_byok_provider(byok_model, byok_prov)
        byok_key_for_profile = get_byok_key(byok_prov_eff)
        if byok_key_for_profile:
            logger.debug('BYOK QoS upgrade: feature=%s %s/%s→%s/%s', feature, model, provider, byok_model, byok_prov)
            model, provider = byok_model, byok_prov
            byok_key = byok_key_for_profile

    effective_provider = _effective_byok_provider(model, provider)
    # VertexGeminiProvider._reject_byok() — Gemini BYOK must use the direct
    # OpenAI-compatible client, not the gateway lane.
    gateway_accepts_byok = effective_provider != "gemini"
    if byok_key and route_through_gateway and effective_provider == lane_provider and gateway_accepts_byok:
        # A BYOK user's request runs the same feature prompt on the same lane, so it needs the
        # same deadline as the omi-managed branch below; without this it silently kept the
        # background transport deadline.
        byok_gateway_options: Dict[str, Any] = {}
        if request_timeout is not None:
            byok_gateway_options["request_timeout"] = request_timeout
        if max_retries is not None:
            byok_gateway_options["max_retries"] = max_retries
        result = get_or_create_omi_gateway_llm_for_byok(
            feature_auto_lane_id(feature),
            provider=effective_provider,
            api_key=byok_key,
            streaming=streaming,
            options=byok_gateway_options or None,
            feature=feature,
        )
    elif byok_key:
        byok_client = _create_byok_client(model, provider, byok_key, streaming, feature)
        result = (
            byok_client
            if byok_client is not None
            else get_default_client(model, provider, streaming, get_route_options(feature, model, provider))
        )
    elif route_through_gateway:
        gateway_options = {}
        if request_timeout is not None:
            gateway_options["request_timeout"] = request_timeout
        if max_retries is not None:
            gateway_options["max_retries"] = max_retries
        result = get_or_create_omi_gateway_llm(
            feature_auto_lane_id(feature), streaming, gateway_options or None, feature=feature
        )
    else:
        route_options = get_route_options(feature, model, provider)
        if request_timeout is not None:
            route_options = {**route_options, "request_timeout": request_timeout}
        if max_retries is not None:
            route_options = {**route_options, "max_retries": max_retries}
        result = get_default_client(model, provider, streaming, route_options)

    result = maybe_wrap_dev_gateway_shadow(
        feature=feature,
        model=model,
        provider=provider,
        streaming=streaming,
        legacy_model=result,
    )

    cache_params: Dict[str, Any] = {}
    if cache_key and supports_prompt_cache(model):
        cache_params['prompt_cache_key'] = cache_key
    if prompt_cache_options and model.startswith('gpt-5.6'):
        # This is a provider request field, not a ChatOpenAI constructor field.
        # extra_body lets the OpenAI client merge it into the wire payload. It
        # must be sent even without a cache key: explicit mode with no
        # breakpoint is how unique prompts opt out of billable cache writes.
        cache_params['extra_body'] = {'prompt_cache_options': prompt_cache_options}
    if cache_params:
        return result.bind(**cache_params)
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
        feature='chat_extraction',
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
_active_qos_profile = get_active_profile()
logger.info('Model QoS profile=%s (%d features)', get_active_profile_name(), len(_active_qos_profile))
for _feat, (_model, _provider) in sorted(_active_qos_profile.items()):
    logger.info('  QoS %s: %s [%s]', _feat, _model, _provider)
logger.info('BYOK QoS profile=%s', get_byok_profile_name())

_so_gemini = {f for f in _active_qos_profile if is_structured_output_feature(f) and _get_model_config(f)[1] == 'gemini'}
if _so_gemini:
    logger.info('Structured output features on Gemini: %s', ', '.join(sorted(_so_gemini)))


# ---------------------------------------------------------------------------
# Anthropic — model resolved from active QoS profile
# ---------------------------------------------------------------------------
ANTHROPIC_AGENT_MODEL = get_model('chat_agent')
ANTHROPIC_AGENT_COMPLEX_MODEL = get_model('chat_agent')


# ---------------------------------------------------------------------------
# Legacy module-level alias (kept for test compatibility).
# Production code should use get_llm(feature) exclusively. The proxy preserves
# the legacy object shape without constructing a provider client at import time.
# ---------------------------------------------------------------------------


class _LazyClientProxy:
    """Resolve a compatibility client only when a caller first uses it."""

    __slots__ = ('_factory', '_instance')

    def __init__(self, factory: Callable[[], Any]):
        object.__setattr__(self, '_factory', factory)
        object.__setattr__(self, '_instance', None)

    def _resolve(self) -> Any:
        instance = self._instance
        if instance is None:
            instance = self._factory()
            object.__setattr__(self, '_instance', instance)
        return instance

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)

    def __or__(self, other: Any) -> Any:
        return self._resolve() | other

    def __ror__(self, other: Any) -> Any:
        return other | self._resolve()


def _create_legacy_llm_mini() -> ChatOpenAI:
    return ChatOpenAI(model=get_model('learnings'), callbacks=[_usage_callback], request_timeout=120, max_retries=1)


llm_mini = _LazyClientProxy(_create_legacy_llm_mini)

# ---------------------------------------------------------------------------
# Embeddings, parser, utilities
# ---------------------------------------------------------------------------
embeddings = _OpenAIEmbeddingsProxy(
    model="text-embedding-3-large",
    default=None,
    ctor_kwargs={},
)
parser = PydanticOutputParser(pydantic_object=StructuredExtraction)


@lru_cache(maxsize=1)
def _get_encoding():
    return tiktoken.encoding_for_model('gpt-4')


def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    num_tokens = len(_get_encoding().encode(string))
    return num_tokens


def generate_embedding(content: str) -> List[float]:
    return embeddings.embed_documents([content])[0]


def _embeddings_gateway_mode() -> bool:
    try:
        return should_route_features_through_gateway()
    except RuntimeError:
        return False


def gemini_embed_query(text: str) -> List[float]:
    """Embed a query using Gemini embedding-001 (3072-dim) for screen activity search.

    Uses RETRIEVAL_QUERY task type to match the RETRIEVAL_DOCUMENT embeddings
    generated by the desktop app.

    Gateway feature mode hops the omi:auto:gemini-embeddings lane (Vertex stays
    an upstream adapter) so the call lands in the spend ledger. A Gemini BYOK
    key keeps the thin direct AI Studio path — the gateway Vertex adapter
    fail-closes BYOK — and FEATURE_MODE=off keeps the legacy direct path.
    """
    byok_key = get_byok_key('gemini')
    if _embeddings_gateway_mode() and not byok_key:
        try:
            return invoke_gemini_embedding_gateway(text, task_type='RETRIEVAL_QUERY')
        except Exception as e:
            if not is_gateway_route_absent(e):
                raise
            _warn_gateway_embeddings_route_absent('gemini_embed_query')
    api_key = byok_key or os.environ.get('GEMINI_API_KEY', '')
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
