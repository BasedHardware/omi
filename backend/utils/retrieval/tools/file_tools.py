"""
File search tools for the agentic chat system.

These tools allow the LLM to search and query files uploaded to chat sessions.
"""

import contextvars
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from typing import List, Optional
import database.chat as chat_db
from models.chat import ChatSession, FileChat, Message
from utils.other.chat_file import FileChatTool
import logging

logger = logging.getLogger(__name__)

# Import agent_config_context for fallback config access
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


@tool
def search_files_tool(question: str, file_ids: Optional[List[str]] = None, config: RunnableConfig = None) -> str:
    """
    Search and ask questions about files attached to the current chat session.
    Use this when the user asks about documents, images, PDFs, or any files they've uploaded.

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

    Returns:
        Answer based on the file contents
    """
    # Get config from parameter or context variable (like other tools do)
    if config is None:
        try:
            config = agent_config_context.get()
            if config:
                logger.info(f"🔧 search_files_tool - got config from context variable")
        except LookupError:
            logger.info(f"❌ search_files_tool - config not found in context variable")
            config = None

    if config is None:
        logger.info(f"❌ search_files_tool - config is None")
        return "Error: Configuration not available"

    try:
        uid = config['configurable'].get('user_id')
        chat_session_id = config['configurable'].get('chat_session_id')
    except (KeyError, TypeError) as e:
        logger.error(f"❌ search_files_tool - error accessing config: {e}")
        import traceback

        traceback.print_exc()
        return f"Error: Configuration error - {str(e)}"

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
        answer = fc_tool.process_chat_with_file(question, file_ids_to_search)

        return answer

    except ValueError as e:
        return f"Session error: {str(e)}"
    except Exception as e:
        import traceback

        logger.error(f"Error in search_files_tool: {e}")
        traceback.print_exc()
        return f"I encountered an error while searching the files. Please try again or rephrase your question."
