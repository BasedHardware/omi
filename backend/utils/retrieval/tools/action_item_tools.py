"""
Tools for accessing and managing user action items.
"""

from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.action_items as action_items_db
from utils.notifications import (
    send_action_item_completed_notification,
    send_action_item_created_notification,
    send_action_item_data_message,
)


@tool
def get_action_items_tool(
    limit: int = 50,
    offset: int = 0,
    completed: Optional[bool] = None,
    conversation_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    due_start_date: Optional[str] = None,
    due_end_date: Optional[str] = None,
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
    - Use start_date/end_date to filter by CREATION date (when the task was created)
    - Use due_start_date/due_end_date to filter by DUE date (when the task is due)
    - **IMPORTANT**: When user asks "tasks due this week" or "tasks due today", use due_start_date/due_end_date
    - **IMPORTANT**: When user asks "tasks created today" or "tasks I added yesterday", use start_date/end_date
    - Default limit is 50, which is suitable for most queries
    - Use higher limit (up to 500) for comprehensive task reviews

    Args:
        limit: Number of action items to retrieve (default: 50, max: 500)
        offset: Pagination offset for retrieving additional items (default: 0)
        completed: Filter by completion status (None=all, True=completed, False=pending)
        conversation_id: Filter by conversation ID that generated the action item
        start_date: Filter by creation date - items created after this date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        end_date: Filter by creation date - items created before this date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        due_start_date: Filter by due date - items due after this date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        due_end_date: Filter by due date - items due before this date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)

    Returns:
        Formatted list of action items with their details.
    """
    print(
        f"🔧 get_action_items_tool called - limit: {limit}, offset: {offset}, completed: {completed}, "
        f"conversation_id: {conversation_id}, start_date: {start_date}, end_date: {end_date}, "
        f"due_start_date: {due_start_date}, due_end_date: {due_end_date}"
    )
    uid = config['configurable'].get('user_id')
    if not uid:
        print(f"❌ get_action_items_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    print(f"✅ get_action_items_tool - uid: {uid}, limit: {limit}")

    # Get safety guard from config if available
    safety_guard = config['configurable'].get('safety_guard')

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

    # Parse created_at dates if provided
    start_dt = None
    end_dt = None

    if start_date:
        try:
            if len(start_date) == 10:  # YYYY-MM-DD
                naive_dt = datetime.strptime(start_date, '%Y-%m-%d')
                start_dt = naive_dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=user_tz)
                print(f"📅 Parsed start_date (created_at) '{start_date}' as {start_dt} in {user_timezone_str}")
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
                print(f"📅 Parsed end_date (created_at) '{end_date}' as {end_dt} in {user_timezone_str}")
            else:
                # Parse ISO format - if no timezone, assume user's timezone
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=user_tz)
        except ValueError:
            return f"Error: Invalid end_date format: {end_date}"

    # Parse due_at dates if provided
    due_start_dt = None
    due_end_dt = None

    if due_start_date:
        try:
            if len(due_start_date) == 10:  # YYYY-MM-DD
                naive_dt = datetime.strptime(due_start_date, '%Y-%m-%d')
                due_start_dt = naive_dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=user_tz)
                print(f"📅 Parsed due_start_date '{due_start_date}' as {due_start_dt} in {user_timezone_str}")
            else:
                # Parse ISO format - if no timezone, assume user's timezone
                due_start_dt = datetime.fromisoformat(due_start_date.replace('Z', '+00:00'))
                if due_start_dt.tzinfo is None:
                    due_start_dt = due_start_dt.replace(tzinfo=user_tz)
        except ValueError:
            return f"Error: Invalid due_start_date format: {due_start_date}"

    if due_end_date:
        try:
            if len(due_end_date) == 10:  # YYYY-MM-DD
                naive_dt = datetime.strptime(due_end_date, '%Y-%m-%d')
                due_end_dt = naive_dt.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=user_tz)
                print(f"📅 Parsed due_end_date '{due_end_date}' as {due_end_dt} in {user_timezone_str}")
            else:
                # Parse ISO format - if no timezone, assume user's timezone
                due_end_dt = datetime.fromisoformat(due_end_date.replace('Z', '+00:00'))
                if due_end_dt.tzinfo is None:
                    due_end_dt = due_end_dt.replace(tzinfo=user_tz)
        except ValueError:
            return f"Error: Invalid due_end_date format: {due_end_date}"

    # Get action items
    action_items = []
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
        print(f"❌ Error getting action items: {e}")
        return f"Error retrieving action items: {str(e)}"

    action_items_count = len(action_items) if action_items else 0
    print(f"📊 get_action_items_tool - found {action_items_count} action items")

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
def create_action_item_tool(
    description: str,
    due_at: Optional[str] = None,
    conversation_id: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Create a new action item (task/to-do) for the user.

    Use this tool when:
    - User asks to create a new task or to-do
    - User asks to add something to their task list
    - User says "remind me to...", "I need to...", "add task..."
    - User wants to track something they need to do
    - User mentions a deadline or something due

    **IMPORTANT**: This creates a NEW action item. To update an existing item, use update_action_item_tool instead.

    Examples:
    - "Add a task to buy milk" -> create_action_item_tool(description="Buy milk")
    - "Remind me to call mom tomorrow at 3pm" -> create_action_item_tool(description="Call mom", due_at="2024-01-20T15:00:00")
    - "I need to finish the report by Friday" -> create_action_item_tool(description="Finish the report", due_at="2024-01-19T23:59:59")

    Due date formatting:
    - Use ISO format: YYYY-MM-DDTHH:MM:SS
    - Will be interpreted in user's timezone
    - Example: "2024-01-20T14:30:00" for January 20, 2024 at 2:30 PM
    - If user doesn't specify time, use end of day (23:59:59)

    Args:
        description: The task description (required)
        due_at: Optional due date in ISO format YYYY-MM-DDTHH:MM:SS
        conversation_id: Optional ID of the conversation this task came from

    Returns:
        Confirmation message with the created action item details.
    """
    print(
        f"🔧 create_action_item_tool called - description: {description}, "
        f"due_at: {due_at}, conversation_id: {conversation_id}"
    )
    uid = config['configurable'].get('user_id')
    if not uid:
        print(f"❌ create_action_item_tool - no user_id in config")
        return "Error: User ID not found in configuration"

    # Validate description
    if not description or not description.strip():
        return "Error: Description is required to create an action item."

    # Prepare action item data
    action_item_data = {
        'description': description.strip(),
        'completed': False,
        'conversation_id': conversation_id,
    }

    # Get user timezone
    user_timezone_str = config['configurable'].get('timezone', 'UTC')
    try:
        user_tz = ZoneInfo(user_timezone_str)
    except Exception:
        user_tz = ZoneInfo('UTC')

    # Parse or set due date
    if due_at is not None:
        # Parse provided due date
        try:
            due_dt = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=user_tz)
            action_item_data['due_at'] = due_dt
        except ValueError:
            return f"Error: Invalid due_at format: {due_at}. Use YYYY-MM-DDTHH:MM:SS"
    else:
        # Set default due date to 24 hours from now
        now = datetime.now(user_tz)
        default_due = now + timedelta(hours=24)
        action_item_data['due_at'] = default_due
        print(f"📅 No due date provided, setting default to 24h from now: {default_due}")

    # Create the action item
    try:
        action_item_id = action_items_db.create_action_item(uid, action_item_data)
        if not action_item_id:
            return "Error: Failed to create action item."

        print(f"✅ create_action_item_tool - successfully created action item {action_item_id}")

        # Get the created item for confirmation
        created_item = action_items_db.get_action_item(uid, action_item_id)
        if not created_item:
            return "Action item created, but couldn't retrieve details."

        # Build confirmation message
        result = f"✅ Successfully created action item:\n"
        result += f"Description: {created_item.get('description', 'Unknown')}\n"
        result += f"ID: {created_item.get('id')}\n"
        result += f"Status: Pending\n"

        if created_item.get('created_at'):
            created_at = created_item['created_at']
            result += f"Created: {created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

        if created_item.get('due_at'):
            due = created_item['due_at']
            result += f"Due: {due.strftime('%Y-%m-%d %H:%M:%S')}\n"

            # Send FCM notification for scheduled reminder
            try:
                send_action_item_data_message(
                    user_id=uid,
                    action_item_id=action_item_id,
                    description=created_item.get('description', ''),
                    due_at=due.isoformat(),
                )
                result += "\n📱 Reminder notification scheduled"
            except Exception as notif_error:
                print(f"⚠️ Failed to send notification: {notif_error}")
                # Don't fail the creation if notification fails

        # Send immediate notification that task was created
        try:
            send_action_item_created_notification(uid, created_item.get('description', 'Task'))
            result += "\n📱 Creation notification sent"
        except Exception as notif_error:
            print(f"⚠️ Failed to send creation notification: {notif_error}")
            # Don't fail the creation if notification fails

        return result

    except Exception as e:
        print(f"❌ Error creating action item: {e}")
        return f"Error creating action item: {str(e)}"


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
