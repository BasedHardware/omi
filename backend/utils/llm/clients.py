import os
from typing import List

import anthropic
import httpx
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import tiktoken

from models.structured import Structured
from utils.llm.usage_tracker import get_usage_callback

# Anthropic client for chat agent
anthropic_client = anthropic.AsyncAnthropic()  # uses ANTHROPIC_API_KEY env var

ANTHROPIC_AGENT_MODEL = "claude-sonnet-4-6"
ANTHROPIC_AGENT_COMPLEX_MODEL = "claude-sonnet-4-6"

# Get the usage tracking callback
_usage_callback = get_usage_callback()

# MiniMax provider configuration
# Set MINIMAX_API_KEY to use MiniMax models (https://api.minimax.io)
_minimax_api_key = os.environ.get('MINIMAX_API_KEY')
_minimax_base_url = os.environ.get('MINIMAX_BASE_URL', 'https://api.minimax.io/v1')

if _minimax_api_key:
    # MiniMax-M2.7: Peak Performance. Ultimate Value. Master the Complex.
    llm_minimax = ChatOpenAI(
        model='MiniMax-M2.7',
        api_key=_minimax_api_key,
        base_url=_minimax_base_url,
        temperature=1.0,  # MiniMax requires temperature in (0.0, 1.0], not 0
        callbacks=[_usage_callback],
    )
    llm_minimax_stream = ChatOpenAI(
        model='MiniMax-M2.7',
        api_key=_minimax_api_key,
        base_url=_minimax_base_url,
        temperature=1.0,
        streaming=True,
        stream_options={"include_usage": True},
        callbacks=[_usage_callback],
    )
    # MiniMax-M2.7-highspeed: Same performance, faster and more agile
    llm_minimax_fast_stream = ChatOpenAI(
        model='MiniMax-M2.7-highspeed',
        api_key=_minimax_api_key,
        base_url=_minimax_base_url,
        temperature=1.0,
        streaming=True,
        stream_options={"include_usage": True},
        callbacks=[_usage_callback],
    )
else:
    llm_minimax = None
    llm_minimax_stream = None
    llm_minimax_fast_stream = None

# Base models for general use
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
if _minimax_api_key:
    # Use MiniMax models directly for persona chat when MINIMAX_API_KEY is configured
    llm_persona_mini_stream = ChatOpenAI(
        model='MiniMax-M2.7-highspeed',
        api_key=_minimax_api_key,
        base_url=_minimax_base_url,
        temperature=1.0,  # MiniMax requires temperature in (0.0, 1.0], not 0
        streaming=True,
        stream_options={"include_usage": True},
        callbacks=[_usage_callback],
    )
    llm_persona_medium_stream = ChatOpenAI(
        model='MiniMax-M2.7',
        api_key=_minimax_api_key,
        base_url=_minimax_base_url,
        temperature=1.0,
        streaming=True,
        stream_options={"include_usage": True},
        callbacks=[_usage_callback],
    )
else:
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
