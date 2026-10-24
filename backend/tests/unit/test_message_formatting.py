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


def test_get_messages_as_string_and_xml_with_mixed_naive_and_aware_timestamps():
    naive_dt = datetime(2026, 10, 18, 10, 0, 0)
    aware_dt = datetime(2026, 10, 18, 11, 0, 0, tzinfo=timezone.utc)

    m_naive = Message(
        id='m_naive',
        text='naive message',
        created_at=naive_dt,
        sender=MessageSender.human,
        type=MessageType.text,
    )
    m_aware = Message(
        id='m_aware',
        text='aware message',
        created_at=aware_dt,
        sender=MessageSender.ai,
        type=MessageType.text,
    )

    res_str = Message.get_messages_as_string([m_aware, m_naive])
    assert 'naive message' in res_str
    assert 'aware message' in res_str
    assert res_str.index('naive message') < res_str.index('aware message')

    res_xml = Message.get_messages_as_xml([m_aware, m_naive])
    assert '<content>naive message</content>' in res_xml
    assert '<content>aware message</content>' in res_xml
    assert res_xml.index('naive message') < res_xml.index('aware message')


def test_get_messages_as_string_and_xml_with_duck_typed_objects():
    from types import SimpleNamespace

    msg1 = SimpleNamespace(
        text='first duck message',
        sender='human',
        created_at=datetime(2026, 10, 18, 10, 0, 0, tzinfo=timezone.utc),
        files_id=[],
        files=[],
    )
    msg2 = SimpleNamespace(
        text='second duck message',
        sender='ai',
        created_at=datetime(2026, 10, 18, 11, 0, 0, tzinfo=timezone.utc),
        files_id=[],
        files=[],
    )

    res_str = Message.get_messages_as_string([msg2, msg1])
    assert 'first duck message' in res_str
    assert 'second duck message' in res_str
    assert res_str.index('first duck message') < res_str.index('second duck message')

    res_xml = Message.get_messages_as_xml([msg2, msg1])
    assert '<content>first duck message</content>' in res_xml
    assert '<content>second duck message</content>' in res_xml
    assert res_xml.index('first duck message') < res_xml.index('second duck message')
