"""Remaining read-side tool handlers: X posts, goals, chat, people, screen, daily summaries."""

from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

from google.api_core.exceptions import FailedPrecondition

import database.chat as chat_db
import database.daily_summaries as daily_summaries_db
import database.goals as goals_db
import database.users as users_db
import database.vector_db as vector_db
import database.x_posts as x_posts_db
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.mcp_data import clean_chat_message, clean_person, end_of_day_utc
from utils.mcp_memories import parse_mcp_bool, parse_mcp_int
from utils.mcp_server.constants import (
    MCP_SCREEN_ACTIVITY_OBSERVATION_GAP_SECONDS,
    MCP_SCREEN_ACTIVITY_TOP_TITLES,
)
from utils.mcp_server.cursors import (
    decode_cursor,
    encode_cursor,
    keyset_position,
    offset_page,
    resolve_offset_cursor,
)
from utils.mcp_server.errors import ToolExecutionError
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
    filters: Dict[str, Any] = {}
    offset = resolve_offset_cursor(arguments, kind="get_chat_messages", uid=uid, filters=filters, offset=offset)
    # The backend counts offset in visible (non-reported) rows, so a limit+1
    # lookahead answers has_more exactly.
    fetched = chat_db.get_messages(uid, limit=limit + 1, offset=offset)
    page, consumed, has_more = offset_page(fetched, limit)
    result: Dict[str, Any] = {"messages": [clean_chat_message(m) for m in page]}
    if has_more:
        result["next_cursor"] = encode_cursor(
            kind="get_chat_messages",
            uid=uid,
            position={"offset": offset + consumed},
            filters=filters,
        )
    return result


def get_people(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    return {"people": [clean_person(p) for p in users_db.get_people(uid)]}


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
    filters = {
        "start": arguments.get("start_date"),
        "end": arguments.get("end_date"),
    }
    offset = resolve_offset_cursor(arguments, kind="get_daily_summaries", uid=uid, filters=filters, offset=offset)
    fetched = daily_summaries_db.get_daily_summaries(
        uid,
        limit=limit + 1,
        offset=offset,
        start_date=arguments.get("start_date"),
        end_date=arguments.get("end_date"),
    )
    page, consumed, has_more = offset_page(fetched, limit)
    result: Dict[str, Any] = {"daily_summaries": page}
    if has_more:
        result["next_cursor"] = encode_cursor(
            kind="get_daily_summaries",
            uid=uid,
            position={"offset": offset + consumed},
            filters=filters,
        )
    return result
