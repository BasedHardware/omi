"""
Shared service functions for action item retrieval and management.
Used by both LangChain tools (mobile chat) and REST router (desktop/web).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config.action_item_reminder_triggers import action_item_write_affects_reminder
import database.action_items as action_items_db
from utils.notifications import (
    send_action_item_completed_notification,
    send_action_item_created_notification,
    send_action_item_data_message,
    sync_action_item_reminder,
)
from utils.model_text import format_date, format_instant
from utils.user_clock import clock_for_uid
from utils.retrieval.tool_services.conversations import parse_iso_date
from utils.retrieval.safety import safe_isoformat
import logging

logger = logging.getLogger(__name__)


def get_action_items_text(
    uid: str,
    limit: int = 50,
    offset: int = 0,
    completed: Optional[bool] = None,
    conversation_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    due_start_date: Optional[str] = None,
    due_end_date: Optional[str] = None,
    source_sink: Optional[List[dict[str, Any]]] = None,
) -> str:
    """Fetch action items and format as LLM-ready text."""
    logger.info(f"get_action_items_text - uid: {uid}, limit: {limit}, offset: {offset}, completed: {completed}")
    clock = clock_for_uid(uid)

    # Cap limit
    limit = min(limit, 500)

    # Parse creation dates
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = parse_iso_date(start_date, 'start_date')
        except ValueError as e:
            return f"Error: Invalid start_date format: {e}"
    if end_date:
        try:
            end_dt = parse_iso_date(end_date, 'end_date')
        except ValueError as e:
            return f"Error: Invalid end_date format: {e}"

    # Parse due dates
    due_start_dt = None
    due_end_dt = None
    if due_start_date:
        try:
            due_start_dt = parse_iso_date(due_start_date, 'due_start_date')
        except ValueError as e:
            return f"Error: Invalid due_start_date format: {e}"
    if due_end_date:
        try:
            due_end_dt = parse_iso_date(due_end_date, 'due_end_date')
        except ValueError as e:
            return f"Error: Invalid due_end_date format: {e}"

    # Fetch
    try:
        action_items = action_items_db.get_action_items(
            uid=uid,
            conversation_id=conversation_id,
            completed=completed,
            start_date=start_dt,
            end_date=end_dt,
            due_start_date=due_start_dt,
            due_end_date=due_end_dt,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"get_action_items_text error: {e}")
        return f"Error retrieving action items: {e}"

    # Filter locked items (paid plan required)
    if action_items:
        action_items = [item for item in action_items if not item.get('is_locked', False)]

    if not action_items:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" created between {format_date(start_dt, clock)} and {format_date(end_dt, clock)}"
        elif start_dt:
            date_info = f" created after {format_date(start_dt, clock)}"
        elif end_dt:
            date_info = f" created before {format_date(end_dt, clock)}"
        if due_start_dt and due_end_dt:
            date_info += f" due between {format_date(due_start_dt, clock)} and {format_date(due_end_dt, clock)}"
        elif due_start_dt:
            date_info += f" due after {format_date(due_start_dt, clock)}"
        elif due_end_dt:
            date_info += f" due before {format_date(due_end_dt, clock)}"
        status_info = ""
        if completed is True:
            status_info = " completed"
        elif completed is False:
            status_info = " pending"
        return f"No{status_info} action items found{date_info}."

    # Render timestamps in the user's local timezone with an explicit label, matching
    # get_action_items_tool: an unlabelled UTC wall clock makes the agent state the wrong
    # time of day (issue #6214). A timezone lookup failure must never abort retrieval.
    result = f"User Action Items ({len(action_items)} total):\n\n"
    if source_sink is not None:
        # Structured client source metadata; not model-facing prose.
        for item in action_items[:128]:
            source_sink.append(
                {
                    'kind': 'task',
                    'source_id': str(item.get('id') or ''),
                    'title': str(item.get('description') or 'Task')[:160],
                    'preview': str(item.get('description') or '')[:600],
                    'created_at': safe_isoformat(item.get('created_at')),
                }
            )
    for i, item in enumerate(action_items, 1):
        status = "✅ Completed" if item.get('completed', False) else "⬜ Pending"
        result += f"{i}. [{status}] {item.get('description', 'No description')}\n"
        result += f"   ID: {item.get('id')}\n"
        if item.get('created_at'):
            result += f"   Created: {format_instant(item['created_at'], clock)}\n"
        if item.get('due_at'):
            result += f"   Due: {format_instant(item['due_at'], clock)}\n"
        if item.get('completed_at'):
            result += f"   Completed: {format_instant(item['completed_at'], clock)}\n"
        if item.get('conversation_id'):
            result += f"   From conversation: {item['conversation_id']}\n"
        result += "\n"
    return result.strip()


def create_action_item_text(
    uid: str,
    description: str,
    due_at: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> str:
    """Create an action item and return confirmation text."""
    logger.info(f"create_action_item_text - uid: {uid}, description: {description}")
    clock = clock_for_uid(uid)

    if not description or not description.strip():
        return "Error: Description is required."

    action_item_data: Dict[str, Any] = {
        'description': description.strip(),
        'completed': False,
        'conversation_id': conversation_id,
    }

    if due_at is not None:
        try:
            due_dt = parse_iso_date(due_at, 'due_at')
            now_utc = datetime.now(timezone.utc)
            if due_dt < now_utc - timedelta(days=1):
                return f"Error: due_at '{due_at}' is in the past. " f"Current time is {format_instant(now_utc, clock)}."
            action_item_data['due_at'] = due_dt
        except ValueError as e:
            return f"Error: Invalid due_at format: {e}"
    else:
        # No invented due date: see create_action_item_tool. A task with no date
        # the user gave belongs in the undated bucket, not tomorrow's.
        pass

    try:
        action_item_id = action_items_db.create_action_item(uid, action_item_data)
        if not action_item_id:
            return "Error: Failed to create action item."

        created_item = action_items_db.get_action_item(uid, action_item_id)
        if not created_item:
            return "Action item created, but couldn't retrieve details."

        task_desc = created_item.get('description', 'Task')
        result = f"✅ Added: {task_desc}"

        if created_item.get('due_at'):
            due = created_item['due_at']
            result += f" (due {format_instant(due, clock)})"
            try:
                send_action_item_data_message(
                    user_id=uid,
                    action_item_id=action_item_id,
                    description=task_desc,
                    due_at=due.isoformat(),  # not-model-facing: client notification payload
                    completed=bool(created_item.get('completed')),
                    status=created_item.get('status'),
                    deleted=bool(created_item.get('deleted')),
                )
            except Exception as notif_error:
                logger.error(f"Failed to send notification: {notif_error}")

        try:
            send_action_item_created_notification(uid, task_desc)
        except Exception as notif_error:
            logger.error(f"Failed to send creation notification: {notif_error}")

        return result

    except Exception as e:
        logger.error(f"create_action_item_text error: {e}")
        return f"Error creating action item: {e}"


def update_action_item_text(
    uid: str,
    action_item_id: str,
    completed: Optional[bool] = None,
    description: Optional[str] = None,
    due_at: Optional[str] = None,
) -> str:
    """Update an action item and return confirmation text."""
    clock = clock_for_uid(uid)
    logger.info(f"update_action_item_text - uid: {uid}, id: {action_item_id}")

    if not action_item_id or not action_item_id.strip():
        return "Error: action_item_id is required."

    # Verify exists and not locked
    existing = action_items_db.get_action_item(uid, action_item_id)
    if not existing:
        return f"Error: Action item '{action_item_id}' not found."
    if existing.get('is_locked', False):
        return "Error: A paid plan is required to modify this action item."

    update_data: Dict[str, Any] = {}
    changes: List[str] = []

    if completed is not None:
        update_data['completed'] = completed
        if completed:
            update_data['completed_at'] = datetime.now(timezone.utc)
            changes.append("marked as completed")
        else:
            update_data['completed_at'] = None
            changes.append("marked as pending")

    if description is not None:
        update_data['description'] = description.strip()
        changes.append(f"description updated to '{description.strip()}'")

    if due_at is not None:
        try:
            due_dt = parse_iso_date(due_at, 'due_at')
            update_data['due_at'] = due_dt
            changes.append(f"due date set to {format_instant(due_dt, clock)}")
        except ValueError as e:
            return f"Error: Invalid due_at format: {e}"

    if not update_data:
        return "No changes specified."

    try:
        action_items_db.update_action_item(uid, action_item_id, update_data)

        # Re-fetch the authoritative post-write state so reminder reconciliation can't act on a stale
        # pre-update value (matches the update_action_item_tool path).
        updated_item = action_items_db.get_action_item(uid, action_item_id)
        if not updated_item:
            return f"Successfully updated action item '{action_item_id}', but couldn't retrieve details."

        # Send notification if completed
        if completed is True:
            try:
                send_action_item_completed_notification(uid, updated_item.get('description', 'Task'))
            except Exception as notif_error:
                logger.error(f"Failed to send completion notification: {notif_error}")

        # Reconcile the scheduled reminder to match the new state — cancel on completion, (re)schedule
        # only for an open task with a due date (#5085). A rename re-arms it with the new title.
        if action_item_write_affects_reminder(update_data):
            try:
                sync_action_item_reminder(
                    uid,
                    action_item_id,
                    updated_item.get('description', ''),
                    bool(updated_item.get('completed')),
                    updated_item.get('due_at'),
                    status=updated_item.get('status'),
                    deleted=bool(updated_item.get('deleted')),
                )
            except Exception as notif_error:
                logger.error(f"Failed to sync action item reminder: {notif_error}")

        task_desc = update_data.get('description', existing.get('description', 'Task'))
        return f"✅ Updated '{task_desc}': {', '.join(changes)}"

    except Exception as e:
        logger.error(f"update_action_item_text error: {e}")
        return f"Error updating action item: {e}"
