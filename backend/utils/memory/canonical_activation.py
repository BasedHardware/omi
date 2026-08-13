"""Canonical memory activation gates shared by routes and background writers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from utils.memory.memory_system import (
    MemorySystem,
    ensure_canonical_apply_control_state,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CanonicalWriteDecision:
    enabled: bool
    memory_system: MemorySystem
    fail_closed: bool = False
    reason: str = "ok"


def canonical_write_decision(uid: str, *, db_client: Any) -> CanonicalWriteDecision:
    """Resolve universal write readiness without an entitlement ceremony.

    The per-user apply ledger is lazily created on first write.  Existing state
    is parsed strictly; malformed or cross-UID state fails closed and never
    routes the submission to a historical writer.
    """

    memory_system = MemorySystem.CANONICAL
    if not uid.strip():
        return CanonicalWriteDecision(
            enabled=False,
            memory_system=MemorySystem.LEGACY,
            fail_closed=True,
            reason="invalid_uid",
        )
    try:
        ensure_canonical_apply_control_state(uid, db_client=db_client)
    except Exception as exc:
        reason = (
            str(exc)
            if str(exc)
            in {
                "canonical apply control state requires a database client",
                "canonical apply control state is malformed",
                "canonical apply control state uid mismatch",
            }
            else type(exc).__name__
        )
        logger.info("canonical_write fail-closed uid=%s reason=%s", uid, reason)
        return CanonicalWriteDecision(
            enabled=False,
            memory_system=memory_system,
            fail_closed=True,
            reason=reason,
        )

    return CanonicalWriteDecision(enabled=True, memory_system=memory_system)


def canonical_write_enabled(uid: str, *, db_client: Any) -> bool:
    """Return true when universal canonical apply state is writable."""
    return canonical_write_decision(uid, db_client=db_client).enabled
