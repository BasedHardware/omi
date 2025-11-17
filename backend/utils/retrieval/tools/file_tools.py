"""
File search tools for the agentic chat system.

These tools allow the LLM to search and query files uploaded to chat sessions.
"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from typing import List, Optional
import database.chat as chat_db
from models.chat import ChatSession, FileChat
from utils.other.chat_file import FileChatTool


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
    if config is None:
        print(f"❌ Configuration error: missing config")
        return "Configuration error: missing config"

    uid = config['configurable']['user_id']
    chat_session_id = config['configurable'].get('chat_session_id')

    if not chat_session_id:
        print(f"❌ No active chat session")
        return "No active chat session. Files are not available."

    try:
        # Get session data
        session_data = chat_db.get_chat_session_by_id(uid, chat_session_id)

        if not session_data:
            print(f"❌ Chat session not found")
            return "Chat session not found."

        chat_session = ChatSession(**session_data)

        # Determine which files to search
        if file_ids and len(file_ids) > 0:
            # Use specified files
            # Validate that these files belong to the session
            session_file_ids = set(chat_session.file_ids or [])
            file_ids_to_search = [fid for fid in file_ids if fid in session_file_ids]

            if not file_ids_to_search:
                print(f"❌ No valid files found in session")
                return "The specified files are not available in this chat session."
        else:
            # Use all session files
            file_ids_to_search = chat_session.file_ids if chat_session.file_ids else []

            if not file_ids_to_search:
                print(f"❌ No files uploaded to session")
                return "No files have been uploaded to this chat session yet. Ask the user to upload files first."

        # Use FileChatTool to query files
        fc_tool = FileChatTool(uid, chat_session_id)
        answer = fc_tool.process_chat_with_file(question, file_ids_to_search)

        return answer

    except ValueError as e:
        print(f"❌ ValueError: {str(e)}")
        return f"Session error: {str(e)}"
    except Exception as e:
        print(f"❌ Exception in search_files_tool: {str(e)}")
        import traceback

        print(f"❌ Traceback: {traceback.format_exc()}")
        return (
            f"I encountered an error while searching the files: {str(e)}. Please try again or rephrase your question."
        )
