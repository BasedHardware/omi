"""Lexical repeat coverage for safety-WAL segments bound to a live row.

``drop_covered_repeats`` drops an incoming segment only when a bounded live
window lexically covers every substantive incoming token; every ambiguity is
kept. Clock truth: the live capture fields when present, otherwise the row
origin plus stored offsets — a content window, faithful capture when the v2
pin is set. All text is synthetic.
"""

from utils.sync.live_speech_dedupe import bounded_span_seconds, drop_covered_repeats, drop_exact_retries

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


def drop(incoming_segments, live=None, **kwargs):
    return drop_covered_repeats(
        incoming_segments,
        live_row_segments() if live is None else live,
        live_origin=ORIGIN,
        live_pinned=False,
    )


def test_reworded_repeat_is_dropped_new_speech_is_kept():
    repeats = [incoming(reworded(LIVE[i]), i * 10.0 + 40) for i in range(3)]
    fresh = incoming('a genuinely new remark about weekend hiking plans with friends', 35.0 + 40)
    kept, report = drop(repeats + [fresh])
    assert kept == [fresh]
    assert report['dropped_seconds'] == 28.5
    assert report['alignment_method'] == 'content_window'
    assert report['repeat_only'] is False


def test_entirely_covered_upload_reports_repeat_only():
    repeats = [incoming(reworded(LIVE[i]), i * 10.0 + 40) for i in range(3)]
    kept, report = drop(repeats)
    assert kept == [] and report['repeat_only'] is True


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


def test_live_capture_fields_and_the_v2_pin_report_capture_window():
    repeat = incoming(reworded(LIVE[0]), 40.0)
    capture = [live_segment(0, audio_capture_start=ORIGIN, audio_capture_end=ORIGIN + 9.5)]
    kept, report = drop_covered_repeats([repeat], capture, live_origin=ORIGIN + 900.0, live_pinned=False)
    assert kept == [] and report['alignment_method'] == 'capture_window'
    kept, report = drop_covered_repeats([repeat], live_row_segments(), live_origin=ORIGIN, live_pinned=True)
    assert kept == [] and report['alignment_method'] == 'capture_window'


def test_legacy_clock_reports_content_window():
    kept, report = drop([incoming(reworded(LIVE[0]), 40.0)])
    assert kept == [] and report['alignment_method'] == 'content_window'


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
    kept, dropped = drop_exact_retries(
        [incoming(LIVE[0], 0.0), incoming(LIVE[1], 0.0), incoming(LIVE[0], 20.0)], existing
    )
    assert dropped == 1 and [segment['text'] for segment in kept] == [LIVE[1], LIVE[0]]
    kept, dropped = drop_exact_retries([{**incoming(LIVE[0], 99.0), 'id': 'seg-a'}], existing)
    assert dropped == 1 and kept == []
    kept, dropped = drop_exact_retries([{**incoming(LIVE[1], 0.0), 'id': 'seg-a'}], existing)
    assert dropped == 0 and len(kept) == 1


def test_bounded_span_seconds_clamps_pathological_inputs():
    assert bounded_span_seconds([{'start': 0.0, 'end': 5.0}, {'start': float('nan'), 'end': 4.0}]) == 5.0
    assert bounded_span_seconds([{'start': -10.0, 'end': 0.0}]) == 10.0
    assert bounded_span_seconds([{'start': 0.0, 'end': 10**9}]) == 86400.0
    assert bounded_span_seconds([{'start': 'x', 'end': float('inf')}]) == 0.0
