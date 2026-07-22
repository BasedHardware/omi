"""Quiet-hours (do-not-disturb) window for proactive mentor notifications.

Users can set a local time window in which proactive "mentor" notifications are suppressed, so
Omi does not buzz them in the middle of the night. The feature is opt-in (disabled by default), so
existing users see no change until they enable it.

Covered here (all against the real modules, no sys.modules stubbing):
  * is_within_quiet_hours  -- pure window math: same-day, overnight wrap, and the start==end no-op.
  * get_quiet_hours / set_quiet_hours -- defaults for a missing doc, stored values, the merge write +
    cache invalidation, and out-of-range rejection (via injected fake Firestore client).
  * process_mentor_notification -- suppresses (returns None) inside the window, and does NOT consult
    the window when the feature is disabled or the current time is outside it.
  * GET/PATCH /v1/users/quiet-hours-settings -- happy path and the ValueError -> 400 mapping.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import database.notifications as notification_db
import utils.mentor_notifications as mentor
import routers.notifications as notifications_router

# ---------------------------------------------------------------------------
# Pure window math
# ---------------------------------------------------------------------------


class TestIsWithinQuietHours:
    def test_same_day_window_start_inclusive_end_exclusive(self):
        # Window 09:00 -> 17:00.
        assert notification_db.is_within_quiet_hours(9, 9, 17) is True  # start inclusive
        assert notification_db.is_within_quiet_hours(12, 9, 17) is True
        assert notification_db.is_within_quiet_hours(16, 9, 17) is True
        assert notification_db.is_within_quiet_hours(17, 9, 17) is False  # end exclusive
        assert notification_db.is_within_quiet_hours(8, 9, 17) is False
        assert notification_db.is_within_quiet_hours(23, 9, 17) is False

    def test_overnight_wrap_window(self):
        # Default window 22:00 -> 07:00 spans midnight.
        for hour in (22, 23, 0, 1, 3, 6):
            assert notification_db.is_within_quiet_hours(hour, 22, 7) is True
        for hour in (7, 8, 12, 17, 21):
            assert notification_db.is_within_quiet_hours(hour, 22, 7) is False

    def test_start_equals_end_is_never_quiet(self):
        for hour in range(24):
            assert notification_db.is_within_quiet_hours(hour, 9, 9) is False


# ---------------------------------------------------------------------------
# Database read/write (fake Firestore client injected via the firestore_client kwarg)
# ---------------------------------------------------------------------------


def _passthrough_cache():
    """A memory-cache stand-in whose get_or_fetch just runs the fetch closure."""
    cache = MagicMock()
    cache.get_or_fetch.side_effect = lambda key, fn, ttl=None: fn()
    return cache


class TestGetQuietHours:
    def test_defaults_for_missing_doc(self):
        client = MagicMock()
        client.collection.return_value.document.return_value.get.return_value.exists = False
        with patch.object(notification_db, "get_memory_cache", return_value=_passthrough_cache()):
            result = notification_db.get_quiet_hours("u1", firestore_client=client)
        assert result == {"enabled": False, "start_hour": 22, "end_hour": 7, "time_zone": None}

    def test_reads_stored_values(self):
        client = MagicMock()
        snap = client.collection.return_value.document.return_value.get.return_value
        snap.exists = True
        snap.to_dict.return_value = {
            "quiet_hours_enabled": True,
            "quiet_hours_start_local": 23,
            "quiet_hours_end_local": 6,
            "time_zone": "America/New_York",
        }
        with patch.object(notification_db, "get_memory_cache", return_value=_passthrough_cache()):
            result = notification_db.get_quiet_hours("u1", firestore_client=client)
        assert result == {
            "enabled": True,
            "start_hour": 23,
            "end_hour": 6,
            "time_zone": "America/New_York",
        }


class TestSetQuietHours:
    def test_writes_merge_and_invalidates_cache(self):
        client = MagicMock()
        cache = MagicMock()
        with patch.object(notification_db, "get_memory_cache", return_value=cache):
            ok = notification_db.set_quiet_hours("u1", True, 22, 7, firestore_client=client)
        assert ok is True
        set_call = client.collection.return_value.document.return_value.set
        set_call.assert_called_once()
        args, kwargs = set_call.call_args
        assert args[0] == {
            "quiet_hours_enabled": True,
            "quiet_hours_start_local": 22,
            "quiet_hours_end_local": 7,
        }
        assert kwargs.get("merge") is True
        cache.delete.assert_called_once_with("quiet_hours:u1")

    @pytest.mark.parametrize("start_hour,end_hour", [(24, 7), (22, -1), (-3, 7), (22, 24)])
    def test_rejects_out_of_range_hours(self, start_hour, end_hour):
        client = MagicMock()
        with pytest.raises(ValueError):
            notification_db.set_quiet_hours("u1", True, start_hour, end_hour, firestore_client=client)
        # Validation happens before any write.
        client.collection.return_value.document.return_value.set.assert_not_called()


# ---------------------------------------------------------------------------
# Enforcement inside process_mentor_notification
# ---------------------------------------------------------------------------


class TestMentorNotificationRespectsQuietHours:
    def test_suppressed_when_within_window(self):
        # Within the window the function must short-circuit to None BEFORE touching the buffer.
        with patch.object(mentor, "get_mentor_notification_frequency", return_value=3), patch.object(
            mentor,
            "get_quiet_hours",
            return_value={"enabled": True, "start_hour": 22, "end_hour": 7, "time_zone": None},
        ), patch.object(mentor, "is_within_quiet_hours", return_value=True), patch.object(
            mentor.message_buffer, "get_buffer"
        ) as get_buffer:
            result = mentor.process_mentor_notification("u_suppress", [{"text": "hello there"}])
        assert result is None
        get_buffer.assert_not_called()

    def test_disabled_never_consults_the_window(self):
        # Feature off -> is_within_quiet_hours must not be evaluated; normal buffering proceeds.
        with patch.object(mentor, "get_mentor_notification_frequency", return_value=3), patch.object(
            mentor,
            "get_quiet_hours",
            return_value={"enabled": False, "start_hour": 22, "end_hour": 7, "time_zone": None},
        ), patch.object(mentor, "is_within_quiet_hours") as within, patch.object(
            mentor.message_buffer,
            "get_buffer",
            return_value={"messages": [], "messages_at_last_analysis": 0, "silence_detected": False},
        ) as get_buffer:
            result = mentor.process_mentor_notification("u_disabled", [])
        within.assert_not_called()
        get_buffer.assert_called_once()
        assert result is None

    def test_outside_window_does_not_suppress(self):
        # Enabled but the current time is outside the window -> evaluated, but not gated.
        with patch.object(mentor, "get_mentor_notification_frequency", return_value=3), patch.object(
            mentor,
            "get_quiet_hours",
            return_value={"enabled": True, "start_hour": 22, "end_hour": 7, "time_zone": None},
        ), patch.object(mentor, "is_within_quiet_hours", return_value=False) as within, patch.object(
            mentor.message_buffer,
            "get_buffer",
            return_value={"messages": [], "messages_at_last_analysis": 0, "silence_detected": False},
        ) as get_buffer:
            result = mentor.process_mentor_notification("u_outside", [])
        within.assert_called_once()
        get_buffer.assert_called_once()
        assert result is None

    def test_bad_timezone_falls_back_to_utc_without_raising(self):
        # An unknown stored time zone string must not crash the notification path.
        with patch.object(mentor, "get_mentor_notification_frequency", return_value=3), patch.object(
            mentor,
            "get_quiet_hours",
            return_value={"enabled": True, "start_hour": 22, "end_hour": 7, "time_zone": "Not/AZone"},
        ), patch.object(mentor, "is_within_quiet_hours", return_value=True) as within, patch.object(
            mentor.message_buffer, "get_buffer"
        ):
            result = mentor.process_mentor_notification("u_badtz", [{"text": "hello there"}])
        assert result is None
        within.assert_called_once()

    def test_non_string_timezone_does_not_crash(self):
        # A corrupted non-string time_zone (pytz.timezone(int) raises AttributeError, not
        # UnknownTimeZoneError) must fall back to UTC and still evaluate the window, not crash.
        with patch.object(mentor, "get_mentor_notification_frequency", return_value=3), patch.object(
            mentor,
            "get_quiet_hours",
            return_value={"enabled": True, "start_hour": 22, "end_hour": 7, "time_zone": 12345},
        ), patch.object(mentor, "is_within_quiet_hours", return_value=False) as within, patch.object(
            mentor.message_buffer,
            "get_buffer",
            return_value={"messages": [], "messages_at_last_analysis": 0, "silence_detected": False},
        ):
            result = mentor.process_mentor_notification("u_nonstr_tz", [])
        within.assert_called_once()
        # The hour handed to the window check came from the UTC fallback: a valid 0-23 int.
        hour_arg = within.call_args.args[0]
        assert isinstance(hour_arg, int) and 0 <= hour_arg <= 23
        assert result is None


# ---------------------------------------------------------------------------
# Endpoints (called directly, bypassing the auth Depends)
# ---------------------------------------------------------------------------


class TestQuietHoursEndpoints:
    def test_get_returns_settings_without_time_zone(self):
        with patch.object(
            notifications_router.notification_db,
            "get_quiet_hours",
            return_value={"enabled": True, "start_hour": 22, "end_hour": 7, "time_zone": "America/New_York"},
        ):
            result = notifications_router.get_quiet_hours_settings(uid="u1")
        assert result.enabled is True
        assert result.start_hour == 22
        assert result.end_hour == 7
        # time_zone is internal (derived from the fcm-token) and intentionally not exposed here.
        assert not hasattr(result, "time_zone")

    def test_patch_persists_and_returns_ok(self):
        captured = {}

        def fake_set(uid, enabled, start_hour, end_hour):
            captured.update(uid=uid, enabled=enabled, start_hour=start_hour, end_hour=end_hour)
            return True

        with patch.object(notifications_router.notification_db, "set_quiet_hours", side_effect=fake_set):
            data = notifications_router.QuietHoursSettingsUpdate(enabled=True, start_hour=23, end_hour=6)
            result = notifications_router.update_quiet_hours_settings(data=data, uid="u1")
        assert result.status == "Ok"
        assert captured == {"uid": "u1", "enabled": True, "start_hour": 23, "end_hour": 6}

    def test_patch_maps_value_error_to_400(self):
        with patch.object(
            notifications_router.notification_db,
            "set_quiet_hours",
            side_effect=ValueError("Invalid start_hour: 99. Must be 0-23."),
        ):
            data = notifications_router.QuietHoursSettingsUpdate(enabled=True, start_hour=9, end_hour=17)
            with pytest.raises(HTTPException) as exc:
                notifications_router.update_quiet_hours_settings(data=data, uid="u1")
        assert exc.value.status_code == 400
