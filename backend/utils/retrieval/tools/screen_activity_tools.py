"""
Tools for accessing screen/computer activity data from the desktop app.
"""

import contextvars
from datetime import datetime
from typing import Optional

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.screen_activity as screen_activity_db
import database.vector_db as vector_db
from database._client import db as firestore_db
from utils.llm.clients import gemini_embed_query
import logging

logger = logging.getLogger(__name__)

try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def _get_uid(config: RunnableConfig) -> Optional[str]:
    if config is None:
        try:
            config = agent_config_context.get()
        except LookupError:
            return None
    if config is None:
        return None
    try:
        return config['configurable'].get('user_id')
    except (KeyError, TypeError):
        return None


@tool
def get_screen_activity_tool(
    start_date: str,
    end_date: str,
    app_filter: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Get screen/computer activity for a date range — shows which apps were used, for how long, and what the user was working on.

    Use this tool when the user asks about their computer usage, screen time, or what they were doing on their computer.

    **When to use:**
    - "What did I do on my computer yesterday?"
    - "What apps did I use today?"
    - "How much time did I spend in Chrome?"
    - "Show me my screen activity for last week"

    **When NOT to use:**
    - Questions about conversations or what they said (use get_conversations_tool)
    - Questions about memories/facts (use get_memories_tool)
    - Specific content search like "when was I looking at spreadsheets" (use search_screen_activity_tool)

    Args:
        start_date: Start of date range (ISO format with timezone: YYYY-MM-DDTHH:MM:SS+HH:MM)
        end_date: End of date range (ISO format with timezone: YYYY-MM-DDTHH:MM:SS+HH:MM)
        app_filter: Optional app name to filter by (exact match, e.g. "Google Chrome", "Slack")

    Returns:
        Formatted markdown summary of app usage with time estimates and window titles.
    """
    logger.info(
        f"get_screen_activity_tool called - start_date={start_date}, end_date={end_date}, app_filter={app_filter}"
    )

    uid = _get_uid(config)
    if not uid:
        return "Error: User ID not found in configuration"

    try:
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    except ValueError as e:
        return f"Error: Invalid date format. Use YYYY-MM-DDTHH:MM:SS+HH:MM. Details: {e}"

    summary = screen_activity_db.get_screen_activity_summary(uid, start_date=start_dt, end_date=end_dt)

    if not summary['apps']:
        return (
            "No screen activity data available for this date range. "
            "The user may not have the Omi desktop app installed, or it wasn't running during this period."
        )

    # Format output
    total = summary['total_screenshots']
    # Each screenshot is ~3 seconds apart
    total_minutes = (total * 3) // 60

    result = f"Screen Activity Summary ({total} screenshots, ~{total_minutes} min total):\n\n"

    # Sort apps by count descending
    sorted_apps = sorted(summary['apps'].items(), key=lambda x: x[1]['count'], reverse=True)

    if app_filter:
        sorted_apps = [(name, data) for name, data in sorted_apps if name.lower() == app_filter.lower()]
        if not sorted_apps:
            return f"No screen activity found for app '{app_filter}' in this date range."

    for app_name, data in sorted_apps:
        count = data['count']
        minutes = (count * 3) // 60
        titles = data.get('window_titles', [])
        first = data.get('first_seen', '')
        last = data.get('last_seen', '')

        result += f"**{app_name}** — ~{minutes} min ({count} screenshots)\n"
        if first and last:
            result += f"  Active: {first} to {last}\n"
        if titles:
            result += f"  Top windows: {', '.join(titles[:5])}\n"
        result += "\n"

    return result.strip()


@tool
def search_screen_activity_tool(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    config: RunnableConfig = None,
) -> str:
    """
    Semantic search across the user's screen/computer activity using AI embeddings.

    Finds screenshots where the on-screen text matches the query, even without exact keyword matches.

    **When to use:**
    - "When was I last working on the budget spreadsheet?"
    - "Find when I was looking at that Python error"
    - "When did I last use Figma for the landing page design?"
    - "Show me when I was reading about machine learning"

    **When NOT to use:**
    - General "what did I do" questions (use get_screen_activity_tool)
    - Questions about spoken conversations (use search_conversations_tool)

    Args:
        query: Natural language description of what to search for in screen content
        start_date: Optional start date filter (ISO format with timezone)
        end_date: Optional end date filter (ISO format with timezone)
        limit: Number of results to return (default 10, max 20)

    Returns:
        Matching screen activity entries with timestamps, app names, and text snippets.
    """
    logger.info(f"search_screen_activity_tool called - query='{query}', start_date={start_date}, end_date={end_date}")

    uid = _get_uid(config)
    if not uid:
        return "Error: User ID not found in configuration"

    limit = min(limit, 20)

    # Parse optional date filters to unix timestamps
    start_ts = None
    end_ts = None
    if start_date:
        try:
            start_ts = int(datetime.fromisoformat(start_date.replace('Z', '+00:00')).timestamp())
        except ValueError:
            pass
    if end_date:
        try:
            end_ts = int(datetime.fromisoformat(end_date.replace('Z', '+00:00')).timestamp())
        except ValueError:
            pass

    try:
        query_vector = gemini_embed_query(query)
    except Exception as e:
        logger.error(f"search_screen_activity_tool - embedding error: {e}")
        return f"Error generating search embedding: {e}"

    matches = vector_db.search_screen_activity_vectors(
        uid=uid,
        query_vector=query_vector,
        start_date=start_ts,
        end_date=end_ts,
        k=limit,
    )

    if not matches:
        return (
            f"No screen activity found matching '{query}'. "
            "The user may not have the Omi desktop app installed, or no matching content was captured."
        )

    # Fetch full metadata from Firestore for matched screenshot IDs
    screenshot_ids = [m['screenshot_id'] for m in matches]
    scores_by_id = {m['screenshot_id']: m['score'] for m in matches}
    app_by_id = {m['screenshot_id']: m.get('appName', '') for m in matches}
    ts_by_id = {m['screenshot_id']: m.get('timestamp', 0) for m in matches}

    result = f"Found {len(matches)} screen activity matches for '{query}':\n\n"

    for sid in screenshot_ids:
        score = scores_by_id.get(sid, 0)
        app_name = app_by_id.get(sid, 'Unknown')
        ts = ts_by_id.get(sid, 0)
        ts_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else 'Unknown'

        # Fetch OCR text from Firestore
        ocr_text = ''
        try:
            doc = firestore_db.collection('users').document(uid).collection('screen_activity').document(str(sid)).get()
            if doc.exists:
                doc_data = doc.to_dict()
                ocr_text = doc_data.get('ocrText', '')[:200]
        except Exception:
            pass

        result += f"- **{ts_str}** | {app_name} (relevance: {score:.2f})\n"
        if ocr_text:
            result += f"  Text: {ocr_text}...\n"
        result += "\n"

    return result.strip()
