import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional, Set


class V17Mode(str, Enum):
    off = "off"
    shadow = "shadow"
    write = "write"
    read = "read"


@dataclass(frozen=True)
class V17Capabilities:
    uid: str
    mode: V17Mode
    legacy_only: bool
    shadow_artifacts_enabled: bool
    v17_writes_enabled: bool
    v17_reads_enabled: bool
    legacy_reads_authoritative: bool


@dataclass
class V17RolloutConfig:
    enabled_users: Set[str] = field(default_factory=set)
    mode: V17Mode = V17Mode.off
    backfill_enabled: bool = False
    backfill_daily_limit: int = 0
    archive_opt_in_enabled: bool = False

    @classmethod
    def from_env(cls) -> "V17RolloutConfig":
        users = {uid.strip() for uid in os.getenv("V17_MEMORY_ENABLED_USERS", "").split(",") if uid.strip()}
        mode = V17Mode(os.getenv("V17_MODE", V17Mode.off.value).strip() or V17Mode.off.value)
        return cls(
            enabled_users=users,
            mode=mode,
            backfill_enabled=os.getenv("V17_BACKFILL_ENABLED", "false").lower() == "true",
            backfill_daily_limit=int(os.getenv("V17_BACKFILL_DAILY_LIMIT", "0") or 0),
            archive_opt_in_enabled=os.getenv("V17_ARCHIVE_OPT_IN_ENABLED", "false").lower() == "true",
        )

    def for_user(self, uid: str) -> V17Capabilities:
        if self.mode == V17Mode.off or uid not in self.enabled_users:
            return V17Capabilities(
                uid=uid,
                mode=V17Mode.off,
                legacy_only=True,
                shadow_artifacts_enabled=False,
                v17_writes_enabled=False,
                v17_reads_enabled=False,
                legacy_reads_authoritative=True,
            )
        return decide_v17_capabilities(uid, self.mode)


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

    def can_transition_to(self, target: V17Mode) -> bool:
        if target == self.mode:
            return True
        if target == V17Mode.off and self.persistent_v17_writes_started:
            return self.decommission_reconciled
        if self.mode == V17Mode.read and target == V17Mode.write:
            return self.fallback_projection_ready
        if target == V17Mode.read:
            return self.fallback_projection_ready
        return True


def decide_v17_capabilities(uid: str, mode: V17Mode | str) -> V17Capabilities:
    resolved = mode if isinstance(mode, V17Mode) else V17Mode(mode)
    if resolved == V17Mode.off:
        return V17Capabilities(uid, resolved, True, False, False, False, True)
    if resolved == V17Mode.shadow:
        return V17Capabilities(uid, resolved, False, True, False, False, True)
    if resolved == V17Mode.write:
        return V17Capabilities(uid, resolved, False, True, True, False, True)
    if resolved == V17Mode.read:
        return V17Capabilities(uid, resolved, False, True, True, True, False)
    raise ValueError(f"Unsupported V17 mode: {mode}")


def parse_enabled_users(raw: str | Iterable[str]) -> Set[str]:
    if isinstance(raw, str):
        return {uid.strip() for uid in raw.split(",") if uid.strip()}
    return {uid.strip() for uid in raw if uid and uid.strip()}
