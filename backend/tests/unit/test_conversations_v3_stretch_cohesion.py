from datetime import datetime, timedelta, timezone

from config.conversations_v3 import stretch_cohesion_enabled
from utils.conversations.v3 import outline, planner

AT = datetime(2026, 11, 18, tzinfo=timezone.utc)


def segment(start, words, **fields):
    return {'id': str(start), 'start': start, 'end': start + 1, 'text': 'speech ' * words, **fields}


def recording(segments, **fields):
    return {'id': 'r', 'started_at': AT, 'transcript_segments': segments, **fields}


def entry(number):
    return {'first_line': number, 'title': f'Topic {number}', 'line': '', 'kind': 'conversation'}


def test_outline_labels_are_stretch_local_and_abstentions_share_one_label(monkeypatch):
    raw = recording(
        [
            segment(0, 1, speaker='raw-3'),
            segment(2, 1, speaker='BATCH_UNASSIGNED_one'),
            segment(4, 1, speaker='raw-9'),
            segment(6, 1, speaker='BATCH_UNASSIGNED_two'),
            segment(8, 1, speaker='raw-3'),
            segment(10, 1, speaker='speaker_99'),
            segment(12, 1, speaker='raw-4', person_name='Synthetic contact'),
            segment(14, 1, speaker='raw-5', is_user=True),
        ]
    )
    group = outline.stretches([raw], AT)[0]
    monkeypatch.delenv('CONVERSATIONS_V3_STRETCH_COHESION', raising=False)
    system, human = outline.messages(group, timezone.utc, cohesion=stretch_cohesion_enabled())
    assert 'S? marks unassigned speech' in system[1]
    assert [line.split('] ')[1].split(':')[0] for line in human[1].splitlines() if line.startswith('[L')] == [
        'S1',
        'S?',
        'S2',
        'S?',
        'S1',
        'S?',
        'Synthetic contact',
        'ME',
    ]
    monkeypatch.setenv('CONVERSATIONS_V3_STRETCH_COHESION', 'off')
    assert 'BATCH_UNASSIGNED_one' in outline.messages(group, timezone.utc, cohesion=stretch_cohesion_enabled())[1][1]


def test_six_short_topics_fold_into_one_visible_517_word_card():
    raw = recording([segment(i * 2, count) for i, count in enumerate([25, 181, 80, 100, 65, 66])])
    groups = outline.stretches([raw], AT + timedelta(minutes=10))
    entries = [[entry(i) for i in range(1, 7)]]
    legacy = planner.windows(groups, entries)
    assert len(legacy) == 6
    assert all(planner.build('synthetic', window, {'r': raw})['home_hidden'] for window in legacy)
    (window,) = planner.windows(groups, entries, cohesion=True)
    row = planner.build('synthetic', window, {'r': raw})
    assert not row['home_hidden']
    assert planner.word_count(window['lines']) == 517
    assert len(row['structured']['sections']) >= 5


def test_silence_does_not_pool_word_eligibility():
    raw = recording([segment(0, 260), segment(302, 260)])
    groups = outline.stretches([raw], AT + timedelta(minutes=20))
    windows = planner.windows(groups, [[entry(1)], [entry(1)]], cohesion=True)
    assert len(windows) == 2
    assert all(
        planner.build('synthetic', window, {'r': raw})['home_hidden_reason'] == 'below_word_minimum'
        for window in windows
    )


def test_manual_cut_preserves_whole_straddling_segment_and_open_short_tail():
    raw = recording(
        [segment(0, 50), {**segment(9, 20), 'end': 12}, segment(14, 20)],
        v3_manual_end=True,
        finished_at=AT + timedelta(seconds=10),
    )
    groups = outline.stretches([raw], AT + timedelta(seconds=20))
    before, after = planner.windows(groups, [[entry(1), entry(2)], [entry(1)]], cohesion=True)
    assert before['manual_end'] and before['finished']
    assert before['lines'][-1]['end'] == AT + timedelta(seconds=12)
    assert not after['manual_end'] and not after['finished']
    assert after['lines'][0]['start'] == AT + timedelta(seconds=14)


def test_cap_does_not_pool_word_eligibility(monkeypatch):
    monkeypatch.setattr(planner, 'CAP', timedelta(seconds=10))
    raw = recording([segment(0, 200), segment(8, 50), segment(16, 200)])
    groups = outline.stretches([raw], AT + timedelta(minutes=10))
    windows = planner.windows(groups, [[entry(1), entry(2), entry(3)]], cohesion=True)
    assert len(windows) == 2
    assert all(
        planner.build('synthetic', window, {'r': raw})['home_hidden_reason'] == 'below_word_minimum'
        for window in windows
    )
