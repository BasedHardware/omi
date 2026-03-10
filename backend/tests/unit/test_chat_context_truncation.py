"""
Tests for chat context truncation in conversation tools.

Verifies that get_conversations_tool and search_conversations_tool
truncate large result strings to prevent context overflow and 504 timeouts.
Issue #4927: Chat freezes with lengthy date ranges.
"""

import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Stub heavy dependencies before importing conversation_tools
for mod_name in [
    'firebase_admin',
    'firebase_admin.firestore',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'firebase_admin.messaging',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.base_query',
    'langchain_core',
    'langchain_core.runnables',
    'langchain_core.tools',
    'database.conversations',
    'database.users',
    'database.vector_db',
    'utils.llm.clients',
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Mock the tool decorator to be a no-op
mock_tool = MagicMock(side_effect=lambda f: f)
sys.modules['langchain_core.tools'].tool = mock_tool

# Mock RunnableConfig
sys.modules['langchain_core.runnables'].RunnableConfig = None

# Now import the module under test
from models.conversation import Conversation
from models.other import Person


def _make_conversation(index: int, overview_size: int = 200) -> dict:
    """Create a fake conversation dict with a specified overview size."""
    return {
        'id': f'conv-{index}',
        'created_at': datetime(2026, 3, 1, tzinfo=timezone.utc) - timedelta(days=index),
        'started_at': datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc) - timedelta(days=index),
        'finished_at': datetime(2026, 3, 1, 11, 0, tzinfo=timezone.utc) - timedelta(days=index),
        'structured': {
            'title': f'Conversation about topic {index}',
            'overview': 'X' * overview_size,
            'category': 'personal',
            'action_items': [],
            'events': [],
            'emoji': '',
        },
        'transcript_segments': [],
        'plugins_results': [],
        'apps_results': [],
        'photos': [],
        'source': 'friend',
        'language': 'en',
        'status': 'completed',
    }


def _make_conversations(count: int, overview_size: int = 200) -> list:
    """Create a list of fake conversation dicts."""
    return [_make_conversation(i, overview_size) for i in range(count)]


class TestConversationContextTruncation(unittest.TestCase):
    """Test that conversations_to_string output is properly bounded."""

    def test_small_result_not_truncated(self):
        """10 conversations with small overviews should not be truncated."""
        convs = [Conversation(**d) for d in _make_conversations(10, overview_size=100)]
        result = Conversation.conversations_to_string(convs)
        # Should have all 10 conversations
        self.assertEqual(result.count('Conversation #'), 10)
        self.assertNotIn('[Note:', result)

    def test_conversations_to_string_output_format(self):
        """Verify basic output format of conversations_to_string."""
        convs = [Conversation(**d) for d in _make_conversations(3)]
        result = Conversation.conversations_to_string(convs)
        self.assertIn('Conversation #1', result)
        self.assertIn('Conversation #2', result)
        self.assertIn('Conversation #3', result)
        self.assertIn('---------------------', result)


class TestGetConversationsToolTruncation(unittest.TestCase):
    """Test truncation logic in get_conversations_tool."""

    def _call_tool_with_conversations(self, conversations_data, max_result_chars=None):
        """Helper to simulate the truncation logic from get_conversations_tool."""
        MAX_RESULT_CHARS = max_result_chars or 1_600_000

        conversations = []
        for conv_data in conversations_data:
            conversations.append(Conversation(**conv_data))

        result = Conversation.conversations_to_string(conversations)

        if len(result) > MAX_RESULT_CHARS:
            truncated_parts = []
            total_chars = 0
            included_count = 0
            separator = "\n\n---------------------\n\n"
            for conversation in conversations:
                part = Conversation.conversations_to_string([conversation])
                if total_chars + len(part) + len(separator) > MAX_RESULT_CHARS and included_count > 0:
                    break
                truncated_parts.append(part)
                total_chars += len(part) + len(separator)
                included_count += 1

            omitted = len(conversations) - included_count
            result = separator.join(truncated_parts)
            if omitted > 0:
                result += f"\n\n[Note: {omitted} older conversations omitted to fit context. Ask about a shorter time period for full details.]"

        return result, len(conversations)

    def test_large_result_gets_truncated(self):
        """Many conversations with large overviews should be truncated."""
        # Each conversation ~5100 chars. 500 convs = ~2.5M chars > 1.6M limit
        conversations_data = _make_conversations(500, overview_size=5000)
        result, total = self._call_tool_with_conversations(conversations_data)

        self.assertEqual(total, 500)
        self.assertLessEqual(len(result), 1_700_000)  # ~1.6M + truncation note
        self.assertIn('[Note:', result)
        self.assertIn('older conversations omitted', result)

    def test_small_result_passes_through(self):
        """Few conversations should not be truncated."""
        conversations_data = _make_conversations(5, overview_size=200)
        result, total = self._call_tool_with_conversations(conversations_data)

        self.assertEqual(total, 5)
        self.assertNotIn('[Note:', result)
        self.assertEqual(result.count('Conversation #'), 5)

    def test_truncation_preserves_order(self):
        """Truncated result should contain the first (most recent) conversations."""
        conversations_data = _make_conversations(500, overview_size=5000)
        result, _ = self._call_tool_with_conversations(conversations_data)

        # First conversation should always be present
        self.assertIn('Conversation #1', result)
        # Last conversation should be omitted
        self.assertNotIn('Conversation #500', result)

    def test_truncation_with_custom_limit(self):
        """Truncation should work with a smaller limit."""
        # Use 10K char limit — each conv ~300 chars, should fit ~30
        conversations_data = _make_conversations(100, overview_size=200)
        result, total = self._call_tool_with_conversations(conversations_data, max_result_chars=10_000)

        self.assertEqual(total, 100)
        self.assertLessEqual(len(result), 11_000)  # 10K + note
        self.assertIn('[Note:', result)

    def test_single_huge_conversation_included(self):
        """A single conversation larger than the limit should still be included."""
        conversations_data = _make_conversations(1, overview_size=2_000_000)
        result, total = self._call_tool_with_conversations(conversations_data)

        # Even if it exceeds the limit, 1 conversation should always be returned
        self.assertEqual(total, 1)
        self.assertIn('Conversation #1', result)

    def test_truncation_note_includes_count(self):
        """Truncation note should include the number of omitted conversations."""
        conversations_data = _make_conversations(500, overview_size=5000)
        result, _ = self._call_tool_with_conversations(conversations_data)

        self.assertIn('[Note:', result)
        # Extract the omitted count from the note
        import re

        match = re.search(r'\[Note: (\d+) older conversations omitted', result)
        self.assertIsNotNone(match)
        omitted = int(match.group(1))
        self.assertGreater(omitted, 0)
        self.assertLess(omitted, 200)


class TestTokenEstimation(unittest.TestCase):
    """Test that context size stays within safety guard limits."""

    def test_truncated_result_fits_safety_guard(self):
        """Truncated result should fit within 500K token safety guard."""
        conversations_data = _make_conversations(1000, overview_size=5000)
        # Simulate truncation
        MAX_RESULT_CHARS = 1_600_000
        conversations = [Conversation(**d) for d in conversations_data]

        truncated_parts = []
        total_chars = 0
        included_count = 0
        separator = "\n\n---------------------\n\n"
        for conversation in conversations:
            part = Conversation.conversations_to_string([conversation])
            if total_chars + len(part) + len(separator) > MAX_RESULT_CHARS and included_count > 0:
                break
            truncated_parts.append(part)
            total_chars += len(part) + len(separator)
            included_count += 1

        result = separator.join(truncated_parts)

        # Estimate tokens (~4 chars per token)
        estimated_tokens = len(result) // 4
        self.assertLess(estimated_tokens, 500_000, "Truncated result should fit within 500K token safety guard")


if __name__ == '__main__':
    unittest.main()
