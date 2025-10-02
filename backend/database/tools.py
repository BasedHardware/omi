from datetime import datetime
from typing import List, Optional

from database.memories import get_memories as db_get_memories
from database.conversations import get_conversations as db_get_conversations
from database.action_items import get_action_items as db_get_action_items


def get_memories_tool(
    uid: str,
    dates_range: Optional[List[datetime]] = None,
    length: Optional[int] = None,
) -> str:
    """
    Retrieve user memories (known facts about the user).

    Args:
        uid: User ID (required)
        dates_range: [start_date, end_date] optional date filtering
        length: Number of memories to retrieve (optional, defaults to 10)

    Returns:
        Formatted string of memories
    """
    try:
        limit = length if length else 10
        start_date = dates_range[0] if dates_range and len(dates_range) >= 1 else None
        end_date = dates_range[1] if dates_range and len(dates_range) >= 2 else None

        memories = db_get_memories(uid, limit=limit, offset=0, start_date=start_date, end_date=end_date)

        if not memories:
            return "No memories found for the given criteria."

        # Format memories as a string
        result = f"Retrieved {len(memories)} memories:\n\n"
        for i, mem in enumerate(memories, 1):
            content = mem.get('content', 'N/A')
            category = mem.get('category', 'N/A')
            created_at = mem.get('created_at', '')
            if created_at:
                created_str = created_at.strftime('%Y-%m-%d') if hasattr(created_at, 'strftime') else str(created_at)
            else:
                created_str = 'N/A'
            result += f"{i}. [{category}] {content}\n   (Created: {created_str})\n\n"

        return result.strip()
    except Exception as e:
        print(f"Error in get_memories_tool: {e}")
        return f"Error retrieving memories: {str(e)}"


def get_conversations_tool(
    uid: str,
    dates_range: Optional[List[datetime]] = None,
    length: Optional[int] = None,
) -> str:
    """
    Retrieve user conversations and meeting transcripts.

    Args:
        uid: User ID (required)
        dates_range: [start_date, end_date] optional date filtering
        length: Number of conversations to retrieve (optional, defaults to 10)

    Returns:
        Formatted string of conversations
    """
    try:
        limit = length if length else 10
        start_date = dates_range[0] if dates_range and len(dates_range) >= 1 else None
        end_date = dates_range[1] if dates_range and len(dates_range) >= 2 else None

        conversations = db_get_conversations(
            uid, limit=limit, offset=0, include_discarded=False, start_date=start_date, end_date=end_date
        )

        if not conversations:
            return "No conversations found for the given criteria."

        # Format conversations as a string (metadata only, not full transcripts)
        result = f"Retrieved {len(conversations)} conversations:\n\n"
        for i, conv in enumerate(conversations, 1):
            title = conv.get('structured', {}).get('title', 'Untitled')
            overview = conv.get('structured', {}).get('overview', 'N/A')
            created_at = conv.get('created_at', '')
            if created_at:
                created_str = (
                    created_at.strftime('%Y-%m-%d %H:%M') if hasattr(created_at, 'strftime') else str(created_at)
                )
            else:
                created_str = 'N/A'
            category = conv.get('structured', {}).get('category', 'N/A')

            result += f"{i}. {title}\n"
            result += f"   Category: {category}\n"
            result += f"   Overview: {overview}\n"
            result += f"   Date: {created_str}\n\n"

        return result.strip()
    except Exception as e:
        print(f"Error in get_conversations_tool: {e}")
        return f"Error retrieving conversations: {str(e)}"


def get_action_items_tool(
    uid: str,
    dates_range: Optional[List[datetime]] = None,
    length: Optional[int] = None,
    include_completed: bool = True,
) -> str:
    """
    Retrieve user action items and tasks.

    Args:
        uid: User ID (required)
        dates_range: [start_date, end_date] optional date filtering
        length: Number of action items to retrieve (optional, defaults to 20)
        include_completed: Include completed action items (defaults to True)

    Returns:
        Formatted string of action items
    """
    try:
        limit = length if length else 20
        start_date = dates_range[0] if dates_range and len(dates_range) >= 1 else None
        end_date = dates_range[1] if dates_range and len(dates_range) >= 2 else None

        action_items = db_get_action_items(
            uid,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=0,
            completed=None if include_completed else False,
        )

        if not action_items:
            return "No action items found for the given criteria."

        # Format action items as a string
        result = f"Retrieved {len(action_items)} action items:\n\n"
        for i, item in enumerate(action_items, 1):
            description = item.get('description', 'N/A')
            completed = item.get('completed', False)
            status_str = "✓ Completed" if completed else "○ Pending"
            due_at = item.get('due_at', '')
            if due_at:
                due_str = due_at.strftime('%Y-%m-%d') if hasattr(due_at, 'strftime') else str(due_at)
            else:
                due_str = 'No deadline'

            result += f"{i}. {status_str} {description}\n"
            result += f"   Due: {due_str}\n\n"

        return result.strip()
    except Exception as e:
        print(f"Error in get_action_items_tool: {e}")
        return f"Error retrieving action items: {str(e)}"
