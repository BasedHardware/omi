"""Canonical memory activation gates shared by routes and background writers."""

from __future__ import annotations

import logging
import os

from config.memory_rollout import MemoryRolloutConfig, MemoryRolloutMode
from utils.memory.memory_system import MemorySystem
from utils.memory.memory_system_pin import pin_memory_system
from utils.memory.v3_account_generation_source import read_memory_v3_trusted_account_generation
from utils.memory.v3_control_reader_contract import (
    V3ControlReaderRequest,
    V3ControlRouteFamily,
    decide_v3_control_route,
)
from utils.memory.v3_control_state_adapter import read_v3_control

logger = logging.getLogger(__name__)


def canonical_write_enabled(uid: str, *, db_client) -> bool:
    """Return true only when the user is in cohort and write gates are ready."""

    if db_client is None:
        return False

    if pin_memory_system(uid, db_client=db_client) != MemorySystem.CANONICAL:
        return False

    try:
        rollout_config = MemoryRolloutConfig.from_env()
    except ValueError:
        return False
    if rollout_config.mode not in {MemoryRolloutMode.write, MemoryRolloutMode.read}:
        return False

    control = read_v3_control(uid=uid, db_client=db_client, rollout_config=rollout_config)
    if not control.cohort_enrolled or control.state is None:
        logger.info("canonical_write disabled uid=%s reason=%s", uid, control.read_error_reason or "missing_state")
        return False

    return control.state.rollout_write_ready


def canonical_read_enabled(
    uid: str,
    *,
    db_client,
    source_decision: str | None = None,
    cursor_memory_read_requested: bool = False,
    archive_requested: bool = False,
    env: dict[str, str] | None = None,
) -> bool:
    """Return true only after the `/v3` read control route allows memory reads."""

    if source_decision is not None and source_decision != "memory_read":
        return False
    if db_client is None:
        return False
    if pin_memory_system(uid, db_client=db_client) != MemorySystem.CANONICAL:
        return False

    try:
        rollout_config = MemoryRolloutConfig.from_env()
    except ValueError:
        return False
    if rollout_config.mode != MemoryRolloutMode.read:
        return False

    control = read_v3_control(uid=uid, db_client=db_client, rollout_config=rollout_config)
    trusted_generation = read_memory_v3_trusted_account_generation(uid=uid, db_client=db_client)
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
