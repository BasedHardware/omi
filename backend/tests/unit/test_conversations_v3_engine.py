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
