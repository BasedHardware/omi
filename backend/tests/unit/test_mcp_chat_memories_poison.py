<content>
import pytest
from unittest.mock import patch, MagicMock
from fastapi import status

from backend.routers.mcp import (
    _validate_simple_chat_messages,
    _validate_cleaner_memories,
    _validate_searched_memories,
    SimpleChatMessage,
    CleanerMemory,
    SearchedMemory,
    MemoryCategory,
)


@pytest.mark.unit
class TestChatMessageValidation:
    def test_get_chat_messages_skips_malformed_records(self):
        messages = [
            {"id": "1", "text": "Hello", "sender": "user"},
            {"id": "2", "text": "Hi there"},  # Missing sender
            {"id": "3", "sender": "user"},  # Missing text
            {"id": "4", "text": 123, "sender": "user"},  # Invalid text type
            {"id": "5", "text": "Valid", "sender": "user"},
        ]
        validated = _validate_simple_chat_messages(messages, "test_uid")
        assert len(validated) == 2
        assert validated[0].id == "1"
        assert validated[0].text == "Hello"
        assert validated[0].sender == "user"
        assert validated[1].id == "5"
        assert validated[1].text == "Valid"
        assert validated[1].sender == "user"

    def test_get_chat_messages_all_valid(self):
        messages = [
            {"id": "1", "text": "Hello", "sender": "user"},
            {"id": "2", "text": "Hi there", "sender": "assistant"},
        ]
        validated = _validate_simple_chat_messages(messages, "test_uid")
        assert len(validated) == 2
        assert all(isinstance(msg, SimpleChatMessage) for msg in validated)

    def test_chat_and_memories_use_validation_guards(self):
        # This test ensures that the validation functions are called in the endpoint
        with patch("backend.routers.mcp.get_chat_messages") as mock_get_chat:
            mock_get_chat.return_value = ([], None, False)
            with patch("backend.routers.mcp._validate_simple_chat_messages") as mock_validate:
                from backend.routers.mcp import get_chat_messages_endpoint
                from fastapi import Response
                from unittest.mock import MagicMock

                response = MagicMock(spec=Response)
                get_chat_messages_endpoint(response, current_user={"uid": "test_uid"})
                mock_validate.assert_called_once()


@pytest.mark.unit
class TestMemoryValidation:
    def test_get_memories_skips_malformed_records(self):
        memories = [
            {"id": "1", "content": "Memory 1", "category": "general"},
            {"id": "2", "content": "Memory 2"},  # Missing category
            {"id": "3", "category": "general"},  # Missing content
            {"id": "4", "content": 123, "category": "general"},  # Invalid content type
            {"id": "5", "content": "Valid", "category": "general"},
        ]
        validated = _validate_cleaner_memories(memories, "test_uid")
        assert len(validated) == 2
        assert validated[0].id == "1"
        assert validated[0].content == "Memory 1"
        assert validated[0].category == "general"
        assert validated[1].id == "5"
        assert validated[1].content == "Valid"
        assert validated[1].category == "general"

    def test_get_memories_all_valid(self):
        memories = [
            {"id": "1", "content": "Memory 1", "category": "general"},
            {"id": "2", "content": "Memory 2", "category": "action_item"},
        ]
        validated = _validate_cleaner_memories(memories, "test_uid")
        assert len(validated) == 2
        assert all(isinstance(memory, CleanerMemory) for memory in validated)

    def test_search_memories_skips_malformed_hits(self):
        memories = [
            {"id": "1", "content": "Memory 1", "category": "general", "relevance_score": 0.9},
            {"id": "2", "content": "Memory 2", "category": "general"},  # Missing relevance_score
            {"id": "3", "content": "Memory 3", "category": "general", "relevance_score": "high"},  # Invalid score type
            {"id": "4", "content": "Memory 4", "category": "general", "relevance_score": 0.8},
        ]
        validated = _validate_searched_memories(memories, "test_uid")
        assert len(validated) == 2
        assert validated[0].id == "1"
        assert validated[0].content == "Memory 1"
        assert validated[0].category == "general"
        assert validated[0].relevance_score == 0.9
        assert validated[1].id == "4"
        assert validated[1].content == "Memory 4"
        assert validated[1].category == "general"
        assert validated[1].relevance_score == 0.8

    def test_search_memories_all_valid(self):
        memories = [
            {"id": "1", "content": "Memory 1", "category": "general", "relevance_score": 0.9},
            {"id": "2", "content": "Memory 2", "category": "action_item", "relevance_score": 0.8},
        ]
        validated = _validate_searched_memories(memories, "test_uid")
        assert len(validated) == 2
        assert all(isinstance(memory, SearchedMemory) for memory in validated)


@pytest.mark.unit
class TestModelMapping:
    def test_simple_chat_message_mapping(self):
        msg = SimpleChatMessage(id="1", text="Hello", sender="user")
        assert msg["id"] == "1"
        assert msg["text"] == "Hello"
        assert msg["sender"] == "user"

    def test_cleaner_memory_mapping(self):
        memory = CleanerMemory(id="1", content="Memory", category=MemoryCategory.GENERAL)
        assert memory["id"] == "1"
        assert memory["content"] == "Memory"
        assert memory["category"] == MemoryCategory.GENERAL

    def test_searched_memory_mapping(self):
        memory = SearchedMemory(
            id="1", content="Memory", category=MemoryCategory.GENERAL, relevance_score=0.9
        )
        assert memory["id"] == "1"
        assert memory["content"] == "Memory"
        assert memory["category"] == MemoryCategory.GENERAL
        assert memory["relevance_score"] == 0.9


@pytest.mark.unit
class TestOpenAPIContract:
    def test_openapi_contract(self):
        # This test ensures that the endpoints return the expected structure
        from backend.routers.mcp import get_chat_messages_endpoint, get_memories_endpoint, search_memories_endpoint
        from fastapi import Response
        from unittest.mock import MagicMock

        # Mock the dependencies
        with patch("backend.routers.mcp.get_chat_messages") as mock_chat, \
             patch("backend.routers.mcp.get_memories") as mock_memories, \
             patch("backend.routers.mcp.search_memories") as mock_search, \
             patch("backend.routers.mcp.get_current_user") as mock_user:

            mock_user.return_value = {"uid": "test_uid"}
            mock_chat.return_value = ([], None, False)
            mock_memories.return_value = ([], None, False)
            mock_search.return_value = ([], None, False)

            response = MagicMock(spec=Response)

            # Test chat endpoint
            chat_result = get_chat_messages_endpoint(response, current_user={"uid": "test_uid"})
            assert isinstance(chat_result, list)
            assert response.headers.get("X-Next-Cursor") == ""
            assert response.headers.get("X-Scan-Truncated") == "false"

            # Test memories endpoint
            memories_result = get_memories_endpoint(response, current_user={"uid": "test_uid"})
            assert isinstance(memories_result, list)
            assert response.headers.get("X-Next-Cursor") == ""
            assert response.headers.get("X-Scan-Truncated") == "false"

            # Test search endpoint
            search_result = search_memories_endpoint(
                response, query="test", current_user={"uid": "test_uid"}
            )
            assert isinstance(search_result, list)
            assert response.headers.get("X-Next-Cursor") == ""
            assert response.headers.get("X-Scan-Truncated") == "false"
</content>