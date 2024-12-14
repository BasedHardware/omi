import datetime
import uuid
from typing import List, Optional, Tuple

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
from models.chat import Message
from models.memory import Memory
from models.plugin import Plugin
from utils.llm import (
    answer_omi_question,
    requires_context,
    answer_simple_message,
    retrieve_context_dates,
    retrieve_context_dates_by_question,
    qa_rag,
    retrieve_is_an_omi_question,
    select_structured_filters,
    extract_question_from_conversation,
    generate_embedding,
)
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


class GraphState(TypedDict):
    uid: str
    messages: List[Message]
    plugin_selected: Optional[Plugin]
    tz: str

    filters: Optional[StructuredFilters]
    date_filters: Optional[DateRangeFilters]

    memories_found: Optional[List[Memory]]

    parsed_question: Optional[str]
    answer: Optional[str]
    ask_for_nps: Optional[bool]


def determine_conversation_type(
        s: GraphState,
) -> Literal["no_context_conversation", "context_dependent_conversation", "omi_question"]:
    is_omi_question = retrieve_is_an_omi_question(s.get("messages", []))
    # TODO: after asked many questions this is causing issues.
    # TODO: an option to be considered, single prompt outputs response needed type (omi,no context, context, suggestion)
    if is_omi_question:
        return "omi_question"

    requires = requires_context(s.get("messages", []))

    if requires:
        return "context_dependent_conversation"
    return "no_context_conversation"


def no_context_conversation(state: GraphState):
    print("no_context_conversation node")
    return {"answer": answer_simple_message(state.get("uid"), state.get("messages")), "ask_for_nps": False}


def omi_question(state: GraphState):
    print("no_context_omi_question node")
    context: dict = get_github_docs_content()
    context_str = 'Documentation:\n\n'.join([f'{k}:\n {v}' for k, v in context.items()])
    answer = answer_omi_question(state.get("messages", []), context_str)
    return {'answer': answer, 'ask_for_nps': True}


def context_dependent_conversation(state: GraphState):
    question = extract_question_from_conversation(state.get("messages", []))
    print("context_dependent_conversation parsed question:", question)
    return {"parsed_question": question}


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
    if not dates_range or len(dates_range) == 0:
        return {"date_filters": {}}
    if len(dates_range) == 1:
        return {"date_filters": {"start": dates_range[0], "end": dates_range[0]}}
    # >=2
    return {"date_filters": {"start": dates_range[0], "end": dates_range[1]}}


def query_vectors(state: GraphState):
    print("query_vectors")
    date_filters = state.get("date_filters")
    uid = state.get("uid")
    vector = (
        generate_embedding(state.get("parsed_question", ""))
        if state.get("parsed_question")
        else [0] * 3072
    )
    print("query_vectors vector:", vector[:5])
    memories_id = query_vectors_by_metadata(
        uid,
        vector,
        dates_filter=[date_filters.get("start"), date_filters.get("end")],
        people=state.get("filters", {}).get("people", []),
        topics=state.get("filters", {}).get("topics", []),
        entities=state.get("filters", {}).get("entities", []),
        dates=state.get("filters", {}).get("dates", []),
    )
    memories = memories_db.get_memories_by_id(uid, memories_id)
    return {"memories_found": memories}


def qa_handler(state: GraphState):
    uid = state.get("uid")
    memories = state.get("memories_found", [])
    response: str = qa_rag(
        uid,
        state.get("parsed_question"),
        Memory.memories_to_string(memories, True),
        state.get("plugin_selected"),
    )
    return {"answer": response, "ask_for_nps": True}


workflow = StateGraph(GraphState)

workflow.add_conditional_edges(
    START,
    determine_conversation_type,
)

workflow.add_node("no_context_conversation", no_context_conversation)
workflow.add_node("omi_question", omi_question)
workflow.add_node("context_dependent_conversation", context_dependent_conversation)

workflow.add_edge("no_context_conversation", END)
workflow.add_edge("omi_question", END)
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


@timeit
def execute_graph_chat(
        uid: str, messages: List[Message], plugin: Optional[Plugin] = None
) -> Tuple[str, bool, List[Memory]]:
    print('execute_graph_chat plugin    :', plugin)
    tz = notification_db.get_user_time_zone(uid)
    result = graph.invoke(
        {"uid": uid, "tz": tz, "messages": messages, "plugin_selected": plugin},
        {"configurable": {"thread_id": str(uuid.uuid4())}},
    )
    return result.get("answer"), result.get('ask_for_nps', False), result.get("memories_found", [])


def _pretty_print_conversation(messages: List[Message]):
    for msg in messages:
        print(f"{msg.sender}: {msg.text}")


if __name__ == "__main__":
    # graph.get_graph().draw_png("workflow.png")
    uid = "viUv7GtdoHXbK1UBCDlPuTDuPgJ2"
    # def _send_message(text: str, sender: str = 'human'):
    #     message = Message(
    #         id=str(uuid.uuid4()), text=text, created_at=datetime.datetime.now(datetime.timezone.utc), sender=sender,
    #         type='text'
    #     )
    #     chat_db.add_message(uid, message.dict())
    messages = [
        Message(
            id=str(uuid.uuid4()),
            text="Should I give equity to Ansh?",
            # text="I need to launch a new consumer hardware wearable and need to make a video for it. Recommend best books about video production for the launch",
            # text="Should I build the features myself or hire people?",
            # text="So i just woke up and i'm thinking i want to wake Up earlier because i woke up today at like 2 p.m. it's crazy. but i need to have something in the morning, some commitment in the morning, like 10 a.m. that i would wake up for so that i go to sleep later as well. what do you think that commitment can and should be?",
            created_at=datetime.datetime.now(datetime.timezone.utc),
            sender="human",
            type="text",
        )
    ]
    result = execute_graph_chat(uid, messages)
    print("result:", print(result[0]))
    # messages = list(reversed([Message(**msg) for msg in chat_db.get_messages(uid, limit=10)]))
    # _pretty_print_conversation(messages)
    # # print(messages[-1].text)
    # # _send_message('Check again, Im pretty sure I had some')
    # # raise Exception()
    # start_time = time.time()
    # result = graph.invoke({'uid': uid, 'messages': messages}, {"configurable": {"thread_id": "foo"}})
    # print('result:', result.get('answer'))
    # print('time:', time.time() - start_time)
