"""Shared write/search orchestration for the MCP action-items surface.

Both the REST endpoints (``routers/mcp.py``) and the MCP tools
(``routers/mcp_sse.py``) drive action-item create/complete/update/delete/search
through these helpers, so the two transports cannot drift in behavior
(idempotency, vector indexing, paywall handling). Past drift between the SSE and
REST MCP paths is exactly what required follow-up alignment fixes, so the write
path is centralized here from the start. Lives in ``utils`` so neither router
imports the other (routers must never import from other routers).
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import database.action_items as action_items_db
from database.vector_db import (
    upsert_action_item_vector,
    delete_action_item_vector,
    search_action_items_by_vector,
)
from utils.mcp_data import clean_action_item

logger = logging.getLogger(__name__)

# Bound how much text a single tool call can write. The app UI never produces a
# task description this long; this only caps adversarial or garbled MCP input so
# a runaway client cannot push a multi-megabyte Firestore document.
MAX_DESCRIPTION_CHARS = 2000

# Upper bound on search breadth — keeps a model from requesting thousands of rows.
MAX_SEARCH_LIMIT = 50


class ActionItemError(Exception):
    """Base class for action-item write failures the routers map to transport codes."""


class ActionItemNotFound(ActionItemError):
    """No action item with that id exists for this user."""


class ActionItemLocked(ActionItemError):
    """The item is behind the paywall (``is_locked``); a paid plan is required to mutate it."""


def content_idempotency_key(uid: str, description: str) -> str:
    """Stable key from (uid, normalized description).

    A retried create with the same description collapses onto the original item
    instead of producing a duplicate — important for MCP, where a model client
    may resend a tool call after a transport hiccup. Length-prefixed so a uid
    containing ``:`` cannot collide with a different (uid, description) pair.
    """
    normalized = (description or '').strip().lower()
    payload = f"{len(uid)}:{uid}:{normalized}"
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _normalize_description(description: Optional[str]) -> str:
    if description is None:
        raise ValueError("description is required")
    text = description.strip()
    if not text:
        raise ValueError("description cannot be empty")
    if len(text) > MAX_DESCRIPTION_CHARS:
        raise ValueError(f"description is too long (max {MAX_DESCRIPTION_CHARS} characters)")
    return text


def parse_due_at(value: Union[str, datetime, None]) -> Optional[datetime]:
    """Accept an ISO 8601 datetime, a yyyy-mm-dd date, a datetime, or None.

    REST passes a parsed ``datetime``; MCP tools pass a JSON string. Both routes
    funnel through here so the accepted formats stay identical.
    """
    if value is None or isinstance(value, datetime):
        return value
    text = value.strip()
    if not text:
        return None
    parsed: Optional[datetime] = None
    try:
        # fromisoformat also accepts a date-only string (e.g. 2026-07-01) and
        # returns it naive, so the strptime branch is a fallback for formats it
        # rejects rather than the date-only path.
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid due_at: '{value}'. Use ISO 8601 (e.g. 2026-07-01T17:00:00Z) or YYYY-MM-DD.")
    # Normalize a tz-naive value to UTC so due-date filtering never has to
    # compare offset-naive and offset-aware datetimes.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _require_unlocked(uid: str, action_item_id: str) -> Dict[str, Any]:
    """Fetch the item (uid-scoped, so a foreign id can never resolve) and reject
    a missing/deleted item with ``ActionItemNotFound`` and a paywalled one with
    ``ActionItemLocked`` — mirroring the memory write guards."""
    item = action_items_db.get_action_item(uid, action_item_id)
    if not item or item.get("deleted", False):
        raise ActionItemNotFound("Action item not found")
    if item.get("is_locked", False):
        raise ActionItemLocked("A paid plan is required to modify this action item.")
    return item


def _reload(uid: str, action_item_id: str) -> Dict[str, Any]:
    """Re-read an item after a write and shape it for the response. Raises
    ActionItemNotFound if a concurrent delete removed it between the write and
    this read, rather than dereferencing None."""
    item = action_items_db.get_action_item(uid, action_item_id)
    if not item:
        raise ActionItemNotFound("Action item not found")
    return clean_action_item(item)


def create_action_item(
    uid: str,
    description: Optional[str],
    due_at: Union[str, datetime, None] = None,
    completed: bool = False,
) -> Dict[str, Any]:
    """Create a task and return its cleaned MCP shape. Content-idempotent on
    (uid, normalized description)."""
    text = _normalize_description(description)
    parsed_due = parse_due_at(due_at)
    data = {
        "description": text,
        "completed": bool(completed),
        "due_at": parsed_due,
        "conversation_id": None,
    }
    key = content_idempotency_key(uid, text)
    item_id = action_items_db.create_action_item(uid, data, idempotency_key=key)

    # Index for semantic search so an MCP-created task is discoverable the same
    # way app-created tasks are. Best-effort: the task already persisted, so a
    # missing vector only degrades search ranking and never loses the task.
    try:
        upsert_action_item_vector(uid, item_id, text)
    except Exception:
        logger.exception("MCP create_action_item: vector upsert failed uid=%s id=%s (task saved)", uid, item_id)

    item = action_items_db.get_action_item(uid, item_id)
    if not item:
        raise ActionItemError("Failed to load the created action item")
    return clean_action_item(item)


def set_completed(uid: str, action_item_id: str, completed: bool = True) -> Dict[str, Any]:
    """Mark a task complete or reopen it."""
    _require_unlocked(uid, action_item_id)
    if not action_items_db.mark_action_item_completed(uid, action_item_id, completed=completed):
        raise ActionItemNotFound("Action item not found")
    return _reload(uid, action_item_id)


def update_action_item(
    uid: str,
    action_item_id: str,
    description: Optional[str] = None,
    due_at: Union[str, datetime, None] = None,
) -> Dict[str, Any]:
    """Update a task's description and/or due date.

    Only the fields provided are changed. Clearing a due date is not supported in
    this version (an omitted ``due_at`` leaves it unchanged rather than nulling it).
    """
    _require_unlocked(uid, action_item_id)
    update_data: Dict[str, Any] = {}
    new_text: Optional[str] = None
    if description is not None:
        new_text = _normalize_description(description)
        update_data["description"] = new_text
    if due_at is not None:
        # Clearing a due date is not supported here, so an empty/blank value
        # (which parses to None) is treated as "not provided" rather than nulling
        # the field — matching the documented contract.
        parsed_due = parse_due_at(due_at)
        if parsed_due is not None:
            update_data["due_at"] = parsed_due
    if not update_data:
        raise ValueError("Provide a description, or a due date in ISO 8601 / YYYY-MM-DD form, to update")

    if not action_items_db.update_action_item(uid, action_item_id, update_data):
        raise ActionItemNotFound("Action item not found")

    # Re-index only when the searchable text changed.
    if new_text is not None:
        try:
            upsert_action_item_vector(uid, action_item_id, new_text)
        except Exception:
            logger.exception(
                "MCP update_action_item: vector upsert failed uid=%s id=%s (task updated)", uid, action_item_id
            )
    return _reload(uid, action_item_id)


def delete_action_item(uid: str, action_item_id: str) -> None:
    """Delete a task and its search vector."""
    _require_unlocked(uid, action_item_id)
    # Honor the delete result: a False here means the row was already gone (a
    # concurrent delete between the existence check above and now), so report
    # not-found rather than a misleading success.
    if not action_items_db.delete_action_item(uid, action_item_id):
        raise ActionItemNotFound("Action item not found")
    try:
        delete_action_item_vector(uid, action_item_id)
    except Exception:
        logger.exception(
            "MCP delete_action_item: vector delete failed uid=%s id=%s (task deleted)", uid, action_item_id
        )


def search_action_items(uid: str, query: Optional[str], limit: int = 10) -> List[Dict[str, Any]]:
    """Semantic search over the user's tasks, returned in relevance order."""
    if not query or not query.strip():
        raise ValueError("query is required")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer")
    limit = max(1, min(limit, MAX_SEARCH_LIMIT))

    ids = search_action_items_by_vector(uid, query, limit=limit)
    if not ids:
        return []
    items: List[Dict[str, Any]] = action_items_db.get_action_items_by_ids(uid, ids)
    # Preserve the relevance order from the vector search; get_action_items_by_ids
    # does not guarantee ordering.
    order = {aid: i for i, aid in enumerate(ids)}
    items.sort(key=lambda it: order.get(it.get("id", ""), len(ids)))
    return [clean_action_item(it) for it in items if not it.get("deleted", False)]
