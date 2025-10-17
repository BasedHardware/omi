"""
Tools for accessing user memories and facts.
"""

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.memories as memory_db
from models.memories import MemoryDB


@tool
def get_memories_tool(
    limit: int = 50,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve structured facts and insights about the user extracted from their conversations.

    Memories are facts about the user (preferences, habits, goals, relationships, personal details)
    that the system has learned over time. This is different from conversation transcripts which
    show what was actually said.

    Use this tool when:
    - User asks "what do you know about me?" or "tell me about my preferences"
    - You need background context about the user to personalize responses
    - User asks about their interests, goals, or habits
    - You want to understand the user better to give more personalized advice
    - **ALWAYS use this tool to learn about the user before answering personal questions**

    Time filtering guidance:
    - **CRITICAL**: When user asks about memories from relative times ("2 minutes ago", "last hour", "this morning"), you MUST calculate and provide start_date/end_date parameters
    - **IMPORTANT**: Use the current datetime from <current_datetime_utc> in the system prompt to calculate all relative times
    - **DO NOT leave start_date/end_date empty when the user specifies a time period** - always calculate the actual datetime values
    - For exact date queries ("October 16th", "yesterday"), use YYYY-MM-DD format - dates are interpreted in user's timezone
    - For relative time queries at hour/minute level ("2 minutes ago", "30 minutes ago", "2 hours ago", "5 minutes ago"):
      * YOU MUST calculate the exact datetime by subtracting from current time in <current_datetime_utc>
      * Use ISO format without timezone (YYYY-MM-DDTHH:MM:SS) - will be interpreted in user's timezone
      * Example: If current time is 2024-01-15 14:00:00 UTC and user asks "2 hours ago", you MUST use start_date="2024-01-15T12:00:00"
      * Example: If current time is 2024-01-15 14:30:00 UTC and user asks "5 minutes ago", you MUST use start_date="2024-01-15T14:25:00"
      * Example: If current time is 2024-01-15 10:35:00 UTC and user asks "2 minutes ago", you MUST use start_date="2024-01-15T10:33:00"
    - For time-of-day queries ("this morning", "this afternoon", "tonight"):
      * Use the current date from <current_datetime_utc> to build the date string
      * "this morning": start_date="YYYY-MM-DDT06:00:00", end_date="YYYY-MM-DDT12:00:00"
      * "this afternoon": start_date="YYYY-MM-DDT12:00:00", end_date="YYYY-MM-DDT18:00:00"
      * "tonight": start_date="YYYY-MM-DDT18:00:00", end_date="YYYY-MM-DDT23:59:59"
    - Combine start_date and end_date to create precise time windows
    - All dates without explicit timezone are assumed to be in the user's local timezone

    Memory retrieval guidance - choosing the right limit:
    - **CRITICAL**: For ANY question asking about basic personal information (name, age, location, background, etc.) or multiple personal facts together, you MUST use limit=5000 to get ALL memories
    - **For GENERAL COMPREHENSIVE questions, you MUST use limit=5000** to get ALL memories
    - **For specific questions about a single narrow topic, you can use limit=50-200**
    - Examples when you MUST use limit=5000:
      * "what do you know about me"
      * "tell me about myself"
      * "what's my name, age, and location"
      * "who am I"
      * "what's my profile"
      * "what's my age"
      * "where do I live"
      * "tell me everything"
      * "what are all my interests"
      * Any question asking for multiple personal facts together
    - Examples when limit=50-200 is acceptable:
      * "what conversations did I have about Python"
      * "what do I know about machine learning"
      * Questions about a specific narrow topic
    - **Ask user for confirmation** before fetching 500+ memories for very broad analysis, as it may take longer
    - **Maximum limit is 5000 per call** - use pagination (offset parameter) if more are needed

    Args:
        limit: Number of memories to retrieve (default: 50, recommended: 50-200, max per call: 5000)
        offset: Pagination offset for retrieving additional memories beyond the limit (default: 0)
        start_date: Filter memories after this date (YYYY-MM-DD for days, YYYY-MM-DDTHH:MM:SS for hours/minutes)
        end_date: Filter memories before this date (YYYY-MM-DD for days, YYYY-MM-DDTHH:MM:SS for hours/minutes)

    Returns:
        Formatted list of facts about the user with categories, dates, and emoji representations.
    """
    print(
        f"🔧 get_memories_tool called - limit: {limit}, offset: {offset}, start_date: {start_date}, end_date: {end_date}"
    )
    uid = config['configurable'].get('user_id')
    if not uid:
        print(f"❌ get_memories_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    print(f"✅ get_memories_tool - uid: {uid}, limit: {limit}")

    # Get safety guard from config if available
    safety_guard = config['configurable'].get('safety_guard')

    # Cap at 5000 per call to prevent overloading context
    if limit > 5000:
        print(f"⚠️ get_memories_tool - limit capped from {limit} to 5000")
        limit = 5000

    # Get user timezone from config, default to UTC
    user_timezone_str = config['configurable'].get('timezone', 'UTC')
    try:
        user_tz = ZoneInfo(user_timezone_str)
    except Exception:
        user_tz = ZoneInfo('UTC')
    print(f"🌍 get_memories_tool - user timezone: {user_timezone_str}")

    # Parse dates if provided
    start_dt = None
    end_dt = None

    if start_date:
        try:
            if len(start_date) == 10:  # YYYY-MM-DD - treat as user's local date
                # Parse as naive datetime and localize to user's timezone
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
            if len(end_date) == 10:  # YYYY-MM-DD - treat as user's local date
                # Parse as naive datetime and localize to user's timezone (end of day)
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

    # Get memories
    memories = []
    try:
        memories = memory_db.get_memories(uid, limit=limit, offset=offset, start_date=start_dt, end_date=end_dt)
    except Exception as e:
        print(e)

    memories_count = len(memories) if memories else 0
    print(f"📊 get_memories_tool - found {memories_count} memories")

    # Log warning if large number of memories retrieved
    if memories_count >= 500:
        print(f"⚠️ Large number of memories retrieved ({memories_count}). Consider if all are needed.")

    if not memories:
        date_info = ""
        if start_dt and end_dt:
            date_info = f" between {start_dt.strftime('%Y-%m-%d')} and {end_dt.strftime('%Y-%m-%d')}"
        elif start_dt:
            date_info = f" after {start_dt.strftime('%Y-%m-%d')}"
        elif end_dt:
            date_info = f" before {end_dt.strftime('%Y-%m-%d')}"

        msg = f"No memories found{date_info}. The user may not have any recorded facts or memories yet in the system, or the date range may be outside their memory history."
        print(f"⚠️ get_memories_tool - {msg}")
        return msg

    # Convert dictionaries to MemoryDB objects for proper formatting
    memory_objects = []
    for memory_data in memories:
        try:
            memory_objects.append(MemoryDB(**memory_data))
        except Exception as e:
            print(f"Error creating MemoryDB object: {e}")
            continue

    if not memory_objects:
        return "Error: Could not parse memories data"

    # Format memories using the Memory model's string formatter
    result = f"User Memories ({len(memory_objects)} total):\n\n"
    result += MemoryDB.get_memories_as_str(memory_objects)

    return result.strip()
