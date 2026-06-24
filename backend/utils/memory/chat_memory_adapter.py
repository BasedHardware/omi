"""Canonical alias module for ``utils.memory.v17_chat_memory_adapter`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_chat_memory_adapter import (
    V17ChatDefaultMemoryRolloutDecision,
    V17ChatMemorySearchResult,
    V17_CHAT_MEMORY_BOUNDARY_NOTICE,
    V17_CHAT_MEMORY_CONTENT_MAX_CHARS,
    V17_CHAT_MEMORY_POLICY_MARKER,
    list_v17_default_chat_memories_decision_text,
    read_v17_chat_default_memory_rollout,
    search_v17_default_chat_memories_text,
    search_v17_default_chat_memories_vector_decision_text,
    search_v17_default_chat_memories_vector_text,
)

__all__ = [
    "V17ChatDefaultMemoryRolloutDecision",
    "V17ChatMemorySearchResult",
    "V17_CHAT_MEMORY_BOUNDARY_NOTICE",
    "V17_CHAT_MEMORY_CONTENT_MAX_CHARS",
    "V17_CHAT_MEMORY_POLICY_MARKER",
    "list_v17_default_chat_memories_decision_text",
    "read_v17_chat_default_memory_rollout",
    "search_v17_default_chat_memories_text",
    "search_v17_default_chat_memories_vector_decision_text",
    "search_v17_default_chat_memories_vector_text",
]
