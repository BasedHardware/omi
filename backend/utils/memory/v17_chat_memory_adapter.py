"""Backward-compatible shim — implementation lives in ``utils.memory.chat_memory_adapter`` (WS-G8a)."""

from utils.memory.chat_memory_adapter import (
    CHAT_MEMORY_BOUNDARY_NOTICE,
    CHAT_MEMORY_CONTENT_MAX_CHARS,
    CHAT_MEMORY_POLICY_MARKER,
    ChatDefaultMemoryRolloutDecision,
    ChatMemorySearchResult,
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
    "CHAT_MEMORY_BOUNDARY_NOTICE",
    "CHAT_MEMORY_CONTENT_MAX_CHARS",
    "CHAT_MEMORY_POLICY_MARKER",
    "ChatDefaultMemoryRolloutDecision",
    "ChatMemorySearchResult",
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
