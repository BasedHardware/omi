"""
Tools for accessing and managing user action items.
"""

from datetime import datetime, timedelta
from typing import Optional
import contextvars

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.action_items as action_items_db
from utils.notifications import (
    send_action_item_completed_notification,
    send_action_item_created_notification,
    send_action_item_data_message,
)

# Import agent_config_context for fallback config access
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


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
    - User asks "what are my tasks?" or "show me my to-dos" or "what should i focus on"
    - User wants to see pending or completed action items
    - User asks about tasks from a specific conversation
    - User asks about tasks due in a certain time period
    - User wants to know what they need to do
    - **ALWAYS use this tool when the user asks about their tasks or action items**

    Filtering guidance:
    - **CRITICAL**: By default, ALWAYS use due_start_date/due_end_date (DUE dates) for time-based queries
    - **ONLY use start_date/end_date (CREATION dates) when the user explicitly asks about when tasks were created**

    Date parameter priority:
    1. **PRIMARY (use by default)**: due_start_date/due_end_date for filtering by when tasks are DUE
       - "tasks for today" → use due_start_date/due_end_date for today
       - "tasks this week" → use due_start_date/due_end_date for this week
       - "what do I need to do tomorrow" → use due_start_date/due_end_date for tomorrow
       - "upcoming tasks" → use due_start_date/due_end_date

    2. **SECONDARY (only when explicitly requested)**: start_date/end_date for filtering by CREATION date
       - "tasks I created today" → use start_date/end_date for today
       - "tasks I added yesterday" → use start_date/end_date for yesterday
       - "tasks created this week" → use start_date/end_date for this week

    Other filters:
    - Use completed=False to get only pending tasks (default for most queries)
    - Use completed=True to get only completed tasks
    - Use conversation_id to get tasks from a specific conversation
    - Default limit is 50, which is suitable for most queries
    - Use higher limit (up to 500) for comprehensive task reviews

    Args:
        limit: Number of action items to retrieve (default: 50, max: 500)
        offset: Pagination offset for retrieving additional items (default: 0)
        completed: Filter by completion status (None=all, True=completed, False=pending)
        conversation_id: Filter by conversation ID that generated the action item
        start_date: Filter by creation date - items created after this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T15:00:00-08:00")
        end_date: Filter by creation date - items created before this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T23:59:59-08:00")
        due_start_date: Filter by due date - items due after this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T15:00:00-08:00")
        due_end_date: Filter by due date - items due before this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T23:59:59-08:00")

    Returns:
        Formatted list of action items with their details.
    """
    print(f"🚀 get_action_items_tool START - limit: {limit}, offset: {offset}, completed: {completed}")
    print(
        f"🔧 get_action_items_tool called - limit: {limit}, offset: {offset}, completed: {completed}, "
        f"conversation_id: {conversation_id}, start_date: {start_date}, end_date: {end_date}, "
        f"due_start_date: {due_start_date}, due_end_date: {due_end_date}"
    )

    # Get config from parameter or context variable (like other tools do)
    if config is None:
        try:
            config = agent_config_context.get()
            if config:
                print(f"🔧 get_action_items_tool - got config from context variable")
        except LookupError:
            print(f"❌ get_action_items_tool - config not found in context variable")
            config = None

    # Safely access config
    try:
        if config is None:
            print(f"❌ get_action_items_tool - config is None")
            return "Error: Configuration not available"

        if 'configurable' not in config:
            print(
                f"❌ get_action_items_tool - config['configurable'] not found. Config keys: {list(config.keys()) if config else 'None'}"
            )
            return "Error: Configuration format invalid"

        uid = config['configurable'].get('user_id')
        if not uid:
            print(
                f"❌ get_action_items_tool - no user_id in config. Configurable keys: {list(config['configurable'].keys()) if config.get('configurable') else 'None'}"
            )
            return "Error: User ID not found in configuration"

        print(f"✅ get_action_items_tool - uid: {uid}, limit: {limit}")
    except Exception as config_error:
        print(f"❌ get_action_items_tool - error accessing config: {config_error}")
        import traceback

        traceback.print_exc()
        return f"Error: Configuration error - {str(config_error)}"

    # Get safety guard from config if available
    safety_guard = config['configurable'].get('safety_guard')

    # Cap at 500 per call
    if limit > 500:
        print(f"⚠️ get_action_items_tool - limit capped from {limit} to 500")
        limit = 500

    # Parse created_at dates if provided (must be ISO format with timezone)
    start_dt = None
    end_dt = None

    if start_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if start_dt.tzinfo is None:
                return f"Error: start_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T15:00:00-08:00'): {start_date}"
            print(f"📅 Parsed start_date '{start_date}' as {start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {start_date} - {str(e)}"

    if end_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                return f"Error: end_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T23:59:59-08:00'): {end_date}"
            print(f"📅 Parsed end_date '{end_date}' as {end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {end_date} - {str(e)}"

    # Parse due_at dates if provided
    due_start_dt = None
    due_end_dt = None

    if due_start_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            due_start_dt = datetime.fromisoformat(due_start_date.replace('Z', '+00:00'))
            if due_start_dt.tzinfo is None:
                return f"Error: due_start_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T15:00:00-08:00'): {due_start_date}"
            print(f"📅 Parsed due_start_date '{due_start_date}' as {due_start_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid due_start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {due_start_date} - {str(e)}"

    if due_end_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            due_end_dt = datetime.fromisoformat(due_end_date.replace('Z', '+00:00'))
            if due_end_dt.tzinfo is None:
                return f"Error: due_end_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T23:59:59-08:00'): {due_end_date}"
            print(f"📅 Parsed due_end_date '{due_end_date}' as {due_end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid due_end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {due_end_date} - {str(e)}"

    # Get action items
    action_items = []
    try:
        print(f"🔍 Calling action_items_db.get_action_items with:")
        print(f"   uid: {uid}")
        print(f"   conversation_id: {conversation_id}")
        print(f"   completed: {completed}")
        print(f"   start_date: {start_dt}")
        print(f"   end_date: {end_dt}")
        print(f"   due_start_date: {due_start_dt}")
        print(f"   due_end_date: {due_end_dt}")
        print(f"   limit: {limit}")
        print(f"   offset: {offset}")

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

        print(f"🔍 Database call completed - received {len(action_items) if action_items else 0} items")
    except Exception as e:
        print(f"❌ Error getting action items: {e}")
        import traceback

        traceback.print_exc()
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
        print(f"✅ get_action_items_tool END - returning early (no items found)")
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

    print(f"✅ get_action_items_tool END - returning {len(action_items)} items")
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

    **ONLY use this tool when user EXPLICITLY asks to create a task:**
    - "add task...", "create a task...", "remind me to..."
    - "add to my list...", "add these tasks..."
    - "I need to do X tomorrow" (clear commitment language)

    **DO NOT use this tool when:**
    - User asks a question ("how would this help?", "what do you think?")
    - User acknowledges something ("nice", "I like it", "sounds good")
    - You're giving advice or suggestions
    - User is exploring ideas without committing to action

    **Task description rules:**
    - Keep descriptions SHORT: 5-10 words max
    - Just the action, no explanations
    - Good: "Ship mentor to production"
    - Bad: "Ship mentor to production - Make the mentor/goal-tracking flow usable end-to-end"

    Args:
        description: Short task description (5-10 words, just the action)
        due_at: Optional due date (ISO format with timezone: YYYY-MM-DDTHH:MM:SS+HH:MM)
        conversation_id: Optional conversation ID this task came from

    Returns:
        Brief confirmation message.
    """
    print(
        f"🔧 create_action_item_tool called - description: {description}, "
        f"due_at: {due_at}, conversation_id: {conversation_id}"
    )

    # Get config from parameter or context variable (like other tools do)
    if config is None:
        try:
            config = agent_config_context.get()
            if config:
                print(f"🔧 create_action_item_tool - got config from context variable")
        except LookupError:
            print(f"❌ create_action_item_tool - config not found in context variable")
            config = None

    if config is None:
        print(f"❌ create_action_item_tool - config is None")
        return "Error: Configuration not available"

    try:
        uid = config['configurable'].get('user_id')
    except (KeyError, TypeError) as e:
        print(f"❌ create_action_item_tool - error accessing config: {e}")
        return "Error: Configuration not available"

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

    # Parse or set due date
    if due_at is not None:
        # Parse provided due date (must be ISO format with timezone)
        try:
            due_dt = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
            if due_dt.tzinfo is None:
                return f"Error: due_at must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T14:30:00-08:00'): {due_at}"
            action_item_data['due_at'] = due_dt
        except ValueError as e:
            return f"Error: Invalid due_at format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {due_at} - {str(e)}"
    else:
        # Set default due date to 24 hours from now in UTC
        now = datetime.now(datetime.now().astimezone().tzinfo)
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

        # Build concise confirmation message
        task_desc = created_item.get('description', 'Task')
        result = f"✅ Added: {task_desc}"

        if created_item.get('due_at'):
            due = created_item['due_at']
            result += f" (due {due.strftime('%b %d')})"

            # Send FCM notification for scheduled reminder
            try:
                send_action_item_data_message(
                    user_id=uid,
                    action_item_id=action_item_id,
                    description=task_desc,
                    due_at=due.isoformat(),
                )
            except Exception as notif_error:
                print(f"⚠️ Failed to send notification: {notif_error}")

        # Send immediate notification that task was created
        try:
            send_action_item_created_notification(uid, task_desc)
        except Exception as notif_error:
            print(f"⚠️ Failed to send creation notification: {notif_error}")

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
    - Use ISO format with timezone: YYYY-MM-DDTHH:MM:SS+HH:MM
    - Example: "2024-01-20T14:30:00-08:00" for January 20, 2024 at 2:30 PM in PST

    Args:
        action_item_id: The ID of the action item to update (get this from get_action_items_tool)
        completed: Set completion status (True=completed, False=pending, None=no change)
        description: New description for the action item (None=no change)
        due_at: New due date in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-20T14:30:00-08:00") (None=no change)

    Returns:
        Confirmation message about the update.
    """
    print(
        f"🔧 update_action_item_tool called - action_item_id: {action_item_id}, "
        f"completed: {completed}, description: {description}, due_at: {due_at}"
    )

    # Get config from parameter or context variable (like other tools do)
    if config is None:
        try:
            config = agent_config_context.get()
            if config:
                print(f"🔧 update_action_item_tool - got config from context variable")
        except LookupError:
            print(f"❌ update_action_item_tool - config not found in context variable")
            config = None

    if config is None:
        print(f"❌ update_action_item_tool - config is None")
        return "Error: Configuration not available"

    try:
        uid = config['configurable'].get('user_id')
    except (KeyError, TypeError) as e:
        print(f"❌ update_action_item_tool - error accessing config: {e}")
        return "Error: Configuration not available"

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
            # Parse due date (must be ISO format with timezone)
            due_dt = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
            if due_dt.tzinfo is None:
                return f"Error: due_at must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T14:30:00-08:00'): {due_at}"

            update_data['due_at'] = due_dt
            changes.append(f"due date set to {due_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except ValueError as e:
            return f"Error: Invalid due_at format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {due_at} - {str(e)}"

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
