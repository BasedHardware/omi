"""
Tests for MCP and developer router lite/full conversation routing.
Uses extracted logic to avoid Firestore init during module import.
"""

from unittest.mock import MagicMock


# Extracted logic from routers/mcp.py get_conversations
def _mcp_get_conversations(mock_conv_db, uid, limit=25, offset=0, categories=None):
    """Simulates MCP list conversations — always uses lite."""
    category_list = []
    conversations = mock_conv_db.get_conversations_lite(
        uid,
        limit,
        offset,
        include_discarded=False,
        statuses=["completed"],
        start_date=None,
        end_date=None,
        categories=[c for c in category_list],
    )
    return conversations


# Extracted logic from routers/developer.py get_user_conversations
def _developer_get_conversations(mock_conv_db, uid, limit=25, offset=0, include_transcript=False):
    """Simulates developer list conversations — conditional lite/full."""
    if include_transcript:
        conversations = mock_conv_db.get_conversations(
            uid,
            limit,
            offset,
            include_discarded=False,
            statuses=["completed"],
            start_date=None,
            end_date=None,
            categories=[],
        )
    else:
        conversations = mock_conv_db.get_conversations_lite(
            uid,
            limit,
            offset,
            include_discarded=False,
            statuses=["completed"],
            start_date=None,
            end_date=None,
            categories=[],
        )

    unlocked = [conv for conv in conversations if not conv.get('is_locked', False)]

    if include_transcript:
        # Would call _add_speaker_names_to_segments(uid, unlocked)
        return unlocked, True  # True = speaker enrichment called
    return unlocked, False


class TestMcpConversationsLite:
    def test_mcp_list_uses_lite(self):
        """MCP list endpoint always uses get_conversations_lite."""
        mock_conv_db = MagicMock()
        mock_conv_db.get_conversations_lite.return_value = []

        _mcp_get_conversations(mock_conv_db, 'test_uid')

        mock_conv_db.get_conversations_lite.assert_called_once()
        mock_conv_db.get_conversations.assert_not_called()


class TestDeveloperConversationsLite:
    def test_include_transcript_false_uses_lite(self):
        """Developer endpoint with include_transcript=False uses lite."""
        mock_conv_db = MagicMock()
        mock_conv_db.get_conversations_lite.return_value = []

        _, speaker_enriched = _developer_get_conversations(mock_conv_db, 'test_uid', include_transcript=False)

        mock_conv_db.get_conversations_lite.assert_called_once()
        mock_conv_db.get_conversations.assert_not_called()
        assert speaker_enriched is False

    def test_include_transcript_true_uses_full(self):
        """Developer endpoint with include_transcript=True uses full get_conversations."""
        mock_conv_db = MagicMock()
        mock_conv_db.get_conversations.return_value = [{'id': 'c1', 'is_locked': False, 'transcript_segments': []}]

        _, speaker_enriched = _developer_get_conversations(mock_conv_db, 'test_uid', include_transcript=True)

        mock_conv_db.get_conversations.assert_called_once()
        mock_conv_db.get_conversations_lite.assert_not_called()
        assert speaker_enriched is True

    def test_include_transcript_false_no_speaker_enrichment(self):
        """Developer endpoint with include_transcript=False skips speaker enrichment."""
        mock_conv_db = MagicMock()
        mock_conv_db.get_conversations_lite.return_value = [{'id': 'c1', 'is_locked': False}]

        _, speaker_enriched = _developer_get_conversations(mock_conv_db, 'test_uid', include_transcript=False)

        assert speaker_enriched is False
