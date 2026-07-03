"""Per-user MemorySystem cohort selector (WS-E).

Replaces fragmented memory rollout flags with one explicit server-owned selector.
``MemorySystem.LEGACY`` is the documented default — not an implicit None fallback.
"""

from enum import Enum
from typing import Any

from config.memory_rollout import MemoryRolloutConfig

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


def resolve_memory_system(uid: str, *, db_client: Any = None) -> MemorySystem:
    """Return the server-owned memory cohort for ``uid``.

    Precedence (authoritative):
      1. ``CANONICAL_MEMORY_USERS`` in this module — code-reviewed cohort membership.
      2. ``MEMORY_ENABLED_USERS`` + ``MEMORY_MODE`` — environment-specific activation.
      3. Absence from either list, or ``MEMORY_MODE=off`` → ``MemorySystem.LEGACY``.

    A stale persisted ``memory_control/state.memory_system=canonical`` does **not** override
    whitelist removal — clearing the code whitelist is the global kill-switch (everyone legacy).

    UID membership alone never activates canonical memory. This keeps the same
    branch deployable to dev or prod while requiring each GCP/Firebase
    environment to opt in explicitly through its own runtime env.
    """
    del db_client  # reserved for callers/tests; cohort is code-defined today

    if not uid:
        return MemorySystem.LEGACY

    if uid not in _canonical_cohort_uids():
        return MemorySystem.LEGACY

    try:
        rollout = MemoryRolloutConfig.from_env()
    except ValueError:
        return MemorySystem.LEGACY

    if rollout.mode.value == "off" or uid not in rollout.enabled_users:
        return MemorySystem.LEGACY

    return MemorySystem.CANONICAL
