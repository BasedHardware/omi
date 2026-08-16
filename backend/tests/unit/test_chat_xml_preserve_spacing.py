"""Regression test: get_messages_as_xml must not strip spacing out of message text.

models.chat.Message.get_messages_as_xml built each message block from a flush-left f-string
template and then did msg.replace('    ', '').strip(). The template has no 4-space runs, so the
replace only deleted 4-space runs from the interpolated message.text (code, tables, aligned or
pasted text), corrupting the chat history fed to the LLM. It now only strips the block's
surrounding whitespace.
"""

from datetime import datetime, timezone

from models.chat import Message


def _msg(text):
    return Message(
        id='1',
        text=text,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        sender='human',
        type='text',
    )


def test_four_space_run_in_message_text_is_preserved():
    xml = Message.get_messages_as_xml([_msg('def foo():        return 1')])
    assert 'def foo():        return 1' in xml


def test_message_text_content_present():
    xml = Message.get_messages_as_xml([_msg('hello world')])
    assert '<content>hello world</content>' in xml
