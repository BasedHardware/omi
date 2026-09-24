"""Remaining read-side tool handlers: X posts, goals, chat, people, screen, daily summaries."""

from typing import Any, Dict, List, Optional

from google.api_core.exceptions import FailedPrecondition

import database.chat as chat_db
import database.daily_summaries as daily_summaries_db
import database.goals as goals_db
import database.screen_activity as screen_activity_db
import database.users as users_db
import database.vector_db as vector_db
import database.x_posts as x_posts_db
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.mcp_data import clean_chat_message, clean_person, clean_screen_activity_row, end_of_day_utc
from utils.mcp_memories import parse_mcp_bool, parse_mcp_int
from utils.mcp_server.errors import ToolExecutionError, raise_screen_activity_index_error
from utils.mcp_server.helpers import parse_mcp_date


def search_x_posts(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    query = arguments.get("query")
    if not query:
        raise ToolExecutionError("query is required")
    try:
        limit = parse_mcp_int(arguments.get("limit"), "limit", default=10, minimum=1, maximum=100)
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)

    matches = vector_db.find_similar_x_posts(uid, query, limit=limit)
    if not matches:
        return {"posts": []}

    score_map = {str(m['post_id']): m.get('score', 0) for m in matches}
    posts = x_posts_db.get_x_posts_by_ids(uid, [m['post_id'] for m in matches])
    results: List[Dict[str, Any]] = []
    for p in posts:
        results.append(
            {
                "id": p.get("id"),
                "text": p.get("text"),
                "kind": p.get("kind"),
                "created_at": p.get("created_at"),
                "relevance_score": round(score_map.get(str(p.get("id")), 0), 4),
            }
        )
    results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return {"posts": results}


def get_x_posts(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    try:
        limit = parse_mcp_int(arguments.get("limit"), "limit", default=50, minimum=1, maximum=200)
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    kind = arguments.get("kind")
    posts = x_posts_db.get_x_posts(uid, limit=limit, kind=kind)
    results = [
        {"id": p.get("id"), "text": p.get("text"), "kind": p.get("kind"), "created_at": p.get("created_at")}
        for p in posts
    ]
    return {"posts": results}


def get_goals(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    try:
        include_inactive = parse_mcp_bool(arguments.get("include_inactive"), "include_inactive", default=False)
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    return {"goals": goals_db.get_all_goals(uid, include_inactive=include_inactive)}


def get_chat_messages(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    try:
        limit = parse_mcp_int(arguments.get("limit"), "limit", default=50, minimum=1, maximum=200)
        offset = parse_mcp_int(arguments.get("offset"), "offset", default=0, minimum=0, maximum=100000)
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    messages = chat_db.get_messages(uid, limit=limit, offset=offset)
    return {"messages": [clean_chat_message(m) for m in messages]}


def get_people(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    return {"people": [clean_person(p) for p in users_db.get_people(uid)]}


def get_screen_activity(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    start = parse_mcp_date(arguments.get("start_date"), "start_date")
    end = parse_mcp_date(arguments.get("end_date"), "end_date")
    if end is not None:
        # Include the entire end day, matching the integration-router
        # convention. The DB layer formats the bound via strftime, so the
        # end-of-day increment must be applied here (the parsed midnight
        # would otherwise match only up to 00:00:00.999 of the end day).
        end = end_of_day_utc(end)
    app = arguments.get("app")
    try:
        summary = parse_mcp_bool(arguments.get("summary"), "summary", default=False)
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    if summary:
        try:
            return screen_activity_db.get_screen_activity_summary(uid, start_date=start, end_date=end)
        except FailedPrecondition as e:
            raise_screen_activity_index_error(e)
    try:
        limit = parse_mcp_int(arguments.get("limit"), "limit", default=200, minimum=1, maximum=1000)
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    try:
        rows = screen_activity_db.get_screen_activity(uid, start_date=start, end_date=end, app_filter=app, limit=limit)
    except FailedPrecondition as e:
        raise_screen_activity_index_error(e)
    return {"screen_activity": [clean_screen_activity_row(r) for r in rows]}


def get_daily_summaries(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    try:
        limit = parse_mcp_int(arguments.get("limit"), "limit", default=30, minimum=1, maximum=100)
        offset = parse_mcp_int(arguments.get("offset"), "offset", default=0, minimum=0, maximum=100000)
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    summaries = daily_summaries_db.get_daily_summaries(
        uid,
        limit=limit,
        offset=offset,
        start_date=arguments.get("start_date"),
        end_date=arguments.get("end_date"),
    )
    return {"daily_summaries": summaries}
