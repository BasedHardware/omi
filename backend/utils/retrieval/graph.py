"""
Chat routing — dispatches to persona, file-chat, or agentic paths.

Replaces the previous LangGraph state machine with a simple async router.
Claude decides implicitly whether to use tools, eliminating the need for
the requires_context() LLM classification call.
"""

from __future__ import annotations

import uuid
import asyncio
from typing import List, Optional, AsyncGenerator, Tuple, Any, Dict, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from models.conversation import Conversation

from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, BaseMessage

from models.app import App
from models.chat import ChatSession, Message, PageContext
from utils.llm.chat import retrieve_is_file_question
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import Features, track_usage
from utils.executors import db_executor, llm_executor, run_blocking
from utils.other.chat_file import FileChatTool
from utils.retrieval.agentic import (
    AGENT_STREAM_FAILURE_MESSAGE,
    AGENT_STREAM_FIRST_EVENT_TIMEOUT_SECONDS,
    AGENT_STREAM_MAX_DURATION_SECONDS,
    AGENT_STREAM_PROGRESS_HEARTBEAT,
    AGENT_STREAM_PROGRESS_HEARTBEAT_SECONDS,
    AGENT_STREAM_TIMEOUT_MESSAGE,
    AsyncStreamingCallback,
    cancel_stream_task,
    execute_agentic_chat_stream,
    next_stream_chunk,
)
from utils.observability.langsmith import get_chat_tracer_callbacks
import logging

logger = logging.getLogger(__name__)


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
# File chat helper
# ---------------------------------------------------------------------------


async def _has_file_context(last_message: Optional[Message], chat_session: Optional[ChatSession]) -> bool:
    """Check if the request involves file attachments."""
    if last_message and last_message.files_id and len(last_message.files_id) > 0:
        return chat_session is not None

    if chat_session and chat_session.file_ids and len(chat_session.file_ids) > 0:
        question = last_message.text if last_message else ""
        # retrieve_is_file_question runs a synchronous ~1-2s LLM inference; offload it so it
        # doesn't block the event loop while execute_chat_stream's async generator is driven
        # on the loop by StreamingResponse.
        if question and await run_blocking(llm_executor, retrieve_is_file_question, question):
            return True

    return False


async def _execute_file_chat_stream(
    uid: str,
    messages: List[Message],
    chat_session: ChatSession,
    callback_data: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[Optional[str], None]:
    """Handle file chat with streaming."""
    last_message = messages[-1] if messages else None
    question = last_message.text if last_message else ""

    # Determine which files to use
    if last_message and last_message.files_id and len(last_message.files_id) > 0:
        file_ids = last_message.files_id
    else:
        file_ids = chat_session.file_ids if chat_session.file_ids else []

    logger.info(f"Processing file chat with {len(file_ids)} files")

    callback = AsyncStreamingCallback()

    try:
        # The constructor reads Firestore synchronously, so it belongs inside
        # the supervised producer as well. That starts the first-event deadline
        # before any blocking file-chat setup can hold the event loop.
        async def _produce() -> str:
            fc_tool = await run_blocking(db_executor, FileChatTool, uid, chat_session.id)
            return await fc_tool.process_chat_with_file_stream(question, file_ids, callback=cast(Any, callback))

        task = asyncio.create_task(_produce())

        async for chunk in _drain_chat_callback(callback, task, route='file'):
            if chunk and chunk.startswith('error: '):
                if callback_data is not None:
                    callback_data['error'] = 'stream_failure'
                yield chunk
                return
            if chunk:
                yield chunk

        answer = await task

        if callback_data is not None:
            callback_data['answer'] = answer
            callback_data['memories_found'] = []
            callback_data['ask_for_nps'] = True

        yield None
    except Exception as error:
        logger.error('file chat stream failed error_type=%s', type(error).__name__)
        if callback_data is not None:
            callback_data['error'] = 'stream_failure'
        yield f'error: {AGENT_STREAM_FAILURE_MESSAGE}'


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
) -> AsyncGenerator[Optional[str], None]:
    """Handle streaming chat responses for persona-type apps."""
    system_prompt = app.persona_prompt
    formatted_messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]

    for msg in messages:
        if msg.sender == "ai":
            formatted_messages.append(AIMessage(content=msg.text))
        else:
            formatted_messages.append(HumanMessage(content=msg.text))

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
                yield chunk
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
        yield f'error: {AGENT_STREAM_FAILURE_MESSAGE}'
        return


# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------


async def execute_chat_stream(
    uid: str,
    messages: List[Message],
    app: Optional[App] = None,
    cited: Optional[bool] = False,
    callback_data: Dict[str, Any] = {},
    chat_session: Optional[ChatSession] = None,
    context: Optional[PageContext] = None,
    platform: Optional[str] = None,
) -> AsyncGenerator[Optional[str], None]:
    """Route chat requests to the appropriate handler.

    - Persona apps -> persona chat (LangChain/OpenAI)
    - File attachments -> file chat (OpenAI Assistants)
    - Everything else -> Anthropic agentic chat (Claude decides whether to use tools)
    """
    logger.info(f'execute_chat_stream app: {app.id if app else "<none>"}')

    # 1. Persona apps
    if app and app.is_a_persona():
        async for chunk in execute_persona_chat_stream(
            uid, messages, app, cited=cited, callback_data=callback_data, chat_session=chat_session
        ):
            yield chunk
        return

    # 2. File attachments
    last_msg = messages[-1] if messages else None
    if chat_session is not None and await _has_file_context(last_msg, chat_session):
        async for chunk in _execute_file_chat_stream(uid, messages, chat_session, callback_data):
            yield chunk
        return

    # 3. Default: Anthropic agentic chat
    # Claude decides implicitly whether to use tools — no requires_context() needed
    async for chunk in execute_agentic_chat_stream(
        uid, messages, app, callback_data=callback_data, chat_session=chat_session, context=context, platform=platform
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
