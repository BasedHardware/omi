import os
from typing import List

from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import tiktoken

from models.conversation import Structured
from pydantic import BaseModel, Field


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
llm_title_generator = ChatOpenAI(
    model='gpt-4o-mini',
    temperature=0.3,
    max_tokens=20,
)
llm_date_parser = ChatOpenAI(
    model='gpt-4o-mini',
    temperature=0.1,  # Low temperature for consistent date parsing
    max_tokens=150,  # Enough for structured date output
)
llm_tool_decision = ChatOpenAI(
    model='gpt-4o-mini',
    temperature=0.1,  # Low temperature for consistent decision making
    max_tokens=50,  # We only need a simple structured response
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


class DateRange(BaseModel):
    """Structured output for LLM date parsing"""

    start_date: str = Field(description="Start datetime in ISO format with UTC timezone (e.g., '2025-09-08T00:00:00Z')")
    end_date: str = Field(description="End datetime in ISO format with UTC timezone (e.g., '2025-09-08T23:59:59Z')")
    original_query: str = Field(description="The original user query")
    interpretation: str = Field(description="Brief explanation of how the date was interpreted")


class ToolDecision(BaseModel):
    """Structured output for tool usage decision"""

    needs_tools: bool = Field(description="True if the question requires personal data tools, False otherwise")
    reasoning: str = Field(description="Brief explanation of the decision")
    suggested_tool_type: str = Field(
        description="Type of tool likely needed: 'memories', 'conversations', 'action_items', or 'none'"
    )


def parse_user_date_query(user_date_query: str, current_time_utc: str) -> DateRange:
    """
    Use GPT-4o-mini to parse user date queries into precise datetime ranges.
    CRITICAL: Returns dates that are compatible with database storage format.

    Args:
        user_date_query: User's natural language date query (e.g., "yesterday", "2 hours ago")
        current_time_utc: Current time in UTC ISO format for reference

    Returns:
        DateRange with start_date and end_date in ISO format compatible with database
    """

    prompt = f"""You are a precise date parser for a database that stores timestamps as Python datetime objects with timezone.utc.

CURRENT TIME (UTC): {current_time_utc}
USER QUERY: "{user_date_query}"

DATABASE FORMAT REQUIREMENTS:
- All timestamps stored as: datetime.now(timezone.utc) 
- Filter queries use: FieldFilter('created_at', '>=', start_date)
- Database expects: Python datetime objects with timezone.utc

YOUR TASK: Return ISO strings that convert perfectly to database-compatible datetime objects.

RULES:
1. ALWAYS return dates in UTC with 'Z' suffix: "2025-09-08T00:00:00Z"
2. For day queries ("yesterday", "today"), use FULL DAY ranges:
   - Start: "2025-09-08T00:00:00Z" (beginning of day)
   - End: "2025-09-08T23:59:59.999999Z" (end of day with microseconds)
3. For time queries ("2 hours ago"), use precise timestamps from current time
4. For relative queries ("last week"), use appropriate boundaries
5. CRITICAL: Ensure dates will convert to datetime objects with timezone.utc

EXAMPLES (given current time {current_time_utc}):
- "yesterday" → start: "2025-09-09T00:00:00Z", end: "2025-09-09T23:59:59.999999Z"
- "2 hours ago" → start: "2025-09-10T12:30:00Z", end: "{current_time_utc}"
- "today" → start: "2025-09-10T00:00:00Z", end: "2025-09-10T23:59:59.999999Z"
- "september 6th" → start: "2025-09-06T00:00:00Z", end: "2025-09-06T23:59:59.999999Z"

Return structured dates that will work perfectly with database queries."""

    structured_llm = llm_date_parser.with_structured_output(DateRange)
    result = structured_llm.invoke(prompt)

    return result


def should_use_tools_for_question(question: str) -> ToolDecision:
    """
    Use GPT-4o-mini to intelligently decide if a question requires personal data tools.
    More reliable than keyword matching for routing decisions.

    Args:
        question: User's question to analyze

    Returns:
        ToolDecision with needs_tools boolean and reasoning
    """

    prompt = f"""You are analyzing whether a user question requires personal data tools.

USER QUESTION: "{question}"

AVAILABLE TOOLS:
- get_user_memories: Retrieve user's personal memories/insights by date
- get_user_conversations: Retrieve user's conversation history by date  
- get_user_action_items: Retrieve user's tasks/action items by date

DECISION RULES:
✅ NEEDS TOOLS if question asks for:
- Personal memories ("my memories from yesterday", "what did I learn about X")
- Conversation history ("my conversations", "what did we discuss on Monday")
- Action items/tasks ("my tasks", "what do I need to do", "my pending items")
- Date-specific personal data ("September 6th conversations", "yesterday's memories")

❌ NO TOOLS NEEDED for:
- General knowledge questions ("how does AI work", "explain quantum physics")
- Casual conversation ("hello", "thanks", "how are you")
- External information requests ("weather today", "latest news")
- Abstract discussions not requiring personal data

Analyze the question and decide if personal data tools are needed."""

    structured_llm = llm_tool_decision.with_structured_output(ToolDecision)
    result = structured_llm.invoke(prompt)

    return result


class SingleTimestamp(BaseModel):
    """Single timestamp output for LLM parsing"""

    timestamp: str = Field(description="Single datetime in ISO format with UTC timezone (e.g., '2025-09-08T12:00:00Z')")
    original_query: str = Field(description="The original user query")
    interpretation: str = Field(description="Brief explanation of the timestamp")


def parse_single_timestamp(user_query: str, current_time_utc: str) -> SingleTimestamp:
    """Parse user query into a single precise timestamp compatible with database format."""

    prompt = f"""Parse the user's query into a single timestamp compatible with database storage format.

DATABASE FORMAT: datetime.now(timezone.utc) - Python datetime objects with timezone.utc
CURRENT TIME (UTC): {current_time_utc}
USER QUERY: "{user_query}"

RULES:
1. Return single timestamp in UTC with 'Z' suffix for database compatibility
2. For "1 day ago" → return start of that day: "2025-09-09T00:00:00Z"  
3. For "now" → return current moment: "{current_time_utc}"
4. For "2 hours ago" → return exact time 2 hours back
5. For "yesterday" → return start of yesterday: "2025-09-09T00:00:00Z"
6. CRITICAL: Ensure timestamp converts to datetime object with timezone.utc

EXAMPLES (database-compatible):
- "1 day ago" → "2025-09-09T00:00:00Z"
- "now" → "{current_time_utc}"
- "2 hours ago" → "2025-09-09T22:30:00Z"
- "yesterday" → "2025-09-09T00:00:00Z"
- "september 6th" → "2025-09-06T00:00:00Z"

Return timestamp that will work perfectly with database queries."""

    structured_llm = llm_date_parser.with_structured_output(SingleTimestamp)
    return structured_llm.invoke(prompt)
