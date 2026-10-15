"""
Chat routing — dispatches every turn to the agentic path.

Replaces the previous LangGraph state machine with a simple async router.
Claude decides implicitly whether to use tools, eliminating the need for
the requires_context() LLM classification call.
"""

from __future__ import annotations

import uuid
import asyncio
from typing import List, Optional, AsyncGenerator, Tuple, Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from models.conversation import Conversation

from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, BaseMessage

from models.app import App
from models.chat import ChatSession, Message, PageContext
from utils.journey_metrics_contract import ClientKind
from utils.llm.chat import get_current_datetime_block, get_user_timezone
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import Features, track_usage
from utils.executors import db_executor, run_blocking
from utils.retrieval.agentic import (
    AGENT_STREAM_FAILURE_MESSAGE,
    AGENT_STREAM_FIRST_EVENT_TIMEOUT_SECONDS,
    AGENT_STREAM_MAX_DURATION_SECONDS,
    AGENT_STREAM_PROGRESS_HEARTBEAT,
    AGENT_STREAM_PROGRESS_HEARTBEAT_SECONDS,
    AGENT_STREAM_SETUP_TIMEOUT_SECONDS,
    AGENT_STREAM_TIMEOUT_MESSAGE,
    AsyncStreamingCallback,
    cancel_stream_task,
    execute_agentic_chat_stream,
    get_mobile_city,
    next_stream_chunk,
)
from utils.observability.langsmith import get_chat_tracer_callbacks
import logging

logger = logging.getLogger(__name__)


async def _current_prompt_metadata(
    uid: str, platform: Optional[str], client_tz: Optional[str] = None
) -> tuple[str, str]:
    try:
        tz = client_tz or await run_blocking(db_executor, get_user_timezone, uid)
        city = await get_mobile_city(uid, platform)
        return get_current_datetime_block(uid, tz=tz, location=city), tz
    except Exception as error:
        logger.warning('Prompt metadata unavailable error_type=%s', type(error).__name__)
        return get_current_datetime_block(uid, tz='UTC'), 'UTC'


def _with_prompt_metadata(text: str, metadata: str) -> str:
    return f'{metadata}\n\n{text}'


async def _drain_chat_callback(
    callback: AsyncStreamingCallback, task: asyncio.Task, *, route: str
) -> AsyncGenerator[str | None, None]:
    """Drain a callback queue without allowing its producer to strand an SSE response."""
    started_at = asyncio.get_running_loop().time()
    received_first_event = False
    try:
        while True:
            remaining_seconds = AGENT_STREAM_MAX_DURATION_SECONDS - (asyncio.get_running_loop().time() - started_at)
            if remaining_seconds <= 0:
                raise asyncio.TimeoutError

            wait_timeout = min(
                (
                    AGENT_STREAM_FIRST_EVENT_TIMEOUT_SECONDS
                    if not received_first_event
                    else AGENT_STREAM_PROGRESS_HEARTBEAT_SECONDS
                ),
                remaining_seconds,
            )
            try:
                chunk = await next_stream_chunk(callback, task, wait_timeout)
            except asyncio.TimeoutError:
                if received_first_event and remaining_seconds > wait_timeout:
                    yield f'think: {AGENT_STREAM_PROGRESS_HEARTBEAT}'
                    continue
                raise

            if chunk is None:
                await task
                return

            received_first_event = True
            yield chunk
    except asyncio.TimeoutError:
        logger.warning('%s chat stream reached its bounded deadline', route)
        await cancel_stream_task(task)
        yield f'error: {AGENT_STREAM_TIMEOUT_MESSAGE}'
    except asyncio.CancelledError:
        await cancel_stream_task(task)
        raise
    except Exception as error:
        logger.error('%s chat stream failed error_type=%s', route, type(error).__name__)
        await cancel_stream_task(task)
        yield f'error: {AGENT_STREAM_FAILURE_MESSAGE}'
    finally:
        if not task.done():
            task.cancel()


# ---------------------------------------------------------------------------
# Persona chat (kept on existing LangChain/OpenAI for now)
# ---------------------------------------------------------------------------


async def execute_persona_chat_stream(
    uid: str,
    messages: List[Message],
    app: App,
    cited: Optional[bool] = False,
    callback_data: Optional[Dict[str, Any]] = None,
    chat_session: Optional[ChatSession] = None,
    current_datetime_block: Optional[str] = None,
) -> AsyncGenerator[Optional[str], None]:
    """Handle streaming chat responses for persona-type apps."""
    if callback_data is not None:
        callback_data.setdefault('route', 'persona')
    system_prompt = app.persona_prompt
    formatted_messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]

    for index, msg in enumerate(messages):
        if msg.sender == "ai":
            formatted_messages.append(AIMessage(content=msg.text))
        else:
            text = msg.text
            if current_datetime_block and index == len(messages) - 1:
                text = _with_prompt_metadata(text, current_datetime_block)
            formatted_messages.append(HumanMessage(content=text))

    full_response: List[str] = []
    callback = AsyncStreamingCallback()

    # Generate run_id for LangSmith tracing
    langsmith_run_id = str(uuid.uuid4())

    tracer_callbacks = get_chat_tracer_callbacks(
        run_id=langsmith_run_id,
        run_name="chat.persona.stream",
        tags=["chat", "persona", "streaming"],
        metadata={
            "uid": uid,
            "app_id": app.id if app else None,
            "app_name": app.name if app else None,
            "cited": cited,
        },
    )

    all_callbacks: List[Any] = [callback] + tracer_callbacks

    run_metadata: Dict[str, Any] = {
        "run_id": langsmith_run_id,
        "run_name": "chat.persona.stream",
        "tags": ["chat", "persona", "streaming"],
        "metadata": {
            "uid": uid,
            "app_id": app.id if app else None,
            "app_name": app.name if app else None,
            "cited": cited,
        },
    }

    if callback_data is not None:
        callback_data['langsmith_run_id'] = langsmith_run_id

    try:
        with track_usage(uid, Features.CHAT):
            task = asyncio.create_task(
                get_llm('chat_graph', streaming=True).agenerate(
                    messages=[formatted_messages], callbacks=all_callbacks, **run_metadata
                )
            )

        async for chunk in _drain_chat_callback(callback, task, route='persona'):
            if chunk and chunk.startswith('error: '):
                if callback_data is not None:
                    callback_data['error'] = 'stream_failure'
                    callback_data['answer'] = chunk[len('error: ') :]
                yield chunk
                yield None
                return
            if chunk:
                if chunk.startswith("data: "):
                    full_response.append(chunk.removeprefix("data: "))
                yield chunk

        await task

        if callback_data is not None:
            callback_data['answer'] = ''.join(full_response)
            callback_data['memories_found'] = []
            callback_data['ask_for_nps'] = False

        yield None
        return

    except Exception as error:
        logger.error('persona chat stream failed error_type=%s', type(error).__name__)
        if callback_data is not None:
            callback_data['error'] = 'stream_failure'
            callback_data['answer'] = AGENT_STREAM_FAILURE_MESSAGE
        yield f'error: {AGENT_STREAM_FAILURE_MESSAGE}'
        yield None
        return


# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------


async def execute_chat_stream(
    uid: str,
    messages: List[Message],
    app: Optional[App] = None,
    cited: Optional[bool] = False,
    callback_data: Optional[Dict[str, Any]] = None,
    chat_session: Optional[ChatSession] = None,
    context: Optional[PageContext] = None,
    platform: Optional[str] = None,
    client_kind: Optional[ClientKind] = None,
    client_tz: Optional[str] = None,
    device_tool_names: Optional[set] = None,
    shaped_invocation: bool = False,
) -> AsyncGenerator[Optional[str], None]:
    """Route chat requests to the agentic chat handler.

    All selected apps (chat and persona capable) run through the same agentic
    stream; the selected app's personality text is applied inside the shared
    system prompt rather than replacing it.
    """
    if callback_data is None:
        callback_data = {}
    logger.info(f'execute_chat_stream app: {app.id if app else "<none>"}')
    # One absolute setup deadline covers router metadata and agentic prompt/tool
    # load so the SSE body cannot stay silent for two stacked 25s budgets.
    setup_deadline_at = asyncio.get_running_loop().time() + AGENT_STREAM_SETUP_TIMEOUT_SECONDS
    try:
        async with asyncio.timeout(max(0.0, setup_deadline_at - asyncio.get_running_loop().time())):
            current_datetime_block, tz = await _current_prompt_metadata(uid, platform, client_tz=client_tz)
    except TimeoutError:
        logger.error(
            'chat stream setup timed out route=router uid=%s reason=setup_timeout',
            uid,
        )
        callback_data['error'] = 'setup_timeout'
        callback_data['route'] = 'router'
        callback_data['answer'] = AGENT_STREAM_TIMEOUT_MESSAGE
        yield f'error: {AGENT_STREAM_TIMEOUT_MESSAGE}'
        yield None
        return

    # Persona apps previously took a dedicated LangChain/OpenAI stream; every
    # turn now keeps the shared prompt, history and tools so a selected persona
    # cannot drop tool, memory, or file access.
    async for chunk in execute_agentic_chat_stream(
        uid,
        messages,
        app,
        callback_data=callback_data,
        chat_session=chat_session,
        context=context,
        platform=platform,
        client_kind=client_kind,
        current_datetime_block=current_datetime_block,
        tz=tz,
        setup_deadline_at=setup_deadline_at,
        device_tool_names=device_tool_names,
        shaped_invocation=shaped_invocation,
    ):
        yield chunk


# Backward compatibility aliases
execute_graph_chat_stream = execute_chat_stream


def execute_graph_chat(
    uid: str, messages: List[Message], app: Optional[App] = None, cited: Optional[bool] = False
) -> Tuple[str, bool, List[Conversation]]:
    """Synchronous chat execution (backward compatibility).

    Runs the streaming chat and collects the result.
    """
    callback_data: Dict[str, Any] = {}

    async def _run():
        async for _ in execute_chat_stream(uid, messages, app, cited=cited, callback_data=callback_data):
            pass

    asyncio.run(_run())
    return (
        callback_data.get('answer', ''),
        callback_data.get('ask_for_nps', False),
        callback_data.get('memories_found', []),
    )
