"""Legacy plugin_id documents must deserialize onto ChatSession.app_id."""

from datetime import datetime, timezone

from models.chat import ChatSession, Message


def test_chat_session_copies_plugin_id_onto_app_id():
    session = ChatSession.model_validate(
        {
            'id': 'sess-1',
            'created_at': datetime(2026, 8, 23, tzinfo=timezone.utc),
            'plugin_id': 'app-legacy',
        }
    )
    assert session.app_id == 'app-legacy'


def test_message_copies_plugin_id_onto_app_id():
    message = Message.model_validate(
        {
            'id': 'msg-1',
            'text': 'hello',
            'created_at': datetime(2026, 8, 23, tzinfo=timezone.utc),
            'sender': 'ai',
            'type': 'text',
            'plugin_id': 'app-legacy',
        }
    )
    assert message.app_id == 'app-legacy'
