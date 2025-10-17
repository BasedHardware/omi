"""
Tools for accessing and managing user action items.
"""

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.action_items as action_items_db
from utils.notifications import send_action_item_completed_notification


@tool
def get_action_items_tool(
    limit: int = 50,
    offset: int = 0,
    completed: Optional[bool] = None,
    conversation_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve the user's action items (tasks, to-dos) with optional filters.

    Action items are tasks or to-dos that have been extracted from the user's conversations
    or manually created. Each action item has a description, completion status, optional due date,
    and may be linked to a conversation.

    Use this tool when:
    - User asks "what are my tasks?" or "show me my to-dos"
    - User wants to see pending or completed action items
    - User asks about tasks from a specific conversation
    - User asks about tasks due in a certain time period
    - User wants to know what they need to do
    - **ALWAYS use this tool when the user asks about their tasks or action items**

    Time filtering guidance:
    - **CRITICAL**: When user asks about action items from relative times ("2 minutes ago", "last hour", "this morning"), you MUST calculate and provide start_date/end_date parameters
    - **IMPORTANT**: Use the current datetime from <current_datetime_utc> in the system prompt to calculate all relative times
    - **DO NOT leave start_date/end_date empty when the user specifies a time period** - always calculate the actual datetime values
    - For exact date queries ("October 16th", "yesterday"), use YYYY-MM-DD format - dates are interpreted in user's timezone
    - For relative time queries at hour/minute level ("2 minutes ago", "30 minutes ago", "2 hours ago"):
      * YOU MUST calculate the exact datetime by subtracting from current time in <current_datetime_utc>
      * Use ISO format without timezone (YYYY-MM-DDTHH:MM:SS) - will be interpreted in user's timezone
      * Example: If current time is 2024-01-15 14:00:00 UTC and user asks "2 hours ago", you MUST use start_date="2024-01-15T12:00:00"
    - For time-of-day queries ("this morning", "this afternoon", "tonight"):
      * Use the current date from <current_datetime_utc> to build the date string
      * "this morning": start_date="YYYY-MM-DDT06:00:00", end_date="YYYY-MM-DDT12:00:00"
      * "this afternoon": start_date="YYYY-MM-DDT12:00:00", end_date="YYYY-MM-DDT18:00:00"
      * "tonight": start_date="YYYY-MM-DDT18:00:00", end_date="YYYY-MM-DDT23:59:59"
    - All dates without explicit timezone are assumed to be in the user's local timezone

    Filtering guidance:
    - Use completed=False to get only pending tasks
    - Use completed=True to get only completed tasks
    - Use conversation_id to get tasks from a specific conversation
    - Use start_date/end_date to filter by creation or due date range
    - Default limit is 50, which is suitable for most queries
    - Use higher limit (up to 500) for comprehensive task reviews

    Args:
        limit: Number of action items to retrieve (default: 50, max: 500)
        offset: Pagination offset for retrieving additional items (default: 0)
        completed: Filter by completion status (None=all, True=completed, False=pending)
        conversation_id: Filter by conversation ID that generated the action item
        start_date: Filter items after this date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        end_date: Filter items before this date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)

    Returns:
        Formatted list of action items with their details.
    """
    print(
        f"🔧 get_action_items_tool called - limit: {limit}, offset: {offset}, completed: {completed}, "
        f"conversation_id: {conversation_id}, start_date: {start_date}, end_date: {end_date}"
    )
    uid = config['configurable'].get('user_id')
    if not uid:
        print(f"❌ get_action_items_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    print(f"✅ get_action_items_tool - uid: {uid}, limit: {limit}")

    # Cap at 500 per call
    if limit > 500:
        print(f"⚠️ get_action_items_tool - limit capped from {limit} to 500")
        limit = 500

    # Get user timezone from config, default to UTC
    user_timezone_str = config['configurable'].get('timezone', 'UTC')
    try:
        user_tz = ZoneInfo(user_timezone_str)
    except Exception:
        user_tz = ZoneInfo('UTC')
    print(f"🌍 get_action_items_tool - user timezone: {user_timezone_str}")

    # Parse dates if provided
    start_dt = None
    end_dt = None

    if start_date:
        try:
            if len(start_date) == 10:  # YYYY-MM-DD
                naive_dt = datetime.strptime(start_date, '%Y-%m-%d')
                start_dt = naive_dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=user_tz)
                print(f"📅 Parsed start_date '{start_date}' as {start_dt} in {user_timezone_str}")
            else:
                # Parse ISO format - if no timezone, assume user's timezone
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=user_tz)
        except ValueError:
            return f"Error: Invalid start_date format: {start_date}"

    if end_date:
        try:
            if len(end_date) == 10:  # YYYY-MM-DD
                naive_dt = datetime.strptime(end_date, '%Y-%m-%d')
                end_dt = naive_dt.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=user_tz)
                print(f"📅 Parsed end_date '{end_date}' as {end_dt} in {user_timezone_str}")
            else:
                # Parse ISO format - if no timezone, assume user's timezone
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=user_tz)
        except ValueError:
            return f"Error: Invalid end_date format: {end_date}"

    # Get action items
    action_items = []
    try:
        action_items = action_items_db.get_action_items(
            uid=uid,
            conversation_id=conversation_id,
            completed=completed,
            start_date=start_dt,
            end_date=end_dt,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        print(f"❌ Error getting action items: {e}")
        return f"Error retrieving action items: {str(e)}"

    action_items_count = len(action_items) if action_items else 0
    print(f"📊 get_action_items_tool - found {action_items_count} action items")

    if not action_items:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" between {start_dt.strftime('%Y-%m-%d')} and {end_dt.strftime('%Y-%m-%d')}"
        elif start_dt:
            date_info = f" after {start_dt.strftime('%Y-%m-%d')}"
        elif end_dt:
            date_info = f" before {end_dt.strftime('%Y-%m-%d')}"

        status_info = ""
        if completed is True:
            status_info = " completed"
        elif completed is False:
            status_info = " pending"

        msg = f"No{status_info} action items found{date_info}."
        print(f"⚠️ get_action_items_tool - {msg}")
        return msg

    # Format action items
    result = f"User Action Items ({len(action_items)} total):\n\n"

    for i, item in enumerate(action_items, 1):
        status = "✅ Completed" if item.get('completed', False) else "⬜ Pending"
        result += f"{i}. [{status}] {item.get('description', 'No description')}\n"

        # Add ID for reference in updates
        result += f"   ID: {item.get('id')}\n"

        # Add dates if available
        if item.get('created_at'):
            created = item['created_at']
            result += f"   Created: {created.strftime('%Y-%m-%d %H:%M:%S')}\n"

        if item.get('due_at'):
            due = item['due_at']
            result += f"   Due: {due.strftime('%Y-%m-%d %H:%M:%S')}\n"

        if item.get('completed_at'):
            completed_at = item['completed_at']
            result += f"   Completed: {completed_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

        if item.get('conversation_id'):
            result += f"   From conversation: {item['conversation_id']}\n"

        result += "\n"

    return result.strip()


@tool
def update_action_item_tool(
    action_item_id: str,
    completed: Optional[bool] = None,
    description: Optional[str] = None,
    due_at: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Update an action item's status, description, or due date.

    Use this tool when:
    - User asks to mark a task as complete/done
    - User asks to mark a task as incomplete/pending
    - User wants to change a task's description
    - User wants to set or change a task's due date
    - User says things like "mark task X as done", "complete the first task", "change task description"

    **CRITICAL**: To update an action item, you MUST first use get_action_items_tool to retrieve the action_item_id.
    The ID is shown in the output of get_action_items_tool.

    Examples:
    - "Mark the first task as complete" -> First call get_action_items_tool, then use the ID from item #1
    - "Complete the task about buying milk" -> First call get_action_items_tool, find the matching task, then use its ID
    - "Change the due date of my meeting task" -> First call get_action_items_tool, find the task, then use its ID

    Due date formatting:
    - Use ISO format: YYYY-MM-DDTHH:MM:SS
    - Will be interpreted in user's timezone
    - Example: "2024-01-20T14:30:00" for January 20, 2024 at 2:30 PM

    Args:
        action_item_id: The ID of the action item to update (get this from get_action_items_tool)
        completed: Set completion status (True=completed, False=pending, None=no change)
        description: New description for the action item (None=no change)
        due_at: New due date in ISO format YYYY-MM-DDTHH:MM:SS (None=no change)

    Returns:
        Confirmation message about the update.
    """
    print(
        f"🔧 update_action_item_tool called - action_item_id: {action_item_id}, "
        f"completed: {completed}, description: {description}, due_at: {due_at}"
    )
    uid = config['configurable'].get('user_id')
    if not uid:
        print(f"❌ update_action_item_tool - no user_id in config")
        return "Error: User ID not found in configuration"

    # Check if action item exists
    existing_item = action_items_db.get_action_item(uid, action_item_id)
    if not existing_item:
        return f"Error: Action item with ID '{action_item_id}' not found. Please use get_action_items_tool first to get the correct ID."

    # Prepare update data
    update_data = {}
    changes = []

    if completed is not None:
        update_data['completed'] = completed
        if completed:
            update_data['completed_at'] = datetime.now(datetime.now().astimezone().tzinfo)
            changes.append("marked as completed")
        else:
            update_data['completed_at'] = None
            changes.append("marked as pending")

    if description is not None:
        update_data['description'] = description
        changes.append(f"description updated to '{description}'")

    if due_at is not None:
        try:
            # Parse due date
            user_timezone_str = config['configurable'].get('timezone', 'UTC')
            try:
                user_tz = ZoneInfo(user_timezone_str)
            except Exception:
                user_tz = ZoneInfo('UTC')

            due_dt = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=user_tz)

            update_data['due_at'] = due_dt
            changes.append(f"due date set to {due_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        except ValueError:
            return f"Error: Invalid due_at format: {due_at}. Use YYYY-MM-DDTHH:MM:SS"

    if not update_data:
        return "No changes specified. Please provide at least one field to update (completed, description, or due_at)."

    # Update the action item
    try:
        success = action_items_db.update_action_item(uid, action_item_id, update_data)
        if not success:
            return f"Error: Failed to update action item with ID '{action_item_id}'."

        print(f"✅ update_action_item_tool - successfully updated action item {action_item_id}")

        # Get updated item for confirmation
        updated_item = action_items_db.get_action_item(uid, action_item_id)
        result = f"Successfully updated action item: {updated_item.get('description', 'Unknown')}\n"
        result += f"Changes: {', '.join(changes)}"

        # Send notification if item was marked as completed
        if completed is True:
            try:
                send_action_item_completed_notification(uid, updated_item.get('description', 'Task'))
            except Exception as notif_error:
                print(f"⚠️ Failed to send completion notification: {notif_error}")
                # Don't fail the update if notification fails

        return result

    except Exception as e:
        print(f"❌ Error updating action item: {e}")
        return f"Error updating action item: {str(e)}"
