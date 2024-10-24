import datetime
import os
import time
from typing import List, Optional

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END
from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict, Literal

from database.vector_db import query_vectors_by_metadata
import database.memories as memories_db
from models.chat import Message, MessageSender, MessageType
from models.memory import Memory
from models.plugin import Plugin
from utils.llm import requires_context, answer_simple_message, retrieve_context_dates, qa_rag

model = ChatOpenAI(model='gpt-4o-mini')


class StructuredFilters(TypedDict):
    topics_discussed: List[str]
    people_mentioned: List[str]
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


# TODO: include a question extractor? node?


def retrieve_topics_filters(state: GraphState):
    print('retrieve_topics_filters')
    # retrieve all available entities, names, topics, etc, and ask it to filter based on the question.
    return {'filters': {'topics_discussed': []}}


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
        people_mentioned=state.get('filters', {}).get('people_mentioned', []),
        topics_discussed=state.get('filters', {}).get('topics_discussed', []),
        entities=state.get('filters', {}).get('entities', []),
        dates_mentioned=state.get('filters', {}).get('dates', []),
    )
    memories = memories_db.get_memories_by_id(uid, memories_id)
    # TODO: maybe didnt find anything, tries RAG, or goes to simple conversation?
    return {'memories_found': memories}


def qa_handler(state: GraphState):
    messages = state.get('messages', [])
    uid = state.get('uid')
    memories = state.get('memories_found', [])
    # TODO: use memories transcript instead
    response: str = qa_rag(uid, Memory.memories_to_string(memories), messages, state.get('plugin_selected'))
    return {'answer': response}


workflow = StateGraph(GraphState)  # custom state?

# workflow.add_edge(START, "determine_conversation_type")
# workflow.add_node('determine_conversation_type', determine_conversation_type)

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

if __name__ == '__main__':
    # graph.get_graph().draw_png('workflow.png')
    uid = 'TtCJi59JTVXHmyUC6vUQ1d9U6cK2'
    # messages = [Message(**msg) for msg in chat_db.get_messages(uid, limit=10)]
    # messages = filter_messages(messages, None)
    messages = [Message(
        id='0',
        text='What have I done this month?',
        created_at=datetime.datetime.now(),
        sender=MessageSender.human,
        type=MessageType.text)
    ]
    start_time = time.time()
    result = graph.invoke({'uid': uid, 'messages': messages}, {"configurable": {"thread_id": "foo"}})
    print('result:', result.get('answer'))
    print('time:', time.time() - start_time)
    # query_vectors_by_metadata(
    #     uid,
    #     [datetime.datetime(2024, 10, 1), datetime.datetime(2024, 10, 10)],
    #     # [],
    #     [], [], [], []
    # )
