from datetime import datetime, timezone
from typing import Optional, Dict, Any
import database.memories as memories_db
import database.conversations as conversations_db
import database.action_items as action_items_db
import dateutil.parser
from utils.llm.clients import parse_user_date_query
from langchain.tools import tool

# ============================================================================
# SIMPLIFIED CLEAN IMPLEMENTATION
# Core approach: uid, date_query, limit (hardcoded) - database-level filtering
# ============================================================================


def parse_date_for_db(date_str: str) -> tuple[Optional[datetime], Optional[datetime]]:
    """Parse user date string to database-compatible datetime objects"""
    if not date_str:
        print("No date query provided")
        return None, None

    try:
        now = datetime.now(timezone.utc)
        current_time_iso = now.isoformat().replace('+00:00', 'Z')

        print(f"Parsing date query: '{date_str}' (current time: {current_time_iso})")

        # Use our fixed LLM date parser
        date_range = parse_user_date_query(date_str, current_time_iso)

        print(f"LLM parsed result: start='{date_range.start_date}', end='{date_range.end_date}'")

        # Convert to exact database format
        start_date = dateutil.parser.parse(date_range.start_date).astimezone(timezone.utc).replace(tzinfo=timezone.utc)
        end_date = dateutil.parser.parse(date_range.end_date).astimezone(timezone.utc).replace(tzinfo=timezone.utc)

        print(f"Final database dates: start={start_date}, end={end_date}")

        return start_date, end_date

    except Exception as e:
        print(f"Date parsing failed for '{date_str}': {e}")
        return None, None


def get_memories_tool(uid: str, date_query: str = None) -> Dict[str, Any]:
    """Simple memories tool - only core parameters: uid, date_query, limit"""
    try:
        print(f"get_memories_tool called with uid={uid}, date_query='{date_query}'")
        start_date, end_date = parse_date_for_db(date_query)

        print(f"Calling memories_db.get_memories with start_date={start_date}, end_date={end_date}")

        # Database-level filtering only
        memories = memories_db.get_memories(
            uid=uid, limit=10, start_date=start_date, end_date=end_date  # Hardcoded as requested
        )

        print(f"get_memories_tool returning {len(memories)} memories")

        return {"status": "success", "count": len(memories), "memories": memories}

    except Exception as e:
        print(f"get_memories_tool error: {e}")
        return {"status": "error", "error": str(e), "count": 0, "memories": []}


def get_conversations_tool(uid: str, date_query: str = None) -> Dict[str, Any]:
    """Simple conversations tool - only core parameters: uid, date_query, limit"""
    try:
        print(f"get_conversations_tool called with uid={uid}, date_query='{date_query}'")
        start_date, end_date = parse_date_for_db(date_query)

        print(f"Calling conversations_db.get_conversations with start_date={start_date}, end_date={end_date}")

        # Database-level filtering only
        conversations = conversations_db.get_conversations(
            uid=uid,
            limit=10,  # Hardcoded as requested
            start_date=start_date,
            end_date=end_date,
            statuses=["completed"],
            include_discarded=False,
        )

        print(f"get_conversations_tool returning {len(conversations)} conversations")

        return {"status": "success", "count": len(conversations), "conversations": conversations}

    except Exception as e:
        print(f"get_conversations_tool error: {e}")
        return {"status": "error", "error": str(e), "count": 0, "conversations": []}


def get_action_items_tool(uid: str, date_query: str = None) -> Dict[str, Any]:
    """Simple action items tool - only core parameters: uid, date_query, limit"""
    try:
        print(f"get_action_items_tool called with uid={uid}, date_query='{date_query}'")
        start_date, end_date = parse_date_for_db(date_query)

        print(f"Calling action_items_db.get_action_items with start_date={start_date}, end_date={end_date}")

        # Database-level filtering only
        action_items = action_items_db.get_action_items(
            uid=uid, limit=10, start_date=start_date, end_date=end_date  # Hardcoded as requested
        )

        print(f"get_action_items_tool returning {len(action_items)} action items")

        return {"status": "success", "count": len(action_items), "action_items": action_items}

    except Exception as e:
        print(f"get_action_items_tool error: {e}")
        return {"status": "error", "error": str(e), "count": 0, "action_items": []}


# ============================================================================
# LANGGRAPH TOOL WRAPPERS
# ============================================================================


@tool
def get_memories(uid: str, date_query: str = None) -> dict:
    """Retrieve user memories filtered by date.

    Args:
        uid: User ID
        date_query: Natural language date like 'yesterday', 'september 6th', 'today'
    """
    return get_memories_tool(uid, date_query)


@tool
def get_conversations(uid: str, date_query: str = None) -> dict:
    """Retrieve user conversations filtered by date.

    Args:
        uid: User ID
        date_query: Natural language date like 'yesterday', 'september 6th', 'today'
    """
    return get_conversations_tool(uid, date_query)


@tool
def get_action_items(uid: str, date_query: str = None) -> dict:
    """Retrieve user action items filtered by date.

    Args:
        uid: User ID
        date_query: Natural language date like 'yesterday', 'september 6th', 'today'
    """
    return get_action_items_tool(uid, date_query)
