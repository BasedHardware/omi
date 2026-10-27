"""Remaining read-side tool handlers: X posts, goals, chat, people, screen, daily summaries."""

from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TypedDict

from google.api_core.exceptions import FailedPrecondition

import database.chat as chat_db
import database.daily_summaries as daily_summaries_db
import database.goals as goals_db
import database.screen_activity as screen_activity_db
import database.users as users_db
from database.person_aliases import normalized_person_alias
import database.vector_db as vector_db
import database.x_posts as x_posts_db
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.mcp_data import clean_chat_message, clean_person, clean_screen_activity_row
from utils.mcp_memories import parse_mcp_bool, parse_mcp_int
from utils.daily_summary_read_contract import summary_read_payload
from utils.mcp_dates import local_date_window, localize_timestamps, resolve_timezone, offset_timestamp
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


def _required_person_id(arguments: Dict[str, Any]) -> str:
    person_id = arguments.get("person_id")
    if not isinstance(person_id, str) or not person_id.strip():
        raise ToolExecutionError("person_id is required", code=-32602)
    return person_id.strip()


def rename_person(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
    *,
    expected_chat_state: dict | None = None,
) -> Dict[str, Any]:
    """Correct a recognised person's display name, retaining the prior one as an alias."""
    person_id = _required_person_id(arguments)
    name = arguments.get("name")
    if not isinstance(name, str):
        raise ToolExecutionError("name is required", code=-32602)
    normalized_name = normalized_person_alias(name)
    if normalized_name is None:
        raise ToolExecutionError("name must contain 1 to 128 characters", code=-32602)
    updated = (
        users_db.update_person(uid, person_id, normalized_name, expected_chat_state=expected_chat_state)
        if expected_chat_state is not None
        else users_db.update_person(uid, person_id, normalized_name)
    )
    if not updated:
        raise ToolExecutionError("Person not found", code=-32001, http_status=404)
    # Deliberately no transcript samples in the response: a correction does not
    # need them and returning them would widen what this scope discloses.
    return {"success": True, "person": {"id": person_id, "name": normalized_name}}


def dismiss_person(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    """Soft-dismiss a false-positive person: preserved in storage and in exports."""
    person_id = _required_person_id(arguments)
    if not users_db.dismiss_person(uid, person_id):
        raise ToolExecutionError("Person not found", code=-32001, http_status=404)
    return {"success": True, "person_id": person_id, "dismissed": True}


_SCREEN_ACTIVITY_GROUP_BY = frozenset({"none", "app", "hour", "day"})


def _screen_activity_timestamp(value: Any) -> Optional[datetime]:
    """Parse the stored 'YYYY-MM-DD HH:MM:SS.mmm' timestamp for bucketing."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _screen_activity_bucket_key(row: Dict[str, Any], group_by: str, *, iso_offset: bool = False) -> str:
    if group_by == "app":
        return row.get("appName") or "Unknown"
    timestamp = str(row.get("timestamp") or "")
    if group_by == "day":
        return timestamp[:10]
    parsed = _screen_activity_timestamp(timestamp)
    return (
        parsed.replace(minute=0, second=0, microsecond=0).isoformat()
        if iso_offset and parsed and parsed.tzinfo
        else timestamp[:13] + ":00"
    )


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
    *,
    iso_offset: bool = False,
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
        previous_key = _screen_activity_bucket_key(seed_row, group_by, iso_offset=iso_offset)
        previous_app = seed_row.get("appName") or "Unknown"
        previous_ts = _screen_activity_timestamp(seed_row.get("timestamp"))
    for row in rows:
        app = row.get("appName") or "Unknown"
        timestamp = row.get("timestamp")
        parsed_ts = _screen_activity_timestamp(timestamp)
        key = _screen_activity_bucket_key(row, group_by, iso_offset=iso_offset)
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
    start, end, zone = local_date_window(
        uid, arguments.get('start_date'), arguments.get('end_date'), arguments.get('timezone')
    )
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
        timezone_name=str(zone),
        timestamp_format=arguments.get("timestamp_format"),
        use_iso_offset=arguments.get("timezone") is not None,
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
    timezone_name: str = "UTC",
    timestamp_format: Optional[str] = None,
    use_iso_offset: bool = False,
) -> Dict[str, Any]:
    """Shared screen-activity read for the MCP tool and the REST endpoint.

    ``cursor_kind`` binds the keyset cursor to the calling surface. Callers
    validate/parse their own inputs (dates arrive as datetimes; REST always
    passes ``group_by="none"``).
    """
    zone = resolve_timezone(uid, timezone_name)
    if timestamp_format not in (None, "legacy", "iso_offset"):
        raise ToolExecutionError("timestamp_format must be legacy or iso_offset", code=-32602)
    use_iso_offset = use_iso_offset or timestamp_format == "iso_offset" or timezone_name != "UTC"
    if start and end and start > end:
        raise ToolExecutionError("start_date must be on or before end_date", code=-32602)
    if summary and group_by != "none":
        raise ToolExecutionError("summary=true cannot be combined with group_by other than 'none'.", code=-32602)
    if summary and group_by == "none":
        # The legacy aggregate path is unchanged: one bounded scan with
        # explicit coverage, no cursor (a cursor here could never resume).
        if cursor_token is not None:
            raise ToolExecutionError("cursor is not supported with summary=true.", code=-32602)
        if app:
            grouped = screen_activity_core(
                uid,
                start=start,
                end=end,
                app=app,
                summary=False,
                group_by='app',
                limit=limit,
                cursor_kind=cursor_kind,
                timezone_name=timezone_name,
                use_iso_offset=use_iso_offset,
            )
            return {
                'apps': {
                    bucket['app']: {
                        'count': bucket['count'],
                        'first_seen': bucket['first_seen'],
                        'last_seen': bucket['last_seen'],
                        'window_titles': [entry['title'] for entry in bucket['top_titles']],
                    }
                    for bucket in grouped['buckets']
                },
                'total_screenshots': sum(bucket['count'] for bucket in grouped['buckets']),
                'coverage': grouped['coverage'],
            }
        try:
            summary_result = screen_activity_db.get_screen_activity_summary(uid, start_date=start, end_date=end)
            return localize_timestamps(summary_result, zone) if use_iso_offset else summary_result
        except FailedPrecondition as e:
            raise_screen_activity_index_error(e)

    if group_by != 'none':
        cap = screen_activity_db.SCREEN_ACTIVITY_SUMMARY_ROW_LIMIT
        try:
            rows = screen_activity_db.get_screen_activity(
                uid, start_date=start, end_date=end, app_filter=app, limit=cap + 1
            )
        except FailedPrecondition as exc:
            raise_screen_activity_index_error(exc)
        truncated = len(rows) > cap
        rows = rows[:cap]
        localized = (
            [{**row, 'timestamp': offset_timestamp(row.get('timestamp'), zone)} for row in rows]
            if use_iso_offset
            else rows
        )
        buckets = _screen_activity_buckets(localized, group_by, iso_offset=use_iso_offset)
        return {
            'group_by': group_by,
            'buckets': buckets,
            **(
                {'note': 'cursor ignored; aggregate covers the full requested window'}
                if cursor_token is not None
                else {}
            ),
            'timezone': str(zone),
            'coverage': {
                'row_limit': cap,
                'scanned_count': len(rows),
                'truncated': truncated,
                'complete_window': not truncated,
                'first_observed_at': localized[0].get('timestamp') if localized else None,
                'last_observed_at': localized[-1].get('timestamp') if localized else None,
            },
            'aggregation_scope': 'bounded_window' if truncated else 'whole_window',
        }

    filters = {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "app": app,
        "group_by": group_by,
        **({"timezone": timezone_name} if timezone_name != "UTC" else {}),
    }
    after = None
    if cursor_token is not None:
        position = decode_cursor(cursor_token, kind=cursor_kind, uid=uid, filters=filters)
        after = keyset_position(position)
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

    result: Dict[str, Any] = {"screen_activity": [clean_screen_activity_row(r) for r in rows]}
    if next_cursor is not None:
        result["next_cursor"] = next_cursor
    return localize_timestamps(result, zone) if use_iso_offset else result


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
    start_date = arguments.get('start_date')
    end_date = arguments.get('end_date')
    _start, _end, zone = local_date_window(uid, start_date, end_date, arguments.get('timezone'))
    filters = {'start': start_date, 'end': end_date, **({'timezone': str(zone)} if arguments.get('timezone') else {})}
    offset = resolve_offset_cursor(arguments, kind='get_daily_summaries', uid=uid, filters=filters, offset=offset)
    if start_date and end_date:
        # Offsets count calendar days when a bounded window is requested, so a
        # missing record cannot disappear between two generated summaries.
        last = datetime.strptime(end_date, '%Y-%m-%d').date()
        first = datetime.strptime(start_date, '%Y-%m-%d').date()
        available = max(0, (last - first).days + 1 - offset)
        dates = [(last - timedelta(days=offset + index)).isoformat() for index in range(min(limit, available))]
        page = []
        for date in dates:
            row = daily_summaries_db.get_daily_summary_by_date(uid, date)
            day_start, day_end, _ = local_date_window(uid, date, date, str(zone))
            assert day_start is not None and day_end is not None
            if row:
                payload = summary_read_payload(row)
                # Historical producers capped their input at 100 conversations.
                # A read-time aggregation corrects the count without rewriting history.
                payload.setdefault('stats', {})['total_conversations'] = daily_summaries_db.get_day_recording_count(
                    uid, day_start, day_end
                )
                payload['stats']['conversation_count_basis'] = 'non_discarded_started_in_local_day'
                payload['timezone'] = str(zone)
                page.append(payload)
                continue
            stored_status = daily_summaries_db.get_daily_summary_generation_status(uid, date)
            stored_status = stored_status if isinstance(stored_status, dict) else {}
            status = stored_status.get('status')
            if status not in {'pending', 'failed', 'no_recordings'}:
                if date >= datetime.now(zone).date().isoformat():
                    status = 'pending'
                else:
                    count = daily_summaries_db.get_day_recording_count(uid, day_start, day_end)
                    status = 'no_recordings' if count == 0 else 'not_generated'
            page.append({'date': date, 'status': status, 'generated_at': None, 'timezone': str(zone)})
        has_more = available > limit
        consumed = len(dates)
    else:
        fetched = daily_summaries_db.get_daily_summaries(
            uid, limit=limit + 1, offset=offset, start_date=start_date, end_date=end_date
        )
        raw_page, consumed, has_more = offset_page(fetched, limit)
        page = []
        for row in raw_page:
            payload = summary_read_payload(row)
            if row.get('date'):
                day_start, day_end, _ = local_date_window(uid, row['date'], row['date'], str(zone))
                assert day_start is not None and day_end is not None
                payload.setdefault('stats', {})['total_conversations'] = daily_summaries_db.get_day_recording_count(
                    uid, day_start, day_end
                )
                payload['stats']['conversation_count_basis'] = 'non_discarded_started_in_local_day'
            payload['timezone'] = str(zone)
            page.append(payload)
    result = {'daily_summaries': localize_timestamps(page, zone)}
    if has_more:
        result['next_cursor'] = encode_cursor(
            kind='get_daily_summaries', uid=uid, position={'offset': offset + consumed}, filters=filters
        )
    return result


def process_recent_conversations(uid, arguments, auth_context=None):
    from utils.conversations.demand_processing import process_recent

    if set(arguments) - {'hours', 'limit'}:
        raise ToolExecutionError('Only hours and limit are accepted', code=-32602)
    try:
        return process_recent(uid, hours=arguments.get('hours', 6), limit=arguments.get('limit', 20))
    except (ValueError, PermissionError) as error:
        raise ToolExecutionError(str(error), code=-32602) from error
