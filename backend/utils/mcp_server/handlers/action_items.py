"""Action-item tool handlers for the hosted MCP server."""

from typing import Any, Dict, Optional

import database.action_items as action_items_db
import utils.mcp_action_items as mcp_action_items
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.mcp_data import clean_action_item, end_of_day_utc
from utils.mcp_memories import parse_mcp_bool, parse_mcp_int, parse_optional_mcp_bool
from utils.mcp_server.cursors import encode_cursor, offset_page, resolve_offset_cursor
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.helpers import parse_mcp_date


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
    filters = {
        "completed": completed,
        "due_start": due_start.isoformat() if due_start else None,
        "due_end": due_end.isoformat() if due_end else None,
    }
    offset = resolve_offset_cursor(arguments, kind="get_action_items", uid=uid, filters=filters, offset=offset)
    # The backend slices its live (non-deleted) list by offset, so a limit+1
    # lookahead answers has_more exactly — a short page is the end.
    fetched = action_items_db.get_action_items(
        uid,
        completed=completed,
        due_start_date=due_start,
        due_end_date=due_end,
        limit=limit + 1,
        offset=offset,
    )
    page, consumed, has_more = offset_page([i for i in fetched if not i.get("deleted", False)], limit)
    result: Dict[str, Any] = {"action_items": [clean_action_item(i) for i in page]}
    if has_more:
        result["next_cursor"] = encode_cursor(
            kind="get_action_items",
            uid=uid,
            position={"offset": offset + consumed},
            filters=filters,
        )
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
