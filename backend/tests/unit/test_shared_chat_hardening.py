"""#20487 — _gateway_messages must survive a malformed resolved conversation.

A conversation row that isn't a Mapping, or whose transcript_segments is a
string/dict/scalar, used to crash on .get()/the segment join before the
gateway call. The guard coerces both to an empty transcript.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from models.conversation import SharedConversationChatRequest
from routers.public_shared_conversation_chat import _gateway_messages


def _request():
    return SharedConversationChatRequest(conversation_id='c1', question='what was said?', history=[])


def test_non_mapping_conversation_returns_empty_transcript():
    for bad in (None, 'raw string', ['a', 'b'], 7):
        msgs = _gateway_messages(_request(), bad)
        assert '<shared_conversation_transcript>\n\n</shared_conversation_transcript>' in msgs[0]['content']
        assert msgs[-1] == {'role': 'user', 'content': 'what was said?'}


def test_non_sequence_segments_coerced_to_empty():
    for bad_segments in ('a string', {'seg': 1}, 42, None):
        msgs = _gateway_messages(_request(), {'transcript_segments': bad_segments})
        assert isinstance(msgs[0]['content'], str)
        assert 'what was said?' == msgs[-1]['content']


def test_mapping_without_segments_is_fine():
    msgs = _gateway_messages(_request(), {'title': 'meeting notes'})
    assert msgs[-1]['content'] == 'what was said?'


def test_real_segments_render_in_system_prompt():
    conv = {'transcript_segments': [{'speaker': 'S1', 'text': 'hello world', 'start': 0, 'end': 1}]}
    msgs = _gateway_messages(_request(), conv)
    assert 'hello world' in msgs[0]['content']
