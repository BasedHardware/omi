"""Global canonical-memory safety controls.

Memory and task product authority is universal for authenticated accounts. The
one user-facing product switch is ``MEMORY_ENABLED=on|off``. Code fail-closes
to ``off`` when it is unset. ``MEMORY_MODE`` and ``MEMORY_V3_GET_ENABLED``
remain one-deploy aliases so old revisions do not explode; they are not
written in overlays or charts.

``on`` enables intake and list. It maps to write-mode intake, not scheduled
ST→LT maintenance (that remains ``MEMORY_CANONICAL_MAINTENANCE_ENABLED`` on
``memory-maintenance-job``).
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

MEMORY_ENABLED_ENV = "MEMORY_ENABLED"
MEMORY_MODE_ENV = "MEMORY_MODE"
MEMORY_V3_GET_ENABLED_ENV = "MEMORY_V3_GET_ENABLED"

_ENABLED_ON = frozenset({"on", "true", "1"})
_MODE_ON = frozenset({"write", "read"})


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
    """Read the one user-facing product flag. Unset fail-closes to off.

    Aliases when ``MEMORY_ENABLED`` is unset: ``MEMORY_MODE=write|read`` → on,
    ``off|shadow`` → off.
    """
    token = _explicit_enabled_token(env)
    if token:
        return token in _ENABLED_ON
    mode = (_env_raw_value(env, key=MEMORY_MODE_ENV, default="") or "").strip().lower()
    return mode in _MODE_ON


def rollout_mode_env_value(env: Mapping[str, str] | None = None) -> str:
    """Derive the intake fence from ``MEMORY_ENABLED``, with ``MEMORY_MODE`` as alias.

    ``MEMORY_ENABLED=on`` is write-mode intake (create+list), never Gate 3 read.
    When the product flag is unset, the raw ``MEMORY_MODE`` string is returned
    so an old revision's ``write|read|off|shadow`` keeps working.
    """
    if _explicit_enabled_token(env):
        return MemoryRolloutMode.write.value if memory_enabled_env_value(env) else MemoryRolloutMode.off.value
    raw = _env_raw_value(env, key=MEMORY_MODE_ENV, default="")
    return (raw or MemoryRolloutMode.off.value).strip() or MemoryRolloutMode.off.value


def rollout_v3_get_enabled_env_value(env: Mapping[str, str] | None = None) -> bool:
    """Leftover GET toggle. Prefer ``MEMORY_ENABLED``; ``MEMORY_V3_GET_ENABLED`` is alias only.

    The live ``GET /v3/memories`` route does not call this. List 503s come from
    ``MEMORY_V3_CURSOR_SECRET`` / ``read_page``, not this flag.
    """
    if _explicit_enabled_token(env):
        return memory_enabled_env_value(env)
    raw = _env_raw_value(env, key=MEMORY_V3_GET_ENABLED_ENV, default="")
    return str(raw).strip().lower() == "true"


__all__ = [
    "MEMORY_ENABLED_ENV",
    "MEMORY_MODE_ENV",
    "MEMORY_V3_GET_ENABLED_ENV",
    "MemoryRolloutCapabilities",
    "MemoryRolloutMode",
    "memory_enabled_env_value",
    "rollout_mode_env_value",
    "rollout_v3_get_enabled_env_value",
    "universal_memory_capabilities",
]
