from typing import Literal

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END
from langgraph.graph import START, StateGraph, MessagesState

model = ChatOpenAI(model='gpt-4o-mini')


def determine_conversation_type(s: MessagesState) -> Literal["no_context_conversation", "context_dependent_conversation"]:
    # call requires context
    # if requires context, spawn 2 parallel graphs edges?
    return 'no_context_conversation'


def no_context_conversation(state: MessagesState):
    # continue the conversation
    return END


def context_dependent_conversation(state: MessagesState):
    pass


# TODO: include a question extractor? node?


def retrieve_topics_filters(state: MessagesState):
    # retrieve all available entities, names, topics, etc, and ask it to filter based on the question.
    return 'query_vectors'


def retrieve_date_filters(state: MessagesState):
    # extract dates filters, and send them to qa_handler node
    return 'query_vectors'


def query_vectors(state: MessagesState):
    # receives both filters, and finds vectors + rerank them
    # TODO: maybe didnt find anything, tries RAG, or goes to simple conversation?
    pass


def qa_handler(state: MessagesState):
    # takes vectors found, retrieves memories, and does QA on them
    return END


workflow = StateGraph(MessagesState)  # custom state?




workflow.add_edge(START, "determine_conversation_type")
workflow.add_node('determine_conversation_type', determine_conversation_type)

workflow.add_conditional_edges(
    "determine_conversation_type",
    determine_conversation_type,
)

workflow.add_node("no_context_conversation", no_context_conversation)
workflow.add_node("context_dependent_conversation", context_dependent_conversation)

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
    graph.get_graph().draw_png('workflow.png')
