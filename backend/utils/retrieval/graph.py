import datetime
import uuid
import asyncio
from typing import List, Optional, Tuple, AsyncGenerator

from langchain.callbacks.base import BaseCallbackHandler
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END
from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict, Literal
# import os
# os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
import database.memories as memories_db
from database.redis_db import get_filter_category_items
from database.vector_db import query_vectors_by_metadata
import database.notifications as notification_db
from models.chat import ChatSession, Message
from models.memory import Memory
from models.plugin import Plugin
from utils.llm import (
    answer_omi_question,
    answer_omi_question_stream,
    requires_context,
    answer_simple_message,
    answer_simple_message_stream,
    retrieve_context_dates,
    retrieve_context_dates_by_question,
    qa_rag,
    qa_rag_stream,
    retrieve_is_an_omi_question,
    retrieve_is_file_question,
    select_structured_filters,
    extract_question_from_conversation,
    generate_embedding,
)
from utils.other.chat_file import FileChatTool
from utils.other.endpoints import timeit
from utils.plugins import get_github_docs_content

model = ChatOpenAI(model="gpt-4o-mini")


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


class GraphState(TypedDict):
    uid: str
    messages: List[Message]
    plugin_selected: Optional[Plugin]
    tz: str
    cited: Optional[bool] = False

    streaming: Optional[bool] = False
    callback: Optional[AsyncStreamingCallback] = None

    filters: Optional[StructuredFilters]
    date_filters: Optional[DateRangeFilters]

    memories_found: Optional[List[Memory]]

    parsed_question: Optional[str]
    answer: Optional[str]
    ask_for_nps: Optional[bool]

    chat_session: Optional[ChatSession]


def determine_conversation(state: GraphState):
    question = extract_question_from_conversation(state.get("messages", []))
    print("determine_conversation parsed question:", question)

    # # stream
    # if state.get('streaming', False):
    #     state['callback'].put_thought_nowait(question)

    return {"parsed_question": question}


def determine_conversation_type(
        state: GraphState,
) -> Literal["no_context_conversation", "context_dependent_conversation", "omi_question", "file_chat_question"]:
    # chat with files by attachments on the last message
    messages = state.get("messages", [])
    if len(messages) > 0 and len(messages[-1].files_id) > 0:
        return "file_chat_question"

    # no context
    question = state.get("parsed_question", "")
    if not question or len(question) == 0:
        return "no_context_conversation"

    # determine the follow up question is chatting with files or not
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

    # streaming
    streaming = state.get("streaming")
    if streaming:
        # state['callback'].put_thought_nowait("Reasoning")
        answer: str = answer_simple_message_stream(
            state.get("uid"), state.get("messages"),
            state.get("plugin_selected"),
            callbacks=[state.get('callback')]
        )
        return {"answer": answer, "ask_for_nps": False}

    # no streaming
    answer: str = answer_simple_message(
        state.get("uid"), state.get("messages"),
        state.get("plugin_selected"),
    )
    return {"answer": answer, "ask_for_nps": False}

def omi_question(state: GraphState):
    print("no_context_omi_question node")

    context: dict = get_github_docs_content()
    context_str = 'Documentation:\n\n'.join([f'{k}:\n {v}' for k, v in context.items()])

    # streaming
    streaming = state.get("streaming")
    if streaming:
        # state['callback'].put_thought_nowait("Reasoning")
        answer: str = answer_omi_question_stream(
            state.get("messages", []), context_str,
            callbacks=[state.get('callback')]
        )
        return {'answer': answer, 'ask_for_nps': True}

    # no streaming
    answer = answer_omi_question(state.get("messages", []), context_str)
    return {'answer': answer, 'ask_for_nps': True}


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
        "people": get_filter_category_items(state.get("uid"), "people"),
        "topics": get_filter_category_items(state.get("uid"), "topics"),
        "entities": get_filter_category_items(state.get("uid"), "entities"),
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
    vector = ([1] * 3072)
    print("query_vectors vector:", vector[:5])

    # TODO: enable it when the in-accurated topic filter get fixed
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
    memories = memories_db.get_memories_by_id(uid, memories_id)

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

    # streaming
    streaming = state.get("streaming")
    if streaming:
        # state['callback'].put_thought_nowait("Reasoning")
        memories = state.get("memories_found", [])
        response: str = qa_rag_stream(
            uid,
            state.get("parsed_question"),
            Memory.memories_to_string(memories, False),
            state.get("plugin_selected"),
            cited=state.get("cited"),
            messages=state.get("messages"),
            tz=state.get("tz"),
            callbacks=[state.get('callback')]
        )
        return {"answer": response, "ask_for_nps": True}

    # no streaming
    memories = state.get("memories_found", [])
    response: str = qa_rag(
        uid,
        state.get("parsed_question"),
        Memory.memories_to_string(memories, False),
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

    streaming = state.get("streaming")
    if streaming:
        answer = fc_tool.process_chat_with_file_stream(uid, question, file_ids, callback=state.get('callback'))
        return {'answer': answer, 'ask_for_nps': True}

    answer = fc_tool.process_chat_with_file(uid, question,file_ids)
    return {'answer': answer, 'ask_for_nps': True}


workflow = StateGraph(GraphState)


workflow.add_edge(START, "determine_conversation")

workflow.add_node("determine_conversation", determine_conversation)

workflow.add_conditional_edges("determine_conversation", determine_conversation_type)

workflow.add_node("no_context_conversation", no_context_conversation)
workflow.add_node("omi_question", omi_question)
workflow.add_node("context_dependent_conversation", context_dependent_conversation)
workflow.add_node("file_chat_question", file_chat_question)

workflow.add_edge("no_context_conversation", END)
workflow.add_edge("omi_question", END)
workflow.add_edge("file_chat_question", END)
workflow.add_edge("context_dependent_conversation", "retrieve_topics_filters")
workflow.add_edge("context_dependent_conversation", "retrieve_date_filters")

workflow.add_node("retrieve_topics_filters", retrieve_topics_filters)
workflow.add_node("retrieve_date_filters", retrieve_date_filters)

workflow.add_edge("retrieve_topics_filters", "query_vectors")
workflow.add_edge("retrieve_date_filters", "query_vectors")

workflow.add_node("query_vectors", query_vectors)

workflow.add_edge("query_vectors", "qa_handler")

workflow.add_node("qa_handler", qa_handler)

workflow.add_edge("qa_handler", END)

checkpointer = MemorySaver()
graph = workflow.compile(checkpointer=checkpointer)

graph_stream = workflow.compile()

@timeit
def execute_graph_chat(
        uid: str, messages: List[Message], plugin: Optional[Plugin] = None, cited: Optional[bool] = False
) -> Tuple[str, bool, List[Memory]]:
    print('execute_graph_chat plugin    :', plugin.id if plugin else '<none>')
    tz = notification_db.get_user_time_zone(uid)
    result = graph.invoke(
        {"uid": uid, "tz": tz, "cited": cited, "messages": messages, "plugin_selected": plugin},
        {"configurable": {"thread_id": str(uuid.uuid4())}},
    )
    return result.get("answer"), result.get('ask_for_nps', False), result.get("memories_found", [])

async def execute_graph_chat_stream(
    uid: str, messages: List[Message], plugin: Optional[Plugin] = None, cited: Optional[bool] = False, callback_data: dict = {}, chat_session: Optional[ChatSession] = None
) -> AsyncGenerator[str, None]:
    print('execute_graph_chat_stream plugin: ', plugin.id if plugin else '<none>')
    tz = notification_db.get_user_time_zone(uid)
    callback = AsyncStreamingCallback()

    task = asyncio.create_task(graph_stream.ainvoke(
        {"uid": uid, "tz": tz, "cited": cited, "messages": messages, "plugin_selected": plugin,
         "streaming": True, "callback": callback, "chat_session": chat_session},
        {"configurable": {"thread_id": str(uuid.uuid4())}},
    ))

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
    callback_data['answer'] = result.get("answer")
    callback_data['memories_found'] = result.get("memories_found", [])
    callback_data['ask_for_nps'] = result.get('ask_for_nps', False)

    yield None
    return
