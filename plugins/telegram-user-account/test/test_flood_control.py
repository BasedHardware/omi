"""Tests for flood_control.py (plan §8).

Pins the contract:
- Rolling 60-min window
- can_send() is non-mutating
- record_send() is called only on success (not on failure)
- detect_flood_wait() walks the __cause__ chain
- env override: TELEGRAM_USER_RATE_PER_HOUR
"""

from __future__ import annotations

import pytest

import flood_control


# ---------------------------------------------------------------------------
# Section 1: RateLimit basic
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_can_send_when_under_cap(self):
        rl = flood_control.RateLimit(max_per_hour=3, clock=lambda: 1000.0)
        assert rl.can_send() is True
        rl.record_send()
        assert rl.can_send() is True
        rl.record_send()
        assert rl.can_send() is True

    def test_can_send_returns_false_at_cap(self):
        rl = flood_control.RateLimit(max_per_hour=3, clock=lambda: 1000.0)
        for _ in range(3):
            rl.record_send()
        assert rl.can_send() is False

    def test_can_send_does_not_mutate_state(self):
        # can_send is the "may I send?" check; calling it should
        # not consume a slot. record_send is the mutation.
        rl = flood_control.RateLimit(max_per_hour=2, clock=lambda: 1000.0)
        rl.record_send()
        # can_send called many times -- still 1 in window.
        for _ in range(100):
            assert rl.can_send() is True
        assert rl.in_window_count() == 1

    def test_window_rolls(self):
        # At t=1000, fill the cap. At t=4600 (an hour later), the
        # OLDEST message is out of the window so can_send is True
        # again. We step the clock by 100s increments.
        t = [1000.0]
        rl = flood_control.RateLimit(max_per_hour=2, window_seconds=3600, clock=lambda: t[0])
        rl.record_send()
        t[0] = 1100.0
        rl.record_send()
        # At t=1100, cap is hit.
        assert rl.can_send() is False
        # Step 1 hour + 1s past the FIRST send (1000 + 3600 + 1 = 4601).
        t[0] = 4601.0
        assert rl.can_send() is True
        rl.record_send()  # this should succeed

    def test_seconds_until_next_slot_returns_positive_when_at_cap(self):
        rl = flood_control.RateLimit(max_per_hour=1, window_seconds=3600, clock=lambda: 1000.0)
        rl.record_send()
        assert rl.can_send() is False
        # 3600 - 0 = 3600s wait.
        assert rl.seconds_until_next_slot() == 3600

    def test_seconds_until_next_slot_returns_0_when_free(self):
        rl = flood_control.RateLimit(max_per_hour=5, clock=lambda: 1000.0)
        assert rl.seconds_until_next_slot() == 0

    def test_seconds_until_next_slot_reservations_only_no_crash(self):
        """Edge case: capacity exhausted ONLY by in-flight reservations
        (no committed sends). Must NOT crash with IndexError.
        See cubic review #4669301493."""
        rl = flood_control.RateLimit(max_per_hour=1, window_seconds=3600, clock=lambda: 1000.0)
        assert rl.reserve_slot() is True
        # _send_times is empty but effective_count == max_per_hour.
        # Must return a positive int, not crash.
        wait = rl.seconds_until_next_slot()
        assert isinstance(wait, int)
        assert wait >= 1

    def test_in_window_count_includes_reservations(self):
        """in_window_count accounts for reserved slots."""
        rl = flood_control.RateLimit(max_per_hour=5, clock=lambda: 1000.0)
        rl.record_send()
        rl.record_send()
        rl.reserve_slot()
        assert rl.in_window_count() == 3  # 2 committed + 1 reserved

    def test_in_window_count(self):
        rl = flood_control.RateLimit(max_per_hour=10, clock=lambda: 1000.0)
        assert rl.in_window_count() == 0
        for _ in range(7):
            rl.record_send()
        assert rl.in_window_count() == 7


# ---------------------------------------------------------------------------
# Section 2: env override
# ---------------------------------------------------------------------------


class TestEnvOverride:
    def test_default_max_per_hour_is_30(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_USER_RATE_PER_HOUR", raising=False)
        # Re-evaluate MAX_PER_HOUR with the env unset. (Import
        # already evaluated it once at module load, but the
        # constant `MAX_PER_HOUR` is the env-read value as of
        # import; the test just pins what the default IS.)
        assert flood_control.MAX_PER_HOUR == 30

    def test_env_override_changes_max(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_USER_RATE_PER_HOUR", "5")
        # Reload the module so MAX_PER_HOUR is re-evaluated.
        import importlib

        importlib.reload(flood_control)
        try:
            assert flood_control.MAX_PER_HOUR == 5
        finally:
            monkeypatch.delenv("TELEGRAM_USER_RATE_PER_HOUR", raising=False)
            importlib.reload(flood_control)


# ---------------------------------------------------------------------------
# Section 3: detect_flood_wait
# ---------------------------------------------------------------------------


class FloodWaitError(Exception):  # noqa: N801
    """A stand-in for telethon.errors.FloodWaitError.

    We match by class NAME in detect_flood_wait, so the fake
    only needs the right __name__ and the `seconds` attribute.
    """

    def __init__(self, seconds: int):
        super().__init__(f"FLOOD_WAIT_{seconds}")
        self.seconds = seconds


class TestDetectFloodWait:
    def test_returns_seconds_for_flood_wait(self):
        exc = FloodWaitError(seconds=42)
        assert flood_control.detect_flood_wait(exc) == 42

    def test_returns_none_for_unrelated_exception(self):
        exc = ValueError("not a flood wait")
        assert flood_control.detect_flood_wait(exc) is None

    def test_walks_cause_chain(self):
        original = FloodWaitError(seconds=120)
        wrapper = None
        try:
            try:
                raise original
            except Exception as e:
                raise RuntimeError("wrapped") from e
        except RuntimeError as caught:
            wrapper = caught
        assert wrapper is not None
        assert flood_control.detect_flood_wait(wrapper) == 120

    def test_returns_none_when_flood_wait_has_no_seconds(self):
        class _BrokenFloodWait(Exception):
            pass

        # Class name matches but no `seconds` attribute. We
        # shouldn't crash; return None.
        exc = _BrokenFloodWait()
        assert flood_control.detect_flood_wait(exc) is None

    def test_handles_cycle_in_cause_chain(self):
        # Defensive: if a buggy library causes a cycle, we must
        # not infinite-loop. detect_flood_wait tracks `id()`
        # to break cycles.
        a = ValueError("a")
        b = ValueError("b")
        a.__cause__ = b
        b.__cause__ = a
        assert flood_control.detect_flood_wait(a) is None


# ---------------------------------------------------------------------------
# Section 4: external cooldown / block_for_seconds (cubic 4617059500 P1)
# ---------------------------------------------------------------------------


class TestBlockForSeconds:
    def test_can_send_returns_false_while_blocked(self):
        # cubic review 4617059500 P1: when Telegram returns
        # FLOOD_WAIT, the endpoint must register the cooldown
        # with the local rate limiter so the next request
        # can't sneak past via a fresh rolling window.
        rl = flood_control.RateLimit(max_per_hour=100, clock=lambda: 1000.0)
        assert rl.can_send() is True
        rl.block_for_seconds(60)
        assert rl.can_send() is False

    def test_can_send_recovers_after_block_expires(self):
        rl = flood_control.RateLimit(max_per_hour=100, clock=lambda: 1000.0)
        rl.block_for_seconds(60)
        assert rl.can_send() is False
        # The fake clock is static; build a new one that
        # returns 1061.0 to simulate 61 seconds having passed.
        rl2 = flood_control.RateLimit(max_per_hour=100, clock=lambda: 1061.0)
        # A fresh instance has no block, but the same instance
        # needs a clock that advances. Use the clock injection
        # properly: rebuild the instance with an advanced
        # clock.
        # Simpler: just verify the math via seconds_until_next_slot.
        # Replace the clock mid-test by mutating _now.
        t = [1000.0]
        rl3 = flood_control.RateLimit(max_per_hour=100, clock=lambda: t[0])
        rl3.block_for_seconds(60)
        assert rl3.can_send() is False
        t[0] = 1061.0
        assert rl3.can_send() is True

    def test_seconds_until_next_slot_returns_cooldown(self):
        # While the external block is active,
        # seconds_until_next_slot returns the REMAINING
        # cooldown, NOT the rolling-window wait. Otherwise
        # the desktop would back off for the wrong duration.
        rl = flood_control.RateLimit(max_per_hour=100, clock=lambda: 1000.0)
        rl.block_for_seconds(120)
        assert rl.seconds_until_next_slot() == 120

    def test_block_for_seconds_is_idempotent_max(self):
        # A longer block extends; a shorter one is ignored.
        # This handles FLOOD_WAIT_5 right after FLOOD_WAIT_60.
        rl = flood_control.RateLimit(max_per_hour=100, clock=lambda: 1000.0)
        rl.block_for_seconds(60)
        rl.block_for_seconds(5)  # shorter, should be ignored
        assert rl.seconds_until_next_slot() == 60
        rl.block_for_seconds(120)  # longer, should extend
        assert rl.seconds_until_next_slot() == 120

    def test_block_for_seconds_zero_or_negative_is_noop(self):
        rl = flood_control.RateLimit(max_per_hour=100, clock=lambda: 1000.0)
        rl.block_for_seconds(0)
        assert rl.can_send() is True
        rl.block_for_seconds(-1)
        assert rl.can_send() is True

    def test_is_blocked(self):
        rl = flood_control.RateLimit(max_per_hour=100, clock=lambda: 1000.0)
        assert rl.is_blocked() is False
        rl.block_for_seconds(60)
        assert rl.is_blocked() is True

    def test_block_independent_of_window(self):
        # The external block must apply EVEN when the rolling
        # window is empty. This is the cubic 4617059500 P1
        # concern: without the block, a fresh start with an
        # empty window would pass can_send() immediately after
        # a FLOOD_WAIT.
        rl = flood_control.RateLimit(max_per_hour=100, clock=lambda: 1000.0)
        # No record_send called -- rolling window is empty.
        # But the external block is active.
        rl.block_for_seconds(60)
        assert rl.can_send() is False
        assert rl.in_window_count() == 0  # window is still empty


# ---------------------------------------------------------------------------
# Section 5: default_rate_limit singleton
# ---------------------------------------------------------------------------


class TestDefaultRateLimit:
    def test_singleton_exists(self):
        assert isinstance(flood_control.default_rate_limit, flood_control.RateLimit)

    def test_singleton_max_per_hour_uses_env(self, monkeypatch):
        # Reload module to pick up the env value.
        monkeypatch.setenv("TELEGRAM_USER_RATE_PER_HOUR", "7")
        import importlib

        importlib.reload(flood_control)
        try:
            assert flood_control.default_rate_limit.max_per_hour == 7
        finally:
            monkeypatch.delenv("TELEGRAM_USER_RATE_PER_HOUR", raising=False)
            importlib.reload(flood_control)


# ---------------------------------------------------------------------------
# Section 5: daily counter (plan §8 messages-sent-today)
# ---------------------------------------------------------------------------


def _fixed_wall_clock(year, month, day):
    """Build a wall_clock callable that returns a fixed
    (year, month, day, ...) tuple. Only the date portion
    matters for the daily counter.
    """

    def _wall():
        return (year, month, day, 0, 0, 0, 0, 0, 0)

    return _wall


class TestDailyCounter:
    def test_starts_at_zero(self):
        rl = flood_control.RateLimit(
            max_per_hour=10,
            wall_clock=_fixed_wall_clock(2026, 7, 2),
        )
        assert rl.daily_count() == 0

    def test_record_send_bumps_daily_count(self):
        rl = flood_control.RateLimit(
            max_per_hour=10,
            wall_clock=_fixed_wall_clock(2026, 7, 2),
        )
        rl.record_send()
        rl.record_send()
        rl.record_send()
        assert rl.daily_count() == 3

    def test_daily_count_independent_of_window(self):
        # The daily counter survives window eviction -- unlike
        # in_window_count which trims to the rolling 60 min.
        # For a daily counter, we want the FULL count for the
        # day, not just the most-recent-hour.
        rl = flood_control.RateLimit(
            max_per_hour=1000,  # high cap so the window doesn't trim
            wall_clock=_fixed_wall_clock(2026, 7, 2),
        )
        for _ in range(50):
            rl.record_send()
        assert rl.daily_count() == 50
        # in_window_count also shows 50 (cap is 1000).
        assert rl.in_window_count() == 50

    def test_day_rollover_resets_count(self):
        # Day 1: 5 sends.
        # Day 2: 3 more sends. The daily_count() call on day 2
        # should report 3, not 8.
        day1_wall = [_fixed_wall_clock(2026, 7, 2)]
        day2_wall = [_fixed_wall_clock(2026, 7, 3)]
        rl = flood_control.RateLimit(max_per_hour=1000, wall_clock=day1_wall[0])
        for _ in range(5):
            rl.record_send()
        assert rl.daily_count() == 5
        # Switch the wall clock to day 2.
        rl._wall_clock = day2_wall[0]
        # 3 more sends on day 2.
        for _ in range(3):
            rl.record_send()
        # daily_count() lazily resets on rollover -- reports 3.
        assert rl.daily_count() == 3

    def test_daily_count_resets_on_read_after_rollover(self):
        # If the clock advanced but no record_send has been
        # called yet, daily_count() should still show 0 (lazy
        # reset on read).
        day1_wall = _fixed_wall_clock(2026, 7, 2)
        day2_wall = _fixed_wall_clock(2026, 7, 3)
        rl = flood_control.RateLimit(max_per_hour=1000, wall_clock=day1_wall)
        for _ in range(7):
            rl.record_send()
        assert rl.daily_count() == 7
        # Time advances to day 2, no new sends.
        rl._wall_clock = day2_wall
        assert rl.daily_count() == 0
