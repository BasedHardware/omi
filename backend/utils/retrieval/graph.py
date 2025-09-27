import datetime
import uuid
import asyncio
from typing import List, Optional, Tuple, AsyncGenerator, Annotated, Any

from langchain.callbacks.base import BaseCallbackHandler
import operator
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, AnyMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END
from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict, Literal

# import os
# os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
import database.conversations as conversations_db
import database.users as users_db
from database.redis_db import get_filter_category_items
from database.vector_db import query_vectors_by_metadata
import database.notifications as notification_db
from models.app import App
from models.chat import ChatSession, Message
from models.conversation import Conversation
from models.other import Person
from utils.llm.chat import (
    answer_omi_question,
    answer_omi_question_stream,
    requires_context,
    answer_simple_message,
    answer_simple_message_stream,
    retrieve_context_dates_by_question,
    qa_rag,
    qa_rag_stream,
    retrieve_is_an_omi_question,
    retrieve_is_file_question,
    select_structured_filters,
    extract_question_from_conversation,
    final_answer,
    final_answer_stream,
)
from utils.llm.persona import answer_persona_question_stream
from utils.other.chat_file import FileChatTool
from utils.other.endpoints import timeit
from utils.app_integrations import get_github_docs_content

# IMPORTS: ADDING process human messages into memories and action items
from models.transcript_segment import TranscriptSegment
from models.conversation import ConversationStatus, ConversationSource
from utils.conversations.process_conversation import _extract_memories, _save_action_items, _extract_trends
import database.conversations as conversations_db
from utils.llm.conversation_processing import get_transcript_structure

# MCP tools
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict, Literal

model = ChatOpenAI(model="gpt-4o-mini")
llm_medium_stream = ChatOpenAI(model='gpt-4o', streaming=True)
# This model will be specifically for the agent's decision-making
# In graph.py

from langchain_core.messages import SystemMessage

# This model will be specifically for the agent's decision-making
# A system prompt is bound to the model to give it strict instructions.
agent_model = ChatOpenAI(model="gpt-4o", temperature=0, streaming=True)


class StructuredFilters(TypedDict):
    topics: List[str]
    people: List[str]
    entities: List[str]
    dates: List[datetime.date]


class DateRangeFilters(TypedDict):
    start: datetime.datetime
    end: datetime.datetime


class AsyncStreamingCallback(BaseCallbackHandler):
    def __init__(self):
        self.queue = asyncio.Queue()

    async def put_data(self, text):
        await self.queue.put(f"data: {text}")

    async def put_thought(self, text):
        await self.queue.put(f"think: {text}")

    def put_thought_nowait(self, text):
        self.queue.put_nowait(f"think: {text}")

    async def end(self):
        await self.queue.put(None)

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        await self.put_data(token)

    async def on_llm_end(self, response, **kwargs) -> None:
        await self.end()

    async def on_llm_error(self, error: Exception, **kwargs) -> None:
        print(f"Error on LLM {error}")
        await self.end()

    def put_data_nowait(self, text):
        self.queue.put_nowait(f"data: {text}")

    def end_nowait(self):
        self.queue.put_nowait(None)


class GraphState(TypedDict):
    uid: str
    messages: List[Any]
    tool_messages: Annotated[List[AnyMessage], operator.add]
    plugin_selected: Optional[App]
    tz: str
    cited: Optional[bool] = False

    streaming: Optional[bool] = False
    callback: Optional[AsyncStreamingCallback] = None

    filters: Optional[StructuredFilters]
    date_filters: Optional[DateRangeFilters]

    memories_found: Optional[List[Conversation]]

    parsed_question: Optional[str]
    answer: Optional[str]
    final_answer: Optional[str]
    ask_for_nps: Optional[bool]

    chat_session: Optional[ChatSession]

    # ADDING process human messages into memories and action items
    should_process_insights: Optional[bool] = False
    pseudo_conversation: Optional[Conversation] = None
    insights_processed: Optional[bool] = False


############################################
############# MCP TOOLS ####################
############################################


# fucntion to fetch MCP tools
def get_user_tools(uid: str) -> List[Any]:
    """
    Get tools for a specific user from the app_state.
    This function accesses the global app_state from main.py
    """
    # Import here to avoid circular import
    from main import app_state

    # Get the MCP tools from app state
    mcp_tools = app_state.get("mcp_tools", [])
    return mcp_tools


# --- Agent Node Definitions ---


async def call_agent(state: GraphState):
    """Invokes the LLM with user-specific tools to decide on an action."""
    question = state.get("parsed_question", "")
    uid = state["uid"]

    # Get the real MCP tools for this user
    tools = get_user_tools(uid)

    if tools:
        model_with_tools = agent_model.bind_tools(tools)
    else:
        model_with_tools = agent_model

    # Use accumulated conversation context instead of starting fresh
    tool_messages = state.get("tool_messages", [])

    if tool_messages:
        # Continue existing conversation - agent sees its own history
        messages = tool_messages
    else:
        # First time - start new conversation
        system_prompt = (
            """You are an AI assistant with access to tools. When a user asks for information:

1. Use tools when you need external data
2. Once you get the required information from a tool, analyze it and provide a response
3. Do NOT repeatedly call the same tool with the same arguments
4. If you have sufficient information to answer the user's question, provide your response instead of calling more tools

The user is asking: """
            + question
        )

        messages = [SystemMessage(content=system_prompt), HumanMessage(content=question)]

    response = await model_with_tools.ainvoke(messages)
    return {"tool_messages": messages + [response]}


async def execute_tools_node(state: GraphState):
    """Executes the tools requested by the agent."""
    uid = state["uid"]

    # Get the real MCP tools for this user
    tools = get_user_tools(uid)

    if not tools:
        error_message = AIMessage(content="I don't have access to any tools right now. Please try again later.")
        return {"tool_messages": state["tool_messages"] + [error_message]}

    # Get existing tool_messages and prepare state for ToolNode
    tool_messages = state.get("tool_messages", [])

    # ToolNode expects the conversation to be in 'messages' field
    tool_state = {
        **state,  # Copy all existing state
        "messages": tool_messages.copy(),  # Put our tool conversation in messages
    }

    tool_node = ToolNode(tools)

    try:
        result = await tool_node.ainvoke(tool_state)

        # ToolNode returns ONLY the new tool execution results
        if isinstance(result, dict) and "messages" in result:
            tool_result_messages = result["messages"]

            if len(tool_result_messages) > 0:
                # Return the tool results to be added to tool_messages
                return {"tool_messages": tool_result_messages}
            else:
                return {}

        return {}
    except Exception as e:
        print(f"Tool execution error: {e}")
        error_message = AIMessage(content=f"Tool execution failed: {str(e)}")
        return {"tool_messages": state["tool_messages"] + [error_message]}


# --- Conditional Edge Logic ---


def should_use_tools(state: GraphState) -> Literal["tools", "__end__"]:
    """The router that decides whether to use tools or end the agent's turn."""
    tool_messages = state.get("tool_messages", [])

    if not tool_messages:
        return "__end__"

    last_message = tool_messages[-1]

    if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        # Check for repetitive tool calls
        current_calls = [f"{tc['name']}({tc['args']})" for tc in last_message.tool_calls]

        # Look for previous AI messages with tool calls
        ai_messages_with_tools = [msg for msg in tool_messages if hasattr(msg, 'tool_calls') and msg.tool_calls]

        if len(ai_messages_with_tools) > 1:
            prev_ai_msg = ai_messages_with_tools[-2]  # Second to last
            prev_calls = [f"{tc['name']}({tc['args']})" for tc in prev_ai_msg.tool_calls]

            if current_calls == prev_calls:
                return "__end__"

        return "tools"

    return "__end__"


def determine_conversation(state: GraphState):
    print("determine_conversation")
    question = extract_question_from_conversation(state.get("messages", []))
    print("determine_conversation parsed question:", question)

    # # stream
    # if state.get('streaming', False):
    #     state['callback'].put_thought_nowait(question)

    return {"parsed_question": question}


def determine_conversation_type(
    state: GraphState,
) -> Literal[
    "no_context_conversation",
    "context_dependent_conversation",
    "omi_question",
    "file_chat_question",
    "persona_question",
]:
    # chat with files by attachments on the last message
    print("determine_conversation_type")
    messages = state.get("messages", [])
    if len(messages) > 0 and len(messages[-1].files_id) > 0:
        return "file_chat_question"

    # persona
    app: App = state.get("plugin_selected")
    if app and app.is_a_persona():
        # file
        question = state.get("parsed_question", "")
        is_file_question = retrieve_is_file_question(question)
        if is_file_question:
            return "file_chat_question"

        return "persona_question"

    # chat
    # no context
    question = state.get("parsed_question", "")
    if not question or len(question) == 0:
        return "no_context_conversation"

    # determine the follow-up question is chatting with files or not
    is_file_question = retrieve_is_file_question(question)
    if is_file_question:
        return "file_chat_question"

    is_omi_question = retrieve_is_an_omi_question(question)
    if is_omi_question:
        return "omi_question"

    requires = requires_context(question)
    if requires:
        return "context_dependent_conversation"
    return "no_context_conversation"


def no_context_conversation(state: GraphState):
    print("no_context_conversation node")

    # no streaming - let final_answer_processor handle streaming
    answer: str = answer_simple_message(
        state.get("uid"),
        state.get("messages"),
        state.get("plugin_selected"),
    )
    return {"answer": answer, "ask_for_nps": False}


def omi_question(state: GraphState):
    print("no_context_omi_question node")

    context: dict = get_github_docs_content()
    context_str = 'Documentation:\n\n'.join([f'{k}:\n {v}' for k, v in context.items()])

    # no streaming - let final_answer_processor handle streaming
    answer = answer_omi_question(state.get("messages", []), context_str)
    return {'answer': answer, 'ask_for_nps': True}


def persona_question(state: GraphState):
    print("persona_question node")

    # no streaming - let final_answer_processor handle streaming
    # TODO: Add proper non-streaming persona implementation
    return {'answer': "Persona response", 'ask_for_nps': True}


def context_dependent_conversation_v1(state: GraphState):
    question = extract_question_from_conversation(state.get("messages", []))
    print("context_dependent_conversation parsed question:", question)
    return {"parsed_question": question}


def context_dependent_conversation(state: GraphState):
    return state


# !! include a question extractor? node?


def retrieve_topics_filters(state: GraphState):
    print("retrieve_topics_filters")
    filters = {
        "people": get_filter_category_items(state.get("uid"), "people", limit=1000),
        "topics": get_filter_category_items(state.get("uid"), "topics", limit=1000),
        "entities": get_filter_category_items(state.get("uid"), "entities", limit=1000),
        # 'dates': get_filter_category_items(state.get('uid'), 'dates'),
    }
    result = select_structured_filters(state.get("parsed_question", ""), filters)
    filters = {
        "topics": result.get("topics", []),
        "people": result.get("people", []),
        "entities": result.get("entities", []),
        # 'dates': result.get('dates', []),
    }
    print("retrieve_topics_filters filters", filters)
    return {"filters": filters}


def retrieve_date_filters(state: GraphState):
    print('retrieve_date_filters')
    # TODO: if this makes vector search fail further, query firestore instead
    dates_range = retrieve_context_dates_by_question(state.get("parsed_question", ""), state.get("tz", "UTC"))
    print('retrieve_date_filters dates_range:', dates_range)
    if dates_range and len(dates_range) >= 2:
        return {"date_filters": {"start": dates_range[0], "end": dates_range[1]}}
    return {"date_filters": {}}


def query_vectors(state: GraphState):
    print("query_vectors")

    # # stream
    # if state.get('streaming', False):
    #     state['callback'].put_thought_nowait("Searching through your memories")

    date_filters = state.get("date_filters")
    uid = state.get("uid")
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
    memories_id = query_vectors_by_metadata(
        uid,
        vector,
        dates_filter=[date_filters.get("start"), date_filters.get("end")],
        people=state.get("filters", {}).get("people", []) if is_topic_filter_enabled else [],
        topics=state.get("filters", {}).get("topics", []) if is_topic_filter_enabled else [],
        entities=state.get("filters", {}).get("entities", []) if is_topic_filter_enabled else [],
        dates=state.get("filters", {}).get("dates", []),
        limit=100,
    )
    memories = conversations_db.get_conversations_by_id(uid, memories_id)

    # Filter out locked conversations if user doesn't have premium access
    memories = [m for m in memories if not m.get('is_locked', False)]

    # stream
    # if state.get('streaming', False):
    #    if len(memories) == 0:
    #        msg = "No relevant memories found"
    #    else:
    #        msg = f"Found {len(memories)} relevant memories"
    #    state['callback'].put_thought_nowait(msg)

    # print(memories_id)
    return {"memories_found": memories}


def qa_handler(state: GraphState):
    uid = state.get("uid")
    memories = state.get("memories_found", [])

    all_person_ids = []
    for m in memories:
        # m is a dict
        segments = m.get('transcript_segments', [])
        all_person_ids.extend([s.get('person_id') for s in segments if s.get('person_id')])

    people = []
    if all_person_ids:
        people_data = users_db.get_people_by_ids(uid, list(set(all_person_ids)))
        people = [Person(**p) for p in people_data]

    # no streaming - let final_answer_processor handle streaming
    response: str = qa_rag(
        uid,
        state.get("parsed_question"),
        Conversation.conversations_to_string(memories, False, people=people),
        state.get("plugin_selected"),
        cited=state.get("cited"),
        messages=state.get("messages"),
        tz=state.get("tz"),
    )
    return {"answer": response, "ask_for_nps": True}


def file_chat_question(state: GraphState):
    print("chat_with_file_question node")

    fc_tool = FileChatTool()

    uid = state.get("uid", "")
    question = state.get("parsed_question", "")

    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None

    file_ids = []
    chat_session = state.get("chat_session")
    if chat_session:
        if last_message:
            if len(last_message.files_id) > 0:
                file_ids = last_message.files_id
            else:
                # if user asked about file but not attach new file, will get all file in session
                file_ids = chat_session.file_ids
    else:
        file_ids = fc_tool.get_files()

    # no streaming - let final_answer_processor handle streaming
    answer = fc_tool.process_chat_with_file(uid, question, file_ids)
    return {'answer': answer, 'ask_for_nps': True}


# ADDING process human messages into memories and action items
def should_process_chat_insights(state: GraphState) -> str:
    """Decide if the last message needs insights processing."""
    messages = state.get("messages", [])
    if not messages:
        return "continue"

    last_message = messages[-1]
    # Only process human messages for insights
    if last_message.sender == "human":
        return "process_insights"
    return "continue"


def should_run_mcp_tools(state: GraphState) -> str:
    """Decide if MCP tools should run for this conversation."""
    uid = state.get("uid")
    question = state.get("parsed_question", "")
    tools = get_user_tools(uid)

    # Run MCP tools if user has any available tools and a question
    if tools and question.strip():
        return "run_mcp"
    else:
        return "continue"


def create_pseudo_conversation_node(state: GraphState) -> GraphState:
    """Convert chat message to conversation format for pipeline reuse."""

    messages = state.get("messages", [])
    if not messages:
        return state

    last_message = messages[-1]
    uid = state.get("uid")
    tz = state.get("tz", "UTC")

    # Get user language preference
    language_code = users_db.get_user_language_preference(uid) or 'en'

    try:
        # Use existing conversation processing to get structured data
        structured = get_transcript_structure(last_message.text, last_message.created_at, language_code, tz)

        # Create pseudo transcript segment
        transcript_segment = TranscriptSegment(
            id=str(uuid.uuid4()),
            text=last_message.text,
            speaker='SPEAKER_01',
            speaker_id=1,
            is_user=True,
            person_id=uid,
            start=0.0,
            end=1.0,
            translations=[],
            speech_profile_processed=True,
        )

        # Create pseudo conversation
        pseudo_conversation = Conversation(
            id=f"chat_message_{last_message.id}",
            uid=uid,
            created_at=last_message.created_at,
            started_at=last_message.created_at,
            finished_at=last_message.created_at,
            structured=structured,
            transcript_segments=[transcript_segment],
            language=language_code,
            status=ConversationStatus.completed,
            source=ConversationSource.omi,
            discarded=False,
            postprocessing=None,
            geolocation=None,
            photos=[],
            plugins_results=[],
            apps_results=[],
            external_data={},
            analysis_results=[],
        )

        print(f"Created pseudo conversation for message {last_message.id}")
        return {**state, "pseudo_conversation": pseudo_conversation}

    except Exception as e:
        print(f"Error creating pseudo conversation: {e}")
        return state


def extract_memories_node(state: GraphState) -> GraphState:
    """Extract memories from pseudo conversation."""
    pseudo_conversation = state.get("pseudo_conversation")
    uid = state.get("uid")

    if pseudo_conversation and uid:
        try:
            _extract_memories(uid, pseudo_conversation)
            print(f"Extracted memories for pseudo conversation {pseudo_conversation.id}")
        except Exception as e:
            print(f"Error extracting memories: {e}")

    return state


def save_action_items_node(state: GraphState) -> GraphState:
    """Save action items from pseudo conversation."""
    pseudo_conversation = state.get("pseudo_conversation")
    uid = state.get("uid")

    if pseudo_conversation and uid:
        try:
            _save_action_items(uid, pseudo_conversation)
            print(f"Saved action items for pseudo conversation {pseudo_conversation.id}")
        except Exception as e:
            print(f"Error saving action items: {e}")

    return state


def extract_trends_node(state: GraphState) -> GraphState:
    """Extract trends from pseudo conversation."""
    pseudo_conversation = state.get("pseudo_conversation")
    uid = state.get("uid")

    if pseudo_conversation and uid:
        try:
            _extract_trends(uid, pseudo_conversation)
            print(f"Extracted trends for pseudo conversation {pseudo_conversation.id}")
        except Exception as e:
            print(f"Error extracting trends: {e}")

    return {**state, "insights_processed": True}


def continue_chat_node(state: GraphState) -> GraphState:
    """Continue with normal chat flow."""
    return state


def final_answer_node(state: GraphState):
    streaming = state.get("streaming")
    question = state.get("parsed_question", "")
    answer = state.get("answer", "")  # Get answer from previous pipeline step
    tool_messages = state.get("tool_messages", [])

    # Check if we have MCP tool results
    has_tool_results = len(tool_messages) > 0

    # If no MCP results and no pipeline answer, we need to run the pipeline first
    if not has_tool_results and not answer:
        # This shouldn't happen with proper routing, but handle gracefully
        return {"answer": "I need more information to help you with that request."}

    # Combine MCP results with pipeline answer (or use MCP results if no pipeline answer)
    if streaming:
        callback = state.get('callback')
        callbacks = [callback] if callback else []
        result = final_answer_stream(question, answer, tool_messages, callbacks=callbacks)
        return {"final_answer": result}

    # no streaming
    result = final_answer(question, answer, tool_messages)
    return {"final_answer": result}


# TODO: could be optimized using parallization or subgraphs.
# Start with insights check
def create_agent_graph():
    workflow = StateGraph(GraphState)
    workflow.add_edge(START, "check_insights")

    # Insights check
    workflow.add_node("check_insights", lambda state: state)  # Pass-through for routing
    workflow.add_conditional_edges(
        "check_insights",
        should_process_chat_insights,
        {
            "process_insights": "create_pseudo_conversation",
            "continue": "determine_conversation",  # Skip insights, extract question first
        },
    )

    # Insights processing pipeline (runs BEFORE conversation processing)
    workflow.add_node("create_pseudo_conversation", create_pseudo_conversation_node)
    workflow.add_node("extract_memories", extract_memories_node)
    workflow.add_node("save_action_items", save_action_items_node)
    workflow.add_node("extract_trends", extract_trends_node)

    workflow.add_edge("create_pseudo_conversation", "extract_memories")
    workflow.add_edge("extract_memories", "save_action_items")
    workflow.add_edge("save_action_items", "extract_trends")
    workflow.add_edge("extract_trends", "determine_conversation")  # After insights, extract question

    # Question extraction happens first (after insights or directly)
    workflow.add_node("determine_conversation", determine_conversation)
    workflow.add_edge("determine_conversation", "mcp_or_continue")  # After question extraction, decide MCP

    # MCP decision point
    workflow.add_node("mcp_or_continue", lambda state: state)
    workflow.add_conditional_edges(
        "mcp_or_continue",
        should_run_mcp_tools,
        {
            "run_mcp": "call_agent",  # Start MCP flow with parsed question
            "continue": "route_conversation",  # Skip MCP, go to conversation routing
        },
    )

    # MCP tools nodes
    workflow.add_node("call_agent", call_agent)
    workflow.add_node("tools", execute_tools_node)
    workflow.add_node("final_answer_processor", final_answer_node)

    # MCP flow: call_agent -> tools (if needed) -> route_conversation (always)
    workflow.add_conditional_edges(
        "call_agent",
        should_use_tools,
        {"tools": "tools", "__end__": "route_conversation"},  # Always go to normal conversation after MCP
    )
    workflow.add_edge("tools", "call_agent")  # Loop back to agent after tool use

    # Conversation type routing (runs after MCP completion OR if MCP skipped)
    workflow.add_node("route_conversation", lambda state: state)
    workflow.add_conditional_edges("route_conversation", determine_conversation_type)

    workflow.add_node("no_context_conversation", no_context_conversation)
    workflow.add_node("omi_question", omi_question)
    workflow.add_node("context_dependent_conversation", context_dependent_conversation)
    workflow.add_node("file_chat_question", file_chat_question)
    workflow.add_node("persona_question", persona_question)

    # All conversation types go to final_answer_processor to combine with MCP results
    workflow.add_edge("no_context_conversation", "final_answer_processor")
    workflow.add_edge("omi_question", "final_answer_processor")
    workflow.add_edge("persona_question", "final_answer_processor")
    workflow.add_edge("file_chat_question", "final_answer_processor")

    # RAG pipeline for context-dependent conversations
    workflow.add_edge("context_dependent_conversation", "retrieve_topics_filters")
    workflow.add_edge("context_dependent_conversation", "retrieve_date_filters")
    workflow.add_node("retrieve_topics_filters", retrieve_topics_filters)
    workflow.add_node("retrieve_date_filters", retrieve_date_filters)
    workflow.add_edge("retrieve_topics_filters", "query_vectors")
    workflow.add_edge("retrieve_date_filters", "query_vectors")
    workflow.add_node("query_vectors", query_vectors)
    workflow.add_edge("query_vectors", "qa_handler")
    workflow.add_node("qa_handler", qa_handler)
    workflow.add_edge("qa_handler", "final_answer_processor")

    # Final answer processor goes to END
    workflow.add_edge("final_answer_processor", END)

    checkpointer = MemorySaver()
    graph = workflow.compile(checkpointer=checkpointer)
    graph_stream = workflow.compile()
    return graph, graph_stream


graph, graph_stream = create_agent_graph()


@timeit
def execute_graph_chat(
    uid: str, messages: List[Message], app: Optional[App] = None, cited: Optional[bool] = False
) -> Tuple[str, bool, List[Conversation]]:
    print('execute_graph_chat app    :', app.id if app else '<none>')
    tz = notification_db.get_user_time_zone(uid)
    result = graph.invoke(
        {"uid": uid, "tz": tz, "cited": cited, "messages": messages, "plugin_selected": app},
        {"configurable": {"thread_id": str(uuid.uuid4())}},
    )
    return (
        result.get("final_answer", result.get("answer", "")),
        result.get('ask_for_nps', False),
        result.get("memories_found", []),
    )


async def execute_graph_chat_stream(
    uid: str,
    messages: List[Message],
    app: Optional[App] = None,
    cited: Optional[bool] = False,
    callback_data: dict = {},
    chat_session: Optional[ChatSession] = None,
) -> AsyncGenerator[str, None]:
    print('execute_graph_chat_stream app: ', app.id if app else '<none>')
    tz = notification_db.get_user_time_zone(uid)
    callback = AsyncStreamingCallback()

    task = asyncio.create_task(
        graph_stream.ainvoke(
            {
                "uid": uid,
                "tz": tz,
                "cited": cited,
                "messages": messages,
                "plugin_selected": app,
                "streaming": True,
                "callback": callback,
                "chat_session": chat_session,
            },
            {"configurable": {"thread_id": str(uuid.uuid4())}},
        )
    )

    while True:
        try:
            chunk = await callback.queue.get()
            if chunk:
                yield chunk
            else:
                break
        except asyncio.CancelledError:
            break
    await task
    result = task.result()
    callback_data['answer'] = result.get("final_answer", result.get("answer", ""))
    callback_data['memories_found'] = result.get("memories_found", [])
    callback_data['ask_for_nps'] = result.get('ask_for_nps', False)

    yield None
    return


async def execute_persona_chat_stream(
    uid: str,
    messages: List[Message],
    app: App,
    cited: Optional[bool] = False,
    callback_data: dict = None,
    chat_session: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Handle streaming chat responses for persona-type apps"""

    system_prompt = app.persona_prompt
    formatted_messages = [SystemMessage(content=system_prompt)]

    for msg in messages:
        if msg.sender == "ai":
            formatted_messages.append(AIMessage(content=msg.text))
        else:
            formatted_messages.append(HumanMessage(content=msg.text))

    full_response = []
    callback = AsyncStreamingCallback()

    try:
        task = asyncio.create_task(llm_medium_stream.agenerate(messages=[formatted_messages], callbacks=[callback]))

        while True:
            try:
                chunk = await callback.queue.get()
                if chunk:
                    token = chunk.replace("data: ", "")
                    full_response.append(token)
                    yield chunk
                else:
                    break
            except asyncio.CancelledError:
                break

        await task

        if callback_data is not None:
            callback_data['answer'] = ''.join(full_response)
            callback_data['memories_found'] = []
            callback_data['ask_for_nps'] = False

        yield None
        return

    except Exception as e:
        print(f"Error in execute_persona_chat_stream: {e}")
        if callback_data is not None:
            callback_data['error'] = str(e)
        yield None
        return
