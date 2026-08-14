"""Global canonical-memory safety controls.

Memory and task product authority is universal for authenticated accounts.  The
remaining mode is a deployment-wide incident/readiness switch; it must never be
combined with a UID inventory or used as product entitlement.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

MEMORY_MODE_ENV = "MEMORY_MODE"
MEMORY_V3_GET_ENABLED_ENV = "MEMORY_V3_GET_ENABLED"


class MemoryRolloutMode(str, Enum):
    off = "off"
    shadow = "shadow"
    write = "write"
    read = "read"


MemoryRolloutMode = MemoryRolloutMode


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


def universal_memory_capabilities(uid: str, *, account_generation: int = 0) -> MemoryRolloutCapabilities:
    """Return the single memory capability policy shared by all accounts.

    The legacy fields remain in this internal DTO while released callers are
    migrated, but they are constants and never derive from UID enrollment or a
    persisted rollout state machine. Global write incident control is enforced
    by ``MemoryService`` through ``MEMORY_MODE``.
    """

    if account_generation < 0:
        raise ValueError("account_generation must be nonnegative")
    return MemoryRolloutCapabilities(
        uid=uid,
        mode=MemoryRolloutMode.read,
        legacy_only=False,
        shadow_artifacts_enabled=False,
        memory_writes_enabled=True,
        memory_reads_enabled=True,
        legacy_reads_authoritative=False,
        account_generation=account_generation,
    )


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
    """Read the deployment-wide memory safety mode from ``MEMORY_MODE``."""
    raw = _env_raw_value(env, key=MEMORY_MODE_ENV, default="")
    return (raw or MemoryRolloutMode.off.value).strip() or MemoryRolloutMode.off.value


def rollout_v3_get_enabled_env_value(env: Mapping[str, str] | None = None) -> bool:
    """Read v3 GET route toggle from ``MEMORY_V3_GET_ENABLED``."""
    raw = _env_raw_value(env, key=MEMORY_V3_GET_ENABLED_ENV, default="")
    return str(raw).strip().lower() == "true"


__all__ = [
    "MEMORY_MODE_ENV",
    "MEMORY_V3_GET_ENABLED_ENV",
    "MemoryRolloutCapabilities",
    "MemoryRolloutMode",
    "rollout_mode_env_value",
    "rollout_v3_get_enabled_env_value",
    "universal_memory_capabilities",
]
