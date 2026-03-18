"""
Chat routing — dispatches to persona, file-chat, or agentic paths.

Replaces the previous LangGraph state machine with a simple async router.
Claude decides implicitly whether to use tools, eliminating the need for
the requires_context() LLM classification call.
"""

import uuid
import asyncio
from typing import List, Optional, AsyncGenerator, Tuple

from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

import database.notifications as notification_db
from models.app import App
from models.chat import ChatSession, Message, PageContext
from models.conversation import Conversation
from utils.llm.chat import retrieve_is_file_question
from utils.llm.persona import answer_persona_question_stream
from utils.other.chat_file import FileChatTool
from utils.retrieval.agentic import AsyncStreamingCallback, execute_agentic_chat_stream
from utils.observability.langsmith import get_chat_tracer_callbacks
import logging

logger = logging.getLogger(__name__)

llm_medium_stream = ChatOpenAI(model='gpt-4.1', streaming=True)


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
    callback_data: dict,
) -> AsyncGenerator[str, None]:
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
        answer = fc_tool.process_chat_with_file_stream(question, file_ids, callback=callback)

        # Yield chunks from callback
        while True:
            chunk = await callback.queue.get()
            if chunk:
                yield chunk
            else:
                break

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
) -> AsyncGenerator[str, None]:
    """Handle streaming chat responses for persona-type apps."""
    system_prompt = app.persona_prompt
    formatted_messages = [SystemMessage(content=system_prompt)]

    for msg in messages:
        if msg.sender == "ai":
            formatted_messages.append(AIMessage(content=msg.text))
        else:
            formatted_messages.append(HumanMessage(content=msg.text))

    full_response = []
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

    all_callbacks = [callback] + tracer_callbacks

    run_metadata = {
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
        task = asyncio.create_task(
            llm_medium_stream.agenerate(messages=[formatted_messages], callbacks=all_callbacks, **run_metadata)
        )

        while True:
            try:
                chunk = await callback.queue.get()
                if chunk:
                    token = chunk.replace("data: ", "")
                    full_response.append(token)
                    yield chunk
                else:
                    break
            except asyncio.CancelledError:
                break

        await task

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
    callback_data: dict = {},
    chat_session: Optional[ChatSession] = None,
    context: Optional[PageContext] = None,
) -> AsyncGenerator[str, None]:
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
    if _has_file_context(last_msg, chat_session):
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
    callback_data = {}

    async def _run():
        async for _ in execute_chat_stream(uid, messages, app, cited=cited, callback_data=callback_data):
            pass

    asyncio.run(_run())
    return (
        callback_data.get('answer', ''),
        callback_data.get('ask_for_nps', False),
        callback_data.get('memories_found', []),
    )
