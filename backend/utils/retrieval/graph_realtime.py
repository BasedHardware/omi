import datetime
import os
import uuid
from typing import List, Optional, Tuple

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END
from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict

from models.transcript_segment import TranscriptSegment
from utils.other.endpoints import timeit

# os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

import database.memories as memories_db
from database.redis_db import get_filter_category_items
from database.vector_db import query_vectors_by_metadata
from models.chat import Message
from models.memory import Memory
from utils.llm import select_structured_filters, generate_embedding, extract_question_from_transcript, \
    provide_advice_message

model = ChatOpenAI(model='gpt-4o-mini')


class StructuredFilters(TypedDict):
    topics: List[str]
    people: List[str]
    entities: List[str]
    dates: List[datetime.date]


class GraphState(TypedDict):
    uid: str
    segments: List[TranscriptSegment]
    parsed_question: Optional[str]

    filters: Optional[StructuredFilters]

    memories_found: Optional[List[Memory]]

    answer: Optional[str]


def extract_question(state: GraphState):
    question = extract_question_from_transcript(state.get('uid'), state.get('segments', []))
    print('context_dependent_conversation parsed question:', question)
    return {'parsed_question': question}


def retrieve_topics_of_interest(state: GraphState):
    print('retrieve_topics_of_interest')
    # TODO: use a different extractor without question but the conversation input?
    filters = {
        'people': get_filter_category_items(state.get('uid'), 'people'),
        'topics': get_filter_category_items(state.get('uid'), 'topics'),
        'entities': get_filter_category_items(state.get('uid'), 'entities'),
    }
    result = select_structured_filters(state.get('parsed_question', ''), filters)
    return {'filters': {
        'topics': result.get('topics', []),
        'people': result.get('people', []),
        'entities': result.get('entities', []),
    }}


def query_vectors(state: GraphState):
    print('query_vectors')
    uid = state.get('uid')
    vector = generate_embedding(state.get('parsed_question', '')) if state.get('parsed_question') else [0] * 3072
    print('query_vectors vector:', vector[:5])
    memories_id = query_vectors_by_metadata(
        uid,
        vector,
        dates_filter=[],
        people=state.get('filters', {}).get('people', []),
        topics=state.get('filters', {}).get('topics', []),
        entities=state.get('filters', {}).get('entities', []),
        dates=state.get('filters', {}).get('dates', []),
    )
    memories = memories_db.get_memories_by_id(uid, memories_id)
    return {'memories_found': memories}


def provide_answer(state: GraphState):
    response: str = provide_advice_message(
        state.get('uid'),
        state.get('segments'),
        Memory.memories_to_string(state.get('memories_found', []), True),
    )
    return {'answer': response}


workflow = StateGraph(GraphState)

workflow.add_edge(START, 'extract_question')
workflow.add_node("extract_question", extract_question)

workflow.add_edge('extract_question', 'retrieve_topics_of_interest')
workflow.add_node("retrieve_topics_of_interest", retrieve_topics_of_interest)
workflow.add_edge('retrieve_topics_of_interest', 'query_vectors')

workflow.add_node('query_vectors', query_vectors)
workflow.add_edge('query_vectors', 'provide_answer')
workflow.add_node('provide_answer', provide_answer)
workflow.add_edge('provide_answer', END)

checkpointer = MemorySaver()
graph = workflow.compile(checkpointer=checkpointer)


@timeit
def execute_graph_realtime(
        uid: str, segments: List[TranscriptSegment], use_full_transcript: bool = False
) -> Tuple[str, List[Memory]]:
    segments = segments if len(segments) < 10 or use_full_transcript else segments[-10:]
    result = graph.invoke({'uid': uid, 'segments': segments}, {"configurable": {"thread_id": str(uuid.uuid4())}})
    return result.get('answer'), result.get('memories_found', [])


def _pretty_print_conversation(messages: List[Message]):
    for msg in messages:
        print(f'{msg.sender}: {msg.text}')


if __name__ == '__main__':
    # uid = 'ccQJWj5mwhSY1dwjS1FPFBfKIXe2'
    # def _send_message(text: str, sender: str = 'human'):
    #     message = Message(
    #         id=str(uuid.uuid4()), text=text, created_at=datetime.datetime.now(datetime.timezone.utc), sender=sender,
    #         type='text'
    #     )
    #     chat_db.add_message(uid, message.dict())

    graph.get_graph().draw_png('workflow.png')
    segments = []
    result = execute_graph_realtime('TtCJi59JTVXHmyUC6vUQ1d9U6cK2', [TranscriptSegment(**s) for s in segments])
    print('result:', result[0])
