"""Flood control for the user-account Telegram plugin (plan §8).

The user-account flow is a "userbot" -- the AI replies AS the user,
not as a separate bot account. Telegram's anti-flood systems target
behaviour that looks automated: high message rates, similar content
repeated, identical send patterns, etc. A userbot that exceeds
Telegram's thresholds risks the user's account being rate-limited,
shadow-banned, or fully banned (see https://core.telegram.org/methods
for the FLOOD_WAIT_* error family).

This module provides:

1. RateLimit -- a process-local rolling-window counter that caps
   outbound messages at ``MAX_PER_HOUR`` per rolling 60 minutes.
   Default 30 (plan §8). Configurable via TELEGRAM_USER_RATE_PER_HOUR.

2. detect_flood_wait -- inspects a Telethon exception (or its
   ``__cause__`` chain) for a ``FloodWaitError`` and extracts the
   ``seconds`` field Telegram returns. Returns ``None`` if no
   FLOOD_WAIT signal is present.

3. record_send / can_send -- the rate-limit API. ``can_send`` is
   non-mutating; ``record_send`` is called after a successful send
   (NOT before -- if the send fails, we don't want to consume the
   budget).

Storage: in-process only. The plugin restarts reset the counter.
That's a deliberate trade-off: a user who restarts the desktop
gets a fresh hour, which is fine for our scale (the cap is
anti-flood, not a quota).
"""

from __future__ import annotations

import os
import time
from collections import deque
from threading import Lock
from typing import Optional


# Configurable via env. Plan §8: 30 outbound messages/hour/chats.
# Default 30. We use the same constant for "per hour" and
# "per chats" (the plan column says "<= 30 outbound messages/hour/
# chats" which we read as "30 per hour total" -- the /chats suffix
# just notes the scope).
MAX_PER_HOUR = int(os.environ.get("TELEGRAM_USER_RATE_PER_HOUR", "30"))
WINDOW_SECONDS = 3600


class RateLimit:
    """Rolling-window outbound-message counter.

    Thread-safe. ``record_send(now)`` adds a timestamp; ``can_send``
    returns True iff the rolling 60-minute window has fewer than
    ``max_per_hour`` entries.

    ``seconds_until_next_slot()`` is informational: how long until
    the OLDEST in-window message ages out, opening a new slot.
    """

    def __init__(
        self,
        max_per_hour: int = MAX_PER_HOUR,
        window_seconds: int = WINDOW_SECONDS,
        clock: Optional[callable] = None,  # for tests
    ) -> None:
        self.max_per_hour = max_per_hour
        self.window_seconds = window_seconds
        self._now = clock or time.monotonic
        self._send_times: "deque[float]" = deque()
        self._lock = Lock()

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._send_times and self._send_times[0] < cutoff:
            self._send_times.popleft()

    def can_send(self) -> bool:
        with self._lock:
            self._trim(self._now())
            return len(self._send_times) < self.max_per_hour

    def record_send(self, now: Optional[float] = None) -> None:
        with self._lock:
            self._trim(self._now() if now is None else now)
            self._send_times.append(self._now() if now is None else now)

    def seconds_until_next_slot(self) -> int:
        """If the limit is hit, how many seconds until the oldest
        in-window message ages out? Returns 0 if a slot is free
        right now.
        """
        with self._lock:
            self._trim(self._now())
            if len(self._send_times) < self.max_per_hour:
                return 0
            oldest = self._send_times[0]
            wait = self.window_seconds - (self._now() - oldest)
            return max(1, int(wait))

    def in_window_count(self) -> int:
        with self._lock:
            self._trim(self._now())
            return len(self._send_times)


def detect_flood_wait(exc: BaseException) -> Optional[int]:
    """If ``exc`` (or its ``__cause__`` chain) is a Telethon
    ``FloodWaitError``, return the ``seconds`` field Telegram
    returned. Otherwise return None.

    Telethon's ``FloodWaitError`` carries ``seconds`` as an
    attribute. We check by class name (not isinstance) to avoid
    importing telethon in the test path -- the real Telethon
    raises from ``telethon.errors.FloodWaitError`` which is the
    class we want to match by name.
    """
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        cls_name = type(current).__name__
        if cls_name == "FloodWaitError":
            seconds = getattr(current, "seconds", None)
            if isinstance(seconds, (int, float)):
                return int(seconds)
        # Telethon wraps the original in some flows. Walk the
        # __cause__ chain looking for the marker.
        current = current.__cause__
    return None


# Module-level singleton. main.py imports this and calls
# .can_send() / .record_send() on every outbound message. Tests
# can construct their own RateLimit instance to avoid sharing
# state with the singleton.
default_rate_limit = RateLimit()
