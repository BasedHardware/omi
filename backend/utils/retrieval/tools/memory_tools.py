"""
Tools for accessing user memories and facts.
"""

from typing import Optional
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.memories as memory_db


@tool
def get_memories_tool(
    limit: int = 50,
    offset: int = 0,
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

    Use get_conversations_tool instead when:
    - User asks "what did I say yesterday?" or wants to see actual conversation transcripts
    - User wants to review specific discussions or topics

    Args:
        limit: Number of memories to retrieve (default: 50, max: 200)
        offset: Pagination offset (default: 0)

    Returns:
        Formatted list of facts about the user with categories, dates, and emoji representations.
    """
    print(f"🔧 get_memories_tool called - limit: {limit}, config: {config}")
    uid = config['configurable'].get('user_id')
    if not uid:
        print(f"❌ get_memories_tool - no user_id in config")
        return "Error: User ID not found in configuration"
    print(f"✅ get_memories_tool - uid: {uid}, limit: {limit}")

    # Limit to reasonable max
    limit = min(limit, 200)

    # Get memories
    memories = memory_db.get_memories(uid, limit=limit, offset=offset)

    print(f"📊 get_memories_tool - found {len(memories) if memories else 0} memories")

    if not memories:
        msg = "No memories found. The user may not have any recorded facts or memories yet in the system."
        print(f"⚠️ get_memories_tool - {msg}")
        return msg

    # Format memories as a readable string
    result = f"User Memories ({len(memories)} total):\n\n"

    for i, memory in enumerate(memories, 1):
        content = memory.get('content', '')
        created_at = memory.get('created_at', '')
        structured = memory.get('structured', {})

        result += f"{i}. {content}\n"

        # Add structured data if available
        if structured:
            category = structured.get('category')
            if category:
                result += f"   Category: {category}\n"

            emoji = structured.get('emoji')
            if emoji:
                result += f"   {emoji}\n"

        if created_at:
            result += f"   Date: {created_at}\n"

        result += "\n"

    return result
