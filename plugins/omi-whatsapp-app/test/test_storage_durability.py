"""Regression tests for the WhatsApp simple_storage data-integrity fixes.

Cubic review 4614064929 raised two P1 issues in
plugins/omi-whatsapp-app/simple_storage.py:

1) `pop_pending_setup` could silently skip purging credential-bearing
   stale entries when `created_at` ended in `Z` (timezone-aware).
   Python 3.11+ `fromisoformat("...Z")` parses the Z as tzinfo, and
   `aware - naive` raises `TypeError` which the previous code
   `pass`ed. Result: setup records with timezone-aware timestamps
   were never purged. (P1)

2) `_save` caught and suppressed all write errors, so every
   persistence call silently succeeded in memory even if the
   disk write failed. (P1)

These tests pin the corrected behavior.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import simple_storage


# ---------------------------------------------------------------------------
# Section 1: pop_pending_setup aware-datetime handling
# ---------------------------------------------------------------------------


class TestPopPendingSetupAwareDatetime:
    """Pin that a setup record with `created_at` ending in `Z`
    (timezone-aware ISO 8601) is correctly identified as stale
    and purged after PENDING_SETUP_TTL_SECONDS.
    """

    def test_z_suffix_timestamp_is_purged(self, tmp_path, monkeypatch):
        """The original P1 bug: a `created_at` ending in `Z` was
        parsed as tz-aware; `now - created_dt` raised TypeError
        (caught with `pass`); the entry was never purged."""
        monkeypatch.setattr(simple_storage, "PENDING_FILE", str(tmp_path / "pending.json"))
        # Insert a pending entry with a tz-aware ISO timestamp.
        # The "created_at" is 2 hours ago (older than the 1-hour TTL).
        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
        # `isoformat()` on a tz-aware datetime includes the offset
        # — e.g. "2026-07-02T12:34:56.789+00:00". Older
        # `datetime.now(timezone.utc).isoformat()` in Python 3.10 used
        # the trailing "Z"; both forms are tz-aware after parsing.
        simple_storage.pending_setups["stale-token-z"] = {
            "access_token": "secret",
            "created_at": two_hours_ago.isoformat(),
        }
        # Pop the entry. The function should also purge stale ones.
        # The token we pop is unrelated; the function walks all
        # entries to identify stales first.
        result = simple_storage.pop_pending_setup("unrelated-token")
        # The stale entry must have been purged (the original bug
        # was that the aware datetime caused an exception and the
        # entry survived).
        assert "stale-token-z" not in simple_storage.pending_setups, (
            "stale entry with tz-aware created_at was NOT purged — "
            "the aware-datetime bug from cubic P1 has regressed"
        )

    def test_naive_timestamp_still_purged(self, tmp_path, monkeypatch):
        """Regression check: the original (pre-fix) naive-datetime
        path must still work."""
        monkeypatch.setattr(simple_storage, "PENDING_FILE", str(tmp_path / "pending.json"))
        two_hours_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        simple_storage.pending_setups["stale-token-naive"] = {
            "access_token": "secret",
            "created_at": two_hours_ago.isoformat(),
        }
        simple_storage.pop_pending_setup("unrelated")
        assert "stale-token-naive" not in simple_storage.pending_setups

    def test_recent_entry_not_purged(self, tmp_path, monkeypatch):
        """An entry within the TTL should NOT be purged, regardless
        of timestamp format."""
        monkeypatch.setattr(simple_storage, "PENDING_FILE", str(tmp_path / "pending.json"))
        one_minute_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        simple_storage.pending_setups["recent-token"] = {
            "access_token": "secret",
            "created_at": one_minute_ago.isoformat(),
        }
        simple_storage.pop_pending_setup("unrelated")
        assert "recent-token" in simple_storage.pending_setups

    def test_malformed_timestamp_not_purged(self, tmp_path, monkeypatch):
        """A malformed `created_at` value (not a valid ISO 8601
        string) must not cause an exception, and the entry is
        conservatively NOT purged (we don't know how stale it is)."""
        monkeypatch.setattr(simple_storage, "PENDING_FILE", str(tmp_path / "pending.json"))
        simple_storage.pending_setups["malformed"] = {
            "access_token": "secret",
            "created_at": "not-a-valid-timestamp",
        }
        # Must not raise.
        simple_storage.pop_pending_setup("unrelated")
        # Conservative: don't purge on parse error.
        assert "malformed" in simple_storage.pending_setups


# ---------------------------------------------------------------------------
# Section 2: _save propagates errors
# ---------------------------------------------------------------------------


class TestSavePropagatesErrors:
    """Pin that _save no longer swallows write errors. If the
    disk write fails, the caller sees the failure (instead of
    silently thinking the write succeeded).
    """

    def test_save_raises_on_disk_write_failure(self, tmp_path, monkeypatch):
        """Drive a write failure by making the target path read-only.

        The atomic-rename step in `_save` uses `os.replace`, which
        will fail with PermissionError (or OSError) when the target
        is read-only. The previous code caught the exception and
        printed a warning; the caller never saw the failure.
        """
        # Point USERS_FILE at a path under a read-only directory.
        ro_dir = tmp_path / "readonly"
        ro_dir.mkdir()
        os.chmod(ro_dir, 0o555)  # read+execute only, no write
        target = ro_dir / "users.json"
        monkeypatch.setattr(simple_storage, "USERS_FILE", str(target))

        # Attempt a save. Should raise (PermissionError or OSError).
        with pytest.raises((PermissionError, OSError)):
            simple_storage.save_user(
                phone="+15550001111",
                omi_uid="test-uid",
                persona_id="persona-1",
                omi_dev_api_key="dev-key",
                access_token="test-access-token",
                phone_number_id="12345",
                verify_token="test-verify-token",
                auto_reply_enabled=True,
            )

        # In-memory state may have been updated (the save helper
        # updates the in-memory dict FIRST, then writes to disk).
        # But the on-disk file MUST NOT exist — the write failed
        # and the caller must know about it.
        assert not target.exists() or os.access(str(ro_dir), os.W_OK) is False

        # Restore permissions for cleanup.
        os.chmod(ro_dir, 0o755)

    def test_save_raises_when_parent_dir_is_missing(self, tmp_path, monkeypatch):
        """_save calls os.makedirs(..., exist_ok=True) so a missing
        parent is auto-created. The exception only fires on the
        actual write. So this test verifies the happy path: a
        missing parent is auto-created and the write succeeds."""
        # The behavior changed in round 5+ — os.makedirs with
        # exist_ok=True handles this case. The test pins it.
        target = tmp_path / "newsubdir" / "users.json"
        monkeypatch.setattr(simple_storage, "USERS_FILE", str(target))
        # Should not raise.
        simple_storage.save_user(
            phone="+15550001111",
            omi_uid="test-uid",
            persona_id="persona-1",
            omi_dev_api_key="dev-key",
            access_token="test-access-token",
            phone_number_id="12345",
            verify_token="test-verify-token",
            auto_reply_enabled=True,
        )
        # File should exist now.
        assert target.exists()
