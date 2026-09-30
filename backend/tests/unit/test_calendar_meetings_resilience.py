import pytest
from unittest.mock import MagicMock, patch

from database.calendar_meetings import (
    create_meeting,
    update_meeting,
    get_meeting,
    delete_meeting,
)


def test_clean_id_in_calendar_meetings():
    with pytest.raises(ValueError, match="uid cannot be empty"):
        create_meeting("", {"calendar_source": "google", "calendar_event_id": "evt123"})

    with pytest.raises(ValueError, match="uid contains prohibited path-traversal"):
        get_meeting("../bad_uid", "meeting123")

    with pytest.raises(ValueError, match="meeting_id cannot be empty"):
        delete_meeting("valid_uid", "")


def test_create_meeting_input_validation():
    with pytest.raises(ValueError, match="calendar_source must be a non-empty string"):
        create_meeting("user_123", {"calendar_source": "", "calendar_event_id": "evt123"})

    with pytest.raises(ValueError, match="calendar_event_id must be a non-empty string"):
        create_meeting("user_123", {"calendar_source": "google", "calendar_event_id": ""})


def test_update_meeting_preserves_exceptions():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.update.side_effect = RuntimeError("Firestore unavailable")
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc

    with patch("database.calendar_meetings._client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="Firestore unavailable"):
            update_meeting("user_123", "meeting_123", {"title": "Team Sync"})
