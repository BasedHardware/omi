import sys
import unittest
from unittest.mock import MagicMock
from pydantic import BaseModel, ValidationError

if "models.memories" not in sys.modules:
    mock_memories = MagicMock()
    mock_memories.MemoryDB = BaseModel
    sys.modules["models.memories"] = mock_memories

from models.integrations import (
    ActionItem,
    ConversationItemGeolocation,
    ConversationTimestampRange,
    Event,
    ExternalIntegrationMemory,
    SearchConversationsResponse,
)


class TestIntegrationsModelValidation(unittest.TestCase):
    def test_timestamp_range_valid(self):
        tr = ConversationTimestampRange(start=100, end=200)
        self.assertEqual(tr.start, 100)
        self.assertEqual(tr.end, 200)

    def test_timestamp_range_equal_bounds(self):
        tr = ConversationTimestampRange(start=100, end=100)
        self.assertEqual(tr.start, 100)
        self.assertEqual(tr.end, 100)

    def test_timestamp_range_negative_start_rejected(self):
        with self.assertRaises(ValidationError):
            ConversationTimestampRange(start=-1, end=100)

    def test_timestamp_range_negative_end_rejected(self):
        with self.assertRaises(ValidationError):
            ConversationTimestampRange(start=0, end=-5)

    def test_timestamp_range_start_exceeds_end_rejected(self):
        with self.assertRaises(ValidationError):
            ConversationTimestampRange(start=200, end=100)

    def test_external_integration_memory_valid(self):
        mem = ExternalIntegrationMemory(content="  User prefers dark mode  ")
        self.assertEqual(mem.content, "User prefers dark mode")

    def test_external_integration_memory_blank_rejected(self):
        with self.assertRaises(ValidationError):
            ExternalIntegrationMemory(content="   ")

    def test_external_integration_memory_non_string_rejected(self):
        with self.assertRaises(ValidationError):
            ExternalIntegrationMemory(content=123)

    def test_response_models_permissive_for_legacy_stored_data(self):
        # Stored historical LLM data should not be dropped on read
        item = ActionItem(description="legacy item")
        self.assertEqual(item.description, "legacy item")

        geo = ConversationItemGeolocation(latitude=37.7749, longitude=-122.4194)
        self.assertEqual(geo.latitude, 37.7749)

    def test_search_conversations_response_valid(self):
        resp = SearchConversationsResponse(
            conversations=[],
            total_pages=5,
            current_page=1,
            per_page=20,
        )
        self.assertEqual(resp.total_pages, 5)
        self.assertEqual(resp.per_page, 20)

    def test_search_conversations_response_invalid_bounds(self):
        with self.assertRaises(ValidationError):
            SearchConversationsResponse(
                conversations=[],
                total_pages=-1,
                current_page=1,
                per_page=20,
            )

        with self.assertRaises(ValidationError):
            SearchConversationsResponse(
                conversations=[],
                total_pages=5,
                current_page=-1,
                per_page=20,
            )

        with self.assertRaises(ValidationError):
            SearchConversationsResponse(
                conversations=[],
                total_pages=5,
                current_page=1,
                per_page=0,
            )


if __name__ == "__main__":
    unittest.main()
