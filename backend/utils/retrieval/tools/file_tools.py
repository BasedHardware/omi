"""
File search tools for the agentic chat system.

These tools allow the LLM to search and query files uploaded to chat sessions.
"""

import contextvars
from collections.abc import Mapping
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from typing import Any, Dict, List, Optional, cast
import database.chat as chat_db
from models.chat import ChatSession
from utils.other.chat_file import FileChatTool, ProviderRejectedChatFileError
import logging

logger = logging.getLogger(__name__)

# Request fields this tool's provider call constructs (chat_file._ask_files /
# _ask_files_stream). A provider 400 naming one of them is a deployment fault
# (bad model id, unsupported token budget, malformed message schema), not the
# user's attachment. Both OpenAI's nested ``error.param``/``error.code`` body
# and flat gateway bodies are honored, mirroring is_gateway_model_not_found.
_REQUEST_FIELD_400_MARKERS = ('model', 'messages', 'max_completion_tokens', 'stream')
_REQUEST_SHAPE_400_CODES = frozenset({'model_not_found'})
# Gateway-normalized provider rejections (llm_gateway/gateway/schemas.py) that
# name a field the request itself constructs — including options the gateway
# injects on the file-chat lanes (reasoning_effort). The gateway allowlists
# these params, so this stays a closed set (no upstream body strings).
_REQUEST_SHAPE_PROVIDER_REJECTIONS = frozenset(
    {
        'model_not_found',
        'invalid_model',
        'invalid_messages',
        'invalid_output_limit',
        'invalid_stream',
        'invalid_reasoning_effort',
        'unsupported_model',
        'unsupported_messages',
        'unsupported_output_limit',
        'unsupported_stream',
        'unsupported_reasoning_effort',
    }
)
# Param paths ending in an attachment reference are about the user's file
# (stale file_id, unreadable image), even though they live under ``messages``.
_ATTACHMENT_PARAM_SUFFIXES = (
    '.file.file_id',
    '.file',
    '.file_id',
    '.image_url',
    '.image_url.url',
)


def _names_request_field(param: object, code: object, provider_rejection: object = None) -> bool:
    """Whether one (param, code, provider_rejection) triple from a provider 400 names our request shape."""
    if code in _REQUEST_SHAPE_400_CODES:
        return True
    if provider_rejection in _REQUEST_SHAPE_PROVIDER_REJECTIONS:
        return True
    if not isinstance(param, str) or not param:
        return False
    if param.endswith(_ATTACHMENT_PARAM_SUFFIXES):
        return False
    return any(
        param == marker or param.startswith(f'{marker}.') or param.startswith(f'{marker}[')
        for marker in _REQUEST_FIELD_400_MARKERS
    )


def _provider_400_names_request_field(cause: object) -> bool:
    """Whether a ProviderRejectedChatFileError's cause 400 is about our request shape."""
    if cause is None:
        return False
    pairs: list[tuple[object, object, object]] = [(getattr(cause, 'param', None), getattr(cause, 'code', None), None)]
    body = getattr(cause, 'body', None)
    if isinstance(body, Mapping):
        nested = body.get('error')
        if isinstance(nested, Mapping):
            pairs.append((nested.get('param'), nested.get('code'), nested.get('provider_rejection')))
        pairs.append((body.get('param'), body.get('code'), body.get('provider_rejection')))
    return any(_names_request_field(param, code, rejection) for param, code, rejection in pairs)


# Import agent_config_context for fallback config access
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def _agent_config() -> Optional[Dict[str, Any]]:
    """Retrieve the agent config dict from the context var, or None if unset."""
    try:
        return agent_config_context.get()
    except LookupError:
        return None


@tool
def search_files_tool(
    question: str,
    file_ids: Optional[List[str]] = None,
    start_seconds: Optional[float] = None,
    end_seconds: Optional[float] = None,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Search and ask questions about files attached to the current chat session.
    Use this when the user asks about documents, images, videos, PDFs, or any files they've uploaded.

    A video is stored as one numbered image of a few frames plus its audio transcript. To look
    closer at part of a video (what happened at 0:12, a detail that changes), pass
    start_seconds and end_seconds; that answers from up to six frames inside the span.

    The conversation history shows which files are attached to which messages in the format:
    [Files attached: X file(s), IDs: file_id_1, file_id_2, ...]

    You can specify which files to search by providing their IDs, or omit file_ids to search all files.

    Examples:
    - User asks "what does the document say?" → Use file_ids from the most recent message with files
    - User asks "compare the two PDFs I uploaded" → Use file_ids from messages with PDFs
    - User asks "summarize all my files" → Don't specify file_ids (searches all)

    Args:
        question: The specific question to ask about the files
        file_ids: Optional list of specific file IDs to search. If not provided, searches all session files.
        start_seconds: Optional start of a video span to look at closely.
        end_seconds: Optional end of that span (defaults to start_seconds + 5).

    Returns:
        Answer based on the file contents
    """
    # Get config from parameter or context variable (like other tools do)
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()
        if cfg:
            logger.info(f"🔧 search_files_tool - got config from context variable")

    if cfg is None:
        logger.info(f"❌ search_files_tool - config is None")
        return "Error: Configuration not available"

    try:
        configurable: Any = cfg.get('configurable')
        uid = configurable.get('user_id')
        chat_session_id = configurable.get('chat_session_id')
    except (KeyError, TypeError, AttributeError) as e:
        logger.error("❌ search_files_tool - error accessing config: %s", type(e).__name__)
        return "Error: Configuration error"

    if not chat_session_id:
        return "No active chat session. Files are not available."

    try:
        # Get session data
        session_data = chat_db.get_chat_session_by_id(uid, chat_session_id)

        if not session_data:
            return "Chat session not found."

        chat_session = ChatSession(**session_data)

        # Determine which files to search
        if file_ids and len(file_ids) > 0:
            # Use specified files
            # Validate that these files belong to the session
            session_file_ids = set(chat_session.file_ids or [])
            file_ids_to_search = [fid for fid in file_ids if fid in session_file_ids]

            if not file_ids_to_search:
                return "The specified files are not available in this chat session."
        else:
            # Use all session files
            file_ids_to_search = chat_session.file_ids if chat_session.file_ids else []

            if not file_ids_to_search:
                return "No files have been uploaded to this chat session yet. Ask the user to upload files first."

        # Use FileChatTool to query files
        fc_tool = FileChatTool(uid, chat_session_id)
        video_window = None
        if start_seconds is not None or end_seconds is not None:
            start = max(0.0, float(start_seconds if start_seconds is not None else max(0.0, (end_seconds or 0) - 5)))
            end = max(start, float(end_seconds if end_seconds is not None else start + 5))
            video_window = (start, end)
        answer = fc_tool.process_chat_with_file(question, file_ids_to_search, video_window)

        return answer

    except ProviderRejectedChatFileError as error:
        # Provider 4xx on the user's file (chat_file.py:_reraise_provider_file_error).
        # That is unreadable input, not a server fault. Logging the traceback at
        # ERROR makes Cloud Error Reporting group the raise site as an outage.
        cause = error.__cause__
        if _provider_400_names_request_field(cause):
            # A 400 naming a field our request constructs (model id, token budget,
            # message schema) is a deployment fault, not a bad attachment. Keep
            # error-level reporting with the traceback so the regression surfaces
            # in Cloud Error Reporting instead of masquerading as a rejected file.
            logger.error(
                "search_files_tool rejected by provider for request shape cause_type=%s status=%s",
                type(cause).__name__ if cause is not None else "none",
                getattr(cause, "status_code", None),
                exc_info=error,
            )
            return "I encountered an error while searching the files. Please try again or rephrase your question."
        logger.warning(
            "search_files_tool provider rejected the file cause_type=%s status=%s",
            type(cause).__name__ if cause is not None else "none",
            getattr(cause, "status_code", None),
        )
        return "The file could not be processed."
    except ValueError as e:
        logger.error("search_files_tool session error (%s)", type(e).__name__)
        return "Session error: Invalid session parameters."
    except Exception as e:
        logger.error(
            "Error in search_files_tool (%s)",
            type(e).__name__,
            exc_info=True,
        )
        return "I encountered an error while searching the files. Please try again or rephrase your question."
