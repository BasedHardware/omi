"""
Agentic chat system using LangGraph tools.

This module implements a tool-calling agent that autonomously decides which tools
to use to gather context and answer user questions. Unlike the previous graph-based
approach, this lets the LLM make decisions about what information it needs.
"""

import re
import uuid
import asyncio
from datetime import datetime, timezone
from typing import List, Optional, AsyncGenerator, Tuple

import database.notifications as notification_db

from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState

from models.app import App
from models.chat import Message, ChatSession
from models.conversation import Conversation
from utils.retrieval.tools import (
    get_conversations_tool,
    vector_search_conversations_tool,
    get_memories_tool,
    get_action_items_tool,
    create_action_item_tool,
    update_action_item_tool,
)
from utils.retrieval.safety import AgentSafetyGuard, SafetyGuardError
from utils.llm.clients import llm_agent, llm_agent_stream
from utils.llm.chat import _get_agentic_qa_prompt
from utils.other.endpoints import timeit


class AsyncStreamingCallback(BaseCallbackHandler):
    """Callback handler for streaming LLM responses with data and thought prefixes."""

    def __init__(self):
        self.queue = asyncio.Queue()

    async def put_data(self, text):
        """Add a data chunk to the queue."""
        await self.queue.put(f"data: {text}")

    async def put_thought(self, text):
        """Add a thought/status message to the queue."""
        await self.queue.put(f"think: {text}")

    def put_thought_nowait(self, text):
        """Add a thought/status message to the queue without waiting."""
        self.queue.put_nowait(f"think: {text}")

    def put_data_nowait(self, text):
        """Add a data chunk to the queue without waiting."""
        self.queue.put_nowait(f"data: {text}")

    async def end(self):
        """Signal the end of the stream."""
        await self.queue.put(None)

    def end_nowait(self):
        """Signal the end of the stream without waiting."""
        self.queue.put_nowait(None)

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        """Handle new tokens from the LLM."""
        await self.put_data(token)

    async def on_llm_end(self, response, **kwargs) -> None:
        """Handle LLM completion."""
        await self.end()

    async def on_llm_error(self, error: Exception, **kwargs) -> None:
        """Handle LLM errors."""
        print(f"Error on LLM: {error}")
        await self.end()


def _messages_to_langchain(messages: List[Message]) -> List:
    """Convert chat messages to LangChain message format."""
    lc_messages = []

    for msg in messages:
        if msg.sender == 'ai':
            lc_messages.append(AIMessage(content=msg.text))
        else:
            lc_messages.append(HumanMessage(content=msg.text))

    return lc_messages


@timeit
def execute_agentic_chat(
    uid: str,
    messages: List[Message],
    app: Optional[App] = None,
) -> Tuple[str, bool, List[Conversation]]:
    """
    Execute an agentic chat interaction (non-streaming).

    Args:
        uid: User ID
        messages: Chat message history
        app: Optional app/plugin

    Returns:
        Tuple of (answer, ask_for_nps, conversations_referenced)
    """
    # Build system prompt
    system_prompt = _get_agentic_qa_prompt(uid, app)

    # Get all tools
    tools = [
        get_conversations_tool,
        vector_search_conversations_tool,
        get_memories_tool,
        get_action_items_tool,
        create_action_item_tool,
        update_action_item_tool,
    ]

    # Convert messages to LangChain format and prepend system message
    lc_messages = [SystemMessage(content=system_prompt)]
    lc_messages.extend(_messages_to_langchain(messages))

    # Create agent with tools
    agent = create_react_agent(
        model=llm_agent,
        tools=tools,
    )

    # Run agent
    config = {
        "configurable": {
            "user_id": uid,
            "thread_id": str(uuid.uuid4()),
        }
    }

    result = agent.invoke(
        {"messages": lc_messages},
        config=config,
    )

    # Extract answer from result
    answer = result["messages"][-1].content if result.get("messages") else "I'm sorry, I couldn't generate a response."

    # Determine if we should ask for NPS
    # Ask for NPS if tools were used (meaning we accessed user data)
    ask_for_nps = len(result.get("messages", [])) > len(lc_messages) + 1

    # Extract any conversations that were referenced
    # For now, return empty list - in the future we could parse tool outputs
    conversations_referenced = []

    return answer, ask_for_nps, conversations_referenced


async def execute_agentic_chat_stream(
    uid: str,
    messages: List[Message],
    app: Optional[App] = None,
    callback_data: dict = None,
    chat_session: Optional[ChatSession] = None,
) -> AsyncGenerator[str, None]:
    """
    Execute an agentic chat interaction with streaming.

    Args:
        uid: User ID
        messages: Chat message history
        app: Optional app/plugin
        callback_data: Dict to store callback data (answer, memories, etc.)
        chat_session: Optional chat session for file context

    Yields:
        Formatted chunks with "data: " or "think: " prefixes
    """
    # Build system prompt
    system_prompt = _get_agentic_qa_prompt(uid, app)

    # Get all tools
    tools = [
        get_conversations_tool,
        vector_search_conversations_tool,
        get_memories_tool,
        get_action_items_tool,
        create_action_item_tool,
        update_action_item_tool,
    ]

    # Convert messages to LangChain format and prepend system message
    lc_messages = [SystemMessage(content=system_prompt)]
    lc_messages.extend(_messages_to_langchain(messages))

    # Create callback for streaming
    callback = AsyncStreamingCallback()

    # Create streaming agent with callback
    agent = create_react_agent(
        model=llm_agent_stream,
        tools=tools,
    )

    # Run agent with streaming
    # Add a list to collect conversations from tools for citation
    conversations_collected = []

    # Initialize safety guard
    safety_guard = AgentSafetyGuard(max_tool_calls=10, max_context_tokens=500000)

    config = {
        "configurable": {
            "user_id": uid,
            "thread_id": str(uuid.uuid4()),
            "conversations_collected": conversations_collected,
            "safety_guard": safety_guard,
        }
    }

    full_response = []
    tool_usage_count = 0

    # Start agent task
    task = asyncio.create_task(
        _run_agent_stream(
            agent,
            lc_messages,
            config,
            callback,
            full_response,
            callback_data,
        )
    )

    # Stream from callback queue
    try:
        while True:
            chunk = await callback.queue.get()
            if chunk is None:
                break

            # Track tool usage from think messages
            if chunk.startswith("think: Using "):
                tool_usage_count += 1

            yield chunk

        # Wait for task to complete
        await task

        # Store results in callback_data
        if callback_data is not None:
            callback_data['answer'] = ''.join(full_response)
            # Extract conversations collected by tools
            callback_data['memories_found'] = conversations_collected if conversations_collected else []
            callback_data['ask_for_nps'] = tool_usage_count > 0
            print(f"📚 Collected {len(callback_data['memories_found'])} conversations for citation")

    except asyncio.CancelledError:
        task.cancel()
        raise
    except Exception as e:
        print(f"❌ Error in execute_agentic_chat_stream: {e}")
        import traceback

        traceback.print_exc()
        if callback_data is not None:
            callback_data['error'] = str(e)

    yield None  # Signal completion


async def _run_agent_stream(
    agent,
    messages: List,
    config: dict,
    callback: AsyncStreamingCallback,
    full_response: List[str],
    callback_data: dict,
):
    """
    Internal function to run the agent and populate the callback queue.

    Args:
        agent: The LangGraph agent
        messages: Messages to send to agent
        config: Agent configuration
        callback: Callback to send chunks to
        full_response: List to accumulate response tokens
        callback_data: Dict to store metadata
    """
    safety_guard = config['configurable'].get('safety_guard')

    try:
        async for event in agent.astream_events(
            {"messages": messages},
            config=config,
            version="v2",
        ):
            kind = event.get("event")

            # Stream LLM tokens
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    token = chunk.content
                    full_response.append(token)
                    await callback.put_data(token)

            # Track tool usage and validate with safety guard
            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_input = event.get("data", {}).get("input", {})
                print(f"🔧 Tool started: {tool_name}")

                # Validate tool call with safety guard
                if safety_guard:
                    try:
                        safety_guard.validate_tool_call(tool_name, tool_input)

                        # Check if we should warn user about approaching limits
                        warning = safety_guard.should_warn_user()
                        if warning:
                            await callback.put_thought(warning)
                    except SafetyGuardError as e:
                        # Send friendly error message to user (no technical jargon)
                        error_msg = f"\n\n{str(e)}"
                        await callback.put_data(error_msg)
                        print(f"🛡️ Safety Guard blocked tool call: {e}")
                        # Signal completion and stop processing
                        await callback.end()
                        return

            elif kind == "on_tool_end":
                tool_name = event.get("name", "unknown")
                output = event.get("data", {}).get("output", "")
                print(f"✅ Tool ended: {tool_name}")

                # Check context size with safety guard
                if safety_guard and output:
                    try:
                        safety_guard.check_context_size(str(output))
                    except SafetyGuardError as e:
                        # Send friendly error message to user (no technical jargon)
                        error_msg = f"\n\n{str(e)}"
                        await callback.put_data(error_msg)
                        print(f"🛡️ Safety Guard blocked due to context size: {e}")
                        # Signal completion and stop processing
                        await callback.end()
                        return

            elif kind == "on_tool_error":
                tool_name = event.get("name", "unknown")
                error = event.get("data", {}).get("error", "")
                print(f"❌ Tool error: {tool_name}")
                print(f"   Error: {error}")

            elif kind == "on_chain_error":
                error = event.get("data", {}).get("error", "")
                print(f"❌ Chain error: {error}")

        # Log final stats
        if safety_guard:
            stats = safety_guard.get_stats()
            print(f"🛡️ Safety Guard final stats: {stats}")

        # Signal completion
        await callback.end()

    except SafetyGuardError as e:
        # Send friendly error message to user (no technical jargon)
        error_msg = f"\n\n{str(e)}"
        await callback.put_data(error_msg)
        print(f"🛡️ Safety Guard stopped execution: {e}")
        await callback.end()
    except Exception as e:
        print(f"❌ Error in _run_agent_stream: {e}")
        import traceback

        traceback.print_exc()
        await callback.end()
