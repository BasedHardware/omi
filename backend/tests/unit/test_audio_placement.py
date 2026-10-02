"""Pure placement gate: provenance-aware windows onto stored audio.

No storage, STT or customer data: every case builds plain mappings. A window
is evidence of coordinates only; every refusal must produce no window.
"""

import math
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from utils.conversations.audio_placement import (
    AudioPlacement,
    locate,
    locate_in_verified_words,
    provisional_window,
)
from utils.speaker_tag_prompts import clips

T = 1_700_000_000.0


def _seg(seg_id, start, end, *, scope=None, unplaced=False, text='words'):
    segment = {'id': seg_id, 'start': start, 'end': end, 'text': text}
    if scope is not None:
        segment['speaker_id_scope'] = scope
    if unplaced:
        segment['audio_alignment'] = 'unplaced'
    return segment


def _conv(segments=(), *, started_at=T, audio_files=None, **extra):
    conversation = {
        'id': 'c1',
        'started_at': started_at,
        'transcript_segments': list(segments),
        'audio_files': audio_files if audio_files is not None else [{'chunk_timestamps': [T]}],
    }
    conversation.update(extra)
    return conversation


def _v2_conv(spans, *, started_at=T, timestamps=None, segments=()):
    files = [
        {
            'chunk_timestamps': list(timestamps) if timestamps is not None else [s['start'] for s in spans],
            'chunk_spans': list(spans),
        }
    ]
    return _conv(segments, started_at=started_at, audio_files=files, audio_timeline={'version': 2})


def test_provisional_window_accepts_datetime_iso_and_numeric_origins():
    aware = datetime.fromtimestamp(T, tz=timezone.utc)
    assert provisional_window(_conv(started_at=aware), 1.0, 3.0) == (T + 1.0, T + 3.0)
    assert provisional_window(_conv(started_at='2023-11-14T22:13:20Z'), 1.0, 3.0) == (T + 1.0, T + 3.0)
    assert provisional_window(_conv(started_at=datetime.utcfromtimestamp(T)), 1.0, 3.0) == (T + 1.0, T + 3.0)
    assert provisional_window(_conv(started_at=T), 1.0, 3.0) == (T + 1.0, T + 3.0)


def test_provisional_window_falls_back_to_created_at():
    conv = {'id': 'c1', 'created_at': T, 'transcript_segments': []}
    assert provisional_window(conv, 2.0, 4.0) == (T + 2.0, T + 4.0)


@pytest.mark.parametrize(
    'started_at,start,end',
    [
        (True, 1.0, 2.0),
        (T, True, 2.0),
        (T, 1.0, True),
        (T, math.nan, 2.0),
        (T, 1.0, math.inf),
        (math.inf, 1.0, 2.0),
        (math.nan, 1.0, 2.0),
        (T, -0.5, 2.0),
        (T, 5.0, 5.0),
        (T, 5.0, 4.0),
        ('not-a-date', 1.0, 2.0),
        (None, 1.0, 2.0),
        (1e308, 1e308, 1.5e308),
        (1e308, 1.0, 2.0),
        (10**400, 1.0, 2.0),
    ],
)
def test_provisional_window_rejects_bad_inputs(started_at, start, end):
    assert provisional_window(_conv(started_at=started_at), start, end) is None


def test_provisional_window_refuses_invalid_started_at_despite_created_at():
    conv = {'id': 'c1', 'started_at': 'not-a-date', 'created_at': T, 'transcript_segments': []}
    assert provisional_window(conv, 1.0, 2.0) is None
    conv['started_at'] = ''
    assert provisional_window(conv, 1.0, 2.0) == (T + 1.0, T + 2.0)


def test_locate_v2_covered_returns_window():
    conv = _v2_conv([{'start': T, 'end': T + 60}])
    placement = locate(conv, 5.0, 10.0)
    assert placement == AudioPlacement((T + 5.0, T + 10.0), 'v2')


def test_locate_v2_gap_is_uncovered():
    conv = _v2_conv(
        [{'start': T, 'end': T + 10}, {'start': T + 30, 'end': T + 60}],
        timestamps=[T, T + 30],
    )
    assert locate(conv, 5.0, 35.0) == AudioPlacement(None, 'uncovered_audio')
    placement = locate(conv, 15.0, 20.0)
    assert placement == AudioPlacement(None, 'uncovered_audio')


def test_locate_v2_covered_window_over_twelve_seconds_returns_window():
    conv = _v2_conv([{'start': T, 'end': T + 60}])
    assert locate(conv, 0.0, 30.0) == AudioPlacement((T, T + 30.0), 'v2')


def test_locate_v2_malformed_manifest_refuses():
    conv = _v2_conv([{'start': T, 'end': T + 60}], timestamps=[T, T + 10])
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'uncovered_audio')
    bad_span = _v2_conv([{'start': T}])
    assert locate(bad_span, 1.0, 5.0) == AudioPlacement(None, 'uncovered_audio')
    no_spans = _conv(audio_timeline={'version': 2}, audio_files=[{'chunk_timestamps': [T]}])
    assert locate(no_spans, 1.0, 5.0) == AudioPlacement(None, 'uncovered_audio')
    scalar_files = _conv(audio_timeline={'version': 2}, audio_files=1)
    assert locate(scalar_files, 1.0, 5.0) == AudioPlacement(None, 'uncovered_audio')
    str_spans = _conv(audio_timeline={'version': 2}, audio_files=[{'chunk_spans': 'x', 'chunk_timestamps': [T]}])
    assert locate(str_spans, 1.0, 5.0) == AudioPlacement(None, 'uncovered_audio')
    nan_ts = _v2_conv([{'start': T, 'end': T + 60}], timestamps=[math.nan])
    assert locate(nan_ts, 1.0, 5.0) == AudioPlacement(None, 'uncovered_audio')
    bool_ts = _v2_conv([{'start': T, 'end': T + 60}], timestamps=[True])
    assert locate(bool_ts, 1.0, 5.0) == AudioPlacement(None, 'uncovered_audio')


def test_locate_malformed_v2_marker_gets_no_trust():
    conv = _conv(audio_timeline={'version': '2'})
    assert locate(conv, 1.0, 5.0).reason == 'untrusted_clock'
    conv = _conv(audio_timeline='v2')
    assert locate(conv, 1.0, 5.0).reason == 'untrusted_clock'
    conv = _conv([_seg('a', 0.0, 10.0, scope='sync:1')], audio_timeline={'version': 9})
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'untrusted_clock')


def test_locate_sync_scope_covering_union_is_trusted():
    conv = _conv([_seg('a', 0.0, 6.0, scope='sync:1'), _seg('b', 6.0, 12.0, scope='sync:2')])
    assert locate(conv, 1.0, 5.0) == AudioPlacement((T + 1.0, T + 5.0), 'sync')
    assert locate(conv, 1.0, 11.0) == AudioPlacement((T + 1.0, T + 11.0), 'sync')


@pytest.mark.parametrize('scope', ['rt-abc:0', 'legacy-conversation:d1:0', 'conversation:c1', 'sync:', None])
def test_locate_non_sync_scopes_are_untrusted(scope):
    conv = _conv([_seg('a', 0.0, 10.0, scope=scope)])
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'untrusted_clock')


def test_locate_mixed_sync_and_live_scopes_are_untrusted():
    conv = _conv([_seg('a', 0.0, 6.0, scope='sync:1'), _seg('b', 6.0, 12.0, scope='live:0')])
    assert locate(conv, 1.0, 11.0) == AudioPlacement(None, 'untrusted_clock')


def test_locate_sync_gap_in_coverage_is_untrusted():
    conv = _conv([_seg('a', 0.0, 3.0, scope='sync:1'), _seg('b', 5.0, 8.0, scope='sync:1')])
    assert locate(conv, 1.0, 7.0) == AudioPlacement(None, 'untrusted_clock')


def test_locate_no_contributors_is_untrusted():
    conv = _conv([_seg('a', 50.0, 60.0, scope='sync:1')])
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'untrusted_clock')


def test_locate_explicit_unplaced_contributor_refuses_even_v2():
    conv = _v2_conv([{'start': T, 'end': T + 60}])
    contributors = [_seg('a', 0.0, 10.0, scope='sync:1', unplaced=True)]
    assert locate(conv, 1.0, 5.0, segments=contributors) == AudioPlacement(None, 'unplaced')
    legacy = _conv()
    assert locate(legacy, 1.0, 5.0, segments=contributors) == AudioPlacement(None, 'unplaced')


def test_locate_inferred_unplaced_contributor_refuses():
    conv = _conv([_seg('a', 2.0, 8.0, scope='sync:1', unplaced=True)])
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'unplaced')
    conv = _v2_conv([{'start': T, 'end': T + 60}], segments=[_seg('a', 2.0, 8.0, unplaced=True)])
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'unplaced')
    point = _conv([_seg('a', 3.0, 3.0, unplaced=True)])
    assert locate(point, 1.0, 5.0) == AudioPlacement(None, 'unplaced')
    outside = _conv([_seg('a', -1.0, -1.0, unplaced=True), _seg('b', 0.0, 10.0, scope='sync:1')])
    assert locate(outside, 1.0, 5.0) == AudioPlacement((T + 1.0, T + 5.0), 'sync')


@pytest.mark.parametrize('start,end', [(5.0, 2.0), (4.0, 4.0), (-2.0, 4.0)])
def test_locate_explicit_bad_interval_contributor_is_unplaced(start, end):
    contributors = [_seg('a', start, end, scope='sync:1')]
    assert locate(_conv(), 1.0, 5.0, segments=contributors) == AudioPlacement(None, 'unplaced')


def test_locate_requires_real_started_at():
    conv = {'id': 'c1', 'created_at': T, 'transcript_segments': [_seg('a', 0.0, 10.0, scope='sync:1')]}
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'missing_origin')
    conv = _conv(started_at=None)
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'missing_origin')


@pytest.mark.parametrize('start,end', [(-1.0, 5.0), (5.0, 5.0), (6.0, 5.0), (math.nan, 5.0)])
def test_locate_invalid_window(start, end):
    assert locate(_conv(), start, end) == AudioPlacement(None, 'invalid_window')


def test_locate_collapsed_epoch_window_is_invalid():
    conv = _conv([_seg('a', 0.0, 10.0, scope='sync:1')], started_at=1e308)
    assert locate(conv, 1.0, 2.0) == AudioPlacement(None, 'invalid_window')
    conv = _conv([_seg('a', 0.0, 10.0, scope='sync:1')], started_at=10**400)
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'missing_origin')


def test_locate_does_not_mutate_inputs():
    segments = [_seg('a', 0.0, 6.0, scope='sync:1')]
    conv = _conv(segments)
    before = deepcopy(conv)
    locate(conv, 1.0, 5.0)
    locate(conv, 1.0, 5.0, segments=segments)
    assert conv == before


def test_clips_v2_iso_started_at_matches_numeric(monkeypatch):
    spans = [{'start': T, 'end': T + 60}]
    base = {
        'id': 'c1',
        'audio_timeline': {'version': 2},
        'audio_files': [{'chunk_timestamps': [T], 'chunk_spans': spans}],
        'transcript_segments': [],
        'private_cloud_sync_enabled': True,
    }
    pcm60 = bytes((i % 251 for i in range(60 * clips.CLIP_SAMPLE_RATE * 2)))
    monkeypatch.setattr(clips, 'download_audio_chunks_and_merge', lambda *a, **k: pcm60)
    expected = pcm60[5 * clips.CLIP_SAMPLE_RATE * 2 : 10 * clips.CLIP_SAMPLE_RATE * 2]
    numeric = clips.conversation_clip_pcm('u', {**base, 'started_at': T}, 5.0, 10.0)
    iso = clips.conversation_clip_pcm('u', {**base, 'started_at': '2023-11-14T22:13:20Z'}, 5.0, 10.0)
    aware = clips.conversation_clip_pcm(
        'u', {**base, 'started_at': datetime.fromtimestamp(T, tz=timezone.utc)}, 5.0, 10.0
    )
    assert numeric == iso == aware == expected


def test_clips_never_reads_a_known_unplaced_window(monkeypatch):
    def banned(*args, **kwargs):
        raise AssertionError('reader must not run for an unplaced window')

    conv = _conv([_seg('a', 2.0, 8.0, unplaced=True)])
    monkeypatch.setattr(clips, 'legacy_speaker_clip_pcm', banned)
    assert clips.conversation_clip_pcm('u', conv, 1.0, 5.0) is None
    v2 = _v2_conv([{'start': T, 'end': T + 60}], segments=[_seg('a', 2.0, 8.0, unplaced=True)])
    monkeypatch.setattr(clips, 'download_audio_chunks_and_merge', banned)
    assert clips.conversation_clip_pcm('u', v2, 1.0, 5.0) is None


def _words(texts, first=0.0, step=0.5):
    return [
        {'timestamp': [first + i * step, first + i * step + step * 0.9], 'text': text, 'speaker': 'SPEAKER_00'}
        for i, text in enumerate(texts)
    ]


EXPECTED = 'alpha bravo charlie delta echo foxtrot golf'


def test_anchor_finds_exact_shifted_prefix():
    words = _words(EXPECTED.split(), first=5.0)
    placement = locate_in_verified_words(EXPECTED, words, 10.0, audio_duration=30.0)
    assert placement == AudioPlacement((5.0, 15.0), 'text_anchor')


def test_anchor_offset_shifts_the_proposed_window():
    words = _words(EXPECTED.split(), first=5.0)
    placement = locate_in_verified_words(EXPECTED, words, 10.0, audio_duration=30.0, anchor_offset=0.4)
    assert placement == AudioPlacement((5.4, 15.4), 'text_anchor')


def test_repeated_prefix_is_ambiguous():
    words = _words(EXPECTED.split(), first=5.0) + _words(EXPECTED.split(), first=15.0)
    assert locate_in_verified_words(EXPECTED, words, 5.0, audio_duration=30.0) == AudioPlacement(
        None, 'ambiguous_text_anchor'
    )


def test_short_expected_text_and_short_word_list_are_insufficient():
    words = _words(EXPECTED.split())
    assert locate_in_verified_words('alpha bravo', words, 5.0, audio_duration=30.0) == AudioPlacement(
        None, 'insufficient_anchor'
    )
    assert locate_in_verified_words(EXPECTED, words[:4], 5.0, audio_duration=30.0) == AudioPlacement(
        None, 'insufficient_anchor'
    )


def test_word_cap_rejects_over_512_entries():
    words = _words(EXPECTED.split() * 74)
    assert len(words) > 512
    assert locate_in_verified_words(EXPECTED, words, 5.0, audio_duration=300.0) == AudioPlacement(
        None, 'invalid_window'
    )
    small_words = _words(EXPECTED.split() * 74, first=0.0, step=0.05)
    assert locate_in_verified_words(EXPECTED, small_words, 5.0, audio_duration=30.0) == AudioPlacement(
        None, 'unsupported_word_times'
    )


@pytest.mark.parametrize(
    'word',
    [
        {'timestamp': '1-2', 'text': 'alpha'},
        {'timestamp': [1.0], 'text': 'alpha'},
        {'timestamp': [1.0, 2.0, 3.0], 'text': 'alpha'},
        {'timestamp': [2.0, 1.0], 'text': 'alpha'},
        {'timestamp': [-1.0, 2.0], 'text': 'alpha'},
        {'timestamp': [1.0, math.inf], 'text': 'alpha'},
        {'timestamp': [1.0, 99.0], 'text': 'alpha'},
        {'timestamp': [1.0, 2.0], 'text': 'alpha beta'},
        {'timestamp': [1.0, 2.0], 'text': ''},
        {'timestamp': [True, 2.0], 'text': 'alpha'},
        {'text': 'alpha'},
        {'timestamp': [1.0, 2.0]},
    ],
)
def test_malformed_and_segment_granular_words_refuse(word):
    words = _words(EXPECTED.split())
    words[2] = word
    assert locate_in_verified_words(EXPECTED, words, 5.0, audio_duration=30.0) == AudioPlacement(
        None, 'unsupported_word_times'
    )


def test_non_monotonic_starts_refuse():
    words = _words(EXPECTED.split())
    words[3]['timestamp'] = [0.01, 0.4]
    assert locate_in_verified_words(EXPECTED, words, 5.0, audio_duration=30.0) == AudioPlacement(
        None, 'unsupported_word_times'
    )


def test_candidate_past_audio_end_is_not_accepted():
    words = _words(EXPECTED.split(), first=25.0)
    assert locate_in_verified_words(EXPECTED, words, 10.0, audio_duration=30.0) == AudioPlacement(
        None, 'text_anchor_missing'
    )


def test_no_matching_prefix_is_missing_not_ambiguous():
    words = _words(['different'] * 7)
    assert locate_in_verified_words(EXPECTED, words, 5.0, audio_duration=30.0) == AudioPlacement(
        None, 'text_anchor_missing'
    )


def test_containment_gate_rejects_foreign_tail():
    words = _words(['alpha', 'bravo', 'charlie', 'delta', 'echo', 'utterly', 'unrelated'])
    placement = locate_in_verified_words(EXPECTED, words, 4.0, audio_duration=30.0)
    assert placement == AudioPlacement(None, 'text_anchor_missing')


def test_cropped_window_from_anchor_offset_still_validates_bounds():
    words = _words(EXPECTED.split(), first=28.0)
    placement = locate_in_verified_words(EXPECTED, words, 6.0, audio_duration=32.0, anchor_offset=-1.0)
    assert placement.reason == 'invalid_window'
    words = _words(EXPECTED.split(), first=26.0)
    placement = locate_in_verified_words(EXPECTED, words, 10.0, audio_duration=32.0, anchor_offset=0.0)
    assert placement == AudioPlacement(None, 'text_anchor_missing')


@pytest.mark.parametrize(
    'duration,audio_duration,anchor_offset',
    [
        (0.0, 30.0, 0.0),
        (-1.0, 30.0, 0.0),
        (13.0, 30.0, 0.0),
        (math.inf, 30.0, 0.0),
        (5.0, 0.0, 0.0),
        (5.0, 33.0, 0.0),
        (5.0, math.nan, 0.0),
        (5.0, 30.0, -0.5),
        (5.0, 30.0, math.inf),
    ],
)
def test_anchor_parameter_validation(duration, audio_duration, anchor_offset):
    words = _words(EXPECTED.split())
    assert locate_in_verified_words(
        EXPECTED, words, duration, audio_duration=audio_duration, anchor_offset=anchor_offset
    ) == AudioPlacement(None, 'invalid_window')
