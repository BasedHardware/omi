"""Synthetic recorded-clock contracts; no model calls or customer fixtures."""

from copy import deepcopy
import base64
from datetime import datetime, timedelta, timezone
import json
import random
import zlib

import pytest

from utils.conversations.v3 import outline, planner

NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def recording(cid='r', at=NOW, segments=None, **extra):
    return {
        'id': cid,
        'started_at': at,
        'source': 'omi',
        'recording': True,
        'transcript_segments': segments or [{'text': 'hello world', 'start': 0, 'end': 10, 'is_user': True}],
        **extra,
    }


def entry(first=1, **extra):
    return {
        'first_line': first,
        'title': 'A stable subject',
        'line': 'You made a plan.',
        'kind': 'conversation',
        'emoji': '🛠',
        'people': [],
        'sections': [],
        **extra,
    }


def test_five_minute_silence_boundary():
    row = recording(segments=[{'text': 'a', 'start': 0, 'end': 10}, {'text': 'b', 'start': 310, 'end': 320}])
    assert len(outline.stretches([row], NOW + timedelta(hours=1))) == 2
    row['transcript_segments'][1]['start'] = 309.999
    assert len(outline.stretches([row], NOW + timedelta(hours=1))) == 1


def test_three_hour_window_cap_is_deterministic_on_the_recorded_clock():
    def turns(start, stop):
        return [{'text': str(t), 'start': t, 'end': t + 10} for t in range(start, stop, 60)]

    rows = [
        recording('a', segments=turns(0, 5400)),
        recording('b', NOW + timedelta(seconds=5400), segments=turns(0, 5520)),
    ]
    now = NOW + timedelta(hours=3, minutes=2)
    cap = timedelta(hours=3)
    groups = outline.stretches(rows, now, max_window=cap)
    assert groups == outline.stretches(rows[::-1], now, max_window=cap)
    earlier, later = groups
    assert earlier['finished'] and earlier['outline_ready']
    assert earlier['window_cap_end'] and not earlier['manual_end']
    assert len(earlier['lines']) == 180
    assert later['after_window_cap'] and not later['finished']
    assert later['lines'][0]['start'] == NOW + cap

    (uncapped,) = outline.stretches(rows, now, max_window=timedelta(0))
    assert uncapped['key'] == earlier['key']
    assert uncapped['lines'] == earlier['lines'] + later['lines']
    assert not uncapped['finished']


@pytest.mark.parametrize('cohesion', [False, True])
def test_resume_does_not_rejoin_the_window_cap(cohesion):
    # After the existing two-hour card split, the tail and successor fit together
    # within two hours. Without the cap guard, resumes_previous can join them.
    row = recording(segments=[{'text': str(t), 'start': t, 'end': t + 10} for t in range(0, 10920, 60)])
    groups = outline.stretches([row], NOW + timedelta(hours=3, minutes=2), max_window=timedelta(hours=3))
    windows = planner.windows(
        groups, [[entry()], [entry(resumes_previous=True)]], cohesion=cohesion, silence_gap=timedelta(minutes=15)
    )
    assert [w['lines'][0]['start'] for w in windows] == [NOW, NOW + timedelta(hours=2), NOW + timedelta(hours=3)]
    assert [w['finished'] for w in windows] == [True, True, False]


def test_recorded_clock_and_near_duplicate():
    a = recording('a', segments=[{'text': 'We should meet at the office tomorrow morning.', 'start': 1, 'end': 11}])
    b = recording('b', segments=[{'text': 'we should meet at the office tomorrow morning', 'start': 2, 'end': 12}])
    groups = outline.stretches([a, b], NOW + timedelta(hours=1))
    assert len(groups[0]['lines']) == 1
    assert groups[0]['lines'][0]['start'] == NOW + timedelta(seconds=1)


def test_repeated_speech_in_one_recording_is_kept():
    said = 'Can you hear me now over there?'
    a = recording('a', segments=[{'text': said, 'start': t, 'end': t + 2} for t in (0, 5, 10)])
    groups = outline.stretches([a], NOW + timedelta(hours=1))
    assert [line['start'] for line in groups[0]['lines']] == [NOW + timedelta(seconds=t) for t in (0, 5, 10)]


def test_duplicate_capture_needs_overlapping_time():
    said = 'Can you hear me now over there?'
    a = recording('a', segments=[{'text': said, 'start': 0, 'end': 2}])
    overlapping = recording('b', segments=[{'text': said, 'start': 1, 'end': 3}])
    later = recording('c', segments=[{'text': said, 'start': 10, 'end': 12}])
    groups = outline.stretches([a, overlapping, later], NOW + timedelta(hours=1))
    assert [line['start'] for line in groups[0]['lines']] == [NOW, NOW + timedelta(seconds=10)]


def test_finished_fingerprint_invalidated_by_late_speech():
    row = recording()
    group = outline.stretches([row], NOW + timedelta(hours=1))[0]
    cached = [{**group, 'finished': True}]
    row['transcript_segments'].append({'text': 'new speech', 'start': 12, 'end': 20})
    assert outline.wanted(outline.stretches([row], NOW + timedelta(hours=1)), cached)


def test_deleted_spans_are_never_rederived():
    row = recording(deleted_spans=[{'start': NOW, 'end': NOW + timedelta(seconds=11)}])
    assert outline.stretches([row], NOW + timedelta(hours=1)) == []


def test_outline_contract_and_title_cap():
    group = outline.stretches([recording()], NOW + timedelta(hours=1))[0]
    parsed = outline.parse(
        json.dumps({'conversations': [entry(title='one two three four five six seven eight')]}), group
    )
    assert parsed[0]['title'] == 'one two three four five six seven'
    assert parsed[0]['first_line'] == 1
    with pytest.raises(ValueError):
        outline.parse(json.dumps({'conversations': [entry(first=True)]}), group)


def test_two_hour_cap_cuts_after_two_hours_whatever_the_outline_sections():
    # Live speech and outline revisions must not move a cut that locks the prefix (#25829 review).
    row = recording(segments=[{'text': str(i), 'start': i * 60, 'end': i * 60 + 10} for i in range(180)])
    groups = outline.stretches([row], NOW + timedelta(hours=4))
    windows = planner.windows(groups, [[entry(sections=[{'first_line': 91, 'title': 'Next subject'}])]])
    assert len(windows) == 2
    assert windows[1]['lines'][0]['start'] == NOW + timedelta(minutes=120)
    assert all(max(line['end'] for line in w['lines']) - w['lines'][0]['start'] <= timedelta(hours=2) for w in windows)


def _locked(segments, minutes):
    return {
        'id': 'locked',
        'status': 'completed',
        'started_at': NOW,
        'finished_at': NOW + timedelta(minutes=minutes, seconds=10),
        'transcript_segments': segments,
    }


@pytest.mark.parametrize('cohesion', [False, True])
def test_a_locked_row_that_holds_none_of_the_stretch_never_cuts_it(cohesion):
    # A separate locked card ending in a pause 20 minutes into an over-cap stretch owns none of its
    # speech, so the cap ignores it and cuts at two hours (#25829 review).
    row = recording(segments=[{'text': str(i), 'start': i * 60, 'end': i * 60 + 10} for i in range(180)])
    groups = outline.stretches([row], NOW + timedelta(hours=4))
    unrelated = _locked([{'id': 'elsewhere', 'text': 'other', 'start': 0, 'end': 5}], 20)
    ownership = planner.Ownership({'locked': unrelated}, {'r': {'claims': []}})
    windows = planner.windows(groups, [[entry()]], cohesion=cohesion, ownership=ownership)
    assert [w['lines'][0]['start'] for w in windows] == [NOW, NOW + timedelta(minutes=120)]


@pytest.mark.parametrize('cohesion', [False, True])
def test_a_locked_row_holding_the_stretch_start_keeps_its_cut(cohesion):
    segments = [{'text': str(i), 'start': i * 60, 'end': i * 60 + 10} for i in range(180)]
    groups = outline.stretches([recording(segments=segments)], NOW + timedelta(hours=4))
    prefix = _locked(deepcopy(segments[:21]), 20)
    ownership = planner.Ownership({'locked': prefix}, {'r': {'claims': []}})
    windows = planner.windows(groups, [[entry()]], cohesion=cohesion, ownership=ownership)
    # Its cut stays; the cap then counts from it (159 minutes remain, cut again at 141).
    assert [w['lines'][0]['start'] for w in windows] == [NOW, NOW + timedelta(minutes=21), NOW + timedelta(minutes=141)]
    assert windows[0]['finished']


def test_an_exact_hold_on_a_later_locked_row_beats_an_earlier_row_claim():
    # Two locked rows: the earlier one's window and audio claim cover the turn, the later one published
    # it exactly. Exact holds decide first, for the cap and the projection alike (#25829 review).
    segments = [{'id': 'x', 'text': 'held turn', 'start': 300, 'end': 330}]
    groups = outline.stretches([recording(segments=segments)], NOW + timedelta(hours=4))
    (line,) = groups[0]['lines']
    wide = {**_locked([], 10), 'id': 'wide', 'v3_recording_ids': ['r']}
    exact = {
        'id': 'exact',
        'status': 'completed',
        'v3_recording_ids': ['r'],
        'started_at': NOW + timedelta(seconds=300),
        'finished_at': NOW + timedelta(seconds=330),
        'transcript_segments': [{'id': 'x', 'text': 'held turn', 'start': 0.0, 'end': 30.0}],
    }
    existing = {'wide': wide, 'exact': exact}
    recordings = {'r': {'claims': [{'conversation_id': 'wide', 'start': NOW, 'end': NOW + timedelta(minutes=10)}]}}
    assert planner.Ownership(existing, recordings).owner_of(line)['id'] == 'exact'
    kept = planner.preserve_finished_windows(planner.windows(groups, [[entry()]]), existing, recordings)
    assert [w.get('existing_id') for w in kept] == ['exact']
    # The exact match needs the line's own recording.
    other = {**exact, 'v3_recording_ids': ['elsewhere']}
    assert planner.Ownership({'wide': wide, 'exact': other}, recordings).owner_of(line)['id'] == 'wide'


def test_a_source_qualified_exact_hold_beats_an_earlier_legacy_one():
    # A locked legacy row (no v3_recording_ids) and an open v3 row both publish the turn exactly; the
    # row that names the line's recording owns it, even though locked rows are scanned first.
    segments = [{'id': 'x', 'text': 'held turn', 'start': 300, 'end': 330}]
    groups = outline.stretches([recording(segments=segments)], NOW + timedelta(hours=4))
    (line,) = groups[0]['lines']
    held = [{'id': 'x', 'text': 'held turn', 'start': 0.0, 'end': 30.0}]
    span = {'started_at': NOW + timedelta(seconds=300), 'finished_at': NOW + timedelta(seconds=330)}
    legacy = {'id': 'legacy', 'status': 'completed', 'transcript_segments': held, **span}
    live = {'id': 'live', 'status': 'in_progress', 'v3_recording_ids': ['r'], 'transcript_segments': held, **span}
    assert planner.Ownership({'legacy': legacy, 'live': live}, {'r': {'claims': []}}).owner_of(line)['id'] == 'live'
    # With no source-qualified holder, the legacy exact hold still wins over containment.
    assert planner.Ownership({'legacy': legacy}, {'r': {'claims': []}}).owner_of(line)['id'] == 'legacy'


def _claimed_by(cid, minutes):
    return {'r': {'claims': [{'conversation_id': cid, 'start': NOW, 'end': NOW + timedelta(minutes=minutes)}]}}


def test_a_deleted_open_row_never_owns_a_line():
    # A deleted open card is left to the time-matched tombstone path, as before: it never takes a line
    # from the locked row whose claim covers it, even when it lists the exact segment.
    segments = [{'id': 'x', 'text': 'held turn', 'start': 300, 'end': 330}]
    groups = outline.stretches([recording(segments=segments)], NOW + timedelta(hours=4))
    (line,) = groups[0]['lines']
    locked = {**_locked([], 10), 'v3_recording_ids': ['r']}
    gone = {
        'id': 'gone',
        'status': 'in_progress',
        'deleted': True,
        'v3_recording_ids': ['r'],
        'started_at': NOW + timedelta(seconds=300),
        'finished_at': NOW + timedelta(seconds=330),
        'transcript_segments': [{'id': 'x', 'text': 'held turn', 'start': 0.0, 'end': 30.0}],
    }
    ownership = planner.Ownership({'locked': locked, 'gone': gone}, _claimed_by('locked', 10))
    assert ownership.owner_of(line)['id'] == 'locked'


def test_an_exact_hold_needs_the_same_timing():
    # A row holding the same segment id at another time does not hold this line; the claim decides.
    segments = [{'id': 'x', 'text': 'retimed turn', 'start': 400, 'end': 430}]
    groups = outline.stretches([recording(segments=segments)], NOW + timedelta(hours=4))
    (line,) = groups[0]['lines']
    stale = {
        'id': 'stale',
        'status': 'in_progress',
        'v3_recording_ids': ['r'],
        'started_at': NOW + timedelta(seconds=300),
        'finished_at': NOW + timedelta(seconds=500),
        'transcript_segments': [{'id': 'x', 'text': 'retimed turn', 'start': 0.0, 'end': 30.0}],
    }
    locked = {**_locked([], 10), 'v3_recording_ids': ['r']}
    ownership = planner.Ownership({'locked': locked, 'stale': stale}, _claimed_by('locked', 10))
    assert ownership.owner_of(line)['id'] == 'locked'


@pytest.mark.parametrize('cohesion', [False, True])
def test_a_tombstone_never_pins_a_cap_cut(cohesion):
    # A deleted locked card holding the first twenty minutes keeps its speech isolated in routing,
    # but the cap does not reuse its cut: the stretch is cut at two hours as if it were not there.
    segments = [{'text': str(i), 'start': i * 60, 'end': i * 60 + 10} for i in range(180)]
    groups = outline.stretches([recording(segments=segments)], NOW + timedelta(hours=4))
    tomb = {**_locked(deepcopy(segments[:21]), 20), 'deleted': True}
    ownership = planner.Ownership({'locked': tomb}, {'r': {'claims': []}})
    assert ownership.owner_of(groups[0]['lines'][0])['id'] == 'locked'  # routing still sees it
    windows = planner.windows(groups, [[entry()]], cohesion=cohesion, ownership=ownership)
    assert [w['lines'][0]['start'] for w in windows] == [NOW, NOW + timedelta(minutes=120)]


@pytest.mark.parametrize('gap', [5, 15.056, 20])
def test_model_resume_cannot_cross_recorded_silence(gap):
    a = recording('a')
    b = recording('b', NOW + timedelta(seconds=10, minutes=gap))
    groups = outline.stretches([a, b], NOW + timedelta(hours=4))
    assert len(groups) == 2
    assert len(planner.windows(groups, [[entry()], [entry(resumes_previous=True)]])) == 2


def test_model_resume_can_undo_a_topic_split_inside_continuous_speech():
    row = recording(segments=[{'text': 'one', 'start': 0, 'end': 10}, {'text': 'two', 'start': 309, 'end': 320}])
    groups = outline.stretches([row], NOW + timedelta(hours=4))
    windows = planner.windows(groups, [[entry(), entry(2, resumes_previous=True)]])
    assert len(windows) == 1
    assert len(windows[0]['lines']) == 2


def test_model_resume_keeps_overlapping_speech_in_one_window():
    row = recording(
        segments=[
            {'text': 'long opening turn', 'start': 0, 'end': 30},
            {'text': 'overlapping short turn', 'start': 10, 'end': 15},
            {'text': 'continuing overlapping turn', 'start': 20, 'end': 40},
        ]
    )
    groups = outline.stretches([row], NOW + timedelta(hours=1))
    assert len(groups) == 1
    windows = planner.windows(groups, [[entry(), entry(3, resumes_previous=True)]])
    assert len(windows) == 1
    assert [(line['segment']['start'], line['segment']['end']) for line in windows[0]['lines']] == [
        (0, 30),
        (10, 15),
        (20, 40),
    ]


@pytest.mark.parametrize('resume', [False, True])
def test_overlapping_turns_cannot_hide_a_window_end_beyond_the_cap(resume):
    segments = [{'text': f'turn {i}', 'start': i * 60, 'end': i * 60 + 55} for i in range(120)]
    segments.extend(
        {'text': f'overlapping turn {i}', 'start': start, 'end': end}
        for i, (start, end) in enumerate([(7188, 7198), (7190, 7195), (7192, 7204), (7193, 7199)])
    )
    row = recording(segments=segments)
    groups = outline.stretches([row], NOW + timedelta(hours=4))
    entries = [entry(), entry(123, resumes_previous=True)] if resume else [entry()]
    windows = planner.windows(groups, [entries])
    built = [planner.build('synthetic', window, {'r': row}) for window in windows]
    assert len(built) == 2
    assert all(window['finished_at'] - window['started_at'] <= timedelta(hours=2) for window in built)
    assert sum(len(window['transcript_segments']) for window in built) == len(segments)


@pytest.mark.parametrize('order', ['in_order', 'reversed', 'reconnect_first'])
def test_two_hour_exchange_stays_one_window_across_reconnects_and_arrival_order(order):
    # Same recorded shape as the incident: an unrelated family chat, a 15m pause,
    # then many short socket captures during an uninterrupted exchange. Text is synthetic.
    family = recording(
        'family', NOW - timedelta(minutes=45, seconds=3.345), segments=[{'text': 'family', 'start': 0, 'end': 1800}]
    )
    chunks = [
        recording(
            f'reconnect-{i}',
            NOW + timedelta(seconds=i * 60),
            segments=[{'id': f'line-{i}', 'text': f'fundraising turn {i}', 'start': 0, 'end': 60 if i == 119 else 55}],
        )
        for i in range(120)
    ]
    arrivals = [family, *chunks]
    if order == 'reversed':
        arrivals.reverse()
    elif order == 'reconnect_first':
        arrivals = [*chunks[::2], family, *chunks[1::2]]
    groups = outline.stretches(arrivals, NOW + timedelta(hours=3))
    windows = planner.windows(groups, [[entry()], [entry(resumes_previous=True)]])
    assert len(windows) == 2
    assert {line['conversation_id'] for line in windows[0]['lines']} == {'family'}
    built = planner.build('synthetic', windows[1], {r['id']: r for r in arrivals})
    assert built['finished_at'] - built['started_at'] == timedelta(hours=2)
    assert len(built['transcript_segments']) == 120
    assert len(built['v3_recording_ids']) == 120
    assert all(s['text'].startswith('fundraising') for s in built['transcript_segments'])


def test_explicit_end_finishes_at_once_without_shortening_automatic_boundary():
    end = NOW + timedelta(seconds=10)
    automatic = recording(finished_at=end)
    assert not outline.stretches([automatic], end + timedelta(seconds=30))[0]['finished']
    manual = dict(automatic, v3_manual_end=True)
    assert outline.stretches([manual], end)[0]['finished']


def test_new_people_prevent_resume():
    groups = outline.stretches([recording('a'), recording('b', NOW + timedelta(minutes=10))], NOW + timedelta(hours=4))
    assert len(planner.windows(groups, [[entry(people=['A'])], [entry(people=['B'], resumes_previous=True)]])) == 2


def test_split_retains_live_id_and_locked_title():
    row = recording(segments=[{'text': 'one', 'start': 0, 'end': 10}, {'text': 'two', 'start': 20, 'end': 30}])
    group = outline.stretches([row], NOW + timedelta(hours=1))[0]
    windows = planner.windows([group], [[entry(), entry(2, kind='voice_work')]])
    prior = {
        'id': 'live-id',
        'status': 'in_progress',
        'title_locked': True,
        'structured': {'title': 'Original title', 'emoji': '🌳'},
    }
    built = planner.build('synthetic', windows[0], {'r': row}, prior)
    assert built['id'] == 'live-id'
    assert built['structured']['title'] == 'Original title'
    assert [s['text'] for s in built['transcript_segments']] == ['one']
    assert planner.build('synthetic', windows[1], {'r': row})['id'] != 'live-id'


@pytest.mark.parametrize(
    'old,new,age,rewrites,expected',
    [
        (2000, 99, 1, 0, False),
        (2000, 100, 1, 0, True),
        (500, 49, 1, 0, False),
        (500, 50, 1, 0, True),
        (2000, 100, 24, 0, True),
        (2000, 100, 24.001, 0, False),
        (2000, 100, 1, 1, False),
        (500, 0, 1, 0, False),
    ],
)
def test_late_audio_threshold_edges(old, new, age, rewrites, expected):
    assert (
        planner.late_rewrite(
            previous_words=old, new_words=new, ended_at=NOW, now=NOW + timedelta(hours=age), rewrites=rewrites
        )
        is expected
    )


def test_manual_end_prevents_a_short_gap_resume():
    a = recording('a', finished_at=NOW + timedelta(seconds=10), v3_manual_end=True)
    b = recording('b', NOW + timedelta(seconds=30))
    groups = outline.stretches([a, b], NOW + timedelta(seconds=40))
    assert len(groups) == 2
    windows = planner.windows(groups, [[entry()], [entry(resumes_previous=True)]])
    assert len(windows) == 2
    assert windows[0]['finished'] is True
    assert windows[1]['finished'] is False


def test_rebuild_preserves_discard_lock_and_user_title():
    row = recording()
    group = outline.stretches([row], NOW + timedelta(hours=1))[0]
    window = planner.windows([group], [[entry()]])[0]
    prior = {
        'id': 'c',
        'status': 'in_progress',
        'discarded': True,
        'is_locked': True,
        'title_locked': True,
        'user_title': 'My edit',
        'structured': {'title': 'Kept title', 'emoji': '🌳'},
    }
    result = planner.build('u', window, {'r': row}, prior)
    assert result['discarded'] and result['is_locked'] and result['title_locked']
    assert result['user_title'] == 'My edit' and result['structured']['title'] == 'Kept title'
    # A paid-plan unlock already applied to the conversation must also survive.
    prior['is_locked'] = False
    row['is_locked'] = True
    assert planner.build('u', window, {'r': row}, prior)['is_locked'] is False


def test_manual_end_after_last_speech_closes_preceding_stretch():
    row = recording(finished_at=NOW + timedelta(seconds=25), v3_manual_end=True)
    group = outline.stretches([row], NOW + timedelta(seconds=30))[0]
    assert group['finished'] and group['manual_end']


def test_outline_fallback_is_valid_and_deterministic():
    group = outline.stretches([recording()], NOW + timedelta(hours=1))[0]
    entries = outline.fallback(group)
    assert entries == outline.fallback(group)
    assert outline.parse(json.dumps({'conversations': entries}), group)


@pytest.mark.parametrize(
    'text,words',
    [
        ('hello世界', 3),
        ('会議の時間です。', 7),
        ('今天开会。', 4),
        ('カタカナとｶﾅ', 7),
        ('한국어', 3),
        ('한국어', 3),
        ('ภาษาไทย', 7),
        ('สวัสดี', 4),
        ('ASCII\twith\nspace !', 4),
        ('Latin 世界，again', 4),
        ('', 0),
    ],
)
def test_transcript_word_floor_counts_mixed_script_without_punctuation(text, words):
    assert planner.word_count([{'text': text}]) == words


@pytest.mark.parametrize('letter', ['界', 'あ'])
@pytest.mark.parametrize('words', [149, 150])
def test_finished_script_aware_window_respects_home_word_floor(letter, words):
    row = recording(segments=[{'text': letter * words, 'start': 0, 'end': 10}])
    group = outline.stretches([row], NOW + timedelta(minutes=10))[0]
    window = planner.windows([group], [[entry()]])[0]
    assert window['finished']
    assert planner.build('u', window, {'r': row})['home_hidden'] is (words < 150)
    # Some projection callers supply no stretch count and use the copied segments.
    window.pop('_stretch_words', None)
    assert planner.build('u', window, {'r': row})['home_hidden'] is (words < 150)


@pytest.mark.parametrize('words', [5, 40])
def test_manual_end_with_any_speech_is_visible_and_sticky(words):
    row = recording(
        segments=[{'text': 'speech ' * words, 'start': 0, 'end': 10}],
        finished_at=NOW + timedelta(seconds=10),
        v3_manual_end=True,
    )
    group = outline.stretches([row], NOW + timedelta(seconds=11))[0]
    window = planner.windows([group], [[entry()]])[0]
    built = planner.build('u', window, {'r': row})
    assert built['manual_end'] is True and built['home_hidden'] is False
    built['status'] = 'completed'
    window['manual_end'] = False  # late audio no longer carries the original cut
    rebuilt = planner.build('u', window, {'r': row}, built)
    assert rebuilt['manual_end'] is True and rebuilt['home_hidden'] is False


@pytest.mark.parametrize('kind', ['media', 'background'])
@pytest.mark.parametrize('enabled,expected_hidden', [(True, False), (False, True)])
def test_manual_end_visibility_preserves_media_and_background_classification(kind, enabled, expected_hidden):
    row = recording(finished_at=NOW + timedelta(seconds=10), v3_manual_end=True)
    group = outline.stretches([row], NOW + timedelta(seconds=11))[0]
    built = planner.build(
        'u', planner.windows([group], [[entry(kind=kind)]])[0], {'r': row}, manual_end_home_visible=enabled
    )
    assert built['manual_end'] is True and built['home_hidden'] is expected_hidden
    assert built['kind'] == built['outline_kind'] == kind
    assert built['home_hidden_reason'] == ('media' if kind == 'media' else 'background_wearer_recognized')

    # Rebuilding a retained row can lack the cut on this pass. The row still owns the manual end.
    window = planner.windows([group], [[entry(kind=kind)]])[0]
    window['manual_end'] = False
    rebuilt = planner.build('u', window, {'r': row}, built, manual_end_home_visible=enabled)
    assert rebuilt['manual_end'] is True and rebuilt['home_hidden'] is expected_hidden


def test_only_final_fragment_of_manual_end_bypasses_classification():
    row = recording(
        segments=[
            {'text': 'broadcast', 'start': 0, 'end': 7190},
            {'text': 'another broadcast', 'start': 7200, 'end': 7210},
        ],
        finished_at=NOW + timedelta(seconds=7210),
        v3_manual_end=True,
    )
    groups = outline.stretches([row], NOW + timedelta(seconds=7211))
    windows = planner.windows(groups, [[entry(kind='media'), entry(2, kind='media')]])
    built = [planner.build('u', window, {'r': row}) for window in windows]
    assert [(r['manual_end'], r['home_hidden']) for r in built] == [(False, True), (True, False)]


def test_manual_end_without_speech_creates_no_window():
    row = recording(finished_at=NOW, v3_manual_end=True)
    row['transcript_segments'] = []
    assert planner.windows(outline.stretches([row], NOW), []) == []


@pytest.mark.parametrize(
    'recognized,words,expected_hidden', [(False, 150, False), (True, 150, True), (False, 149, True)]
)
def test_background_visibility_requires_wearer_recognition(recognized, words, expected_hidden):
    row = recording(segments=[{'id': 's', 'text': 'speech ' * words, 'start': 0, 'end': 10, 'is_user': recognized}])
    group = outline.stretches([row], NOW + timedelta(hours=1))[0]
    result = planner.build('u', planner.windows([group], [[entry(kind='background')]])[0], {'r': row})
    assert result['home_hidden'] is expected_hidden
    assert result['kind'] == ('background' if recognized else 'conversation')
    assert result['home_hidden_reason'] == (
        'background_wearer_recognized'
        if recognized
        else 'wearer_recognition_uncertain' if words >= 150 else 'below_word_minimum'
    )


def test_uncertain_background_manual_end_uses_intent_without_word_minimum():
    row = recording(
        segments=[{'text': 'five words about a plan', 'start': 0, 'end': 10, 'is_user': False}],
        v3_manual_end=True,
        finished_at=NOW + timedelta(seconds=10),
    )
    group = outline.stretches([row], NOW + timedelta(hours=1))[0]
    result = planner.build('u', planner.windows([group], [[entry(kind='background')]])[0], {'r': row})
    assert result['manual_end'] and not result['home_hidden'] and result['kind'] == 'conversation'


def test_media_stays_hidden_without_recognition():
    row = recording(segments=[{'text': 'television ' * 300, 'start': 0, 'end': 10, 'is_user': False}])
    group = outline.stretches([row], NOW + timedelta(hours=1))[0]
    result = planner.build('u', planner.windows([group], [[entry(kind='media')]])[0], {'r': row})
    assert result['home_hidden'] and result['kind'] == 'media' and result['home_hidden_reason'] == 'media'


def test_piece_trim_uses_playback_clock_for_171_second_capture_skew():
    row = recording(
        audio_files=[
            {
                'id': 'f',
                'started_at': NOW + timedelta(seconds=171),
                'chunk_timestamps': [(NOW + timedelta(seconds=171)).timestamp()],
                'playback_start': NOW.timestamp(),
                'duration': 10,
            }
        ]
    )
    group = outline.stretches([row], NOW + timedelta(hours=1))[0]
    built = planner.build('u', planner.windows([group], [[entry()]])[0], {'r': row})
    assert built['recording_pieces'] == [{'recording_id': 'r', 'audio_file_id': 'f', 'start': 0, 'end': 10}]


def test_copy_keeps_strongest_protection_and_custom_stt_provenance():
    plain = recording('a', segments=[{'text': 'first part of the talk', 'start': 0, 'end': 10}])
    guarded = recording(
        'b',
        NOW + timedelta(seconds=20),
        segments=[{'text': 'second part of the talk', 'start': 0, 'end': 10}],
        data_protection_level='enhanced',
        uses_custom_stt=True,
    )
    plain['data_protection_level'] = 'standard'
    group = outline.stretches([plain, guarded], NOW + timedelta(hours=1))[0]
    window = planner.windows([group], [[entry()]])[0]
    built = planner.build('synthetic', window, {'a': plain, 'b': guarded})
    assert built['v3_recording_ids'] == ['a', 'b']
    assert built['data_protection_level'] == 'enhanced'
    assert built['uses_custom_stt'] is True
    # A conversation that is already enhanced never drops back to standard.
    only_plain = planner.windows([outline.stretches([plain], NOW + timedelta(hours=1))[0]], [[entry()]])[0]
    rebuilt = planner.build(
        'synthetic',
        only_plain,
        {'a': plain},
        {
            'id': 'kept',
            'data_protection_level': 'enhanced',
            'started_at': NOW,
            'finished_at': NOW + timedelta(seconds=10),
        },
    )
    assert rebuilt['data_protection_level'] == 'enhanced' and rebuilt['uses_custom_stt'] is False


def test_late_merge_keeps_a_repeated_sentence_but_not_a_recaptured_one():
    said = 'Can you hear me now over there?'
    row = recording(segments=[{'text': said, 'start': 0, 'end': 2}, {'text': said, 'start': 10, 'end': 12}])
    window = planner.windows([outline.stretches([row], NOW + timedelta(hours=1))[0]], [[entry()]])[0]
    prior = {
        'id': 'c',
        'status': 'completed',
        'started_at': NOW,
        'finished_at': NOW + timedelta(seconds=12),
        # The stored copy already has the first utterance (another id, overlapping time).
        'transcript_segments': [{'id': 'stored', 'text': said, 'start': 0.5, 'end': 2.5}],
    }
    built = planner.build('u', window, {'r': row}, prior)
    assert [s['start'] for s in built['transcript_segments']] == [0.5, 10.0]


def test_copy_carries_the_recording_location_and_keeps_its_own():
    here = {'latitude': 1.5, 'longitude': 2.5, 'address': 'Synthetic street'}
    row = recording(geolocation=here)
    window = planner.windows([outline.stretches([row], NOW + timedelta(hours=1))[0]], [[entry()]])[0]
    assert planner.build('u', window, {'r': row})['geolocation'] == here
    kept = {'latitude': 9.0, 'longitude': 9.0}
    prior = {
        'id': 'c',
        'status': 'completed',
        'started_at': NOW,
        'finished_at': NOW + timedelta(seconds=10),
        'geolocation': kept,
    }
    assert planner.build('u', window, {'r': row}, prior)['geolocation'] == kept


def test_finish_sli_keeps_adjacent_cuts_on_their_own_cards():
    a = recording('a', NOW, finished_at=NOW + timedelta(seconds=15), v3_manual_end=True)
    b = recording('b', NOW + timedelta(seconds=16), finished_at=NOW + timedelta(seconds=35), v3_manual_end=True)
    c = recording('c', NOW + timedelta(seconds=36), finished_at=NOW + timedelta(seconds=45), v3_manual_end=True)
    c['transcript_segments'] = []
    groups = outline.stretches([a, b, c], NOW + timedelta(minutes=2), finish_routes=set())
    windows = planner.windows(groups, [[entry()], [entry()]])
    assert [w['_finish_sli_sources'] for w in windows] == [('a',), ('b',)]


@pytest.mark.parametrize('cohesion', [False, True])
@pytest.mark.parametrize('silence_gap', [timedelta(minutes=5), timedelta(minutes=15)])
def test_outline_reuses_identical_prefix_and_numbered_lines_after_append(cohesion, silence_gap):
    row = recording(segments=[{'text': 'Hablamos de la entrega', 'start': 0, 'end': 10, 'is_user': True}])

    def render(cache_prefix):
        (group,) = outline.stretches([row], NOW + timedelta(hours=1), silence_gap=silence_gap)
        return outline.messages(
            group, timezone.utc, cohesion=cohesion, silence_gap=silence_gap, cache_prefix=cache_prefix
        )

    legacy = render(False)
    initial = render(True)
    row['transcript_segments'].append({'text': 'Mañana confirmamos', 'start': 6 * 10, 'end': 70, 'is_user': True})
    updated = render(True)
    assert initial[0] == updated[0] == ('system', outline.OUTLINE_CACHE_PREFIX)
    assert initial[2][1].split('\n\nStretch')[0] == 'Transcript:\n' + legacy[1][1].split('\n\nTranscript:\n')[1]
    assert updated[2][1].startswith(initial[2][1].split('\n\nStretch')[0] + '\n')
    assert updated[2][1].endswith('Stretch 12:00 to 12:01.')


@pytest.mark.parametrize('cohesion', [False, True])
def test_transcript_size_cap_replans_failed_projection(monkeypatch, cohesion):

    rng = random.Random(2918)
    segments = [
        {
            'text': ' '.join(base64.b64encode(rng.randbytes(21)).decode() for _ in range(500)),
            'start': i * 10,
            'end': i * 10 + 8,
            'id': str(i),
        }
        for i in range(100)
    ]
    source = recording(segments=segments)
    recordings = {'r': source}
    groups = outline.stretches([source], NOW + timedelta(hours=1))
    outlines = [[entry()]]
    monkeypatch.setenv('CONVERSATIONS_V3_TRANSCRIPT_SIZE_CAP', 'off')
    (oversized,) = planner.windows(groups, outlines, cohesion=cohesion)
    raw = planner.build('u', oversized, recordings)
    assert len(zlib.compress(json.dumps(raw['transcript_segments']).encode())) > 1048487

    monkeypatch.delenv('CONVERSATIONS_V3_TRANSCRIPT_SIZE_CAP')

    def replan():
        planned = planner.windows(groups, outlines, cohesion=cohesion)
        return [planner.build('u', window, recordings) for window in planned]

    recovered = replan()
    assert len(recovered) > 1
    assert [row['id'] for row in recovered] == [row['id'] for row in replan()]
    assert [segment['id'] for row in recovered for segment in row['transcript_segments']] == [
        segment['id'] for segment in segments
    ]
    for row in recovered:
        compressed = zlib.compress(json.dumps(row['transcript_segments']).encode())
        assert len(base64.b64encode(bytes(28) + compressed.hex().encode())) < planner.TRANSCRIPT_BUDGET
