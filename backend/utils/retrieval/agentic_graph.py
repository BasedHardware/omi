import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, AsyncGenerator, Annotated

from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.tools import InjectedState
from langchain_core.messages import AIMessageChunk, AIMessage, ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.checkpoint.memory import MemorySaver
from langgraph.runtime import get_runtime
from langgraph.types import Command
from pydantic import BaseModel

import database.action_items as action_items_db
import database.conversations as conversations_db
from database.redis_db import get_filter_category_items
from database.vector_db import query_vectors_by_metadata
import database.notifications as notification_db
from models.app import App
from models.chat import ChatSession, Message
from models.conversation import Conversation, ActionItem
from models.memories import Memory
from utils.app_integrations import get_github_docs_content
from utils.llm.chat import (
    retrieve_context_dates_by_question,
    select_structured_filters
)
from utils.llm.clients import llm_mini_stream, llm_persona_medium_stream, llm_persona_mini_stream
from utils.llms.memory import get_prompt_data
from utils.other.chat_file import FileChatTool
from utils.retrieval.state import BaseAgentState


@dataclass
class Context:
    uid: str
    tz: str
    chat_session: Optional[ChatSession] = None
    files: Optional[List[str]] = None


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
def get_memories(question: str = "",
                 state: Annotated[AgentState, InjectedState] = None,
                 tool_call_id: Annotated[str, InjectedToolCallId] = ""
                 ) -> Command:
    """ Retrieve user memories.
    """
    print(f"get_memories: {question}")
    runtime = get_runtime(Context)
    user_name, user_made_memories, generated_memories = get_prompt_data(runtime.context.uid)
    memories_str = (
        f'you already know the following facts about {user_name}: \n{Memory.get_memories_as_str(generated_memories)}.'
    )
    if user_made_memories:
        memories_str += (
            f'\n\n{user_name} also shared the following about self: \n{Memory.get_memories_as_str(user_made_memories)}'
        )

    return Command(update={
        # 'memories': user_made_memories + generated_memories, # TODO: Refs to memories aren't supported yet
        'messages': [ToolMessage(content=memories_str, tool_call_id=tool_call_id)]})

@tool
def get_conversations(question: str = "",
                      state: Annotated[AgentState, InjectedState] = None,
                      tool_call_id: Annotated[str, InjectedToolCallId] = ""
                      ) -> Command:
    """ Retrieve user conversations.

    Args:
        question (str): The question to filter memories.
     """
    print(f"get_conversations: {question}")
    runtime = get_runtime(Context)
    conversations = query_vectors(runtime.context.uid, question, runtime.context.tz)
    return Command(update={
        'conversations': conversations,
        'messages': [ToolMessage(content=Conversation.conversations_to_string(conversations), tool_call_id=tool_call_id)]})

@tool
def get_actions(question: str = "",
                      state: Annotated[AgentState, InjectedState] = None,
                      tool_call_id: Annotated[str, InjectedToolCallId] = ""
                      ) -> Command:
    """ Retrieve user actions.

    Args:
        question (str): The question to filter user actions.
     """
    print(f"get_actions: {question}")
    runtime = get_runtime(Context)

    action_items = action_items_db.get_action_items(
        uid=runtime.context.uid,
        # conversation_id=conversation_id,
        # completed=completed,
        # start_date=start_date,
        # end_date=end_date,
        # limit=limit,
        # offset=offset,
    )

    return Command(update={
        'messages': [ToolMessage(content=ActionItem.actions_to_string(action_items), tool_call_id=tool_call_id)]})

@tool
def get_omi_documentation():
    """ Retrieve Omi device and app documentation to answer all questions like:
    - How does it work?
    - What can you do?
    - How can I buy it?
    - Where do I get it?
    - How does the chat function?
    """
    context: dict = get_github_docs_content(path='docs')
    return 'Documentation:\n\n'.join([f'{k}:\n {v}' for k, v in context.items()])

class ResponseFormat(BaseModel):
    answer: str
    memories_found: Optional[List[str]]
    ask_for_nps: bool = False

# checkpointer = MemorySaver()

# graph_stream = create_agent(
#     llm_mini_stream,
#     [
#         get_memories,
#         get_conversations,
#         # get_omi_documentation,  TODO: Current doc must be formatted other way
#     ],
#     prompt="""You are a helpful assistant of wearable AI device named Omi.
#     Add text of memories returned by get_memories to response.""",
#     checkpointer=checkpointer,
#     response_format=ResponseFormat
# )

@tool
def chat_file(question: str):
    """ Process user inquires about files uploaded.
    """
    print(f"chat_file: {question}")
    runtime = get_runtime(Context)
    print(runtime.context.files)
    fc_tool = FileChatTool(runtime.context.uid, runtime.context.chat_session.id)
    answer = fc_tool.process_chat_with_file(question, runtime.context.files)
    return AIMessage(content=answer)

def get_files(messages: List[Message], chat_session: ChatSession = None):
    last_message = messages[-1]
    if len(last_message.files_id) > 0:
        file_ids = last_message.files_id
    elif chat_session:
        file_ids = chat_session.file_ids
    else:
        file_ids = None

    return file_ids

class StateMiddleware(AgentMiddleware[BaseAgentState]):
    state_schema = BaseAgentState

PROMPT_BASE = """
<assistant_role>
You are a helpful assistant of wearable AI device named Omi.
</assistant_role>

<tools>
- You can call tools to gather context when needed:
  - get_memories: fetch personalized user facts and knowledge.
  - get_conversations: fetch prior conversations relevant to the question.
  - get_actions: fetch the user's action items when it helps answer.
</tools>
{CHAT_FILES}

<instructions>
- You MUST answer the question directly, concisely, and with high quality.
- Refine the user's question using the last previous messages, but DO NOT use prior AI assistant messages as references/facts.
- Prefer the user's memories and conversations when relevant; if they are empty or insufficient, still answer with existing general knowledge.
- NEVER write phrases like "based on the available memories".
- Time context: {TIME_CONTEXT}
{PERSONA_PROMPT}
{CITATIONS_PROMPT}
</instructions>
{PERSONA_INSTRUCTIONS}
{CITATIONS_INSTRUCTIONS}

<reports_instructions>
- If the user requests a report or summary of a period, structure the answer with:
  - Goals and Achievements
  - Mood Tracker
  - Gratitude Log
  - Lessons Learned
</reports_instructions>
"""
# Add found memories if get_memories was called.

def create_graph(
        uid: str,
        messages: List[Message],
        app: Optional[App] = None,
        cited: Optional[bool] = False,
        callback_data: dict = {},
        chat_session: Optional[ChatSession] = None,
        files: Optional[List[str]] = None,
        tz: Optional[str] = "UTC",
):
    tools = [
        get_memories,
        get_conversations,
        get_actions,
        # get_files,
        # get_omi_documentation,  TODO: Current doc must be formatted other way
    ]

    if files:
        tools.append(chat_file)
        prompt_chat_files = "Use chat_file tool if user asked about file uploaded.\n"
    else:
        prompt_chat_files = ""

    checkpointer = MemorySaver()

    # Dynamic prompt sections
    citations_block = """
<citation_instructions>
- You MUST cite the most relevant memories or conversations that support your answer.
- Cite using [index] at the end of sentences, e.g., "You discussed optimizing firmware yesterday[1][2]".
- NO SPACE between the last word and the citation.
- Avoid citing irrelevant items.
</citation_instructions>
""" if cited else ""

    time_context = f"Question's timezone: {tz}. Current date time in UTC: {datetime.now().strftime('%Y-%m-%d %H:%M, %a')}"

    model = llm_mini_stream

    if app and app.is_a_persona():
        if not os.getenv('LOCAL_DEVELOPMENT'):
            if app.is_influencer:
                model = llm_persona_medium_stream
            else:
                model = llm_persona_mini_stream
        system_prompt = PROMPT_BASE.format(
            CHAT_FILES=prompt_chat_files,
            CITATIONS_PROMPT="""
- You MUST cite the most relevant memories and conversations if you used them in your answer. Expand it with <citation_instructions>.
""" if citations_block else '',
            CITATIONS_INSTRUCTIONS=citations_block,
            TIME_CONTEXT=time_context,
            PERSONA_PROMPT="""
- Regard the <plugin_instructions>
""",
            PERSONA_INSTRUCTIONS=f"""
<plugin_instructions>
{app.persona_prompt}
</plugin_instructions>
""")
    else:
        system_prompt = PROMPT_BASE.format(
            CHAT_FILES=prompt_chat_files,
            CITATIONS_PROMPT="""
- Regard the <citations>
""" if citations_block else '',
            CITATIONS_INSTRUCTIONS=citations_block,
            TIME_CONTEXT=time_context,
            PERSONA_PROMPT='',
            PERSONA_INSTRUCTIONS=''
        )

    graph = create_agent(
        model,
        tools,
        system_prompt=system_prompt,
        middleware=[StateMiddleware()],
        checkpointer=checkpointer,
        # response_format=ResponseFormat
    )

    return graph


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

    files = get_files(messages, chat_session)

    graph = create_graph(uid, messages, app, cited, callback_data, chat_session, files, tz)

    async for event in graph.astream(
            {
                # uid and tz: Sent via Context
                "cited": cited,
                "messages": Message.get_messages_as_dict(messages),
                # "app": app,
            },
            context=Context(uid=uid, tz=tz, chat_session=chat_session, files=files),
            stream_mode=["messages", "custom", "updates"],
            config={"configurable": {"thread_id": str(uuid.uuid4())}},
            subgraphs=True,
    ):
        ns, stream_mode, payload = event
        # print(ns, stream_mode, payload)
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
            elif isinstance(chunk, ToolMessage):
                chunk: ToolMessage
                # if chunk.name in ['get_memories', 'get_conversations']:
                #     callback_data['memories_found'] = json.loads(chunk.content)
            else:
                # Pass other chunks like ToolMessage
                pass

        elif stream_mode == "updates":
            payload: dict
            if 'tools' in payload:
                if not callback_data.get('memories_found'):
                    callback_data['memories_found'] = []
                if payload['tools'].get('conversations'):
                    callback_data['memories_found'] += payload['tools']['conversations']
                if payload['tools'].get('memories'):
                    callback_data['memories_found'] += payload['tools']['memories']

            for k in ['model', 'agent']:
                if k in payload:
                    last_message: AIMessage = payload[k]['messages'][0]
                    if last_message.response_metadata['finish_reason'] == 'stop':
                        callback_data['answer'] = last_message.content
                        # callback_data['answer'] = payload[k]['structured_response'].answer

        elif stream_mode == "custom":
            # Forward custom events as is
            yield f"data: {payload}"

    yield None
    return
