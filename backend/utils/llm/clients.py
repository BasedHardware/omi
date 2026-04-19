import logging
import os
from typing import Dict, List, Optional

import anthropic
import httpx
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import tiktoken

from models.structured import Structured
from utils.llm.usage_tracker import get_usage_callback

logger = logging.getLogger(__name__)

# Anthropic client for chat agent
anthropic_client = anthropic.AsyncAnthropic()  # uses ANTHROPIC_API_KEY env var

ANTHROPIC_AGENT_MODEL = "claude-sonnet-4-6"
ANTHROPIC_AGENT_COMPLEX_MODEL = "claude-sonnet-4-6"

# Get the usage tracking callback
_usage_callback = get_usage_callback()

# ---------------------------------------------------------------------------
# Omi QoS Tier System
#
# Maps Omi features to quality tiers. Each tier resolves to a concrete
# ChatOpenAI instance.  Override per-feature via env vars:
#   OMI_QOS_CONV_ACTION_ITEMS=medium   (use gpt-5.1 for action items)
#   OMI_QOS_KNOWLEDGE_GRAPH=nano       (use gpt-4.1-nano for KG)
#
# Tier names: nano, mini, medium, high
# ---------------------------------------------------------------------------

TIER_NANO = 'nano'
TIER_MINI = 'mini'
TIER_MEDIUM = 'medium'
TIER_HIGH = 'high'

_TIER_MODELS = {
    TIER_NANO: 'gpt-4.1-nano',
    TIER_MINI: 'gpt-4.1-mini',
    TIER_MEDIUM: 'gpt-5.1',
    TIER_HIGH: 'o4-mini',
}

# Default tier for each feature.  Change these to downgrade/upgrade features.
# Current defaults set cost-optimized tiers for high-volume features while
# preserving quality on features that need it.
# Only features currently wired through get_llm() are listed here.
_FEATURE_TIER_DEFAULTS: Dict[str, str] = {
    # Conversation processing — high volume, structured extraction
    'conv_action_items': TIER_MINI,
    'conv_structure': TIER_MEDIUM,
    'conv_apps': TIER_MINI,
    'daily_summary': TIER_MEDIUM,
    # Memories
    'memories': TIER_MINI,
    'memory_conflict': TIER_MINI,
    'memory_category': TIER_MINI,
    # Knowledge graph
    'knowledge_graph': TIER_MINI,
}


def _resolve_tier(feature: str) -> str:
    """Resolve the Omi QoS tier for a feature: env var override > default > mini fallback."""
    env_key = f'OMI_QOS_{feature.upper()}'
    tier = os.environ.get(env_key, '').strip().lower()
    if tier and tier in _TIER_MODELS:
        return tier
    return _FEATURE_TIER_DEFAULTS.get(feature, TIER_MINI)


# Cache of ChatOpenAI instances per model name to avoid re-creating them.
_llm_cache: Dict[str, ChatOpenAI] = {}


def _get_or_create_llm(model_name: str) -> ChatOpenAI:
    """Get or create a ChatOpenAI instance for the given model name."""
    if model_name not in _llm_cache:
        kwargs = {'model': model_name, 'callbacks': [_usage_callback]}
        if model_name == 'gpt-5.1':
            kwargs['extra_body'] = {"prompt_cache_retention": "24h"}
        _llm_cache[model_name] = ChatOpenAI(**kwargs)
    return _llm_cache[model_name]


# Models that support OpenAI prompt caching (prompt_cache_key routing).
_CACHE_KEY_MODELS = {'gpt-5.1'}


def get_llm(feature: str, cache_key: Optional[str] = None) -> ChatOpenAI:
    """Get the ChatOpenAI instance for a feature based on its Omi QoS tier.

    Args:
        feature: Omi feature name (e.g. 'conv_action_items').
        cache_key: Optional prompt cache routing key. Only applied when the
            resolved model supports it (currently gpt-5.1). Safely ignored
            for other models so tier swaps via env vars don't break.

    Usage:
        llm = get_llm('conv_action_items', cache_key='omi-extract-actions')
        response = llm.invoke(prompt)

    Override via env var:
        OMI_QOS_CONV_ACTION_ITEMS=medium  -> uses gpt-5.1
        OMI_QOS_CONV_ACTION_ITEMS=nano    -> uses gpt-4.1-nano
    """
    tier = _resolve_tier(feature)
    model_name = _TIER_MODELS[tier]
    llm = _get_or_create_llm(model_name)
    if cache_key and model_name in _CACHE_KEY_MODELS:
        return llm.bind(prompt_cache_key=cache_key)
    return llm


def get_llm_tier_info() -> Dict[str, Dict[str, str]]:
    """Return current feature-to-tier-to-model mapping for debugging/monitoring."""
    info = {}
    for feature in _FEATURE_TIER_DEFAULTS:
        tier = _resolve_tier(feature)
        info[feature] = {'tier': tier, 'model': _TIER_MODELS[tier]}
    return info


# Base models for general use (preserved for backward compatibility)
llm_mini = ChatOpenAI(model='gpt-4.1-mini', callbacks=[_usage_callback])
llm_mini_stream = ChatOpenAI(
    model='gpt-4.1-mini',
    streaming=True,
    stream_options={"include_usage": True},
    callbacks=[_usage_callback],
)
llm_large = ChatOpenAI(model='o1-preview', callbacks=[_usage_callback])
llm_large_stream = ChatOpenAI(
    model='o1-preview',
    streaming=True,
    stream_options={"include_usage": True},
    temperature=1,
    callbacks=[_usage_callback],
)
llm_high = ChatOpenAI(model='o4-mini', callbacks=[_usage_callback])
llm_high_stream = ChatOpenAI(
    model='o4-mini',
    streaming=True,
    stream_options={"include_usage": True},
    temperature=1,
    callbacks=[_usage_callback],
)
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

# Specialized models for agentic workflows
# prompt_cache_key ensures consistent routing to the same cache machine
# for better prompt prefix cache hit rates.
_agent_cache_kwargs = {
    "prompt_cache_key": "omi-agent-v1",
}
llm_agent = ChatOpenAI(
    model='gpt-5.1',
    extra_body={"prompt_cache_retention": "24h"},
    callbacks=[_usage_callback],
    model_kwargs=_agent_cache_kwargs,
)
llm_agent_stream = ChatOpenAI(
    model='gpt-5.1',
    streaming=True,
    stream_options={"include_usage": True},
    extra_body={"prompt_cache_retention": "24h"},
    callbacks=[_usage_callback],
    model_kwargs=_agent_cache_kwargs,
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
