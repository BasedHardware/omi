"""Lightweight helpers for conversation data that avoid importing models.conversation."""

from typing import List


def extract_memory_ids(memories: list, limit: int = 5) -> List[str]:
    """Extract IDs from a list of memories (may be dicts or objects).

    Used by chat routers to get conversation IDs without importing Conversation.
    """
    result = []
    for m in memories[:limit]:
        if isinstance(m, dict):
            result.append(m.get('id', ''))
        else:
            result.append(m.id)
    return result
