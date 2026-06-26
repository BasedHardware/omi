"""Per-user MemorySystem cohort selector (WS-E).

Replaces fragmented memory rollout flags with one explicit server-owned selector.
``MemorySystem.LEGACY`` is the documented default — not an implicit None fallback.
"""

from enum import Enum

MEMORY_SYSTEM_FIELD = "memory_system"

# Code-as-config canonical cohort whitelist (reviewable, diff-able, test-guarded).
# Add Firebase UIDs here to enroll users in the canonical memory path.
# Everyone not listed resolves to LEGACY.
CANONICAL_MEMORY_USERS: frozenset[str] = frozenset(
    {
        "vi7SA9ckQCe4ccobWNxlbdcNdC23",  # david.d.zhang@gmail.com (prod Firebase: based-hardware)
    }
)


class MemorySystem(str, Enum):
    LEGACY = "legacy"
    CANONICAL = "canonical"


def _canonical_cohort_uids() -> frozenset[str]:
    """Return the code-defined canonical cohort set."""
    return CANONICAL_MEMORY_USERS


def list_canonical_cohort_uids() -> list[str]:
    """Return sorted uids from ``CANONICAL_MEMORY_USERS``."""
    return sorted(_canonical_cohort_uids())


def resolve_memory_system(uid: str, *, db_client=None) -> MemorySystem:
    """Return the server-owned memory cohort for ``uid``.

    Precedence (authoritative):
      1. ``CANONICAL_MEMORY_USERS`` in this module — sole source of canonical cohort membership.
      2. Absence from the whitelist → ``MemorySystem.LEGACY`` (explicit default; no implicit None).

    A stale persisted ``memory_control/state.memory_system=canonical`` does **not** override
    whitelist removal — clearing the code whitelist is the global kill-switch (everyone legacy).

    Transitional memory rollout controls (``MEMORY_MODE``, ``MEMORY_ENABLED_USERS``, stage gates,
    global read gates) select memory read/write adapters — they do **not** imply ``MemorySystem.CANONICAL``.
    """
    del db_client  # reserved for callers/tests; cohort is code-defined today

    if not uid:
        return MemorySystem.LEGACY

    if uid in _canonical_cohort_uids():
        return MemorySystem.CANONICAL

    return MemorySystem.LEGACY
