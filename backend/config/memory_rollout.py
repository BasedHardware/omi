"""Canonical rollout configuration (WS-G5).

Neutral ``MemoryRollout*`` symbols are the source of truth. Legacy ``memory*`` names
remain importable aliases until later rename waves. Env vars read neutral ``MEMORY_*``
keys only; cohort membership is code-defined in ``utils.memory.memory_system.CANONICAL_MEMORY_USERS``.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable, Optional, Set, cast

MEMORY_MODE_ENV = "MEMORY_MODE"
MEMORY_ENABLED_USERS_ENV = "MEMORY_ENABLED_USERS"
MEMORY_V3_GET_ENABLED_ENV = "MEMORY_V3_GET_ENABLED"


class MemoryRolloutMode(str, Enum):
    off = "off"
    shadow = "shadow"
    write = "write"
    read = "read"


class MemoryRolloutStageGate(str, Enum):
    shadow = "shadow"
    write = "write"
    read = "read"


MemoryRolloutMode = MemoryRolloutMode
MemoryRolloutStageGate = MemoryRolloutStageGate

PASSED = "passed"


@dataclass(frozen=True)
class MemoryRolloutCapabilities:
    uid: str
    mode: MemoryRolloutMode
    legacy_only: bool
    shadow_artifacts_enabled: bool
    memory_writes_enabled: bool
    memory_reads_enabled: bool
    legacy_reads_authoritative: bool
    account_generation: int = 0


MemoryRolloutCapabilities = MemoryRolloutCapabilities


@dataclass
class MemoryRolloutState:
    uid: str
    mode: MemoryRolloutMode = MemoryRolloutMode.off
    mode_epoch: int = 0
    cutover_epoch: int = 0
    account_generation: int = 0
    last_reconciled_legacy_revision: Optional[str] = None
    fallback_projection_ready: bool = False
    persistent_memory_writes_started: bool = False
    decommission_reconciled: bool = False
    writes_blocked: bool = False
    stage_gates: dict[MemoryRolloutStageGate, str] = field(default_factory=dict[MemoryRolloutStageGate, str])

    def __post_init__(self):
        if self.mode_epoch < 0:
            raise ValueError("mode_epoch must be nonnegative")
        if self.cutover_epoch < 0:
            raise ValueError("cutover_epoch must be nonnegative")
        if self.account_generation < 0:
            raise ValueError("account_generation must be nonnegative")
        raw_stage_gates = cast(Mapping[MemoryRolloutStageGate | str, str], self.stage_gates)
        self.stage_gates = {
            key if isinstance(key, MemoryRolloutStageGate) else MemoryRolloutStageGate(key): value
            for key, value in raw_stage_gates.items()
        }

    def gate_passed(self, gate: MemoryRolloutStageGate) -> bool:
        return self.stage_gates.get(gate) == PASSED

    def can_transition_to(self, target: MemoryRolloutMode) -> bool:
        if target == self.mode:
            return True
        if target == MemoryRolloutMode.off and self.persistent_memory_writes_started:
            return self.decommission_reconciled
        if self.mode == MemoryRolloutMode.read and target in {
            MemoryRolloutMode.write,
            MemoryRolloutMode.shadow,
            MemoryRolloutMode.off,
        }:
            if target == MemoryRolloutMode.off and self.decommission_reconciled:
                return True
            return self.fallback_projection_ready
        if target == MemoryRolloutMode.read:
            return self.fallback_projection_ready and self.gate_passed(MemoryRolloutStageGate.read)
        return True

    def transition_to(self, target: MemoryRolloutMode) -> "MemoryRolloutState":
        if not self.can_transition_to(target):
            raise ValueError(f"Cannot transition from {self.mode.value} to {target.value}")
        next_epoch = self.mode_epoch + (0 if target == self.mode else 1)
        cutover_epoch = self.cutover_epoch
        if target == MemoryRolloutMode.read and self.mode != MemoryRolloutMode.read:
            cutover_epoch = next_epoch
        return replace(self, mode=target, mode_epoch=next_epoch, cutover_epoch=cutover_epoch)


MemoryRolloutState = MemoryRolloutState


@dataclass
class MemoryRolloutConfig:
    enabled_users: Set[str] = field(default_factory=set[str])
    mode: MemoryRolloutMode = MemoryRolloutMode.off

    @classmethod
    def from_env(cls) -> "MemoryRolloutConfig":
        mode = MemoryRolloutMode(rollout_mode_env_value())
        return cls(
            enabled_users=parse_enabled_users(rollout_enabled_users_env_raw()),
            mode=mode,
        )

    def for_user(self, uid: str, state: Optional[MemoryRolloutState] = None) -> MemoryRolloutCapabilities:
        if self.mode == MemoryRolloutMode.off or uid not in self.enabled_users:
            return _legacy_capabilities(uid)
        if state is None:
            state = MemoryRolloutState(
                uid=uid,
                mode=self.mode,
                stage_gates={MemoryRolloutStageGate.shadow: PASSED},
            )
        if state.uid != uid:
            return _legacy_capabilities(uid)
        return decide_memory_rollout_capabilities(uid, self.mode, state)


MemoryRolloutConfig = MemoryRolloutConfig


def _legacy_capabilities(uid: str) -> MemoryRolloutCapabilities:
    return MemoryRolloutCapabilities(
        uid=uid,
        mode=MemoryRolloutMode.off,
        legacy_only=True,
        shadow_artifacts_enabled=False,
        memory_writes_enabled=False,
        memory_reads_enabled=False,
        legacy_reads_authoritative=True,
    )


def decide_memory_rollout_capabilities(
    uid: str,
    mode: MemoryRolloutMode | str,
    state: MemoryRolloutState,
) -> MemoryRolloutCapabilities:
    resolved = mode if isinstance(mode, MemoryRolloutMode) else MemoryRolloutMode(mode)
    if resolved == MemoryRolloutMode.off:
        return _legacy_capabilities(uid)

    shadow_enabled = state.gate_passed(MemoryRolloutStageGate.shadow)
    write_enabled = (
        resolved in {MemoryRolloutMode.write, MemoryRolloutMode.read}
        and shadow_enabled
        and state.gate_passed(MemoryRolloutStageGate.write)
        and not state.writes_blocked
    )
    read_enabled = (
        resolved == MemoryRolloutMode.read
        and write_enabled
        and state.gate_passed(MemoryRolloutStageGate.read)
        and state.fallback_projection_ready
    )
    return MemoryRolloutCapabilities(
        uid=uid,
        mode=resolved,
        legacy_only=False,
        shadow_artifacts_enabled=shadow_enabled,
        memory_writes_enabled=write_enabled,
        memory_reads_enabled=read_enabled,
        legacy_reads_authoritative=not read_enabled,
        account_generation=state.account_generation,
    )


def parse_enabled_users(raw: str | Iterable[str]) -> Set[str]:
    if isinstance(raw, str):
        return {uid.strip() for uid in raw.split(",") if uid.strip()}
    return {uid.strip() for uid in raw if uid and uid.strip()}


def _env_raw_value(
    env: Mapping[str, str] | None,
    *,
    key: str,
    default: str,
) -> str:
    source = env if env is not None else os.environ
    if key in source:
        return source.get(key, default) or default
    return default


def rollout_mode_env_value(env: Mapping[str, str] | None = None) -> str:
    """Read rollout mode from ``MEMORY_MODE``.

    Does **not** read ``CANONICAL_MEMORY_USERS`` — cohort membership is separate (WS-E).
    """
    raw = _env_raw_value(env, key=MEMORY_MODE_ENV, default="")
    return (raw or MemoryRolloutMode.off.value).strip() or MemoryRolloutMode.off.value


def rollout_enabled_users_env_raw(env: Mapping[str, str] | None = None) -> str:
    """Read enabled-user list from ``MEMORY_ENABLED_USERS``."""
    return _env_raw_value(env, key=MEMORY_ENABLED_USERS_ENV, default="")


def rollout_v3_get_enabled_env_value(env: Mapping[str, str] | None = None) -> bool:
    """Read v3 GET route toggle from ``MEMORY_V3_GET_ENABLED``."""
    raw = _env_raw_value(env, key=MEMORY_V3_GET_ENABLED_ENV, default="")
    return str(raw).strip().lower() == "true"


__all__ = [
    "MEMORY_ENABLED_USERS_ENV",
    "MEMORY_MODE_ENV",
    "MEMORY_V3_GET_ENABLED_ENV",
    "MemoryRolloutCapabilities",
    "MemoryRolloutConfig",
    "MemoryRolloutMode",
    "MemoryRolloutStageGate",
    "MemoryRolloutState",
    "PASSED",
    "MemoryRolloutCapabilities",
    "MemoryRolloutMode",
    "MemoryRolloutConfig",
    "MemoryRolloutState",
    "MemoryRolloutStageGate",
    "decide_memory_rollout_capabilities",
    "parse_enabled_users",
    "rollout_enabled_users_env_raw",
    "rollout_mode_env_value",
    "rollout_v3_get_enabled_env_value",
]
