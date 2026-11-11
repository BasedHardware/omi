"""Regression: manual merge must re-base donor segments on the first clock.

The stored audio stays on each source's absolute clock; the legacy arithmetic
(prior transcript tail plus the wall gap) rebased donor segments onto the
*transcript* tail instead of the merged conversation's origin, so merged
segments pointed at the wrong audio.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from utils.conversations.merge_conversations import _merge_transcript_segments

T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _conv(started_at, finished_at=None, segments=()):
    return {
        'id': 'c',
        'started_at': started_at,
        'finished_at': finished_at,
        'transcript_segments': list(segments),
    }


def _seg(start, end):
    return {'start': start, 'end': end, 'text': 'w'}


def test_trailing_silence_does_not_collapse_donor_onto_transcript_tail():
    first = _conv(T, T + timedelta(seconds=100), [_seg(0, 10)])
    donor = _conv(T + timedelta(seconds=110), T + timedelta(seconds=120), [_seg(0, 5)])
    merged = _merge_transcript_segments([first, donor])
    assert merged[1]['start'] == 110
    assert merged[1]['end'] == 115
    assert merged[1]['start'] != 20, 'legacy fallback would park the donor right after segment end'


def test_overlapping_source_keeps_its_own_clock():
    first = _conv(T, T + timedelta(seconds=100), [_seg(0, 100)])
    donor = _conv(T + timedelta(seconds=5), T + timedelta(seconds=50), [_seg(0, 5)])
    merged = _merge_transcript_segments([first, donor])
    assert merged[1]['start'] == 5
    assert merged[1]['end'] == 10
    assert merged[1]['start'] != 100


def test_three_donor_chain_uses_direct_origins():
    first = _conv(T, T + timedelta(seconds=100), [_seg(0, 10)])
    second = _conv(T + timedelta(seconds=50), T + timedelta(seconds=90), [_seg(0, 5)])
    third = _conv(T + timedelta(seconds=200), T + timedelta(seconds=210), [_seg(0, 7)])
    merged = _merge_transcript_segments([first, second, third])
    assert (merged[1]['start'], merged[1]['end']) == (50, 55)
    assert (merged[2]['start'], merged[2]['end']) == (200, 207)


def test_first_conversation_without_segments_still_uses_clock():
    first = _conv(T, T + timedelta(seconds=100), [])
    donor = _conv(T + timedelta(seconds=110), T + timedelta(seconds=120), [_seg(0, 5)])
    merged = _merge_transcript_segments([first, donor])
    assert (merged[0]['start'], merged[0]['end']) == (110, 115)


def test_missing_origin_falls_back_to_legacy_arithmetic():
    first = {'id': 'a', 'started_at': None, 'finished_at': None, 'transcript_segments': [_seg(0, 10)]}
    donor = _conv(T + timedelta(seconds=110), T + timedelta(seconds=120), [_seg(0, 5)])
    merged = _merge_transcript_segments([first, donor])
    assert (merged[1]['start'], merged[1]['end']) == (10, 15)


def test_inputs_are_not_mutated_and_invariant_holds():
    first = _conv(T, T + timedelta(seconds=100), [_seg(0, 10)])
    donor = _conv(T + timedelta(seconds=110), T + timedelta(seconds=120), [_seg(0, 5), _seg(6, 9)])
    before = deepcopy([first, donor])
    merged = _merge_transcript_segments([first, donor])
    assert [first, donor] == before
    for source_seg, merged_seg in zip(before[1]['transcript_segments'], merged[1:]):
        shift = (before[1]['started_at'] - before[0]['started_at']).total_seconds()
        assert merged_seg['start'] == source_seg['start'] + shift
        assert merged_seg['end'] == source_seg['end'] + shift
