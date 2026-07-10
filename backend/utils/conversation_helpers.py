"""Lightweight helpers for conversation data that avoid importing models.conversation."""

from typing import Any, Dict, List, cast


def extract_memory_ids(memories: List[Any], limit: int = 5) -> List[str]:
    """Extract IDs from a list of memories (may be dicts or objects).

    Used by chat routers to get conversation IDs without importing Conversation.
    """
    result: List[str] = []
    for m in memories[:limit]:
        if isinstance(m, dict):
            d = cast(Dict[str, Any], m)
            result.append(d.get('id', ''))
        else:
            result.append(m.id)
    return result
