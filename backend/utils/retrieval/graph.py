import datetime
import os
import time
import uuid
from typing import List, Optional, Tuple

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END
from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict, Literal

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

import database.memories as memories_db
from database.redis_db import get_filter_category_items
from database.vector_db import query_vectors_by_metadata
from models.chat import Message, MessageSender, MessageType
from models.memory import Memory
from models.plugin import Plugin
from utils.llm import requires_context, answer_simple_message, retrieve_context_dates, qa_rag, select_structured_filters

model = ChatOpenAI(model='gpt-4o-mini')


class StructuredFilters(TypedDict):
    topics: List[str]
    people: List[str]
    entities: List[str]
    dates: List[datetime.date]


class DateRangeFilters(TypedDict):
    start: datetime.datetime
    end: datetime.datetime


class GraphState(TypedDict):
    uid: str
    messages: List[Message]
    plugin_selected: Optional[Plugin]

    filters: Optional[StructuredFilters]
    date_filters: Optional[DateRangeFilters]

    memories_found: Optional[List[Memory]]

    answer: Optional[str]


def determine_conversation_type(s: GraphState) -> Literal[
    "no_context_conversation", "context_dependent_conversation"]:
    requires = requires_context(s.get('messages', []))

    if requires:
        return 'context_dependent_conversation'
    return 'no_context_conversation'


def no_context_conversation(state: GraphState):
    print('no_context_conversation node')
    return {'answer': answer_simple_message(state.get('uid'), state.get('messages'))}


def context_dependent_conversation(state: GraphState):
    return {'uid': state.get('uid')}


# !! include a question extractor? node?


def retrieve_topics_filters(state: GraphState):
    print('retrieve_topics_filters')
    filters = {
        'people': get_filter_category_items(state.get('uid'), 'people'),
        'topics': get_filter_category_items(state.get('uid'), 'topics'),
        'entities': get_filter_category_items(state.get('uid'), 'entities'),
        # 'dates': get_filter_category_items(state.get('uid'), 'dates'),
    }
    result = select_structured_filters(state.get('messages', []), filters)
    return {'filters': {
        'topics': result.get('topics', []),
        'people': result.get('people', []),
        'entities': result.get('entities', []),
        # 'dates': result.get('dates', []),
    }}


def retrieve_date_filters(state: GraphState):
    dates_range = retrieve_context_dates(state.get('messages', []))
    if dates_range and len(dates_range) == 2:
        return {'date_filters': {'start': dates_range[0], 'end': dates_range[1]}}
    return {'date_filters': {}}


def query_vectors(state: GraphState):
    print('query_vectors')
    date_filters = state.get('date_filters')
    uid = state.get('uid')
    memories_id = query_vectors_by_metadata(
        uid,
        dates_filter=[date_filters.get('start'), date_filters.get('end')],
        people=state.get('filters', {}).get('people', []),
        topics=state.get('filters', {}).get('topics', []),
        entities=state.get('filters', {}).get('entities', []),
        dates=state.get('filters', {}).get('dates', []),
    )
    memories = memories_db.get_memories_by_id(uid, memories_id)
    # TODO: maybe didnt find anything, tries RAG, or goes to simple conversation?
    return {'memories_found': memories}


def qa_handler(state: GraphState):
    messages = state.get('messages', [])
    uid = state.get('uid')
    memories = state.get('memories_found', [])
    response: str = qa_rag(uid, Memory.memories_to_string(memories, True), messages, state.get('plugin_selected'))
    return {'answer': response}


workflow = StateGraph(GraphState)

workflow.add_conditional_edges(
    START,
    determine_conversation_type,
)

workflow.add_node("no_context_conversation", no_context_conversation)
workflow.add_node("context_dependent_conversation", context_dependent_conversation)

workflow.add_edge("no_context_conversation", END)

workflow.add_edge("context_dependent_conversation", "retrieve_topics_filters")
workflow.add_edge("context_dependent_conversation", "retrieve_date_filters")

workflow.add_node("retrieve_topics_filters", retrieve_topics_filters)
workflow.add_node("retrieve_date_filters", retrieve_date_filters)

workflow.add_edge('retrieve_topics_filters', 'query_vectors')
workflow.add_edge('retrieve_date_filters', 'query_vectors')

workflow.add_node('query_vectors', query_vectors)

workflow.add_edge('query_vectors', 'qa_handler')

workflow.add_node('qa_handler', qa_handler)

workflow.add_edge('qa_handler', END)

checkpointer = MemorySaver()
graph = workflow.compile(checkpointer=checkpointer)


def execute_graph_chat(uid: str, messages: List[Message]) -> Tuple[str, List[Memory]]:
    start_time = time.time()
    result = graph.invoke({'uid': uid, 'messages': messages}, {"configurable": {"thread_id": str(uuid.uuid4())}})
    print('graph chat result:', result.get('answer'), 'took:', time.time() - start_time)
    return result, result.get('memories_found')


if __name__ == '__main__':
    # graph.get_graph().draw_png('workflow.png')
    uid = 'TtCJi59JTVXHmyUC6vUQ1d9U6cK2'
    messages = []
    start_time = time.time()
    result = graph.invoke({'uid': uid, 'messages': messages}, {"configurable": {"thread_id": "foo"}})
    print('result:', result.get('answer'))
    print('time:', time.time() - start_time)
