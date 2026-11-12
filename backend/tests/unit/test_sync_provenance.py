from datetime import datetime, timezone
from unittest.mock import patch
import pytest

from utils.sync.provenance import capture_matches_server_conversation


def _make_conversation(
    conversation_id="conv-123",
    uid="user-123",
    client_device_id="device-abc",
    started_at=None,
    finished_at=None,
    deleted=False,
):
    base_time = started_at or datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "id": conversation_id,
        "uid": uid,
        "client_device_id": client_device_id,
        "started_at": base_time,
        "finished_at": finished_at or base_time,
        "deleted": deleted,
    }


def test_capture_matches_server_conversation_active_matches():
    uid = "user-123"
    conversation_id = "conv-123"
    device_id = "device-abc"
    filenames = ["1712000000.wav"]
    conv = _make_conversation(conversation_id=conversation_id, uid=uid, client_device_id=device_id)

    with patch("database.conversations.get_conversation", return_value=conv), patch(
        "utils.sync.provenance.capture_times_within_window", return_value=True
    ):
        result = capture_matches_server_conversation(
            uid=uid,
            conversation_id=conversation_id,
            filenames=filenames,
            client_device_id=device_id,
        )
        assert result is True


def test_capture_matches_server_conversation_rejects_soft_deleted_tombstone():
    uid = "user-123"
    conversation_id = "conv-123"
    device_id = "device-abc"
    filenames = ["1712000000.wav"]
    tombstone = _make_conversation(
        conversation_id=conversation_id,
        uid=uid,
        client_device_id=device_id,
        deleted=True,
    )

    with patch("database.conversations.get_conversation", return_value=tombstone), patch(
        "utils.sync.provenance.capture_times_within_window", return_value=True
    ) as mock_window:
        result = capture_matches_server_conversation(
            uid=uid,
            conversation_id=conversation_id,
            filenames=filenames,
            client_device_id=device_id,
        )
        assert result is False
        mock_window.assert_not_called()


def test_capture_matches_server_conversation_missing_conversation():
    with patch("database.conversations.get_conversation", return_value=None):
        result = capture_matches_server_conversation(
            uid="user-123",
            conversation_id="nonexistent-conv",
            filenames=["1712000000.wav"],
            client_device_id="device-abc",
        )
        assert result is False


def test_capture_matches_server_conversation_mismatched_device():
    conv = _make_conversation(client_device_id="device-owner")
    with patch("database.conversations.get_conversation", return_value=conv):
        result = capture_matches_server_conversation(
            uid="user-123",
            conversation_id="conv-123",
            filenames=["1712000000.wav"],
            client_device_id="device-attacker",
        )
        assert result is False


def test_capture_matches_server_conversation_missing_ids():
    assert capture_matches_server_conversation("user-123", None, ["1712000000.wav"], "device-abc") is False
    assert capture_matches_server_conversation("user-123", "", ["1712000000.wav"], "device-abc") is False
    assert capture_matches_server_conversation("user-123", "conv-123", ["1712000000.wav"], None) is False
    assert capture_matches_server_conversation("user-123", "conv-123", ["1712000000.wav"], "") is False


def test_capture_matches_server_conversation_invalid_timestamps():
    conv = _make_conversation()
    conv["started_at"] = "invalid-date-string"
    with patch("database.conversations.get_conversation", return_value=conv):
        result = capture_matches_server_conversation(
            uid="user-123",
            conversation_id="conv-123",
            filenames=["1712000000.wav"],
            client_device_id="device-abc",
        )
        assert result is False


def test_capture_matches_server_conversation_outside_window():
    conv = _make_conversation()
    with patch("database.conversations.get_conversation", return_value=conv), patch(
        "utils.sync.provenance.capture_times_within_window", return_value=False
    ):
        result = capture_matches_server_conversation(
            uid="user-123",
            conversation_id="conv-123",
            filenames=["1712000000.wav"],
            client_device_id="device-abc",
        )
        assert result is False
