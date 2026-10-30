"""Manual merge: a source without ``started_at`` is ordered by ``created_at``, not forced first.

The sort key fell straight from a missing (or unparseable, normalised to None)
``started_at`` to the year-0001 sentinel, so such a source sorted first whatever
its real time: a conversation created at noon was placed before one recorded at
10:00, became the transcript origin (the 10:00 transcript was appended after it),
and lent the merged conversation its noon ``created_at``.
"""

from datetime import datetime, timezone

from utils.conversations.merge_conversations import (
    _UTC_MIN,
    _merge_order_key,
    _merge_transcript_segments,
    _normalize_conversation_timestamps,
)


def _at(hour, minute=0, second=0):
    return datetime(2026, 5, 30, hour, minute, second, tzinfo=timezone.utc)


def _segment(text):
    return {
        'id': text,
        'text': text,
        'speaker': 'SPEAKER_00',
        'speaker_id': 0,
        'is_user': False,
        'start': 0.0,
        'end': 5.0,
    }


def test_order_key_falls_back_to_created_at_then_sentinel():
    assert _merge_order_key({'started_at': _at(10), 'created_at': _at(12)}) == _at(10)
    assert _merge_order_key({'started_at': None, 'created_at': _at(12)}) == _at(12)
    assert _merge_order_key({'created_at': _at(12).isoformat()}) == _at(12)
    assert _merge_order_key({'started_at': 'not-a-date', 'created_at': None}) == _UTC_MIN
    assert _merge_order_key({}) == _UTC_MIN


def test_source_without_started_at_is_placed_by_its_created_at():
    pendant = {
        'id': 'pendant',
        'created_at': _at(10),
        'started_at': _at(10),
        'finished_at': _at(10, 0, 5),
        'transcript_segments': [_segment('recorded at ten')],
    }
    api = {
        'id': 'api',
        'created_at': _at(12),
        'started_at': None,
        'finished_at': None,
        'transcript_segments': [_segment('created at noon')],
    }

    sorted_convs = sorted(_normalize_conversation_timestamps([api, pendant]), key=_merge_order_key)
    merged = _merge_transcript_segments(sorted_convs)

    assert [conv['id'] for conv in sorted_convs] == ['pendant', 'api']
    assert sorted_convs[0]['created_at'] == _at(10)
    assert [segment['text'] for segment in merged] == ['recorded at ten', 'created at noon']
    assert merged[1]['start'] >= merged[0]['end']


def test_sources_with_neither_timestamp_keep_their_given_order():
    first = {'id': 'a', 'started_at': None, 'finished_at': None, 'transcript_segments': [_segment('a')]}
    second = {'id': 'b', 'started_at': None, 'finished_at': None, 'transcript_segments': [_segment('b')]}

    assert [conv['id'] for conv in sorted([first, second], key=_merge_order_key)] == ['a', 'b']
