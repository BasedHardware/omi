"""Default-off gate for the canary live STT failover recovery path.

The switch is a pod-level environment variable snapshot once per session:
``ListenSessionRuntime`` pins ``current_recovery_enabled`` for the whole run,
and components constructed inside a session read the pinned value (or an
explicit ``recovery_enabled`` attribute on their owner chain) instead of
re-reading the environment, so a session never changes mode mid-flight.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Any

STT_FAILOVER_RECOVERY_ENV = 'STT_FAILOVER_RECOVERY_ENABLED'

current_recovery_enabled: ContextVar['bool | None'] = ContextVar('stt_failover_recovery_enabled', default=None)


def recovery_enabled() -> bool:
    pinned = current_recovery_enabled.get()
    if pinned is not None:
        return pinned
    return os.getenv(STT_FAILOVER_RECOVERY_ENV, 'false').lower() == 'true'


def session_recovery_enabled(owner: Any) -> bool:
    """Read an explicit ``recovery_enabled`` bool on owner, its receiver, or its
    host; fall back to the session/env pin only when none declares a bool."""
    for holder in (owner, getattr(owner, 'receiver', None), getattr(owner, 'host', None)):
        value = getattr(holder, 'recovery_enabled', None)
        if type(value) is bool:
            return value
    return recovery_enabled()
