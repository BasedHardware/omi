"""
Agentic chat system using Anthropic native tool use.

This module implements a tool-calling agent that autonomously decides which tools
to use to gather context and answer user questions. Uses Anthropic's native
tool use API with streaming for real-time responses.
"""

import uuid
import asyncio
import contextvars
import traceback
from typing import List, Optional, AsyncGenerator, Any, Tuple

from langchain_core.runnables import RunnableConfig

# Context variable to store config for tools
agent_config_context: contextvars.ContextVar[dict] = contextvars.ContextVar('agent_config', default=None)

from models.app import App
from models.chat import Message, ChatSession, PageContext
from models.conversation import Conversation
from utils.retrieval.tools import (
    get_conversations_tool,
    search_conversations_tool,
    get_memories_tool,
    search_memories_tool,
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
    get_apple_health_steps_tool,
    get_apple_health_sleep_tool,
    get_apple_health_heart_rate_tool,
    get_apple_health_workouts_tool,
    get_apple_health_summary_tool,
    search_files_tool,
    manage_daily_summary_tool,
    create_chart_tool,
    get_screen_activity_tool,
    search_screen_activity_tool,
    save_user_preference_tool,
)
from utils.retrieval.tools.app_tools import load_app_tools, get_tool_status_message
from utils.retrieval.safety import AgentSafetyGuard, SafetyGuardError
from utils.llm.clients import anthropic_client, ANTHROPIC_AGENT_MODEL
from utils.llm.chat import _get_agentic_qa_prompt
from utils.other.endpoints import timeit
from utils.observability.langsmith import is_langsmith_enabled
import logging

# Import langsmith traceable if available
try:
    from langsmith import traceable as _traceable
except ImportError:

    def _traceable(**kwargs):
        def decorator(func):
            return func

        return decorator


logger = logging.getLogger(__name__)

# PROMPT CACHE OPTIMIZATION: This list MUST stay fixed and in this exact order.
# Anthropic caches the tools array as part of the request prefix.  If the tool
# definitions are identical across requests they are cached automatically.
# Dynamic per-user app tools are appended AFTER this list so the prefix stays stable.
CORE_TOOLS = [
    get_conversations_tool,
    search_conversations_tool,
    get_memories_tool,
    search_memories_tool,
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
    get_apple_health_steps_tool,
    get_apple_health_sleep_tool,
    get_apple_health_heart_rate_tool,
    get_apple_health_workouts_tool,
    get_apple_health_summary_tool,
    search_files_tool,
    manage_daily_summary_tool,
    create_chart_tool,
    get_screen_activity_tool,
    search_screen_activity_tool,
    save_user_preference_tool,
]

# Standard tool names (used to detect app tools by exclusion)
STANDARD_TOOL_NAMES = {t.name for t in CORE_TOOLS}


def get_tool_display_name(tool_name: str, tool_obj: Optional[Any] = None) -> str:
    """Convert tool name to user-friendly display name."""
    # Check global mapping from app_tools first
    status_msg = get_tool_status_message(tool_name)
    if status_msg:
        return status_msg

    # Check tool object for custom status_message
    if tool_obj and hasattr(tool_obj, 'status_message') and tool_obj.status_message:
        return tool_obj.status_message

    tool_display_map = {
        'get_calendar_events_tool': 'Checking calendar',
        'create_calendar_event_tool': 'Creating calendar event',
        'update_calendar_event_tool': 'Updating calendar event',
        'delete_calendar_event_tool': 'Deleting calendar event',
        'get_gmail_messages_tool': 'Checking Gmail',
        'perplexity_web_search_tool': 'Searching the web',
        'get_conversations_tool': 'Searching conversations',
        'search_conversations_tool': 'Searching conversations',
        'get_memories_tool': 'Searching memories',
        'search_memories_tool': 'Searching memories',
        'get_action_items_tool': 'Checking action items',
        'create_action_item_tool': 'Creating action item',
        'update_action_item_tool': 'Updating action item',
        'get_omi_product_info_tool': 'Looking up product info',
        'manage_daily_summary_tool': 'Updating notification settings',
        'create_chart_tool': 'Creating chart',
        'get_screen_activity_tool': 'Checking screen activity',
        'search_screen_activity_tool': 'Searching screen activity',
        'save_user_preference_tool': 'Saving preference',
    }

    if tool_name in tool_display_map:
        return tool_display_map[tool_name]

    if 'calendar' in tool_name.lower():
        return 'Checking calendar'
    elif 'perplexity' in tool_name.lower() or 'search' in tool_name.lower():
        return 'Searching the web'
    elif 'memory' in tool_name.lower():
        return 'Searching memories'
    elif 'conversation' in tool_name.lower():
        return 'Searching conversations'
    elif 'action' in tool_name.lower():
        return 'Checking action items'

    return tool_name.replace('_', ' ').title()


class AsyncStreamingCallback:
    """Callback for streaming LLM responses with data and thought prefixes."""

    def __init__(self):
        self.queue = asyncio.Queue()

    async def put_data(self, text):
        await self.queue.put(f"data: {text}")

    async def put_thought(self, text, app_id: Optional[str] = None):
        if app_id:
            await self.queue.put(f"think: {text}|app_id:{app_id}")
        else:
            await self.queue.put(f"think: {text}")

    def put_thought_nowait(self, text, app_id: Optional[str] = None):
        if app_id:
            self.queue.put_nowait(f"think: {text}|app_id:{app_id}")
        else:
            self.queue.put_nowait(f"think: {text}")

    def put_data_nowait(self, text):
        self.queue.put_nowait(f"data: {text}")

    async def end(self):
        await self.queue.put(None)

    def end_nowait(self):
        self.queue.put_nowait(None)


# ---------------------------------------------------------------------------
# Tool schema conversion: LangChain @tool -> Anthropic tool format
# ---------------------------------------------------------------------------


def _langchain_tool_to_anthropic(lc_tool, defer_loading: bool = False) -> dict:
    """Convert a LangChain @tool to Anthropic tool schema format."""
    schema = lc_tool.args_schema.schema()
    properties = {k: v for k, v in schema.get('properties', {}).items() if k != 'config'}
    required = [r for r in schema.get('required', []) if r != 'config']

    # Clean up schema: remove 'title' keys that Pydantic adds (not needed by Anthropic)
    cleaned_properties = {}
    for k, v in properties.items():
        cleaned = {pk: pv for pk, pv in v.items() if pk != 'title'}
        cleaned_properties[k] = cleaned

    tool_def = {
        "name": lc_tool.name,
        "description": lc_tool.description,
        "input_schema": {
            "type": "object",
            "properties": cleaned_properties,
            "required": required,
        },
    }
    if defer_loading:
        tool_def["defer_loading"] = True
    return tool_def


# Tool search tool definition — Anthropic's built-in tool discovery
TOOL_SEARCH_TOOL = {
    "type": "tool_search_tool_regex_20251119",
    "name": "tool_search_tool_regex",
}


def _convert_tools(core_tools: list, app_tools: list = None) -> tuple:
    """Convert all tools and build name->object registry.

    Core tools are always visible to Claude. App tools are marked with
    defer_loading=True so Claude discovers them on-demand via tool search,
    keeping the context window small.

    Returns:
        (tool_schemas, tool_registry) where tool_schemas is a list of Anthropic
        tool definitions and tool_registry maps tool name -> LangChain tool object.
    """
    schemas = []

    # Add tool search tool if there are app tools to discover
    if app_tools:
        schemas.append(TOOL_SEARCH_TOOL)

    # Core tools — always visible
    for t in core_tools:
        schemas.append(_langchain_tool_to_anthropic(t, defer_loading=False))

    # App tools — deferred, discovered on-demand
    for t in app_tools or []:
        schemas.append(_langchain_tool_to_anthropic(t, defer_loading=True))

    # Registry includes ALL tools (core + app) for execution
    all_tools = list(core_tools) + list(app_tools or [])
    registry = {t.name: t for t in all_tools}
    return schemas, registry


@_traceable(name="chat.tool_execution", run_type="tool")
async def _execute_tool(tool_name: str, tool_input: dict, registry: dict, configurable: dict) -> str:
    """Execute a LangChain tool by name, injecting RunnableConfig."""
    tool_obj = registry[tool_name]
    config = RunnableConfig(configurable=configurable)
    result = await tool_obj.ainvoke(tool_input, config=config)
    return str(result)


# ---------------------------------------------------------------------------
# App ID extraction for non-standard tools
# ---------------------------------------------------------------------------


def _extract_app_id(tool_name: str) -> Optional[str]:
    """Extract app_id from an app tool name (format: appid_toolname)."""
    if tool_name not in STANDARD_TOOL_NAMES and '_' in tool_name:
        parts = tool_name.split('_', 1)
        if len(parts) == 2:
            return parts[0]
    return None


# ---------------------------------------------------------------------------
# Calendar tool status messages
# ---------------------------------------------------------------------------


async def _emit_calendar_status(callback: AsyncStreamingCallback, tool_name: str, output: str):
    """Emit calendar-specific completion status messages."""
    if 'calendar' not in tool_name.lower():
        return

    if 'create' in tool_name.lower():
        if output and ('Successfully created' in output or '✅' in output):
            await callback.put_thought('Event created successfully')
        elif output and ('Error' in output or 'error' in output.lower()):
            await callback.put_thought('Failed to create event')
        else:
            await callback.put_thought('Creating event...')
    elif 'update' in tool_name.lower():
        if output and ('Successfully updated' in output or '✅' in output):
            await callback.put_thought('Event updated successfully')
        elif output and ('Error' in output or 'error' in output.lower()):
            await callback.put_thought('Failed to update event')
        else:
            await callback.put_thought('Updating event...')
    elif 'delete' in tool_name.lower():
        if output and ('Successfully deleted' in output or '✅' in output):
            await callback.put_thought('Event deleted successfully')
        elif output and ('Error' in output or 'error' in output.lower()):
            await callback.put_thought('Failed to delete event')
        else:
            await callback.put_thought('Deleting event...')
    elif 'get' in tool_name.lower() or 'search' in tool_name.lower():
        if output and len(output) > 0:
            await callback.put_thought('Found calendar events')
        else:
            await callback.put_thought('No events found')


# ---------------------------------------------------------------------------
# Message format conversion
# ---------------------------------------------------------------------------


def _messages_to_anthropic(messages: List[Message]) -> list:
    """Convert chat messages to Anthropic API format."""
    anthropic_messages = []
    for msg in messages:
        role = "assistant" if msg.sender == "ai" else "user"
        anthropic_messages.append({"role": role, "content": msg.text})
    return anthropic_messages


# ---------------------------------------------------------------------------
# Core Anthropic agent streaming loop
# ---------------------------------------------------------------------------


async def _run_anthropic_agent_stream(
    system_prompt: str,
    messages: list,
    tool_schemas: list,
    tool_registry: dict,
    callback: AsyncStreamingCallback,
    full_response: list,
    safety_guard: AgentSafetyGuard,
    configurable: dict,
):
    """Run the Anthropic tool-use loop with streaming.

    This replaces LangGraph's create_react_agent + astream_events with a simple
    while loop that calls Anthropic's messages API, executes any tool calls,
    and feeds results back until the model stops requesting tools.
    """
    # System prompt with cache_control for Anthropic prompt caching
    system_blocks = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]

    loop_iteration = 0

    while True:
        loop_iteration += 1
        first_text_in_iteration = True

        try:
            async with anthropic_client.messages.stream(
                model=ANTHROPIC_AGENT_MODEL,
                system=system_blocks,
                messages=messages,
                tools=tool_schemas,
                max_tokens=8192,
            ) as stream:
                async for event in stream:
                    # Stream text tokens
                    if event.type == "content_block_delta" and hasattr(event.delta, 'type'):
                        if event.delta.type == "text_delta":
                            # Add separator between loop iterations so text doesn't run together
                            if first_text_in_iteration and loop_iteration > 1 and full_response:
                                last_char = full_response[-1][-1] if full_response[-1] else ''
                                first_char = event.delta.text[0] if event.delta.text else ''
                                if (
                                    last_char
                                    and first_char
                                    and last_char not in (' ', '\n')
                                    and first_char not in (' ', '\n')
                                ):
                                    full_response.append('\n\n')
                                    await callback.put_data('\n\n')
                            first_text_in_iteration = False
                            full_response.append(event.delta.text)
                            await callback.put_data(event.delta.text)
                        elif event.delta.type == "thinking_delta":
                            pass  # Don't stream thinking to client

                    # Emit status when tool call starts
                    elif event.type == "content_block_start":
                        if hasattr(event.content_block, 'type') and event.content_block.type == "tool_use":
                            tool_name = event.content_block.name
                            # Skip tool_search_tool — handled server-side by Anthropic
                            if 'tool_search' in tool_name:
                                logger.info(f"Tool search invoked (server-side)")
                                continue
                            app_id = _extract_app_id(tool_name)
                            tool_obj = tool_registry.get(tool_name)
                            display_name = get_tool_display_name(tool_name, tool_obj)
                            await callback.put_thought(display_name, app_id=app_id)
                            logger.info(f"Tool started: {tool_name}")

                # Get final message while stream is still open
                response = await stream.get_final_message()

        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            await callback.put_data(f"\n\nSorry, I encountered an error. Please try again.")
            await callback.end()
            return

        # If no tool_use, we're done
        if response.stop_reason != "tool_use":
            break

        # Execute tool calls
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        tool_results = []
        should_stop = False

        for block in tool_use_blocks:
            # Safety guard: validate before execution
            try:
                safety_guard.validate_tool_call(block.name, block.input)
                warning = safety_guard.should_warn_user()
                if warning:
                    await callback.put_thought(warning)
            except SafetyGuardError as e:
                await callback.put_data(f"\n\n{str(e)}")
                logger.error(f"Safety Guard blocked tool call: {e}")
                await callback.end()
                return

            # Execute tool
            try:
                result = await _execute_tool(block.name, block.input, tool_registry, configurable)
            except Exception as e:
                logger.error(f"Tool execution error ({block.name}): {e}")
                result = f"Error executing tool: {str(e)}"

            logger.info(f"Tool ended: {block.name}")

            # Calendar status messages
            await _emit_calendar_status(callback, block.name, result)

            # Safety guard: check context size after execution
            try:
                safety_guard.check_context_size(result)
            except SafetyGuardError as e:
                await callback.put_data(f"\n\n{str(e)}")
                logger.error(f"Safety Guard blocked due to context size: {e}")
                await callback.end()
                return

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )

        # Append assistant message + tool results for next iteration
        # Serialize content blocks for the messages array
        assistant_content = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

    # Log final safety guard stats
    stats = safety_guard.get_stats()
    logger.info(f"Safety Guard final stats: {stats}")

    await callback.end()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@_traceable(name="chat.anthropic.stream", run_type="chain")
async def execute_agentic_chat_stream(
    uid: str,
    messages: List[Message],
    app: Optional[App] = None,
    callback_data: dict = None,
    chat_session: Optional[ChatSession] = None,
    context: Optional[PageContext] = None,
) -> AsyncGenerator[str, None]:
    """Execute an agentic chat interaction with streaming.

    Yields formatted chunks with "data: " or "think: " prefixes.
    """
    # Build system prompt
    system_prompt = _get_agentic_qa_prompt(uid, app, messages, context=context)

    # Get prompt metadata for tracing/versioning
    prompt_name, prompt_commit, prompt_source = None, None, None
    try:
        from utils.observability.langsmith_prompts import get_prompt_metadata

        prompt_name, prompt_commit, prompt_source = get_prompt_metadata()
    except Exception as e:
        logger.error(f"Could not get prompt metadata: {e}")

    # Core tools (fixed order) — always visible to Claude
    core_tools = list(CORE_TOOLS)

    # Dynamic app tools — deferred, discovered on-demand via tool search
    app_tools = []
    try:
        app_tools = load_app_tools(uid)
        if app_tools:
            logger.info(f"Loaded {len(app_tools)} app tools (deferred via tool search)")
    except Exception as e:
        logger.error(f"Error loading app tools: {e}")

    # Convert tools to Anthropic format (core = visible, app = defer_loading)
    tool_schemas, tool_registry = _convert_tools(core_tools, app_tools)

    # Convert messages to Anthropic format
    anthropic_messages = _messages_to_anthropic(messages)

    callback = AsyncStreamingCallback()

    # Conversations collected by tools for citation
    conversations_collected = []

    # Safety guard
    safety_guard = AgentSafetyGuard(max_tool_calls=25, max_context_tokens=500000)

    # Generate run_id for LangSmith tracing
    langsmith_run_id = str(uuid.uuid4())

    # Config for tools to access via RunnableConfig
    configurable = {
        "user_id": uid,
        "thread_id": str(uuid.uuid4()),
        "conversations_collected": conversations_collected,
        "safety_guard": safety_guard,
        "chat_session_id": chat_session.id if chat_session else None,
        "tools": core_tools + app_tools,
    }

    # Store config in context variable for tools that use agent_config_context
    agent_config_context.set({"configurable": configurable})

    # Store run_id and prompt metadata in callback_data
    if callback_data is not None:
        callback_data['langsmith_run_id'] = langsmith_run_id
        callback_data['prompt_name'] = prompt_name
        callback_data['prompt_commit'] = prompt_commit

    full_response = []
    tool_usage_count = 0

    # Start agent task
    task = asyncio.create_task(
        _run_anthropic_agent_stream(
            system_prompt,
            anthropic_messages,
            tool_schemas,
            tool_registry,
            callback,
            full_response,
            safety_guard,
            configurable,
        )
    )

    # Stream from callback queue
    try:
        while True:
            chunk = await callback.queue.get()
            if chunk is None:
                break

            if chunk.startswith("think: "):
                tool_usage_count += 1

            yield chunk

        await task

        # Store results in callback_data
        if callback_data is not None:
            callback_data['answer'] = ''.join(full_response)
            callback_data['memories_found'] = conversations_collected if conversations_collected else []
            callback_data['ask_for_nps'] = tool_usage_count > 0
            chart_data_from_config = configurable.get('chart_data')
            if chart_data_from_config:
                callback_data['chart_data'] = chart_data_from_config
            logger.info(f"Collected {len(callback_data['memories_found'])} conversations for citation")

    except asyncio.CancelledError:
        task.cancel()
        raise
    except Exception as e:
        logger.error(f"Error in execute_agentic_chat_stream: {e}")
        traceback.print_exc()
        if callback_data is not None:
            callback_data['error'] = str(e)

    yield None  # Signal completion
