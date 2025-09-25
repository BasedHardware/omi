import asyncio
from typing import List, Optional, AsyncGenerator

from langchain.callbacks.base import BaseCallbackHandler
from langgraph.constants import END
from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict

from utils.llm.chat_convos import get_conversation_context_for_question
from models.chat_convo import ConversationChatMessage
from utils.llm.chat_convos import (
    extract_question_from_conversation_messages,
    question_requires_conversation_context,
    answer_simple_conversation_message_stream,
    answer_conversation_question_stream,
)
from utils.other.endpoints import timeit


class AsyncStreamingCallback(BaseCallbackHandler):
    """Callback handler for streaming responses"""

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


class ConversationGraphState(TypedDict):
    """State for conversation chat graph"""

    uid: str
    conversation_id: str
    messages: List[ConversationChatMessage]

    # Processing state
    streaming: Optional[bool] = False
    callback: Optional[AsyncStreamingCallback] = None

    # Extracted information
    parsed_question: Optional[str]
    requires_context: Optional[bool]

    # Context and response
    conversation_context: Optional[dict]
    answer: Optional[str]
    ask_for_nps: Optional[bool]


def determine_conversation_question(state: ConversationGraphState):
    """Extract the user's question from conversation messages"""
    print("determine_conversation_question")

    question = extract_question_from_conversation_messages(state.get("messages", []))
    print(f"Extracted question: {question}")

    return {"parsed_question": question}


def determine_context_requirement(state: ConversationGraphState):
    """Determine if the question requires conversation context"""
    print("determine_context_requirement")

    question = state.get("parsed_question", "")
    requires_context = question_requires_conversation_context(question)

    print(f"Requires context: {requires_context}")
    return {"requires_context": requires_context}


def simple_conversation_response(state: ConversationGraphState):
    """Handle simple responses that don't need conversation context"""
    print("simple_conversation_response")

    uid = state.get("uid")
    conversation_id = state.get("conversation_id")
    messages = state.get("messages", [])
    streaming = state.get("streaming", False)

    if streaming:
        answer = answer_simple_conversation_message_stream(
            uid, messages, conversation_id, callbacks=[state.get('callback')]
        )
        return {"answer": answer, "ask_for_nps": False}

    # TODO: Implement non-streaming version if needed
    return {"answer": "Sorry, non-streaming responses not yet implemented.", "ask_for_nps": False}


def retrieve_conversation_context(state: ConversationGraphState):
    """Retrieve context from the conversation"""
    print("retrieve_conversation_context")

    uid = state.get("uid")
    conversation_id = state.get("conversation_id")
    question = state.get("parsed_question", "")

    # Get conversation context
    context = get_conversation_context_for_question(uid, conversation_id, question)
    print(f"Retrieved context: {len(context.get('context_text', ''))} characters")

    return {"conversation_context": context}


def context_based_response(state: ConversationGraphState):
    """Generate response using conversation context"""
    print("context_based_response")

    uid = state.get("uid")
    conversation_id = state.get("conversation_id")
    question = state.get("parsed_question", "")
    messages = state.get("messages", [])
    context = state.get("conversation_context", {})
    streaming = state.get("streaming", False)

    context_text = context.get('context_text', '')
    conversation_title = context.get('conversation_title', 'Conversation')

    if streaming:
        answer = answer_conversation_question_stream(
            uid=uid,
            question=question,
            conversation_context=context_text,
            messages=messages,
            conversation_title=conversation_title,
            conversation_id=conversation_id,
            callbacks=[state.get('callback')],
        )
        return {
            "answer": answer,
            "ask_for_nps": True,
            "memories_found": context.get('memories_found', []),
            "action_items_found": context.get('action_items_found', []),
        }

    # TODO: Implement non-streaming version if needed
    return {"answer": "Sorry, non-streaming responses not yet implemented.", "ask_for_nps": False}


def route_conversation_type(state: ConversationGraphState) -> str:
    """Route conversation based on whether context is needed"""
    requires_context = state.get("requires_context", False)
    question = state.get("parsed_question", "")

    # If no question or doesn't require context, use simple response
    if not question.strip() or not requires_context:
        return "simple_response"

    return "context_response"


# Create the conversation chat workflow
workflow = StateGraph(ConversationGraphState)

# Add nodes
workflow.add_node("determine_question", determine_conversation_question)
workflow.add_node("determine_context", determine_context_requirement)
workflow.add_node("simple_response", simple_conversation_response)
workflow.add_node("retrieve_context", retrieve_conversation_context)
workflow.add_node("context_response", context_based_response)

# Add edges
workflow.add_edge(START, "determine_question")
workflow.add_edge("determine_question", "determine_context")
workflow.add_conditional_edges(
    "determine_context",
    route_conversation_type,
    {"simple_response": "simple_response", "context_response": "retrieve_context"},
)
workflow.add_edge("simple_response", END)
workflow.add_edge("retrieve_context", "context_response")
workflow.add_edge("context_response", END)

# Compile the graph
conversation_graph = workflow.compile()


@timeit
def execute_conversation_chat(
    uid: str, conversation_id: str, messages: List[ConversationChatMessage]
) -> tuple[str, bool, dict]:
    """Execute conversation chat (non-streaming)"""
    print(f'execute_conversation_chat for conversation: {conversation_id}')

    result = conversation_graph.invoke(
        {"uid": uid, "conversation_id": conversation_id, "messages": messages, "streaming": False}
    )

    return (result.get("answer", ""), result.get('ask_for_nps', False), result.get("conversation_context", {}))


async def execute_conversation_chat_stream(
    uid: str, conversation_id: str, messages: List[ConversationChatMessage], callback_data: dict = {}
) -> AsyncGenerator[str, None]:
    """Execute conversation chat with streaming"""
    print(f'execute_conversation_chat_stream for conversation: {conversation_id}')

    callback = AsyncStreamingCallback()

    task = asyncio.create_task(
        conversation_graph.ainvoke(
            {
                "uid": uid,
                "conversation_id": conversation_id,
                "messages": messages,
                "streaming": True,
                "callback": callback,
            }
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

    # Pass results back to caller
    callback_data['answer'] = result.get("answer")
    callback_data['memories_found'] = result.get("memories_found", [])
    callback_data['action_items_found'] = result.get("action_items_found", [])
    callback_data['ask_for_nps'] = result.get('ask_for_nps', False)

    yield None
    return


# TODO: Add additional conversation-specific nodes as needed
# Examples of nodes you might want to add:
#
# def analyze_conversation_participants(state: ConversationGraphState):
#     """Analyze who participated in the conversation"""
#     pass
#
# def extract_action_items(state: ConversationGraphState):
#     """Extract action items from conversation"""
#     pass
#
# def summarize_conversation(state: ConversationGraphState):
#     """Generate a summary of the conversation"""
#     pass
#
# def identify_key_topics(state: ConversationGraphState):
#     """Identify main topics discussed"""
#     pass
