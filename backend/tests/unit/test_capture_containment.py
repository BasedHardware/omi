"""Pure detector contracts for time-aligned user-utterance containment.

Synthetic transcripts only; the complementary pair is tuned so the shipped
exact-trigram rule cannot confirm (8 < 15 shared trigrams) while token
coverage stays at 0.8125 >= 0.8.
"""

import logging
import time
from collections import UserDict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from models.conversation import Conversation
from tests.unit.fixtures import containment_long_pair as long_pair
from utils.conversations import capture_containment as cc
from utils.conversations.shared_speech import measure_shared_speech

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

UTTERANCES = [
    'alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa',
    'quartz jasper onyx topaz garnet opal pearl ruby amber coral ivory slate flint agate basalt cedar',
    'willow birch maple oak pine spruce hemlock alder aspen beech elm fir larch rowan poplar yew',
    'violet indigo cobalt umber sienna ocher mauve teal cyan fuchsia beige khaki lilac maroon navy plum',
]
UTTERANCE_TIMES = [80.0, 140.0, 200.0, 260.0]
REMOTE_FILLER = 'remote voice filler jargon aside tangent remark aside ' * 3


def transcript_variant(text):
    """Sparse ASR noise: three substitutions plus two insertions per utterance."""
    words = text.split()
    words[4], words[8], words[12] = 'zzzfive', 'zzznine', 'zzzthirteen'
    words.insert(7, 'hum')
    words.insert(2, 'uh')
    return ' '.join(words)


def segment(text, start, is_user=True, end=None, **extra):
    return {
        'text': text,
        'start': start,
        'end': start + 12.0 if end is None else end,
        'is_user': is_user,
        'speaker': 'SPEAKER_00',
        **extra,
    }


def complementary_pair():
    """Pendant heard only the wearer; the laptop also heard remote participants.

    Capture clocks differ: the laptop started three seconds earlier, so equal
    wall time is written as a +3s capture-local offset.
    """
    pendant_segments = [segment(text, start) for text, start in zip(UTTERANCES, UTTERANCE_TIMES)]
    laptop_segments = []
    for index, (text, start) in enumerate(zip(UTTERANCES, UTTERANCE_TIMES)):
        laptop_segments.append(segment(transcript_variant(text), start + 3.0))
        if index < len(UTTERANCES) - 1:
            laptop_segments.append(segment(REMOTE_FILLER, start + 11.0, is_user=False, end=start + 31.0))
    laptop_segments.sort(key=lambda item: item['start'])
    pendant = row('pendant', 'omi', 0, 300, pendant_segments)
    laptop = row('laptop', 'desktop', -3, 297, laptop_segments)
    return pendant, laptop


def row(id, source, start=0, end=600, segments=None, **extra):
    return {
        'id': id,
        'source': source,
        'status': 'completed',
        'discarded': False,
        'started_at': T0 + timedelta(seconds=start),
        'finished_at': T0 + timedelta(seconds=end),
        'transcript_segments': segments if segments is not None else [],
        **extra,
    }


def test_complementary_pair_joins_in_both_orders_and_symmetric_rule_cannot():
    pendant, laptop = complementary_pair()
    assert not measure_shared_speech(pendant['transcript_segments'], laptop['transcript_segments']).confirms()
    for first, second in ((pendant, laptop), (laptop, pendant)):
        decision = cc.measure_capture_containment(first, second)
        assert decision.would_join and decision.reason == 'contained'
        assert decision.matched_words == 52 and decision.smaller_words == 64
        assert decision.matched_utterances == 4 and decision.distinct_words >= 20
        assert decision.support_seconds == 48.0 and decision.coverage == 0.8125


def test_evidence_is_numeric_only():
    pendant, laptop = complementary_pair()
    record = cc.measure_capture_containment(pendant, laptop).evidence()
    assert record['method'] == 'user_speech_containment'
    assert set(record) == {
        'method',
        'matched_words',
        'smaller_words',
        'matched_utterances',
        'distinct_words',
        'support_seconds',
        'coverage',
    }
    assert all(not isinstance(value, str) for key, value in record.items() if key != 'method')


def test_dict_and_model_rows_agree():
    pendant, laptop = complementary_pair()
    model = Conversation(
        **{k: v for k, v in laptop.items() if k != 'transcript_segments'},
        transcript_segments=laptop['transcript_segments'],
        created_at=T0,
        structured={},
    )
    by_model = cc.measure_capture_containment(pendant, model)
    by_dict = cc.measure_capture_containment(pendant, laptop)
    assert by_model == by_dict


def test_non_dict_mapping_rows_and_segments_agree():
    pendant, laptop = complementary_pair()
    mapping = UserDict(laptop)
    mapping['transcript_segments'] = [UserDict(item) for item in laptop['transcript_segments']]
    assert cc.measure_capture_containment(pendant, mapping) == cc.measure_capture_containment(pendant, laptop)


def test_unrelated_meetings_with_user_speech_do_not_join():
    other = [
        'the quarterly numbers came in above forecast because renewals held up better '
        'than we modeled and finance still wants a slower hiring plan next quarter',
        'okay yeah right the support team roadmap shifts again after the board meeting '
        'closes and recruiting pauses while the budget review wraps up this week',
    ]
    pendant, _ = complementary_pair()
    stranger = row(
        'stranger',
        'desktop',
        -3,
        297,
        [segment(other[0], 83.0, end=113.0), segment(other[1], 203.0, end=233.0)],
    )
    decision = cc.measure_capture_containment(pendant, stranger)
    assert not decision.would_join and decision.reason == 'timing'


def test_background_media_without_user_attribution_never_joins():
    pendant, laptop = complementary_pair()
    for item in laptop['transcript_segments']:
        if not item['is_user']:
            item['start'] += 5.0
        item['is_user'] = False
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'no_user_speech'


def test_missing_or_unknown_user_attribution_fails_closed():
    pendant, laptop = complementary_pair()
    for item in laptop['transcript_segments']:
        if not item['is_user']:
            item['start'] += 5.0
        item.pop('is_user')
    assert cc.measure_capture_containment(pendant, laptop).reason == 'no_user_speech'
    for item in laptop['transcript_segments']:
        item['is_user'] = 'yes'
    assert cc.measure_capture_containment(pendant, laptop).reason == 'no_user_speech'


def test_tiny_repeated_snippets_stay_below_size_floor():
    small = row(
        'pendant',
        'omi',
        0,
        300,
        [segment('one two three four five', start) for start in (80.0, 140.0, 200.0, 260.0)],
    )
    large = row(
        'laptop',
        'desktop',
        0,
        300,
        [segment('one two three four five', start) for start in (80.0, 140.0, 200.0, 260.0)],
    )
    decision = cc.measure_capture_containment(small, large)
    assert not decision.would_join and decision.reason == 'too_small'
    assert decision.smaller_words == 20


def test_one_or_two_large_utterances_cannot_support_a_group():
    pendant, laptop = complementary_pair()
    pendant['transcript_segments'] = pendant['transcript_segments'][:1]
    laptop['transcript_segments'] = [item for item in laptop['transcript_segments'] if item['start'] == 83.0]
    assert cc.measure_capture_containment(pendant, laptop).reason == 'too_small'


def test_repeated_identical_utterance_counts_once():
    repeated = ' '.join(UTTERANCES[0].split())
    pendant, laptop = complementary_pair()
    pendant['transcript_segments'] = [segment(repeated, t) for t in UTTERANCE_TIMES]
    laptop['transcript_segments'] = [segment(transcript_variant(repeated), t + 3.0) for t in UTTERANCE_TIMES]
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join
    assert decision.matched_utterances == 1


def test_speech_outside_the_shared_window_is_not_evidence():
    pendant, laptop = complementary_pair()
    laptop['finished_at'] = T0 + timedelta(seconds=150)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join


def test_wall_skew_beyond_twelve_seconds_is_not_a_match():
    pendant, laptop = complementary_pair()
    for item in laptop['transcript_segments']:
        if item['is_user']:
            item['start'] += 20.0
            item['end'] += 20.0
    assert cc.measure_capture_containment(pendant, laptop).reason == 'timing'


@pytest.mark.parametrize('bad', [{'start': 'x'}, {'end': None}, {'start': True}, {'end': False}])
def test_malformed_segment_times_fail_closed(bad):
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0].update(bad)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.reason == 'layout_timing' and decision.dropped_segments == 0


def test_missing_segment_time_fails_closed():
    pendant, laptop = complementary_pair()
    del laptop['transcript_segments'][0]['end']
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.reason == 'layout_timing' and decision.dropped_segments == 0


@pytest.mark.parametrize(
    'bad', [{'end': float('nan')}, {'start': float('inf')}, {'start': float('-inf')}, {'end': 10**400}]
)
def test_non_finite_segment_times_fail_closed(bad):
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0].update(bad)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.reason == 'layout_non_finite' and decision.dropped_segments == 0


def test_unplaced_or_crossing_segments_fail_closed():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0]['audio_alignment'] = 'unplaced'
    assert cc.measure_capture_containment(pendant, laptop).reason == 'layout_unplaced'
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0].update(start=-1.0, end=-1.0, audio_alignment='unplaced')
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.reason == 'layout_unplaced' and decision.dropped_segments == 0
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0]['end'] = 4000.0
    assert cc.measure_capture_containment(pendant, laptop).reason == 'layout_window_slop'


def test_bounds_overflow_never_accepts_a_prefix():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'] = laptop['transcript_segments'] + [
        {'text': '', 'start': float(i), 'end': float(i) + 0.5, 'is_user': False} for i in range(cc.MAX_SEGMENTS + 5)
    ]
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds_segments'
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'] = 'not a segment list'
    assert cc.measure_capture_containment(pendant, laptop).reason == 'layout_shape'


def test_oversized_in_window_segments_fail_closed():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0] = segment(' '.join(['word'] * 200), 83.0, end=183.0)
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds_segment_words'


def test_a_target_segment_is_consumed_once():
    same = UTTERANCES[0]
    pendant = row(
        'pendant',
        'omi',
        0,
        300,
        [segment(same, 80.0), segment(UTTERANCES[1], 140.0), segment(UTTERANCES[2], 200.0), segment(same, 260.0)],
    )
    laptop = row(
        'laptop',
        'desktop',
        -3,
        297,
        [
            segment(transcript_variant(same), 83.0),
            segment(transcript_variant(UTTERANCES[1]), 143.0),
            segment(transcript_variant(UTTERANCES[2]), 203.0),
            segment(REMOTE_FILLER, 240.0, is_user=False, end=290.0),
        ],
    )
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.matched_utterances == 3


def test_reordered_tokens_do_not_confirm():
    pendant, laptop = complementary_pair()
    for item in laptop['transcript_segments']:
        if item['is_user']:
            words = item['text'].split()
            words.reverse()
            item['text'] = ' '.join(words)
    assert cc.measure_capture_containment(pendant, laptop).reason == 'timing'


@pytest.mark.parametrize(
    'mutate',
    [
        lambda row: row.update(source='omi'),
        lambda row: row.update(discarded=True),
        lambda row: row.update(deleted=True),
        lambda row: row.update(status='processing'),
        lambda row: row.update(started_at='not-a-datetime'),
        lambda row: row.update(finished_at=row['started_at']),
    ],
)
def test_ineligible_rows_never_join(mutate):
    pendant, laptop = complementary_pair()
    mutate(laptop)
    assert cc.measure_capture_containment(pendant, laptop).reason == 'ineligible'


def test_naive_windows_are_treated_as_utc():
    pendant, laptop = complementary_pair()
    for item in (pendant, laptop):
        item['started_at'] = item['started_at'].replace(tzinfo=None)
        item['finished_at'] = item['finished_at'].replace(tzinfo=None)
    assert cc.measure_capture_containment(pendant, laptop).would_join


def test_mode_defaults_shadow_and_fails_closed(monkeypatch):
    monkeypatch.delenv(cc.MODE_ENV, raising=False)
    assert cc.capture_group_containment_mode() == 'shadow'
    for value, expected in (('ON', 'on'), ('off', 'off'), ('', 'off'), ('typo', 'off'), (' shadow ', 'shadow')):
        monkeypatch.setenv(cc.MODE_ENV, value)
        assert cc.capture_group_containment_mode() == expected


def test_log_line_is_fixed_format_and_content_free(caplog):
    decision = cc.CaptureContainment(True, 'contained', 52, 64, 4, 52, 188.0, 0.8125)
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        cc.record_capture_containment(decision, mode='shadow', phase='jev', jev_p=0.75)
        cc.record_capture_containment(
            cc.CaptureContainment(False, 'timing'), mode='off', phase='rule', jev_p=float('nan')
        )
    lines = [r.message for r in caplog.records]
    assert lines[0] == (
        'event=capture_group_containment mode=shadow phase=jev would_join=true '
        'reason=contained jev_p=0.750000 basis=full dropped_segments=0'
    )
    assert lines[1] == (
        'event=capture_group_containment mode=off phase=rule would_join=false '
        'reason=timing jev_p=unavailable basis=full dropped_segments=0'
    )


def test_log_labels_and_score_are_clamped(caplog):
    decision = SimpleNamespace(would_join=False, reason='not-a-reason')
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        cc.record_capture_containment(decision, mode='bogus', phase='bogus', jev_p=1.5)
    assert caplog.records[0].message == (
        'event=capture_group_containment mode=off phase=rule would_join=false '
        'reason=ineligible jev_p=unavailable basis=full dropped_segments=0'
    )


@pytest.mark.parametrize(
    'value,expected', [(3, 3), (-5, 0), (2 * cc.MAX_SEGMENTS + 1, 2 * cc.MAX_SEGMENTS), ('x', 0), (True, 0), (2.5, 0)]
)
def test_log_dropped_segments_is_allowlisted_and_clamped(caplog, value, expected):
    decision = cc.CaptureContainment(False, 'timing')
    object.__setattr__(decision, 'dropped_segments', value)
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        cc.record_capture_containment(decision, mode='shadow')
    assert caplog.records[0].message.endswith('dropped_segments=%d' % expected)


@pytest.mark.parametrize('basis', ['full', 'sampled', 'PRIVATE-SENTINEL', 42])
def test_log_basis_is_allowlisted_and_clamped(caplog, basis):
    decision = cc.CaptureContainment(False, 'timing')
    object.__setattr__(decision, 'basis', basis)
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        cc.record_capture_containment(decision, mode='shadow')
    expected = basis if basis in ('full', 'sampled') else 'full'
    assert caplog.records[0].message.endswith('jev_p=unavailable basis=%s dropped_segments=0' % expected)
    assert 'PRIVATE-SENTINEL' not in caplog.records[0].message


NATURAL_UTTERANCES = [
    'we must deliver the revised sensor assembly before friday because customers expect reliable battery performance immediately',
    'please ask the factory manager whether replacement microphones arrived today and confirm shipping dates tomorrow morning',
    'our launch checklist includes firmware calibration acoustic testing supplier approval packaging review and updated installation instructions',
    'finance should authorize the vendor deposit after procurement verifies quantities serial numbers warranty terms and invoices',
]
REMOTE_SPEECH = 'the remote participant reviews roadmap budget hiring and quarterly planning details with the team'


def natural_pair():
    """Natural-language complementary pair with a +3s residual laptop clock skew."""
    pendant_segments = [segment(text, start) for text, start in zip(NATURAL_UTTERANCES, UTTERANCE_TIMES)]
    laptop_segments = []
    for index, (text, start) in enumerate(zip(NATURAL_UTTERANCES, UTTERANCE_TIMES)):
        laptop_segments.append(segment(transcript_variant(text), start + 6.0))
        if index < len(NATURAL_UTTERANCES) - 1:
            laptop_segments.append(segment(REMOTE_SPEECH, start + 11.0, is_user=False, end=start + 31.0))
    laptop_segments.sort(key=lambda item: item['start'])
    pendant = row('pendant', 'omi', 0, 300, pendant_segments)
    laptop = row('laptop', 'desktop', -3, 303, laptop_segments)
    return pendant, laptop


def test_natural_language_pair_with_residual_skew():
    pendant, laptop = natural_pair()
    shared = measure_shared_speech(pendant['transcript_segments'], laptop['transcript_segments'])
    assert not shared.confirms()
    for first, second in ((pendant, laptop), (laptop, pendant)):
        assert cc.measure_capture_containment(first, second).would_join


def test_three_tiny_exact_fragments_are_too_small():
    fragments = [' '.join(text.split()[:10]) for text in UTTERANCES[:3]]
    times = [80.0, 140.0, 200.0]
    pendant = row(
        'pendant', 'omi', 0, 300, [segment(text, start, end=start + 16.0) for text, start in zip(fragments, times)]
    )
    laptop = row(
        'laptop', 'desktop', 0, 300, [segment(text, start, end=start + 16.0) for text, start in zip(fragments, times)]
    )
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'too_small'


def test_two_large_matched_utterances_do_not_join():
    texts = [text + ' extra' + ' word' * 7 for text in UTTERANCES[:2]]
    texts = [' '.join(text.split()[:24]) for text in texts]
    times = [80.0, 200.0]
    pendant = row(
        'pendant', 'omi', 0, 300, [segment(text, start, end=start + 30.0) for text, start in zip(texts, times)]
    )
    laptop = row(
        'laptop',
        'desktop',
        0,
        300,
        [segment(transcript_variant(text), start, end=start + 30.0) for text, start in zip(texts, times)],
    )
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'too_small' and decision.matched_utterances == 2


def test_segment_character_bound_rejects():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0] = segment('averyverylongtokenword ' * 104, 83.0)
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds_segment_chars'


def test_capture_character_bound_rejects():
    text = 'averyverylongtokenw ' * 100
    segments = [segment(text, index * 9.0) for index in range(280)]
    pendant, _ = complementary_pair()
    pendant['finished_at'] = T0 + timedelta(seconds=2530)
    laptop = row('laptop', 'desktop', 0, 2530, segments)
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds_chars'


def test_capture_word_bound_rejects():
    text = ' '.join('word%03d' % index for index in range(124))
    segments = [segment(text, index * 10.0, end=index * 10.0 + 8.0) for index in range(517)]
    pendant = row('pendant', 'omi', 0, 5180, segments)
    laptop = row('laptop', 'desktop', 0, 5180, [dict(item) for item in segments])
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds_words'


def test_segment_word_bound_rejects():
    text = ' '.join('word%03d' % index for index in range(129))
    pendant = row('pendant', 'omi', 0, 300, [segment(text, 80.0)])
    laptop = row('laptop', 'desktop', 0, 300, [segment(text, 80.0)])
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds_segment_words'


def test_segment_duration_bound_rejects():
    pendant = row('pendant', 'omi', 0, 300, [segment(UTTERANCES[0], 80.0, end=171.0)])
    laptop = row('laptop', 'desktop', 0, 300, [segment(UTTERANCES[0], 80.0, end=171.0)])
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds_segment_seconds'


def test_target_candidate_overflow_rejects():
    small_texts = [UTTERANCES[0]] + [' '.join('s%d_%d' % (index, word) for word in range(12)) for index in range(3)]
    times = [100.0, 140.0, 200.0, 260.0]
    pendant = row('pendant', 'omi', 0, 300, [segment(text, start) for text, start in zip(small_texts, times)])
    targets = [
        segment(' '.join('t%d_%d' % (index, word) for word in range(8)), 90.0 + index, end=90.0 + index + 1.0)
        for index in range(20)
    ]
    laptop = row('laptop', 'desktop', 0, 300, targets)
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds_candidates'


def test_negative_segment_time_rejects():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0]['start'] = -2.001
    assert cc.measure_capture_containment(pendant, laptop).reason == 'layout_window_slop'


def test_segment_end_past_capture_window_rejects():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0]['end'] = 400.0
    assert cc.measure_capture_containment(pendant, laptop).reason == 'layout_window_slop'


def _pair_with_laptop_split(splits):
    pendant, laptop = complementary_pair()
    tokens = transcript_variant(UTTERANCES[0]).split()
    bounds = [83.0 + index * (12.0 / splits) for index in range(splits + 1)]
    chunks = [tokens[index * len(tokens) // splits : (index + 1) * len(tokens) // splits] for index in range(splits)]
    pieces = [segment(' '.join(chunk), bounds[index], end=bounds[index + 1]) for index, chunk in enumerate(chunks)]
    laptop['transcript_segments'] = [
        item for item in laptop['transcript_segments'] if not (item['is_user'] and item['start'] == 83.0)
    ]
    laptop['transcript_segments'].extend(pieces)
    laptop['transcript_segments'].sort(key=lambda item: item['start'])
    return pendant, laptop


@pytest.mark.parametrize('splits', [2, 3])
def test_utterance_matched_across_split_target_segments(splits):
    pendant, laptop = _pair_with_laptop_split(splits)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.would_join and decision.matched_words == 52 and decision.matched_utterances == 4


def test_sparse_matches_with_long_span_reject():
    pendant, laptop = complementary_pair()
    for record in (pendant, laptop):
        for item in record['transcript_segments']:
            if item.get('is_user'):
                item['end'] = item['start'] + 8.0
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'too_small'
    assert decision.matched_words == 52 and decision.coverage == 0.8125 and decision.support_seconds == 32.0


@pytest.mark.parametrize('track', [True, False])
@pytest.mark.parametrize('unordered', [False, True])
def test_one_exact_duplicate_per_track_is_allowed(track, unordered):
    canonical = cc.measure_capture_containment(*complementary_pair())
    for order in (('pendant', 'laptop'), ('laptop', 'pendant')):
        pendant, laptop = complementary_pair()
        targets = [item for item in laptop['transcript_segments'] if item['is_user'] is track]
        laptop['transcript_segments'].append(dict(targets[0]))
        if unordered:
            laptop['transcript_segments'].reverse()
        rows = {'pendant': pendant, 'laptop': laptop}
        decision = cc.measure_capture_containment(rows[order[0]], rows[order[1]])
        assert decision == canonical
        assert decision.matched_words == 52 and decision.smaller_words == 64
        assert decision.support_seconds == 48.0 and decision.coverage == 0.8125


@pytest.mark.parametrize('track', [True, False])
def test_partial_same_track_overlap_below_half_is_allowed(track):
    canonical = cc.measure_capture_containment(*complementary_pair())
    for order in (('pendant', 'laptop'), ('laptop', 'pendant')):
        pendant, laptop = complementary_pair()
        laptop['transcript_segments'].append(
            {'text': 'another remote remark', 'start': 100.0, 'end': 111.0, 'is_user': False, 'speaker': 'SPEAKER_00'}
            if not track
            else segment('extra one two three four five six seven', 91.0, end=102.0)
        )
        rows = {'pendant': pendant, 'laptop': laptop}
        decision = cc.measure_capture_containment(rows[order[0]], rows[order[1]])
        assert decision == canonical
        assert decision.matched_words == 52 and decision.reason == 'contained'


@pytest.mark.parametrize('same_text', [True, False])
def test_same_track_triple_overlap_rejects_layout_overlap_ratio(monkeypatch, same_text):
    pendant, _ = complementary_pair()
    texts = (
        ['alpha bravo charlie delta echo foxtrot golf hotel'] * 3
        if same_text
        else [
            'alpha bravo charlie delta echo foxtrot golf hotel',
            'quartz jasper onyx topaz garnet opal pearl ruby',
            'willow birch maple oak pine spruce hemlock alder',
        ]
    )
    laptop = row('laptop', 'desktop', 0, 300, [segment(text, 80.0) for text in texts])
    calls = []
    monkeypatch.setattr(cc, '_ordered_match', _counting_matcher(calls))
    for first, second in ((pendant, laptop), (laptop, pendant)):
        decision = cc.measure_capture_containment(first, second)
        assert not decision.would_join and decision.reason == 'layout_overlap_ratio'
        assert decision.matched_words == 0 and decision.support_seconds == 0.0
    assert not calls


def test_nested_same_track_overlap_rejects_layout_overlap_ratio():
    pendant, _ = complementary_pair()
    laptop = row(
        'laptop',
        'desktop',
        0,
        300,
        [
            segment('alpha bravo charlie delta echo foxtrot golf hotel', 80.0, end=92.0),
            segment('quartz jasper onyx topaz garnet opal pearl ruby', 81.0, end=92.0),
            segment('willow birch maple oak pine spruce hemlock alder', 82.0, end=92.0),
        ],
    )
    for first, second in ((pendant, laptop), (laptop, pendant)):
        assert cc.measure_capture_containment(first, second).reason == 'layout_overlap_ratio'


def test_overlapping_turns_from_different_speakers_do_not_reject():
    canonical = cc.measure_capture_containment(*complementary_pair())
    for order in (('pendant', 'laptop'), ('laptop', 'pendant')):
        pendant, laptop = complementary_pair()
        for speaker_id in (1, 2, 3):
            laptop['transcript_segments'].append(
                {
                    'text': ' '.join('r%dw%d' % (speaker_id, index) for index in range(10)),
                    'start': 103.0,
                    'end': 123.0,
                    'is_user': False,
                    'speaker_id': speaker_id,
                }
            )
        rows = {'pendant': pendant, 'laptop': laptop}
        assert cc.measure_capture_containment(rows[order[0]], rows[order[1]]) == canonical


def test_overlapping_bundle_slightly_overlapping_split_is_rejected():
    for order in (('pendant', 'laptop'), ('laptop', 'pendant')):
        pendant, laptop = complementary_pair()
        first_user = next(item for item in laptop['transcript_segments'] if item['is_user'])
        laptop['transcript_segments'].remove(first_user)
        tokens = first_user['text'].split()
        laptop['transcript_segments'] += [
            segment(' '.join(tokens[:6]), first_user['start'], end=first_user['start'] + 6.25),
            segment(' '.join(tokens[6:]), first_user['start'] + 6.0, end=first_user['end']),
        ]
        laptop['transcript_segments'].reverse()
        pendant['transcript_segments'].reverse()
        rows = {'pendant': pendant, 'laptop': laptop}
        decision = cc.measure_capture_containment(rows[order[0]], rows[order[1]])
        assert not decision.would_join and decision.reason == 'insufficient_coverage'
        assert decision.matched_words == 39 and decision.smaller_words == 64
        assert decision.support_seconds == 36.0 and decision.coverage == 39 / 64


def _pair_with_user_track_pieces(pieces_for):
    pendant, laptop = complementary_pair()
    rebuilt = []
    for item in laptop['transcript_segments']:
        if not item['is_user']:
            rebuilt.append(item)
            continue
        tokens = item['text'].split()
        rebuilt += [
            segment(text, start, end=end) for text, start, end in pieces_for(tokens, item['start'], item['end'])
        ]
    laptop['transcript_segments'] = rebuilt
    return pendant, laptop


@pytest.mark.parametrize('mode', ['on', 'shadow'])
@pytest.mark.parametrize('unordered', [False, True])
def test_overlapping_bundle_identical_halves_never_join(mode, unordered):
    for order in (('pendant', 'laptop'), ('laptop', 'pendant')):
        pendant, laptop = _pair_with_user_track_pieces(
            lambda tokens, start, end: (
                (' '.join(tokens[:9]), start, end),
                (' '.join(tokens[9:]), start, end),
            )
        )
        if unordered:
            laptop['transcript_segments'].reverse()
            pendant['transcript_segments'].reverse()
        rows = {'pendant': pendant, 'laptop': laptop}
        shared = measure_shared_speech(pendant['transcript_segments'], laptop['transcript_segments'])
        assert not shared.confirms()
        decision = cc.measure_capture_containment(rows[order[0]], rows[order[1]], mode=mode)
        assert not decision.would_join and decision.reason == 'timing'
        assert decision.matched_words == 0 and decision.matched_utterances == 0
        assert decision.smaller_words == 64 and decision.support_seconds == 0.0
        assert decision.basis == 'full'


@pytest.mark.parametrize('mode', ['on', 'shadow'])
def test_overlapping_bundle_slight_overlap_never_joins(mode):
    for order in (('pendant', 'laptop'), ('laptop', 'pendant')):
        pendant, laptop = _pair_with_user_track_pieces(
            lambda tokens, start, end: (
                (' '.join(tokens[:9]), start, start + 6.25),
                (' '.join(tokens[9:]), start + 6.0, end),
            )
        )
        rows = {'pendant': pendant, 'laptop': laptop}
        shared = measure_shared_speech(pendant['transcript_segments'], laptop['transcript_segments'])
        assert not shared.confirms()
        decision = cc.measure_capture_containment(rows[order[0]], rows[order[1]], mode=mode)
        assert not decision.would_join and decision.reason == 'timing'
        assert decision.matched_words == 0 and decision.matched_utterances == 0
        assert decision.support_seconds == 0.0 and decision.basis == 'full'


@pytest.mark.parametrize('mode', ['on', 'shadow'])
def test_overlapping_bundle_nested_pieces_never_join(mode):
    for order in (('pendant', 'laptop'), ('laptop', 'pendant')):
        pendant, laptop = _pair_with_user_track_pieces(
            lambda tokens, start, end: (
                (' '.join(tokens[:9]), start, end),
                (' '.join(tokens[9:]), start + 3.0, start + 9.0),
            )
        )
        rows = {'pendant': pendant, 'laptop': laptop}
        decision = cc.measure_capture_containment(rows[order[0]], rows[order[1]], mode=mode)
        assert not decision.would_join and decision.reason == 'timing'
        assert decision.matched_words == 0 and decision.matched_utterances == 0
        assert decision.support_seconds == 0.0 and decision.basis == 'full'


@pytest.mark.parametrize('mode', ['on', 'shadow'])
def test_overlapping_bundle_three_piece_boundary_never_joins(mode):
    for order in (('pendant', 'laptop'), ('laptop', 'pendant')):
        pendant, laptop = _pair_with_user_track_pieces(
            lambda tokens, start, end: (
                (' '.join(tokens[:6]), start, start + 4.0),
                (' '.join(tokens[6:12]), start + 4.0, start + 8.25),
                (' '.join(tokens[12:]), start + 8.0, end),
            )
        )
        rows = {'pendant': pendant, 'laptop': laptop}
        decision = cc.measure_capture_containment(rows[order[0]], rows[order[1]], mode=mode)
        assert not decision.would_join and decision.reason == 'timing'
        assert decision.matched_words == 0 and decision.matched_utterances == 0
        assert decision.support_seconds == 0.0 and decision.basis == 'full'


@pytest.mark.parametrize('decoy_first', [False, True])
def test_overlapping_bundle_decoy_alternatives_still_join(decoy_first):
    canonical = cc.measure_capture_containment(*complementary_pair())
    for order in (('pendant', 'laptop'), ('laptop', 'pendant')):
        pendant, laptop = complementary_pair()
        rebuilt = []
        decoy_index = 0
        for item in laptop['transcript_segments']:
            if not item['is_user']:
                rebuilt.append(item)
                continue
            decoy = segment(
                ' '.join('d%dw%d' % (decoy_index, word) for word in range(16)),
                item['start'],
                end=item['end'],
            )
            decoy_index += 1
            rebuilt += [decoy, item] if decoy_first else [item, decoy]
        laptop['transcript_segments'] = rebuilt
        rows = {'pendant': pendant, 'laptop': laptop}
        decision = cc.measure_capture_containment(rows[order[0]], rows[order[1]])
        assert decision == canonical
        assert decision.matched_words == 52 and decision.smaller_words == 64
        assert decision.support_seconds == 48.0 and decision.coverage == 0.8125


def test_adjacent_intervals_within_a_track_are_allowed():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'].append(
        {'text': 'another remote remark', 'start': 231.0, 'end': 240.0, 'is_user': False, 'speaker': 'SPEAKER_00'}
    )
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.would_join and decision.matched_words == 52


def test_whitespace_only_segment_counts_against_character_bounds():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'].insert(0, {'text': ' ' * 2049, 'start': 83.0, 'end': 91.0})
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds_segment_chars'


def test_whitespace_segments_accumulate_capture_character_budget():
    segments = [
        {'text': ' ' * 2000, 'start': index * 9.0, 'end': index * 9.0 + 8.0, 'is_user': False} for index in range(263)
    ]
    pendant, _ = complementary_pair()
    pendant['finished_at'] = T0 + timedelta(seconds=2380)
    laptop = row('laptop', 'desktop', 0, 2380, segments)
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds_chars'


def _counting_matcher(calls):
    real = cc._ordered_match

    def spy(u_words, bundle_words):
        calls.append((len(u_words) + len(bundle_words), len(u_words) * len(bundle_words)))
        return real(u_words, bundle_words)

    return spy


def _maximum_layout_pair():
    pendant, laptop = complementary_pair()
    user = [item for item in laptop['transcript_segments'] if item['is_user']]
    remote = [
        {
            'text': 'w%d' % index,
            'start': index * 0.25,
            'end': index * 0.25 + 0.25,
            'is_user': False,
            'speaker': 'SPEAKER_00',
        }
        for index in range(4092)
    ]
    merged = sorted(user + remote, key=lambda item: item['start'])
    assert len(merged) == cc.MAX_SEGMENTS == 4096
    return pendant, row('laptop', 'desktop', -3, 1030, merged)


def test_whole_pair_maximum_layout_stays_within_budgets(monkeypatch):
    pendant, laptop = _maximum_layout_pair()
    calls = []
    monkeypatch.setattr(cc, '_ordered_match', _counting_matcher(calls))
    for first, second in ((pendant, laptop), (laptop, pendant)):
        calls.clear()
        decision = cc.measure_capture_containment(first, second)
        assert decision.would_join and decision.matched_words == 52 and decision.smaller_words == 64
        assert 0 < len(calls) <= cc.MAX_MATCHER_CALLS
        assert sum(tokens for tokens, _ in calls) <= cc.MAX_COMPARED_TOKENS
        assert sum(cells for _, cells in calls) <= cc.MAX_TOKEN_COMPARISONS


def test_duplicate_user_intervals_bounds_before_any_matching(monkeypatch):
    pendant, _ = _maximum_layout_pair()
    laptop = row(
        'laptop',
        'desktop',
        -3,
        297,
        [
            {
                'text': 'one two three four five six seven eight',
                'start': 83.0,
                'end': 95.0,
                'is_user': True,
                'speaker': 'SPEAKER_00',
            }
            for _ in range(cc.MAX_SEGMENTS)
        ],
    )
    calls = []
    monkeypatch.setattr(cc, '_ordered_match', _counting_matcher(calls))
    for first, second in ((pendant, laptop), (laptop, pendant)):
        decision = cc.measure_capture_containment(first, second)
        assert not decision.would_join and decision.reason == 'layout_overlap_ratio'
    assert not calls


def _budget_rows(count):
    segments = [segment('a%d b%d c%d d%d e%d f%d g%d h%d' % ((index,) * 8), index * 30.0) for index in range(count)]
    end = count * 30.0 + 30.0
    return (
        row('pendant', 'omi', 0, end, segments),
        row('laptop', 'desktop', 0, end, [dict(item) for item in segments]),
    )


def test_whole_pair_call_budget_exhaustion_bounds(monkeypatch):
    monkeypatch.setattr(cc, 'MAX_MATCHER_CALLS', 2)
    pendant, laptop = _budget_rows(6)
    calls = []
    monkeypatch.setattr(cc, '_ordered_match', _counting_matcher(calls))
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'bounds_matcher_calls'
    assert len(calls) == 2
    assert decision.matched_words == 0 and decision.matched_utterances == 0
    assert decision.distinct_words == 0 and decision.support_seconds == 0.0 and decision.coverage == 0.0


def test_whole_pair_under_call_budget_joins(monkeypatch):
    pendant, laptop = _budget_rows(128)
    calls = []
    monkeypatch.setattr(cc, '_ordered_match', _counting_matcher(calls))
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.would_join and len(calls) == cc.MAX_MATCHER_CALLS == 128


def test_full_population_matches_every_eligible_utterance(monkeypatch):
    pendant, laptop = _budget_rows(64)
    calls = []
    monkeypatch.setattr(cc, '_ordered_match', _counting_matcher(calls))
    for first, second in ((pendant, laptop), (laptop, pendant)):
        calls.clear()
        decision = cc.measure_capture_containment(first, second)
        assert decision.would_join and decision.basis == 'full' and decision.coverage == 1
        assert len(calls) == 64


@pytest.mark.parametrize('mode', ['on', 'shadow'])
def test_full_population_over_call_budget_abstains_without_partial_evidence(monkeypatch, mode):
    pendant, laptop = _budget_rows(129)
    calls = []
    monkeypatch.setattr(cc, '_ordered_match', _counting_matcher(calls))
    for first, second in ((pendant, laptop), (laptop, pendant)):
        calls.clear()
        decision = cc.measure_capture_containment(first, second, mode=mode)
        if mode == 'shadow':
            assert decision.would_join and decision.basis == 'sampled' and len(calls) == 32
            continue
        assert not decision.would_join and decision.reason == 'bounds_matcher_calls' and decision.basis == 'full'
        assert len(calls) == cc.MAX_MATCHER_CALLS == 128
        assert decision.matched_words == 0 and decision.matched_utterances == 0
        assert decision.distinct_words == 0 and decision.support_seconds == 0.0 and decision.coverage == 0.0


@pytest.mark.parametrize('cap', ['tokens', 'cells'])
def test_whole_pair_token_and_cell_budgets_bound_midway(monkeypatch, cap):
    monkeypatch.setattr(cc, 'MAX_MATCHER_CALLS', 10000)
    if cap == 'tokens':
        monkeypatch.setattr(cc, 'MAX_COMPARED_TOKENS', 32)
    else:
        monkeypatch.setattr(cc, 'MAX_TOKEN_COMPARISONS', 128)
    pendant, laptop = _budget_rows(6)
    calls = []
    monkeypatch.setattr(cc, '_ordered_match', _counting_matcher(calls))
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'bounds_' + cap
    assert len(calls) == 2


def test_whole_pair_exact_budget_limits_still_accept(monkeypatch):
    pendant, laptop = complementary_pair()
    totals = {'calls': 0, 'tokens': 0, 'cells': 0}
    real = cc._ordered_match

    def spy(u_words, bundle_words):
        totals['calls'] += 1
        totals['tokens'] += len(u_words) + len(bundle_words)
        totals['cells'] += len(u_words) * len(bundle_words)
        return real(u_words, bundle_words)

    monkeypatch.setattr(cc, '_ordered_match', spy)
    assert cc.measure_capture_containment(pendant, laptop).would_join
    monkeypatch.setattr(cc, 'MAX_MATCHER_CALLS', totals['calls'])
    monkeypatch.setattr(cc, 'MAX_COMPARED_TOKENS', totals['tokens'])
    monkeypatch.setattr(cc, 'MAX_TOKEN_COMPARISONS', totals['cells'])
    assert cc.measure_capture_containment(pendant, laptop).would_join


def _adversarial_pair():
    repeated = ' '.join(['same', 'other'] * 64)
    pendant = row(
        'pendant',
        'omi',
        0,
        300,
        [segment(repeated, start, end=start + 30.0) for start in (80.0, 140.0, 200.0)],
    )
    laptop = row(
        'laptop',
        'desktop',
        0,
        300,
        [
            segment(repeated, start + 12.0 * piece, end=start + 12.0 * piece + 12.0)
            for start in (80.0, 140.0, 200.0)
            for piece in range(3)
        ],
    )
    return pendant, laptop


def test_whole_pair_cell_budget_exhaustion_bounds(monkeypatch):
    pendant, laptop = _adversarial_pair()
    calls = []
    monkeypatch.setattr(cc, '_ordered_match', _counting_matcher(calls))
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'bounds_cells'
    assert len(calls) == 8
    assert sum(cells for _, cells in calls) == cc.MAX_TOKEN_COMPARISONS == 262144


def _no_candidate_pair():
    pendant = row(
        'pendant',
        'omi',
        0,
        300,
        [segment('u%d a%d b%d c%d d%d e%d f%d g%d' % ((index,) * 8), 30.0 + 30.0 * index) for index in range(6)],
    )
    laptop_segments = []
    for index in range(6):
        for piece in range(10):
            start = 30.0 + 30.0 * index - 12.0 + 0.1 * piece
            laptop_segments.append(
                {
                    'text': 'v%d_%d' % (index, piece),
                    'start': start,
                    'end': start + 0.05,
                    'is_user': True,
                    'speaker': 'SPEAKER_00',
                }
            )
    laptop_segments.sort(key=lambda item: item['start'])
    return pendant, row('laptop', 'desktop', 0, 300, laptop_segments)


def test_whole_pair_bundle_check_budget_bounds_without_matching(monkeypatch):
    pendant, laptop = _no_candidate_pair()
    calls = []
    monkeypatch.setattr(cc, '_ordered_match', _counting_matcher(calls))
    monkeypatch.setattr(cc, 'MAX_BUNDLE_CHECKS', 2)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'bounds_bundle_checks'
    assert not calls
    monkeypatch.setattr(cc, 'MAX_BUNDLE_CHECKS', 4096)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'timing'


def test_whole_pair_bundle_check_budget_at_exact_limit_accepts(monkeypatch):
    pendant, laptop = complementary_pair()
    monkeypatch.setattr(cc, 'MAX_BUNDLE_CHECKS', 9)
    assert cc.measure_capture_containment(pendant, laptop).would_join
    monkeypatch.setattr(cc, 'MAX_BUNDLE_CHECKS', 8)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'bounds_bundle_checks'


# CPU ceiling for one decision batch. These run at 0.03-0.18 s on an idle machine,
# but process_time still grows on a shared CI runner whose cores and caches other
# test processes are using, and 0.30 s failed there for unchanged code. The call,
# token and cell budgets asserted below bound the work exactly; this ceiling,
# the fast-unit guard's fail limit, only has to catch an order-of-magnitude
# regression.
CPU_CEILING_SECONDS = 1.0


@pytest.mark.parametrize('layout', ['maximum', 'exhaustion', 'adversarial'])
def test_whole_pair_decision_cpu_stays_bounded(layout):
    if layout == 'maximum':
        first, second = _maximum_layout_pair()
    elif layout == 'exhaustion':
        first, second = _budget_rows(129)
    else:
        first, second = _adversarial_pair()
    start = time.process_time()
    for _ in range(6):
        cc.measure_capture_containment(first, second)
    elapsed = time.process_time() - start
    assert elapsed < CPU_CEILING_SECONDS, elapsed


def test_two_hour_meeting_pair_stays_within_original_budgets(monkeypatch):
    pendant, desktop = long_pair.long_complementary_pair()
    assert len(desktop['transcript_segments']) == 2500 and len(pendant['transcript_segments']) == 1250
    assert not measure_shared_speech(pendant['transcript_segments'], desktop['transcript_segments']).confirms()
    matched_inputs = []
    real = cc._ordered_match

    def spy(u_words, bundle_words):
        matched_inputs.append((u_words, len(u_words) + len(bundle_words), len(u_words) * len(bundle_words)))
        return real(u_words, bundle_words)

    monkeypatch.setattr(cc, '_ordered_match', spy)
    for first, second in ((pendant, desktop), (desktop, pendant)):
        matched_inputs.clear()
        start = time.process_time()
        decision = cc.measure_capture_containment(first, second, mode='shadow')
        elapsed = time.process_time() - start
        assert decision.would_join and decision.reason == 'contained' and decision.basis == 'sampled'
        assert decision.coverage >= cc.MIN_COVERAGE and decision.support_seconds >= cc.MIN_SUPPORT_SECONDS
        assert elapsed < CPU_CEILING_SECONDS, elapsed
        assert 0 < len(matched_inputs) <= cc.MAX_MATCHER_CALLS
        assert sum(tokens for _, tokens, _ in matched_inputs) <= cc.MAX_COMPARED_TOKENS
        assert sum(cells for _, _, cells in matched_inputs) <= cc.MAX_TOKEN_COMPARISONS
        assert len({u_words for u_words, _, _ in matched_inputs}) <= 32


def test_full_population_two_hour_pair_abstains_on_matcher_budget(monkeypatch):
    pendant, desktop = long_pair.long_complementary_pair()
    calls = []
    monkeypatch.setattr(cc, '_ordered_match', _counting_matcher(calls))
    for first, second in ((pendant, desktop), (desktop, pendant)):
        calls.clear()
        start = time.process_time()
        decision = cc.measure_capture_containment(first, second, mode='on')
        elapsed = time.process_time() - start
        assert not decision.would_join and decision.reason == 'bounds_matcher_calls' and decision.basis == 'full'
        assert len(calls) == cc.MAX_MATCHER_CALLS == 128 and elapsed < CPU_CEILING_SECONDS


def test_two_hour_unrelated_pendant_never_joins():
    pendant, desktop = long_pair.long_unrelated_pair()
    for first, second in ((pendant, desktop), (desktop, pendant)):
        decision = cc.measure_capture_containment(first, second, mode='shadow')
        assert not decision.would_join and decision.reason in ('timing', 'insufficient_coverage')


def test_out_of_window_text_is_skipped_before_character_accounting():
    pendant, laptop = complementary_pair()
    laptop['finished_at'] = T0 + timedelta(seconds=7200)
    laptop['transcript_segments'] += [
        {'text': 'x' * 5000, 'start': float(start), 'end': float(start) + 2.0, 'is_user': False}
        for start in range(400, 7000, 10)
    ]
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.would_join and decision.reason == 'contained'


def test_raw_segment_overflow_rejects_even_when_mostly_out_of_window():
    pendant, laptop = complementary_pair()
    laptop['finished_at'] = T0 + timedelta(seconds=9000)
    laptop['transcript_segments'] += [
        {'text': 'pad', 'start': float(start), 'end': float(start) + 1.0, 'is_user': False}
        for start in range(400, 4500)
    ]
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds_segments'


def test_utterance_sample_is_evenly_strided_with_endpoints():
    eligible = [(T0, T0, ('w%03d' % index,)) for index in range(100)]
    sample = cc._sample_utterances(eligible)
    assert len(sample) == cc.MAX_SMALLER_UTTERANCES == 32
    assert all(weight == 1 for _, _, _, weight in sample)
    indices = [
        index
        for index, item in enumerate(eligible)
        if (item[0], item[1], item[2]) in [(s, e, w) for s, e, w, _ in sample]
    ]
    assert indices == [i * 99 // 31 for i in range(32)]
    assert indices[0] == 0 and indices[-1] == 99


def test_utterance_sample_follows_word_mass_not_utterance_count():
    eligible = [(T0, T0, ('w%03d' % index,) * (8 if index % 2 == 0 else 120)) for index in range(40)]
    sample = cc._sample_utterances(eligible)
    assert len(sample) <= cc.MAX_SMALLER_UTTERANCES
    assert len({(s, e, w) for s, e, w, _ in sample}) == len(sample)
    assert sum(weight for _, _, _, weight in sample) == cc.MAX_SMALLER_UTTERANCES == 32
    assert any(weight > 1 for _, _, _, weight in sample)
    chosen = [(s, e, w) for s, e, w, _ in sample]
    assert chosen[0] == eligible[0] and chosen[-1] == eligible[-1]
    indices = [index for index, item in enumerate(eligible) if item in chosen]
    assert indices != [i * 39 // 31 for i in range(len(indices))]


def test_utterance_sample_weights_equal_words_when_unsampled():
    eligible = [(T0, T0, ('w%03d' % index,) * (index + 8)) for index in range(32)]
    sample = cc._sample_utterances(eligible)
    assert [(s, e, w) for s, e, w, _ in sample] == eligible
    assert all(weight == len(words) for _, _, words, weight in sample)


def test_length_skewed_pair_cannot_confirm_under_word_mass_sampling():
    pendant, desktop = long_pair.length_skewed_pair()
    for first, second in ((pendant, desktop), (desktop, pendant)):
        decision = cc.measure_capture_containment(first, second, mode='shadow')
        assert not decision.would_join and decision.coverage < cc.MIN_COVERAGE


def test_collapsed_quantile_hits_retain_weight_in_coverage():
    pendant, desktop = long_pair.quantile_collapse_pair()
    for first, second in ((pendant, desktop), (desktop, pendant)):
        decision = cc.measure_capture_containment(first, second, mode='shadow')
        assert not decision.would_join
        assert decision.coverage == pytest.approx(22 / 32) and decision.coverage < cc.MIN_COVERAGE
    eligible = [(T0, T0, tuple(seg['text'].split())) for seg in pendant['transcript_segments']]
    sample = cc._sample_utterances(eligible)
    assert sum(weight for _, _, _, weight in sample) == 32
    mass_weight = sum(weight for _, _, words, weight in sample if words[0].startswith('mass'))
    assert mass_weight == 22


def test_filler_between_every_target_token_still_rejects():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'] = [
        segment(' filler '.join(text.split()), start + 3.0) for text, start in zip(UTTERANCES, UTTERANCE_TIMES)
    ]
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'timing' and decision.matched_words == 0


@pytest.mark.parametrize('mode', ['on', 'shadow'])
def test_only_matching_prefix_of_a_long_capture_cannot_confirm(mode):
    times = [40.0 + 20.0 * index for index in range(64)]
    pendant_texts = [' '.join('a%02dw%d' % (index, word) for word in range(16)) for index in range(64)]
    laptop_texts = [
        transcript_variant(text) if index < 32 else ' '.join('b%02dw%d' % (index, word) for word in range(17))
        for index, text in enumerate(pendant_texts)
    ]
    pendant = row('pendant', 'omi', 0, 1400, [segment(text, t, end=t + 8.0) for text, t in zip(pendant_texts, times)])
    laptop = row('laptop', 'desktop', 0, 1400, [segment(text, t, end=t + 8.0) for text, t in zip(laptop_texts, times)])
    decision = cc.measure_capture_containment(pendant, laptop, mode=mode)
    assert not decision.would_join and decision.reason == 'insufficient_coverage'
    assert decision.basis == ('sampled' if mode == 'shadow' else 'full')
    assert 0 < decision.matched_utterances <= 32


@pytest.mark.parametrize('mode', ['on', 'shadow'])
def test_sampled_match_cannot_erase_majority_non_user_speech(mode):
    user_times = [40.0 + 12.0 * index for index in range(40)]
    pendant_texts = [' '.join('c%02dw%d' % (index, word) for word in range(16)) for index in range(40)]
    non_user = [
        segment(
            ' '.join('n%03dw%d' % (index, word) for word in range(10)),
            600.0 + 2.0 * index,
            is_user=False,
            end=601.0 + 2.0 * index,
        )
        for index in range(200)
    ]
    pendant = row(
        'pendant',
        'omi',
        0,
        1020,
        [segment(text, t, end=t + 8.0) for text, t in zip(pendant_texts, user_times)] + non_user,
    )
    laptop = row(
        'laptop',
        'desktop',
        0,
        1020,
        [segment(transcript_variant(text), t, end=t + 8.0) for text, t in zip(pendant_texts, user_times)]
        + [dict(item) for item in non_user],
    )
    decision = cc.measure_capture_containment(pendant, laptop, mode=mode)
    assert not decision.would_join and decision.reason == 'insufficient_coverage'
    assert decision.smaller_words == 2640


@pytest.mark.parametrize('reason', list(cc._REASONS))
def test_every_fixed_reason_survives_the_log_allowlist(caplog, reason):
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        cc.record_capture_containment(cc.CaptureContainment(False, reason), mode='shadow')
    assert len(caplog.records) == 1
    assert 'reason=%s jev_p=unavailable' % reason in caplog.records[0].message
    assert 'reason=bounds ' not in caplog.records[0].message


@pytest.mark.parametrize('mode', ['on', 'shadow'])
def test_favorable_subset_is_rejected_only_by_the_full_population(mode):
    pendant, desktop = long_pair.favorable_subset_pair()
    assert not measure_shared_speech(pendant['transcript_segments'], desktop['transcript_segments']).confirms()
    for first, second in ((pendant, desktop), (desktop, pendant)):
        decision = cc.measure_capture_containment(first, second, mode=mode)
        if mode == 'shadow':
            assert decision.would_join and decision.basis == 'sampled'
            assert decision.coverage == pytest.approx(0.8125)
            continue
        assert not decision.would_join and decision.reason == 'insufficient_coverage' and decision.basis == 'full'
        assert decision.matched_words == 32 * 13 and decision.smaller_words == 64 * 16
        assert decision.coverage == 0.40625
        default = cc.measure_capture_containment(first, second)
        assert default == decision


@pytest.mark.parametrize('mode', ['on', 'shadow'])
def test_favorable_subset_budget_abstention_reports_its_basis(monkeypatch, mode):
    monkeypatch.setattr(cc, 'MAX_MATCHER_CALLS', 2)
    pendant, desktop = long_pair.favorable_subset_pair()
    for first, second in ((pendant, desktop), (desktop, pendant)):
        decision = cc.measure_capture_containment(first, second, mode=mode)
        assert not decision.would_join and decision.reason == 'bounds_matcher_calls'
        assert decision.basis == ('sampled' if mode == 'shadow' else 'full')
        assert decision.matched_words == 0 and decision.coverage == 0.0


def _clamped_boundary_pair(start_slop=0.25, end_slop=0.25):
    """Same-origin pair whose utterances slightly overrun the capture window."""
    times = [(-start_slop, 12.0), (80.0, 92.0), (140.0, 152.0), (288.0, 300.0 + end_slop)]
    pendant = row('pendant', 'omi', 0, 300, [segment(text, s, end=e) for text, (s, e) in zip(UTTERANCES, times)])
    laptop_segments = []
    for index, (text, (s, e)) in enumerate(zip(UTTERANCES, times)):
        laptop_segments.append(segment(transcript_variant(text), s, end=e))
        if index < len(UTTERANCES) - 1:
            laptop_segments.append(segment(REMOTE_FILLER, 20.0 + 40.0 * index, is_user=False, end=32.0 + 40.0 * index))
    laptop_segments.sort(key=lambda item: item['start'])
    laptop = row('laptop', 'desktop', 0, 300, laptop_segments)
    return pendant, laptop


def test_boundary_segments_clamp_to_the_capture_window():
    pendant, laptop = _clamped_boundary_pair()
    originals = deepcopy([item['transcript_segments'] for item in (pendant, laptop)])
    for first, second in ((pendant, laptop), (laptop, pendant)):
        decision = cc.measure_capture_containment(first, second)
        assert decision.would_join and decision.reason == 'contained'
        assert decision.matched_words == 52 and decision.smaller_words == 64
        assert decision.support_seconds == 48.0 and decision.coverage == 0.8125
        assert decision.dropped_segments == 0
    assert [item['transcript_segments'] for item in (pendant, laptop)] == originals


@pytest.mark.parametrize(
    'start,end',
    [(-2.0, 10.0), (296.0, 302.0)],
)
def test_exact_window_slop_tolerance_is_allowed(start, end):
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'].append(
        {'text': 'edge padding remark words', 'start': start, 'end': end, 'is_user': False, 'speaker': 'SPEAKER_00'}
    )
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.would_join and decision.reason == 'contained'


@pytest.mark.parametrize(
    'start,end',
    [(-2.001, 10.0), (296.0, 302.001)],
)
def test_beyond_window_slop_tolerance_rejects(start, end):
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'].append(
        {'text': 'edge padding remark words', 'start': start, 'end': end, 'is_user': False, 'speaker': 'SPEAKER_00'}
    )
    assert cc.measure_capture_containment(pendant, laptop).reason == 'layout_window_slop'


@pytest.mark.parametrize('start,end', [(-1.0, -0.1), (300.0, 301.0)])
def test_wholly_out_of_window_intervals_reject(start, end):
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'].append(
        {'text': 'outside entirely', 'start': start, 'end': end, 'is_user': False, 'speaker': 'SPEAKER_00'}
    )
    assert cc.measure_capture_containment(pendant, laptop).reason == 'layout_out_of_window'


def test_raw_duration_bound_applies_before_clamping():
    pendant, laptop = complementary_pair()
    laptop['started_at'] = T0
    laptop['transcript_segments'].append(
        {'text': 'long edge interval', 'start': -1.0, 'end': 90.0, 'is_user': False, 'speaker': 'SPEAKER_00'}
    )
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds_segment_seconds'


def test_degenerate_durations_are_dropped_and_counted():
    pendant, laptop = complementary_pair()
    pendant['transcript_segments'].append(segment('spoken extra words here', 80.0, end=80.0))
    laptop['transcript_segments'].append(segment('more extra words now', 100.0, end=99.0))
    for first, second in ((pendant, laptop), (laptop, pendant)):
        decision = cc.measure_capture_containment(first, second)
        assert decision.would_join and decision.reason == 'contained'
        assert decision.matched_words == 52 and decision.dropped_segments == 2


def test_all_degenerate_pair_reports_drops_without_user_speech():
    small = row('pendant', 'omi', 0, 300, [segment('a b c', 80.0, end=80.0)])
    large = row('laptop', 'desktop', 0, 300, [segment('d e f', 100.0, end=99.0)])
    for first, second in ((small, large), (large, small)):
        decision = cc.measure_capture_containment(first, second)
        assert not decision.would_join and decision.reason == 'no_user_speech'
        assert decision.dropped_segments == 2


def _union_overlap_pair(times):
    texts = [' '.join('f%du%d' % (index, word) for word in range(16)) for index in range(4)]
    pendant = row('pendant', 'omi', 0, 300, [segment(text, s, end=e) for text, (s, e) in zip(texts, times)])
    laptop_segments = [segment(transcript_variant(text), s, end=e) for text, (s, e) in zip(texts, times)]
    laptop_segments.append(segment(REMOTE_FILLER, 230.0, is_user=False, end=250.0))
    laptop_segments.sort(key=lambda item: item['start'])
    return pendant, row('laptop', 'desktop', 0, 300, laptop_segments)


def test_matched_support_uses_interval_union_not_interval_sum():
    pendant, laptop = _union_overlap_pair([(80.0, 92.0), (90.0, 102.0), (140.0, 151.0), (200.0, 211.0)])
    for first, second in ((pendant, laptop), (laptop, pendant)):
        decision = cc.measure_capture_containment(first, second)
        assert not decision.would_join and decision.reason == 'too_small'
        assert decision.matched_words == 52 and decision.matched_utterances == 4
        assert decision.coverage == 0.8125 and decision.support_seconds == 44.0


def test_nested_match_intervals_contribute_union_support_only():
    pendant, laptop = _union_overlap_pair([(80.0, 100.0), (90.0, 95.0), (140.0, 152.0), (200.0, 212.0)])
    for first, second in ((pendant, laptop), (laptop, pendant)):
        decision = cc.measure_capture_containment(first, second)
        assert not decision.would_join and decision.reason == 'too_small'
        assert decision.support_seconds == 44.0


@pytest.mark.parametrize('mode', ['on', 'shadow'])
def test_exact_half_overlap_ratio_allows_one_duplicate_each(mode):
    canonical = cc.measure_capture_containment(*complementary_pair())
    for order in (('pendant', 'laptop'), ('laptop', 'pendant')):
        pendant, laptop = complementary_pair()
        pendant['transcript_segments'] += [dict(item) for item in pendant['transcript_segments']]
        laptop['transcript_segments'] += [dict(item) for item in laptop['transcript_segments'] if item['is_user']]
        rows = {'pendant': pendant, 'laptop': laptop}
        decision = cc.measure_capture_containment(rows[order[0]], rows[order[1]], mode=mode)
        assert decision == canonical
        assert decision.matched_words == 52 and decision.support_seconds == 48.0


def test_just_over_half_overlap_ratio_rejects_before_matching(monkeypatch):
    pendant, laptop = complementary_pair()
    pendant['transcript_segments'] += [dict(item) for item in pendant['transcript_segments']]
    laptop['transcript_segments'] += [dict(item) for item in laptop['transcript_segments'] if item['is_user']]
    pendant['transcript_segments'].append(segment('nested one two three four five six seven', 80.0, end=80.001))
    calls = []
    monkeypatch.setattr(cc, '_ordered_match', _counting_matcher(calls))
    for first, second in ((pendant, laptop), (laptop, pendant)):
        decision = cc.measure_capture_containment(first, second)
        assert not decision.would_join and decision.reason == 'layout_overlap_ratio'
    assert not calls


@pytest.mark.parametrize('mode', ['on', 'shadow'])
def test_distinct_text_on_an_identical_interval_is_not_deduped(mode):
    unrelated = ' '.join('u5w%d' % index for index in range(16))
    for order in (('pendant', 'laptop'), ('laptop', 'pendant')):
        pendant, laptop = complementary_pair()
        pendant['transcript_segments'].append(segment(unrelated, 80.0, end=92.0))
        rows = {'pendant': pendant, 'laptop': laptop}
        decision = cc.measure_capture_containment(rows[order[0]], rows[order[1]], mode=mode)
        assert not decision.would_join and decision.reason == 'insufficient_coverage'
        assert decision.smaller_words == 80 and decision.matched_words == 52
        assert decision.support_seconds == 48.0
