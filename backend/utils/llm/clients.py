import os
from typing import List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import tiktoken

from models.conversation import Structured


# Check if Groq API is available for high-speed inference
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
USE_GROQ = bool(GROQ_API_KEY)

# Lazy import for Groq to avoid import errors if not installed
if USE_GROQ:
    try:
        from langchain_groq import ChatGroq
    except ImportError:
        USE_GROQ = False
        ChatGroq = None


# Base models for general use
llm_mini = ChatOpenAI(model='gpt-4.1-mini')
llm_mini_stream = ChatOpenAI(model='gpt-4.1-mini', streaming=True)
llm_large = ChatOpenAI(model='o1-preview')
llm_large_stream = ChatOpenAI(model='o1-preview', streaming=True, temperature=1)
llm_high = ChatOpenAI(model='o4-mini')
llm_high_stream = ChatOpenAI(model='o4-mini', streaming=True, temperature=1)
llm_medium = ChatOpenAI(model='gpt-4.1')
llm_medium_stream = ChatOpenAI(model='gpt-4.1', streaming=True)
llm_medium_experiment = ChatOpenAI(model='gpt-5.1')

# Specialized models for agentic workflows
llm_agent = ChatOpenAI(model='gpt-5.1')
llm_agent_stream = ChatOpenAI(model='gpt-5.1', streaming=True)


# =============================================================================
# GROQ HIGH-SPEED INFERENCE MODELS
# =============================================================================
# Groq provides extremely fast inference (~200ms) using their LPU (Language
# Processing Unit) hardware. These models are ideal for:
# - Real-time chat responses
# - Quick question answering
# - Low-latency applications
# - Teacher/tutor apps that need instant feedback
#
# Available Groq models:
# - llama-3.1-8b-instant: Fastest, good for simple tasks (~200ms)
# - llama-3.1-70b-versatile: Balanced speed/quality (~500ms)
# - llama-3.3-70b-versatile: Latest, best quality (~500ms)
# - mixtral-8x7b-32768: Good for longer context
# =============================================================================

if USE_GROQ:
    # Fast models - optimized for speed (~200ms response time)
    llm_groq_fast = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.3,
        max_tokens=512,
        api_key=GROQ_API_KEY,
    )
    llm_groq_fast_stream = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.3,
        max_tokens=512,
        api_key=GROQ_API_KEY,
        streaming=True,
    )
    
    # Medium models - balanced speed and quality (~500ms response time)
    llm_groq_medium = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.5,
        max_tokens=1024,
        api_key=GROQ_API_KEY,
    )
    llm_groq_medium_stream = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.5,
        max_tokens=1024,
        api_key=GROQ_API_KEY,
        streaming=True,
    )
    
    # Long context model - for documents and extended conversations
    llm_groq_long_context = ChatGroq(
        model="mixtral-8x7b-32768",
        temperature=0.5,
        max_tokens=2048,
        api_key=GROQ_API_KEY,
    )
    llm_groq_long_context_stream = ChatGroq(
        model="mixtral-8x7b-32768",
        temperature=0.5,
        max_tokens=2048,
        api_key=GROQ_API_KEY,
        streaming=True,
    )
else:
    # Fallback to OpenAI if Groq is not available
    llm_groq_fast = llm_mini
    llm_groq_fast_stream = llm_mini_stream
    llm_groq_medium = llm_medium
    llm_groq_medium_stream = llm_medium_stream
    llm_groq_long_context = llm_medium
    llm_groq_long_context_stream = llm_medium_stream


def get_fast_llm(prefer_groq: bool = True):
    """
    Get the fastest available LLM client.
    
    Args:
        prefer_groq: If True, use Groq when available for ~5x faster responses.
                    If False, always use OpenAI.
    
    Returns:
        LLM client (ChatGroq or ChatOpenAI)
    """
    if prefer_groq and USE_GROQ:
        return llm_groq_fast
    return llm_mini


def get_fast_llm_stream(prefer_groq: bool = True):
    """
    Get the fastest available streaming LLM client.
    
    Args:
        prefer_groq: If True, use Groq when available for ~5x faster responses.
                    If False, always use OpenAI.
    
    Returns:
        Streaming LLM client (ChatGroq or ChatOpenAI)
    """
    if prefer_groq and USE_GROQ:
        return llm_groq_fast_stream
    return llm_mini_stream


def is_groq_available() -> bool:
    """Check if Groq high-speed inference is available."""
    return USE_GROQ


# Persona models using OpenRouter
llm_persona_mini_stream = ChatOpenAI(
    temperature=0.8,
    model="google/gemini-flash-1.5-8b",
    api_key=os.environ.get('OPENROUTER_API_KEY'),
    base_url="https://openrouter.ai/api/v1",
    default_headers={"X-Title": "Omi Chat"},
    streaming=True,
)
llm_persona_medium_stream = ChatOpenAI(
    temperature=0.8,
    model="anthropic/claude-3.5-sonnet",
    api_key=os.environ.get('OPENROUTER_API_KEY'),
    base_url="https://openrouter.ai/api/v1",
    default_headers={"X-Title": "Omi Chat"},
    streaming=True,
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
