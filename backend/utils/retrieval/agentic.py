"""
Agentic chat system with provider-specific streaming tool use.

This module implements a tool-calling agent that autonomously decides which tools
to use to gather context and answer user questions. Managed gateway traffic uses
the OpenAI-compatible chat-completions contract; direct specialist traffic keeps
Anthropic's native streaming contract.
"""

import json
import uuid
import asyncio
import contextvars
import os
from typing import List, Optional, AsyncGenerator, Any, Tuple

from langchain_core.runnables import RunnableConfig
from langchain_core.callbacks import BaseCallbackHandler

# Context variable to store config for tools
agent_config_context: contextvars.ContextVar[dict] = contextvars.ContextVar('agent_config', default=None)

from models.app import App
from utils.journey_metrics_contract import ClientKind
from utils.observability.journeys import ClientJourneyAttempt
from models.chat import Message, ChatSession, PageContext
from utils.retrieval.tools import (
    get_conversations_tool,
    search_conversations_tool,
    get_memories_tool,
    search_memories_tool,
    get_action_items_tool,
    create_action_item_tool,
    update_action_item_tool,
    get_omi_product_info_tool,
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
    frame_request_runtime_config,
    look_at_frame_tool,
    save_user_preference_tool,
    fetch_url_tool,
    traverse_knowledge_graph_tool,
    get_entity_timeline_tool,
    read_playbook,
    search_historical_facts,
    search_knowledge,
    save_playbook,
    create_standing_trigger,
    close_fact_tool,
)
from utils.retrieval.tools.app_tools import load_app_tools, get_tool_status_message
from utils.retrieval.tools.conversation_jit_gate import (
    append_jit_conversation_retrieval_prompt,
)
from utils.retrieval.tool_result_boundaries import preserve_chat_memory_tool_result_boundary
from utils.retrieval.chat_scope import build_chat_scope
from utils.retrieval.safety import (
    AgentSafetyGuard,
    CollectedContextReady,
    SafetyGuardError,
    fit_within_budget,
    provider_fallback_reason,
    should_retry_provider_error,
    INPUT_TOO_LONG_MESSAGE,
)
from utils.retrieval.web_search_gate import WEB_SEARCH_TOOL, request_tools_after_private_taint
from utils.observability.fallback import record_fallback
from utils.llm.byok_errors import handle_llm_error_async
from utils.llm.clients import anthropic_client, ANTHROPIC_AGENT_MODEL, get_llm, num_tokens_from_string
from utils.llm.usage_tracker import reset_usage_context, set_usage_context
from utils.llm.chat import _get_agentic_qa_prompt, get_current_datetime_block, get_user_timezone
from utils.executors import run_blocking, db_executor
from utils.jit_rollout import JITDecisionStage, resolve_jit_rollout
from utils.chat_followup import (
    FOLLOWUP_DELIMITER,
    FOLLOWUP_PROMPT_SECTION,
    FollowUpTailStreamFilter,
    split_followup_tail,
)
from database.redis_db import get_cached_user_geolocation
from database.users import get_user_location_context_consent
from models.geolocation import Geolocation
from utils.conversations.location import async_get_google_maps_city
import logging

try:
    from utils.llm.gateway_client import should_route_chat_agent_through_gateway
except ImportError:

    def should_route_chat_agent_through_gateway() -> bool:
        return False


# Import langsmith traceable if available
try:
    from langsmith import traceable as _traceable
except ImportError:

    def _traceable(**kwargs):
        def decorator(func):
            return func

        return decorator


logger = logging.getLogger(__name__)


async def _resolve_jit_conversation_retrieval(uid: str) -> bool:
    """Resolve the server-owned JIT rollout before constructing chat config.

    The conversation tools intentionally accept only the resulting per-request
    boolean. They must not perform their own control-plane lookup, and a
    caller-provided config value must never be able to enroll itself. Any
    unknown/error result therefore stays on the released legacy path.
    """
    try:
        decision = await resolve_jit_rollout(uid, stage=JITDecisionStage.READ_ONLY)
    except Exception as error:
        # The control plane is additive. A transient resolver failure must not
        # take down an otherwise healthy chat request or activate JIT by
        # accident. Keep logs type-only so provider details never enter logs.
        logger.warning(
            'JIT conversation retrieval authority unavailable; keeping gate off error_type=%s',
            type(error).__name__,
        )
        return False
    return decision.permits_work


class _PerplexityWebSearchToolProxy:
    """Lazy adapter for the gateway-only web-search function tool.

    Agentic unit tests intentionally load this module with a minimal LangChain
    stub. Avoid importing the optional Perplexity tool module at import time,
    while retaining the real LangChain tool and gateway implementation when a
    managed request actually executes it.
    """

    name = 'perplexity_web_search_tool'
    description = 'Search the web for current information using Perplexity AI.'

    @property
    def args_schema(self):
        try:
            from utils.retrieval.tools.perplexity_tools import perplexity_web_search_tool

            return perplexity_web_search_tool.args_schema
        except ModuleNotFoundError as error:
            if error.name != 'langchain_core.tools':
                raise

            class _FallbackArgsSchema:
                @classmethod
                def schema(cls):
                    return {
                        'properties': {'query': {'type': 'string'}},
                        'required': ['query'],
                    }

            return _FallbackArgsSchema

    async def ainvoke(self, tool_input, config=None):
        from utils.retrieval.tools.perplexity_tools import perplexity_web_search_tool

        return await perplexity_web_search_tool.ainvoke(tool_input, config=config)


perplexity_web_search_tool = _PerplexityWebSearchToolProxy()


def _positive_timeout_from_env(name: str, default: float) -> float:
    """Read a positive stream deadline at import time so invalid deploy config fails fast."""
    raw_value = os.environ.get(name, str(default))
    try:
        timeout = float(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{name} must be a number') from error
    if timeout <= 0:
        raise ValueError(f'{name} must be greater than zero')
    return timeout


def _positive_int_from_env(name: str, default: int) -> int:
    """Read a positive attempt count at import time so invalid deploy config fails fast."""
    raw_value = os.environ.get(name, str(default))
    try:
        attempts = int(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{name} must be an integer') from error
    if attempts <= 0:
        raise ValueError(f'{name} must be greater than zero')
    return attempts


# Setup (timezone / prompt / app tools) has its own budget so multi-second Firestore
# work cannot silently consume the post-setup first-stream-event (TTFT) window.
# After setup, the first event must arrive before the client/proxy deadline; afterwards a
# heartbeat keeps a known-long tool call observable while the total deadline
# still prevents an agent task from running without bound.
AGENT_STREAM_SETUP_TIMEOUT_SECONDS = _positive_timeout_from_env('AGENT_STREAM_SETUP_TIMEOUT_SECONDS', 25.0)
AGENT_STREAM_FIRST_EVENT_TIMEOUT_SECONDS = _positive_timeout_from_env('AGENT_STREAM_FIRST_EVENT_TIMEOUT_SECONDS', 25.0)
AGENT_STREAM_PROGRESS_HEARTBEAT_SECONDS = _positive_timeout_from_env('AGENT_STREAM_PROGRESS_HEARTBEAT_SECONDS', 20.0)
AGENT_STREAM_MAX_DURATION_SECONDS = _positive_timeout_from_env('AGENT_STREAM_MAX_DURATION_SECONDS', 150.0)
AGENT_STREAM_CANCEL_GRACE_SECONDS = _positive_timeout_from_env('AGENT_STREAM_CANCEL_GRACE_SECONDS', 2.0)

# How much of the turn budget a retry needs to be worth starting. The silent-interval bound on
# the call itself belongs to the transport (the gateway client, or the shared Anthropic client
# when features are not routed through it) and is deliberately not overridden per request.
AGENT_STREAM_PROVIDER_MIN_RETRY_HEADROOM_SECONDS = _positive_timeout_from_env(
    'AGENT_STREAM_PROVIDER_MIN_RETRY_HEADROOM_SECONDS', 45.0
)
AGENT_STREAM_PROVIDER_MAX_ATTEMPTS = _positive_int_from_env('AGENT_STREAM_PROVIDER_MAX_ATTEMPTS', 3)
AGENT_STREAM_PROVIDER_RETRY_BACKOFF_SECONDS = _positive_timeout_from_env(
    'AGENT_STREAM_PROVIDER_RETRY_BACKOFF_SECONDS', 1.0
)
# Independent tool_use blocks in one model turn run concurrently. Sequential is
# only required when a later call depends on an earlier result in the same turn
# (rare; default is parallel). Each call still counts toward the safety cap.
AGENT_TOOL_TURN_CONCURRENCY = _positive_int_from_env('AGENT_TOOL_TURN_CONCURRENCY', 8)
_COLLECTED_CONTEXT_TOOL_STUB = (
    'Relevant conversations are already collected. Answer the user from that context '
    'without calling this tool again.'
)
AGENT_STREAM_PROGRESS_HEARTBEAT = 'Still working…'
AGENT_STREAM_SETUP_PROGRESS = 'Preparing response…'
AGENT_STREAM_TIMEOUT_MESSAGE = 'The response took too long. Please try again.'
AGENT_STREAM_FAILURE_MESSAGE = 'Unable to complete the response. Please try again.'
# File chat still uses direct OpenAI Assistants/vision while gateway feature mode is on;
# until that surface is migrated, fail with a typed user-safe copy instead of the generic canned reply.
FILE_CHAT_GATEWAY_BLOCKED_MESSAGE = (
    "File chat isn't available right now. Try again without attachments, or try again later."
)
# Delivered when a provider safety classifier declines the turn. Retrying the same prompt would
# be declined again, so this says the request cannot be answered rather than inviting a retry.
AGENT_REFUSAL_MESSAGE = "I can't help with that one. Try asking me something else."
# Delivered when a loop runs to completion without the model ever emitting text. Unlike a
# refusal this is not a policy decision, so it does invite a retry.
AGENT_EMPTY_ANSWER_MESSAGE = "I wasn't able to put a response together for that. Please try again."

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
    look_at_frame_tool,
    save_user_preference_tool,
    fetch_url_tool,
    traverse_knowledge_graph_tool,
    get_entity_timeline_tool,
    search_knowledge,
    read_playbook,
    search_historical_facts,
    save_playbook,
    create_standing_trigger,
    close_fact_tool,
]

# JIT-only tools: schemas must not reach the model for users outside the JIT
# rollout — a legacy user has no ledger/playbook/frame data, so exposing these
# only burns tool-call budget on "no entries found" answers and changes chat
# behavior for the whole fleet. Filtered per request off the same resolved
# rollout boolean that gates the JIT prompt appendix, keeping the tool block
# stable per user within a rollout state. The three ledger write verbs
# (save_playbook, create_standing_trigger, close_fact) mutate the same
# rollout-gated ledger the read tools above expose, so they are gated
# identically.
JIT_ONLY_TOOL_NAMES = frozenset(
    tool.name
    for tool in (
        look_at_frame_tool,
        get_entity_timeline_tool,
        search_knowledge,
        read_playbook,
        search_historical_facts,
        save_playbook,
        create_standing_trigger,
        close_fact_tool,
    )
)

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
        'web_search': 'Searching the web',
        'get_conversations_tool': 'Searching conversations',
        'search_conversations_tool': 'Searching conversations',
        'get_memories_tool': 'Searching memories',
        'search_memories_tool': 'Searching memories',
        'traverse_knowledge_graph_tool': 'Traversing knowledge graph',
        'get_entity_timeline_tool': 'Reviewing entity timeline',
        'search_knowledge': 'Searching current knowledge',
        'read_playbook': 'Reading playbook',
        'search_historical_facts': 'Searching historical facts',
        'save_playbook': 'Saving playbook',
        'create_standing_trigger': 'Creating standing trigger',
        'close_fact': 'Closing fact',
        'get_action_items_tool': 'Checking action items',
        'create_action_item_tool': 'Creating action item',
        'update_action_item_tool': 'Updating action item',
        'get_omi_product_info_tool': 'Looking up product info',
        'manage_daily_summary_tool': 'Updating notification settings',
        'create_chart_tool': 'Creating chart',
        'get_screen_activity_tool': 'Checking screen activity',
        'search_screen_activity_tool': 'Searching screen activity',
        'save_user_preference_tool': 'Saving preference',
        'fetch_url_tool': 'Reading page',
    }

    if tool_name in tool_display_map:
        return tool_display_map[tool_name]

    if 'calendar' in tool_name.lower():
        return 'Checking calendar'
    elif 'web_search' in tool_name.lower():
        return 'Searching the web'
    elif 'memory' in tool_name.lower():
        return 'Searching memories'
    elif 'conversation' in tool_name.lower():
        return 'Searching conversations'
    elif 'action' in tool_name.lower():
        return 'Checking action items'

    return tool_name.replace('_', ' ').title()


class AsyncStreamingCallback(BaseCallbackHandler):
    """Callback for streaming LLM responses with data and thought prefixes."""

    def __init__(self):
        self.queue = asyncio.Queue()
        # Sync providers can invoke the nowait methods from an executor worker.
        # asyncio.Queue is bound to this request loop, so its mutation must always
        # be marshalled back to that loop instead of happening from the worker.
        self._loop = asyncio.get_running_loop()

    def _put_nowait_threadsafe(self, value: str | None) -> None:
        """Queue a synchronous callback value on the loop that owns the response."""
        if self._loop.is_closed():
            return
        try:
            self._loop.call_soon_threadsafe(self.queue.put_nowait, value)
        except RuntimeError:
            # The request loop can close after a bounded stream is cancelled while
            # a non-cooperative sync provider is still unwinding in its worker.
            return

    async def put_data(self, text):
        await self.queue.put(f"data: {text}")

    async def put_thought(self, text, app_id: Optional[str] = None):
        if app_id:
            await self.queue.put(f"think: {text}|app_id:{app_id}")
        else:
            await self.queue.put(f"think: {text}")

    def put_thought_nowait(self, text, app_id: Optional[str] = None):
        if app_id:
            self._put_nowait_threadsafe(f"think: {text}|app_id:{app_id}")
        else:
            self._put_nowait_threadsafe(f"think: {text}")

    def put_data_nowait(self, text):
        self._put_nowait_threadsafe(f"data: {text}")

    async def end(self):
        await self.queue.put(None)

    def end_nowait(self):
        self._put_nowait_threadsafe(None)

    async def on_llm_new_token(self, token: str, **_kwargs) -> None:
        """Bridge LangChain streaming callbacks for persona chat."""
        await self.put_data(token)

    async def on_llm_end(self, _response, **_kwargs) -> None:
        """Always terminate the persona callback queue on normal completion."""
        await self.end()

    async def on_llm_error(self, _error: Exception, **_kwargs) -> None:
        """Terminate the persona callback queue without exposing provider details."""
        await self.end()


# ---------------------------------------------------------------------------
# Tool schema conversion: LangChain @tool -> OpenAI chat-completions (live)
# and Anthropic Messages (leftover specialist tests only).
# ---------------------------------------------------------------------------


def _langchain_tool_parameters(lc_tool) -> tuple[str, str, dict]:
    """Shared name/description/JSON-schema extraction for both wire formats."""
    schema = lc_tool.args_schema.schema()
    properties = {k: v for k, v in schema.get('properties', {}).items() if k != 'config'}
    required = [r for r in schema.get('required', []) if r != 'config']
    cleaned_properties = {}
    for key, value in properties.items():
        cleaned_properties[key] = {pk: pv for pk, pv in value.items() if pk != 'title'}
    return (
        lc_tool.name,
        lc_tool.description,
        {
            'type': 'object',
            'properties': cleaned_properties,
            'required': required,
        },
    )


def _langchain_tool_to_openai(lc_tool) -> dict:
    """Convert a LangChain @tool to the chat-completions function shape."""
    name, description, parameters = _langchain_tool_parameters(lc_tool)
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': description,
            'parameters': parameters,
        },
    }


def _langchain_tool_to_anthropic(lc_tool, defer_loading: bool = False) -> dict:
    """Leftover Anthropic Messages schema. Not the live chat-agent path."""
    name, description, parameters = _langchain_tool_parameters(lc_tool)
    tool_def = {
        "name": name,
        "description": description,
        "input_schema": parameters,
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
    """Convert tools to the live OpenAI chat-completions function shape.

    Anthropic server tools (``web_search``, ``tool_search_tool_regex``) are not
    part of this contract. App tools are exposed directly so the model can call
    them by name.
    """
    all_tools = list(core_tools) + list(app_tools or [])
    schemas = [_langchain_tool_to_openai(t) for t in all_tools]
    registry = {t.name: t for t in all_tools}
    return schemas, registry


def _collected_results_from_config(configurable: dict | None) -> Any:
    if not isinstance(configurable, dict):
        return None
    collected = configurable.get('conversations_collected')
    if collected:
        return collected
    evidence = configurable.get('evidence_references')
    return evidence or None


async def _execute_independent_tool_calls(
    tool_calls: list,
    *,
    name_of,
    input_of,
    id_of,  # noqa: ARG001 — caller-facing symmetry with name/input
    tool_registry: dict,
    configurable: dict,
    safety_guard: AgentSafetyGuard,
    callback: 'AsyncStreamingCallback',
    full_response: list,
    result_factory,
) -> list | None:
    """Validate sequentially, run independent tools concurrently, preserve order.

    Returns the provider-shaped tool results, or ``None`` when a hard safety
    limit ended the stream. ``CollectedContextReady`` stubs remaining calls so
    the model can answer from already-collected conversations.
    """
    collected = _collected_results_from_config(configurable)
    validated: list = []
    stub_after = False
    for call in tool_calls:
        try:
            safety_guard.validate_tool_call(name_of(call), input_of(call), collected_results=collected)
            warning = safety_guard.should_warn_user()
            if warning:
                await callback.put_thought(warning)
            validated.append(call)
        except CollectedContextReady:
            stub_after = True
            break
        except SafetyGuardError as error:
            await _put_outcome_text(callback, full_response, f'\n\n{str(error)}')
            logger.error('Safety Guard blocked tool call: %s', error)
            await callback.end()
            return None

    for call in validated:
        tool_name = name_of(call)
        await callback.put_thought(
            get_tool_display_name(tool_name, tool_registry.get(tool_name)), app_id=_extract_app_id(tool_name)
        )

    async def _run_one(call):
        tool_name = name_of(call)
        try:
            return await _execute_tool(tool_name, input_of(call), tool_registry, configurable)
        except Exception as error:
            logger.error('Tool execution error (%s): %s', tool_name, error)
            return f'Error executing tool: {str(error)}'

    results_text: list[str] = []
    if validated:
        semaphore = asyncio.Semaphore(AGENT_TOOL_TURN_CONCURRENCY)

        async def _bounded(call):
            async with semaphore:
                return await _run_one(call)

        results_text = list(await asyncio.gather(*[_bounded(call) for call in validated]))

    tool_results = []
    for call, result in zip(validated, results_text):
        tool_name = name_of(call)
        logger.info('Tool ended: %s', tool_name)
        await _emit_calendar_status(callback, tool_name, result)
        try:
            safety_guard.check_context_size(result)
        except SafetyGuardError as error:
            await _put_outcome_text(callback, full_response, f'\n\n{str(error)}')
            logger.error('Safety Guard blocked due to context size: %s', error)
            await callback.end()
            return None
        tool_results.append(result_factory(call, result))

    if stub_after:
        for call in tool_calls[len(validated) :]:
            tool_results.append(result_factory(call, _COLLECTED_CONTEXT_TOOL_STUB))

    return tool_results


def _convert_anthropic_tools_to_openai(tool_schemas: list[dict]) -> list[dict]:
    """Convert function-shaped Anthropic tools to the chat-completions shape.

    Anthropic's server-side ``web_search`` and ``tool_search_tool_regex`` entries
    intentionally have no ``input_schema``. They are not part of the OpenAI
    contract, so filtering them here keeps the managed lane from receiving an
    invalid tool definition. App tools are already present in ``tool_schemas``
    and are exposed directly instead of relying on Anthropic tool discovery.
    """
    openai_tools = []
    for tool in tool_schemas:
        input_schema = tool.get('input_schema')
        if not isinstance(input_schema, dict):
            continue
        openai_tools.append(
            {
                'type': 'function',
                'function': {
                    'name': tool['name'],
                    'description': tool.get('description', ''),
                    'parameters': input_schema,
                },
            }
        )
    return openai_tools


_MEMORY_RETRIEVAL_TOOLS = frozenset({'get_memories_tool', 'search_memories_tool'})


def _finish_memory_retrieval(attempt: ClientJourneyAttempt, result: str) -> None:
    normalized = result.strip().lower()
    if not normalized or normalized.startswith('no memories found'):
        attempt.degrade('empty_answer')
    elif normalized.startswith('error'):
        attempt.fail('dependency_unavailable')
    else:
        attempt.succeed()


@_traceable(name="chat.tool_execution", run_type="tool")
async def _execute_tool(tool_name: str, tool_input: dict, registry: dict, configurable: dict) -> str:
    """Execute a LangChain tool by name, injecting RunnableConfig."""
    tool_obj = registry[tool_name]
    config = RunnableConfig(configurable=configurable)
    client_kind = configurable.get('client_kind')
    attempt = (
        ClientJourneyAttempt('memory_retrieval', client_kind)
        if tool_name in _MEMORY_RETRIEVAL_TOOLS and client_kind is not None
        else None
    )
    try:
        result = await tool_obj.ainvoke(tool_input, config=config)
    except asyncio.CancelledError:
        if attempt is not None:
            attempt.cancel()
        raise
    except Exception:
        if attempt is not None:
            attempt.fail('dependency_unavailable')
        raise
    result = preserve_chat_memory_tool_result_boundary(tool_name, str(result))
    if attempt is not None:
        _finish_memory_retrieval(attempt, result)
    return result


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


def _inject_current_datetime(anthropic_messages: list, datetime_block: str) -> list:
    """Prepend the current-datetime block to the latest user turn.

    The datetime changes every request, so it is kept out of the cache_control system
    prefix (which must stay byte-identical for prompt-cache hits) and delivered here in the
    user turn instead. Handles both string content (prepended as text) and list/multimodal
    content (prepended as a leading text block). Falls back to appending a new user message
    only if there is no user turn to attach it to.
    """
    if not datetime_block:
        return anthropic_messages
    for msg in reversed(anthropic_messages):
        if msg["role"] != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            msg["content"] = f"{datetime_block}\n\n{content}"
        elif isinstance(content, list):
            msg["content"] = [{"type": "text", "text": datetime_block}, *content]
        else:
            break  # unexpected content shape — fall back to a separate user message
        return anthropic_messages
    anthropic_messages.append({"role": "user", "content": datetime_block})
    return anthropic_messages


async def get_mobile_city(uid: str, platform: Optional[str]) -> Optional[str]:
    if platform is None or platform.strip().lower() not in {'ios', 'android'}:
        return None
    try:
        consent = await run_blocking(db_executor, get_user_location_context_consent, uid)
        if consent is None or not consent.is_active():
            return None
        geolocation = await run_blocking(db_executor, get_cached_user_geolocation, uid)
        if not geolocation:
            return None
        validated_geolocation = Geolocation.model_validate(geolocation)
        return await async_get_google_maps_city(validated_geolocation.latitude, validated_geolocation.longitude)
    except (KeyError, TypeError, ValueError):
        return None
    except Exception as error:
        logger.warning('Mobile city context unavailable error_type=%s', type(error).__name__)
        return None


# ---------------------------------------------------------------------------
# Core Anthropic agent streaming loop
# ---------------------------------------------------------------------------


async def _put_answer_text(callback: AsyncStreamingCallback, full_response: list, text: str) -> None:
    """Stream text to the client and record it as part of the answer.

    ``put_data`` alone reaches only the live stream; the persisted reply and the terminal
    ``done:`` frame are built from ``full_response``, so text that skips it is overwritten by
    the router's canned error when the turn ends.
    """
    full_response.append(text)
    await callback.put_data(text)


async def _put_outcome_text(callback: AsyncStreamingCallback, full_response: list, text: str) -> None:
    """Record backend-authored text that ends the turn, voiding any follow-up tail.

    A model can emit its closing-question marker and still leave tool calls to run. If the turn
    then ends on a safety limit or an error, the parser would split the answer at that marker and
    drop this message with the rest of the tail — the user would be left with the partial answer
    and no reason for it. Backend outcome text supersedes the tail: the marker is removed, so this
    message stays in the persisted answer and the failed turn offers no chip. ``full_response`` is
    rebuilt when that happens, so no caller may hold an index into it across this call.
    """
    joined = ''.join(full_response)
    marker = joined.find(FOLLOWUP_DELIMITER)
    if marker >= 0:
        full_response[:] = [joined[:marker].rstrip()]
    await _put_answer_text(callback, full_response, text)


def _has_answer(full_response: list) -> bool:
    """Whether anything the router would render as an answer has been delivered.

    List truthiness is not the same question. A stream can emit the inter-iteration separator or
    a whitespace-only delta and then fail, which leaves ``full_response`` non-empty while the
    persisted reply is still blank to the reader.
    """
    return bool(''.join(full_response).strip())


async def _end_with_answer_guarantee(
    callback: AsyncStreamingCallback, full_response: list, provider: str
) -> Optional[str]:
    """Close the stream, guaranteeing the turn left the user something to read.

    Either loop can run to completion without the model emitting any text: a content filter, an
    empty completion, or a tool-only iteration with nothing to say. ``full_response`` is what the
    router persists and renders, so returning here silently hands the user a blank answer and
    records the turn as a success. Report it as the failure it is instead.
    """
    if _has_answer(full_response):
        await callback.end()
        return None
    logger.warning('Chat agent loop finished with no answer provider=%s', provider)
    await _put_answer_text(callback, full_response, AGENT_EMPTY_ANSWER_MESSAGE)
    await callback.end()
    return 'empty_answer'


def _refusal_category(response: Any) -> str:
    """Name the policy category behind a refusal, for logs only.

    ``stop_details`` is populated only alongside ``stop_reason == "refusal"`` and is absent on
    older provider versions, so every level is optional. The category is a fixed provider enum
    and carries none of the request content.
    """
    details = getattr(response, 'stop_details', None)
    category = getattr(details, 'category', None) if details is not None else None
    return category if isinstance(category, str) and category else 'unspecified'


async def _run_anthropic_agent_stream(
    system_prompt: str,
    messages: list,
    tool_schemas: list,
    tool_registry: dict,
    callback: AsyncStreamingCallback,
    full_response: list,
    safety_guard: AgentSafetyGuard,
    configurable: dict,
) -> Optional[str]:
    """Run the Anthropic tool-use loop with streaming.

    This replaces LangGraph's create_react_agent + astream_events with a simple
    while loop that calls Anthropic's messages API, executes any tool calls,
    and feeds results back until the model stops requesting tools.

    Returns ``None`` when the loop finished on its own terms, or a short failure reason when it
    gave up on the provider.
    """
    # System prompt with cache_control for Anthropic prompt caching
    # TTL=1h: Anthropic changed default from 1h→5m on 2026-03-06; interactive chat
    # sessions have gaps >5min between turns, so the 5-min default kills cache hit rate.
    system_blocks = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral", "ttl": "1h"}}]

    producer_started_at = asyncio.get_running_loop().time()
    loop_iteration = 0

    # Re-decide the server-side web_search offer inside the loop. The taint
    # only appears after tool results are appended; see web_search_gate.py.
    server_web_search_withheld = False

    while True:
        loop_iteration += 1

        request_tools, server_web_search_withheld = request_tools_after_private_taint(
            tool_schemas, messages, withheld=server_web_search_withheld
        )

        attempts_made = 0
        retried_reason: Optional[str] = None

        while True:
            attempts_made += 1
            first_text_in_iteration = True
            text_before_attempt = len(full_response)

            try:
                async with anthropic_client.messages.stream(
                    model=ANTHROPIC_AGENT_MODEL,
                    system=system_blocks,
                    messages=messages,
                    tools=request_tools,
                    max_tokens=8192,
                    # Anthropic moves this breakpoint to the last cacheable message
                    # block on every request. That incrementally caches both the
                    # append-only inter-turn history epoch and each agentic tool-loop
                    # iteration while the explicit system breakpoint remains stable.
                    cache_control={"type": "ephemeral", "ttl": "1h"},
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
                            if hasattr(event.content_block, 'type') and event.content_block.type == "server_tool_use":
                                server_tool_name = getattr(event.content_block, 'name', '')
                                if server_tool_name == 'web_search':
                                    await callback.put_thought('Searching the web')
                                logger.info(f"Server tool invoked: {server_tool_name}")
                            elif hasattr(event.content_block, 'type') and event.content_block.type == "tool_use":
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
                break

            except Exception as e:
                elapsed = asyncio.get_running_loop().time() - producer_started_at
                if should_retry_provider_error(
                    e,
                    attempts_made=attempts_made,
                    max_attempts=AGENT_STREAM_PROVIDER_MAX_ATTEMPTS,
                    text_already_streamed=len(full_response) > text_before_attempt,
                    seconds_remaining=AGENT_STREAM_MAX_DURATION_SECONDS - elapsed,
                    min_headroom_seconds=AGENT_STREAM_PROVIDER_MIN_RETRY_HEADROOM_SECONDS,
                ):
                    retried_reason = provider_fallback_reason(e)
                    logger.warning(
                        'Agent stream provider call failed, retrying attempt=%d error_type=%s',
                        attempts_made + 1,
                        type(e).__name__,
                    )
                    await asyncio.sleep(AGENT_STREAM_PROVIDER_RETRY_BACKOFF_SECONDS)
                    continue

                await handle_llm_error_async(e, 'anthropic', feature='chat_agent', model=ANTHROPIC_AGENT_MODEL)
                # ``put_data`` alone reaches the live stream but not the persisted answer, so the
                # router would overwrite this apology with its own canned error.
                await _put_outcome_text(callback, full_response, "\n\nSorry, I encountered an error. Please try again.")
                await callback.end()
                return f'provider_{type(e).__name__}'

        if retried_reason is not None:
            record_fallback(
                component='other',
                from_mode='llm_answer',
                to_mode='llm_answer_retried',
                reason=retried_reason,
                outcome='recovered',
            )

        # A safety classifier can decline the turn. The response is a normal success with an
        # empty (or partial) content list, so the loop would otherwise exit as if the model had
        # simply answered nothing: the router sees a blank answer, emits its generic error, and
        # records no error at all. Say so through the normal streamed/persisted contract and
        # report the turn as failed instead.
        if response.stop_reason == "refusal":
            logger.warning('Chat agent turn refused by provider category=%s', _refusal_category(response))
            if not _has_answer(full_response):
                await _put_outcome_text(callback, full_response, AGENT_REFUSAL_MESSAGE)
            await callback.end()
            return 'provider_refusal'

        # If no tool_use, we're done
        if response.stop_reason != "tool_use":
            break

        # Execute independent tool_use blocks concurrently (leftover Anthropic path).
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        tool_results = await _execute_independent_tool_calls(
            tool_use_blocks,
            name_of=lambda block: block.name,
            input_of=lambda block: block.input,
            id_of=lambda block: block.id,
            tool_registry=tool_registry,
            configurable=configurable,
            safety_guard=safety_guard,
            callback=callback,
            full_response=full_response,
            result_factory=lambda block, result: {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            },
        )
        if tool_results is None:
            return None

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

    return await _end_with_answer_guarantee(callback, full_response, 'anthropic')


def _openai_content_text(content: Any) -> str:
    """Extract text from an OpenAI-compatible message or message chunk."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ''

    text_parts = []
    for part in content:
        if isinstance(part, dict):
            text = part.get('text')
        else:
            text = getattr(part, 'text', None)
        if isinstance(text, str):
            text_parts.append(text)
    return ''.join(text_parts)


def _normalize_openai_tool_call(raw_call: dict, index: int) -> dict:
    """Normalize LangChain/OpenAI tool-call variants to one internal shape."""
    function = raw_call.get('function') if isinstance(raw_call.get('function'), dict) else {}
    name = raw_call.get('name') or function.get('name')
    if not isinstance(name, str) or not name:
        raise ValueError('OpenAI tool call omitted a function name')

    arguments = raw_call.get('args')
    if arguments is None:
        arguments = function.get('arguments')
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as error:
            raise ValueError('OpenAI tool call contained invalid arguments') from error
    if not isinstance(arguments, dict):
        arguments = {}

    call_id = raw_call.get('id') or f'call_{index}'
    return {'id': call_id, 'name': name, 'input': arguments}


def _openai_tool_calls(chunks: list[Any]) -> list[dict]:
    """Collect complete tool calls from streamed OpenAI-compatible chunks."""
    tool_call_chunks = []
    for chunk in chunks:
        raw_chunks = getattr(chunk, 'tool_call_chunks', None) or []
        if isinstance(raw_chunks, list):
            tool_call_chunks.extend(raw_chunks)

    if tool_call_chunks:
        aggregated: dict[str, dict[str, Any]] = {}
        by_index: dict[str, str] = {}
        by_id: dict[str, str] = {}
        for position, raw_call in enumerate(tool_call_chunks):
            if not isinstance(raw_call, dict):
                continue
            raw_index = raw_call.get('index')
            raw_id = raw_call.get('id')
            if raw_index is not None and str(raw_index) in by_index:
                key = by_index[str(raw_index)]
            elif raw_id and str(raw_id) in by_id:
                key = by_id[str(raw_id)]
            else:
                if raw_id:
                    key = str(raw_id)
                elif raw_index is not None:
                    key = str(raw_index)
                else:
                    key = str(position)
            if raw_index is not None:
                by_index[str(raw_index)] = key
            if raw_id:
                by_id[str(raw_id)] = key
            entry = aggregated.setdefault(key, {'id': raw_call.get('id'), 'name': '', 'args': ''})
            if raw_call.get('id'):
                entry['id'] = raw_call['id']
            if raw_call.get('name'):
                entry['name'] += raw_call['name']
            arguments = raw_call.get('args')
            if isinstance(arguments, str):
                if isinstance(entry['args'], str):
                    entry['args'] += arguments
                else:
                    entry['args'] = arguments
            elif isinstance(arguments, dict):
                entry['args'] = arguments
        return [_normalize_openai_tool_call(call, index) for index, call in enumerate(aggregated.values())]

    for chunk in reversed(chunks):
        raw_tool_calls = getattr(chunk, 'tool_calls', None) or []
        if not raw_tool_calls:
            additional_kwargs = getattr(chunk, 'additional_kwargs', {})
            if isinstance(additional_kwargs, dict):
                raw_tool_calls = additional_kwargs.get('tool_calls') or []
        if raw_tool_calls:
            return [_normalize_openai_tool_call(call, index) for index, call in enumerate(raw_tool_calls)]
    return []


async def _run_openai_agent_stream(
    system_prompt: str,
    messages: list,
    tool_schemas: list,
    tool_registry: dict,
    callback: AsyncStreamingCallback,
    full_response: list,
    safety_guard: AgentSafetyGuard,
    configurable: dict,
) -> Optional[str]:
    """Run the managed agent loop through the OpenAI chat-completions contract."""
    try:
        chat_model = get_llm('chat_agent', streaming=True)
        chat_model = chat_model.bind(tools=tool_schemas, tool_choice='auto', max_completion_tokens=8192)
    except Exception as error:
        await handle_llm_error_async(error, 'openai', feature='chat_agent', model='omi:auto:chat-agent')
        # ``put_data`` alone reaches the live stream but not the persisted answer, so the
        # router would overwrite this apology with its own canned error.
        await _put_answer_text(callback, full_response, '\n\nSorry, I encountered an error. Please try again.')
        await callback.end()
        return f'provider_{type(error).__name__}'

    producer_started_at = asyncio.get_running_loop().time()
    loop_iteration = 0

    while True:
        loop_iteration += 1
        attempts_made = 0
        retried_reason: Optional[str] = None

        while True:
            attempts_made += 1
            first_text_in_iteration = True
            text_before_attempt = len(full_response)
            iteration_text: list[str] = []
            chunks: list[Any] = []

            try:
                usage_token = None
                user_id = configurable.get('user_id') if isinstance(configurable, dict) else None
                if isinstance(user_id, str) and user_id:
                    usage_token = set_usage_context(user_id, 'chat_agent')
                try:
                    async for chunk in chat_model.astream([{'role': 'system', 'content': system_prompt}, *messages]):
                        chunks.append(chunk)
                        text = _openai_content_text(getattr(chunk, 'content', ''))
                        if not text:
                            continue
                        if first_text_in_iteration and loop_iteration > 1 and full_response:
                            last_char = full_response[-1][-1] if full_response[-1] else ''
                            first_char = text[0]
                            if (
                                last_char
                                and first_char
                                and last_char not in (' ', '\n')
                                and first_char not in (' ', '\n')
                            ):
                                await _put_answer_text(callback, full_response, '\n\n')
                        first_text_in_iteration = False
                        iteration_text.append(text)
                        await _put_answer_text(callback, full_response, text)
                finally:
                    if usage_token is not None:
                        reset_usage_context(usage_token)
                tool_calls = _openai_tool_calls(chunks)
                break
            except Exception as error:
                elapsed = asyncio.get_running_loop().time() - producer_started_at
                if should_retry_provider_error(
                    error,
                    attempts_made=attempts_made,
                    max_attempts=AGENT_STREAM_PROVIDER_MAX_ATTEMPTS,
                    text_already_streamed=len(full_response) > text_before_attempt,
                    seconds_remaining=AGENT_STREAM_MAX_DURATION_SECONDS - elapsed,
                    min_headroom_seconds=AGENT_STREAM_PROVIDER_MIN_RETRY_HEADROOM_SECONDS,
                ):
                    retried_reason = provider_fallback_reason(error)
                    logger.warning(
                        'Agent stream provider call failed, retrying attempt=%d error_type=%s',
                        attempts_made + 1,
                        type(error).__name__,
                    )
                    await asyncio.sleep(AGENT_STREAM_PROVIDER_RETRY_BACKOFF_SECONDS)
                    continue

                await handle_llm_error_async(error, 'openai', feature='chat_agent', model='omi:auto:chat-agent')
                await _put_outcome_text(callback, full_response, '\n\nSorry, I encountered an error. Please try again.')
                await callback.end()
                return f'provider_{type(error).__name__}'

        if retried_reason is not None:
            record_fallback(
                component='other',
                from_mode='llm_answer',
                to_mode='llm_answer_retried',
                reason=retried_reason,
                outcome='recovered',
            )

        if not tool_calls:
            break

        tool_results = await _execute_independent_tool_calls(
            tool_calls,
            name_of=lambda tool_call: tool_call['name'],
            input_of=lambda tool_call: tool_call['input'],
            id_of=lambda tool_call: tool_call['id'],
            tool_registry=tool_registry,
            configurable=configurable,
            safety_guard=safety_guard,
            callback=callback,
            full_response=full_response,
            result_factory=lambda tool_call, result: {
                'role': 'tool',
                'tool_call_id': tool_call['id'],
                'content': result,
            },
        )
        if tool_results is None:
            return None

        assistant_message = {
            'role': 'assistant',
            'content': ''.join(iteration_text),
            'tool_calls': [
                {
                    'id': tool_call['id'],
                    'type': 'function',
                    'function': {
                        'name': tool_call['name'],
                        'arguments': json.dumps(tool_call['input'], separators=(',', ':')),
                    },
                }
                for tool_call in tool_calls
            ],
        }
        messages.append(assistant_message)
        messages.extend(tool_results)

    logger.info('Safety Guard final stats: %s', safety_guard.get_stats())
    return await _end_with_answer_guarantee(callback, full_response, 'openai')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def next_stream_chunk(callback: AsyncStreamingCallback, task: asyncio.Task, timeout_seconds: float) -> str | None:
    """Return the next callback chunk while supervising the producer task.

    The callback queue is not a completion primitive: an uncaught producer
    error can leave it empty forever. Race the queue receive against the
    producer so unexpected completion is surfaced immediately, and bound an
    otherwise silent dependency stall below the client/proxy deadline.
    """
    queue_get_task = asyncio.create_task(callback.queue.get())
    try:
        completed, _pending = await asyncio.wait(
            {queue_get_task, task},
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if queue_get_task in completed:
            return queue_get_task.result()

        if task in completed:
            try:
                task.result()
            except asyncio.CancelledError as error:
                raise RuntimeError('agent producer was cancelled') from error
            raise RuntimeError('agent producer exited without an end-of-stream callback')

        raise asyncio.TimeoutError
    finally:
        if not queue_get_task.done():
            queue_get_task.cancel()
            try:
                await queue_get_task
            except asyncio.CancelledError:
                pass


async def cancel_stream_task(task: asyncio.Task) -> None:
    """Request cancellation without letting a non-cooperative dependency hold the SSE open."""
    if task.done():
        return

    task.cancel()
    completed, _pending = await asyncio.wait({task}, timeout=AGENT_STREAM_CANCEL_GRACE_SECONDS)
    if task not in completed:
        # A dependency that suppresses cancellation must not keep a client
        # request alive. Retain a done callback solely to consume any eventual
        # exception rather than leaking an unhandled-task warning.
        task.cancel()
        task.add_done_callback(_consume_agent_task_exception)
        logger.error('Agent stream producer ignored cancellation within %.1fs', AGENT_STREAM_CANCEL_GRACE_SECONDS)


def _consume_agent_task_exception(task: asyncio.Task) -> None:
    """Consume a detached task result without logging raw provider data."""
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as error:
        logger.error('Detached agent stream producer failed error_type=%s', type(error).__name__)


@_traceable(name="chat.openai.stream", run_type="chain")
async def execute_agentic_chat_stream(
    uid: str,
    messages: List[Message],
    app: Optional[App] = None,
    callback_data: dict = None,
    chat_session: Optional[ChatSession] = None,
    context: Optional[PageContext] = None,
    platform: Optional[str] = None,
    client_kind: Optional[ClientKind] = None,
    current_datetime_block: Optional[str] = None,
    tz: Optional[str] = None,
    setup_deadline_at: Optional[float] = None,
) -> AsyncGenerator[str, None]:
    """Execute an agentic chat interaction with streaming.

    Yields formatted chunks with "data: " or "think: " prefixes.
    ``setup_deadline_at`` is an absolute loop-clock deadline shared with the
    chat router so metadata + prompt/tool load use one setup budget.
    """
    # Guard against oversized input before any setup or model call. An extremely long message (or
    # a long history) would exceed the chat model's context window; the Anthropic call then raises
    # input-too-long, the agent loop swallows it, and the client is left without a finalized reply
    # ("no response"). Trim the oldest turns to fit the budget; if the newest message alone is too
    # large, return a clear, persisted reply through the normal done: contract instead of calling
    # the model with input that cannot fit.
    messages, input_too_long = fit_within_budget(messages, lambda m: m.text or "", num_tokens_from_string)
    if input_too_long:
        logger.warning('Chat input exceeds token budget uid=%s; returning too-long reply', uid)
        if callback_data is not None:
            callback_data['answer'] = INPUT_TOO_LONG_MESSAGE
            callback_data['memories_found'] = []
            callback_data['ask_for_nps'] = False
        yield None
        return

    if callback_data is not None:
        callback_data.setdefault('route', 'agentic')

    # Setup and post-setup TTFT use separate clocks so multi-second prompt/tool
    # loading cannot silently consume the first-stream-event window.
    gateway_feature_mode = False
    try:
        # Resolve the user's timezone once and reuse it for both the system prompt and the
        # injected datetime block, avoiding a duplicate notification_db lookup per request.
        # These helpers perform Firestore and LangSmith I/O before the producer task exists,
        # so they use the remaining shared setup budget instead of a second full window.
        if setup_deadline_at is None:
            setup_deadline_at = asyncio.get_running_loop().time() + AGENT_STREAM_SETUP_TIMEOUT_SECONDS
        setup_remaining = setup_deadline_at - asyncio.get_running_loop().time()
        if setup_remaining <= 0:
            raise asyncio.TimeoutError()
        async with asyncio.timeout(setup_remaining):
            # Omi-managed chat-agent is always the OpenAI/Luna runner. Anthropic BYOK
            # no longer selects a second Messages path. CHAT_AGENT_ROUTE=direct is
            # honored inside get_llm() as a kill switch onto direct OpenAI.
            gateway_feature_mode = should_route_chat_agent_through_gateway()
            logger.debug('Chat agent live runner=openai gateway_lane=%s', gateway_feature_mode)
            tz = tz or await run_blocking(db_executor, get_user_timezone, uid)
            city = await get_mobile_city(uid, platform) if current_datetime_block is None else None
            jit_conversation_retrieval_enabled = await _resolve_jit_conversation_retrieval(uid)
            system_prompt = await run_blocking(
                db_executor,
                _get_agentic_qa_prompt,
                uid,
                app,
                messages,
                context=context,
                tz=tz,
                platform=platform,
            )
            system_prompt = append_jit_conversation_retrieval_prompt(
                system_prompt, enabled=jit_conversation_retrieval_enabled
            )

            # Get prompt metadata for tracing/versioning
            prompt_name, prompt_commit, prompt_source = None, None, None
            try:
                from utils.observability.langsmith_prompts import get_prompt_metadata

                prompt_name, prompt_commit, prompt_source = get_prompt_metadata()
            except Exception as error:
                logger.error('Could not get prompt metadata error_type=%s', type(error).__name__)

            # Core tools (fixed order). JIT-only tools are withheld unless the
            # server-owned rollout admitted this user; order is preserved. Both
            # branches copy CORE_TOOLS (never mutate it) per the prompt-cache
            # optimization contract.
            core_tools = list(CORE_TOOLS)
            if not jit_conversation_retrieval_enabled:
                core_tools = [tool for tool in core_tools if tool.name not in JIT_ONLY_TOOL_NAMES]

            # Dynamic app tools — exposed directly on the OpenAI/Luna chat-agent lane
            app_tools = []
            try:
                app_tools = await run_blocking(db_executor, load_app_tools, uid)
                if app_tools:
                    logger.info(f"Loaded {len(app_tools)} app tools")
            except Exception as error:
                logger.error('Error loading app tools error_type=%s', type(error).__name__)
    except asyncio.TimeoutError:
        logger.warning(
            'Agent stream timed out before the producer started uid=%s reason=setup_timeout route=agentic', uid
        )
        if callback_data is not None:
            callback_data['error'] = 'setup_timeout'
            # Persist the typed timeout through the normal done: contract so the
            # router does not overwrite it with the generic canned fallback.
            callback_data['answer'] = AGENT_STREAM_TIMEOUT_MESSAGE
        yield f'error: {AGENT_STREAM_TIMEOUT_MESSAGE}'
        yield None
        return
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.error(
            'Agent stream setup failed uid=%s reason=setup_failure route=agentic error_type=%s',
            uid,
            type(error).__name__,
        )
        if callback_data is not None:
            callback_data['error'] = type(error).__name__
            callback_data['answer'] = AGENT_STREAM_FAILURE_MESSAGE
        yield f'error: {AGENT_STREAM_FAILURE_MESSAGE}'
        yield None
        return

    # Emit a client-visible progress event immediately after setup so the SSE
    # body is never silent while waiting for the first model token. This also
    # starts the post-setup first-event clock with a fresh budget.
    first_event_deadline = asyncio.get_running_loop().time() + AGENT_STREAM_FIRST_EVENT_TIMEOUT_SECONDS
    yield f'think: {AGENT_STREAM_SETUP_PROGRESS}'

    # Append app tool awareness to the system prompt. Anthropic discovers deferred app tools
    # through its server-side search tool; the OpenAI-compatible gateway receives those tools
    # directly and must be told to call them by name.
    if app_tools:
        app_names = set()
        for t in app_tools:
            # Tool names are prefixed with app_id; extract the human-readable app name from description
            app_names.add(t.name)
        app_tool_names = ", ".join(sorted(app_names))
        system_prompt += f"""

<available_app_tools>
You have access to additional tools from the user's connected apps. Call the relevant tool directly when the user asks about an external service (e.g. GitHub, Twitter, Slack, Google Calendar, Notion, Shopify, WhatsApp, Splitwise, etc.).

Available app tool names: {app_tool_names}

IMPORTANT: Always call a matching integration tool when relevant. Never tell the user you don't have access to an integration if a matching tool exists above.
</available_app_tools>"""

    # Instruct the model to use fetch_url_tool for any direct URL in the conversation.
    system_prompt += """

<url_fetching_instructions>
You have fetch_url_tool available. When the user shares any URL (starting with http:// or https://), you MUST call fetch_url_tool to read its content before responding. Never say you cannot browse, visit, or read a URL. Always attempt to fetch it first.
</url_fetching_instructions>"""

    # The typed lanes almost never end an answer with a question, so a turn that
    # had an obvious next hop still ends the session. The tail is stripped from
    # the visible text below and delivered as one structured chip instead.
    system_prompt += FOLLOWUP_PROMPT_SECTION

    # Live chat-agent tools are OpenAI chat-completions functions. Perplexity
    # covers web search; Anthropic server tools are not on this lane.
    tool_schemas, tool_registry = _convert_tools(core_tools, app_tools)
    tool_registry = dict(tool_registry)
    tool_registry[perplexity_web_search_tool.name] = perplexity_web_search_tool
    tool_schemas = [*tool_schemas, _langchain_tool_to_openai(perplexity_web_search_tool)]

    # Build the provider-neutral role/content message shape. The current datetime is injected
    # into the user turn (not the system prompt) so the direct Anthropic cache prefix stays stable.
    anthropic_messages = _messages_to_anthropic(messages)
    anthropic_messages = _inject_current_datetime(
        anthropic_messages, current_datetime_block or get_current_datetime_block(uid, tz=tz, location=city)
    )

    callback = AsyncStreamingCallback()

    conversations_collected = []
    evidence_references = []

    safety_guard = AgentSafetyGuard(max_tool_calls=25, max_context_tokens=500000)

    langsmith_run_id = str(uuid.uuid4())

    chat_scope = build_chat_scope(context)

    # Config for tools to access via RunnableConfig
    configurable = {
        "user_id": uid,
        "thread_id": str(uuid.uuid4()),
        **frame_request_runtime_config(messages, chat_session),
        "conversations_collected": conversations_collected,
        "evidence_references": evidence_references,
        "safety_guard": safety_guard,
        "chat_session_id": chat_session.id if chat_session else None,
        "client_kind": client_kind,
        "jit_conversation_retrieval_enabled": jit_conversation_retrieval_enabled,
        "tools": core_tools + app_tools,
        "chat_scope": chat_scope,
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
    # The follow-up tail is model output like any other token. Hold it back from
    # what the user watches stream in so the chip's text never appears twice.
    followup_filter = FollowUpTailStreamFilter()

    def attach_evidence_to_callback() -> None:
        """Expose only the bounded references collected by successful JIT tools."""
        if callback_data is not None and evidence_references:
            callback_data['evidence'] = {
                'schema_version': 1,
                'references': evidence_references[:24],
            }

    # Live path is always the OpenAI-compatible runner (gateway Luna or direct OpenAI).
    agent_runner = _run_openai_agent_stream
    task = asyncio.create_task(
        agent_runner(
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

    def keep_streamed_answer() -> bool:
        """Preserve what already reached the user when the stream stops early.

        The bounded deadline and failure paths cancel the producer, but the
        tokens yielded before that are a real answer the user watched arrive.
        Returns whether there was anything to keep.
        """
        if callback_data is None:
            return False
        streamed, _ = split_followup_tail(''.join(full_response))
        if not streamed:
            return False
        callback_data['answer'] = streamed
        # A turn that stopped early is a failed turn; it never invites a next question.
        callback_data.pop('followup', None)
        callback_data['memories_found'] = conversations_collected if conversations_collected else []
        callback_data['ask_for_nps'] = tool_usage_count > 0
        attach_evidence_to_callback()
        chart_data_from_config = configurable.get('chart_data')
        if chart_data_from_config:
            callback_data['chart_data'] = chart_data_from_config
        return True

    # Stream from callback queue. Setup already emitted a think: progress event for the
    # client, but the first-event clock below still bounds silence from the producer
    # (post-setup TTFT) separately from that setup progress.
    try:
        started_at = asyncio.get_running_loop().time()
        received_first_event = False
        while True:
            remaining_seconds = AGENT_STREAM_MAX_DURATION_SECONDS - (asyncio.get_running_loop().time() - started_at)
            if remaining_seconds <= 0:
                raise asyncio.TimeoutError

            wait_timeout = min(
                (
                    max(0, first_event_deadline - asyncio.get_running_loop().time())
                    if not received_first_event
                    else AGENT_STREAM_PROGRESS_HEARTBEAT_SECONDS
                ),
                remaining_seconds,
            )
            try:
                chunk = await next_stream_chunk(callback, task, wait_timeout)
            except asyncio.TimeoutError:
                # A successful first status/token means the agent can be in a
                # deliberately long tool call (some app tools allow 120s).
                # Keep the proxy/client stream alive until the hard task cap.
                if received_first_event and remaining_seconds > wait_timeout:
                    yield f'think: {AGENT_STREAM_PROGRESS_HEARTBEAT}'
                    continue
                raise
            if chunk is None:
                break

            received_first_event = True
            if chunk.startswith("think: ") and chunk != f'think: {AGENT_STREAM_PROGRESS_HEARTBEAT}':
                tool_usage_count += 1

            if chunk.startswith("data: "):
                visible = followup_filter.push(chunk[len("data: ") :])
                if not visible:
                    continue
                chunk = f'data: {visible}'

            yield chunk

        producer_failure = await task

        held_back = followup_filter.flush()
        if held_back:
            yield f'data: {held_back}'

        # Store results in callback_data
        if callback_data is not None:
            answer_text, followup_question = split_followup_tail(''.join(full_response))
            callback_data['answer'] = answer_text
            if followup_question and not producer_failure:
                callback_data['followup'] = followup_question
            # Reported even though the stream ended cleanly, so the router can tell a failed
            # turn from one the model ended empty on its own.
            if producer_failure:
                callback_data['error'] = producer_failure
            callback_data['memories_found'] = conversations_collected if conversations_collected else []
            callback_data['ask_for_nps'] = tool_usage_count > 0
            attach_evidence_to_callback()
            chart_data_from_config = configurable.get('chart_data')
            if chart_data_from_config:
                callback_data['chart_data'] = chart_data_from_config
            logger.info(f"Collected {len(callback_data['memories_found'])} conversations for citation")

    except asyncio.TimeoutError:
        logger.warning('Agent stream reached its bounded deadline uid=%s reason=idle_timeout route=agentic', uid)
        await cancel_stream_task(task)
        if callback_data is not None:
            callback_data['error'] = 'idle_timeout'
        if keep_streamed_answer():
            yield None
            return
        if callback_data is not None:
            # Persist the typed timeout so the router emits one coherent done: frame
            # instead of a second generic canned sorry bubble.
            callback_data['answer'] = AGENT_STREAM_TIMEOUT_MESSAGE
        yield f'error: {AGENT_STREAM_TIMEOUT_MESSAGE}'
        yield None
        return
    except asyncio.CancelledError:
        await cancel_stream_task(task)
        raise
    except Exception as error:
        logger.error(
            'Agent stream failed uid=%s reason=stream_failure route=agentic error_type=%s',
            uid,
            type(error).__name__,
        )
        await cancel_stream_task(task)
        if callback_data is not None:
            callback_data['error'] = type(error).__name__
        if keep_streamed_answer():
            yield None
            return
        if callback_data is not None:
            callback_data['answer'] = AGENT_STREAM_FAILURE_MESSAGE
        yield f'error: {AGENT_STREAM_FAILURE_MESSAGE}'
        yield None
        return
    finally:
        if not task.done():
            task.cancel()

    yield None  # Signal completion
