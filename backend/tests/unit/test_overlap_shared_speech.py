"""Synthetic acceptance and hard negatives for overlapping sentence evidence."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from config.capture_shared_speech import shared_speech_mode
from utils.conversations import overlap_shared_speech as matcher

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
SENTENCES = [
    'The orange telescope needs a polished mirror before our mountain observatory opens tomorrow morning',
    'Please deliver twelve wooden benches beside the eastern garden while gardeners plant violet flowers',
    'Our ceramic workshop will display handmade blue bowls near the central library next Saturday afternoon',
]


def row(offset=0, skew=0, texts=None):
    return {
        'id': f'synthetic-{offset}',
        'source': 'omi',
        'status': 'completed',
        'started_at': T0 + timedelta(seconds=offset),
        'finished_at': T0 + timedelta(seconds=300),
        'transcript_segments': [
            {'start': time - offset + skew, 'end': time - offset + skew + 8, 'text': text}
            for time, text in zip((60, 100, 140), texts or SENTENCES)
        ],
    }


def test_same_sentences_ignore_punctuation_case_diarization_and_account_for_origins():
    first, second = row(), row(offset=5, skew=4, texts=[text.upper() + '!!!' for text in SENTENCES])
    for segment in second['transcript_segments']:
        segment.update(speaker_id=17, is_user=False)
    decision = matcher.measure_overlap_shared_speech(first, second)
    assert decision.would_join and decision.matched_sentences == 3
    assert decision == matcher.measure_overlap_shared_speech(second, first)
    assert all(text not in str(decision.evidence()) for text in SENTENCES)


@pytest.mark.parametrize('case', ['silent', 'outside_overlap', 'time_shift', 'repetition', 'one_sentence', 'different'])
def test_false_fold_classes_abstain(case):
    first, second = row(), row(offset=5)
    if case == 'silent':
        second['transcript_segments'] = []
    elif case == 'outside_overlap':
        second['started_at'] = T0 + timedelta(seconds=200)
        second['finished_at'] = T0 + timedelta(seconds=500)
        second['transcript_segments'] = deepcopy(first['transcript_segments'])
    elif case == 'time_shift':
        second = row(skew=60)
    elif case == 'repetition':
        first, second = row(texts=[SENTENCES[0]] * 3), row(texts=[SENTENCES[0]] * 3)
    elif case == 'one_sentence':
        first['transcript_segments'] = first['transcript_segments'][:1]
        second['transcript_segments'] = second['transcript_segments'][:1]
    else:
        second = row(texts=['zebra quartz tundra silver meadow frozen glacier across narrow valleys quietly'] * 3)
    assert not matcher.measure_overlap_shared_speech(first, second).would_join


@pytest.mark.parametrize('value', [None, '60', float('nan'), float('inf'), True, 10**1000])
def test_invalid_timing_abstains(value):
    first, second = row(), row()
    for segment in second['transcript_segments']:
        segment['start'] = value
    decision = matcher.measure_overlap_shared_speech(first, second)
    assert not decision.would_join and decision.reason == 'insufficient_speech'
    assert decision.dropped_segments == 3


@pytest.mark.parametrize('case', ['long_line', 'too_many', 'huge_text', 'unplaced', 'straddle', 'lock', 'deleted'])
def test_untrusted_layout_and_privacy_fail_closed(case):
    first, second = row(), row()
    if case == 'long_line':
        for segment in second['transcript_segments']:
            segment['end'] = segment['start'] + 100
    elif case == 'too_many':
        second['transcript_segments'] *= matcher.MAX_SEGMENTS
    elif case == 'huge_text':
        second['transcript_segments'][0]['text'] = 'word ' * matcher.MAX_SEGMENT_CHARS
    elif case == 'unplaced':
        for segment in second['transcript_segments']:
            segment['audio_alignment'] = 'unplaced'
    elif case == 'straddle':
        # None of the words in this long boundary-crossing line prove overlap speech.
        second['started_at'] = T0 + timedelta(seconds=145)
        second['finished_at'] = T0 + timedelta(seconds=445)
        first['transcript_segments'] = [{'text': ' '.join(SENTENCES), 'start': 0, 'end': 149}]
    elif case == 'lock':
        second['is_locked'] = True
    else:
        second['deleted'] = True
    assert not matcher.measure_overlap_shared_speech(first, second).would_join


def test_sparse_asr_substitutions_still_match():
    variant = [
        text.replace('mirror', 'reflector').replace('twelve', 'eleven').replace('blue', 'green') for text in SENTENCES
    ]
    assert matcher.measure_overlap_shared_speech(row(), row(texts=variant)).would_join


def test_word_bag_with_reversed_order_is_not_shared_sentence():
    reversed_words = [' '.join(reversed(text.split())) for text in SENTENCES]
    assert not matcher.measure_overlap_shared_speech(row(), row(texts=reversed_words)).would_join


def test_brief_shared_phrases_cannot_borrow_silence_for_speech_duration():
    first, second = row(), row()
    for record in (first, second):
        for segment in record['transcript_segments']:
            segment['end'] = segment['start'] + 1
    decision = matcher.measure_overlap_shared_speech(first, second)
    assert not decision.would_join and decision.matched_speech_seconds == 3


def test_out_of_capture_sentence_cannot_complete_short_overlap_evidence():
    first, second = row(), row()
    first['transcript_segments'] = [
        {'start': 0, 'end': 15, 'text': SENTENCES[0] + ' bright stars shimmer overhead'},
        {'start': 15, 'end': 17, 'text': SENTENCES[1]},
    ]
    second['transcript_segments'] = deepcopy(first['transcript_segments'])
    second['finished_at'] = T0 + timedelta(seconds=15)
    assert not matcher.measure_overlap_shared_speech(first, second).would_join


def test_overlap_boundary_margin_cannot_supply_whole_sentence_words():
    first, second = row(), row()
    second['started_at'] = T0 + timedelta(seconds=65)
    second['finished_at'] = T0 + timedelta(seconds=300)
    # Only the final original line fits wholly in the actual intersection on both sides.
    first['transcript_segments'] = first['transcript_segments'][:2]
    second['transcript_segments'] = [
        {'start': 0, 'end': 8, 'text': SENTENCES[0]},
        {'start': 35, 'end': 43, 'text': SENTENCES[1]},
    ]
    decision = matcher.measure_overlap_shared_speech(first, second)
    assert not decision.would_join


@pytest.mark.parametrize('field,value', [('has_transcript_corrections', True), ('transcript_correction_overlay', {})])
def test_mutable_transcript_corrections_abstain(field, value):
    first, second = row(), row()
    second[field] = value
    assert matcher.measure_overlap_shared_speech(first, second).reason == 'transcript_corrections'


def test_epoch_rounding_is_clamped_to_capture_and_overlap_bounds():
    first, second = row(), row()
    first['transcript_segments'][0].update(start=-0.0000005, end=8)
    second['transcript_segments'][0].update(start=0, end=8)
    decision = matcher.measure_overlap_shared_speech(first, second)
    assert decision.would_join and decision.matched_speech_seconds == 24


def test_sub_microsecond_line_cannot_supply_sentence_evidence():
    first, second = row(), row()
    for record in (first, second):
        record['transcript_segments'] = [
            {'start': 0, 'end': 15, 'text': SENTENCES[0] + ' bright stars shimmer overhead'},
            {'start': 15, 'end': 15.0000005, 'text': SENTENCES[1]},
        ]
    assert not matcher.measure_overlap_shared_speech(first, second).would_join


def test_dense_layout_abstains_at_bounded_comparison_budget(monkeypatch):
    monkeypatch.setattr(matcher, 'MAX_COMPARISONS', 1)
    assert matcher.measure_overlap_shared_speech(row(), row()).reason == 'bounds'


def test_mode_defaults_and_cohort_are_fail_closed(monkeypatch):
    for key in ('CAPTURE_SHARED_SPEECH_MODE', 'CAPTURE_SHARED_SPEECH_UID_ALLOWLIST', 'CAPTURE_SHARED_SPEECH_PERCENT'):
        monkeypatch.delenv(key, raising=False)
    assert shared_speech_mode('synthetic') == 'off'
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'on')
    assert shared_speech_mode('synthetic') == 'off'
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_UID_ALLOWLIST', ' synthetic ')
    assert shared_speech_mode('synthetic') == 'on'
    assert shared_speech_mode('other') == 'off'
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_PERCENT', '100')
    assert shared_speech_mode('other') == 'on'
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_PERCENT', 'nan')
    assert shared_speech_mode('other') == 'off'
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'typo')
    assert shared_speech_mode('synthetic') == 'off'


def test_percentage_is_stable_and_shadow_is_scoped(monkeypatch):
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_MODE', 'shadow')
    monkeypatch.setenv('CAPTURE_SHARED_SPEECH_PERCENT', '5')
    monkeypatch.delenv('CAPTURE_SHARED_SPEECH_UID_ALLOWLIST', raising=False)
    modes = [shared_speech_mode(f'synthetic-{i}') for i in range(1000)]
    assert modes == [shared_speech_mode(f'synthetic-{i}') for i in range(1000)]
    assert 20 < modes.count('shadow') < 80


def test_isolated_bad_line_cannot_supply_evidence_or_veto_strong_proven_speech():
    first, second = row(), row()
    second['transcript_segments'].append({'start': None, 'end': None, 'text': 'uncertain placement'})
    decision = matcher.measure_overlap_shared_speech(first, second)
    assert decision.would_join and decision.matched_sentences == 3
    assert decision.dropped_segments == 1 and decision.unknown_words == 2
    assert decision.window_jaccard < 1


def test_unknown_speech_is_charged_against_window_similarity():
    first, second = row(), row()
    second['transcript_segments'].append(
        {'start': None, 'end': None, 'text': ' '.join(f'unknown{i}' for i in range(200))}
    )
    decision = matcher.measure_overlap_shared_speech(first, second)
    assert not decision.would_join and decision.reason == 'window_text'
    assert decision.unknown_words == 200 and decision.window_jaccard < 0.25
