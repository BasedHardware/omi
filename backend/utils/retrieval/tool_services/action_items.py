"""
Shared service functions for action item retrieval and management.
Used by both LangChain tools (mobile chat) and REST router (desktop/web).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import database.action_items as action_items_db
from utils.notifications import (
    send_action_item_completed_notification,
    send_action_item_created_notification,
    send_action_item_data_message,
)
from utils.retrieval.tool_services.conversations import parse_iso_date
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
) -> str:
    """Fetch action items and format as LLM-ready text."""
    logger.info(f"get_action_items_text - uid: {uid}, limit: {limit}, offset: {offset}, completed: {completed}")

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
            date_info = f" created between {start_dt.strftime('%Y-%m-%d')} and {end_dt.strftime('%Y-%m-%d')}"
        elif start_dt:
            date_info = f" created after {start_dt.strftime('%Y-%m-%d')}"
        elif end_dt:
            date_info = f" created before {end_dt.strftime('%Y-%m-%d')}"
        if due_start_dt and due_end_dt:
            date_info += f" due between {due_start_dt.strftime('%Y-%m-%d')} and {due_end_dt.strftime('%Y-%m-%d')}"
        elif due_start_dt:
            date_info += f" due after {due_start_dt.strftime('%Y-%m-%d')}"
        elif due_end_dt:
            date_info += f" due before {due_end_dt.strftime('%Y-%m-%d')}"
        status_info = ""
        if completed is True:
            status_info = " completed"
        elif completed is False:
            status_info = " pending"
        return f"No{status_info} action items found{date_info}."

    # Format
    result = f"User Action Items ({len(action_items)} total):\n\n"
    for i, item in enumerate(action_items, 1):
        status = "✅ Completed" if item.get('completed', False) else "⬜ Pending"
        result += f"{i}. [{status}] {item.get('description', 'No description')}\n"
        result += f"   ID: {item.get('id')}\n"
        if item.get('created_at'):
            result += f"   Created: {item['created_at'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        if item.get('due_at'):
            result += f"   Due: {item['due_at'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        if item.get('completed_at'):
            result += f"   Completed: {item['completed_at'].strftime('%Y-%m-%d %H:%M:%S')}\n"
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

    if not description or not description.strip():
        return "Error: Description is required."

    action_item_data = {
        'description': description.strip(),
        'completed': False,
        'conversation_id': conversation_id,
    }

    if due_at is not None:
        try:
            due_dt = parse_iso_date(due_at, 'due_at')
            now_utc = datetime.now(timezone.utc)
            if due_dt < now_utc - timedelta(days=1):
                return (
                    f"Error: due_at '{due_at}' is in the past. "
                    f"Current time is {now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}."
                )
            action_item_data['due_at'] = due_dt
        except ValueError as e:
            return f"Error: Invalid due_at format: {e}"
    else:
        now = datetime.now(datetime.now().astimezone().tzinfo)
        action_item_data['due_at'] = now + timedelta(hours=24)

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
            result += f" (due {due.strftime('%b %d')})"
            try:
                send_action_item_data_message(
                    user_id=uid,
                    action_item_id=action_item_id,
                    description=task_desc,
                    due_at=due.isoformat(),
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
    logger.info(f"update_action_item_text - uid: {uid}, id: {action_item_id}")

    if not action_item_id or not action_item_id.strip():
        return "Error: action_item_id is required."

    # Verify exists and not locked
    existing = action_items_db.get_action_item(uid, action_item_id)
    if not existing:
        return f"Error: Action item '{action_item_id}' not found."
    if existing.get('is_locked', False):
        return "Error: A paid plan is required to modify this action item."

    update_data = {}
    changes = []

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
            changes.append(f"due date set to {due_dt.strftime('%Y-%m-%d %H:%M')}")
        except ValueError as e:
            return f"Error: Invalid due_at format: {e}"

    if not update_data:
        return "No changes specified."

    try:
        action_items_db.update_action_item(uid, action_item_id, update_data)

        # Send notification if completed
        if completed is True:
            try:
                send_action_item_completed_notification(uid, existing.get('description', 'Task'))
            except Exception as notif_error:
                logger.error(f"Failed to send completion notification: {notif_error}")

        task_desc = update_data.get('description', existing.get('description', 'Task'))
        return f"✅ Updated '{task_desc}': {', '.join(changes)}"

    except Exception as e:
        logger.error(f"update_action_item_text error: {e}")
        return f"Error updating action item: {e}"
