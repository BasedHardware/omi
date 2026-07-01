"""Regression test for should_nudge tz-aware/naive datetime subtraction.

Cubic-found P2 on PR #8531: when the user file is reloaded from disk
with a tz-aware timestamp (e.g. when the file was written by a newer
Python that includes 'Z' suffix or an explicit offset), subtracting it
from datetime.utcnow() (naive) raises TypeError in production webhooks.

should_nudge() must normalize both sides to naive UTC before subtracting.

P2 (cubic follow-up): use the shared conftest's load_simple_storage()
helper instead of duplicating the module-loading helper + mutating
sys.path at module level. The conftest already handles sys.modules
isolation via an autouse fixture so this test doesn't pollute other
tests' sys.path.
"""

from conftest import load_simple_storage


class TestShouldNudgeTzAware:
    def setup_method(self):
        self.mod = load_simple_storage()

    def test_naive_isoformat_does_not_crash(self):
        # Old format (datetime.utcnow().isoformat() — no tz suffix).
        user = {"last_nudge_at": "2026-06-29T10:00:00.000000"}
        # Cooldown of 0 → always nudge. Must NOT raise TypeError.
        assert self.mod.should_nudge(user, cooldown_seconds=0) is True

    def test_z_suffix_isoformat_does_not_crash(self):
        # Newer Python emits 'Z' suffix → tz-aware. Previously this raised
        # TypeError when subtracted from datetime.utcnow() (naive).
        user = {"last_nudge_at": "2026-06-29T10:00:00.000000Z"}
        assert self.mod.should_nudge(user, cooldown_seconds=0) is True

    def test_offset_isoformat_does_not_crash(self):
        # Explicit offset (e.g. +07:00 for Bangkok) → tz-aware.
        user = {"last_nudge_at": "2026-06-29T10:00:00.000000+07:00"}
        assert self.mod.should_nudge(user, cooldown_seconds=0) is True

    def test_future_aware_timestamp_returns_false(self):
        """A timestamp in the future should always be 'too recent to nudge'."""
        from datetime import datetime, timedelta, timezone

        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        user = {"last_nudge_at": future}
        # 1-second cooldown against a 1-hour-future timestamp → not yet time.
        assert self.mod.should_nudge(user, cooldown_seconds=1.0) is False

    def test_malformed_timestamp_returns_true(self):
        """If we can't parse the timestamp at all, default to 'nudge now' —
        the alternative (returning False) would silently drop the nudge
        message forever."""
        user = {"last_nudge_at": "not-a-timestamp"}
        assert self.mod.should_nudge(user, cooldown_seconds=99999) is True
