"""
Tools for accessing user memories and facts.
"""

from datetime import datetime
from typing import Optional, List
import contextvars

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.memories as memory_db
import database.vector_db as vector_db
from models.memories import MemoryDB

# Import agent_config_context for fallback config access
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


@tool
def get_memories_tool(
    limit: int = 50,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve structured FACTS and PREFERENCES about the user (NOT events/incidents).

    Memories are STATIC FACTS about the user (name, age, preferences, habits, goals, relationships)
    that the system has learned over time. This is DIFFERENT from events/incidents that happened.

    **CRITICAL DISTINCTION - Use the right tool:**
    - "What's my favorite food?" → USE THIS TOOL (preference/fact)
    - "When did I get food poisoning?" → DO NOT USE THIS - use search_conversations_tool (event)
    - "Do I like dogs?" → USE THIS TOOL (preference)
    - "When did a dog bite me?" → DO NOT USE THIS - use search_conversations_tool (event)
    - "What are my hobbies?" → USE THIS TOOL (facts about user)
    - "What happened at the party?" → DO NOT USE THIS - use search_conversations_tool (event)

    Use this tool ONLY when:
    - User asks "what do you know about me?" or "tell me about my preferences"
    - You need background context about the user's preferences to personalize responses
    - User asks about their interests, goals, habits, or relationships (static facts)
    - Questions like "do I like X?", "what's my favorite Y?", "what are my Z?"

    DO NOT use this tool when:
    - User asks about specific events/incidents (use search_conversations_tool instead)
    - Questions like "when did X happen?", "what happened at Y?", "when did I get Z?"

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

    # Get config from parameter or context variable (like other tools do)
    if config is None:
        try:
            config = agent_config_context.get()
            if config:
                print(f"🔧 get_memories_tool - got config from context variable")
        except LookupError:
            print(f"❌ get_memories_tool - config not found in context variable")
            config = None

    if config is None:
        print(f"❌ get_memories_tool - config is None")
        return "Error: Configuration not available"

    try:
        uid = config['configurable'].get('user_id')
    except (KeyError, TypeError) as e:
        print(f"❌ get_memories_tool - error accessing config: {e}")
        return "Error: Configuration not available"

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


@tool
def search_memories_tool(
    query: str,
    limit: int = 10,
    config: RunnableConfig = None,
) -> str:
    """
    Search memories using semantic vector search to find relevant facts about the user.

    This tool uses AI embeddings to find memories (facts/preferences) that are semantically
    similar to your query, even if they don't contain the exact keywords.

    **When to use this tool:**
    - Searching for specific facts or preferences about the user
    - Finding memories related to a concept or theme
    - Looking up what the user knows/likes/dislikes about a topic
    - Questions like "what do I know about cooking?", "my preferences for travel"

    **When NOT to use this tool:**
    - For finding when specific events happened (use search_conversations_tool instead)
    - Questions like "when did X happen?", "what happened at Y?"

    **Examples:**
    - "cooking preferences" → finds memories about food, cooking habits
    - "work goals" → finds career-related facts and goals
    - "family members" → finds memories about relationships

    Args:
        query: Natural language description of what to search for (required)
        limit: Number of memories to retrieve (default: 10, max: 50)

    Returns:
        Formatted string with semantically matching memories ranked by relevance.
    """
    print(f"🔧 search_memories_tool called with query: {query}")

    # Get config from parameter or context variable
    if config is None:
        try:
            config = agent_config_context.get()
            if config:
                print(f"🔧 search_memories_tool - got config from context variable")
        except LookupError:
            print(f"❌ search_memories_tool - config not found in context variable")
            config = None

    if config is None:
        print(f"❌ search_memories_tool - config is None")
        return "Error: Configuration not available"

    try:
        uid = config['configurable'].get('user_id')
    except (KeyError, TypeError) as e:
        print(f"❌ search_memories_tool - error accessing config: {e}")
        return "Error: Configuration not available"

    if not uid:
        print(f"❌ search_memories_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    print(f"✅ search_memories_tool - uid: {uid}, query: {query}, limit: {limit}")

    # Cap limit at 50
    limit = min(limit, 50)

    try:
        # Perform vector search on memories
        # Use a lower threshold for search (0.5) to get more results
        matches = vector_db.find_similar_memories(uid, query, threshold=0.5, limit=limit)

        print(f"📊 search_memories_tool - found {len(matches)} results for query: '{query}'")

        if not matches:
            msg = (
                f"No memories found matching '{query}'. The user may not have any recorded facts about this topic yet."
            )
            print(f"⚠️ search_memories_tool - {msg}")
            return msg

        memory_ids = [match.get('memory_id') for match in matches if match.get('memory_id')]
        scores_by_id = {match.get('memory_id'): match.get('score', 0) for match in matches}

        if not memory_ids:
            return f"Found matches but no valid memory IDs for query: '{query}'"

        memories_data = memory_db.get_memories_by_ids(uid, memory_ids)

        # Convert to MemoryDB objects with scores
        memory_objects = []
        for memory_data in memories_data:
            try:
                memory_obj = MemoryDB(**memory_data)
                score = scores_by_id.get(memory_data.get('id'), 0)
                memory_objects.append({'memory': memory_obj, 'score': score})
            except Exception as e:
                print(f"Error creating MemoryDB object: {e}")
                continue

        if not memory_objects:
            return f"Found matches but could not retrieve memory details for query: '{query}'"

        print(f"🔍 search_memories_tool - Loaded {len(memory_objects)} full memories")

        # Format results with relevance scores
        result = f"Found {len(memory_objects)} memories matching '{query}':\n\n"
        for item in memory_objects:
            memory = item['memory']
            score = item['score']
            date_str = memory.created_at.strftime('%Y-%m-%d') if memory.created_at else 'Unknown'
            result += (
                f"- {memory.content} (relevance: {score:.2f}, category: {memory.category.value}, date: {date_str})\n"
            )

        print(f"🔍 search_memories_tool - Generated result string, length: {len(result)}")

        return result.strip()

    except Exception as e:
        error_msg = f"Error performing memory search: {str(e)}"
        print(f"❌ search_memories_tool - {error_msg}")
        import traceback

        traceback.print_exc()
        return f"Error searching memories: {str(e)}"
