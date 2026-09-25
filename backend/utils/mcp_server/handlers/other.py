"""Remaining read-side tool handlers: X posts, goals, chat, people, screen, daily summaries."""

from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

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


_SCREEN_ACTIVITY_GROUP_BY = frozenset({"none", "app", "hour", "day"})


def _screen_activity_timestamp(value: Any) -> Optional[datetime]:
    """Parse the stored 'YYYY-MM-DD HH:MM:SS.mmm' timestamp for bucketing."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _screen_activity_bucket_key(row: Dict[str, Any], group_by: str) -> str:
    if group_by == "app":
        return row.get("appName") or "Unknown"
    timestamp = str(row.get("timestamp") or "")
    if group_by == "day":
        return timestamp[:10]
    return timestamp[:13] + ":00"  # hour


def _screen_activity_bucket_label(key: str, group_by: str) -> Dict[str, Any]:
    if group_by == "app":
        return {"app": key}
    if group_by == "day":
        return {"day": key}
    return {"hour": key}


class _ScreenActivityBucket(TypedDict):
    count: int
    estimated_observation_seconds: int
    first_seen: Any
    last_seen: Any
    titles: Counter[str]


def _screen_activity_buckets(
    rows: List[Dict[str, Any]],
    group_by: str,
    seed_row: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Group one page of rows into count/duration/top-title buckets.

    ``estimated_observation_seconds`` sums the gaps between CONSECUTIVE rows
    that share the same bucket AND app, capped at
    ``MCP_SCREEN_ACTIVITY_OBSERVATION_GAP_SECONDS`` per gap: it is the span
    covered by observed captures, never a measure of actual usage duration.
    ``seed_row`` (the previous page's last row, carried by the cursor) lets
    the gap that bridges a page boundary still count.
    """
    buckets: Dict[str, _ScreenActivityBucket] = {}
    previous_key = ""
    previous_app = ""
    previous_ts: Optional[datetime] = None
    if seed_row is not None:
        previous_key = _screen_activity_bucket_key(seed_row, group_by)
        previous_app = seed_row.get("appName") or "Unknown"
        previous_ts = _screen_activity_timestamp(seed_row.get("timestamp"))
    for row in rows:
        app = row.get("appName") or "Unknown"
        timestamp = row.get("timestamp")
        parsed_ts = _screen_activity_timestamp(timestamp)
        key = _screen_activity_bucket_key(row, group_by)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = _ScreenActivityBucket(
                count=0,
                estimated_observation_seconds=0,
                first_seen=timestamp,
                last_seen=timestamp,
                titles=Counter(),
            )
            buckets[key] = bucket
        bucket["count"] += 1
        bucket["last_seen"] = timestamp
        title = row.get("windowTitle")
        if title:
            bucket["titles"][title] += 1
        if previous_ts is not None and previous_key == key and previous_app == app and parsed_ts is not None:
            gap = (parsed_ts - previous_ts).total_seconds()
            if 0 <= gap <= MCP_SCREEN_ACTIVITY_OBSERVATION_GAP_SECONDS:
                bucket["estimated_observation_seconds"] += int(gap)
        previous_key = key
        previous_app = app
        previous_ts = parsed_ts

    results: List[Dict[str, Any]] = []
    for key, bucket in buckets.items():
        top_titles = sorted(bucket["titles"].items(), key=lambda item: (-item[1], item[0]))[
            :MCP_SCREEN_ACTIVITY_TOP_TITLES
        ]
        results.append(
            {
                **_screen_activity_bucket_label(key, group_by),
                "count": bucket["count"],
                "estimated_observation_seconds": bucket["estimated_observation_seconds"],
                "top_titles": [{"title": title, "count": count} for title, count in top_titles],
                "first_seen": bucket["first_seen"],
                "last_seen": bucket["last_seen"],
            }
        )
    if group_by == "app":
        results.sort(key=lambda item: (-item["count"], item["app"]))
    else:
        results.sort(key=lambda item: item[group_by])
    return results


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
    if app is not None and not isinstance(app, str):
        raise ToolExecutionError("app must be a string", code=-32602)
    try:
        summary = parse_mcp_bool(arguments.get("summary"), "summary", default=False)
        limit = parse_mcp_int(arguments.get("limit"), "limit", default=200, minimum=1, maximum=1000)
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    group_by = arguments.get("group_by") or "none"
    if group_by not in _SCREEN_ACTIVITY_GROUP_BY:
        raise ToolExecutionError("Invalid group_by. Expected one of: none, app, hour, day.", code=-32602)
    return screen_activity_core(
        uid,
        start=start,
        end=end,
        app=app,
        summary=summary,
        group_by=group_by,
        limit=limit,
        cursor_token=arguments.get("cursor"),
        cursor_kind="get_screen_activity",
    )


def screen_activity_core(
    uid: str,
    *,
    start: Optional[datetime],
    end: Optional[datetime],
    app: Optional[str],
    summary: bool,
    group_by: str,
    limit: int,
    cursor_token: Optional[str] = None,
    cursor_kind: str,
) -> Dict[str, Any]:
    """Shared screen-activity read for the MCP tool and the REST endpoint.

    ``cursor_kind`` binds the keyset cursor to the calling surface. Callers
    validate/parse their own inputs (dates arrive as datetimes; REST always
    passes ``group_by="none"``).
    """
    if summary and group_by != "none":
        raise ToolExecutionError("summary=true cannot be combined with group_by other than 'none'.", code=-32602)
    if summary and group_by == "none":
        # The legacy aggregate path is unchanged: one bounded scan with
        # explicit coverage, no cursor (a cursor here could never resume).
        if cursor_token is not None:
            raise ToolExecutionError("cursor is not supported with summary=true.", code=-32602)
        try:
            return screen_activity_db.get_screen_activity_summary(uid, start_date=start, end_date=end)
        except FailedPrecondition as e:
            raise_screen_activity_index_error(e)

    filters = {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "app": app,
        "group_by": group_by,
    }
    after = None
    seed_row: Optional[Dict[str, Any]] = None
    if cursor_token is not None:
        position = decode_cursor(cursor_token, kind=cursor_kind, uid=uid, filters=filters)
        after = keyset_position(position)
        # Carry the boundary row's app so a gap bridging pages still counts.
        seed_row = {"appName": position.get("app"), "timestamp": position.get("ts")}
    try:
        rows, has_more = screen_activity_db.get_screen_activity_page(
            uid,
            start_date=start,
            end_date=end,
            app_filter=app,
            limit=limit,
            after=after,
        )
    except FailedPrecondition as e:
        raise_screen_activity_index_error(e)

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = encode_cursor(
            kind=cursor_kind,
            uid=uid,
            position={
                "ts": str(last.get("timestamp") or ""),
                "id": str(last.get("id") or ""),
                "app": last.get("appName"),
            },
            filters=filters,
        )

    if group_by == "none":
        result: Dict[str, Any] = {"screen_activity": [clean_screen_activity_row(r) for r in rows]}
    else:
        result = {
            "group_by": group_by,
            "buckets": _screen_activity_buckets(rows, group_by, seed_row=seed_row),
        }
    if next_cursor is not None:
        result["next_cursor"] = next_cursor
    return result


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
