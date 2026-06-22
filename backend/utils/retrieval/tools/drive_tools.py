"""
Tools for accessing Google Drive files.
"""

import contextvars
from datetime import datetime, timezone
from typing import Optional, List

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.users as users_db
from utils.retrieval.tools.integration_base import (
    ensure_capped,
    prepare_access,
)

# Import shared Google utilities
from utils.retrieval.tools.google_utils import refresh_google_token, google_api_request
import logging

logger = logging.getLogger(__name__)

# Import the context variable from agentic module
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


async def get_drive_files(
    access_token: str,
    query: Optional[str] = None,
    max_results: int = 10,
) -> List[dict]:
    """
    Fetch files from Google Drive API.

    Args:
        access_token: Google access token
        query: Optional Google Drive search query (e.g., "name contains 'meeting'")
        max_results: Maximum number of files to return

    Returns:
        List of file metadata
    """
    params = {
        'pageSize': min(max_results, 50),
        'fields': 'nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink)',
    }

    if query:
        params['q'] = query

    files = []
    page_token = None

    while True:
        page_params = dict(params)
        if page_token:
            page_params['pageToken'] = page_token

        data = await google_api_request(
            "GET",
            'https://www.googleapis.com/drive/v3/files',
            access_token,
            params=page_params,
        )

        fetched = data.get('files', [])
        files.extend(fetched)

        if len(files) >= max_results:
            files = files[:max_results]
            break

        page_token = data.get('nextPageToken')
        if not page_token:
            break

    return files


@tool
async def search_google_drive_tool(
    query: Optional[str] = None,
    max_results: int = 10,
    config: RunnableConfig = None,
) -> str:
    """
    Search for files in the user's Google Drive.

    Use this tool when:
    - User asks "find my document about X" or "search my drive for Y"
    - User mentions checking their Google Drive

    Query examples:
    - "name contains 'meeting'" - files with 'meeting' in the name
    - "mimeType='application/vnd.google-apps.spreadsheet'" - only spreadsheets
    - "modifiedTime > '2024-01-01T12:00:00'" - files modified after a date
    - "fullText contains 'financial'" - files containing the word 'financial'

    Args:
        query: Optional Google Drive search query.
        max_results: Maximum number of files to return (default: 10, max: 50)

    Returns:
        Formatted list of files.
    """
    uid, integration, access_token, access_err = prepare_access(
        config,
        'google_calendar',
        'Google Drive',
        'Google Drive is not connected. Please connect your Google account from settings.',
        'Google Drive access token not found. Please reconnect your Google account from settings.',
        'Error checking Google Drive connection',
    )
    if access_err:
        return access_err

    try:
        max_results = ensure_capped(max_results, 50, "⚠️ search_google_drive_tool - max_results capped from {} to {}")

        try:
            files = await get_drive_files(access_token, query, max_results)
        except Exception as e:
            error_msg = str(e)
            if "Authentication failed" in error_msg or "401" in error_msg or "token" in error_msg.lower():
                logger.info(f"🔄 Attempting to refresh Google token for Drive...")
                new_token = await refresh_google_token(uid, integration)
                if new_token:
                    files = await get_drive_files(new_token, query, max_results)
                else:
                    return "Google authentication expired. Please reconnect your Google account from settings."
            else:
                return f"Error searching Google Drive: {error_msg}"

        if not files:
            query_info = f" matching '{query}'" if query else ""
            return f"No Google Drive files found{query_info}."

        # Format files
        result = f"Google Drive Files ({len(files)} found):\n\n"

        for i, file in enumerate(files, 1):
            result += f"{i}. {file.get('name', 'Unknown Name')}\n"
            result += f"   Type: {file.get('mimeType', 'Unknown')}\n"
            if 'modifiedTime' in file:
                result += f"   Modified: {file['modifiedTime']}\n"
            if 'webViewLink' in file:
                result += f"   Link: {file['webViewLink']}\n"
            result += "\n"

        return result.strip()
    except Exception as e:
        logger.error(f"❌ Unexpected error in search_google_drive_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error fetching Google Drive files: {str(e)}"
