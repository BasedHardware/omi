"""conv_discard must survive the non-JSON replies gpt-5-nano actually returns.

Prod logs showed 450+ `Error determining memory discard: Invalid json output`
per day, split between `{"discard": True}` (Python booleans) and the bare
`discard = True` line the prompt asks for. Both raised, the caller failed open
to False, and every conversation the model wanted to discard was kept.
"""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.exceptions import OutputParserException

from utils.llm import conversation_processing
from utils.llm.discard_parser import DiscardConversation, LenientDiscardParser


def _parser() -> LenientDiscardParser:
    return LenientDiscardParser(pydantic_object=DiscardConversation)


@pytest.mark.parametrize(
    'text, expected',
    [
        ('{"discard": true}', True),  # valid JSON still parses
        ('{"discard": false}', False),
        ('{"discard": True}', True),  # prod shape: Python booleans
        ('{"discard": False}', False),
        ('discard = True', True),  # prod shape: the one-line format the prompt asks for
        ('discard = False', False),
        ('```json\n{"discard": True}\n```', True),
    ],
)
def test_parser_accepts_shapes_seen_in_prod(text, expected):
    assert _parser().parse(text).discard is expected


def test_parser_still_raises_on_a_reply_with_no_decision():
    with pytest.raises(OutputParserException):
        _parser().parse('I am not sure about this conversation.')


def test_should_discard_conversation_honors_python_boolean_reply(monkeypatch):
    fake_llm = FakeMessagesListChatModel(responses=[AIMessage(content='{"discard": True}')])
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda feature, **kwargs: fake_llm)

    assert conversation_processing.should_discard_conversation('hello there', duration_seconds=15) is True


def test_should_discard_conversation_fails_open_when_reply_is_unusable(monkeypatch):
    fake_llm = FakeMessagesListChatModel(responses=[AIMessage(content='no idea')])
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda feature, **kwargs: fake_llm)

    assert conversation_processing.should_discard_conversation('hello there', duration_seconds=15) is False
