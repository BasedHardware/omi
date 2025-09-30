"""
Unit tests for MCP Server implementation

Tests all 14 MCP tools:
- search_conversations
- get_conversation
- search_memories
- create_memory
- update_memory
- delete_memory
- create_action_item
- list_action_items
- update_action_item
- get_user_context
- get_conversation_summary
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

# Import MCP server functions
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mcp_server_omi import (
    search_conversations_impl,
    get_conversation_impl,
    search_memories_impl,
    create_memory_impl,
    update_memory_impl,
    delete_memory_impl,
    create_action_item_impl,
    list_action_items_impl,
    update_action_item_impl,
    get_user_context_impl,
    get_conversation_summary_impl,
)


class TestConversationTools:
    """Test conversation-related MCP tools"""

    @pytest.mark.asyncio
    async def test_search_conversations_basic(self):
        """Test basic conversation search"""
        uid = "test_user"
        args = {
            "query": "machine learning",
            "limit": 10
        }

        with patch('mcp_server_omi.generate_embedding') as mock_embed, \
             patch('mcp_server_omi.query_vectors_by_metadata') as mock_query, \
             patch('mcp_server_omi.conversations_db.get_conversations_by_id') as mock_get:

            # Mock embedding
            mock_embed.return_value = [0.1] * 3072

            # Mock vector search results
            mock_query.return_value = ['conv1', 'conv2']

            # Mock conversation data
            mock_get.return_value = [
                {
                    'id': 'conv1',
                    'structured': {
                        'title': 'ML Discussion',
                        'overview': 'Talked about machine learning',
                        'category': 'technology'
                    },
                    'started_at': datetime.now(timezone.utc),
                    'finished_at': datetime.now(timezone.utc),
                    'language': 'en',
                    'is_locked': False
                }
            ]

            result = await search_conversations_impl(uid, args)

            assert result['success'] is True
            assert result['count'] == 1
            assert len(result['conversations']) == 1
            assert result['conversations'][0]['title'] == 'ML Discussion'

    @pytest.mark.asyncio
    async def test_search_conversations_with_date_filter(self):
        """Test conversation search with date filters"""
        uid = "test_user"
        args = {
            "query": "meeting",
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-01-31T23:59:59Z",
            "limit": 5
        }

        with patch('mcp_server_omi.generate_embedding'), \
             patch('mcp_server_omi.query_vectors_by_metadata') as mock_query, \
             patch('mcp_server_omi.conversations_db.get_conversations_by_id'):

            mock_query.return_value = []

            result = await search_conversations_impl(uid, args)

            # Should call query_vectors with date filters
            assert mock_query.called
            call_args = mock_query.call_args
            assert call_args[1]['dates_filter'][0] is not None  # start_date parsed
            assert call_args[1]['dates_filter'][1] is not None  # end_date parsed

    @pytest.mark.asyncio
    async def test_get_conversation_success(self):
        """Test getting a specific conversation"""
        uid = "test_user"
        args = {"conversation_id": "conv123"}

        with patch('mcp_server_omi.conversations_db.get_conversation') as mock_get:
            mock_get.return_value = {
                'id': 'conv123',
                'structured': {'title': 'Test Conversation'},
                'transcript_segments': [],
                'is_locked': False
            }

            result = await get_conversation_impl(uid, args)

            assert result['success'] is True
            assert 'conversation' in result
            assert result['conversation']['id'] == 'conv123'

    @pytest.mark.asyncio
    async def test_get_conversation_locked(self):
        """Test getting a locked conversation (premium required)"""
        uid = "test_user"
        args = {"conversation_id": "conv_locked"}

        with patch('mcp_server_omi.conversations_db.get_conversation') as mock_get:
            mock_get.return_value = {'id': 'conv_locked', 'is_locked': True}

            result = await get_conversation_impl(uid, args)

            assert result['success'] is False
            assert 'locked' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self):
        """Test getting non-existent conversation"""
        uid = "test_user"
        args = {"conversation_id": "nonexistent"}

        with patch('mcp_server_omi.conversations_db.get_conversation') as mock_get:
            mock_get.return_value = None

            result = await get_conversation_impl(uid, args)

            assert result['success'] is False
            assert 'not found' in result['error'].lower()


class TestMemoryTools:
    """Test memory-related MCP tools"""

    @pytest.mark.asyncio
    async def test_search_memories_all(self):
        """Test searching all memories"""
        uid = "test_user"
        args = {"limit": 25}

        with patch('mcp_server_omi.memories_db.get_memories') as mock_get:
            mock_get.return_value = [
                {'id': 'mem1', 'content': 'User loves hiking', 'is_locked': False},
                {'id': 'mem2', 'content': 'Birthday is June 15', 'is_locked': False}
            ]

            result = await search_memories_impl(uid, args)

            assert result['success'] is True
            assert result['count'] == 2
            assert len(result['memories']) == 2

    @pytest.mark.asyncio
    async def test_search_memories_with_query(self):
        """Test searching memories with text query"""
        uid = "test_user"
        args = {"query": "hiking", "limit": 10}

        with patch('mcp_server_omi.memories_db.get_memories') as mock_get:
            mock_get.return_value = [
                {'id': 'mem1', 'content': 'User loves hiking', 'is_locked': False},
                {'id': 'mem2', 'content': 'Birthday is June 15', 'is_locked': False}
            ]

            result = await search_memories_impl(uid, args)

            # Should filter to only hiking-related memory
            assert result['success'] is True
            assert result['count'] == 1
            assert 'hiking' in result['memories'][0]['content']

    @pytest.mark.asyncio
    async def test_create_memory_success(self):
        """Test creating a new memory"""
        uid = "test_user"
        args = {
            "content": "User's favorite color is blue",
            "category": "core"
        }

        with patch('mcp_server_omi.memories_db.create_memory') as mock_create, \
             patch('mcp_server_omi.threading.Thread'):

            result = await create_memory_impl(uid, args)

            assert result['success'] is True
            assert 'memory_id' in result
            assert result['category'] == 'core'
            assert mock_create.called

    @pytest.mark.asyncio
    async def test_create_memory_auto_categorize(self):
        """Test creating memory with auto-categorization"""
        uid = "test_user"
        args = {"content": "User loves playing tennis on weekends"}

        with patch('mcp_server_omi.identify_category_for_memory') as mock_categorize, \
             patch('mcp_server_omi.memories_db.create_memory'), \
             patch('mcp_server_omi.threading.Thread'):

            mock_categorize.return_value = "interests_hobbies"

            result = await create_memory_impl(uid, args)

            assert result['success'] is True
            assert mock_categorize.called
            # Should have auto-detected category
            assert 'category' in result

    @pytest.mark.asyncio
    async def test_create_memory_empty_content(self):
        """Test creating memory with empty content"""
        uid = "test_user"
        args = {"content": ""}

        result = await create_memory_impl(uid, args)

        assert result['success'] is False
        assert 'empty' in result['error'].lower()

    @pytest.mark.asyncio
    async def test_update_memory_success(self):
        """Test updating an existing memory"""
        uid = "test_user"
        args = {
            "memory_id": "mem123",
            "content": "Updated content"
        }

        with patch('mcp_server_omi.memories_db.edit_memory') as mock_edit:
            result = await update_memory_impl(uid, args)

            assert result['success'] is True
            assert mock_edit.called
            mock_edit.assert_called_with(uid, "mem123", "Updated content")

    @pytest.mark.asyncio
    async def test_delete_memory_success(self):
        """Test deleting a memory"""
        uid = "test_user"
        args = {"memory_id": "mem123"}

        with patch('mcp_server_omi.memories_db.delete_memory') as mock_delete:
            result = await delete_memory_impl(uid, args)

            assert result['success'] is True
            assert mock_delete.called
            mock_delete.assert_called_with(uid, "mem123")


class TestActionItemTools:
    """Test action item-related MCP tools"""

    @pytest.mark.asyncio
    async def test_create_action_item_basic(self):
        """Test creating a basic action item"""
        uid = "test_user"
        args = {"description": "Buy groceries"}

        with patch('mcp_server_omi.action_items_db.create_action_item') as mock_create:
            result = await create_action_item_impl(uid, args)

            assert result['success'] is True
            assert 'action_item_id' in result
            assert mock_create.called

    @pytest.mark.asyncio
    async def test_create_action_item_with_due_date(self):
        """Test creating action item with due date"""
        uid = "test_user"
        due_date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        args = {
            "description": "Submit report",
            "due_date": due_date
        }

        with patch('mcp_server_omi.action_items_db.create_action_item') as mock_create:
            result = await create_action_item_impl(uid, args)

            assert result['success'] is True
            # Should have parsed due date
            call_args = mock_create.call_args[0][1]
            assert call_args['due_date'] is not None

    @pytest.mark.asyncio
    async def test_list_action_items_pending(self):
        """Test listing pending action items"""
        uid = "test_user"
        args = {"status": "pending", "limit": 25}

        with patch('mcp_server_omi.action_items_db.get_action_items') as mock_get:
            mock_get.return_value = [
                {'id': 'action1', 'description': 'Task 1', 'completed': False},
                {'id': 'action2', 'description': 'Task 2', 'completed': False}
            ]

            result = await list_action_items_impl(uid, args)

            assert result['success'] is True
            assert result['count'] == 2
            # Should have called with completed=False
            mock_get.assert_called_with(uid, limit=25, offset=0, completed=False)

    @pytest.mark.asyncio
    async def test_list_action_items_all(self):
        """Test listing all action items"""
        uid = "test_user"
        args = {"status": "all", "limit": 10}

        with patch('mcp_server_omi.action_items_db.get_action_items') as mock_get:
            mock_get.return_value = []

            result = await list_action_items_impl(uid, args)

            # Should have called with completed=None (no filter)
            mock_get.assert_called_with(uid, limit=10, offset=0, completed=None)

    @pytest.mark.asyncio
    async def test_update_action_item_mark_complete(self):
        """Test marking action item as complete"""
        uid = "test_user"
        args = {
            "action_item_id": "action123",
            "completed": True
        }

        with patch('mcp_server_omi.action_items_db.update_action_item_status') as mock_update:
            result = await update_action_item_impl(uid, args)

            assert result['success'] is True
            mock_update.assert_called_with(uid, "action123", True)

    @pytest.mark.asyncio
    async def test_update_action_item_change_description(self):
        """Test updating action item description"""
        uid = "test_user"
        args = {
            "action_item_id": "action123",
            "description": "New description"
        }

        with patch('mcp_server_omi.action_items_db.update_action_item_description') as mock_update:
            result = await update_action_item_impl(uid, args)

            assert result['success'] is True
            mock_update.assert_called_with(uid, "action123", "New description")


class TestContextTools:
    """Test context retrieval tools"""

    @pytest.mark.asyncio
    async def test_get_user_context(self):
        """Test getting comprehensive user context"""
        uid = "test_user"

        with patch('mcp_server_omi.users_db.get_user') as mock_user, \
             patch('mcp_server_omi.memories_db.get_memories') as mock_memories, \
             patch('mcp_server_omi.action_items_db.get_action_items') as mock_actions:

            mock_user.return_value = {
                'name': 'John Doe',
                'email': 'john@example.com',
                'timezone': 'America/New_York'
            }
            mock_memories.return_value = [
                {'content': 'Memory 1'},
                {'content': 'Memory 2'}
            ]
            mock_actions.return_value = [
                {'description': 'Task 1'}
            ]

            result = await get_user_context_impl(uid)

            assert result['success'] is True
            assert result['user']['name'] == 'John Doe'
            assert result['recent_memories_count'] == 2
            assert result['pending_actions_count'] == 1

    @pytest.mark.asyncio
    async def test_get_conversation_summary(self):
        """Test getting conversation summary"""
        uid = "test_user"
        args = {"days": 7}

        with patch('mcp_server_omi.conversations_db.get_conversations') as mock_get:
            mock_get.return_value = [
                {'id': 'c1', 'structured': {'category': 'work', 'title': 'Meeting'}, 'is_locked': False},
                {'id': 'c2', 'structured': {'category': 'personal', 'title': 'Chat'}, 'is_locked': False},
                {'id': 'c3', 'structured': {'category': 'work', 'title': 'Project'}, 'is_locked': False}
            ]

            result = await get_conversation_summary_impl(uid, args)

            assert result['success'] is True
            assert result['total_conversations'] == 3
            assert 'by_category' in result
            assert result['by_category']['work'] == 2
            assert result['by_category']['personal'] == 1


class TestErrorHandling:
    """Test error handling in MCP tools"""

    @pytest.mark.asyncio
    async def test_tool_handles_database_error(self):
        """Test that tools handle database errors gracefully"""
        uid = "test_user"
        args = {"limit": 10}

        with patch('mcp_server_omi.memories_db.get_memories') as mock_get:
            mock_get.side_effect = Exception("Database connection failed")

            result = await search_memories_impl(uid, args)

            assert result['success'] is False
            assert 'error' in result

    @pytest.mark.asyncio
    async def test_tool_validates_input(self):
        """Test that tools validate input parameters"""
        uid = "test_user"
        args = {"memory_id": "", "content": ""}  # Invalid input

        result = await update_memory_impl(uid, args)

        assert result['success'] is False
        assert 'required' in result['error'].lower()


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
