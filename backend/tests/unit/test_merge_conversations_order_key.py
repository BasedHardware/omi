"""Merge ordering: a source with no started_at orders by created_at.

API or integration-created conversations can lack started_at entirely.
Without a fallback they sink to the year-0001 sentinel and merge first
regardless of when they happened — scrambling the transcript and stamping
the merged conversation with the wrong created_at.
"""

from datetime import datetime, timezone

from utils.conversations.merge_conversations import (
    _merge_order_key, _merge_transcript_segments, _normalize_conversation_timestamps)

T = lambda h, m=0, s=0: datetime(2026, 5, 30, h, m, s, tzinfo=timezone.utc)
_SEG = lambda text: {'id': text, 'text': text, 'speaker': 'SPEAKER_00',
                     'speaker_id': 0, 'is_user': False, 'start': 0.0, 'end': 5.0}


def _convs():
    pendant = {'id': 'pendant', 'created_at': T(10), 'started_at': T(10),
               'finished_at': T(10, 0, 5), 'transcript_segments': [_SEG('recorded at ten')]}
    api = {'id': 'api', 'created_at': T(12), 'started_at': None,
           'finished_at': None, 'transcript_segments': [_SEG('created at noon')]}
    return pendant, api


def test_order_key_falls_back_to_created_at():
    pendant, api = _convs()
    assert _merge_order_key(pendant) < _merge_order_key(api)


def test_order_key_keeps_sentinel_without_timestamps():
    conv = {'id': 'legacy', 'created_at': None, 'started_at': None}
    from utils.conversations.merge_conversations import _UTC_MIN
    assert _merge_order_key(conv) == _UTC_MIN


def test_merge_places_untimed_source_chronologically():
    pendant, api = _convs()
    convs = sorted(_normalize_conversation_timestamps([api, pendant]),
                   key=_merge_order_key)
    assert [c['id'] for c in convs] == ['pendant', 'api']
    assert convs[0]['created_at'] == T(10)
    assert [s['text'] for s in _merge_transcript_segments(convs)] == [
        'recorded at ten', 'created at noon']
