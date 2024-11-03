import pytest
from database.chat import ChatDB
from models.chat import ChatMessage, ChatSession

class TestChatDB:
    @pytest.fixture
    def chat_db(self, db_client):
        return ChatDB(db_client)

    async def test_create_chat_session(self, chat_db):
        session_data = {
            "session_id": "test_session_1",
            "user_id": "test_user_1",
            "created_at": "2024-03-20T10:00:00Z"
        }
        result = await chat_db.create_session(session_data)
        assert result["session_id"] == session_data["session_id"]
        assert result["user_id"] == session_data["user_id"]

    async def test_get_chat_session(self, chat_db):
        session_id = "test_session_1"
        session = await chat_db.get_session(session_id)
        assert session is not None
        assert session["session_id"] == session_id

    async def test_add_message(self, chat_db):
        message = ChatMessage(
            session_id="test_session_1",
            message_id="test_message_1",
            content="Hello, world!",
            role="user"
        )
        result = await chat_db.add_message(message)
        assert result["message_id"] == message.message_id
        assert result["content"] == message.content

    async def test_get_session_messages(self, chat_db):
        session_id = "test_session_1"
        messages = await chat_db.get_session_messages(session_id)
        assert len(messages) > 0
        assert messages[0]["session_id"] == session_id 