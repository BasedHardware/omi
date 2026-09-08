"""Tests for proactive-message delivery over /v4/listen.

Covers the new event model, the Redis publish seam, the process-local
listen-session registry, and the async dispatcher that forwards published
messages to the right websocket.
"""

import asyncio
import json
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


class TestProactiveMessageEvent:
    def test_to_json_sets_type_and_drops_event_type(self):
        from models.message_event import ProactiveMessageEvent

        event = ProactiveMessageEvent(
            app_id="mentor",
            title="Omi",
            message="Hey, want to talk about what you said earlier?",
        )
        result = event.to_json()
        assert result["type"] == "proactive_message"
        assert "event_type" not in result
        assert result["app_id"] == "mentor"
        assert result["title"] == "Omi"
        assert result["message"] == "Hey, want to talk about what you said earlier?"

    def test_to_json_excludes_none_conversation_id(self):
        from models.message_event import ProactiveMessageEvent

        event = ProactiveMessageEvent(
            app_id="some-app",
            title="Some App",
            message="Check this out",
            conversation_id=None,
        )
        result = event.to_json()
        assert "conversation_id" not in result

    def test_to_json_includes_conversation_id_when_set(self):
        from models.message_event import ProactiveMessageEvent

        event = ProactiveMessageEvent(
            app_id="mentor",
            title="Omi",
            message="Hi",
            conversation_id="conv-123",
        )
        result = event.to_json()
        assert result["conversation_id"] == "conv-123"


class TestPublishProactiveMessage:
    def test_publishes_json_payload_to_channel(self):
        from database import redis_db

        mock_redis = MagicMock()
        with patch.object(redis_db, 'r', mock_redis):
            redis_db.publish_proactive_message('uid-1', 'mentor', 'Omi', 'Hello', 'conv-1')

        mock_redis.publish.assert_called_once()
        channel, payload = mock_redis.publish.call_args[0]
        assert channel == redis_db.PROACTIVE_MESSAGE_CHANNEL
        data = json.loads(payload)
        assert data == {
            'uid': 'uid-1',
            'app_id': 'mentor',
            'title': 'Omi',
            'message': 'Hello',
            'conversation_id': 'conv-1',
        }

    def test_fail_open_on_redis_error(self):
        from database import redis_db

        mock_redis = MagicMock()
        mock_redis.publish.side_effect = ConnectionError("redis down")
        with patch.object(redis_db, 'r', mock_redis):
            result = redis_db.publish_proactive_message('uid-1', 'mentor', 'Omi', 'Hello')
        assert result is None


class TestListenSessionRegistry:
    def setup_method(self):
        from routers.listen import registry

        registry._sessions.clear()

    def teardown_method(self):
        from routers.listen import registry

        registry._sessions.clear()

    def _make_session(self, uid: str) -> MagicMock:
        session = MagicMock()
        session.request.uid = uid
        session.send_event = MagicMock()
        return session

    def test_register_and_sessions_for(self):
        from routers.listen.registry import register, _sessions_for

        s1 = self._make_session("uid-a")
        s2 = self._make_session("uid-a")
        s3 = self._make_session("uid-b")

        register(s1)
        register(s2)
        register(s3)

        assert set(_sessions_for("uid-a")) == {s1, s2}
        assert _sessions_for("uid-b") == [s3]
        assert _sessions_for("uid-c") == []

    def test_unregister_removes_session(self):
        from routers.listen.registry import register, unregister, _sessions_for

        s1 = self._make_session("uid-a")
        s2 = self._make_session("uid-a")
        register(s1)
        register(s2)

        unregister(s1)
        assert _sessions_for("uid-a") == [s2]

        unregister(s2)
        assert _sessions_for("uid-a") == []

    def test_unregister_unknown_session_is_noop(self):
        from routers.listen.registry import unregister, _sessions_for

        s = self._make_session("uid-ghost")
        unregister(s)
        assert _sessions_for("uid-ghost") == []


class TestProactiveMessageDispatcher:
    def setup_method(self):
        from routers.listen import registry

        registry._sessions.clear()

    def teardown_method(self):
        from routers.listen import registry

        registry._sessions.clear()

    def _make_session(self, uid: str) -> MagicMock:
        session = MagicMock()
        session.request.uid = uid
        session.send_event = MagicMock()
        return session

    @pytest.mark.asyncio
    async def test_dispatcher_forwards_to_registered_sessions(self):
        from routers.listen.registry import register, proactive_message_dispatcher

        s1 = self._make_session("uid-target")
        s2 = self._make_session("uid-other")
        register(s1)
        register(s2)

        payload = {
            "uid": "uid-target",
            "app_id": "mentor",
            "title": "Omi",
            "message": "Hey there",
            "conversation_id": "conv-42",
        }

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()

        call_count = 0

        async def fake_get_message(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"type": "message", "data": json.dumps(payload)}
            raise asyncio.CancelledError()

        mock_pubsub.get_message = fake_get_message

        mock_client = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub

        await proactive_message_dispatcher(client=mock_client)

        s1.send_event.assert_called_once()
        s2.send_event.assert_not_called()

        delivered_event = s1.send_event.call_args[0][0]
        assert delivered_event.event_type == "proactive_message"
        assert delivered_event.app_id == "mentor"
        assert delivered_event.title == "Omi"
        assert delivered_event.message == "Hey there"
        assert delivered_event.conversation_id == "conv-42"

    @pytest.mark.asyncio
    async def test_dispatcher_ignores_messages_without_uid(self):
        from routers.listen.registry import register, proactive_message_dispatcher

        s = self._make_session("uid-x")
        register(s)

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()

        call_count = 0

        async def fake_get_message(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"type": "message", "data": json.dumps({"app_id": "x", "message": "no uid"})}
            raise asyncio.CancelledError()

        mock_pubsub.get_message = fake_get_message

        mock_client = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub

        await proactive_message_dispatcher(client=mock_client)

        s.send_event.assert_not_called()
