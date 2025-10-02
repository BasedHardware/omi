import uuid
from dataclasses import dataclass
from typing import List, Optional, AsyncGenerator

from langchain.agents import create_agent, AgentState
from langchain_core.messages import AIMessageChunk
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.runtime import get_runtime

import database.conversations as conversations_db
from database.redis_db import get_filter_category_items
from database.vector_db import query_vectors_by_metadata
import database.notifications as notification_db
from models.app import App
from models.chat import ChatSession, Message
from utils.llm.chat import (
    retrieve_context_dates_by_question,
    select_structured_filters,
)
from utils.llm.clients import llm_mini_stream
from utils.llms.memory import get_prompt_data

@dataclass
class ContextSchema:
    uid: str
    tz: str


def retrieve_topics_filters(uid: str, question: str = "") -> dict:
    print("retrieve_topics_filters")
    filters = {
        "people": get_filter_category_items(uid, "people", limit=1000),
        "topics": get_filter_category_items(uid, "topics", limit=1000),
        "entities": get_filter_category_items(uid, "entities", limit=1000),
        # 'dates': get_filter_category_items(state.get('uid'), 'dates'),
    }
    result = select_structured_filters(question, filters)
    filters = {
        "topics": result.get("topics", []),
        "people": result.get("people", []),
        "entities": result.get("entities", []),
        # 'dates': result.get('dates', []),
    }
    print("retrieve_topics_filters filters", filters)
    return filters

def retrieve_date_filters(tz: str = "UTC", question: str = ""):
    print('retrieve_date_filters')

    # TODO: if this makes vector search fail further, query firestore instead
    dates_range = retrieve_context_dates_by_question(question, tz)
    print('retrieve_date_filters dates_range:', dates_range)
    if dates_range and len(dates_range) >= 2:
        return {"start": dates_range[0], "end": dates_range[1]}
    return {}

def query_vectors(uid: str, question: str, tz: str = "UTC", limit: int = 100):
    print("query_vectors")

    # # stream
    # if state.get('streaming', False):
    #     state['callback'].put_thought_nowait("Searching through your memories")

    date_filters = retrieve_date_filters(tz, question)
    filters = retrieve_topics_filters(uid, question)
    # vector = (
    #    generate_embedding(state.get("parsed_question", ""))
    #    if state.get("parsed_question")
    #    else [0] * 3072
    # )

    # Use [1] * dimension to trigger the score distance to fetch all vectors by meta filters
    vector = [1] * 3072
    print("query_vectors vector:", vector[:5])

    # TODO: enable it when the in-accurate topic filter get fixed
    is_topic_filter_enabled = date_filters.get("start") is None
    conversations_id = query_vectors_by_metadata(
        uid,
        vector,
        dates_filter=[date_filters.get("start"), date_filters.get("end")],
        people=filters.get("people", []) if is_topic_filter_enabled else [],
        topics=filters.get("topics", []) if is_topic_filter_enabled else [],
        entities=filters.get("entities", []) if is_topic_filter_enabled else [],
        dates=filters.get("dates", []),
        limit=100,
    )
    conversations = conversations_db.get_conversations_by_id(uid, conversations_id)

    # Filter out locked conversations if user doesn't have premium access
    conversations = [m for m in conversations if not m.get('is_locked', False)]

    # stream
    # if state.get('streaming', False):
    #    if len(memories) == 0:
    #        msg = "No relevant memories found"
    #    else:
    #        msg = f"Found {len(memories)} relevant memories"
    #    state['callback'].put_thought_nowait(msg)

    # print(memories_id)
    return conversations

@tool
def get_memories():
    """ Retrieve user memories.
    """
    runtime = get_runtime(ContextSchema)
    user_name, user_made_memories, generated_memories = get_prompt_data(runtime.context.uid)
    return {
        "user_name": user_name,
        "user_made_memories": user_made_memories,
        "memories_found": generated_memories,
    }

@tool
def get_conversations(question: str = ""):
    """ Retrieve user conversations.

    Args:
        question (str): The question to filter memories.
     """
    runtime = get_runtime(ContextSchema)
    return query_vectors(runtime.context.uid, runtime.context.tz, question)


checkpointer = MemorySaver()

graph_stream = create_agent(
    llm_mini_stream,
    [
        get_memories,
        get_conversations,
    ],
    checkpointer=checkpointer
)


async def execute_graph_chat_stream(
    uid: str,
    messages: List[Message],
    app: Optional[App] = None,
    cited: Optional[bool] = False,
    callback_data: dict = {},
    chat_session: Optional[ChatSession] = None,
) -> AsyncGenerator[str, None]:
    print('execute_graph_chat_stream agentic app: ', app.id if app else '<none>')
    tz = notification_db.get_user_time_zone(uid)

    async for event in graph_stream.astream(
            {
                # "cited": cited,
                "messages": Message.get_messages_as_dict(messages),
                # "plugin_selected": app,
                # "chat_session": chat_session,
            },
            context=ContextSchema(uid=uid, tz=tz),
            stream_mode=["messages", "custom"],
            config={"configurable": {"thread_id": str(uuid.uuid4())}},
            subgraphs=True,
    ):
        ns, stream_mode, payload = event

        if stream_mode == "messages":
            chunk, metadata = payload
            metadata: dict
            if chunk and isinstance(chunk, AIMessageChunk):
                # Skip silent chunks (e.g., follow-up actions generation)
                if metadata.get("silence"):
                    continue

                content = str(chunk.content)
                tool_calls = chunk.tool_calls

                # Show tool execution progress
                if tool_calls:
                    for tool_call in tool_calls:
                        tool_name_raw = tool_call.get("name")
                        print('tool_call', tool_name_raw)
                        if tool_name_raw:
                            tool_name = tool_name_raw.replace("_", " ").title()
                            yield f"think: Executing {tool_name}..."

                        # progress_data = format_tool_progress(tool_call)
                        # if progress_data:
                        #     yield format_sse_data(progress_data)

                # Only yield content from the main agent to avoid duplication
                if content and len(ns) == 0:
                    yield f"data: {content}"

        elif stream_mode == "custom":
            # Forward custom events as is
            yield f"data: {payload}"

    yield None
    return
