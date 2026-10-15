"""Lexical repeat coverage for safety-WAL segments bound to a live row.

``drop_covered_repeats`` drops an incoming segment only when its index is
independently capture-proven (``verified_capture_indices``) AND a bounded live
window lexically covers every substantive incoming token; every ambiguity is
kept. Clock truth: the live capture fields when present, otherwise the row
origin plus stored offsets — a content window, faithful capture when the v2
pin is set. All text is synthetic.
"""

import pytest

from utils.sync import live_speech_dedupe
from utils.sync.live_speech_dedupe import (
    bounded_span_seconds,
    drop_covered_repeats,
    drop_exact_retries,
    drop_proven_exact_retries,
)

ORIGIN = 1_800_000_000.0

LIVE = [
    'the quarterly planning review meeting covered agenda item one in detail',
    'the quarterly planning review meeting covered agenda item two in detail',
    'the quarterly planning review meeting covered agenda item three in detail',
    'the quarterly planning review meeting covered agenda item four in detail',
    'the quarterly planning review meeting covered agenda item five in detail',
    'the quarterly planning review meeting covered agenda item six in detail',
    'the quarterly planning review meeting covered agenda item seven in detail',
]


def live_segment(index, text=None, **extra):
    segment = {'start': index * 10.0, 'end': index * 10.0 + 9.5, 'text': text or LIVE[index], 'speaker_id': 0}
    segment.update(extra)
    return segment


def live_row_segments(**per_segment):
    return [live_segment(i, **per_segment) for i in range(len(LIVE))]


def incoming(text, start, duration=9.5):
    return {'start': start, 'end': start + duration, 'timestamp': ORIGIN + start, 'text': text}


def reworded(text):
    words = [token for token in text.replace('the ', '').split(' ') if token]
    return 'Um, ' + ' '.join(words).capitalize() + '!'


def proven(incoming_segments):
    return frozenset(range(min(len(incoming_segments), 64)))


def drop(incoming_segments, live=None, verified=None, **kwargs):
    if verified is None:
        verified = proven(incoming_segments)
    return drop_covered_repeats(
        incoming_segments,
        live_row_segments() if live is None else live,
        live_origin=ORIGIN,
        live_pinned=False,
        verified_capture_indices=verified,
    )


def test_reworded_repeat_is_dropped_new_speech_is_kept():
    repeats = [incoming(reworded(LIVE[i]), i * 10.0 + 40) for i in range(3)]
    fresh = incoming('a genuinely new remark about weekend hiking plans with friends', 35.0 + 40)
    kept, report = drop(repeats + [fresh])
    assert kept == [fresh]
    assert report['dropped_seconds'] == 28.5
    assert report['alignment_method'] == 'source_frame_lexical'
    assert report['repeat_only'] is False


def test_entirely_covered_upload_reports_repeat_only():
    repeats = [incoming(reworded(LIVE[i]), i * 10.0 + 40) for i in range(3)]
    kept, report = drop(repeats)
    assert kept == [] and report['repeat_only'] is True


def test_unproven_identical_and_reworded_second_utterance_is_kept():
    """Without independent capture proof the same words are legitimate repetition."""
    incoming_segments = [incoming(LIVE[0], 40.0), incoming(reworded(LIVE[1]), 50.0)]
    kept, report = drop(incoming_segments, verified=frozenset())
    assert kept == incoming_segments
    assert report['dropped_segments'] == 0 and report['evaluated_segments'] == 0
    assert report['alignment_method'] == 'none' and report['repeat_only'] is False


def test_unproven_speaker_change_is_kept():
    segment = incoming(LIVE[0], 40.0)
    segment['speaker_id'] = 1
    kept, _ = drop([segment], verified=frozenset())
    assert kept == [segment]


def test_partially_proven_upload_proves_only_the_proven_indices():
    repeats = [incoming(reworded(LIVE[i]), i * 10.0 + 40) for i in range(3)]
    kept, report = drop(repeats, verified=frozenset({0, 2}))
    assert kept == [repeats[1]]
    assert report['dropped_segments'] == 2 and report['evaluated_segments'] == 2


def test_no_proof_never_scans_or_tokenizes(monkeypatch):
    calls = []
    monkeypatch.setattr(live_speech_dedupe, '_tokens', lambda text: calls.append(text) or [])
    kept, report = drop([incoming(reworded(LIVE[0]), 40.0)], verified=frozenset())
    assert report['evaluated_segments'] == 0 and calls == []


def test_oversized_live_row_abstains_before_scanning(monkeypatch):
    calls = []
    monkeypatch.setattr(live_speech_dedupe, '_tokens', lambda text: calls.append(text) or [])
    huge = [live_segment(0) for _ in range(4097)]
    segment = incoming(reworded(LIVE[0]), 40.0)
    kept, report = drop([segment], live=huge)
    assert kept == [segment] and report['evaluated_segments'] == 0 and calls == []


def test_oversized_candidate_neighborhood_keeps_before_candidate_work(monkeypatch):
    token_calls = []
    matcher_calls = []
    real_tokens = live_speech_dedupe._tokens

    def counting(text):
        token_calls.append(text)
        return real_tokens(text)

    class NoMatcher:
        def __init__(self, *args, **kwargs):
            matcher_calls.append(args)

    monkeypatch.setattr(live_speech_dedupe, '_tokens', counting)
    monkeypatch.setattr(live_speech_dedupe, 'SequenceMatcher', NoMatcher)
    crowd = [live_segment(0, start=i * 5.0, end=i * 5.0 + 4.0) for i in range(129)]
    segment = incoming(reworded(LIVE[0]), 40.0)
    kept, _ = drop([segment], live=crowd)
    assert kept == [segment]
    assert token_calls == [segment['text']] and matcher_calls == []


def test_distant_live_segments_are_never_tokenized(monkeypatch):
    token_calls = []
    real_tokens = live_speech_dedupe._tokens

    def counting(text):
        token_calls.append(text)
        return real_tokens(text)

    monkeypatch.setattr(live_speech_dedupe, '_tokens', counting)
    far = [live_segment(0, start=ORIGIN + 4000.0, end=ORIGIN + 4009.0)]
    far[0]['audio_capture_start'] = ORIGIN + 4000.0
    far[0]['audio_capture_end'] = ORIGIN + 4009.0
    segment = incoming(reworded(LIVE[0]), 40.0)
    kept, _ = drop([segment], live=far)
    assert kept == [segment]
    assert token_calls == [segment['text']]


def test_same_segment_mixing_repeat_and_novel_clause_is_kept():
    mixed = incoming(reworded(LIVE[0]) + ' and then budget moved to forty two thousand dollars', 40.0)
    kept, _ = drop([mixed])
    assert kept == [mixed]


def test_changed_number_name_and_negation_are_kept():
    assert drop([incoming(LIVE[0].replace('one', 'eight'), 40.0)])[0]
    assert drop([incoming(LIVE[0].replace('quarterly', 'monthly'), 40.0)])[0]
    assert drop([incoming(LIVE[0].replace('covered', 'skipped'), 40.0)])[0]


def test_single_new_factual_token_keeps_the_segment():
    kept, _ = drop([incoming(LIVE[0] + ' postponed', 40.0)])
    assert len(kept) == 1


def test_short_acknowledgement_is_never_a_repeat_candidate():
    kept, _ = drop([incoming('yes okay', 40.0, duration=1.0)])
    assert len(kept) == 1


def test_beyond_the_matching_window_is_kept():
    repeat = incoming(reworded(LIVE[0]), 40.0)
    repeat['timestamp'] = ORIGIN + 1801.0
    kept, _ = drop([repeat])
    assert kept == [repeat]


def test_exactly_at_the_window_edge_still_matches():
    repeat = incoming(reworded(LIVE[0]), 40.0)
    repeat['timestamp'] = ORIGIN + 1800.0
    kept, _ = drop([repeat])
    assert kept == []


def test_invalid_and_oversized_spans_are_kept():
    assert drop([{**incoming(reworded(LIVE[0]), 40.0), 'end': 40.0}])[0]
    huge = incoming(reworded(LIVE[0]), 40.0)
    huge['timestamp'] = float('nan')
    assert drop([huge])[0]
    long_text = incoming(LIVE[0] + ' word' * 4000, 40.0)
    assert drop([long_text])[0]


def test_empty_live_row_and_non_live_rows_never_donate_coverage():
    repeat = incoming(reworded(LIVE[0]), 40.0)
    assert drop([repeat], live=[])[0] == [repeat]
    sync_scoped = [live_segment(0, speaker_id_scope='sync:WAL-1')]
    assert drop([repeat], live=sync_scoped)[0] == [repeat]
    legacy_scoped = [live_segment(0, speaker_id_scope='legacy-conversation:X:0')]
    assert drop([repeat], live=legacy_scoped)[0] == [repeat]


def test_capture_fields_and_pinned_rows_still_cover_proven_repeats():
    repeat = incoming(reworded(LIVE[0]), 40.0)
    capture = [live_segment(0, audio_capture_start=ORIGIN, audio_capture_end=ORIGIN + 9.5)]
    kept, report = drop_covered_repeats(
        [repeat], capture, live_origin=ORIGIN + 900.0, live_pinned=False, verified_capture_indices=frozenset({0})
    )
    assert kept == [] and report['alignment_method'] == 'source_frame_lexical'
    kept, report = drop_covered_repeats(
        [repeat],
        live_row_segments(),
        live_origin=ORIGIN,
        live_pinned=True,
        verified_capture_indices=frozenset({0}),
    )
    assert kept == [] and report['alignment_method'] == 'source_frame_lexical'


def test_past_the_incoming_cap_is_retained_untouched():
    repeats = [incoming(reworded(LIVE[i % len(LIVE)]), i * 10.0 + 40) for i in range(70)]
    kept, report = drop(repeats)
    assert kept == repeats[64:]
    assert report['dropped_segments'] == 64


def test_window_concatenates_adjacent_live_segments():
    repeat = incoming(LIVE[0].replace('the ', '') + ' ' + LIVE[1].replace('the ', ''), 40.0, duration=19.5)
    kept, _ = drop([repeat], live=live_row_segments())
    assert kept == []


def test_window_never_joins_segments_past_the_gap():
    wide_gap = live_row_segments()
    wide_gap[1]['start'] = wide_gap[0]['end'] + 30.0
    wide_gap[1]['end'] = wide_gap[1]['start'] + 9.5
    repeat = incoming(LIVE[0].replace('the ', '') + ' ' + LIVE[1].replace('the ', ''), 40.0, duration=19.5)
    kept, _ = drop([repeat], live=wide_gap)
    assert kept == [repeat]


CORRECTION_LIVE = 'the quarterly planning review meeting covered agenda item one in detail'


@pytest.mark.parametrize('skew', [40, 1200])
def test_correction_prefix_is_never_a_repeat(skew):
    live = [live_segment(0, text=CORRECTION_LIVE)]
    assert drop([incoming('Actually ' + CORRECTION_LIVE, float(skew))], live=live)[0]


def test_correction_marker_only_in_live_is_never_a_repeat():
    live = [live_segment(0, text='actually ' + CORRECTION_LIVE)]
    assert drop([incoming(CORRECTION_LIVE, 40.0)], live=live)[0]


def test_correction_marker_count_mismatch_is_never_a_repeat():
    live = [live_segment(0, text='actually actually ' + CORRECTION_LIVE)]
    assert drop([incoming('actually ' + CORRECTION_LIVE, 40.0)], live=live)[0]


def test_novel_correction_words_keep_the_segment():
    live = [live_segment(0, text=CORRECTION_LIVE)]
    for marker in ('instead', 'rather', 'correction', 'corrected', 'sorry', 'mean', 'meant'):
        assert drop([incoming(CORRECTION_LIVE + ' ' + marker, 40.0)], live=live)[0]


def test_reordered_correction_marker_count_mismatch_is_never_a_repeat():
    live = [live_segment(0, text='sorry ' + CORRECTION_LIVE + ' instead')]
    assert drop([incoming(CORRECTION_LIVE + ' instead', 40.0)], live=live)[0]
    live = [live_segment(0, text=CORRECTION_LIVE + ' instead')]
    assert drop([incoming('sorry ' + CORRECTION_LIVE + ' instead', 40.0)], live=live)[0]


NEGATED = 'the quarterly planning review did not cover the budget numbers in detail'


def test_added_or_removed_negation_is_never_a_repeat():
    live = [live_segment(0, text=NEGATED)]
    assert drop([incoming(NEGATED.replace('did not', 'did'), 40.0)], live=live)[0]
    live = [live_segment(0, text=NEGATED.replace('did not', 'did'))]
    assert drop([incoming(NEGATED, 40.0)], live=live)[0]


def test_contraction_change_is_never_a_repeat():
    live = [live_segment(0, text=NEGATED)]
    assert drop([incoming(NEGATED.replace('did not', "didn't"), 40.0)], live=live)[0]
    live = [live_segment(0, text=NEGATED.replace('did not', 'did'))]
    assert drop([incoming(NEGATED.replace('did not', "didn't"), 40.0)], live=live)[0]


def test_changed_or_omitted_digit_tokens_are_never_repeats():
    base = 'the quarterly planning review moved to room 204 for the budget talk'
    live = [live_segment(0, text=base)]
    assert drop([incoming(base.replace('204', '205'), 40.0)], live=live)[0]
    assert drop([incoming(base.replace(' 204', ''), 40.0)], live=live)[0]
    live = [live_segment(0, text=base.replace('204 ', ''))]
    assert drop([incoming(base, 40.0)], live=live)[0]


def test_exact_retry_drops_only_identical_text_and_range():
    existing = [{'timestamp': ORIGIN, 'start': 0.0, 'end': 9.5, 'text': LIVE[0], 'id': 'seg-a'}]
    kept, dropped, sync_retry = drop_exact_retries(
        [incoming(LIVE[0], 0.0), incoming(LIVE[1], 0.0), incoming(LIVE[0], 20.0)], existing
    )
    assert dropped == 1 and sync_retry is False
    assert [segment['text'] for segment in kept] == [LIVE[1], LIVE[0]]
    kept, dropped, sync_retry = drop_exact_retries([{**incoming(LIVE[0], 99.0), 'id': 'seg-a'}], existing)
    assert dropped == 1 and kept == [] and sync_retry is False
    kept, dropped, sync_retry = drop_exact_retries([{**incoming(LIVE[1], 0.0), 'id': 'seg-a'}], existing)
    assert dropped == 0 and len(kept) == 1 and sync_retry is False


def test_exact_retry_marks_sync_scoped_matches_for_completion():
    sync_scoped = {
        'timestamp': ORIGIN,
        'start': 0.0,
        'end': 9.5,
        'text': LIVE[0],
        'id': 'seg-a',
        'speaker_id_scope': 'sync:wal-1:0',
    }
    _, dropped, sync_retry = drop_exact_retries([incoming(LIVE[0], 0.0)], [sync_scoped])
    assert dropped == 1 and sync_retry is True
    _, dropped, sync_retry = drop_exact_retries([incoming(LIVE[0], 0.0)], [{**sync_scoped, 'speaker_id_scope': ''}])
    assert dropped == 1 and sync_retry is False


def test_exact_retry_keeps_invalid_ranges_and_oversized_text():
    existing = [{'timestamp': ORIGIN, 'start': 0.0, 'end': 9.5, 'text': LIVE[0], 'id': 'seg-a'}]
    for segment in (
        {**incoming(LIVE[0], 0.0), 'timestamp': float('inf')},
        {**incoming(LIVE[0], 0.0), 'start': 5.0, 'end': 1.0},
        {**incoming(LIVE[0], 0.0), 'text': 'x' * 5000},
    ):
        kept, dropped, _ = drop_exact_retries([segment], existing)
        assert dropped == 0 and kept == [segment]
    stored = dict(existing[0])
    stored['end'] = stored['start']
    _, dropped, _ = drop_exact_retries([incoming(LIVE[0], 0.0)], [stored])
    assert dropped == 0


def test_proven_exact_retry_drops_against_live_text():
    stored = {'timestamp': ORIGIN, 'start': 0.0, 'end': 9.5, 'text': LIVE[0], 'id': 'seg-a'}
    segment = incoming(LIVE[0], 0.0)
    kept, dropped, sync_retry = drop_proven_exact_retries([(0, segment)], [stored], verified_indices=frozenset({0}))
    assert dropped == 1 and kept == [] and sync_retry is False


def test_unproven_exact_retry_needs_the_same_sync_scope():
    stored = {'timestamp': ORIGIN, 'start': 0.0, 'end': 9.5, 'text': LIVE[0], 'id': 'seg-a'}
    segment = incoming(LIVE[0], 0.0)
    kept, dropped, _ = drop_proven_exact_retries([(0, segment)], [stored])
    assert dropped == 0 and kept == [segment]
    scoped_stored = dict(stored, speaker_id_scope='sync:wal-1')
    scoped_segment = dict(segment, speaker_id_scope='sync:wal-1')
    kept, dropped, sync_retry = drop_proven_exact_retries([(0, scoped_segment)], [scoped_stored])
    assert dropped == 1 and kept == [] and sync_retry is True
    other_scope = dict(segment, speaker_id_scope='sync:wal-2')
    kept, dropped, _ = drop_proven_exact_retries([(0, other_scope)], [scoped_stored])
    assert dropped == 0 and kept == [other_scope]


def test_unproven_exact_retry_ignores_id_matches_on_live_text():
    stored = {'timestamp': ORIGIN, 'start': 0.0, 'end': 9.5, 'text': LIVE[0], 'id': 'seg-a'}
    segment = dict(incoming(LIVE[0], 99.0), id='seg-a')
    kept, dropped, _ = drop_proven_exact_retries([(0, segment)], [stored])
    assert dropped == 0 and kept == [segment]
    kept, dropped, _ = drop_proven_exact_retries([(0, segment)], [stored], verified_indices=frozenset({0}))
    assert dropped == 1 and kept == []


def test_oversized_live_row_returns_everything_unchanged():
    stored = {'timestamp': ORIGIN, 'start': 0.0, 'end': 9.5, 'text': LIVE[0], 'id': 'seg-a'}
    segment = incoming(LIVE[0], 0.0)
    huge = [stored] * 4097
    kept, dropped, sync_retry = drop_proven_exact_retries([(0, segment)], huge, verified_indices=frozenset({0}))
    assert (dropped, sync_retry) == (0, False) and kept == [segment]


def test_oversized_live_text_never_enters_windows_or_matching():
    huge = 'the ' + 'word ' * 2000
    live = [live_segment(0, text=huge)]
    incoming_segment = incoming(LIVE[0], 40.0)
    kept, report = drop([incoming_segment], live=live)
    assert kept == [incoming_segment]
    live = [live_segment(0)]
    incoming_segment = incoming('x' * 5000, 40.0)
    kept, report = drop([incoming_segment], live=live)
    assert kept == [incoming_segment]


def test_bounded_span_seconds_clamps_pathological_inputs():
    assert bounded_span_seconds([{'start': 0.0, 'end': 5.0}, {'start': float('nan'), 'end': 4.0}]) == 5.0
    assert bounded_span_seconds([{'start': -10.0, 'end': 0.0}]) == 10.0
    assert bounded_span_seconds([{'start': 0.0, 'end': 10**9}]) == 86400.0
    assert bounded_span_seconds([{'start': 'x', 'end': float('inf')}]) == 0.0
