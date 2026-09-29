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


def test_build_transcript_chunks_handles_iso_string_and_numeric_timestamps():
    segs = [{'text': 'the beta shipped', 'is_user': True}]
    # ISO string with UTC 'Z'
    chunks_iso = transcript_chunks.build_transcript_chunks(segs, '2026-08-14T21:30:00Z')
    assert len(chunks_iso) == 1
    assert '[Conversation on 14 Aug 2026, 21:30]' in chunks_iso[0]['text']
    assert chunks_iso[0]['created_at'] == int(STARTED_AT.timestamp())

    # Numeric integer epoch timestamp
    chunks_int = transcript_chunks.build_transcript_chunks(segs, int(STARTED_AT.timestamp()))
    assert len(chunks_int) == 1
    assert '[Conversation on 14 Aug 2026, 21:30]' in chunks_int[0]['text']
    assert chunks_int[0]['created_at'] == int(STARTED_AT.timestamp())

    # Numeric float epoch timestamp
    chunks_float = transcript_chunks.build_transcript_chunks(segs, STARTED_AT.timestamp() + 0.75)
    assert len(chunks_float) == 1
    assert chunks_float[0]['created_at'] == int(STARTED_AT.timestamp())

    # Naive datetime is treated as UTC
    naive_dt = datetime(2026, 8, 14, 21, 30, 0)
    chunks_naive = transcript_chunks.build_transcript_chunks(segs, naive_dt)
    assert chunks_naive[0]['created_at'] == int(STARTED_AT.timestamp())

    # Fallbacks on None, boolean, or malformed string
    for invalid in [None, False, True, 'not-a-date']:
        chunks_invalid = transcript_chunks.build_transcript_chunks(segs, invalid)
        assert len(chunks_invalid) == 1
        assert chunks_invalid[0]['created_at'] == 0
        assert not chunks_invalid[0]['text'].startswith('[Conversation on')


def test_hydrate_chunk_texts_handles_iso_string_and_timestamp_in_conversation(conversations_by_id):
    conv_str = {
        'id': 'conv-str',
        'structured': {'title': 'ISO Chat'},
        'started_at': '2026-08-14T21:30:00Z',
        'transcript_segments': [{'text': 'shipped today', 'is_user': True}],
    }
    conv_int = {
        'id': 'conv-int',
        'structured': {'title': 'Timestamp Chat'},
        'created_at': int(STARTED_AT.timestamp()),
        'transcript_segments': [{'text': 'shipped yesterday', 'is_user': False}],
    }
    conversations_by_id['conversations'] = [conv_str, conv_int]

    rows = transcript_chunks.hydrate_chunk_texts(
        'uid-1',
        [
            {'conversation_id': 'conv-str', 'chunk_index': 0},
            {'conversation_id': 'conv-int', 'chunk_index': 0},
        ],
    )
    assert len(rows) == 2
    assert '[Conversation on 14 Aug 2026, 21:30]' in rows[0]['text']
    assert rows[0]['conversation_title'] == 'ISO Chat'
    assert '[Conversation on 14 Aug 2026, 21:30]' in rows[1]['text']
    assert rows[1]['conversation_title'] == 'Timestamp Chat'
