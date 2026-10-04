"""Pure detector contracts for time-aligned user-utterance containment.

Synthetic transcripts only; the complementary pair is tuned so the shipped
exact-trigram rule cannot confirm (8 < 15 shared trigrams) while token
coverage stays at 0.8125 >= 0.8.
"""

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from models.conversation import Conversation
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
        'end': start + 8.0 if end is None else end,
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
        assert decision.support_seconds == 188.0 and decision.coverage == 0.8125


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
        item['is_user'] = False
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'no_user_speech'


def test_missing_or_unknown_user_attribution_fails_closed():
    pendant, laptop = complementary_pair()
    for item in laptop['transcript_segments']:
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


@pytest.mark.parametrize('bad', [{'start': 'x'}, {'end': float('nan')}, {'start': True}, {'start': 9.0, 'end': 5.0}])
def test_malformed_segment_times_fail_closed(bad):
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0].update(bad)
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'


def test_unplaced_or_crossing_segments_fail_closed():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0]['audio_alignment'] = 'unplaced'
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0]['end'] = 4000.0
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'


def test_bounds_overflow_never_accepts_a_prefix():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'] = laptop['transcript_segments'] + [
        {'text': '', 'start': float(i), 'end': float(i) + 0.5, 'is_user': False} for i in range(cc.MAX_SEGMENTS + 5)
    ]
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'] = 'not a segment list'
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'


def test_oversized_in_window_segments_fail_closed():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0] = segment(' '.join(['word'] * 200), 83.0, end=183.0)
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'


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
        'event=capture_group_containment mode=shadow phase=jev would_join=true ' 'reason=contained jev_p=0.750000'
    )
    assert lines[1] == (
        'event=capture_group_containment mode=off phase=rule would_join=false ' 'reason=timing jev_p=unavailable'
    )


def test_log_labels_and_score_are_clamped(caplog):
    decision = SimpleNamespace(would_join=False, reason='not-a-reason')
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        cc.record_capture_containment(decision, mode='bogus', phase='bogus', jev_p=1.5)
    assert caplog.records[0].message == (
        'event=capture_group_containment mode=off phase=rule would_join=false ' 'reason=ineligible jev_p=unavailable'
    )


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
    pendant = row('pendant', 'omi', 0, 300, [segment(text, start) for text, start in zip(fragments, times)])
    laptop = row('laptop', 'desktop', 0, 300, [segment(text, start) for text, start in zip(fragments, times)])
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'too_small'


def test_two_large_matched_utterances_do_not_join():
    texts = [text + ' extra' + ' word' * 7 for text in UTTERANCES[:2]]
    texts = [' '.join(text.split()[:24]) for text in texts]
    times = [80.0, 200.0]
    pendant = row('pendant', 'omi', 0, 300, [segment(text, start) for text, start in zip(texts, times)])
    laptop = row(
        'laptop', 'desktop', 0, 300, [segment(transcript_variant(text), start) for text, start in zip(texts, times)]
    )
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'too_small' and decision.matched_utterances == 2


def test_segment_character_bound_rejects():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0] = segment('averyverylongtokenword ' * 104, 83.0)
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'


def test_capture_character_bound_rejects():
    text = 'averyverylongtokenw ' * 100
    segments = [segment(text, index * 9.0) for index in range(66)]
    pendant, _ = complementary_pair()
    laptop = row('laptop', 'desktop', 0, 600, segments)
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'


def test_capture_word_bound_rejects():
    text = ' '.join('word%03d' % index for index in range(124))
    segments = [segment(text, index * 10.0) for index in range(130)]
    pendant = row('pendant', 'omi', 0, 1300, segments)
    laptop = row('laptop', 'desktop', 0, 1300, [dict(item) for item in segments])
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'


def test_segment_word_bound_rejects():
    text = ' '.join('word%03d' % index for index in range(129))
    pendant = row('pendant', 'omi', 0, 300, [segment(text, 80.0)])
    laptop = row('laptop', 'desktop', 0, 300, [segment(text, 80.0)])
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'


def test_segment_duration_bound_rejects():
    pendant = row('pendant', 'omi', 0, 300, [segment(UTTERANCES[0], 80.0, end=171.0)])
    laptop = row('laptop', 'desktop', 0, 300, [segment(UTTERANCES[0], 80.0, end=171.0)])
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'


def test_target_candidate_overflow_rejects():
    small_texts = [UTTERANCES[0]] + [' '.join('s%d_%d' % (index, word) for word in range(12)) for index in range(3)]
    times = [100.0, 140.0, 200.0, 260.0]
    pendant = row('pendant', 'omi', 0, 300, [segment(text, start) for text, start in zip(small_texts, times)])
    targets = [
        segment(' '.join('t%d_%d' % (index, word) for word in range(8)), 90.0 + index, end=90.0 + index + 1.0)
        for index in range(20)
    ]
    laptop = row('laptop', 'desktop', 0, 300, targets)
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'


def test_negative_segment_time_rejects():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0]['start'] = -2.0
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'


def test_segment_end_past_capture_window_rejects():
    pendant, laptop = complementary_pair()
    laptop['transcript_segments'][0]['end'] = 400.0
    assert cc.measure_capture_containment(pendant, laptop).reason == 'bounds'


def _pair_with_laptop_split(splits):
    pendant, laptop = complementary_pair()
    tokens = transcript_variant(UTTERANCES[0]).split()
    bounds = [83.0 + index * (8.0 / splits) for index in range(splits + 1)]
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
