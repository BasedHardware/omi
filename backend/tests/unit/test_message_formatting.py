from datetime import datetime, timezone
from models.chat import Message, MessageSender, MessageType


def test_get_messages_as_string_sender_app_id():
    m = Message(
        id='m1',
        text='hello',
        created_at=datetime.now(timezone.utc),
        sender=MessageSender.ai,
        type=MessageType.text,
        app_id='some-app-id',
    )
    result = Message.get_messages_as_string([m], use_plugin_name_if_available=True)
    assert "some-app-id" in result


def test_get_messages_as_xml_sender_app_id():
    m = Message(
        id='m1',
        text='hello',
        created_at=datetime.now(timezone.utc),
        sender=MessageSender.ai,
        type=MessageType.text,
        app_id='some-app-id',
    )
    result = Message.get_messages_as_xml([m], use_plugin_name_if_available=True)
    assert "<sender>some-app-id</sender>" in result


def test_get_messages_as_string_defaults_to_ai_sender_for_app_id():
    m = Message(
        id='m1',
        text='hello',
        created_at=datetime.now(timezone.utc),
        sender=MessageSender.ai,
        type=MessageType.text,
        app_id='some-app-id',
    )

    result = Message.get_messages_as_string([m])

    assert "AI: hello" in result


def test_get_messages_as_xml_defaults_to_ai_sender_for_app_id():
    m = Message(
        id='m1',
        text='hello',
        created_at=datetime.now(timezone.utc),
        sender=MessageSender.ai,
        type=MessageType.text,
        app_id='some-app-id',
    )

    result = Message.get_messages_as_xml([m])

    assert "<sender>AI</sender>" in result


def _blank_app_id_variants():
    return [None, '', '   ']


def test_get_messages_as_string_blank_app_id_falls_back_to_ai_sender():
    for app_id in _blank_app_id_variants():
        m = Message(
            id='m1',
            text='hello',
            created_at=datetime.now(timezone.utc),
            sender=MessageSender.ai,
            type=MessageType.text,
            app_id=app_id,
        )

        result = Message.get_messages_as_string([m], use_plugin_name_if_available=True)

        assert "AI: hello" in result, f"blank app_id={app_id!r} must not emit an empty sender"


def test_get_messages_as_xml_blank_app_id_falls_back_to_ai_sender():
    for app_id in _blank_app_id_variants():
        m = Message(
            id='m1',
            text='hello',
            created_at=datetime.now(timezone.utc),
            sender=MessageSender.ai,
            type=MessageType.text,
            app_id=app_id,
        )

        result = Message.get_messages_as_xml([m], use_plugin_name_if_available=True)

        assert "<sender>AI</sender>" in result, f"blank app_id={app_id!r} must not emit an empty sender"
