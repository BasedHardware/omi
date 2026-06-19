import os
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable, Optional, Set


class V17Mode(str, Enum):
    off = "off"
    shadow = "shadow"
    write = "write"
    read = "read"


class V17StageGate(str, Enum):
    shadow = "shadow"
    write = "write"
    read = "read"


PASSED = "passed"


@dataclass(frozen=True)
class V17Capabilities:
    uid: str
    mode: V17Mode
    legacy_only: bool
    shadow_artifacts_enabled: bool
    v17_writes_enabled: bool
    v17_reads_enabled: bool
    legacy_reads_authoritative: bool
    account_generation: int = 0


@dataclass
class V17RolloutState:
    uid: str
    mode: V17Mode = V17Mode.off
    mode_epoch: int = 0
    cutover_epoch: int = 0
    account_generation: int = 0
    last_reconciled_legacy_revision: Optional[str] = None
    fallback_projection_ready: bool = False
    persistent_v17_writes_started: bool = False
    decommission_reconciled: bool = False
    writes_blocked: bool = False
    stage_gates: dict[V17StageGate, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.mode_epoch < 0:
            raise ValueError("mode_epoch must be nonnegative")
        if self.cutover_epoch < 0:
            raise ValueError("cutover_epoch must be nonnegative")
        if self.account_generation < 0:
            raise ValueError("account_generation must be nonnegative")
        self.stage_gates = {
            key if isinstance(key, V17StageGate) else V17StageGate(key): value
            for key, value in self.stage_gates.items()
        }

    def gate_passed(self, gate: V17StageGate) -> bool:
        return self.stage_gates.get(gate) == PASSED

    def can_transition_to(self, target: V17Mode) -> bool:
        if target == self.mode:
            return True
        if target == V17Mode.off and self.persistent_v17_writes_started:
            return self.decommission_reconciled
        if self.mode == V17Mode.read and target in {V17Mode.write, V17Mode.shadow, V17Mode.off}:
            if target == V17Mode.off and self.decommission_reconciled:
                return True
            return self.fallback_projection_ready
        if target == V17Mode.read:
            return self.fallback_projection_ready and self.gate_passed(V17StageGate.read)
        return True

    def transition_to(self, target: V17Mode) -> "V17RolloutState":
        if not self.can_transition_to(target):
            raise ValueError(f"Cannot transition from {self.mode.value} to {target.value}")
        next_epoch = self.mode_epoch + (0 if target == self.mode else 1)
        cutover_epoch = self.cutover_epoch
        if target == V17Mode.read and self.mode != V17Mode.read:
            cutover_epoch = next_epoch
        return replace(self, mode=target, mode_epoch=next_epoch, cutover_epoch=cutover_epoch)


@dataclass
class V17RolloutConfig:
    enabled_users: Set[str] = field(default_factory=set)
    mode: V17Mode = V17Mode.off
    backfill_enabled: bool = False
    backfill_daily_limit: int = 0
    archive_opt_in_enabled: bool = False

    @classmethod
    def from_env(cls) -> "V17RolloutConfig":
        mode = V17Mode(os.getenv("V17_MODE", V17Mode.off.value).strip() or V17Mode.off.value)
        limit = int(os.getenv("V17_BACKFILL_DAILY_LIMIT", "0") or 0)
        if limit < 0:
            raise ValueError("V17_BACKFILL_DAILY_LIMIT must be nonnegative")
        return cls(
            enabled_users=parse_enabled_users(os.getenv("V17_MEMORY_ENABLED_USERS", "")),
            mode=mode,
            backfill_enabled=os.getenv("V17_BACKFILL_ENABLED", "false").lower() == "true",
            backfill_daily_limit=limit,
            archive_opt_in_enabled=os.getenv("V17_ARCHIVE_OPT_IN_ENABLED", "false").lower() == "true",
        )

    def for_user(self, uid: str, state: Optional[V17RolloutState] = None) -> V17Capabilities:
        if self.mode == V17Mode.off or uid not in self.enabled_users:
            return _legacy_capabilities(uid)
        if state is None:
            state = V17RolloutState(uid=uid, mode=self.mode, stage_gates={V17StageGate.shadow: PASSED})
        if state.uid != uid:
            return _legacy_capabilities(uid)
        return decide_v17_capabilities(uid, self.mode, state)


def _legacy_capabilities(uid: str) -> V17Capabilities:
    return V17Capabilities(
        uid=uid,
        mode=V17Mode.off,
        legacy_only=True,
        shadow_artifacts_enabled=False,
        v17_writes_enabled=False,
        v17_reads_enabled=False,
        legacy_reads_authoritative=True,
    )


def decide_v17_capabilities(uid: str, mode: V17Mode | str, state: V17RolloutState) -> V17Capabilities:
    resolved = mode if isinstance(mode, V17Mode) else V17Mode(mode)
    if resolved == V17Mode.off:
        return _legacy_capabilities(uid)

    shadow_enabled = state.gate_passed(V17StageGate.shadow)
    write_enabled = (
        resolved in {V17Mode.write, V17Mode.read}
        and shadow_enabled
        and state.gate_passed(V17StageGate.write)
        and not state.writes_blocked
    )
    read_enabled = (
        resolved == V17Mode.read
        and write_enabled
        and state.gate_passed(V17StageGate.read)
        and state.fallback_projection_ready
    )
    return V17Capabilities(
        uid=uid,
        mode=resolved,
        legacy_only=False,
        shadow_artifacts_enabled=shadow_enabled,
        v17_writes_enabled=write_enabled,
        v17_reads_enabled=read_enabled,
        legacy_reads_authoritative=not read_enabled,
        account_generation=state.account_generation,
    )


def parse_enabled_users(raw: str | Iterable[str]) -> Set[str]:
    if isinstance(raw, str):
        return {uid.strip() for uid in raw.split(",") if uid.strip()}
    return {uid.strip() for uid in raw if uid and uid.strip()}
