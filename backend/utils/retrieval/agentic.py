"""
Agentic chat system using LangGraph tools.

This module implements a tool-calling agent that autonomously decides which tools
to use to gather context and answer user questions. Unlike the previous graph-based
approach, this lets the LLM make decisions about what information it needs.
"""

import re
import uuid
import asyncio
import contextvars
from datetime import datetime, timezone
from typing import List, Optional, AsyncGenerator, Any, Tuple

import database.notifications as notification_db

from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState

# Context variable to store config for tools
agent_config_context: contextvars.ContextVar[dict] = contextvars.ContextVar('agent_config', default=None)

from models.app import App
from models.chat import Message, ChatSession, PageContext
from models.conversation import Conversation
from utils.retrieval.tools import (
    get_conversations_tool,
    search_conversations_tool,
    get_memories_tool,
    get_action_items_tool,
    create_action_item_tool,
    update_action_item_tool,
    get_omi_product_info_tool,
    perplexity_web_search_tool,
    get_calendar_events_tool,
    create_calendar_event_tool,
    update_calendar_event_tool,
    delete_calendar_event_tool,
    get_gmail_messages_tool,
    get_whoop_sleep_tool,
    get_whoop_recovery_tool,
    get_whoop_workout_tool,
    search_notion_pages_tool,
    get_twitter_tweets_tool,
    get_github_pull_requests_tool,
    get_github_issues_tool,
    create_github_issue_tool,
    close_github_issue_tool,
    search_files_tool,
    manage_daily_summary_tool,
)
from utils.retrieval.tools.app_tools import load_app_tools, get_tool_status_message
from utils.retrieval.safety import AgentSafetyGuard, SafetyGuardError
from utils.llm.clients import llm_agent, llm_agent_stream
from utils.llm.chat import _get_agentic_qa_prompt
from utils.observability.langsmith import get_chat_tracer_callbacks
from utils.other.endpoints import timeit


def get_tool_display_name(tool_name: str, tool_obj: Optional[Any] = None) -> str:
    """
    Convert tool name to user-friendly display name.

    Args:
        tool_name: Internal tool name (e.g., 'search_notion_pages_tool')
        tool_obj: Optional tool object that may have status_message attribute

    Returns:
        User-friendly display name (e.g., 'Searching Notion')
    """
    # Check if tool has a custom status_message (for app tools)
    # First check the global mapping
    status_msg = get_tool_status_message(tool_name)
    if status_msg:
        return status_msg

    # Fallback: check if tool object has status_message attribute
    if tool_obj and hasattr(tool_obj, 'status_message') and tool_obj.status_message:
        return tool_obj.status_message
    tool_display_map = {
        'search_notion_pages_tool': 'Searching Notion',
        'get_whoop_sleep_tool': 'Checking Whoop sleep data',
        'get_whoop_recovery_tool': 'Checking Whoop recovery data',
        'get_whoop_workout_tool': 'Checking Whoop workout data',
        'get_twitter_tweets_tool': 'Checking Twitter',
        'get_github_pull_requests_tool': 'Checking GitHub pull requests',
        'get_github_issues_tool': 'Checking GitHub issues',
        'create_github_issue_tool': 'Creating GitHub issue',
        'close_github_issue_tool': 'Closing GitHub issue',
        'get_calendar_events_tool': 'Checking calendar',
        'create_calendar_event_tool': 'Creating calendar event',
        'update_calendar_event_tool': 'Updating calendar event',
        'delete_calendar_event_tool': 'Deleting calendar event',
        'get_gmail_messages_tool': 'Checking Gmail',
        'perplexity_web_search_tool': 'Searching the web',
        'get_conversations_tool': 'Searching conversations',
        'search_conversations_tool': 'Searching conversations',
        'get_memories_tool': 'Searching memories',
        'get_action_items_tool': 'Checking action items',
        'create_action_item_tool': 'Creating action item',
        'update_action_item_tool': 'Updating action item',
        'get_omi_product_info_tool': 'Looking up product info',
        'manage_daily_summary_tool': 'Updating notification settings',
    }

    # Try exact match first
    if tool_name in tool_display_map:
        return tool_display_map[tool_name]

    # Try partial matches for common patterns
    if 'notion' in tool_name.lower():
        return 'Searching Notion'
    elif 'whoop' in tool_name.lower():
        return 'Checking Whoop data'
    elif 'twitter' in tool_name.lower():
        return 'Checking Twitter'
    elif 'github' in tool_name.lower():
        return 'Checking GitHub'
    elif 'calendar' in tool_name.lower():
        return 'Checking calendar'
    elif 'perplexity' in tool_name.lower() or 'search' in tool_name.lower():
        return 'Searching the web'
    elif 'memory' in tool_name.lower():
        return 'Searching memories'
    elif 'conversation' in tool_name.lower():
        return 'Searching conversations'
    elif 'action' in tool_name.lower():
        return 'Checking action items'

    # Default: convert snake_case to Title Case
    return tool_name.replace('_', ' ').title()


class AsyncStreamingCallback(BaseCallbackHandler):
    """Callback handler for streaming LLM responses with data and thought prefixes."""

    def __init__(self):
        self.queue = asyncio.Queue()

    async def put_data(self, text):
        """Add a data chunk to the queue."""
        await self.queue.put(f"data: {text}")

    async def put_thought(self, text, app_id: Optional[str] = None):
        """Add a thought/status message to the queue."""
        if app_id:
            await self.queue.put(f"think: {text}|app_id:{app_id}")
        else:
            await self.queue.put(f"think: {text}")

    def put_thought_nowait(self, text, app_id: Optional[str] = None):
        """Add a thought/status message to the queue without waiting."""
        if app_id:
            self.queue.put_nowait(f"think: {text}|app_id:{app_id}")
        else:
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
    
    # Get prompt metadata for tracing/versioning
    try:
        from utils.observability.langsmith_prompts import get_prompt_metadata
        prompt_name, prompt_commit, prompt_source = get_prompt_metadata()
    except Exception as e:
        print(f"⚠️ Could not get prompt metadata: {e}")
        prompt_name, prompt_commit, prompt_source = None, None, None

    # Get all tools
    tools = [
        get_conversations_tool,
        search_conversations_tool,
        get_memories_tool,
        get_action_items_tool,
        create_action_item_tool,
        update_action_item_tool,
        get_omi_product_info_tool,
        perplexity_web_search_tool,
        get_calendar_events_tool,
        create_calendar_event_tool,
        update_calendar_event_tool,
        delete_calendar_event_tool,
        get_gmail_messages_tool,
        get_whoop_sleep_tool,
        get_whoop_recovery_tool,
        get_whoop_workout_tool,
        search_notion_pages_tool,
        get_twitter_tweets_tool,
        get_github_pull_requests_tool,
        get_github_issues_tool,
        create_github_issue_tool,
        close_github_issue_tool,
        search_files_tool,
        manage_daily_summary_tool,
    ]

    # Load tools from enabled apps
    try:
        app_tools = load_app_tools(uid)
        tools.extend(app_tools)
        if app_tools:
            print(f"🔧 Added {len(app_tools)} app tools to chat")
    except Exception as e:
        print(f"⚠️ Error loading app tools: {e}")

    # Convert messages to LangChain format and prepend system message
    lc_messages = [SystemMessage(content=system_prompt)]
    lc_messages.extend(_messages_to_langchain(messages))

    # Create agent with tools
    agent = create_react_agent(
        model=llm_agent,
        tools=tools,
    )

    # Get per-request LangSmith tracer callbacks (enables tracing without global env)
    tracer_callbacks = get_chat_tracer_callbacks(
        run_name="chat.agentic",
        tags=["chat", "agentic"],
        metadata={
            "uid": uid,
            "app_id": app.id if app else None,
            "app_name": app.name if app else None,
            "prompt_name": prompt_name,
            "prompt_commit": prompt_commit,
            "prompt_source": prompt_source,
        },
    )

    # Run agent with LangSmith tracing metadata
    config = {
        "configurable": {
            "user_id": uid,
            "thread_id": str(uuid.uuid4()),
        },
        "callbacks": tracer_callbacks,
        "run_name": "chat.agentic",
        "tags": ["chat", "agentic"],
        "metadata": {
            "uid": uid,
            "app_id": app.id if app else None,
            "app_name": app.name if app else None,
            "prompt_name": prompt_name,
            "prompt_commit": prompt_commit,
            "prompt_source": prompt_source,
        },
    }

    # Store config in context for tools to access
    agent_config_context.set(config)

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
    context: Optional[PageContext] = None,
) -> AsyncGenerator[str, None]:
    """
    Execute an agentic chat interaction with streaming.

    Args:
        uid: User ID
        messages: Chat message history
        app: Optional app/plugin
        callback_data: Dict to store callback data (answer, memories, etc.)
        chat_session: Optional chat session for file context
        context: Optional page context (type, id, title)

    Yields:
        Formatted chunks with "data: " or "think: " prefixes
    """
    # Build system prompt with file context and page context
    system_prompt = _get_agentic_qa_prompt(uid, app, messages, context=context)
    
    # Get prompt metadata for tracing/versioning
    try:
        from utils.observability.langsmith_prompts import get_prompt_metadata
        prompt_name, prompt_commit, prompt_source = get_prompt_metadata()
    except Exception as e:
        print(f"⚠️ Could not get prompt metadata: {e}")
        prompt_name, prompt_commit, prompt_source = None, None, None

    # Get all tools
    tools = [
        get_conversations_tool,
        search_conversations_tool,
        get_memories_tool,
        get_action_items_tool,
        create_action_item_tool,
        update_action_item_tool,
        get_omi_product_info_tool,
        perplexity_web_search_tool,
        get_calendar_events_tool,
        create_calendar_event_tool,
        update_calendar_event_tool,
        delete_calendar_event_tool,
        get_gmail_messages_tool,
        get_whoop_sleep_tool,
        get_whoop_recovery_tool,
        get_whoop_workout_tool,
        search_notion_pages_tool,
        get_twitter_tweets_tool,
        get_github_pull_requests_tool,
        get_github_issues_tool,
        create_github_issue_tool,
        close_github_issue_tool,
        search_files_tool,
        manage_daily_summary_tool,
    ]

    # Load tools from enabled apps
    try:
        app_tools = load_app_tools(uid)
        tools.extend(app_tools)
        if app_tools:
            print(f"🔧 Added {len(app_tools)} app tools to chat")
    except Exception as e:
        print(f"⚠️ Error loading app tools: {e}")

    # Convert messages to LangChain format and prepend system message
    lc_messages = [SystemMessage(content=system_prompt)]
    lc_messages.extend(_messages_to_langchain(messages))

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
    safety_guard = AgentSafetyGuard(max_tool_calls=25, max_context_tokens=500000)

    # Generate run_id for LangSmith tracing (allows feedback attachment later)
    langsmith_run_id = str(uuid.uuid4())

    # Get per-request LangSmith tracer callbacks (enables tracing without global env)
    tracer_callbacks = get_chat_tracer_callbacks(
        run_id=langsmith_run_id,
        run_name="chat.agentic.stream",
        tags=["chat", "agentic", "streaming"],
        metadata={
            "uid": uid,
            "app_id": app.id if app else None,
            "app_name": app.name if app else None,
            "chat_session_id": chat_session.id if chat_session else None,
            "has_context": context is not None,
            "context_type": context.type if context else None,
            "num_tools": len(tools),
            "prompt_name": prompt_name,
            "prompt_commit": prompt_commit,
            "prompt_source": prompt_source,
        },
    )

    # LangSmith tracing metadata
    config = {
        "run_id": langsmith_run_id,  # Explicit run_id for LangSmith feedback
        "configurable": {
            "user_id": uid,
            "thread_id": str(uuid.uuid4()),
            "conversations_collected": conversations_collected,
            "safety_guard": safety_guard,
            "chat_session_id": chat_session.id if chat_session else None,
            "tools": tools,  # Store tools for status message lookup
        },
        "callbacks": tracer_callbacks,
        "run_name": "chat.agentic.stream",
        "tags": ["chat", "agentic", "streaming"],
        "metadata": {
            "uid": uid,
            "app_id": app.id if app else None,
            "app_name": app.name if app else None,
            "chat_session_id": chat_session.id if chat_session else None,
            "has_context": context is not None,
            "context_type": context.type if context else None,
            "num_tools": len(tools),
            "prompt_name": prompt_name,
            "prompt_commit": prompt_commit,
            "prompt_source": prompt_source,
        },
    }

    # Store run_id and prompt metadata in callback_data for message persistence
    if callback_data is not None:
        callback_data['langsmith_run_id'] = langsmith_run_id
        callback_data['prompt_name'] = prompt_name
        callback_data['prompt_commit'] = prompt_commit

    # Store config in context for tools to access
    agent_config_context.set(config)

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

                # Extract app_id from tool name if it's from an app tool
                # App tools have format: app_id_tool_name
                app_id = None
                tools_list = config.get('configurable', {}).get('tools', [])

                # Standard tool names that don't come from apps
                standard_tool_names = {
                    'get_conversations_tool',
                    'search_conversations_tool',
                    'get_memories_tool',
                    'get_action_items_tool',
                    'create_action_item_tool',
                    'update_action_item_tool',
                    'get_omi_product_info_tool',
                    'perplexity_web_search_tool',
                    'get_calendar_events_tool',
                    'create_calendar_event_tool',
                    'update_calendar_event_tool',
                    'delete_calendar_event_tool',
                    'get_gmail_messages_tool',
                    'get_whoop_sleep_tool',
                    'get_whoop_recovery_tool',
                    'get_whoop_workout_tool',
                    'search_notion_pages_tool',
                    'get_twitter_tweets_tool',
                    'get_github_pull_requests_tool',
                    'get_github_issues_tool',
                    'create_github_issue_tool',
                    'close_github_issue_tool',
                    'search_files_tool',
                }

                # If tool name is not a standard tool and contains underscore, it's likely an app tool
                if tool_name not in standard_tool_names and '_' in tool_name:
                    parts = tool_name.split('_', 1)
                    if len(parts) == 2:
                        # First part is likely the app_id
                        app_id = parts[0]

                # Send user-friendly tool call message to frontend
                # Get tool object to check for custom status_message
                tool_obj = None
                for tool in tools_list:
                    if hasattr(tool, 'name') and tool.name == tool_name:
                        tool_obj = tool
                        break

                tool_display_name = get_tool_display_name(tool_name, tool_obj)
                await callback.put_thought(tool_display_name, app_id=app_id)

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
                output_raw = event.get("data", {}).get("output", "")

                # Extract string content from output (could be ToolMessage object or string)
                if hasattr(output_raw, 'content'):
                    output = str(output_raw.content)
                elif isinstance(output_raw, str):
                    output = output_raw
                else:
                    output = str(output_raw)

                print(f"✅ Tool ended: {tool_name}")

                # Send completion message for calendar tools to update status
                if 'calendar' in tool_name.lower():
                    if 'create' in tool_name.lower():
                        # Clear the "Creating calendar event" status
                        # The tool output will contain the success message which the LLM will include
                        if output and ('Successfully created' in output or '✅' in output):
                            # Send a brief completion status that will be replaced by the actual response
                            await callback.put_thought('Event created successfully')
                        elif output and ('Error' in output or 'error' in output.lower()):
                            await callback.put_thought('Failed to create event')
                        else:
                            await callback.put_thought('Creating event...')
                    elif 'update' in tool_name.lower():
                        # Clear the "Updating calendar event" status
                        if output and ('Successfully updated' in output or '✅' in output):
                            await callback.put_thought('Event updated successfully')
                        elif output and ('Error' in output or 'error' in output.lower()):
                            await callback.put_thought('Failed to update event')
                        else:
                            await callback.put_thought('Updating event...')
                    elif 'delete' in tool_name.lower():
                        # Clear the "Deleting calendar event" status
                        if output and ('Successfully deleted' in output or '✅' in output):
                            await callback.put_thought('Event deleted successfully')
                        elif output and ('Error' in output or 'error' in output.lower()):
                            await callback.put_thought('Failed to delete event')
                        else:
                            await callback.put_thought('Deleting event...')
                    elif 'get' in tool_name.lower() or 'search' in tool_name.lower():
                        # For read operations, clear the "Checking calendar" status
                        # The actual results will be in the response
                        if output and len(output) > 0:
                            await callback.put_thought('Found calendar events')
                        else:
                            await callback.put_thought('No events found')

                # Check context size with safety guard
                if safety_guard and output:
                    try:
                        safety_guard.check_context_size(output)
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
