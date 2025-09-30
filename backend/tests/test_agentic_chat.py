"""
Unit tests for agentic chat implementation

Tests the OpenAI Agents + MCP integration for:
- Agent tool calling behavior
- Proactive memory creation
- Action item extraction
- Conversation search
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock

from utils.llm.agentic_chat import (
    execute_agentic_chat_stream,
    _build_system_prompt,
    _convert_messages_to_agent_format,
    get_agent_config
)
from models.chat import Message, MessageType


class TestAgenticChatStreaming:
    """Test agentic chat streaming functionality"""

    @pytest.mark.asyncio
    async def test_agent_stream_basic_response(self):
        """Test that agent streams a basic response"""
        uid = "test_user_123"
        messages = [
            Message(
                id="1",
                sender="human",
                type=MessageType.text,
                text="Hello!",
                created_at=datetime.now(timezone.utc)
            )
        ]

        callback_data = {}
        chunks = []

        async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
            if chunk:
                chunks.append(chunk)

        # Should have streamed some content
        assert len(chunks) > 0
        # Should have final answer
        assert 'answer' in callback_data
        assert isinstance(callback_data['answer'], str)

    @pytest.mark.asyncio
    async def test_agent_creates_memory_proactively(self):
        """Test that agent automatically creates memories when user shares important info"""
        uid = "test_user_mem"
        messages = [
            Message(
                id="1",
                sender="human",
                type=MessageType.text,
                text="My favorite color is blue and I love hiking on weekends",
                created_at=datetime.now(timezone.utc)
            )
        ]

        callback_data = {}
        async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
            pass

        # Verify memory creation tool was called
        agent_actions = callback_data.get('agent_actions', [])
        tool_calls = [action.get('tool') for action in agent_actions]

        # Should have called create_memory tool
        assert 'create_memory' in tool_calls

    @pytest.mark.asyncio
    async def test_agent_creates_action_item(self):
        """Test agent creates action items when user mentions tasks"""
        uid = "test_user_action"
        messages = [
            Message(
                id="1",
                sender="human",
                type=MessageType.text,
                text="I need to call John tomorrow at 3pm",
                created_at=datetime.now(timezone.utc)
            )
        ]

        callback_data = {}
        async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
            pass

        # Verify action item creation
        agent_actions = callback_data.get('agent_actions', [])
        tool_calls = [action.get('tool') for action in agent_actions]

        # Should have called create_action_item tool
        assert 'create_action_item' in tool_calls

    @pytest.mark.asyncio
    async def test_agent_searches_conversations(self):
        """Test agent searches conversations when answering questions about past"""
        uid = "test_user_search"
        messages = [
            Message(
                id="1",
                sender="human",
                type=MessageType.text,
                text="What did I discuss with Sarah last week?",
                created_at=datetime.now(timezone.utc)
            )
        ]

        callback_data = {}
        async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
            pass

        # Verify conversation search was performed
        agent_actions = callback_data.get('agent_actions', [])
        tool_calls = [action.get('tool') for action in agent_actions]

        # Should have called search_conversations tool
        assert 'search_conversations' in tool_calls

    @pytest.mark.asyncio
    async def test_agent_handles_multi_turn_conversation(self):
        """Test agent maintains context in multi-turn conversation"""
        uid = "test_user_multi"
        messages = [
            Message(
                id="1",
                sender="human",
                type=MessageType.text,
                text="I love hiking",
                created_at=datetime.now(timezone.utc)
            ),
            Message(
                id="2",
                sender="ai",
                type=MessageType.text,
                text="That's great! I'll remember that.",
                created_at=datetime.now(timezone.utc)
            ),
            Message(
                id="3",
                sender="human",
                type=MessageType.text,
                text="What do you know about my hobbies?",
                created_at=datetime.now(timezone.utc)
            )
        ]

        callback_data = {}
        async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
            pass

        # Should have an answer
        assert 'answer' in callback_data
        answer = callback_data['answer'].lower()

        # Answer should reference hiking
        assert 'hiking' in answer or 'hobby' in answer


class TestSystemPromptBuilding:
    """Test system prompt construction"""

    def test_build_default_system_prompt(self):
        """Test building default Omi system prompt"""
        prompt = _build_system_prompt(
            user_name="John",
            memories_str="John loves hiking. His birthday is June 15th.",
            timezone_str="America/New_York",
            app=None
        )

        # Should include user name
        assert "John" in prompt
        # Should include memories
        assert "hiking" in prompt
        # Should include timezone
        assert "America/New_York" in prompt
        # Should include tool instructions
        assert "search_conversations" in prompt
        assert "create_memory" in prompt

    def test_build_custom_app_prompt(self):
        """Test building custom app prompt"""
        from models.app import App

        app = App(
            id="test_app",
            name="TestBot",
            chat_prompt="a helpful assistant that speaks like a pirate",
            capabilities=["chat"]
        )

        prompt = _build_system_prompt(
            user_name="John",
            memories_str="",
            timezone_str="UTC",
            app=app
        )

        # Should include app name
        assert "TestBot" in prompt
        # Should include custom prompt
        assert "pirate" in prompt


class TestMessageConversion:
    """Test message format conversion"""

    def test_convert_messages_to_agent_format(self):
        """Test converting Omi messages to agent format"""
        messages = [
            Message(
                id="1",
                sender="human",
                type=MessageType.text,
                text="Hello",
                created_at=datetime.now(timezone.utc)
            ),
            Message(
                id="2",
                sender="ai",
                type=MessageType.text,
                text="Hi there!",
                created_at=datetime.now(timezone.utc)
            )
        ]

        agent_messages = _convert_messages_to_agent_format(messages)

        assert len(agent_messages) == 2
        assert agent_messages[0]['role'] == 'user'
        assert agent_messages[0]['content'] == 'Hello'
        assert agent_messages[1]['role'] == 'assistant'
        assert agent_messages[1]['content'] == 'Hi there!'


class TestAgentConfig:
    """Test agent configuration"""

    @patch.dict('os.environ', {
        'ENABLE_AGENTIC_CHAT': 'true',
        'AGENT_MODEL': 'o4-mini',
        'AGENT_REASONING_EFFORT': 'high'
    })
    def test_get_agent_config_from_env(self):
        """Test reading agent config from environment"""
        config = get_agent_config()

        assert config['enabled'] is True
        assert config['model'] == 'o4-mini'
        assert config['reasoning_effort'] == 'high'

    @patch.dict('os.environ', {})
    def test_get_agent_config_defaults(self):
        """Test agent config with defaults"""
        config = get_agent_config()

        # Should have sensible defaults
        assert 'enabled' in config
        assert 'model' in config
        assert 'reasoning_effort' in config


class TestErrorHandling:
    """Test error handling in agentic chat"""

    @pytest.mark.asyncio
    async def test_agent_handles_mcp_server_error(self):
        """Test agent gracefully handles MCP server errors"""
        uid = "test_user_error"
        messages = [
            Message(
                id="1",
                sender="human",
                type=MessageType.text,
                text="Hello",
                created_at=datetime.now(timezone.utc)
            )
        ]

        callback_data = {}

        # Mock MCP server to raise error
        with patch('utils.llm.agentic_chat.MCPServerStdio') as mock_mcp:
            mock_mcp.side_effect = Exception("MCP connection failed")

            async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
                pass

            # Should have error in callback_data
            assert 'error' in callback_data

    @pytest.mark.asyncio
    async def test_agent_handles_tool_call_error(self):
        """Test agent handles tool call errors gracefully"""
        # This would require mocking tool responses
        # Left as a TODO for full implementation
        pass


class TestPerformance:
    """Test performance characteristics"""

    @pytest.mark.asyncio
    async def test_streaming_latency(self):
        """Test that first token arrives quickly"""
        uid = "test_user_perf"
        messages = [
            Message(
                id="1",
                sender="human",
                type=MessageType.text,
                text="Hello!",
                created_at=datetime.now(timezone.utc)
            )
        ]

        callback_data = {}
        start_time = asyncio.get_event_loop().time()
        first_chunk_time = None

        async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
            if chunk and first_chunk_time is None:
                first_chunk_time = asyncio.get_event_loop().time()
                break

        if first_chunk_time:
            latency = first_chunk_time - start_time
            # First token should arrive within 5 seconds
            assert latency < 5.0, f"First token latency too high: {latency}s"


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
