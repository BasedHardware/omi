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
    callback_data: Optional[Dict[str, Any]] = None,
    chat_session: Optional[ChatSession] = None,
    extra_user_messages: Optional[List["HumanMessage"]] = None,
) -> AsyncGenerator[Optional[str], None]:
    """Handle streaming chat responses for persona-type apps."""
    system_prompt = app.persona_prompt
    formatted_messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]

    # T-020: optional context blocks (sender name, platform, chat type).
    if extra_user_messages:
        formatted_messages.extend(extra_user_messages)

    for msg in messages:
        if msg.sender == "ai":
            formatted_messages.append(AIMessage(content=msg.text))
        else:
            formatted_messages.append(HumanMessage(content=msg.text))

    full_response: List[str] = []

    # LangSmith tracing — only generate a run_id when the API key
    # is configured so callback_data doesn't carry a phantom UUID
    # that submit_langsmith_feedback() would 404 against.
    from utils.observability.langsmith import has_langsmith_api_key, get_chat_tracer_callbacks

    langsmith_run_id = uuid.uuid4() if has_langsmith_api_key() else None

    tracer_callbacks = (
        get_chat_tracer_callbacks(
            run_id=str(langsmith_run_id),
            run_name="chat.persona.stream",
            tags=["chat", "persona", "streaming"],
            metadata={
                "uid": uid,
                "app_id": app.id if app else None,
                "app_name": app.name if app else None,
                "cited": cited,
            },
        )
        if langsmith_run_id is not None
        else []
    )

    # Pass a RunnableConfig to astream() so LangSmith traces get
    # stamped with the run_id. The config dict carries 'callbacks'
    # (tracer wiring) and 'run_id' (trace UUID stamping).
    runnable_kwargs = {
        "config": {
            "callbacks": tracer_callbacks,
            "run_id": langsmith_run_id,
            "tags": ["chat", "persona", "streaming"],
            "metadata": {
                "uid": uid,
                "app_id": app.id if app else None,
                "app_name": app.name if app else None,
                "cited": cited,
            },
        }
    }

    if callback_data is not None and langsmith_run_id is not None:
        callback_data['langsmith_run_id'] = str(langsmith_run_id)

    try:
        llm = get_llm('persona_chat', streaming=True)

        # Use astream() with a RunnableConfig so LangSmith traces get
        # stamped with the run_id. The old agenerate(callbacks=) pattern
        # required AsyncStreamingCallback to implement the full langchain
        # callback protocol (run_inline, on_llm_new_token, ...) — which it
        # didn't. After the upstream langchain_core bump, passing a
        # non-conforming callback crashes. astream() yields chunks directly.
        async for chunk in llm.astream(formatted_messages, **runnable_kwargs):  # type: ignore[arg-type]
            raw = chunk.content if hasattr(chunk, 'content') else str(chunk)
            # LangChain AIMessageChunk.content can be str or list[str|dict]
            token = raw if isinstance(raw, str) else str(raw)
            if token:
                full_response.append(token)
                yield f"data: {token}"

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
