"""Per-user MemorySystem cohort selector (WS-E).

Replaces fragmented memory rollout flags with one explicit server-owned selector.
``MemorySystem.LEGACY`` is the documented default — not an implicit None fallback.
"""

from enum import Enum
from typing import Any

from config import canonical_memory_cohort

MEMORY_SYSTEM_FIELD = "memory_system"

# Code-as-config canonical cohort whitelist (reviewable, diff-able, test-guarded).
# Add Firebase UIDs here to enroll users in the canonical memory path.
# Everyone not listed resolves to LEGACY.
CANONICAL_MEMORY_USERS = canonical_memory_cohort.CANONICAL_MEMORY_USERS


class MemorySystem(str, Enum):
    LEGACY = "legacy"
    CANONICAL = "canonical"


def _canonical_cohort_uids() -> frozenset[str]:
    """Return the code-defined canonical cohort set."""
    return canonical_memory_cohort.CANONICAL_MEMORY_USERS


def list_canonical_cohort_uids() -> list[str]:
    """Return sorted uids from ``CANONICAL_MEMORY_USERS``."""
    return sorted(_canonical_cohort_uids())


def resolve_memory_system(uid: str, *, db_client: Any = None) -> MemorySystem:
    """Return the server-owned memory cohort for ``uid``.

    ``CANONICAL_MEMORY_USERS`` is the sole entitlement selector. Runtime rollout
    configuration and persisted control records may supply readiness and
    concurrency fences after this selector has chosen ``CANONICAL``; they must
    never reinterpret an enrolled account as ``LEGACY``.

    A stale persisted ``memory_control/state.memory_system=canonical`` does **not** override
    whitelist removal — clearing the code whitelist is the global kill-switch (everyone legacy).
    """
    del db_client  # reserved for callers/tests; cohort is code-defined today

    return MemorySystem.CANONICAL if canonical_memory_cohort.is_canonical_memory_user(uid) else MemorySystem.LEGACY
