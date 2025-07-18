import os
from typing import List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import tiktoken

from models.conversation import Structured


llm_mini = ChatOpenAI(model='gpt-4o-mini')
llm_mini_stream = ChatOpenAI(model='gpt-4o-mini', streaming=True)
llm_large = ChatOpenAI(model='o1-preview')
llm_large_stream = ChatOpenAI(model='o1-preview', streaming=True, temperature=1)
llm_high = ChatOpenAI(model='o4-mini')
llm_high_stream = ChatOpenAI(model='o4-mini', streaming=True, temperature=1)
llm_medium = ChatOpenAI(model='gpt-4o')
llm_medium_experiment = ChatOpenAI(model='gpt-4.1')
llm_medium_stream = ChatOpenAI(model='gpt-4o', streaming=True)
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
