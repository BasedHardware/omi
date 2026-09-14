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


def test_current_datetime_block_mentions_relative_time_words():
    from utils.llm import chat as llm_chat

    block = llm_chat.get_current_datetime_block("uid1", tz="America/Los_Angeles")
    assert "tonight" in block
    assert "America/Los_Angeles" in block
