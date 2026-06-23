"""Per-user MemorySystem cohort selector (WS-E).

Replaces fragmented V17 rollout flags with one explicit server-owned selector.
``MemorySystem.LEGACY`` is the documented default — not an implicit None fallback.
"""

import os
from enum import Enum
from typing import Optional, Set

from database.v17_collections import V17Collections

MEMORY_SYSTEM_FIELD = "memory_system"
CANONICAL_COHORT_ENV = "MEMORY_CANONICAL_USERS"


class MemorySystem(str, Enum):
    LEGACY = "legacy"
    CANONICAL = "canonical"


def _canonical_users_from_env() -> Set[str]:
    raw = os.getenv(CANONICAL_COHORT_ENV, "")
    return {uid.strip() for uid in raw.split(",") if uid.strip()}


def _read_persisted_memory_system(uid: str, db_client) -> Optional[MemorySystem]:
    if db_client is None:
        return None

    path = V17Collections(uid=uid).memory_control_state
    snapshot = db_client.document(path).get()
    if not getattr(snapshot, "exists", False):
        return None

    data = snapshot.to_dict() or {}
    value = data.get(MEMORY_SYSTEM_FIELD)
    if value == MemorySystem.CANONICAL.value:
        return MemorySystem.CANONICAL
    if value == MemorySystem.LEGACY.value:
        return MemorySystem.LEGACY
    return None


def _default_db_client():
    try:
        from database import _client as db_client_module

        return getattr(db_client_module, "db", None)
    except Exception:
        return None


def resolve_memory_system(uid: str, *, db_client=None) -> MemorySystem:
    """Return the server-owned memory cohort for ``uid``.

    Defaults explicitly to ``MemorySystem.LEGACY``. Canonical cohort requires an
    explicit assignment via ``MEMORY_CANONICAL_USERS`` or a persisted
    ``memory_system=canonical`` field on ``users/{uid}/memory_control/state``.

    Transitional V17 rollout controls (``V17_MODE``, ``V17_MEMORY_ENABLED_USERS``,
    stage gates, global read gates) select V17 read/write adapters — they do **not**
    imply ``MemorySystem.CANONICAL``. No production user is canonical in WS-E.
    """
    if not uid:
        return MemorySystem.LEGACY

    if uid in _canonical_users_from_env():
        return MemorySystem.CANONICAL

    client = db_client if db_client is not None else _default_db_client()
    persisted = _read_persisted_memory_system(uid, client)
    if persisted == MemorySystem.CANONICAL:
        return MemorySystem.CANONICAL

    return MemorySystem.LEGACY
