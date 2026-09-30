import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from backend.utils.people_stats import aggregate_people_stats
from backend.models.conversation import Conversation


@pytest.fixture
def mock_conversations_db():
    """Mock ConversationsDB with controlled responses."""
    db = MagicMock()
    return db


def test_aggregate_people_stats_with_tombstone(mock_conversations_db):
    """
    Test that aggregate_people_stats correctly handles tombstone rows (discarded=False, deleted=True)
    and does not terminate pagination early.
    """
    # Create mock conversations: [visible, tombstone, visible, visible]
    now = datetime.utcnow()
    conversations = [
        Conversation(
            id=1,
            speaker_id=101,
            created_at=now - timedelta(days=4),
            duration=100,
            discarded=False,
            deleted=False
        ),
        Conversation(
            id=2,
            speaker_id=102,
            created_at=now - timedelta(days=3),
            duration=0,
            discarded=False,
            deleted=True  # Tombstone: deleted=True, discarded=False
        ),
        Conversation(
            id=3,
            speaker_id=101,
            created_at=now - timedelta(days=2),
            duration=200,
            discarded=False,
            deleted=False
        ),
        Conversation(
            id=4,
            speaker_id=103,
            created_at=now - timedelta(days=1),
            duration=300,
            discarded=False,
            deleted=False
        )
    ]

    # Mock get_conversations_without_photos to return all rows (including tombstone) in one page
    mock_conversations_db.get_conversations_without_photos.return_value = conversations

    # Call aggregate_people_stats
    result = aggregate_people_stats(
        conversations_db=mock_conversations_db,
        uid=1,
        scan_cap=10,
        batch=10
    )

    # Assert tombstone (speaker_id=102) is excluded from stats
    assert 102 not in result["people"]

    # Assert stats for speaker_id=101 include both conversations (id=1 and id=3)
    assert result["people"][101]["conversation_count"] == 2
    assert result["people"][101]["talk_seconds"] == 300  # 100 + 200
    assert result["people"][101]["last_heard_at"] == now - timedelta(days=2)  # Most recent

    # Assert stats for speaker_id=103 include one conversation (id=4)
    assert result["people"][103]["conversation_count"] == 1
    assert result["people"][103]["talk_seconds"] == 300

    # Assert total conversations exclude tombstone
    assert result["total_conversations"] == 3


def test_aggregate_people_stats_empty_page_handling(mock_conversations_db):
    """
    Test that empty pages (true exhaustion) still terminate correctly.
    """
    mock_conversations_db.get_conversations_without_photos.return_value = []

    result = aggregate_people_stats(
        conversations_db=mock_conversations_db,
        uid=1,
        scan_cap=10,
        batch=10
    )

    assert result["people"] == {}
    assert result["total_conversations"] == 0
