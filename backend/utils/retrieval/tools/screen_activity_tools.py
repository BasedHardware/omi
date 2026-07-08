"""
Tools for accessing screen/computer activity data from the desktop app.
"""

import contextvars
from datetime import datetime, timezone, tzinfo
from typing import Any, Dict, List, Optional, Tuple, cast
from zoneinfo import ZoneInfo

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from langchain_core.runnables import RunnableConfig

import database.screen_activity as screen_activity_db
import database.vector_db as vector_db
import database.notifications as notification_db
from database._client import db as firestore_db
from utils.llm.clients import gemini_embed_query
import logging

logger = logging.getLogger(__name__)

try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def _agent_config() -> Optional[Dict[str, Any]]:
    """Retrieve the agent config dict from the context var, or None if unset."""
    try:
        return agent_config_context.get()
    except LookupError:
        return None


def _get_uid(config: RunnableConfig) -> Optional[str]:
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()
    if cfg is None:
        return None
    try:
        configurable = cfg.get('configurable')
        if isinstance(configurable, dict):
            conf: Dict[str, Any] = cast(Dict[str, Any], configurable)
            return conf.get('user_id')
        return None
    except (KeyError, TypeError):
        return None


# Bound the chat tool result so a wide-range desktop query ("what did I do last month") cannot
# flood the chat model's context and make it freeze or refuse (issue #4927; the same fix already
# shipped for the conversations, memories, and action items tools). The summary lists every app the
# user touched in the range, each with up to five window titles whose length is uncapped, so a long
# range on a busy machine can run to tens of thousands of characters. Cap the apps shown and the raw
# character size and tell the model to summarize and narrow.
MAX_APPS_FOR_LLM = 50
MAX_RESULT_CHARS = 60000


def _cap_apps_for_llm(apps: List[Tuple[str, Dict[str, Any]]]) -> Tuple[List[Tuple[str, Dict[str, Any]]], bool]:
    """Keep at most ``MAX_APPS_FOR_LLM`` apps for the chat model.

    Apps arrive sorted most-used first, so this keeps the ones that matter. Returns
    ``(capped_list, truncated)`` where ``truncated`` is True when some apps were dropped.
    """
    if len(apps) > MAX_APPS_FOR_LLM:
        return apps[:MAX_APPS_FOR_LLM], True
    return list(apps), False


def _bounded_screen_activity_result(result: str, truncated: bool) -> str:
    """Apply a hard character budget and, when the set was truncated, append a note telling the
    model to summarize what it has and to offer to narrow, so it answers instead of freezing.

    When clipping for size, cut back to the start of the last complete app record so a partial app
    block is never left dangling (each record starts with "**<app>**" on its own line, matching the
    record-boundary clipping the conversations tool uses). If the first (or only) record is itself
    larger than the budget, keep the hard-clipped text so its data is still returned truncated rather
    than dropping every app down to just the summary header.

    The note deliberately does not state a total count: callers may pass an already-paginated
    page whose length is not the true total, so claiming a total would mislead (cubic on #8527).
    """
    if len(result) > MAX_RESULT_CHARS:
        clipped = result[:MAX_RESULT_CHARS]
        first_record = result.find("\n**")  # boundary just before the first app record
        boundary = clipped.rfind("\n**")  # boundary just before the last record that fits
        if boundary > first_record >= 0:
            # A complete record precedes the cut, so drop only the partial trailing record.
            result = clipped[:boundary]
        else:
            # The first (or only) record overflows the budget; keep the hard-clipped text so its
            # data is still returned truncated rather than dropping every app to just the header.
            result = clipped
        truncated = True
    if truncated:
        result += (
            "\n\n[Only the most-used apps are shown here to stay within limits; more may exist. "
            "Summarize what is shown and tell the user they can ask about a specific app or a "
            "narrower date range for the rest.]"
        )
    return result


def _resolve_display_tz(uid: str) -> tzinfo:
    # Render timestamps in the user's timezone so a chat answer shows screen-activity matches in the
    # same timezone as conversation matches (conversation_tools renders in the user's timezone too).
    # Fall back to UTC on any failure: no timezone set, an invalid IANA name, or a Firestore error
    # reading it (a transient lookup error must not fail an otherwise successful search).
    try:
        tz_name = notification_db.get_user_time_zone(uid)
        if tz_name:
            return ZoneInfo(tz_name)
    except Exception:
        logger.warning("search_screen_activity_tool - could not resolve user timezone, using UTC")
    return timezone.utc


@tool
def get_screen_activity_tool(
    start_date: str,
    end_date: str,
    app_filter: Optional[str] = None,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Get a summary of the user's screen/computer activity for a date range.

    Use this for questions like "what did I do on my computer today/this week?" or
    "which apps did I use?". Shows per-app usage time and top window titles.

    Requires the Omi desktop app to be installed and running.

    Args:
        start_date: Start of the range (ISO format with timezone, e.g. "2025-01-15T00:00:00+00:00")
        end_date: End of the range (ISO format with timezone)
        app_filter: Optional app name to filter to a single application

    Returns:
        Formatted summary of screen activity by app.
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

    apps_dict: Dict[str, Dict[str, Any]] = cast(Dict[str, Dict[str, Any]], summary['apps'])
    if not apps_dict:
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
    sorted_apps: List[Tuple[str, Dict[str, Any]]] = sorted(apps_dict.items(), key=lambda x: x[1]['count'], reverse=True)

    if app_filter:
        sorted_apps = [(name, data) for name, data in sorted_apps if name.lower() == app_filter.lower()]
        if not sorted_apps:
            return f"No screen activity found for app '{app_filter}' in this date range."

    # Bound how many apps go to the chat model so a wide date range on a busy machine cannot
    # overflow its context (issue #4927). Apps are already sorted most-used first.
    total_apps = len(sorted_apps)
    sorted_apps, apps_truncated = _cap_apps_for_llm(sorted_apps)
    if apps_truncated:
        result += f"(showing the {len(sorted_apps)} most-used apps of {total_apps})\n\n"

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

    return _bounded_screen_activity_result(result.strip(), apps_truncated)


@tool
def search_screen_activity_tool(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
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

    display_tz = _resolve_display_tz(uid)
    result = f"Found {len(matches)} screen activity matches for '{query}':\n\n"

    for sid in screenshot_ids:
        score = scores_by_id.get(sid, 0)
        app_name = app_by_id.get(sid, 'Unknown')
        ts = ts_by_id.get(sid, 0)
        ts_str = datetime.fromtimestamp(ts, tz=display_tz).strftime('%Y-%m-%d %H:%M:%S') if ts else 'Unknown'

        # Fetch OCR text from Firestore
        ocr_text = ''
        try:
            doc = firestore_db.collection('users').document(uid).collection('screen_activity').document(str(sid)).get()
            if doc.exists:
                doc_data = cast(Dict[str, Any], doc.to_dict())
                ocr_text = doc_data.get('ocrText', '')[:200]
        except Exception:
            pass

        result += f"- **{ts_str}** | {app_name} (relevance: {score:.2f})\n"
        if ocr_text:
            result += f"  Text: {ocr_text}...\n"
        result += "\n"

    return result.strip()
