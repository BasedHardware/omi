from datetime import datetime, timezone

from pydantic import TypeAdapter

from models.chat_session import ChatSessionResponse


def test_chat_session_response_repairs_legacy_none_fields():
    created_at = datetime(2026, 7, 5, tzinfo=timezone.utc)

    response = ChatSessionResponse.model_validate(
        {
            'id': 'session-1',
            'title': None,
            'preview': None,
            'created_at': created_at,
            'updated_at': created_at,
            'app_id': None,
            'plugin_id': None,
            'message_count': None,
            'starred': None,
            'message_ids': ['message-1', 'message-2'],
        }
    )

    assert response.title == 'New Chat'
    assert response.message_count == 2
    assert response.starred is False


def test_chat_session_response_list_accepts_legacy_missing_updated_at():
    created_at = datetime(2026, 7, 5, tzinfo=timezone.utc)

    responses = TypeAdapter(list[ChatSessionResponse]).validate_python(
        [
            {
                'id': 'session-1',
                'created_at': created_at,
                'plugin_id': 'app-1',
                'message_ids': ['message-1'],
            }
        ]
    )

    assert responses[0].title == 'New Chat'
    assert responses[0].updated_at == created_at
    assert responses[0].app_id == 'app-1'
    assert responses[0].plugin_id == 'app-1'
    assert responses[0].message_count == 1
    assert responses[0].starred is False
