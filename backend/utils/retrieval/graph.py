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
from utils.other.chat_file import FileChatTool
from utils.retrieval.agentic import AsyncStreamingCallback, execute_agentic_chat_stream
from utils.observability.langsmith import (
    get_chat_tracer_callbacks,
    has_langsmith_api_key,
)
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File chat helper
# ---------------------------------------------------------------------------


def _has_file_context(last_message: Optional[Message], chat_session: Optional[ChatSession]) -> bool:
    """Check if the request involves file attachments."""
    if last_message and last_message.files_id and len(last_message.files_id) > 0:
        return chat_session is not None

    if chat_session and chat_session.file_ids and len(chat_session.file_ids) > 0:
        question = last_message.text if last_message else ""
        if question and retrieve_is_file_question(question):
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

    try:
        fc_tool = FileChatTool(uid, chat_session.id)
    except Exception as e:
        logger.error(f"Failed to create FileChatTool: {e}")
        raise

    # Determine which files to use
    if last_message and last_message.files_id and len(last_message.files_id) > 0:
        file_ids = last_message.files_id
    else:
        file_ids = chat_session.file_ids if chat_session.file_ids else []

    logger.info(f"Processing file chat with {len(file_ids)} files")

    callback = AsyncStreamingCallback()

    try:
        # Run the producer as a concurrent task so chunks stream in real-time
        async def _produce() -> str:
            return await fc_tool.process_chat_with_file_stream(question, file_ids, callback=cast(Any, callback))

        task = asyncio.create_task(_produce())

        # Drain the queue concurrently while the producer runs
        while True:
            chunk = await callback.queue.get()
            if chunk:
                yield chunk
            else:
                break

        answer = await task

        if callback_data is not None:
            callback_data['answer'] = answer
            callback_data['memories_found'] = []
            callback_data['ask_for_nps'] = True

        yield None
    except Exception as e:
        logger.error(f"Error in file chat: {e}")
        if callback_data is not None:
            callback_data['error'] = str(e)
        yield None


# ---------------------------------------------------------------------------
# Persona chat (kept on existing LangChain/OpenAI for now)
# ---------------------------------------------------------------------------


async def execute_persona_chat_stream(
    uid: str,
    messages: List[Message],
    app: App,
    cited: Optional[bool] = False,
    callback_data: dict = None,
    chat_session: Optional[str] = None,
    extra_user_messages: Optional[List["HumanMessage"]] = None,
) -> AsyncGenerator[str, None]:
    """Handle streaming chat responses for persona-type apps.

    Uses `LLM.astream()` directly rather than `agenerate(callbacks=...)`
    because the latter requires the callback to implement the full
    langchain callback protocol (run_inline, on_llm_start, ...). Our
    `AsyncStreamingCallback` was originally just a queue and didn't
    implement those hooks, so the previous version produced an empty
    HTTP body (tokens went into the LLM's internal generator and were
    never pushed to the queue). astream() yields chunks as an
    async iterator — we just push each chunk to the SSE consumer.

    `extra_user_messages` (T-020) are HumanMessage instances inserted
    immediately after the persona_prompt SystemMessage and before any
    prior turns. Used by the integration persona-chat route to inject
    sender / platform / chat-type context WITHOUT changing the
    persona_prompt template itself. They are HumanMessage (not
    SystemMessage) because the values come from untrusted chat-platform
    profile fields — a user can set their Telegram first_name to
    anything, including prompt-injection payloads. Demoting to user
    role + framing the values as DATA (see
    routers.integration._render_persona_context_message) means
    attacker-controlled strings cannot override the persona prompt.
    Pass None or an empty list for the existing single-shot desktop flow.
    """
    callback_data: Optional[Dict[str, Any]] = None,
    chat_session: Optional[ChatSession] = None,
) -> AsyncGenerator[Optional[str], None]:
    """Handle streaming chat responses for persona-type apps."""
    system_prompt = app.persona_prompt
    formatted_messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]

    # T-020: optional context blocks (sender name, platform, chat type).
    # Inserted at position 1 so they sit right after the persona_prompt
    # and before any prior turns. Empty list = no-op (preserves existing
    # behavior). HumanMessage role — see prompt-injection note above.
    if extra_user_messages:
        formatted_messages.extend(extra_user_messages)

    for msg in messages:
        if msg.sender == "ai":
            formatted_messages.append(AIMessage(content=msg.text))
        else:
            formatted_messages.append(HumanMessage(content=msg.text))

    full_response: list[str] = []
    full_response: List[str] = []
    callback = AsyncStreamingCallback()
    # Generate run_id for LangSmith tracing
    langsmith_run_id = str(uuid.uuid4())

    # Build a LangSmith tracer for this request so the run_id stored
    # on the ai_message actually maps to a real trace in LangSmith.
    # Without a tracer attached, submit_langsmith_feedback() called
    # later would fail because the run_id never existed.
    #
    # If no API key is configured, the callback list is empty AND we
    # deliberately don't store a fake langsmith_run_id on the message —
    # a phantom run_id would cause feedback submission to error out
    # server-side. Identified by cubic (P2): partial-removal of
    # LangSmith tracing created non-resolvable run IDs.
    langsmith_run_id = str(uuid.uuid4()) if has_langsmith_api_key() else None
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

    if callback_data is not None and langsmith_run_id is not None:
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
        # Use the 'persona_chat' feature (not 'chat_graph') so the QoS
        # model config routes to gpt-4.1-nano (cheap) for non-premium
        # personas, not gpt-4.1-mini (more expensive). The old code
        # used 'chat_graph' by mistake — this was pre-existing.
        llm = get_llm('persona_chat', streaming=True)
        # Wire the tracer via RunnableConfig so the run_id is real in
        # LangSmith. `config` is the v0.2+ way to pass callbacks into
        # astream() — callbacks= was removed in langchain-core >= 0.2.
        #
        # Critical: the run_id MUST be in config (not just passed to
        # the tracer constructor). LangChainTracer.__init__ does NOT
        # accept a run_id — that argument is silently swallowed by
        # **kwargs. RunnableConfig.run_id is what the callback manager
        # reads to stamp the trace, so submit_langsmith_feedback() can
        # later attach feedback to the exact same run. Identified by
        # code-review sub-agent on PR #8531 (cubic-found follow-up).
        astream_kwargs = (
            {"config": {"callbacks": tracer_callbacks, "run_id": langsmith_run_id}}
            if tracer_callbacks and langsmith_run_id
            else {}
        )
        chunk_count = 0
        async for chunk in llm.astream(formatted_messages, **astream_kwargs):
            chunk_count += 1
            token = chunk.content
            if not token:
                continue
            full_response.append(token)
            # CRITICAL: yield with "data: " prefix to match what
            # AsyncStreamingCallback.put_data() produces in the agentic
            # path. Both chat.py and integration.py consumers expect
            # chunks in the format "data: <token>" so they can add
            # the \n\n SSE terminator. Without this prefix, the regular
            # chat route (chat.py) would emit raw tokens that the SSE
            # parser ignores, breaking persona chat on desktop/mobile.
            yield f"data: {token}"
        logger.info(f"persona: astream done, {chunk_count} chunks, {sum(len(c) for c in full_response)} chars")

        if callback_data is not None:
            callback_data['answer'] = ''.join(full_response)
            callback_data['memories_found'] = []
            callback_data['ask_for_nps'] = False

        yield None
        return

    except Exception as e:
        logger.error(f"Error in execute_persona_chat_stream: {e}")
        if callback_data is not None:
            callback_data['error'] = str(e)
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
    callback_data: Dict[str, Any] = {},
    chat_session: Optional[ChatSession] = None,
    context: Optional[PageContext] = None,
    extra_user_messages: Optional[List["HumanMessage"]] = None,
) -> AsyncGenerator[str, None]:
) -> AsyncGenerator[Optional[str], None]:
    """Route chat requests to the appropriate handler.

    - Persona apps -> persona chat (LangChain/OpenAI)
    - File attachments -> file chat (OpenAI Assistants)
    - Everything else -> Anthropic agentic chat (Claude decides whether to use tools)

    `extra_user_messages` (T-020) are forwarded only to the persona
    handler. The agentic / file-chat paths ignore them — those don't use
    a persona_prompt and the context doesn't apply. They carry
    untrusted sender / platform metadata, demoted to user role so
    they can't override the persona prompt via prompt injection (see
    execute_persona_chat_stream for the security rationale).
    """
    logger.info(f'execute_chat_stream app: {app.id if app else "<none>"}')

    # 1. Persona apps
    if app and app.is_a_persona():
        async for chunk in execute_persona_chat_stream(
            uid,
            messages,
            app,
            cited=cited,
            callback_data=callback_data,
            chat_session=chat_session,
            extra_user_messages=extra_user_messages,
        ):
            yield chunk
        return

    # 2. File attachments
    last_msg = messages[-1] if messages else None
    if chat_session is not None and _has_file_context(last_msg, chat_session):
        async for chunk in _execute_file_chat_stream(uid, messages, chat_session, callback_data):
            yield chunk
        return

    # 3. Default: Anthropic agentic chat
    # Claude decides implicitly whether to use tools — no requires_context() needed
    async for chunk in execute_agentic_chat_stream(
        uid, messages, app, callback_data=callback_data, chat_session=chat_session, context=context
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
