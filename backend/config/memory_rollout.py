"""Global canonical-memory safety controls.

Memory and task product authority is universal for authenticated accounts. The
one user-facing product switch is ``MEMORY_ENABLED=on|off``. Code fail-closes
to ``off`` when it is unset.

``on`` enables intake and list. It maps to write-mode intake, not scheduled
ST→LT maintenance (that remains ``MEMORY_CANONICAL_MAINTENANCE_ENABLED`` on
``memory-maintenance-job``).
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

MEMORY_ENABLED_ENV = "MEMORY_ENABLED"

_ENABLED_ON = frozenset({"on", "true", "1"})


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
    by ``MemoryService`` through ``MEMORY_ENABLED``.
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


def _explicit_enabled_token(env: Mapping[str, str] | None = None) -> str:
    return (_env_raw_value(env, key=MEMORY_ENABLED_ENV, default="") or "").strip().lower()


def memory_enabled_env_value(env: Mapping[str, str] | None = None) -> bool:
    """Read the one user-facing product flag. Unset fail-closes to off."""
    return _explicit_enabled_token(env) in _ENABLED_ON


def rollout_mode_env_value(env: Mapping[str, str] | None = None) -> str:
    """Derive the intake fence from ``MEMORY_ENABLED``.

    ``MEMORY_ENABLED=on`` is write-mode intake (create+list), never Gate 3 read.
    """
    return MemoryRolloutMode.write.value if memory_enabled_env_value(env) else MemoryRolloutMode.off.value


__all__ = [
    "MEMORY_ENABLED_ENV",
    "MemoryRolloutCapabilities",
    "MemoryRolloutMode",
    "memory_enabled_env_value",
    "rollout_mode_env_value",
    "universal_memory_capabilities",
]
