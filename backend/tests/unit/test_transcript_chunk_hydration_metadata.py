"""hydrate_chunk_texts must attach parent-conversation metadata for typed sources.

The /v1/tools/conversations/search-chunks endpoint builds ToolSource entries
(kind 'conversation', source_id = parent conversation id) from hydrated rows, so
hydration has to carry the conversation title and start time alongside the text
without a second Firestore read.
"""

from datetime import datetime, timezone

import pytest

import utils.conversations.transcript_chunks as transcript_chunks

STARTED_AT = datetime(2026, 8, 14, 21, 30, tzinfo=timezone.utc)


def _conversation(conv_id="conv-a", title="Release chat", segments=None):
    return {
        'id': conv_id,
        'structured': {'title': title},
        'started_at': STARTED_AT,
        'transcript_segments': segments if segments is not None else [{'text': 'the beta shipped', 'is_user': True}],
    }


@pytest.fixture
def conversations_by_id(monkeypatch):
    holder = {'conversations': []}
    monkeypatch.setattr(
        transcript_chunks.conversations_db,
        'get_conversations_by_id',
        lambda _uid, _ids, **_kwargs: holder['conversations'],
    )
    return holder


def test_hydrated_rows_carry_conversation_title_and_start_time(conversations_by_id):
    conversations_by_id['conversations'] = [_conversation()]
    rows = transcript_chunks.hydrate_chunk_texts(
        'uid-1', [{'conversation_id': 'conv-a', 'chunk_index': 0, 'created_at': 0, 'score': 0.9}]
    )
    assert len(rows) == 1
    assert 'the beta shipped' in rows[0]['text']
    assert rows[0]['conversation_title'] == 'Release chat'
    assert rows[0]['conversation_started_at'] == STARTED_AT


def test_non_dict_structured_yields_none_title_not_a_crash(conversations_by_id):
    conversation = _conversation()
    conversation['structured'] = None
    conversations_by_id['conversations'] = [conversation]
    rows = transcript_chunks.hydrate_chunk_texts(
        'uid-1', [{'conversation_id': 'conv-a', 'chunk_index': 0, 'created_at': 0, 'score': 0.9}]
    )
    assert rows[0]['conversation_title'] is None


def test_vanished_conversation_rows_still_drop(conversations_by_id):
    conversations_by_id['conversations'] = [_conversation()]
    rows = transcript_chunks.hydrate_chunk_texts(
        'uid-1',
        [
            {'conversation_id': 'conv-a', 'chunk_index': 0, 'created_at': 0, 'score': 0.9},
            {'conversation_id': 'conv-gone', 'chunk_index': 0, 'created_at': 0, 'score': 0.8},
        ],
    )
    assert [r['conversation_id'] for r in rows] == ['conv-a']
