from datetime import datetime, timezone
from unittest.mock import patch

from models.chat import Message, MessageSender, MessageType


def _ai_message(*, app_id='some-app-id', text='hello'):
    return Message(
        id='m1',
        text=text,
        created_at=datetime.now(timezone.utc),
        sender=MessageSender.ai,
        type=MessageType.text,
        app_id=app_id,
    )


def test_get_messages_as_string_sender_uses_app_display_name():
    m = _ai_message()
    with patch('database.apps.get_app_by_id_db', return_value={'id': 'some-app-id', 'name': 'Friendly Bot'}) as lookup:
        result = Message.get_messages_as_string([m], use_plugin_name_if_available=True)

    assert 'Friendly Bot: hello' in result
    assert 'some-app-id' not in result
    lookup.assert_called_once_with('some-app-id')


def test_get_messages_as_xml_sender_uses_app_display_name():
    m = _ai_message()
    with patch('database.apps.get_app_by_id_db', return_value={'id': 'some-app-id', 'name': 'Friendly Bot'}) as lookup:
        result = Message.get_messages_as_xml([m], use_plugin_name_if_available=True)

    assert '<sender>Friendly Bot</sender>' in result
    lookup.assert_called_once_with('some-app-id')


def test_get_messages_as_string_defaults_to_ai_sender_for_app_id():
    m = _ai_message()

    with patch('database.apps.get_app_by_id_db') as lookup:
        result = Message.get_messages_as_string([m])

    assert 'AI: hello' in result
    lookup.assert_not_called()


def test_get_messages_as_xml_defaults_to_ai_sender_for_app_id():
    m = _ai_message()

    with patch('database.apps.get_app_by_id_db') as lookup:
        result = Message.get_messages_as_xml([m])

    assert '<sender>AI</sender>' in result
    lookup.assert_not_called()


def _blank_app_id_variants():
    return [None, '', '   ']


def test_get_messages_as_string_blank_app_id_falls_back_to_ai_sender():
    for app_id in _blank_app_id_variants():
        m = _ai_message(app_id=app_id)

        with patch('database.apps.get_app_by_id_db') as lookup:
            result = Message.get_messages_as_string([m], use_plugin_name_if_available=True)

        assert 'AI: hello' in result, f'blank app_id={app_id!r} must not emit an empty sender'
        lookup.assert_not_called()


def test_get_messages_as_xml_blank_app_id_falls_back_to_ai_sender():
    for app_id in _blank_app_id_variants():
        m = _ai_message(app_id=app_id)

        with patch('database.apps.get_app_by_id_db') as lookup:
            result = Message.get_messages_as_xml([m], use_plugin_name_if_available=True)

        assert '<sender>AI</sender>' in result, f'blank app_id={app_id!r} must not emit an empty sender'
        lookup.assert_not_called()


def test_get_messages_as_string_missing_app_falls_back_to_ai_sender():
    m = _ai_message()
    with patch('database.apps.get_app_by_id_db', return_value=None) as lookup:
        result = Message.get_messages_as_string([m], use_plugin_name_if_available=True)

    assert 'AI: hello' in result
    lookup.assert_called_once_with('some-app-id')


def test_get_messages_as_xml_missing_app_falls_back_to_ai_sender():
    m = _ai_message()
    with patch('database.apps.get_app_by_id_db', return_value=None) as lookup:
        result = Message.get_messages_as_xml([m], use_plugin_name_if_available=True)

    assert '<sender>AI</sender>' in result
    lookup.assert_called_once_with('some-app-id')


def test_get_messages_as_string_blank_app_name_falls_back_to_ai_sender():
    m = _ai_message()
    with patch('database.apps.get_app_by_id_db', return_value={'id': 'some-app-id', 'name': '  '}):
        result = Message.get_messages_as_string([m], use_plugin_name_if_available=True)

    assert 'AI: hello' in result


def test_sender_name_lookup_is_cached_per_app_id():
    messages = [
        _ai_message(app_id='shared-app', text='one'),
        Message(
            id='m2',
            text='two',
            created_at=datetime.now(timezone.utc),
            sender=MessageSender.ai,
            type=MessageType.text,
            app_id='shared-app',
        ),
    ]
    with patch('database.apps.get_app_by_id_db', return_value={'id': 'shared-app', 'name': 'Shared'}) as lookup:
        result = Message.get_messages_as_string(messages, use_plugin_name_if_available=True)

    assert result.count('Shared:') == 2
    lookup.assert_called_once_with('shared-app')
