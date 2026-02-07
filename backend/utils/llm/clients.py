import os
from typing import List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import tiktoken

from models.conversation import Structured
from utils.llm.usage_tracker import get_usage_callback

# Get the usage tracking callback
_usage_callback = get_usage_callback()

# Base models for general use
llm_mini = ChatOpenAI(model='gpt-4o-mini', callbacks=[_usage_callback])
llm_mini_stream = ChatOpenAI(
    model='gpt-4o-mini',
    streaming=True,
    stream_options={"include_usage": True},
    callbacks=[_usage_callback],
)
llm_large = ChatOpenAI(model='o1-preview', callbacks=[_usage_callback])
# Note: o1 models don't support streaming or temperature parameters
llm_large_stream = ChatOpenAI(
    model='o1-preview',
    callbacks=[_usage_callback],
)
llm_high = ChatOpenAI(model='o1-mini', callbacks=[_usage_callback])
# Note: o1 models don't support streaming or temperature parameters
llm_high_stream = ChatOpenAI(
    model='o1-mini',
    callbacks=[_usage_callback],
)
llm_medium = ChatOpenAI(model='gpt-4o', callbacks=[_usage_callback])
llm_medium_stream = ChatOpenAI(
    model='gpt-4o',
    streaming=True,
    stream_options={"include_usage": True},
    callbacks=[_usage_callback],
)
llm_medium_experiment = ChatOpenAI(model='gpt-4o', callbacks=[_usage_callback])

# Specialized models for agentic workflows
llm_agent = ChatOpenAI(model='gpt-4o', callbacks=[_usage_callback])
llm_agent_stream = ChatOpenAI(
    model='gpt-4o',
    streaming=True,
    stream_options={"include_usage": True},
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

embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
parser = PydanticOutputParser(pydantic_object=Structured)

encoding = tiktoken.encoding_for_model('gpt-4')


def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    num_tokens = len(encoding.encode(string))
    return num_tokens


def generate_embedding(content: str) -> List[float]:
    return embeddings.embed_documents([content])[0]
