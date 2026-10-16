"""Unlabelled (speech=all) containment fallback contracts.

When the smaller capture carries no explicit ``is_user is True`` speech, the
detector falls back to matching all normalized smaller-side speech against all
normalized larger-side speech under stricter floors. The complementary fixture
is tuned so the shipped exact-trigram rule cannot confirm (12 < 15 shared
trigrams) while ordered coverage stays at ~0.857 >= 0.85.
"""

import json
import logging
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from database import capture_groups as groups_db
from database import conversations as conversations_db
from models.conversation import Conversation
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import capture_containment as cc
from utils.conversations import capture_jev_shadow as shadow
from utils.conversations import duplicate_capture as policy
from utils.conversations.shared_speech import measure_shared_speech

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
UID = 'synthetic-unlabelled-user'

ALL_UTTERANCES = [
    'we must deliver the revised sensor assembly before friday because customers expect reliable battery performance immediately in every region this quarter',
    'please ask the factory manager whether replacement microphones arrived today and confirm shipping dates tomorrow morning with the logistics team on site',
    'our launch checklist includes firmware calibration acoustic testing supplier approval packaging review and updated installation instructions for installers and technicians',
    'finance should authorize the vendor deposit after procurement verifies quantities serial numbers warranty terms and invoices this afternoon without further delay',
]
ALL_TIMES = [80.0, 140.0, 200.0, 260.0]
REMOTE_SPEECH = 'remote voice filler jargon aside tangent remark aside ' * 3


def unlabelled_variant(text, substitutions=3):
    """Sparse ASR noise: substitutions plus five filler insertions per utterance."""
    words = text.split()
    if substitutions == 4:
        words[4], words[8], words[12], words[16] = 'zzzfive', 'zzznine', 'zzzthirteen', 'zzzseventeen'
    elif substitutions == 3:
        words[4], words[8], words[12] = 'zzzfive', 'zzznine', 'zzzthirteen'
    elif substitutions == 2:
        words[4], words[8] = 'zzzfive', 'zzznine'
    for position, filler in ((20, 'mm'), (16, 'er'), (11, 'hm'), (7, 'hum'), (2, 'uh')):
        words.insert(min(position, len(words)), filler)
    return ' '.join(words)


def segment(text, start, end=None, **extra):
    item = {
        'text': text,
        'start': start,
        'end': start + 16.0 if end is None else end,
        'speaker': 'SPEAKER_00',
    }
    item.update(extra)
    return item


def row(id, source, start=0, end=600, segments=None, **extra):
    return {
        'id': id,
        'source': source,
        'status': 'completed',
        'discarded': False,
        'started_at': T0 + timedelta(seconds=start),
        'finished_at': T0 + timedelta(seconds=end),
        'created_at': T0,
        'structured': {},
        'transcript_segments': segments if segments is not None else [],
        'external_data': {},
        **extra,
    }


def path(id, uid=UID):
    return ('users', uid, 'conversations', id)


def unlabelled_pair(texts=None, times=None, duration=16.0, variant=None, laptop_is_user=False):
    """Pendant holds only unlabelled speech; the laptop adds remote turns.

    The laptop clock started three seconds earlier, so a +6s capture-local
    offset leaves a 3s residual skew inside the 12s window.
    """
    texts = ALL_UTTERANCES if texts is None else texts
    times = ALL_TIMES if times is None else times
    variant = unlabelled_variant if variant is None else variant
    pendant_segments = [segment(text, start, end=start + duration, is_user=False) for text, start in zip(texts, times)]
    laptop_segments = []
    for index, (text, start) in enumerate(zip(texts, times)):
        laptop_segments.append(segment(variant(text), start + 6.0, end=start + 6.0 + duration, is_user=laptop_is_user))
        if index < len(texts) - 1:
            laptop_segments.append(segment(REMOTE_SPEECH, start + 11.0, end=start + 31.0, is_user=laptop_is_user))
    laptop_segments.sort(key=lambda item: item['start'])
    pendant = row('pendant', 'omi', 0, 300, pendant_segments)
    laptop = row('laptop', 'desktop', -3, 303, laptop_segments)
    return pendant, laptop


def containment_lines(caplog):
    return [r.message for r in caplog.records if 'event=capture_group_containment' in r.message]


def test_unlabelled_pair_baseline_symmetric_rule_cannot_confirm():
    pendant, laptop = unlabelled_pair()
    shared = measure_shared_speech(pendant['transcript_segments'], laptop['transcript_segments'])
    assert not shared.confirms() and shared.shared_trigrams < 15


def test_unlabelled_pair_joins_in_both_orders_under_all_speech():
    pendant, laptop = unlabelled_pair()
    for first, second in ((pendant, laptop), (laptop, pendant)):
        for mode in ('on', 'shadow'):
            decision = cc.measure_capture_containment(first, second, mode=mode)
            assert decision.would_join and decision.reason == 'contained'
            assert decision.speech == 'all' and decision.basis == 'full'
            assert decision.matched_words == 72 and decision.smaller_words == 84
            assert decision.matched_utterances == 4 and decision.distinct_words >= 20
            assert decision.support_seconds == 64.0 and decision.coverage == pytest.approx(72 / 84)


def test_unlabelled_evidence_uses_all_speech_method_with_numeric_keys():
    pendant, laptop = unlabelled_pair()
    record = cc.measure_capture_containment(pendant, laptop).evidence()
    assert record['method'] == 'all_speech_containment'
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


def test_dict_and_model_rows_agree_on_the_all_path():
    pendant, laptop = unlabelled_pair()
    model = Conversation(**laptop)
    assert cc.measure_capture_containment(pendant, model) == cc.measure_capture_containment(pendant, laptop)


@pytest.mark.parametrize('label', [False, 'missing', 'none', 'string'])
def test_false_missing_none_or_string_labels_count_unlabelled(label):
    pendant, laptop = unlabelled_pair()
    for item in pendant['transcript_segments']:
        if label == 'missing':
            item.pop('is_user', None)
        elif label == 'none':
            item['is_user'] = None
        elif label == 'string':
            item['is_user'] = 'yes'
        else:
            item['is_user'] = label
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.would_join and decision.speech == 'all'


def test_any_true_label_on_the_smaller_side_prevents_fallback():
    pendant, laptop = unlabelled_pair()
    pendant['transcript_segments'][0]['is_user'] = True
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.speech == 'user' and decision.reason == 'no_user_speech'
    pendant, laptop = unlabelled_pair(laptop_is_user=True)
    pendant['transcript_segments'].append(segment('tiny user remark', 100.0, end=103.0, is_user=True))
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.speech == 'user'
    assert not decision.would_join and decision.matched_words == 0
    assert decision.reason == 'timing'


def test_larger_side_labels_are_irrelevant_on_the_all_path():
    pendant, unlabelled_laptop = unlabelled_pair()
    _, labelled_laptop = unlabelled_pair(laptop_is_user=True)
    by_unlabelled = cc.measure_capture_containment(pendant, unlabelled_laptop)
    by_labelled = cc.measure_capture_containment(pendant, labelled_laptop)
    assert by_labelled == by_unlabelled and by_unlabelled.speech == 'all'


def test_true_labels_on_both_sides_keep_the_user_path():
    pendant, laptop = unlabelled_pair(laptop_is_user=True)
    for item in pendant['transcript_segments']:
        item['is_user'] = True
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.speech == 'user'
    assert decision.would_join and decision.reason == 'contained'
    assert decision.coverage == pytest.approx(72 / 84)


def test_mixed_labels_keep_exact_user_path_decision():
    pendant, laptop = unlabelled_pair(laptop_is_user=True)
    for item in pendant['transcript_segments'][:3]:
        item['is_user'] = True
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.speech == 'user'
    assert decision.matched_utterances == 3 and decision.matched_words == 54
    assert decision.smaller_words == 84 and decision.coverage == pytest.approx(54 / 84)
    assert not decision.would_join and decision.reason == 'insufficient_coverage'


def test_empty_smaller_speech_returns_bounded_no_speech():
    pendant, laptop = unlabelled_pair()
    pendant['transcript_segments'] = [segment('   ', 80.0, end=81.0)]
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'no_speech' and decision.speech == 'all'
    pendant, laptop = unlabelled_pair()
    laptop['transcript_segments'] = [segment('   ', 80.0, end=81.0)]
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'no_speech' and decision.speech == 'all'


def _seam_pair(texts, times, durations, substitutions=3):
    return unlabelled_pair(
        texts=texts,
        times=times,
        duration=durations,
        variant=lambda text: unlabelled_variant(text, substitutions=substitutions),
    )


def test_all_floor_coverage_between_user_and_all_thresholds_rejects():
    texts = [' '.join('c%du%d' % (index, word) for word in range(22)) for index in range(4)]
    pendant, laptop = _seam_pair(texts, ALL_TIMES, 16.0, substitutions=4)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.speech == 'all'
    assert decision.reason == 'insufficient_coverage'
    assert decision.matched_words == 72 and decision.smaller_words == 88
    assert cc.MIN_COVERAGE <= decision.coverage < cc.MIN_ALL_COVERAGE
    assert decision.matched_utterances >= cc.MIN_ALL_MATCHED_UTTERANCES
    assert decision.support_seconds >= cc.MIN_ALL_SUPPORT_SECONDS


def test_all_floor_matched_words_rejects():
    texts = [' '.join('m%du%d' % (index, word) for word in range(16)) for index in range(4)]
    pendant, laptop = _seam_pair(texts, ALL_TIMES, 16.0, substitutions=2)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.speech == 'all'
    assert decision.reason == 'too_small'
    assert cc.MIN_MATCHED_WORDS <= decision.matched_words < cc.MIN_ALL_MATCHED_WORDS
    assert decision.coverage >= cc.MIN_ALL_COVERAGE
    assert decision.matched_utterances >= cc.MIN_ALL_MATCHED_UTTERANCES
    assert decision.support_seconds >= cc.MIN_ALL_SUPPORT_SECONDS


def test_all_floor_distinct_utterances_rejects():
    texts = [' '.join('u%du%d' % (index, word) for word in range(25)) for index in range(3)]
    times = [80.0, 160.0, 240.0]
    pendant, laptop = _seam_pair(texts, times, 21.0, substitutions=3)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.speech == 'all'
    assert decision.reason == 'too_small'
    assert decision.matched_utterances == cc.MIN_MATCHED_UTTERANCES == 3
    assert decision.matched_words >= cc.MIN_ALL_MATCHED_WORDS
    assert decision.coverage >= cc.MIN_ALL_COVERAGE
    assert decision.support_seconds >= cc.MIN_ALL_SUPPORT_SECONDS


def test_all_floor_support_seconds_rejects():
    texts = [' '.join('s%du%d' % (index, word) for word in range(17)) for index in range(5)]
    times = [80.0, 140.0, 200.0, 260.0, 320.0]
    pendant, laptop = unlabelled_pair(
        texts=texts,
        times=times,
        duration=11.0,
        variant=lambda text: unlabelled_variant(text, substitutions=2),
    )
    pendant['finished_at'] = T0 + timedelta(seconds=360)
    laptop['finished_at'] = T0 + timedelta(seconds=363)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.speech == 'all'
    assert decision.reason == 'too_small'
    assert cc.MIN_SUPPORT_SECONDS <= decision.support_seconds < cc.MIN_ALL_SUPPORT_SECONDS
    assert decision.matched_words >= cc.MIN_ALL_MATCHED_WORDS
    assert decision.matched_utterances >= cc.MIN_ALL_MATCHED_UTTERANCES
    assert decision.coverage >= cc.MIN_ALL_COVERAGE


def test_all_floor_smaller_words_rejects_before_matching():
    texts = [' '.join('t%du%d' % (index, word) for word in range(14)) for index in range(4)]
    pendant, laptop = _seam_pair(texts, ALL_TIMES, 16.0, substitutions=2)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.speech == 'all'
    assert decision.reason == 'too_small'
    assert cc.MIN_SMALLER_WORDS <= decision.smaller_words < cc.MIN_ALL_SMALLER_WORDS
    assert decision.matched_words == 0


def test_repeated_identical_utterance_counts_once_on_all_path():
    pendant, laptop = unlabelled_pair(
        texts=[ALL_UTTERANCES[0]] * 4,
        times=ALL_TIMES,
    )
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.speech == 'all'
    assert decision.matched_utterances == 1


def test_union_support_not_span_on_all_path():
    times = [80.0, 86.0, 200.0, 206.0]
    pendant, laptop = unlabelled_pair(times=times, duration=16.0)
    for item in laptop['transcript_segments']:
        if item['text'] == REMOTE_SPEECH:
            item['speaker'] = 'SPEAKER_01'
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.speech == 'all'
    assert decision.reason == 'too_small'
    assert decision.support_seconds == 44.0
    assert decision.support_seconds < cc.MIN_ALL_SUPPORT_SECONDS


def test_full_denominator_includes_unmatched_and_short_words():
    pendant, laptop = unlabelled_pair()
    extra = [' '.join('e%du%d' % (index, word) for word in range(20)) for index in range(2)]
    pendant['transcript_segments'] += [segment(text, 10.0 + index * 30.0) for index, text in enumerate(extra)]
    pendant['transcript_segments'].append(segment('short unmatched remark', 50.0, end=52.0))
    laptop['transcript_segments'].append(segment('different extra words entirely', 20.0, end=40.0))
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.speech == 'all'
    assert decision.reason == 'insufficient_coverage'
    assert decision.smaller_words == 84 + 40 + 3 and decision.coverage < cc.MIN_ALL_COVERAGE


def test_overlapping_target_members_never_bundle_on_all_path():
    for order in (('pendant', 'laptop'), ('laptop', 'pendant')):
        pendant, laptop = unlabelled_pair()
        rebuilt = []
        for item in laptop['transcript_segments']:
            if item['start'] != 86.0:
                rebuilt.append(item)
                continue
            tokens = item['text'].split()
            rebuilt += [
                segment(' '.join(tokens[:14]), item['start'], end=item['end']),
                segment(' '.join(tokens[14:]), item['start'], end=item['end']),
            ]
        laptop['transcript_segments'] = rebuilt
        rows = {'pendant': pendant, 'laptop': laptop}
        decision = cc.measure_capture_containment(rows[order[0]], rows[order[1]])
        assert not decision.would_join and decision.speech == 'all'


def test_same_audio_time_aligned_still_joins_known_limitation():
    """Unattributed fallback joins genuinely same audio by design.

    Matching all speech cannot distinguish the wearer from time-aligned
    background media playing in both rooms, so identical audio at the same
    times joins; the decision is content containment, not event-identity proof.
    """
    media = [' '.join('a%du%d' % (index, word) for word in range(24)) for index in range(4)]
    pendant, laptop = _seam_pair(media, ALL_TIMES, 16.0, substitutions=3)
    decision = cc.measure_capture_containment(pendant, laptop)
    assert decision.would_join and decision.speech == 'all'


def test_same_transcript_misaligned_beyond_skew_rejects():
    pendant, laptop = unlabelled_pair()
    for item in laptop['transcript_segments']:
        item['start'] += 20.0
        item['end'] += 20.0
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.speech == 'all' and decision.reason == 'timing'


def test_unrelated_overlap_with_generic_phrases_stays_separate():
    texts = [
        'yeah okay sounds good let me know how it goes and we can talk more about it later this week',
        'sure that works for me thanks again for the update and see you soon at the next meeting',
        'right exactly that makes sense to me as well so keep me posted on what happens next please',
        'no worries at all take care and have a great rest of your day talk soon bye for now',
    ]
    stranger = row(
        'stranger',
        'desktop',
        -3,
        303,
        [segment(text, start + 6.0) for text, start in zip(texts, ALL_TIMES)],
    )
    pendant, _ = unlabelled_pair()
    decision = cc.measure_capture_containment(pendant, stranger)
    assert not decision.would_join and decision.speech == 'all' and decision.reason == 'timing'


def test_background_media_with_different_content_stays_separate():
    texts = [' '.join('b%du%d' % (index, word) for word in range(21)) for index in range(4)]
    media = row(
        'media',
        'desktop',
        -3,
        303,
        [segment(text, start + 6.0) for text, start in zip(texts, ALL_TIMES)],
    )
    pendant, _ = unlabelled_pair()
    decision = cc.measure_capture_containment(pendant, media)
    assert not decision.would_join and decision.speech == 'all' and decision.reason == 'timing'


def test_partial_phrase_overlap_fails_coverage():
    pendant, _ = unlabelled_pair()
    mixed = row(
        'mixed',
        'desktop',
        -3,
        303,
        [
            segment(unlabelled_variant(ALL_UTTERANCES[0]), 86.0),
            segment(unlabelled_variant(ALL_UTTERANCES[1]), 146.0),
            segment(' '.join('xw%d' % word for word in range(30)), 206.0),
            segment(' '.join('yw%d' % word for word in range(30)), 266.0),
        ],
    )
    decision = cc.measure_capture_containment(pendant, mixed)
    assert not decision.would_join and decision.speech == 'all'


def test_sampled_all_basis_remains_sampled():
    texts = [' '.join('p%03du%d' % (index, word) for word in range(16)) for index in range(40)]
    times = [40.0 + 20.0 * index for index in range(40)]
    pendant, laptop = unlabelled_pair(texts=texts, times=times, duration=8.0)
    pendant['finished_at'] = laptop['finished_at'] = T0 + timedelta(seconds=900)
    laptop['finished_at'] = T0 + timedelta(seconds=903)
    sampled = cc.measure_capture_containment(pendant, laptop, mode='shadow')
    assert sampled.speech == 'all' and sampled.basis == 'sampled'
    full = cc.measure_capture_containment(pendant, laptop, mode='on')
    assert full.speech == 'all' and full.basis == 'full'


def test_budget_exhaustion_preserves_all_speech_label(monkeypatch, caplog):
    monkeypatch.setattr(cc, 'MAX_MATCHER_CALLS', 2)
    pendant, laptop = unlabelled_pair()
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'bounds_matcher_calls'
    assert decision.speech == 'all' and decision.basis == 'full'
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        cc.record_capture_containment(decision, mode='shadow')
    assert caplog.records[0].message.endswith('speech=all')


def test_log_line_appends_speech_label(caplog):
    decision = cc.CaptureContainment(True, 'contained', 72, 84, 4, 66, 64.0, 0.8571)
    object.__setattr__(decision, 'speech', 'all')
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        cc.record_capture_containment(decision, mode='on', phase='rule')
    assert caplog.records[0].message == (
        'event=capture_group_containment mode=on phase=rule would_join=true '
        'reason=contained jev_p=unavailable basis=full dropped_segments=0 speech=all'
    )


@pytest.mark.parametrize('value', ['user', 'all', 'bogus', 42])
def test_log_speech_label_is_allowlisted_and_clamped(caplog, value):
    decision = cc.CaptureContainment(False, 'timing')
    object.__setattr__(decision, 'speech', value)
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        cc.record_capture_containment(decision, mode='shadow')
    expected = value if value in ('user', 'all') else 'user'
    assert caplog.records[0].message.endswith('speech=%s' % expected)


@pytest.fixture
def seam(monkeypatch):
    store = StrictFirestore()
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(groups_db, 'get_firestore_client', lambda: store)

    def query(uid, *, status, finished_after, limit):
        rows = [
            deepcopy(r)
            for p, r in store.rows.items()
            if p[:2] == ('users', uid) and r['status'] == status and r['finished_at'] >= finished_after
        ]
        return sorted(rows, key=lambda r: r['finished_at'])[:limit]

    monkeypatch.setattr(conversations_db, 'get_conversations_finished_after', query)
    events = []
    monkeypatch.setattr(policy, 'record_product_event', lambda event, **kw: events.append((event, kw.get('outcome'))))
    monkeypatch.setattr(policy, 'submit_same_scene', lambda *args: None)
    monkeypatch.setattr(policy, 'submit_resummary', lambda *args: None)
    return {'store': store, 'events': events}


@pytest.mark.parametrize('last', ['pendant', 'laptop'])
def test_on_mode_joins_unlabelled_pair_with_all_speech_evidence(seam, monkeypatch, last, caplog):
    monkeypatch.setenv(cc.MODE_ENV, 'on')
    pendant, laptop = unlabelled_pair()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    before = deepcopy(seam['store'].rows)
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path(last)]))
    record = seam['store'].rows[path('pendant')].get('capture_group')
    assert record and record == seam['store'].rows[path('laptop')].get('capture_group')
    assert {m['id'] for m in record['members']} == {'pendant', 'laptop'}
    assert {m['evidence']['method'] for m in record['members']} == {'all_speech_containment'}
    evidence = next(m['evidence'] for m in record['members'])
    assert evidence['matched_words'] == 72 and evidence['smaller_words'] == 84
    assert ('capture_group_joined', 'applied') in seam['events']
    lines = containment_lines(caplog)
    assert len(lines) == 1
    assert lines[0] == (
        'event=capture_group_containment mode=on phase=rule would_join=true '
        'reason=contained jev_p=unavailable basis=full dropped_segments=0 speech=all'
    )
    assert all(token not in '\n'.join(lines) for token in (UID, 'pendant', 'laptop', 'sensor'))
    for cid in ('pendant', 'laptop'):
        strip = {k: v for k, v in seam['store'].rows[path(cid)].items() if k != 'capture_group'}
        original = {k: v for k, v in before[path(cid)].items() if k != 'external_data'}
        assert {k: v for k, v in strip.items() if k != 'external_data'} == original


def test_shadow_logs_unlabelled_positive_without_grouping(seam, monkeypatch, caplog):
    monkeypatch.setenv(cc.MODE_ENV, 'shadow')
    pendant, laptop = unlabelled_pair()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    before = deepcopy(seam['store'].rows)
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    assert all('capture_group' not in r for r in seam['store'].rows.values())
    assert ('capture_group_joined', 'none') in seam['events']
    lines = containment_lines(caplog)
    assert len(lines) == 1
    assert 'mode=shadow' in lines[0] and 'would_join=true' in lines[0] and 'speech=all' in lines[0]
    for cid in ('pendant', 'laptop'):
        after = {k: v for k, v in seam['store'].rows[path(cid)].items() if k != 'external_data'}
        prior = {k: v for k, v in before[path(cid)].items() if k != 'external_data'}
        assert after == prior


def test_off_mode_never_measures_or_logs_unlabelled(seam, monkeypatch, caplog):
    monkeypatch.setenv(cc.MODE_ENV, 'off')
    detector = MagicMock(side_effect=AssertionError('detector must not run'))
    monkeypatch.setattr(policy, 'measure_capture_containment', detector)
    pendant, laptop = unlabelled_pair()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    detector.assert_not_called()
    assert not containment_lines(caplog)
    assert all('capture_group' not in r for r in seam['store'].rows.values())


REPO = Path(__file__).resolve().parents[3]
BASE_COMMIT = 'c1d08dd2a6df3859550d3f1c8718fb379a7b913e'


def _baseline_policy():
    source = subprocess.run(
        ['git', 'show', f'{BASE_COMMIT}:backend/utils/conversations/duplicate_capture.py'],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    name = 'duplicate_capture_baseline'
    module = ModuleType(name)
    module.__file__ = str(REPO / 'backend/utils/conversations/duplicate_capture.py')
    sys.modules[name] = module
    try:
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


def _run_capture_flow(module, rows, last_id, monkeypatch, caplog):
    store = StrictFirestore()
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(groups_db, 'get_firestore_client', lambda: store)

    def query(uid, *, status, finished_after, limit):
        found = [
            deepcopy(r)
            for p, r in store.rows.items()
            if p[:2] == ('users', uid) and r['status'] == status and r['finished_at'] >= finished_after
        ]
        return sorted(found, key=lambda r: r['finished_at'])[:limit]

    monkeypatch.setattr(conversations_db, 'get_conversations_finished_after', query)
    store.rows.update({path(key): deepcopy(value) for key, value in rows.items()})
    events = []
    monkeypatch.setattr(module, 'record_product_event', lambda event, **kw: events.append((event, kw.get('outcome'))))
    monkeypatch.setattr(module, 'submit_same_scene', lambda *args: None)
    monkeypatch.setattr(module, 'submit_resummary', lambda *args: None)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        module.link_duplicate_captures(UID, Conversation(**deepcopy(rows[last_id])))
    return store, events, [record.message for record in caplog.records]


def _snapshot(store):
    rows = json.dumps([[list(key), value] for key, value in sorted(store.rows.items())], sort_keys=True, default=str)
    updates = json.dumps(
        [[list(p), payload] for transaction in store.transactions for p, payload in transaction.updates],
        sort_keys=True,
        default=str,
    )
    return rows, updates


@pytest.mark.parametrize('mode', ['off', 'typo'])
def test_disabled_mode_is_identical_to_baseline(monkeypatch, caplog, mode):
    baseline = _baseline_policy()
    if mode == 'typo':
        monkeypatch.setenv(cc.MODE_ENV, 'shadow-typo')
    else:
        monkeypatch.setenv(cc.MODE_ENV, 'off')
    pendant, laptop = unlabelled_pair()
    rows = {'pendant': pendant, 'laptop': laptop}
    baseline_state = _run_capture_flow(baseline, rows, 'laptop', monkeypatch, caplog)
    current_state = _run_capture_flow(policy, rows, 'laptop', monkeypatch, caplog)
    assert _snapshot(baseline_state[0]) == _snapshot(current_state[0])
    assert baseline_state[1] == current_state[1]
    assert baseline_state[2] == current_state[2]


def test_jev_companion_reports_all_speech_label(seam, monkeypatch, caplog):
    monkeypatch.setenv(cc.MODE_ENV, 'shadow')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_UID_ALLOWLIST', UID)
    monkeypatch.setattr(shadow, 'submit_with_context', lambda _executor, fn, *args: fn(*args))
    pendant, laptop = unlabelled_pair()
    rows = {'pendant': pendant, 'laptop': laptop}
    monkeypatch.setattr(
        shadow.conversations_db, 'get_conversation_for_capture_check', lambda uid, cid: (rows[cid], 'fingerprint')
    )
    monkeypatch.setattr(shadow, '_cap', lambda *args: 'admitted')

    class Answer:
        served_model = 'typesafe/jev-1.13'

        def noul(self, name):
            return 0.75

    monkeypatch.setattr(shadow, 'ask_jev', lambda *args, **kwargs: Answer())
    monkeypatch.setattr(shadow, '_record', lambda record: None)
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        shadow.submit_same_scene(UID, 'pendant', 'laptop')
    lines = containment_lines(caplog)
    assert len(lines) == 1
    assert lines[0] == (
        'event=capture_group_containment mode=shadow phase=jev would_join=true '
        'reason=contained jev_p=0.750000 basis=full dropped_segments=0 speech=all'
    )


def test_empty_pair_reports_no_speech_all():
    pendant, laptop = unlabelled_pair()
    pendant['transcript_segments'] = []
    laptop['transcript_segments'] = []
    decision = cc.measure_capture_containment(pendant, laptop)
    assert not decision.would_join and decision.reason == 'no_speech' and decision.speech == 'all'


def _floor_pair(kind):
    if kind == 'coverage':
        texts = [' '.join('c%du%d' % (index, word) for word in range(22)) for index in range(4)]
        return _seam_pair(texts, ALL_TIMES, 16.0, substitutions=4)
    if kind == 'matched':
        texts = [' '.join('m%du%d' % (index, word) for word in range(16)) for index in range(4)]
        return _seam_pair(texts, ALL_TIMES, 16.0, substitutions=2)
    if kind == 'utterances':
        texts = [' '.join('u%du%d' % (index, word) for word in range(25)) for index in range(3)]
        return _seam_pair(texts, [80.0, 160.0, 240.0], 21.0, substitutions=3)
    if kind == 'support':
        texts = [' '.join('s%du%d' % (index, word) for word in range(17)) for index in range(5)]
        pendant, laptop = unlabelled_pair(
            texts=texts,
            times=[80.0, 140.0, 200.0, 260.0, 320.0],
            duration=11.0,
            variant=lambda text: unlabelled_variant(text, substitutions=2),
        )
        pendant['finished_at'] = T0 + timedelta(seconds=360)
        laptop['finished_at'] = T0 + timedelta(seconds=363)
        return pendant, laptop
    if kind == 'smalltalk':
        texts = [
            'yeah that sounds good to me let me know when you are free and we can catch up properly over coffee this weekend together soon',
            'no worries at all thanks for checking in on that and have a great rest of your evening talk soon bye for now take care always',
            'right exactly i agree completely so keep me posted on what happens next and we can review it together tomorrow morning then',
        ]
        return _seam_pair(texts, [80.0, 160.0, 240.0], 21.0, substitutions=3)
    if kind == 'generic':
        generic = 'yeah okay sounds good let me know how it goes and we can talk more about it later this week for sure'
        unique = [' '.join('g%du%d' % (index, word) for word in range(20)) for index in range(3)]
        other = [' '.join('h%du%d' % (index, word) for word in range(20)) for index in range(3)]
        pendant = row(
            'pendant',
            'omi',
            0,
            300,
            [segment(generic, 80.0, is_user=False)]
            + [segment(t, s, is_user=False) for t, s in zip(unique, [140.0, 200.0, 260.0])],
        )
        laptop = row(
            'laptop',
            'desktop',
            -3,
            303,
            [segment(unlabelled_variant(generic), 86.0, is_user=False)]
            + [segment(t, s, is_user=False) for t, s in zip(other, [146.0, 206.0, 266.0])],
        )
        return pendant, laptop
    if kind == 'media':
        texts = [' '.join('b%du%d' % (index, word) for word in range(21)) for index in range(4)]
        pendant, _ = unlabelled_pair()
        media = row(
            'laptop',
            'desktop',
            -3,
            303,
            [segment(t, s + 6.0, is_user=False) for t, s in zip(texts, ALL_TIMES)],
        )
        return pendant, media
    if kind == 'partial_media':
        pendant, _ = unlabelled_pair()
        mixed = row(
            'laptop',
            'desktop',
            -3,
            303,
            [
                segment(unlabelled_variant(ALL_UTTERANCES[0]), 86.0, is_user=False),
                segment(unlabelled_variant(ALL_UTTERANCES[1]), 146.0, is_user=False),
                segment(' '.join('xw%d' % word for word in range(30)), 206.0, is_user=False),
                segment(' '.join('yw%d' % word for word in range(30)), 266.0, is_user=False),
            ],
        )
        return pendant, mixed
    if kind == 'shifted':
        pendant, laptop = unlabelled_pair()
        for item in laptop['transcript_segments']:
            item['start'] += 20.0
            item['end'] += 20.0
        return pendant, laptop
    raise AssertionError(kind)


ALL_NEGATIVE_KINDS = [
    'coverage',
    'matched',
    'utterances',
    'support',
    'smalltalk',
    'generic',
    'media',
    'partial_media',
    'shifted',
]


@pytest.mark.parametrize('kind', ALL_NEGATIVE_KINDS)
def test_on_mode_never_groups_unlabelled_negative_pairs(seam, monkeypatch, caplog, kind):
    monkeypatch.setenv(cc.MODE_ENV, 'on')
    pendant, laptop = _floor_pair(kind)
    assert not measure_shared_speech(pendant['transcript_segments'], laptop['transcript_segments']).confirms()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    assert all('capture_group' not in r for r in seam['store'].rows.values())
    assert ('capture_group_joined', 'none') in seam['events']
    lines = containment_lines(caplog)
    assert len(lines) == 1
    assert 'would_join=false' in lines[0] and 'speech=all' in lines[0]


@pytest.mark.parametrize('kind', ALL_NEGATIVE_KINDS)
def test_shadow_logs_unlabelled_negative_pairs_without_grouping(seam, monkeypatch, caplog, kind):
    monkeypatch.setenv(cc.MODE_ENV, 'shadow')
    pendant, laptop = _floor_pair(kind)
    assert not measure_shared_speech(pendant['transcript_segments'], laptop['transcript_segments']).confirms()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    before = deepcopy(seam['store'].rows)
    with caplog.at_level(logging.INFO, logger=cc.logger.name):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    assert all('capture_group' not in r for r in seam['store'].rows.values())
    lines = containment_lines(caplog)
    assert len(lines) == 1
    assert 'mode=shadow' in lines[0] and 'would_join=false' in lines[0] and 'speech=all' in lines[0]
    for cid in ('pendant', 'laptop'):
        after = {k: v for k, v in seam['store'].rows[path(cid)].items() if k != 'external_data'}
        prior = {k: v for k, v in before[path(cid)].items() if k != 'external_data'}
        assert after == prior


def test_sampled_all_decision_cannot_authorize_a_join(seam, monkeypatch):
    monkeypatch.setenv(cc.MODE_ENV, 'on')
    pendant, laptop = unlabelled_pair()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    sampled = cc.CaptureContainment(True, 'contained', 72, 84, 4, 66, 64.0, 0.86, basis='sampled', speech='all')
    monkeypatch.setattr(policy, 'measure_capture_containment', lambda *args, **kwargs: sampled)
    policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    assert all('capture_group' not in r for r in seam['store'].rows.values())
    assert ('capture_group_joined', 'none') in seam['events']
