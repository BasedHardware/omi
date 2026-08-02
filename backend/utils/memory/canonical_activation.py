"""Canonical memory activation gates shared by routes and background writers."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from utils.memory.memory_system import MemorySystem
from utils.memory.memory_system_pin import pin_memory_system
from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation
from utils.memory.v3.control_reader_contract import (
    V3ControlReaderRequest,
    V3ControlRouteFamily,
    decide_v3_control_route,
)
from utils.memory.v3.control_state_adapter import read_v3_control

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CanonicalWriteDecision:
    enabled: bool
    memory_system: MemorySystem
    fail_closed: bool = False
    reason: str = "ok"


def canonical_write_decision(uid: str) -> CanonicalWriteDecision:
    """Resolve canonical write readiness without collapsing enrolled failures into legacy fallback."""

    memory_system = pin_memory_system(uid)
    if memory_system != MemorySystem.CANONICAL:
        return CanonicalWriteDecision(enabled=False, memory_system=memory_system, reason="not_canonical")

    control = read_v3_control(uid=uid)
    if not control.cohort_enrolled or control.state is None:
        reason = control.read_error_reason or "missing_state"
        logger.info("canonical_write disabled uid=%s reason=%s", uid, reason)
        return CanonicalWriteDecision(
            enabled=False,
            memory_system=memory_system,
            fail_closed=True,
            reason=reason,
        )
    if not control.state.rollout_write_ready:
        return CanonicalWriteDecision(
            enabled=False,
            memory_system=memory_system,
            fail_closed=True,
            reason="rollout_write_not_ready",
        )

    return CanonicalWriteDecision(enabled=True, memory_system=memory_system)


def canonical_write_enabled(uid: str) -> bool:
    """Return true only when the user is in cohort and write gates are ready."""
    return canonical_write_decision(uid).enabled


def canonical_read_enabled(
    uid: str,
    *,
    source_decision: str | None = None,
    cursor_memory_read_requested: bool = False,
    archive_requested: bool = False,
    env: dict[str, str] | None = None,
) -> bool:
    """Return true only after the `/v3` read control route allows memory reads."""

    if source_decision is not None and source_decision != "memory_read":
        return False
    if pin_memory_system(uid) != MemorySystem.CANONICAL:
        return False

    control = read_v3_control(uid=uid)
    trusted_generation = read_memory_v3_trusted_account_generation(uid=uid)
    effective_env = env if env is not None else os.environ
    decision = decide_v3_control_route(
        V3ControlReaderRequest(
            uid=uid,
            expected_account_generation=trusted_generation.account_generation,
            cursor_memory_read_requested=cursor_memory_read_requested,
            cursor_secret_config_present=bool(effective_env.get("MEMORY_V3_CURSOR_SECRET")),
            archive_requested=archive_requested,
        ),
        control,
    )
    return decision.route_family == V3ControlRouteFamily.MEMORY_PROJECTION and decision.allowed
