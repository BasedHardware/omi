"""Pure placement gate: provenance-aware windows onto stored audio.

No storage, STT or customer data: every case builds plain mappings. A window
is evidence of coordinates only; every refusal must produce no window.
"""

import math
import time
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from utils.conversations.audio_placement import (
    AudioPlacement,
    PreparedAudioCoverage,
    locate,
    locate_in_verified_words,
    prepare_audio_coverage,
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


def _capture_seg(seg_id, start, end, cap_start, cap_end, *, scope='conn:0', **kwargs):
    segment = _seg(seg_id, start, end, scope=scope, **kwargs)
    segment['audio_capture_start'] = cap_start
    segment['audio_capture_end'] = cap_end
    return segment


def _span_files(spans, timestamps=None):
    return [
        {
            'chunk_timestamps': list(timestamps) if timestamps is not None else [s['start'] for s in spans],
            'chunk_spans': list(spans),
        }
    ]


CAP = T + 500.0


def test_locate_capture_span_trusted_inside_validated_coverage():
    conv = _conv(
        [_capture_seg('a', 1.0, 5.0, CAP + 1.0, CAP + 5.0)],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 60}]),
    )
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement((CAP + 1.0, CAP + 5.0), 'capture_span')
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'untrusted_clock')


def test_locate_capture_span_returns_capture_window_not_started_at_projection():
    conv = _conv(
        [_capture_seg('a', 10.0, 14.0, CAP + 10.0, CAP + 14.0)],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 60}]),
    )
    placement = locate(conv, 10.0, 14.0, capture_spans=True)
    assert placement == AudioPlacement((CAP + 10.0, CAP + 14.0), 'capture_span')


@pytest.mark.parametrize('missing', ['audio_capture_start', 'audio_capture_end'])
def test_locate_capture_span_missing_endpoint_refuses(missing):
    segment = _capture_seg('a', 1.0, 5.0, CAP + 1.0, CAP + 5.0)
    segment[missing] = None
    conv = _conv([segment], audio_files=_span_files([{'start': CAP, 'end': CAP + 60}]))
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement(None, 'untrusted_clock')


@pytest.mark.parametrize(
    'cap_start,cap_end',
    [
        (CAP + 5.0, CAP + 1.0),
        (CAP + 1.0, CAP + 1.0),
        (math.nan, CAP + 5.0),
        (CAP + 1.0, math.inf),
        ('text', CAP + 5.0),
        (True, CAP + 5.0),
    ],
)
def test_locate_capture_span_malformed_capture_fields_refuse(cap_start, cap_end):
    conv = _conv(
        [_capture_seg('a', 1.0, 5.0, cap_start, cap_end)],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 60}]),
    )
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement(None, 'untrusted_clock')


def test_locate_capture_span_duration_mismatch_refuses():
    conv = _conv(
        [_capture_seg('a', 1.0, 5.0, CAP + 1.0, CAP + 6.0)],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 60}]),
    )
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement(None, 'untrusted_clock')


def test_locate_capture_span_conflicting_contributor_offsets_refuse():
    conv = _conv(
        [
            _capture_seg('a', 1.0, 3.0, CAP + 1.0, CAP + 3.0),
            _capture_seg('b', 3.0, 5.0, CAP + 4.0, CAP + 6.0),
        ],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 60}]),
    )
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement(None, 'untrusted_clock')


def test_locate_capture_span_contributors_covering_text_window_accept():
    conv = _conv(
        [
            _capture_seg('a', 1.0, 3.0, CAP + 1.0, CAP + 3.0),
            _capture_seg('b', 3.0, 5.0, CAP + 3.0, CAP + 5.0),
        ],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 60}]),
    )
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement((CAP + 1.0, CAP + 5.0), 'capture_span')


def test_locate_capture_span_legacy_spanless_manifest_refuses():
    conv = _conv([_capture_seg('a', 1.0, 5.0, CAP + 1.0, CAP + 5.0)])
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement(None, 'untrusted_clock')


def test_locate_capture_span_mixed_span_and_spanless_manifest_refuses():
    files = _span_files([{'start': CAP, 'end': CAP + 60}]) + [{'chunk_timestamps': [CAP + 60]}]
    conv = _conv([_capture_seg('a', 1.0, 5.0, CAP + 1.0, CAP + 5.0)], audio_files=files)
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement(None, 'untrusted_clock')


def test_locate_capture_span_timestamp_span_mismatch_refuses():
    conv = _conv(
        [_capture_seg('a', 1.0, 5.0, CAP + 1.0, CAP + 5.0)],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 60}], timestamps=[CAP, CAP + 30]),
    )
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement(None, 'untrusted_clock')


def test_locate_capture_span_uncovered_gap_refuses():
    files = _span_files(
        [{'start': CAP, 'end': CAP + 10}, {'start': CAP + 30, 'end': CAP + 60}],
        timestamps=[CAP, CAP + 30],
    )
    conv = _conv([_capture_seg('a', 1.0, 5.0, CAP + 10.5, CAP + 14.5)], audio_files=files)
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement(None, 'untrusted_clock')


@pytest.mark.parametrize('window', [(CAP - 5.0, CAP + 4.0), (CAP + 55.0, CAP + 65.0)])
def test_locate_capture_span_outside_coverage_refuses(window):
    cap_start, cap_end = window
    start, end = 1.0, 1.0 + (cap_end - cap_start)
    conv = _conv(
        [_capture_seg('a', start, end, cap_start, cap_end)],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 60}]),
    )
    assert locate(conv, start, end, capture_spans=True) == AudioPlacement(None, 'untrusted_clock')


def test_locate_capture_span_unplaced_contributor_refuses():
    conv = _conv(
        [_capture_seg('a', 1.0, 5.0, CAP + 1.0, CAP + 5.0, unplaced=True)],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 60}]),
    )
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement(None, 'unplaced')


def test_locate_capture_span_unknown_timeline_marker_still_refuses():
    conv = _conv(
        [_capture_seg('a', 1.0, 5.0, CAP + 1.0, CAP + 5.0)],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 60}]),
        audio_timeline={'version': 9},
    )
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement(None, 'untrusted_clock')


def test_locate_capture_span_v2_still_wins_over_capture_fields():
    conv = _v2_conv(
        [{'start': T, 'end': T + 60}],
        segments=[_capture_seg('a', 1.0, 5.0, CAP + 1.0, CAP + 5.0)],
    )
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement((T + 1.0, T + 5.0), 'v2')


def test_locate_capture_span_sync_scope_still_uses_sync_window():
    segment = _capture_seg('a', 1.0, 5.0, CAP + 1.0, CAP + 5.0, scope='sync:1')
    conv = _conv([segment], audio_files=_span_files([{'start': CAP, 'end': CAP + 60}]))
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement((T + 1.0, T + 5.0), 'sync')


def test_locate_v2_refuses_window_intersecting_overlapping_spans():
    conv = _v2_conv([{'start': T + 100, 'end': T + 112}, {'start': T + 103, 'end': T + 113}])
    assert locate(conv, 104.0, 107.8) == AudioPlacement(None, 'uncovered_audio')


def test_locate_v2_refuses_nested_containing_overlap():
    conv = _v2_conv([{'start': T, 'end': T + 60}, {'start': T + 10, 'end': T + 20}])
    assert locate(conv, 11.0, 15.0) == AudioPlacement(None, 'uncovered_audio')


def test_locate_v2_refuses_identical_duplicate_spans():
    conv = _v2_conv([{'start': T, 'end': T + 60}, {'start': T, 'end': T + 60}])
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'uncovered_audio')


def test_locate_v2_refuses_more_than_two_overlapping_spans():
    conv = _v2_conv([{'start': T, 'end': T + 10}, {'start': T + 5, 'end': T + 15}, {'start': T + 12, 'end': T + 30}])
    assert locate(conv, 13.0, 14.0) == AudioPlacement(None, 'uncovered_audio')


def test_locate_v2_touching_half_open_boundaries_still_accept():
    conv = _v2_conv([{'start': T, 'end': T + 10}, {'start': T + 10, 'end': T + 20}])
    assert locate(conv, 1.0, 5.0) == AudioPlacement((T + 1.0, T + 5.0), 'v2')
    assert locate(conv, 11.0, 15.0) == AudioPlacement((T + 11.0, T + 15.0), 'v2')


def test_locate_v2_windows_disjoint_from_ambiguity_still_place():
    conv = _v2_conv([{'start': T, 'end': T + 10}, {'start': T + 5, 'end': T + 15}])
    assert locate(conv, 1.0, 4.0) == AudioPlacement((T + 1.0, T + 4.0), 'v2')
    assert locate(conv, 10.5, 13.0) == AudioPlacement((T + 10.5, T + 13.0), 'v2')
    assert locate(conv, 4.5, 5.5) == AudioPlacement(None, 'uncovered_audio')


def test_locate_capture_span_refuses_window_in_span_overlap():
    conv = _conv(
        [_capture_seg('a', 1.0, 5.0, CAP + 4.0, CAP + 8.0)],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 12}, {'start': CAP + 3, 'end': CAP + 13}]),
    )
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement(None, 'untrusted_clock')


def test_locate_capture_span_window_disjoint_from_overlap_still_trusted():
    conv = _conv(
        [_capture_seg('a', 1.0, 3.5, CAP + 0.5, CAP + 3.0)],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 12}, {'start': CAP + 6, 'end': CAP + 13}]),
    )
    assert locate(conv, 1.0, 3.5, capture_spans=True) == AudioPlacement((CAP + 0.5, CAP + 3.0), 'capture_span')


def test_locate_capture_span_identical_spans_are_ambiguous_not_equivalent():
    conv = _conv(
        [_capture_seg('a', 1.0, 5.0, CAP + 1.0, CAP + 5.0)],
        audio_files=_span_files([{'start': CAP, 'end': CAP + 60}, {'start': CAP, 'end': CAP + 60}]),
    )
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement(None, 'untrusted_clock')


def test_prepare_audio_coverage_validates_and_indexes_once():
    files = _span_files(
        [{'start': T + 100, 'end': T + 112}, {'start': T + 103, 'end': T + 113}, {'start': T + 200, 'end': T + 210}]
    )
    prepared = prepare_audio_coverage(files)
    assert prepared.validated
    assert prepared.coverage == ((T + 100.0, T + 113.0), (T + 200.0, T + 210.0))
    assert prepared.ambiguity == ((T + 103.0, T + 112.0),)
    assert prepared.covers(T + 104.0, T + 107.8)
    assert prepared.ambiguous(T + 104.0, T + 107.8)
    assert not prepared.ambiguous(T + 113.5, T + 114.0)


@pytest.mark.parametrize(
    'files',
    [
        [{'chunk_timestamps': [T], 'chunk_spans': [{'start': T + 5, 'end': T}]}],
        [{'chunk_timestamps': [T], 'chunk_spans': [{'start': T}]}],
        [{'chunk_timestamps': [T, T + 1], 'chunk_spans': [{'start': T, 'end': T + 1}]}],
        [{'chunk_timestamps': 'x', 'chunk_spans': [{'start': T, 'end': T + 1}]}],
        'not-files',
        [],
    ],
)
def test_prepare_audio_coverage_invalid_manifest_is_not_validated(files):
    prepared = prepare_audio_coverage(files)
    assert not prepared.validated
    assert prepared.coverage == ()
    assert prepared.ambiguity == ()


def test_prepare_audio_coverage_bounds_never_yield_a_partial_index():
    files = _span_files(
        [{'start': T + 100, 'end': T + 112}, {'start': T + 103, 'end': T + 113}, {'start': T + 200, 'end': T + 210}]
    )
    assert prepare_audio_coverage(files, max_spans=2) == PreparedAudioCoverage(validated=False)
    expired = prepare_audio_coverage(files, deadline=time.monotonic() - 1.0)
    assert expired == PreparedAudioCoverage(validated=False)
    prepared = prepare_audio_coverage(files, deadline=time.monotonic() + 60.0, max_spans=3)
    assert prepared.validated
    assert len(prepared.coverage) == 2


def test_prepare_audio_coverage_deadline_expiring_during_sweep_is_unvalidated(monkeypatch):
    """Every bound validated; the sweep's first union step then hits the
    deadline — the index must come back unvalidated, not half-built."""
    files = _span_files(
        [{'start': T + 100, 'end': T + 112}, {'start': T + 103, 'end': T + 113}, {'start': T + 200, 'end': T + 210}]
    )
    ticks = iter(range(100))
    monkeypatch.setattr(time, 'monotonic', lambda: next(ticks))
    prepared = prepare_audio_coverage(files, deadline=5.5)
    assert prepared == PreparedAudioCoverage(validated=False)

    ticks = iter(range(100))
    prepared = prepare_audio_coverage(files, deadline=60.0)
    assert prepared.validated
    assert prepared.ambiguity == ((T + 103.0, T + 112.0),)


def test_locate_accepts_a_prepared_coverage_index():
    files = _span_files([{'start': T + 100, 'end': T + 112}, {'start': T + 103, 'end': T + 113}])
    prepared = prepare_audio_coverage(files)
    conv = _v2_conv([{'start': T + 100, 'end': T + 112}, {'start': T + 103, 'end': T + 113}])
    assert locate(conv, 104.0, 107.8, coverage=prepared) == AudioPlacement(None, 'uncovered_audio')
    assert locate(conv, 112.5, 113.0, coverage=prepared) == AudioPlacement((T + 112.5, T + 113.0), 'v2')


def test_locate_saved_sync_source_is_trusted_like_a_sync_scope():
    segment = _seg('a', 1.0, 5.0, scope='conversation:c1')
    segment['audio_source'] = {'type': 'sync', 'start': T + 1.0, 'end': T + 5.0}
    conv = _conv([segment])
    assert locate(conv, 1.0, 5.0) == AudioPlacement((T + 1.0, T + 5.0), 'sync')


def test_locate_saved_sync_source_survives_rebased_offsets():
    segment = _seg('a', 301.0, 305.0, scope='legacy-conversation:d1:0')
    segment['audio_source'] = {'type': 'sync', 'start': T + 301.0, 'end': T + 305.0}
    conv = _conv([segment])
    assert locate(conv, 301.0, 305.0) == AudioPlacement((T + 301.0, T + 305.0), 'sync')


@pytest.mark.parametrize(
    'source',
    [
        {'type': 'other', 'start': T + 1.0, 'end': T + 5.0},
        {'type': 'sync', 'start': T + 2.0, 'end': T + 5.0},
        {'type': 'sync', 'start': T + 1.0, 'end': T + 6.0},
        {'type': 'sync', 'start': 'x', 'end': T + 5.0},
        {'type': 'sync', 'start': T + 5.0, 'end': T + 1.0},
        {'type': 'sync'},
        'sync',
        [{'type': 'sync', 'start': T + 1.0, 'end': T + 5.0}],
    ],
)
def test_locate_saved_sync_source_malformed_or_retimed_refuses(source):
    segment = _seg('a', 1.0, 5.0, scope='conversation:c1')
    segment['audio_source'] = source
    conv = _conv([segment])
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'untrusted_clock')


def test_locate_own_scope_without_source_stays_untrusted():
    conv = _conv([_seg('a', 1.0, 5.0, scope='conversation:c1')])
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'untrusted_clock')


def test_locate_live_capture_fields_alone_are_not_sync_provenance():
    segment = _capture_seg('a', 1.0, 5.0, CAP + 1.0, CAP + 5.0, scope='conversation:c1')
    conv = _conv([segment], audio_files=_span_files([{'start': CAP, 'end': CAP + 60}]))
    assert locate(conv, 1.0, 5.0) == AudioPlacement(None, 'untrusted_clock')
    assert locate(conv, 1.0, 5.0, capture_spans=True) == AudioPlacement((CAP + 1.0, CAP + 5.0), 'capture_span')


def test_locate_saved_sync_source_in_ambiguous_manifest_refuses():
    segment = _seg('a', 104.0, 110.0, scope='conversation:c1')
    segment['audio_source'] = {'type': 'sync', 'start': T + 104.0, 'end': T + 110.0}
    conv = _conv(
        [segment],
        audio_files=_span_files([{'start': T + 100, 'end': T + 112}, {'start': T + 103, 'end': T + 113}]),
    )
    index = prepare_audio_coverage(conv['audio_files'])
    assert locate(conv, 104.0, 110.0, coverage=index) == AudioPlacement(None, 'untrusted_clock')
    assert locate(conv, 104.0, 110.0) == AudioPlacement(None, 'untrusted_clock')
    disjoint = _seg('b', 4.0, 7.8, scope='conversation:c1')
    disjoint['audio_source'] = {'type': 'sync', 'start': T + 4.0, 'end': T + 7.8}
    assert locate(conv, 4.0, 7.8, segments=[disjoint], coverage=index) == AudioPlacement((T + 4.0, T + 7.8), 'sync')


def test_locate_mixed_saved_source_and_sync_scope_union_covers():
    first = _seg('a', 0.0, 6.0, scope='sync:1')
    second = _seg('b', 6.0, 12.0, scope='conversation:c1')
    second['audio_source'] = {'type': 'sync', 'start': T + 6.0, 'end': T + 12.0}
    conv = _conv([first, second])
    assert locate(conv, 1.0, 11.0) == AudioPlacement((T + 1.0, T + 11.0), 'sync')


def test_locate_saved_source_gap_in_coverage_is_untrusted():
    first = _seg('a', 0.0, 3.0, scope='conversation:c1')
    first['audio_source'] = {'type': 'sync', 'start': T, 'end': T + 3.0}
    second = _seg('b', 5.0, 8.0, scope='conversation:c1')
    second['audio_source'] = {'type': 'sync', 'start': T + 5.0, 'end': T + 8.0}
    conv = _conv([first, second])
    assert locate(conv, 1.0, 7.0) == AudioPlacement(None, 'untrusted_clock')


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
