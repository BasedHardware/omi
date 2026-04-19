import os
from typing import Any, Dict, List, Optional

import anthropic
import httpx
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import tiktoken

from models.structured import Structured
from utils.byok import get_byok_key
from utils.llm.usage_tracker import get_usage_callback

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
            cache_key = f"emb:{self._model}:{hash(byok)}"
            inst = _openai_cache.get(cache_key)
            if inst is None:
                inst = OpenAIEmbeddings(model=self._model, api_key=byok, **self._ctor_kwargs)
                _openai_cache[cache_key] = inst
            return inst
        return self._default

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)


_openai_cache: Dict[str, ChatOpenAI] = {}
_anthropic_cache: Dict[str, anthropic.AsyncAnthropic] = {}


def _cached_openai_chat(model: str, api_key: str, ctor_kwargs: Dict[str, Any]) -> ChatOpenAI:
    cache_key = f"{model}:{hash(api_key)}:{hash(frozenset((k, repr(v)) for k, v in ctor_kwargs.items()))}"
    inst = _openai_cache.get(cache_key)
    if inst is None:
        inst = ChatOpenAI(model=model, api_key=api_key, **ctor_kwargs)
        _openai_cache[cache_key] = inst
    return inst


def _cached_anthropic(api_key: str) -> anthropic.AsyncAnthropic:
    inst = _anthropic_cache.get(api_key)
    if inst is None:
        inst = anthropic.AsyncAnthropic(api_key=api_key)
        _anthropic_cache[api_key] = inst
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


ANTHROPIC_AGENT_MODEL = "claude-sonnet-4-6"
ANTHROPIC_AGENT_COMPLEX_MODEL = "claude-sonnet-4-6"

# Get the usage tracking callback
_usage_callback = get_usage_callback()

# Base models for general use — proxies route to BYOK OpenAI key per-request when set.
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
# Anthropic-via-OpenRouter stays on OpenRouter for now; direct-Anthropic via
# langchain would need the langchain-anthropic dep. BYOK Anthropic users still
# pay Omi for this specific persona model — flag for follow-up.
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
    url = f'https://generativelanguage.googleapis.com/v1beta/models/embedding-001:embedContent?key={api_key}'
    payload = {
        'model': 'models/embedding-001',
        'content': {'parts': [{'text': text}]},
        'taskType': 'RETRIEVAL_QUERY',
    }
    resp = httpx.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()['embedding']['values']
