"""
Tools for accessing and managing user action items.
"""

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Dict, List, Optional, Tuple, cast
import contextvars

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from langchain_core.runnables import RunnableConfig

from utils.messaging.undo import record_write
from utils.messaging.projection import surface_runtime
from utils.messaging.turn_context import phone_reminder_confirmation
from config.action_item_reminder_triggers import action_item_write_affects_reminder
import database.action_items as action_items_db
from utils.notifications import (
    send_action_item_completed_notification,
    send_action_item_created_notification,
    send_action_item_data_message,
    sync_action_item_reminder,
)
from utils.model_text import count_header, format_date, format_instant, truncation_note
from utils.user_clock import clock_for_config
from utils.retrieval.chat_scope import apply_chat_scope_dates, chat_scope_from_config
from utils.retrieval.turn_refs import register_record_ref, resolve_edit_ref
import logging

logger = logging.getLogger(__name__)

# Import agent_config_context for fallback config access
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


# Bound the chat tool result so a broad request ("show me all my tasks") cannot flood the chat
# model's context and make it freeze or refuse (issue #4927; the same fix already shipped for the
# conversations tool in #8503). A single page can hold up to 500 items, each rendered over several
# lines, which runs to tens of thousands of characters, so cap both the row count and the raw
# character size and tell the model to summarize what it has and offer to narrow.
MAX_ACTION_ITEMS_FOR_LLM = 200
MAX_RESULT_CHARS = 60000


def _cap_action_items_for_llm(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    """Keep at most ``MAX_ACTION_ITEMS_FOR_LLM`` action items for the chat model.

    Items arrive in the order the database returned them, so this keeps the first ones. Returns
    ``(capped_list, truncated)`` where ``truncated`` is True when some rows were dropped.
    """
    if len(items) > MAX_ACTION_ITEMS_FOR_LLM:
        return items[:MAX_ACTION_ITEMS_FOR_LLM], True
    return list(items), False


def _bounded_action_items_result(result: str, truncated: bool, order: str = "database order") -> str:
    """Apply a hard character budget and, when the set was truncated, append a note telling the
    model to summarize what it has and to offer to narrow, so it answers instead of freezing.

    The note deliberately does not claim a total count: the database query is capped by ``limit``,
    so the rows in hand are a page and not necessarily the full set, and stating a total would
    mislead. When clipping for size, cut back to the last complete line so a record is not sliced
    mid-field.
    """
    if len(result) > MAX_RESULT_CHARS:
        clipped = result[:MAX_RESULT_CHARS]
        boundary = clipped.rfind("\n")
        result = clipped[:boundary] if boundary > 0 else clipped
        truncated = True
    if truncated:
        result += "\n\n" + truncation_note(
            shown=len(re.findall(r"(?m)^\d+\. \[", result)),
            total=None,
            cut=True,
            unit="action items",
            how_to_get_more=f"Rows are ordered {order}. Ask for a narrower topic or date range, or page with the offset.",
        )
    return result


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
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
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
    - Prefer date or status filters over a large limit: only the most relevant items are returned to
      stay within the chat context, and a broad pull is summarized rather than listed in full

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
    logger.info(f"🚀 get_action_items_tool START - limit: {limit}, offset: {offset}, completed: {completed}")
    logger.info(
        f"🔧 get_action_items_tool called - limit: {limit}, offset: {offset}, completed: {completed}, "
        f"conversation_id: {conversation_id}, start_date: {start_date}, end_date: {end_date}, "
        f"due_start_date: {due_start_date}, due_end_date: {due_end_date}"
    )

    # Get config from parameter or context variable (like other tools do)
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        try:
            ctx_cfg: object = agent_config_context.get()
            if ctx_cfg:
                cfg = cast(Optional[Dict[str, Any]], ctx_cfg)
                logger.info(f"🔧 get_action_items_tool - got config from context variable")
        except LookupError:
            logger.warning(f"❌ get_action_items_tool - config not found in context variable")
            cfg = None

    # Safely access config
    try:
        if cfg is None:
            logger.info(f"❌ get_action_items_tool - config is None")
            return "Error: Configuration not available"

        if 'configurable' not in cfg:
            logger.info(
                f"❌ get_action_items_tool - config['configurable'] not found. Config keys: {list(cfg.keys()) if cfg else 'None'}"
            )
            return "Error: Configuration format invalid"

        configurable: Any = cfg.get('configurable')
        uid = configurable.get('user_id')
        if not uid:
            logger.info(
                f"❌ get_action_items_tool - no user_id in config. Configurable keys: {list(configurable.keys()) if configurable else 'None'}"
            )
            return "Error: User ID not found in configuration"
        clock = clock_for_config(cfg, uid)

        logger.info(f"✅ get_action_items_tool - uid: {uid}, limit: {limit}")
    except Exception as config_error:
        logger.error(f"❌ get_action_items_tool - error accessing config: {config_error}", exc_info=True)
        return "Error: Configuration error."

    # Hard-scope: force conversation_id and intersect creation dates with chat_scope (#4515).
    scope = chat_scope_from_config(configurable)
    if scope and scope.get("conversation_id"):
        scoped_cid = str(scope["conversation_id"])
        if conversation_id and conversation_id != scoped_cid:
            return (
                f"Error: Chat is scoped to conversation {scoped_cid}. "
                "Action items outside that conversation are unavailable."
            )
        conversation_id = scoped_cid
    start_date, end_date, scope_err = apply_chat_scope_dates(scope, start_date, end_date)
    if scope_err:
        return f"Error: {scope_err}"

    # Cap at 500 per call
    if limit > 500:
        logger.info(f"⚠️ get_action_items_tool - limit capped from {limit} to 500")
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
            logger.info("Parsed action-item start_date")
        except ValueError:
            return (
                f"Error: Invalid start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {start_date}"
            )

    if end_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                return f"Error: end_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T23:59:59-08:00'): {end_date}"
            logger.info("Parsed action-item end_date")
        except ValueError:
            return f"Error: Invalid end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {end_date}"

    # Parse due_at dates if provided
    due_start_dt = None
    due_end_dt = None

    if due_start_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            due_start_dt = datetime.fromisoformat(due_start_date.replace('Z', '+00:00'))
            if due_start_dt.tzinfo is None:
                return f"Error: due_start_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T15:00:00-08:00'): {due_start_date}"
            logger.info("Parsed action-item due_start_date")
        except ValueError:
            return f"Error: Invalid due_start_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {due_start_date}"

    if due_end_date:
        try:
            # Parse ISO format with timezone - should be in user's timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)
            due_end_dt = datetime.fromisoformat(due_end_date.replace('Z', '+00:00'))
            if due_end_dt.tzinfo is None:
                return f"Error: due_end_date must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-19T23:59:59-08:00'): {due_end_date}"
            logger.info("Parsed action-item due_end_date")
        except ValueError:
            return f"Error: Invalid due_end_date format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {due_end_date}"

    # Get action items
    action_items: List[Dict[str, Any]] = []
    try:
        logger.info(f"🔍 Calling action_items_db.get_action_items with:")
        logger.info(f"   uid: {uid}")
        logger.info(f"   conversation_id: {conversation_id}")
        logger.info(f"   completed: {completed}")
        logger.info(f"   start_date: {start_dt}")
        logger.info(f"   end_date: {end_dt}")
        logger.info(f"   due_start_date: {due_start_dt}")
        logger.info(f"   due_end_date: {due_end_dt}")
        logger.info(f"   limit: {limit}")
        logger.info(f"   offset: {offset}")

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

        logger.info(f"🔍 Database call completed - received {len(action_items) if action_items else 0} items")
    except Exception as e:
        logger.error(f"❌ Error getting action items: {e}", exc_info=True)
        return "Error retrieving action items. Please try again."

    action_items_count = len(action_items) if action_items else 0
    logger.info(f"📊 get_action_items_tool - found {action_items_count} action items")

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

        msg = f"No{status_info} action items found{date_info}."
        logger.info(f"⚠️ get_action_items_tool - {msg}")
        logger.info(f"✅ get_action_items_tool END - returning early (no items found)")
        return msg

    # Bound how much goes back to the chat model so a broad request cannot overflow its context
    # (issue #4927). A full page (len == limit) may mean more rows exist beyond it, so flag the
    # result as truncated in that case too, not only when the per-call row cap trims it.
    more_in_db = len(action_items) >= limit
    action_items, capped_for_llm = _cap_action_items_for_llm(action_items)
    results_truncated = capped_for_llm or more_in_db

    # Format action items. Render timestamps in the user's local timezone so the
    # chat model labels the time of day correctly (issue #4643). A timezone lookup
    # failure must never abort retrieval, so fall back to UTC formatting.
    order = (
        "pending first, soonest due date first, newest created first (undated last)"
        if completed is None
        else "soonest due date first, newest created first (undated last)"
    )
    header = (
        count_header("Action items", shown=len(action_items), order=order, more_may_exist=results_truncated) + "\n\n"
    )
    result = header
    shown = 0

    for i, item in enumerate(action_items, 1):
        previous_result = result
        status = "✅ Completed" if item.get('completed', False) else "⬜ Pending"
        result += f"{i}. [{status}] {item.get('description', 'No description')}\n"

        # Add ID for reference in updates
        result += f"   ID: {item.get('id')}\n"

        # Add dates if available (rendered in the user's local timezone)
        if item.get('created_at'):
            result += f"   Created: {format_instant(item['created_at'], clock)}\n"

        if item.get('due_at'):
            result += f"   Due: {format_instant(item['due_at'], clock)}\n"

        if item.get('completed_at'):
            result += f"   Completed: {format_instant(item['completed_at'], clock)}\n"

        if item.get('conversation_id'):
            result += f"   From conversation: {item['conversation_id']}\n"

        result += "\n"
        if len(result) > MAX_RESULT_CHARS:
            result = previous_result
            results_truncated = True
            break
        register_record_ref(configurable, 'tasks', item.get('id'))
        shown += 1
        channel_items = configurable.get('channel_items')
        if item.get('id') and isinstance(channel_items, list):
            channel_items.append({'kind': 'task', 'id': item['id'], 'title': item.get('description', 'Task')})

    final_header = count_header("Action items", shown=shown, order=order, more_may_exist=results_truncated) + "\n\n"
    result = final_header + result[len(header) :]
    logger.info(f"✅ get_action_items_tool END - returning {shown} items")
    return _bounded_action_items_result(result.strip(), results_truncated, order=order)


@tool
def create_action_item_tool(
    description: str,
    due_at: Optional[str] = None,
    conversation_id: Optional[str] = None,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
    *,
    due_in_minutes: Optional[int] = None,
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
        due_in_minutes: Relative reminder interval; anchored to original message time on channels. Do not also pass due_at.
        conversation_id: Optional conversation ID this task came from

    Returns:
        Brief confirmation message.
    """
    logger.info('create_action_item_tool called')

    # Get config from parameter or context variable (like other tools do)
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        try:
            ctx_cfg: object = agent_config_context.get()
            if ctx_cfg:
                cfg = cast(Optional[Dict[str, Any]], ctx_cfg)
                logger.info(f"🔧 create_action_item_tool - got config from context variable")
        except LookupError:
            logger.warning(f"❌ create_action_item_tool - config not found in context variable")
            cfg = None

    if cfg is None:
        logger.info(f"❌ create_action_item_tool - config is None")
        return "Error: Configuration not available"

    try:
        configurable: Any = cfg.get('configurable')
        uid = configurable.get('user_id')
    except (KeyError, TypeError, AttributeError) as e:
        logger.error(f"❌ create_action_item_tool - error accessing config: {e}", exc_info=True)
        return "Error: Configuration not available"

    if not uid:
        logger.info(f"❌ create_action_item_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    clock = clock_for_config(cfg, uid)

    # Validate description
    if not description or not description.strip():
        return "Error: Description is required to create an action item."
    # Prepare action item data
    action_item_data: Dict[str, Any] = {
        'description': description.strip(),
        'completed': False,
        'conversation_id': conversation_id,
    }

    runtime = surface_runtime.get()
    channel = runtime is not None and runtime.surface != 'app'
    display_tz = configurable.get('user_timezone') or 'UTC'
    anchored_relative = False
    if due_in_minutes is not None:
        # The model can pass a bool or a non-int despite the annotation.
        minutes: Any = due_in_minutes
        if due_at is not None or type(minutes) is not int or minutes <= 0 or minutes > 366 * 24 * 60:
            return 'Error: Use a positive due_in_minutes or an absolute due_at, not both.'
        anchor = runtime.request_at if channel and runtime is not None else datetime.now(timezone.utc)
        if anchor is None:
            return 'Error: Original message time unavailable. Ask for an explicit reminder time.'
        anchored_relative = channel
        due_at = (anchor + timedelta(minutes=minutes)).isoformat()  # not-model-facing: database timestamp input

    # Parse or set due date
    if due_at is not None:
        # Parse provided due date (must be ISO format with timezone)
        try:
            due_dt = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
            if due_dt.tzinfo is None:
                return f"Error: due_at must include timezone in user's timezone format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T14:30:00-08:00'): {due_at}"
            # Reject due dates more than 1 day in the past (allow 1-day grace for timezone differences).
            # A channel relative reminder keeps the original due instant. Asking for a
            # future date is what shifted a delayed reminder onto processing time.
            now_utc = datetime.now(timezone.utc)
            if due_dt < now_utc - timedelta(days=1) and not anchored_relative:
                logger.warning('create_action_item_tool rejected past due_at')
                return (
                    f"Error: due_at '{due_at}' is in the past. "
                    f"The current time is {format_instant(now_utc, clock)}. "
                    "Please use a future date for the due date."
                )
            action_item_data['due_at'] = due_dt
        except ValueError:
            return f"Error: Invalid due_at format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {due_at}"
    else:
        # A task the user never dated has no due date. Inventing now+24h put it in
        # neither the overdue nor the due-today bucket any reader uses, so
        # "remind me to X" followed by "what's on my list" deterministically
        # returned nothing. `due_at` is Optional everywhere; leave it unset.
        logger.info("📅 No due date provided, leaving due_at unset")

    # Create the action item
    try:
        action_item_id = action_items_db.create_action_item(uid, action_item_data)
        if not action_item_id:
            return "Error: Failed to create action item."

        logger.info(f"✅ create_action_item_tool - successfully created action item {action_item_id}")

        # Get the created item for confirmation
        created_item = action_items_db.get_action_item(uid, action_item_id)
        if not created_item:
            return "Action item created, but couldn't retrieve details."

        # Build concise confirmation message
        task_desc = created_item.get('description', 'Task')
        result = f"✅ Added: {task_desc}"
        reminder_state = None

        if created_item.get('due_at'):
            due = created_item['due_at']
            result += f" (due {format_instant(due, clock)})"

            # Send FCM notification for scheduled reminder
            try:
                if channel and due <= datetime.now(timezone.utc):
                    reminder_state = 'late'
                else:
                    send_action_item_data_message(
                        user_id=uid,
                        action_item_id=action_item_id,
                        description=task_desc,
                        due_at=due.isoformat(),  # not-model-facing: client notification payload
                        completed=bool(created_item.get('completed')),
                        status=created_item.get('status'),
                        deleted=bool(created_item.get('deleted')),
                    )
                    reminder_state = 'requested'
            except Exception as notif_error:
                reminder_state = 'failed'
                logger.error(f"⚠️ Failed to send notification: {notif_error}")

        receipt_data = dict(created_item)
        if channel and reminder_state:
            confirmation = phone_reminder_confirmation(created_item['due_at'], display_tz, reminder_state)
            result += '. ' + confirmation
            receipt_data['_channel_reminder_confirmation'] = confirmation
        result += record_write(uid, 'task', action_item_id, None, receipt_data)

        # Send immediate notification that task was created
        try:
            send_action_item_created_notification(uid, task_desc)
        except Exception as notif_error:
            logger.error(f"⚠️ Failed to send creation notification: {notif_error}")

        return result

    except Exception as e:
        logger.error(f"❌ Error creating action item: {e}", exc_info=True)
        return "Error creating action item. Please try again."


@tool
def update_action_item_tool(
    action_item_id: str,
    completed: Optional[bool] = None,
    description: Optional[str] = None,
    due_at: Optional[str] = None,
    delete: bool = False,
    clear_due_date: bool = False,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Update or soft-delete a task only when the user asks or confirms a proposed correction.
    Deletion is reversible. clear_due_date removes a due date.

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
    logger.info(
        f"🔧 update_action_item_tool called - action_item_id: {action_item_id}, "
        f"completed: {completed}, description: {description}, due_at: {due_at}"
    )

    # Get config from parameter or context variable (like other tools do)
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        try:
            ctx_cfg: object = agent_config_context.get()
            if ctx_cfg:
                cfg = cast(Optional[Dict[str, Any]], ctx_cfg)
                logger.info(f"🔧 update_action_item_tool - got config from context variable")
        except LookupError:
            logger.warning(f"❌ update_action_item_tool - config not found in context variable")
            cfg = None

    if cfg is None:
        logger.info(f"❌ update_action_item_tool - config is None")
        return "Error: Configuration not available"

    try:
        configurable: Any = cfg.get('configurable')
        uid = configurable.get('user_id')
    except (KeyError, TypeError, AttributeError) as e:
        logger.error(f"❌ update_action_item_tool - error accessing config: {e}", exc_info=True)
        return "Error: Configuration not available"

    if not uid:
        logger.info(f"❌ update_action_item_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    clock = clock_for_config(cfg, uid)

    # Check if action item exists
    resolved_id, ref_error = resolve_edit_ref(configurable, 'tasks', action_item_id, parameter='action_item_id')
    if ref_error:
        return ref_error
    assert resolved_id is not None
    action_item_id = resolved_id
    existing_item = action_items_db.get_action_item(uid, action_item_id)
    if not existing_item:
        return f"Error: Action item with ID '{action_item_id}' not found. Please use get_action_items_tool first to get the correct ID."

    # Prepare update data
    update_data: Dict[str, Any] = {}
    changes: List[str] = []

    if delete:
        update_data.update(deleted=True, deleted_at=datetime.now(timezone.utc))
        changes.append('deleted')
    if clear_due_date:
        update_data['due_at'] = None
        changes.append('due date removed')

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
            # Reject due dates more than 1 day in the past (allow 1-day grace for timezone differences)
            now_utc = datetime.now(timezone.utc)
            if due_dt < now_utc - timedelta(days=1):
                logger.warning("⚠️ update_action_item_tool - rejected past due_at")
                return (
                    f"Error: due_at '{due_at}' is in the past. "
                    f"The current time is {format_instant(now_utc, clock)}. "
                    "Please use a future date for the due date."
                )

            update_data['due_at'] = due_dt
            changes.append(f"due date set to {format_instant(due_dt, clock)}")
        except ValueError:
            return f"Error: Invalid due_at format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM in user's timezone: {due_at}"

    if not update_data:
        return "No changes specified. Please provide at least one field to update (completed, description, or due_at)."

    # Import mutation storage only for writes; retrieval and tool schemas need no client.
    from database import chat_edits
    from database.chat_edits import envelope

    # Update the action item
    try:
        before_snapshot = chat_edits.snapshot(uid, 'task', action_item_id)
        write_state = {'before': before_snapshot}
        success = action_items_db.update_action_item(uid, action_item_id, update_data, expected_chat_state=write_state)
        if not success:
            return f"Error: Failed to update action item with ID '{action_item_id}'."

        logger.info(f"✅ update_action_item_tool - successfully updated action item {action_item_id}")

        # Get updated item for confirmation
        updated_item = action_items_db.get_action_item(uid, action_item_id)
        if not updated_item:
            return f"Successfully updated action item '{action_item_id}', but couldn't retrieve details."
        result = f"Successfully updated action item: {updated_item.get('description', 'Unknown')}\n"
        result += f"Changes: {', '.join(changes)}"
        result += record_write(
            uid,
            'task',
            action_item_id,
            envelope(before_snapshot, existing_item.get('description', 'Task')),
            envelope(write_state['after'], updated_item.get('description', 'Task')),
        )

        # Send notification if item was marked as completed
        if completed is True:
            try:
                send_action_item_completed_notification(uid, updated_item.get('description', 'Task'))
            except Exception as notif_error:
                logger.error(f"⚠️ Failed to send completion notification: {notif_error}")
                # Don't fail the update if notification fails

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
                logger.error(f"⚠️ Failed to sync action item reminder: {notif_error}")

        return result

    except Exception as e:
        logger.error(f"❌ Error updating action item: {e}", exc_info=True)
        return "Error updating action item. Please try again."
