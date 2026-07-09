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
from datetime import date
from threading import Lock
from typing import Optional


# Configurable via env. Plan §8: 30 outbound messages/hour/chats.
# Default 30. We use the same constant for "per hour" and
# "per chats" (the plan column says "≤ 30 outbound messages/hour/
# chats" which we read as "30 per hour total" -- the /chats suffix
# just notes the scope).
MAX_PER_HOUR = int(os.environ.get("TELEGRAM_USER_RATE_PER_HOUR", "30"))
WINDOW_SECONDS = 3600


class RateLimit:
    """Rolling-window outbound-message counter with external cooldown.

    Two independent gating conditions, both checked by ``can_send``:

    1. Rolling 60-minute window: ``record_send(now)`` adds a
       timestamp; the window has at most ``max_per_hour`` entries.
    2. External cooldown: ``block_for_seconds(seconds)`` sets a
       "blocked until" timestamp (set by ``main.py`` when Telegram
       returns ``FLOOD_WAIT``). While the cooldown is active,
       ``can_send`` returns False.

    Thread-safe. ``seconds_until_next_slot()`` returns the
    larger of the two waits: either the time until the oldest
    in-window message ages out, OR the remaining cooldown
    duration. This is the value the endpoint surfaces as
    ``Retry-After``."""

    def __init__(
        self,
        max_per_hour: int = MAX_PER_HOUR,
        window_seconds: int = WINDOW_SECONDS,
        clock: Optional[callable] = None,  # for tests
        wall_clock: Optional[callable] = None,  # for tests
    ) -> None:
        self.max_per_hour = max_per_hour
        self.window_seconds = window_seconds
        self._now = clock or time.monotonic
        # Wall clock for the daily counter. In production this
        # is time.localtime; tests inject a fixed return.
        self._wall_clock = wall_clock or time.localtime
        self._send_times: "deque[float]" = deque()
        # cubic review 4617059500 P1: external cooldown
        # timestamp. While self._blocked_until > self._now(),
        # can_send() returns False. Set by block_for_seconds()
        # when Telegram returns FLOOD_WAIT_*; this prevents the
        # caller from immediately retrying (and wasting LLM
        # tokens on the persona call) for the duration Telegram
        # requested.
        self._blocked_until: float = 0.0
        # Daily counter for plan §8 "messages sent today" --
        # monotonic, resets on local-time day rollover. This
        # complements the in-memory rolling-window cap (which
        # is exact but covers only 60 min) and the simple_storage
        # ring buffer (which is durable but bounded by
        # CHAT_HISTORY_MAX = 10 per chat). The exact daily
        # count lives in process memory; plugin restarts reset
        # it. Cubic review 4618627789 P2: better to expose
        # an EXACT in-memory daily counter than to read a
        # bounded undercounting source from simple_storage.
        self._daily_count: int = 0
        self._daily_date: Optional[date] = None
        # In-flight reservations: incremented by reserve_slot(),
        # decremented by commit_slot()/release_slot(). Prevents
        # concurrent DMs from all passing can_send() during the
        # ~15s LLM call and exceeding the cap.
        self._reserved_count: int = 0
        self._lock = Lock()

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._send_times and self._send_times[0] < cutoff:
            self._send_times.popleft()

    def block_for_seconds(self, seconds: int, now: Optional[float] = None) -> None:
        """Set the external cooldown to ``seconds`` from now.

        Called by ``main.py`` after a FLOOD_WAIT detection. While
        the cooldown is active, ``can_send()`` returns False and
        ``seconds_until_next_slot()`` returns the remaining
        cooldown. Idempotent: a longer cooldown extends the
        block; a shorter one is ignored.
        """
        if seconds <= 0:
            return
        with self._lock:
            current = self._now() if now is None else now
            # Don't shrink an existing block. This handles the
            # case where Telegram returns FLOOD_WAIT_5 right after
            # we just got FLOOD_WAIT_60 -- we wait the longer one.
            requested = current + seconds
            if requested > self._blocked_until:
                self._blocked_until = requested

    def can_send(self) -> bool:
        with self._lock:
            now = self._now()
            self._trim(now)
            if self._blocked_until > now:
                return False
            effective_count = len(self._send_times) + self._reserved_count
            return effective_count < self.max_per_hour

    def reserve_slot(self) -> bool:
        """Reserve a send slot BEFORE the LLM call (check-then-reserve).

        Returns True if a slot was reserved, False if the cap is hit.
        The reservation counts against the cap so concurrent DMs
        can't all pass can_send() and exceed max_per_hour during
        the ~15s persona API call.

        Must be paired with either commit_slot() (on success) or
        release_slot() (on failure). Failure to release leaks
        a slot until the process restarts.
        """
        with self._lock:
            now = self._now()
            self._trim(now)
            if self._blocked_until > now:
                return False
            effective_count = len(self._send_times) + self._reserved_count
            if effective_count >= self.max_per_hour:
                return False
            self._reserved_count += 1
            return True

    def commit_slot(self, now: Optional[float] = None) -> None:
        """Commit a reserved slot to the rolling window.

        Called AFTER send success. Converts the reservation into
        a permanent entry in _send_times and bumps the daily
        counter. If no slot was reserved, this is a no-op
        (falls back to record_send behaviour).
        """
        with self._lock:
            now = self._now() if now is None else now
            self._trim(now)
            if self._reserved_count > 0:
                self._reserved_count -= 1
            self._send_times.append(now)
            self._bump_daily_locked()

    def release_slot(self) -> None:
        """Release a reserved slot without recording a send.

        Called when the persona API fails, the reply is empty,
        or send_message raises. Releases the reservation so the
        budget isn't consumed by a failed attempt.
        """
        with self._lock:
            if self._reserved_count > 0:
                self._reserved_count -= 1

    def record_send(self, now: Optional[float] = None) -> None:
        """Record a successful outbound send. Called AFTER send
        success -- failed sends do NOT consume the budget.
        Also bumps the in-memory daily counter (plan §8
        "messages sent today"). The daily counter resets on
        local-time day rollover.
        """
        with self._lock:
            now = self._now() if now is None else now
            self._trim(now)
            self._send_times.append(now)
            self._bump_daily_locked()

    def _bump_daily_locked(self) -> None:
        """Increment the daily counter, resetting on day
        rollover. Caller must hold self._lock.
        """
        today = date(*self._wall_clock()[:3])
        if self._daily_date != today:
            self._daily_date = today
            self._daily_count = 0
        self._daily_count += 1

    def seconds_until_next_slot(self) -> int:
        """If the limit is hit, how many seconds until a slot is
        free? Returns the LARGER of:
        - (rolling window) time until the oldest in-window
          message ages out
        - (external cooldown) remaining time on the active block

        Accounts for in-flight reservations: if reservations
        consume the remaining capacity, the wait time is based
        on the rolling window (the oldest committed send must
        age out before a reservation can succeed).

        Returns 0 if a slot is free right now.
        """
        with self._lock:
            now = self._now()
            self._trim(now)
            # External cooldown takes precedence.
            if self._blocked_until > now:
                return int(self._blocked_until - now)
            effective_count = len(self._send_times) + self._reserved_count
            if effective_count < self.max_per_hour:
                return 0
            # If we're full (committed + reserved), the caller
            # must wait for the oldest committed send to age out.
            oldest = self._send_times[0]
            wait = self.window_seconds - (now - oldest)
            return max(1, int(wait))

    def in_window_count(self) -> int:
        """Committed sends + in-flight reservations in the current
        window. Use this (not len of send_times alone) to report
        the effective count to callers so 429 responses reflect
        the real blocking condition.
        """
        with self._lock:
            self._trim(self._now())
            return len(self._send_times) + self._reserved_count

    def daily_count(self) -> int:
        """Number of successful sends since the most recent
        local-time midnight. plan §8 "messages sent today".
        In-memory only: plugin restarts reset the counter.
        Exact (not bounded by per-chat ring buffers).
        """
        with self._lock:
            today = date(*self._wall_clock()[:3])
            if self._daily_date != today:
                # Day rolled over with no record_send call
                # since midnight. Reset lazily on read so the
                # counter shows 0 for the new day even if no
                # send has happened yet.
                self._daily_date = today
                self._daily_count = 0
            return self._daily_count

    def is_blocked(self) -> bool:
        """True iff an external cooldown is currently active."""
        with self._lock:
            return self._blocked_until > self._now()


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
