"""How much of a live session anyone could actually watch in real time.

Clients report ``{"type": "client_state", "foreground": bool, "transcript_visible": bool}``
whenever either changes. The server splits the session's wall time into four buckets:

- ``visible``: the live transcript was on screen;
- ``foreground``: the app was in front, but the transcript was not;
- ``background``: the app was not in front (a wearable in a pocket);
- ``unreported``: the client never sent a state, e.g. builds that predate this message.

This is the measurement behind routing background capture off real-time vendor
streams. It never changes routing itself, holds no audio or text, and keeps O(1) state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Callable, Mapping

REALTIME_DEMAND_BUCKETS = ('visible', 'foreground', 'background', 'unreported')

# A client flapping state is not a reason to spend work; past this many reports
# the tracker keeps the last known state and stops counting changes.
MAX_STATE_REPORTS = 2000


def _bucket(foreground: bool, visible: bool) -> str:
    if visible:
        return 'visible'
    return 'foreground' if foreground else 'background'


@dataclass
class RealtimeDemandTracker:
    clock: Callable[[], float] = monotonic
    started_at: float = field(default=-1.0)
    _state: str | None = None
    _since: float = 0.0
    _seconds: dict[str, float] = field(default_factory=lambda: dict.fromkeys(REALTIME_DEMAND_BUCKETS, 0.0))
    reports: int = 0

    def __post_init__(self) -> None:
        if self.started_at < 0:
            self.started_at = self.clock()
        self._since = self.started_at

    @property
    def reported(self) -> bool:
        return self._state is not None

    def observe(self, payload: Mapping[str, Any]) -> bool:
        """Apply one client_state message. Returns False when it is malformed or over budget."""

        foreground, visible = payload.get('foreground'), payload.get('transcript_visible')
        if not isinstance(foreground, bool) or not isinstance(visible, bool):
            return False
        if self.reports >= MAX_STATE_REPORTS:
            return False
        self.reports += 1
        now = self.clock()
        # Clients report on connect, so the moments before the first report belong
        # to that first state; `unreported` is reserved for clients that never report.
        if self._state is not None:
            self._seconds[self._state] += max(0.0, now - self._since)
            self._since = now
        # A visible transcript implies the app is in front, whatever the flag says.
        self._state = _bucket(foreground or visible, visible)
        return True

    def totals(self) -> dict[str, float]:
        """Seconds per bucket up to now. Safe to call repeatedly."""

        now = self.clock()
        out = dict(self._seconds)
        out[self._state or 'unreported'] += max(0.0, now - self._since)
        return out
