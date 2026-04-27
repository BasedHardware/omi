import asyncio
import hashlib
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional

import anthropic
import httpx
from cachetools import TTLCache
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import tiktoken

from models.structured import Structured
from utils.byok import get_byok_key
from utils.llm.regolo_errors import (
    RegoloError,
    RegoloRateLimitError,
    RegoloServiceError,
    classify_regolo_error,
)
from utils.llm.usage_tracker import get_usage_callback

logger = logging.getLogger(__name__)

_usage_callback = get_usage_callback()

# ---------------------------------------------------------------------------
# BYOK routing proxies
#
# The backend has ~50 call sites that use module-level `llm_medium`, `llm_mini`,
# etc. directly (e.g. `llm_medium.invoke(prompt)` or `llm_medium.bind_tools(...).ainvoke(...)`).
# Rewriting every site to go through a factory would be a massive sweep.
#
# Instead we wrap each default client in a transparent proxy: every attribute
# access resolves to either the default client or a BYOK-keyed client built
# on the fly, keyed by (model, api_key) so we build each BYOK client once.
# `__getattr__` forwards `bind_tools`, `with_structured_output`, `|` chaining,
# etc. to the resolved client so tool-use/structured-output still route right.
# ---------------------------------------------------------------------------


class _OpenAIChatProxy:
    """Forwards every attribute and call to the appropriate ChatOpenAI for the request."""

    __slots__ = ('_model', '_default', '_ctor_kwargs')

    def __init__(self, model: str, default: ChatOpenAI, ctor_kwargs: Dict[str, Any]):
        object.__setattr__(self, '_model', model)
        object.__setattr__(self, '_default', default)
        object.__setattr__(self, '_ctor_kwargs', ctor_kwargs)

    def _resolve(self) -> ChatOpenAI:
        byok = get_byok_key('openai')
        if byok:
            return _cached_openai_chat(self._model, byok, self._ctor_kwargs)
        return self._default

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)

    # Needed for `prompt | model | parser`-style chain composition.
    def __or__(self, other):
        return self._resolve() | other

    def __ror__(self, other):
        return other | self._resolve()


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


# Google's OpenAI-compatible endpoint lets us keep langchain_openai.ChatOpenAI
# as the client class while routing to Gemini directly — no new langchain dep.
_GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class _OpenRouterGeminiProxy:
    """For models served via OpenRouter that we want to route direct when BYOK Gemini is set.

    Falls back to the OpenRouter-backed default client when no BYOK gemini key
    is present — so non-BYOK users are unaffected.
    """

    __slots__ = ('_default', '_direct_model', '_ctor_kwargs')

    def __init__(self, default: ChatOpenAI, direct_model: str, ctor_kwargs: Dict[str, Any]):
        object.__setattr__(self, '_default', default)
        object.__setattr__(self, '_direct_model', direct_model)
        object.__setattr__(self, '_ctor_kwargs', ctor_kwargs)

    def _resolve(self) -> ChatOpenAI:
        byok = get_byok_key('gemini')
        if byok:
            return _cached_openai_chat(
                self._direct_model,
                byok,
                {**self._ctor_kwargs, 'base_url': _GEMINI_OPENAI_BASE_URL},
            )
        return self._default

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)

    def __or__(self, other):
        return self._resolve() | other

    def __ror__(self, other):
        return other | self._resolve()


class _RegoloChatProxy:
    """Forwards every attribute and call to the appropriate ChatOpenAI for Regolo.

    Regolo (https://api.regolo.ai/v1) is OpenAI-compatible; we drive it through
    langchain_openai.ChatOpenAI with a custom base_url. BYOK Regolo keys (via
    `X-BYOK-Regolo`) take precedence over the env REGOLO_API_KEY.
    """

    __slots__ = ('_model', '_default', '_ctor_kwargs')

    def __init__(self, model: str, default: ChatOpenAI, ctor_kwargs: Dict[str, Any]):
        object.__setattr__(self, '_model', model)
        object.__setattr__(self, '_default', default)
        object.__setattr__(self, '_ctor_kwargs', ctor_kwargs)

    def _resolve(self) -> ChatOpenAI:
        byok = get_byok_key('regolo')
        if byok:
            return _cached_openai_chat(self._model, byok, self._ctor_kwargs)
        return self._default

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Wrap ChatOpenAI.invoke with reasoning-content stripping, typed error
        classification, bounded retry on 429/5xx, and provider=regolo telemetry.

        - On success: drops `reasoning_content` so MiniMax / Qwen3.x thinking
          output never leaks into chat history.
        - On 429: retries up to `_REGOLO_MAX_RATE_LIMIT_ATTEMPTS` times,
          honoring `Retry-After` when present.
        - On 5xx: retries once with exponential backoff.
        - On 401/403/404 / unrecognized: re-raises typed `RegoloError`
          subclass with the original exception preserved via `from`.
        - Telemetry: injects `provider=regolo` + `model=<name>` tags into
          the langchain `RunnableConfig` so the upstream `_usage_callback`
          can attribute usage rows to Regolo.
        """
        target = self._resolve()
        args, kwargs = _inject_regolo_telemetry(self._model, args, kwargs)
        return _regolo_invoke_with_retry(lambda: target.invoke(*args, **kwargs))

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        """Async equivalent of invoke — same strip / classify / retry / tag contract."""
        target = self._resolve()
        args, kwargs = _inject_regolo_telemetry(self._model, args, kwargs)
        return await _regolo_ainvoke_with_retry(lambda: target.ainvoke(*args, **kwargs))

    def stream(self, *args: Any, **kwargs: Any):
        """Sync streaming wrapper — strips reasoning_content per chunk and
        classifies exceptions raised during iteration. Yields the same chunk
        objects langchain would yield, mutated in place. Telemetry tags
        injected so streaming usage attributes to Regolo too.

        `target.stream(...)` returns a generator and does not raise on
        construction; HTTP errors only materialize during iteration.
        """
        target = self._resolve()
        args, kwargs = _inject_regolo_telemetry(self._model, args, kwargs)
        iterator = target.stream(*args, **kwargs)
        try:
            for chunk in iterator:
                yield strip_reasoning_content(chunk)
        except RegoloError:
            raise
        except Exception as exc:
            raise classify_regolo_error(exc) from exc

    async def astream(self, *args: Any, **kwargs: Any):
        """Async streaming wrapper — same contract as `stream` but async."""
        target = self._resolve()
        args, kwargs = _inject_regolo_telemetry(self._model, args, kwargs)
        iterator = target.astream(*args, **kwargs)
        try:
            async for chunk in iterator:
                yield strip_reasoning_content(chunk)
        except RegoloError:
            raise
        except Exception as exc:
            raise classify_regolo_error(exc) from exc

    def __getattr__(self, name: str) -> Any:
        # Everything else (bind_tools, batch, abatch, with_structured_output,
        # with_retry, ...) falls through to the underlying ChatOpenAI. The
        # invoke/ainvoke/stream/astream paths above cover the four hand-offs
        # that touch reasoning_content and Regolo error envelopes.
        return getattr(self._resolve(), name)

    def __or__(self, other: Any) -> Any:
        return self._resolve() | other

    def __ror__(self, other: Any) -> Any:
        return other | self._resolve()


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


# ---------------------------------------------------------------------------
# Regolo embeddings (M2.5)
#
# Qwen3-Embedding-8B is 4096-dim; OpenAI text-embedding-3-large is 3072-dim.
# Pinecone enforces a fixed dimensionality at index creation time, so the
# 4096-dim vectors CANNOT share an index with the existing 3072-dim ones.
# Production deployment depends on a SEPARATE Pinecone index provisioned at
# 4096-dim, surfaced via the PINECONE_INDEX_NAME_EU env var. Until that env
# var is set, _RegoloEmbeddingProxy.embed_documents/embed_query construct
# fine but writes/reads will hit the wrong index — see eu_privacy
# .eu_embedding_index_provisioned() which gates the routing decision.
# ---------------------------------------------------------------------------
_REGOLO_EMBEDDING_MODEL = 'Qwen3-Embedding-8B'
_REGOLO_EMBEDDING_DIM = 4096


class _RegoloEmbeddingProxy:
    """Embeddings client routed to api.regolo.ai/v1 with BYOK Regolo key
    preferred over the env REGOLO_API_KEY.

    Mirrors `_OpenAIEmbeddingsProxy`'s shape so callers that handle
    `embed_documents([content])` / `embed_query(text)` can swap proxies
    without code changes. Same `__getattr__` fallthrough to forward any
    other langchain Embeddings method to the underlying client.
    """

    __slots__ = ('_model', '_default', '_ctor_kwargs')

    def __init__(self, model: str, default: OpenAIEmbeddings, ctor_kwargs: Dict[str, Any]):
        object.__setattr__(self, '_model', model)
        object.__setattr__(self, '_default', default)
        object.__setattr__(self, '_ctor_kwargs', ctor_kwargs)

    def _resolve(self) -> OpenAIEmbeddings:
        byok = get_byok_key('regolo')
        # Cache key includes provider tag so 'emb:<model>:<hash>' for OpenAI
        # and 'emb-regolo:<model>:<hash>' for Regolo never collide if the
        # same key happens to be used cross-provider (unlikely, but safe).
        if byok:
            cache_key = f"emb-regolo:{self._model}:{_hash_key(byok)}"
            inst = _openai_cache.get(cache_key)
            if inst is None:
                inst = OpenAIEmbeddings(
                    model=self._model,
                    api_key=byok,
                    base_url=_REGOLO_BASE_URL,
                    **self._ctor_kwargs,
                )
                _openai_cache[cache_key] = inst
            return inst
        return self._default

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)


# ---------------------------------------------------------------------------
# Regolo retry policy (M1.3)
#
# Applied at the invoke / ainvoke hand-off in `_RegoloChatProxy`. NOT applied
# to streaming wrappers — retrying mid-stream would resend the prompt and
# duplicate any side effects callers have already observed from the partial
# output.
#
# Policy:
#   - 429 (RegoloRateLimitError): up to 3 total attempts (initial + 2 retries).
#     Honors `Retry-After` when present, otherwise exponential backoff with
#     10% jitter, capped at _REGOLO_RETRY_MAX_BACKOFF_S.
#   - 5xx (RegoloServiceError): 1 retry with exponential backoff, then re-raise.
#   - Everything else (auth / forbidden / model-not-found / unknown):
#     re-raise immediately as the typed RegoloError subclass.
# ---------------------------------------------------------------------------
_REGOLO_MAX_RATE_LIMIT_ATTEMPTS = 3
_REGOLO_RETRY_BASE_BACKOFF_S = 1.0
_REGOLO_RETRY_MAX_BACKOFF_S = 30.0

_REGOLO_PROVIDER_TAG = 'provider=regolo'


def _inject_regolo_telemetry(
    model: str, args: tuple, kwargs: Dict[str, Any]
) -> tuple:
    """Add `provider=regolo` + `model=<name>` to the langchain RunnableConfig.

    langchain's `Runnable.invoke(input, config=None, **kwargs)` accepts the
    config either as 2nd positional or `config=` kwarg. We merge into whichever
    the caller used (or set kwarg if neither). Both tags and metadata channels
    carry the attribution so callbacks reading either can attribute usage rows
    to Regolo.

    Idempotency / merge rules:
      - `provider=regolo` tag: appended only if not already present.
      - `model=<name>` tag: appended only if no `model=` tag is already present
        (so a caller's own `model=foo` isn't double-stamped).
      - `metadata['regolo_provider']` and `metadata['regolo_model']`: always
        set (these are M1-private keys; never collide with caller metadata).
      - `metadata['provider']`: set via setdefault to preserve any caller-
        supplied value. The tags channel + the `regolo_provider` key keep
        attribution working even if a caller pre-sets `metadata['provider']`.
    """
    # Resolve current config (may be None, dict, or langchain's RunnableConfig
    # which is a TypedDict — both behave like dicts at runtime).
    config_via_kwarg = 'config' in kwargs
    if config_via_kwarg:
        existing = kwargs.get('config') or {}
    elif len(args) >= 2:
        existing = args[1] or {}
    else:
        existing = {}

    new_config = dict(existing)

    tags = list(new_config.get('tags') or [])
    if _REGOLO_PROVIDER_TAG not in tags:
        tags.append(_REGOLO_PROVIDER_TAG)
    if not any(isinstance(t, str) and t.startswith('model=') for t in tags):
        tags.append(f'model={model}')
    new_config['tags'] = tags

    metadata = dict(new_config.get('metadata') or {})
    # M1-private keys — always overwrite so the upstream callback gets a
    # reliable Regolo signal even when caller metadata uses 'provider'.
    metadata['regolo_provider'] = 'regolo'
    metadata['regolo_model'] = model
    metadata.setdefault('provider', 'regolo')
    new_config['metadata'] = metadata

    if config_via_kwarg or len(args) < 2:
        kwargs['config'] = new_config
        return args, kwargs
    args = (args[0], new_config) + args[2:]
    return args, kwargs


def _regolo_backoff_seconds(attempt: int, retry_after_s: Optional[float]) -> float:
    """Wait seconds for a Regolo retry. `attempt` is 0-indexed."""
    if retry_after_s is not None and retry_after_s > 0:
        return min(retry_after_s, _REGOLO_RETRY_MAX_BACKOFF_S)
    base = _REGOLO_RETRY_BASE_BACKOFF_S * (2**attempt)
    jitter = random.uniform(0, base * 0.1)
    return min(base + jitter, _REGOLO_RETRY_MAX_BACKOFF_S)


def _next_regolo_retry_wait(
    rate_limit_attempts: int, five_xx_retried: bool, classified: RegoloError
) -> Optional[float]:
    """Wait seconds, or None if the retry budget is exhausted / error is terminal."""
    if isinstance(classified, RegoloRateLimitError):
        if rate_limit_attempts >= _REGOLO_MAX_RATE_LIMIT_ATTEMPTS - 1:
            return None
        return _regolo_backoff_seconds(rate_limit_attempts, classified.retry_after_s)
    if isinstance(classified, RegoloServiceError) and not five_xx_retried:
        return _regolo_backoff_seconds(0, None)
    return None


def _regolo_invoke_with_retry(call: Any) -> Any:
    """Sync retry loop. `call` is a 0-arg callable that returns the LLM result."""
    rate_limit_attempts = 0
    five_xx_retried = False
    while True:
        try:
            return strip_reasoning_content(call())
        except Exception as exc:
            classified = exc if isinstance(exc, RegoloError) else classify_regolo_error(exc)
            wait = _next_regolo_retry_wait(rate_limit_attempts, five_xx_retried, classified)
            if wait is None:
                if isinstance(exc, RegoloError):
                    raise
                raise classified from exc
            if isinstance(classified, RegoloRateLimitError):
                rate_limit_attempts += 1
            elif isinstance(classified, RegoloServiceError):
                five_xx_retried = True
            time.sleep(wait)


async def _regolo_ainvoke_with_retry(call: Any) -> Any:
    """Async retry loop. `call` is a 0-arg callable returning an awaitable."""
    rate_limit_attempts = 0
    five_xx_retried = False
    while True:
        try:
            return strip_reasoning_content(await call())
        except Exception as exc:
            classified = exc if isinstance(exc, RegoloError) else classify_regolo_error(exc)
            wait = _next_regolo_retry_wait(rate_limit_attempts, five_xx_retried, classified)
            if wait is None:
                if isinstance(exc, RegoloError):
                    raise
                raise classified from exc
            if isinstance(classified, RegoloRateLimitError):
                rate_limit_attempts += 1
            elif isinstance(classified, RegoloServiceError):
                five_xx_retried = True
            await asyncio.sleep(wait)


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


def _byok_openai(model: str, **ctor_kwargs) -> _OpenAIChatProxy:
    """Build a module-level ChatOpenAI that transparently routes to BYOK if set."""
    default = ChatOpenAI(model=model, **ctor_kwargs)
    return _OpenAIChatProxy(model=model, default=default, ctor_kwargs=ctor_kwargs)


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
# Each profile maps every feature to a specific model. Features span multiple
# providers (OpenAI, Anthropic, OpenRouter, Perplexity). Within a profile,
# each feature gets the model appropriate for that cost/quality level.
#
# Global switch:     MODEL_QOS=premium        (selects entire profile)
# Per-feature:       MODEL_QOS_CHAT_AGENT=claude-haiku-3.5  (overrides one feature)
#
# Two profiles:
#   premium — cost-effective default (80% of max quality)
#   max     — maximum quality, latest flagship models
# ---------------------------------------------------------------------------

MODEL_QOS_PROFILES: Dict[str, Dict[str, str]] = {
    'premium': {
        # OpenAI — conversation processing
        'conv_action_items': 'gpt-5.4-mini',
        'conv_structure': 'gpt-5.4-mini',
        'conv_app_result': 'gpt-5.4-mini',
        'conv_app_select': 'gpt-4.1-nano',
        'conv_folder': 'gpt-4.1-nano',
        'conv_discard': 'gpt-4.1-nano',
        'daily_summary': 'gpt-5.4-mini',
        'daily_summary_simple': 'gpt-4.1-nano',
        'external_structure': 'gpt-4.1-mini',  # quality-sensitive: structuring external data
        # OpenAI — memories & knowledge
        'memories': 'gpt-4.1-mini',  # quality-sensitive: memory extraction
        'learnings': 'gpt-5.4-mini',
        'memory_conflict': 'gpt-4.1-mini',  # quality-sensitive: conflict detection
        'memory_category': 'gpt-4.1-nano',
        'knowledge_graph': 'gpt-4.1-mini',  # quality-sensitive: entity/relationship extraction
        # OpenAI — chat
        'chat_responses': 'gpt-5.4-mini',
        'chat_extraction': 'gpt-4.1-mini',  # quality-sensitive: structured data extraction
        'chat_graph': 'gpt-4.1-mini',  # quality-sensitive: graph queries
        'session_titles': 'gpt-4.1-nano',
        # OpenAI — features
        'goals': 'gpt-4.1-mini',  # quality-sensitive: goal analysis
        'goals_advice': 'gpt-5.4-mini',
        'notifications': 'gpt-5.4-mini',
        'proactive_notification': 'gpt-4.1-mini',  # quality-sensitive: notification decisions
        'followup': 'gpt-4.1-nano',
        'smart_glasses': 'gpt-4.1-nano',
        'onboarding': 'gpt-4.1-nano',
        'app_generator': 'gpt-5.4-mini',
        'app_integration': 'gpt-4.1-nano',
        'persona_clone': 'gpt-5.4-mini',
        'trends': 'gpt-4.1-nano',
        # Anthropic (chat_agent — used via get_model() + anthropic_client)
        'chat_agent': 'claude-sonnet-4-6',
        # OpenAI — persona (moved from deprecated OpenRouter models to direct API)
        'persona_chat': 'gpt-4.1-nano',
        'persona_chat_premium': 'gpt-5.4-mini',
        # OpenRouter — wrapped_analysis only (gemini-3-flash-preview still active)
        'wrapped_analysis': 'google/gemini-3-flash-preview',
        # Perplexity
        'web_search': 'sonar-pro',
    },
    'max': {
        # OpenAI — conversation processing (gpt-5.4 replaces gpt-5.1/5.2, rest unchanged)
        'conv_action_items': 'gpt-5.4',
        'conv_structure': 'gpt-5.4',
        'conv_app_result': 'gpt-5.4',
        'conv_app_select': 'gpt-4.1-mini',
        'conv_folder': 'gpt-4.1-mini',
        'conv_discard': 'gpt-4.1-mini',
        'daily_summary': 'gpt-5.4',
        'daily_summary_simple': 'gpt-4.1-mini',
        'external_structure': 'gpt-4.1-mini',
        # OpenAI — memories & knowledge (unchanged from production)
        'memories': 'gpt-4.1-mini',
        'learnings': 'o4-mini',
        'memory_conflict': 'gpt-4.1-mini',
        'memory_category': 'gpt-4.1-mini',
        'knowledge_graph': 'gpt-4.1-mini',
        # OpenAI — chat (gpt-5.4 replaces gpt-5.2, rest unchanged)
        'chat_responses': 'gpt-5.4',
        'chat_extraction': 'gpt-4.1-mini',
        'chat_graph': 'gpt-4.1',
        'session_titles': 'gpt-4.1-mini',
        # OpenAI — features (gpt-5.4 replaces gpt-5.2/5.1, rest unchanged)
        'goals': 'gpt-4.1-mini',
        'goals_advice': 'gpt-5.4',
        'notifications': 'gpt-5.4',
        'proactive_notification': 'gpt-4.1-mini',
        'followup': 'gpt-4.1-mini',
        'smart_glasses': 'gpt-4.1-mini',
        'onboarding': 'gpt-4.1-mini',
        'app_generator': 'gpt-5.4',
        'app_integration': 'gpt-4.1-mini',
        'persona_clone': 'gpt-5.4',
        'trends': 'gpt-4.1-mini',
        # Anthropic (unchanged)
        'chat_agent': 'claude-sonnet-4-6',
        # OpenAI — persona (moved from deprecated OpenRouter models to direct API)
        'persona_chat': 'gpt-4.1-nano',
        'persona_chat_premium': 'gpt-5.4-mini',
        # OpenRouter — wrapped_analysis only (gemini-3-flash-preview still active)
        'wrapped_analysis': 'google/gemini-3-flash-preview',
        # Perplexity (unchanged)
        'web_search': 'sonar-pro',
    },
}

# Pinned features — model is fixed regardless of profile or env override.
_PINNED_FEATURES: Dict[str, str] = {
    'fair_use': 'gpt-5.1',
}

# Resolve active profile once at startup (kai: OnceLock/singleton pattern).
_active_profile_name = os.environ.get('MODEL_QOS', 'premium').strip().lower()
if _active_profile_name not in MODEL_QOS_PROFILES:
    logger.warning('MODEL_QOS=%s is not a valid profile, falling back to premium', _active_profile_name)
    _active_profile_name = 'premium'
_active_profile = MODEL_QOS_PROFILES[_active_profile_name]

# Provider detection from model name — provider depends on profile, not feature.
# A feature like persona_chat may be OpenRouter in premium but OpenAI in max.
_ANTHROPIC_ONLY_FEATURES = {'chat_agent'}  # always Anthropic, used via get_model() + anthropic_client
_PERPLEXITY_ONLY_FEATURES = {'web_search'}  # always Perplexity, used via get_model() + HTTP client


def _classify_provider(model: str) -> str:
    """Classify provider from model name. Provider follows the model, not the feature.

    Regolo models are tagged with a `regolo/` prefix to distinguish them from
    OpenRouter (which also uses `/`-prefixed names like `google/gemini-...`).
    The Regolo prefix is stripped before being sent to the API.
    """
    if model.startswith('regolo/'):
        return 'regolo'
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

# Per-feature temperatures for Regolo features. Empty today — populate when a
# Regolo-routed feature needs a non-default temperature. Keep this distinct
# from `_OPENROUTER_TEMPERATURES` so a future entry doesn't silently affect
# the wrong provider.
_REGOLO_TEMPERATURES: Dict[str, float] = {}

# Models that support OpenAI prompt caching (prompt_cache_key routing).
_CACHE_KEY_MODELS = {'gpt-5.4', 'gpt-5.4-mini'}


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
# QoS clients are BYOK-aware via _byok_openai / _OpenRouterGeminiProxy.
# ---------------------------------------------------------------------------

_llm_cache: Dict[tuple, Any] = {}


def _get_or_create_openai_llm(model_name: str, streaming: bool = False) -> _OpenAIChatProxy:
    """Get or create a BYOK-aware ChatOpenAI proxy for an OpenAI model."""
    key = (model_name, streaming, 'openai')
    if key not in _llm_cache:
        kwargs: Dict[str, Any] = {'callbacks': [_usage_callback]}
        if model_name == 'gpt-5.1':
            kwargs['extra_body'] = {"prompt_cache_retention": "24h"}
        if streaming:
            kwargs['streaming'] = True
            kwargs['stream_options'] = {"include_usage": True}
        _llm_cache[key] = _byok_openai(model_name, **kwargs)
    return _llm_cache[key]


def _get_or_create_openrouter_llm(
    model_name: str, streaming: bool = False, temperature: Optional[float] = None
) -> ChatOpenAI:
    """Get or create a ChatOpenAI instance for an OpenRouter model."""
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
        # For Gemini models on OpenRouter, use proxy for BYOK Gemini routing
        if model_name.startswith('google/gemini'):
            direct_model = model_name.split('/', 1)[1]
            default = ChatOpenAI(model=model_name, **kwargs)
            _llm_cache[key] = _OpenRouterGeminiProxy(default=default, direct_model=direct_model, ctor_kwargs=kwargs)
        else:
            _llm_cache[key] = ChatOpenAI(model=model_name, **kwargs)
    return _llm_cache[key]


# Regolo (https://api.regolo.ai) — Italy-hosted, OpenAI-compatible, GDPR-compliant
# (zero-retention) inference. Used for the EU Privacy Mode path.
#
# SSRF defense: _REGOLO_BASE_URL is a private module constant. It is NEVER
# derived from request headers or user input. Tests assert the exact prefix.
_REGOLO_BASE_URL = "https://api.regolo.ai/v1"

# Models that require chat_template_kwargs.enable_thinking=False or they will
# burn the entire output budget on hidden reasoning tokens (and the visible
# completion comes back as content=null with finish_reason=length). Live-
# probed Apr 27 2026 — see docs/04-model-mapping.md for raw probe results.
#
# Every model in the qwen-3.x family + minimax-m2.5 falls into this bucket.
# Llama, mistral, gpt-oss, gemma, apertus, and qwen3-coder-next do NOT.
_REGOLO_THINKING_MODELS = frozenset(
    {
        'minimax-m2.5',
        'qwen3.5-122b',
        'qwen3.5-9b',
        'qwen3.6-27b',
    }
)


def _get_or_create_regolo_llm(
    model_name: str, streaming: bool = False, temperature: Optional[float] = None
) -> ChatOpenAI:
    """Get or create a BYOK-aware ChatOpenAI proxy for a Regolo model.

    `model_name` is expected to carry the `regolo/` prefix (e.g.
    `regolo/Llama-3.3-70B-Instruct`); the prefix is stripped before being
    sent to api.regolo.ai. Auth uses the per-request BYOK Regolo key when
    set, otherwise the process-wide REGOLO_API_KEY env var.

    For thinking models (minimax-m2.5, qwen3.5-122b), injects
    `chat_template_kwargs.enable_thinking=False` via `extra_body` so the
    model returns chat content instead of a truncated reasoning trace.
    """
    key = (model_name, streaming, 'regolo', temperature)
    if key not in _llm_cache:
        api_model = model_name.split('/', 1)[1] if model_name.startswith('regolo/') else model_name
        kwargs: Dict[str, Any] = {
            'api_key': os.environ.get('REGOLO_API_KEY'),
            'base_url': _REGOLO_BASE_URL,
            'callbacks': [_usage_callback],
        }
        # Thinking knob — Regolo-specific request body field. Without it,
        # minimax-m2.5/qwen3.5-122b return content=null, finish_reason=length.
        if api_model in _REGOLO_THINKING_MODELS:
            kwargs['extra_body'] = {"chat_template_kwargs": {"enable_thinking": False}}
        if temperature is not None:
            kwargs['temperature'] = temperature
        if streaming:
            kwargs['streaming'] = True
            kwargs['stream_options'] = {"include_usage": True}
        default = ChatOpenAI(model=api_model, **kwargs)
        _llm_cache[key] = _RegoloChatProxy(model=api_model, default=default, ctor_kwargs=kwargs)
    return _llm_cache[key]


def strip_reasoning_content(message: Any) -> Any:
    """Strip Regolo's non-OpenAI `reasoning_content` field before persistence.

    Thinking models (minimax-m2.5, qwen3.5-122b) emit a `reasoning_content`
    field on the assistant message and on streaming deltas. Persisting it
    bloats Firestore and risks leaking raw chain-of-thought to the client.
    This helper mutates-in-place when given a langchain `BaseMessage` (drops
    `additional_kwargs.reasoning_content`) and also works on raw dict deltas.

    Returns the same object for chaining.
    """
    if message is None:
        return message
    # langchain BaseMessage: reasoning_content lands in additional_kwargs.
    if hasattr(message, 'additional_kwargs') and isinstance(message.additional_kwargs, dict):
        message.additional_kwargs.pop('reasoning_content', None)
    # Raw dict (streaming delta): drop top-level field.
    if isinstance(message, dict):
        message.pop('reasoning_content', None)
        # OpenAI streaming chunks nest content under 'delta' or 'message'.
        for nested_key in ('delta', 'message'):
            nested = message.get(nested_key)
            if isinstance(nested, dict):
                nested.pop('reasoning_content', None)
    return message


def get_llm(feature: str, streaming: bool = False, cache_key: Optional[str] = None) -> ChatOpenAI:
    """Get the LLM client for a feature based on the active Model QoS profile.

    Works for OpenAI and OpenRouter features (returns ChatOpenAI or BYOK proxy).
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

    if provider == 'regolo':
        temp = _REGOLO_TEMPERATURES.get(feature)
        return _get_or_create_regolo_llm(model, streaming, temp)

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
# Anthropic — model resolved from active QoS profile
# ---------------------------------------------------------------------------
ANTHROPIC_AGENT_MODEL = get_model('chat_agent')
ANTHROPIC_AGENT_COMPLEX_MODEL = get_model('chat_agent')


# ---------------------------------------------------------------------------
# Legacy model instances (for callsites not yet wired through get_llm)
#
# These are kept for backward compatibility with BYOK routing.
# New code should use get_llm(feature) or get_model(feature) instead.
# ---------------------------------------------------------------------------
llm_mini = _byok_openai('gpt-4.1-mini', callbacks=[_usage_callback])
llm_mini_stream = _byok_openai(
    'gpt-4.1-mini',
    streaming=True,
    stream_options={"include_usage": True},
    callbacks=[_usage_callback],
)
llm_large = _byok_openai('o1-preview', callbacks=[_usage_callback])
llm_large_stream = _byok_openai(
    'o1-preview',
    streaming=True,
    stream_options={"include_usage": True},
    temperature=1,
    callbacks=[_usage_callback],
)
llm_high = _byok_openai('o4-mini', callbacks=[_usage_callback])
llm_high_stream = _byok_openai(
    'o4-mini',
    streaming=True,
    stream_options={"include_usage": True},
    temperature=1,
    callbacks=[_usage_callback],
)
llm_medium = _byok_openai('gpt-5.2', callbacks=[_usage_callback])
llm_medium_stream = _byok_openai(
    'gpt-5.2',
    streaming=True,
    stream_options={"include_usage": True},
    callbacks=[_usage_callback],
)
llm_medium_experiment = _byok_openai(
    'gpt-5.1',
    extra_body={"prompt_cache_retention": "24h"},
    callbacks=[_usage_callback],
)

# Specialized models for agentic workflows
# prompt_cache_key ensures consistent routing to the same cache machine
# for better prompt prefix cache hit rates.
_agent_cache_kwargs = {
    "prompt_cache_key": "omi-agent-v1",
}
llm_agent = _byok_openai(
    'gpt-5.1',
    extra_body={"prompt_cache_retention": "24h"},
    callbacks=[_usage_callback],
    model_kwargs=_agent_cache_kwargs,
)
llm_agent_stream = _byok_openai(
    'gpt-5.1',
    streaming=True,
    stream_options={"include_usage": True},
    extra_body={"prompt_cache_retention": "24h"},
    callbacks=[_usage_callback],
    model_kwargs=_agent_cache_kwargs,
)
_persona_mini_kwargs = dict(
    temperature=0.8,
    streaming=True,
    stream_options={"include_usage": True},
    callbacks=[_usage_callback],
)
_persona_mini_default = ChatOpenAI(
    model="google/gemini-flash-1.5-8b",
    api_key=os.environ.get('OPENROUTER_API_KEY'),
    base_url="https://openrouter.ai/api/v1",
    default_headers={"X-Title": "Omi Chat"},
    **_persona_mini_kwargs,
)
# BYOK Gemini → route direct to Google's OpenAI-compat endpoint.
# Model name drops the `google/` prefix: gemini-flash-1.5-8b on Google direct.
llm_persona_mini_stream = _OpenRouterGeminiProxy(
    default=_persona_mini_default,
    direct_model="gemini-flash-1.5-8b",
    ctor_kwargs=_persona_mini_kwargs,
)
# Anthropic-via-OpenRouter. BYOK Anthropic users route to Anthropic's
# OpenAI-compat endpoint directly, avoiding Omi's OpenRouter bill.
_ANTHROPIC_OPENAI_BASE_URL = "https://api.anthropic.com/v1/"
_persona_medium_kwargs = dict(
    temperature=0.8,
    streaming=True,
    stream_options={"include_usage": True},
    callbacks=[_usage_callback],
)
_persona_medium_default = ChatOpenAI(
    model="anthropic/claude-3.5-sonnet",
    api_key=os.environ.get('OPENROUTER_API_KEY'),
    base_url="https://openrouter.ai/api/v1",
    default_headers={"X-Title": "Omi Chat"},
    **_persona_medium_kwargs,
)


class _AnthropicViaOpenAIProxy:
    """Route to Anthropic's OpenAI-compat endpoint when BYOK Anthropic key is set."""

    __slots__ = ('_default', '_ctor_kwargs')

    def __init__(self, default: ChatOpenAI, ctor_kwargs: Dict[str, Any]):
        object.__setattr__(self, '_default', default)
        object.__setattr__(self, '_ctor_kwargs', ctor_kwargs)

    def _resolve(self) -> ChatOpenAI:
        byok = get_byok_key('anthropic')
        if byok:
            return _cached_openai_chat(
                'claude-sonnet-4-20250514',
                byok,
                {**self._ctor_kwargs, 'base_url': _ANTHROPIC_OPENAI_BASE_URL},
            )
        return self._default

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)

    def __or__(self, other):
        return self._resolve() | other

    def __ror__(self, other):
        return other | self._resolve()


llm_persona_medium_stream = _AnthropicViaOpenAIProxy(
    default=_persona_medium_default,
    ctor_kwargs=_persona_medium_kwargs,
)

# Gemini models for large context analysis
_gemini_flash_kwargs = dict(
    temperature=0.7,
    callbacks=[_usage_callback],
)
_gemini_flash_default = ChatOpenAI(
    model="google/gemini-3-flash-preview",
    api_key=os.environ.get('OPENROUTER_API_KEY'),
    base_url="https://openrouter.ai/api/v1",
    default_headers={"X-Title": "Omi Wrapped"},
    **_gemini_flash_kwargs,
)
llm_gemini_flash = _OpenRouterGeminiProxy(
    default=_gemini_flash_default,
    direct_model="gemini-3-flash-preview",
    ctor_kwargs=_gemini_flash_kwargs,
)

# ---------------------------------------------------------------------------
# Embeddings, parser, utilities
# ---------------------------------------------------------------------------
_embeddings_default = OpenAIEmbeddings(model="text-embedding-3-large")
embeddings = _OpenAIEmbeddingsProxy(
    model="text-embedding-3-large",
    default=_embeddings_default,
    ctor_kwargs={},
)

# Regolo embeddings (M2.5). Default client targets api.regolo.ai with the
# env REGOLO_API_KEY; BYOK Regolo keys take precedence per _RegoloEmbeddingProxy
# ._resolve. Only used when EU Privacy Mode is on AND
# eu_privacy.eu_embedding_index_provisioned() is True (see PINECONE_INDEX_NAME_EU).
_regolo_embeddings_default = OpenAIEmbeddings(
    model=_REGOLO_EMBEDDING_MODEL,
    api_key=os.environ.get('REGOLO_API_KEY', ''),
    base_url=_REGOLO_BASE_URL,
)
regolo_embeddings = _RegoloEmbeddingProxy(
    model=_REGOLO_EMBEDDING_MODEL,
    default=_regolo_embeddings_default,
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


def generate_regolo_embedding(content: str) -> List[float]:
    """Generate a 4096-dim embedding via Qwen3-Embedding-8B on api.regolo.ai.

    Used when EU Privacy Mode is on AND the EU-side Pinecone index has been
    provisioned. Callers MUST verify both conditions via
    eu_privacy.eu_embedding_index_provisioned() before invoking — writing
    a 4096-dim vector to the legacy 3072-dim index hard-fails server-side.
    """
    return regolo_embeddings.embed_documents([content])[0]


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
