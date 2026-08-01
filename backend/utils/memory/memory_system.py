"""Per-user MemorySystem cohort selector (WS-E).

Replaces fragmented memory rollout flags with one explicit server-owned selector.
``MemorySystem.LEGACY`` is the documented default — not an implicit None fallback.
"""

import os
from enum import Enum
from typing import Any

from config import canonical_memory_cohort

MEMORY_SYSTEM_FIELD = "memory_system"

# Code-as-config canonical cohort whitelist (reviewable, diff-able, test-guarded).
# Add Firebase UIDs here to enroll users in the canonical memory path.
# Everyone not listed resolves to LEGACY.
CANONICAL_MEMORY_USERS = canonical_memory_cohort.CANONICAL_MEMORY_USERS
_LOCAL_FIXTURE_STAGES = frozenset({'local', 'offline'})


class MemorySystem(str, Enum):
    LEGACY = "legacy"
    CANONICAL = "canonical"


def _canonical_cohort_uids() -> frozenset[str]:
    """Return the code-defined canonical cohort set."""
    return canonical_memory_cohort.CANONICAL_MEMORY_USERS


def list_canonical_cohort_uids() -> list[str]:
    """Return sorted uids from ``CANONICAL_MEMORY_USERS``."""
    return sorted(_canonical_cohort_uids())


def _local_fixture_canonical_uids() -> frozenset[str]:
    """Return harness-selected users only for the isolated local/offline stages."""
    if os.getenv('OMI_ENV_STAGE', '').strip().lower() not in _LOCAL_FIXTURE_STAGES:
        return frozenset()
    return frozenset(uid.strip() for uid in os.getenv('MEMORY_CANONICAL_USERS', '').split(',') if uid.strip())


def resolve_memory_system(uid: str, *, db_client: Any = None) -> MemorySystem:
    """Return the server-owned memory cohort for ``uid``.

    ``CANONICAL_MEMORY_USERS`` is the production entitlement selector. The
    isolated local/offline harness may add its seeded Firebase Auth UIDs through
    ``MEMORY_CANONICAL_USERS`` so its advertised fixture path remains canonical.
    Runtime rollout configuration and persisted control records may supply
    readiness and concurrency fences after this selector has chosen
    ``CANONICAL``; they must never reinterpret an enrolled account as
    ``LEGACY``.

    A stale persisted ``memory_control/state.memory_system=canonical`` does **not** override
    whitelist removal — clearing the code whitelist is the global kill-switch (everyone legacy).
    """
    del db_client  # reserved for callers/tests; cohort is code-defined today

    is_canonical = canonical_memory_cohort.is_canonical_memory_user(uid) or uid in _local_fixture_canonical_uids()
    return MemorySystem.CANONICAL if is_canonical else MemorySystem.LEGACY
