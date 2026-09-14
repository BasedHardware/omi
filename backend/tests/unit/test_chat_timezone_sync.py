"""Chat timezone sync from client requests (issue #4643)."""

from unittest.mock import MagicMock, patch

import pytest

from models.chat import SendMessageRequest
import database.notifications as notification_db


def test_send_message_request_accepts_valid_iana_timezone():
    req = SendMessageRequest(text="hi", time_zone="America/New_York")
    assert req.time_zone == "America/New_York"


def test_send_message_request_rejects_invalid_timezone():
    with pytest.raises(ValueError, match="IANA"):
        SendMessageRequest(text="hi", time_zone="Not/A/Timezone")


@patch.object(notification_db, "set_user_time_zone")
@patch.object(notification_db, "get_user_time_zone", return_value=None)
def test_sync_user_time_zone_from_client_persists_valid_zone(get_tz, set_tz):
    tz = notification_db.sync_user_time_zone_from_client("uid1", "Europe/Berlin")
    assert tz == "Europe/Berlin"
    set_tz.assert_called_once_with("uid1", "Europe/Berlin")


@patch.object(notification_db, "set_user_time_zone")
@patch.object(notification_db, "get_user_time_zone", return_value="Europe/Berlin")
def test_sync_user_time_zone_from_client_skips_write_when_unchanged(get_tz, set_tz):
    tz = notification_db.sync_user_time_zone_from_client("uid1", "Europe/Berlin")
    assert tz == "Europe/Berlin"
    set_tz.assert_not_called()


@patch.object(notification_db, "set_user_time_zone")
@patch.object(notification_db, "get_user_time_zone", return_value="UTC")
def test_sync_user_time_zone_from_client_ignores_invalid_request(get_tz, set_tz):
    tz = notification_db.sync_user_time_zone_from_client("uid1", "bogus")
    assert tz == "UTC"
    set_tz.assert_not_called()


@patch.object(notification_db, "set_user_time_zone", side_effect=RuntimeError("firestore down"))
@patch.object(notification_db, "get_user_time_zone", return_value="UTC")
def test_sync_user_time_zone_from_client_returns_request_tz_when_persist_fails(get_tz, set_tz):
    tz = notification_db.sync_user_time_zone_from_client("uid1", "Europe/Berlin")
    assert tz == "Europe/Berlin"
    set_tz.assert_called_once_with("uid1", "Europe/Berlin")


@patch.object(notification_db, "get_firestore_client")
def test_set_user_time_zone_uses_injectable_firestore_client(get_client):
    fake_client = MagicMock()
    get_client.return_value = fake_client
    notification_db.set_user_time_zone("uid1", "America/Chicago", firestore_client=fake_client)
    fake_client.collection.assert_called_once_with("users")
    get_client.assert_not_called()


@patch.object(notification_db, "get_firestore_client")
def test_set_user_time_zone_defaults_to_get_firestore_client(get_client):
    fake_client = MagicMock()
    get_client.return_value = fake_client
    notification_db.set_user_time_zone("uid1", "America/Chicago")
    get_client.assert_called_once()
    fake_client.collection.assert_called_once_with("users")
