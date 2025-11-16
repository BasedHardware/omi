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
    print(f"🔍 search_files_tool called")
    print(f"🔍 question: {question[:100] if len(question) > 100 else question}...")
    print(f"🔍 file_ids param: {file_ids}")

    if config is None:
        print("❌ Config is None")
        return "Configuration error: missing config"

    uid = config['configurable']['user_id']
    chat_session_id = config['configurable'].get('chat_session_id')

    print(f"🔍 uid: {uid}")
    print(f"🔍 chat_session_id: {chat_session_id}")

    if not chat_session_id:
        print("❌ No chat_session_id in config")
        return "No active chat session. Files are not available."

    try:
        # Get session data
        session_data = chat_db.get_chat_session_by_id(uid, chat_session_id)
        print(f"🔍 session_data found: {session_data is not None}")

        if not session_data:
            print("❌ Session data not found in database")
            return "Chat session not found."

        chat_session = ChatSession(**session_data)
        print(f"🔍 chat_session.file_ids: {chat_session.file_ids}")
        print(f"🔍 Number of files in session: {len(chat_session.file_ids) if chat_session.file_ids else 0}")

        # Determine which files to search
        if file_ids and len(file_ids) > 0:
            print(f"🔍 Using specified file_ids: {file_ids}")
            # Use specified files
            # Validate that these files belong to the session
            session_file_ids = set(chat_session.file_ids or [])
            file_ids_to_search = [fid for fid in file_ids if fid in session_file_ids]

            if not file_ids_to_search:
                print(f"❌ None of the specified files are in this session")
                print(f"   Requested: {file_ids}")
                print(f"   Available: {list(session_file_ids)}")
                return "The specified files are not available in this chat session."

            print(f"🔍 Searching {len(file_ids_to_search)} specific files: {file_ids_to_search}")
        else:
            # Use all session files
            print(f"🔍 No specific file_ids provided, using all session files")
            file_ids_to_search = chat_session.file_ids if chat_session.file_ids else []

            if not file_ids_to_search:
                print(f"❌ Session has no files")
                return "No files have been uploaded to this chat session yet. Ask the user to upload files first."

            print(f"🔍 Searching all {len(file_ids_to_search)} files in session: {file_ids_to_search}")

        # Use FileChatTool to query files
        print(f"🔍 Creating FileChatTool for session {chat_session_id}")
        fc_tool = FileChatTool(uid, chat_session_id)
        print(f"🔍 FileChatTool created, calling process_chat_with_file")
        answer = fc_tool.process_chat_with_file(question, file_ids_to_search)
        print(f"🔍 Got answer from FileChatTool, length: {len(answer)} chars")

        return answer

    except ValueError as e:
        print(f"❌ ValueError in search_files_tool: {e}")
        return f"Session error: {str(e)}"
    except Exception as e:
        print(f"❌ Exception in search_files_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"I encountered an error while searching the files. Please try again or rephrase your question."
