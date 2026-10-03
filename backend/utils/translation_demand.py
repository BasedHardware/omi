"""Socket-local transcript visibility admission with monotonic receipt time."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping


class DemandPolicy(str, Enum):
    legacy_unknown = 'legacy_unknown'
    legacy_stale = 'legacy_stale'
    viewed = 'viewed'
    hidden = 'hidden'
    lease_expired = 'lease_expired'
    closed = 'closed'


@dataclass(frozen=True)
class DemandSnapshot:
    policy: DemandPolicy
    expires_at: float | None
    generation: int


class TranslationDemand:
    """A report belongs only to the authenticated socket that owns this object."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, lease_seconds: float = 60) -> None:
        self._clock = clock
        self._lease_seconds = lease_seconds
        self._last_report: float | None = None
        self._visible = False
        self._lease_v1 = False
        self._unsupported = False
        self._closed = False
        self._generation = 0
        self._last_rate_window: float | None = None
        self._window_reports = 0

    def observe(self, payload: Mapping[str, object], *, lease_v1_enabled: bool) -> bool:
        if self._closed or len(str(payload)) > 2048:
            return False
        foreground = payload.get('foreground')
        visible = payload.get('transcript_visible')
        if type(foreground) is not bool or type(visible) is not bool or (visible and not foreground):
            return False
        version = payload.get('translation_demand_version')
        if version is not None and (type(version) is not int or version != 1):
            self._unsupported = True
            return False
        if self._lease_v1 and version != 1:
            return False
        now = self._clock()
        if self._last_rate_window is None or now - self._last_rate_window >= 60:
            self._last_rate_window = now
            self._window_reports = 0
        if self._window_reports >= 120:
            return False
        self._window_reports += 1
        if version == 1 and not lease_v1_enabled:
            self._unsupported = True
            return False
        if version == 1:
            self._lease_v1 = True
        old_policy = self.snapshot(lease_v1_enabled=lease_v1_enabled).policy
        self._visible = visible
        self._last_report = now
        if self.snapshot(lease_v1_enabled=lease_v1_enabled).policy != old_policy:
            self._generation += 1
        return True

    def snapshot(self, *, lease_v1_enabled: bool) -> DemandSnapshot:
        if self._closed:
            return DemandSnapshot(DemandPolicy.closed, None, self._generation)
        if self._unsupported or self._last_report is None:
            return DemandSnapshot(DemandPolicy.legacy_unknown, None, self._generation)
        expires_at = self._last_report + self._lease_seconds
        if self._clock() >= expires_at:
            policy = DemandPolicy.lease_expired if self._lease_v1 and lease_v1_enabled else DemandPolicy.legacy_stale
        else:
            policy = DemandPolicy.viewed if self._visible else DemandPolicy.hidden
        return DemandSnapshot(policy, expires_at, self._generation)

    def close(self) -> None:
        self._closed = True
        self._generation += 1
