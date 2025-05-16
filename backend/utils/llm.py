import json
import re
import os
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import tiktoken
from langchain.schema import (
    HumanMessage,
    SystemMessage,
    AIMessage,
)
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field, ValidationError

from database.redis_db import add_filter_category_item
from models.app import App
from models.chat import Message, MessageSender
from models.memories import Memory, MemoryCategory
from models.conversation import Structured, ConversationPhoto, CategoryEnum, Conversation, ActionItem, Event
from models.transcript_segment import TranscriptSegment
from models.trend import TrendEnum, ceo_options, company_options, software_product_options, hardware_product_options, \
    ai_product_options, TrendType
from utils.prompts import extract_memories_prompt, extract_learnings_prompt, extract_memories_text_content_prompt
from utils.llms.memory import get_prompt_memories

llm_mini = ChatOpenAI(model='gpt-4o-mini')
llm_mini_stream = ChatOpenAI(model='gpt-4o-mini', streaming=True)
llm_large = ChatOpenAI(model='o1-preview')
llm_large_stream = ChatOpenAI(model='o1-preview', streaming=True, temperature=1)
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


# TODO: include caching layer, redis


# **********************************************
# ********** CONVERSATION PROCESSING ***********
# **********************************************
# move to utils/llm/conversation_processing.py


# **************************************
# ************* OPENGLASS **************
# **************************************

# move to utils/llm/openglass.py


# **************************************************
# ************* EXTERNAL INTEGRATIONS **************
# **************************************************
# move to utils/llm/external_integrations.py


# ****************************************
# ************* CHAT BASICS **************
# ****************************************


# *********************************************
# ************* RETRIEVAL + CHAT **************
# *********************************************


# **************************************************
# ************* RETRIEVAL (EMOTIONAL) **************
# **************************************************

# moved to utils/llm/chat.py


# *********************************************
# ************* MEMORIES (FACTS) **************
# *********************************************


# **********************************
# ************* TRENDS **************
# **********************************
# moved to utils/llm/trends.py


# **********************************************************
# ************* RANDOM JOAN SPECIFIC FEATURES **************
# **********************************************************
# moved to utils/llm/followup.py


# **********************************************
# ************* CHAT V2 LANGGRAPH **************
# **********************************************
# moved to utils/llm/chat.py


# **************************************************
# ************* REALTIME V2 LANGGRAPH **************
# **************************************************
# moved to utils/llm/chat.py


# **************************************************
# ************* PROACTIVE NOTIFICATION *************
# **************************************************
# moved to utils/llm/proactive_notification.py


# **************************************************
# *************** APPS AI GENERATE *****************
# **************************************************


# **************************************************
# ******************* PERSONA **********************
# **************************************************
# moved to llm/persona.py


# **************************************************
# ***************** FACT/MEMORY ********************
# **************************************************
# moved to llm/memories.py



