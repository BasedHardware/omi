"""Canonical alias module for ``utils.memory.v17_developer_memory_adapter`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_developer_memory_adapter import (
    V17DeveloperDefaultMemoryRolloutDecision,
    V17DeveloperMemorySearchResult,
    read_v17_developer_default_memory_rollout,
    search_v17_default_developer_memories,
    search_v17_default_developer_memories_vector,
)

__all__ = [
    "V17DeveloperDefaultMemoryRolloutDecision",
    "V17DeveloperMemorySearchResult",
    "read_v17_developer_default_memory_rollout",
    "search_v17_default_developer_memories",
    "search_v17_default_developer_memories_vector",
]
