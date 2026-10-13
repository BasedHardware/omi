"""Tests ensuring timezone validators accept only schedulable pytz timezones.

Regression coverage for #21220:
- SyncUserTimeZoneRequest and SaveFcmTokenRequest reject unschedulable timezones.
- resolve_user_timezone falls back to UTC for unschedulable or invalid timezones.
- sync_user_time_zone_from_client ignores unschedulable zones and falls back to resolve_user_timezone.
- save_token forwards only schedulable timezones to _update_summary_schedule.
"""

from unittest.mock import MagicMock, patch
import pytest

from models.other import (
    SaveFcmTokenRequest,
    SyncUserTimeZoneRequest,
    is_schedulable_time_zone,
)
import database.notifications as notification_db


def test_is_schedulable_time_zone():
    assert is_schedulable_time_zone("America/New_York") is True
    assert is_schedulable_time_zone("UTC") is True
    assert is_schedulable_time_zone("Europe/London") is True
    assert is_schedulable_time_zone("Asia/Tokyo") is True

    assert is_schedulable_time_zone("") is False
    assert is_schedulable_time_zone("   ") is False
    assert is_schedulable_time_zone(None) is False
    assert is_schedulable_time_zone("Not/A/Timezone") is False
    assert is_schedulable_time_zone("InvalidZone") is False


def test_sync_user_time_zone_request_validation():
    req = SyncUserTimeZoneRequest(time_zone="America/Los_Angeles")
    assert req.time_zone == "America/Los_Angeles"

    with pytest.raises(ValueError, match="valid IANA timezone"):
        SyncUserTimeZoneRequest(time_zone="Not/A/Timezone")

    with pytest.raises(ValueError, match="non-empty IANA timezone"):
        SyncUserTimeZoneRequest(time_zone="   ")


def test_save_fcm_token_request_validation():
    req = SaveFcmTokenRequest(fcm_token="token123", time_zone="America/New_York")
    assert req.time_zone == "America/New_York"

    with pytest.raises(ValueError, match="valid IANA timezone"):
        SaveFcmTokenRequest(fcm_token="token123", time_zone="Not/A/Timezone")

    with pytest.raises(ValueError, match="non-empty IANA timezone"):
        SaveFcmTokenRequest(fcm_token="token123", time_zone="   ")


@patch.object(notification_db, "get_user_time_zone", return_value="America/Chicago")
def test_resolve_user_timezone_valid(get_tz):
    assert notification_db.resolve_user_timezone("u1") == "America/Chicago"


@patch.object(notification_db, "get_user_time_zone", return_value="Invalid/Zone")
def test_resolve_user_timezone_falls_back_to_utc_for_unschedulable(get_tz):
    assert notification_db.resolve_user_timezone("u1") == "UTC"


@patch.object(notification_db, "get_user_time_zone", return_value=None)
def test_resolve_user_timezone_none_returns_utc(get_tz):
    assert notification_db.resolve_user_timezone("u1") == "UTC"


@patch.object(notification_db, "set_user_time_zone")
@patch.object(notification_db, "get_user_time_zone", return_value="UTC")
def test_sync_user_time_zone_from_client_ignores_unschedulable_zone(get_tz, set_tz):
    tz = notification_db.sync_user_time_zone_from_client("u1", "Invalid/Timezone")
    assert tz == "UTC"
    set_tz.assert_not_called()


@patch.object(notification_db, "set_user_time_zone")
@patch.object(notification_db, "get_user_time_zone", return_value=None)
def test_sync_user_time_zone_from_client_persists_schedulable_zone(get_tz, set_tz):
    tz = notification_db.sync_user_time_zone_from_client("u1", "Europe/Paris")
    assert tz == "Europe/Paris"
    set_tz.assert_called_once_with("u1", "Europe/Paris")


@patch.object(notification_db, "_update_summary_schedule")
def test_save_token_forwards_only_schedulable_timezone(mock_update_schedule):
    fake_client = MagicMock()
    user_ref = MagicMock()
    user_ref.get.return_value.exists = False
    fake_client.collection.return_value.document.return_value = user_ref

    # Schedulable timezone forwards to _update_summary_schedule
    notification_db.save_token(
        "u1",
        {"fcm_token": "tok1", "time_zone": "America/New_York", "device_key": "dev1"},
        firestore_client=fake_client,
    )
    mock_update_schedule.assert_called_with("u1", {"time_zone": "America/New_York"}, firestore_client=fake_client)

    # Unschedulable timezone does NOT forward to _update_summary_schedule
    mock_update_schedule.reset_mock()
    notification_db.save_token(
        "u1",
        {"fcm_token": "tok2", "time_zone": "Invalid/Zone", "device_key": "dev2"},
        firestore_client=fake_client,
    )
    mock_update_schedule.assert_called_with("u1", {}, firestore_client=fake_client)
