"""Action-item tool handlers for the hosted MCP server."""

from typing import Any, Dict, List, Optional, Tuple

from google.api_core.exceptions import FailedPrecondition

import database.action_item_sync as action_item_sync_db
import database.action_items as action_items_db
import utils.mcp_action_items as mcp_action_items
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.mcp_data import clean_action_item, end_of_day_utc
from utils.mcp_memories import (
    parse_mcp_bool,
    parse_mcp_int,
    parse_optional_mcp_bool,
    parse_sync_timestamp,
)
from utils.mcp_server.cursors import (
    decode_cursor,
    encode_cursor,
    offset_page,
    resolve_offset_cursor,
    serialize_timestamp,
    timestamp_keyset_position,
)
from utils.mcp_server.errors import ToolExecutionError, raise_action_item_index_error
from utils.mcp_server.helpers import parse_mcp_date


def action_items_list_page_core(
    uid: str,
    *,
    completed: Optional[bool],
    due_start: Optional[Any],
    due_end: Optional[Any],
    limit: int,
    offset: int = 0,
    cursor_token: Optional[str] = None,
    cursor_kind: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Shared product-ordered action-item page for the MCP tool and REST list."""
    filters = {
        "completed": completed,
        "due_start": due_start.isoformat() if due_start else None,
        "due_end": due_end.isoformat() if due_end else None,
    }
    arguments = {"cursor": cursor_token}
    offset = resolve_offset_cursor(arguments, kind=cursor_kind, uid=uid, filters=filters, offset=offset)
    # The backend slices its live (non-deleted) list by offset, so a limit+1
    # lookahead answers has_more exactly — a short page is the end.
    try:
        fetched = action_items_db.get_action_items(
            uid,
            completed=completed,
            due_start_date=due_start,
            due_end_date=due_end,
            limit=limit + 1,
            offset=offset,
        )
    except FailedPrecondition as e:
        raise_action_item_index_error(e)
    page, consumed, has_more = offset_page([i for i in fetched if not i.get("deleted", False)], limit)
    next_cursor = None
    if has_more:
        next_cursor = encode_cursor(
            kind=cursor_kind,
            uid=uid,
            position={"offset": offset + consumed},
            filters=filters,
        )
    return [clean_action_item(i) for i in page], next_cursor


def action_items_sync_page_core(
    uid: str,
    *,
    updated_since: Any,
    limit: int,
    cursor_token: Optional[str] = None,
    cursor_kind: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Shared ``(updated_at ASC, __name__ ASC)`` incremental feed for REST sync.

    Emits the persisted ``updated_at`` watermark on every item and includes
    soft tombstones only where a row with ``deleted: true`` actually exists;
    hard deletes leave no row and are not reported.
    """
    filters = {"updated_since": updated_since.isoformat()}
    after = None
    if cursor_token is not None:
        after = timestamp_keyset_position(decode_cursor(cursor_token, kind=cursor_kind, uid=uid, filters=filters))
    try:
        rows, resume = action_item_sync_db.get_action_items_sync_page(
            uid,
            updated_since=updated_since,
            after=after,
            limit=limit,
        )
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    except FailedPrecondition as e:
        raise_action_item_index_error(e)
    items: List[Dict[str, Any]] = []
    for row in rows:
        cleaned = clean_action_item(row)
        cleaned["updated_at"] = row.get("updated_at")
        if row.get("deleted", False):
            cleaned["deleted"] = True
        items.append(cleaned)
    next_cursor = None
    if resume is not None:
        next_cursor = encode_cursor(
            kind=cursor_kind,
            uid=uid,
            position={"ts": serialize_timestamp(resume[0]), "id": resume[1]},
            filters=filters,
        )
    return items, next_cursor


def get_action_items(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    try:
        limit = parse_mcp_int(arguments.get("limit"), "limit", default=100, minimum=1, maximum=500)
        offset = parse_mcp_int(arguments.get("offset"), "offset", default=0, minimum=0, maximum=100000)
        completed = parse_optional_mcp_bool(arguments.get("completed"), "completed")
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    due_start = parse_mcp_date(arguments.get("due_start_date"), "due_start_date")
    due_end = parse_mcp_date(arguments.get("due_end_date"), "due_end_date")
    if due_end is not None:
        # Include the entire end day, matching the integration-router convention.
        due_end = end_of_day_utc(due_end)

    raw_updated_since = arguments.get("updated_since")
    if raw_updated_since is not None:
        try:
            updated_since = parse_sync_timestamp(raw_updated_since, "updated_since")
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        if completed is not None or due_start is not None or due_end is not None:
            raise ToolExecutionError("completed/due-date filters are not supported with updated_since.", code=-32602)
        if offset != 0:
            raise ToolExecutionError("offset is not supported with updated_since; use cursor.", code=-32602)
        items, next_cursor = action_items_sync_page_core(
            uid,
            updated_since=updated_since,
            limit=limit,
            cursor_token=arguments.get("cursor"),
            cursor_kind="get_action_items",
        )
        result: Dict[str, Any] = {"action_items": items}
        if next_cursor is not None:
            result["next_cursor"] = next_cursor
        return result

    items, next_cursor = action_items_list_page_core(
        uid,
        completed=completed,
        due_start=due_start,
        due_end=due_end,
        limit=limit,
        offset=offset,
        cursor_token=arguments.get("cursor"),
        cursor_kind="get_action_items",
    )
    result = {"action_items": items}
    if next_cursor is not None:
        result["next_cursor"] = next_cursor
    return result


def search_action_items(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    try:
        items = mcp_action_items.search_action_items(uid, arguments.get("query"), limit=arguments.get("limit", 10))
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    return {"action_items": items}


def create_action_item(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    try:
        completed = parse_mcp_bool(arguments.get("completed"), "completed", default=False)
        item = mcp_action_items.create_action_item(
            uid,
            arguments.get("description"),
            due_at=arguments.get("due_at"),
            completed=completed,
        )
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    return {"success": True, "action_item": item}


def complete_action_item(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    action_item_id = arguments.get("action_item_id")
    if not isinstance(action_item_id, str) or not action_item_id:
        raise ToolExecutionError("action_item_id is required and must be a string", code=-32602)
    try:
        completed = parse_mcp_bool(arguments.get("completed"), "completed", default=True)
        item = mcp_action_items.set_completed(uid, action_item_id, completed=completed)
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    except mcp_action_items.ActionItemNotFound:
        raise ToolExecutionError("Action item not found", code=-32001)
    except mcp_action_items.ActionItemLocked:
        raise ToolExecutionError("A paid plan is required to modify this action item.", code=-32002)
    return {"success": True, "action_item": item}


def update_action_item(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    action_item_id = arguments.get("action_item_id")
    if not isinstance(action_item_id, str) or not action_item_id:
        raise ToolExecutionError("action_item_id is required and must be a string", code=-32602)
    try:
        item = mcp_action_items.update_action_item(
            uid,
            action_item_id,
            description=arguments.get("description"),
            due_at=arguments.get("due_at"),
        )
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)
    except mcp_action_items.ActionItemNotFound:
        raise ToolExecutionError("Action item not found", code=-32001)
    except mcp_action_items.ActionItemLocked:
        raise ToolExecutionError("A paid plan is required to modify this action item.", code=-32002)
    return {"success": True, "action_item": item}


def delete_action_item(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    action_item_id = arguments.get("action_item_id")
    if not isinstance(action_item_id, str) or not action_item_id:
        raise ToolExecutionError("action_item_id is required and must be a string", code=-32602)
    try:
        mcp_action_items.delete_action_item(uid, action_item_id)
    except mcp_action_items.ActionItemNotFound:
        raise ToolExecutionError("Action item not found", code=-32001)
    except mcp_action_items.ActionItemLocked:
        raise ToolExecutionError("A paid plan is required to modify this action item.", code=-32002)
    return {"success": True}
