"""Synthetic recorded-clock contracts; no model calls or customer fixtures."""

from datetime import datetime, timedelta, timezone
import json

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


def test_two_hour_cap_at_nearest_middle_section():
    row = recording(segments=[{'text': str(i), 'start': i * 60, 'end': i * 60 + 10} for i in range(180)])
    groups = outline.stretches([row], NOW + timedelta(hours=4))
    windows = planner.windows(groups, [[entry(sections=[{'first_line': 91, 'title': 'Next subject'}])]])
    assert len(windows) == 2
    assert windows[1]['lines'][0]['start'] == NOW + timedelta(minutes=90)
    assert all(w['lines'][-1]['end'] - w['lines'][0]['start'] <= timedelta(hours=2) for w in windows)


@pytest.mark.parametrize('gap,expected', [(20, 1), (20.001, 2)])
def test_resume_twenty_minute_limit(gap, expected):
    a = recording('a')
    b = recording('b', NOW + timedelta(seconds=10, minutes=gap))
    groups = outline.stretches([a, b], NOW + timedelta(hours=4))
    assert len(planner.windows(groups, [[entry()], [entry(resumes_previous=True)]])) == expected


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
def test_manual_end_does_not_promote_recognized_media_or_background(kind):
    row = recording(finished_at=NOW + timedelta(seconds=10), v3_manual_end=True)
    group = outline.stretches([row], NOW + timedelta(seconds=11))[0]
    built = planner.build('u', planner.windows([group], [[entry(kind=kind)]])[0], {'r': row})
    assert built['manual_end'] is True and built['home_hidden'] is True


def test_manual_end_without_speech_creates_no_window():
    row = recording(finished_at=NOW, v3_manual_end=True)
    row['transcript_segments'] = []
    assert planner.windows(outline.stretches([row], NOW), []) == []


@pytest.mark.parametrize(
    'recognized,words,expected_hidden', [(False, 300, False), (True, 300, True), (False, 40, True)]
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
        else 'wearer_recognition_uncertain' if words >= 300 else 'below_word_minimum'
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
