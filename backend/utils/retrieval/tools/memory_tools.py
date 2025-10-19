"""
Tools for accessing user memories and facts.
"""

from datetime import datetime
from typing import Optional

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
        start_date: Filter memories after this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T15:00:00-08:00")
        end_date: Filter memories before this date (ISO format in user's timezone: YYYY-MM-DDTHH:MM:SS+HH:MM, e.g. "2024-01-19T23:59:59-08:00")

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

    # Parse dates if provided (must be ISO format with timezone)
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
