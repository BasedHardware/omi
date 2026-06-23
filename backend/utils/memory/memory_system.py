"""Per-user MemorySystem cohort selector (WS-E).

Replaces fragmented V17 rollout flags with one explicit server-owned selector.
``MemorySystem.LEGACY`` is the documented default — not an implicit None fallback.
"""

import os
from enum import Enum
from typing import Set

MEMORY_SYSTEM_FIELD = "memory_system"
CANONICAL_COHORT_ENV = "MEMORY_CANONICAL_USERS"


class MemorySystem(str, Enum):
    LEGACY = "legacy"
    CANONICAL = "canonical"


def _canonical_users_from_env() -> Set[str]:
    raw = os.getenv(CANONICAL_COHORT_ENV, "")
    return {uid.strip() for uid in raw.split(",") if uid.strip()}


def resolve_memory_system(uid: str, *, db_client=None) -> MemorySystem:
    """Return the server-owned memory cohort for ``uid``.

    Precedence (authoritative):
      1. ``MEMORY_CANONICAL_USERS`` env whitelist — sole source of canonical cohort membership.
      2. Absence from the whitelist → ``MemorySystem.LEGACY`` (explicit default; no implicit None).

    A stale persisted ``memory_control/state.memory_system=canonical`` does **not** override
    whitelist removal — emptying the whitelist is the global kill-switch (everyone legacy).

    Transitional V17 rollout controls (``V17_MODE``, ``V17_MEMORY_ENABLED_USERS``, stage gates,
    global read gates) select V17 read/write adapters — they do **not** imply ``MemorySystem.CANONICAL``.
    """
    del db_client  # reserved for callers/tests; cohort is env-only today

    if not uid:
        return MemorySystem.LEGACY

    if uid in _canonical_users_from_env():
        return MemorySystem.CANONICAL

    return MemorySystem.LEGACY
