from datetime import datetime, timezone
from unittest.mock import MagicMock

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
    lookup = MagicMock(return_value='Friendly Bot')
    result = Message.get_messages_as_string([m], use_plugin_name_if_available=True, app_name_resolver=lookup)

    assert 'Friendly Bot: hello' in result
    assert 'some-app-id' not in result
    lookup.assert_called_once_with('some-app-id')


def test_get_messages_as_xml_sender_uses_app_display_name():
    m = _ai_message()
    lookup = MagicMock(return_value='Friendly Bot')
    result = Message.get_messages_as_xml([m], use_plugin_name_if_available=True, app_name_resolver=lookup)

    assert '<sender>Friendly Bot</sender>' in result
    lookup.assert_called_once_with('some-app-id')


def test_get_messages_as_string_defaults_to_ai_sender_for_app_id():
    m = _ai_message()

    lookup = MagicMock()
    result = Message.get_messages_as_string([m], app_name_resolver=lookup)

    assert 'AI: hello' in result
    lookup.assert_not_called()


def test_get_messages_as_xml_defaults_to_ai_sender_for_app_id():
    m = _ai_message()

    lookup = MagicMock()
    result = Message.get_messages_as_xml([m], app_name_resolver=lookup)

    assert '<sender>AI</sender>' in result
    lookup.assert_not_called()


def _blank_app_id_variants():
    return [None, '', '   ']


def test_get_messages_as_string_blank_app_id_falls_back_to_ai_sender():
    for app_id in _blank_app_id_variants():
        m = _ai_message(app_id=app_id)

        lookup = MagicMock()
        result = Message.get_messages_as_string([m], use_plugin_name_if_available=True, app_name_resolver=lookup)

        assert 'AI: hello' in result, f'blank app_id={app_id!r} must not emit an empty sender'
        lookup.assert_not_called()


def test_get_messages_as_xml_blank_app_id_falls_back_to_ai_sender():
    for app_id in _blank_app_id_variants():
        m = _ai_message(app_id=app_id)

        lookup = MagicMock()
        result = Message.get_messages_as_xml([m], use_plugin_name_if_available=True, app_name_resolver=lookup)

        assert '<sender>AI</sender>' in result, f'blank app_id={app_id!r} must not emit an empty sender'
        lookup.assert_not_called()


def test_get_messages_as_string_missing_app_falls_back_to_ai_sender():
    m = _ai_message()
    lookup = MagicMock(return_value=None)
    result = Message.get_messages_as_string([m], use_plugin_name_if_available=True, app_name_resolver=lookup)

    assert 'AI: hello' in result
    lookup.assert_called_once_with('some-app-id')


def test_get_messages_as_xml_missing_app_falls_back_to_ai_sender():
    m = _ai_message()
    lookup = MagicMock(return_value=None)
    result = Message.get_messages_as_xml([m], use_plugin_name_if_available=True, app_name_resolver=lookup)

    assert '<sender>AI</sender>' in result
    lookup.assert_called_once_with('some-app-id')


def test_get_messages_as_string_blank_app_name_falls_back_to_ai_sender():
    m = _ai_message()
    lookup = MagicMock(return_value='  ')
    result = Message.get_messages_as_string([m], use_plugin_name_if_available=True, app_name_resolver=lookup)

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
    lookup = MagicMock(return_value='Shared')
    result = Message.get_messages_as_string(messages, use_plugin_name_if_available=True, app_name_resolver=lookup)

    assert result.count('Shared:') == 2
    lookup.assert_called_once_with('shared-app')
