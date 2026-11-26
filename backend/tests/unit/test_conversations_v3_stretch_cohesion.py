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
            segment(10, 1, speaker='speaker_99', speaker_id=99, person_name='Incorrect binding'),
            segment(12, 1, speaker='raw-4', person_name='Synthetic contact'),
            segment(14, 1, speaker='raw-5', is_user=True),
            segment(16, 1, speaker='SPEAKER_99', speaker_id=4),
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
        'Omi',
        'Synthetic contact',
        'ME',
        'S3',
    ]
    for disabled in ('off', 'false', '0', 'no'):
        monkeypatch.setenv('CONVERSATIONS_V3_STRETCH_COHESION', disabled)
        assert (
            'BATCH_UNASSIGNED_one' in outline.messages(group, timezone.utc, cohesion=stretch_cohesion_enabled())[1][1]
        )


def test_six_short_topics_fold_into_one_visible_517_word_card():
    raw = recording([segment(i * 2, count) for i, count in enumerate([25, 140, 80, 100, 65, 107])])
    groups = outline.stretches([raw], AT + timedelta(minutes=10))
    entries = [[entry(i) for i in range(1, 7)]]
    legacy = planner.windows(groups, entries)
    assert len(legacy) == 6
    assert all(planner.build('synthetic', window, {'r': raw})['home_hidden'] for window in legacy)
    (window,) = planner.windows(groups, entries, cohesion=True)
    row = planner.build('synthetic', window, {'r': raw})
    assert not row['home_hidden']
    assert planner.word_count(window['lines']) == 517
    assert len(row['structured']['sections']) == 5
    assert all(section['heading'] != row['structured']['title'] for section in row['structured']['sections'])


def test_silence_does_not_pool_word_eligibility():
    raw = recording([segment(0, 130), segment(302, 130)])
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
    raw = recording([segment(0, 100), segment(8, 25), segment(16, 100)])
    groups = outline.stretches([raw], AT + timedelta(minutes=10))
    windows = planner.windows(groups, [[entry(1), entry(2), entry(3)]], cohesion=True)
    assert len(windows) == 2
    assert all(
        planner.build('synthetic', window, {'r': raw})['home_hidden_reason'] == 'below_word_minimum'
        for window in windows
    )


def test_short_media_and_recognized_background_keep_their_visibility_policy():
    raw = recording([segment(0, 10), segment(2, 320), segment(4, 10), segment(6, 20)], _v3_wearer_recognized=True)
    groups = outline.stretches([raw], AT + timedelta(minutes=10))
    entries = [[{**entry(1), 'kind': 'media'}, entry(2), {**entry(3), 'kind': 'background'}, entry(4)]]
    windows = planner.windows(groups, entries, cohesion=True)
    rows = [planner.build('synthetic', window, {'r': raw}) for window in windows]
    assert [row['home_hidden_reason'] for row in rows] == [
        'media',
        'conversation',
        'background_wearer_recognized',
        'conversation',
    ]
    assert [len(row['transcript_segments']) for row in rows] == [1, 1, 1, 1]
    assert planner.word_count(windows[-1]['lines']) == 20
    assert not rows[-1]['home_hidden']

    recorded = {
        **raw,
        'claims': [{'conversation_id': row['id'], **claim} for row in rows for claim in row['_v3_claims']['r']],
    }
    existing = {row['id']: row for row in rows}
    replay = planner.preserve_finished_windows(windows, existing, {'r': recorded})
    rebuilt = planner.build('synthetic', replay[-1], {'r': recorded}, existing[replay[-1]['existing_id']])
    assert rebuilt['id'] == rows[-1]['id'] and not rebuilt['home_hidden']

    disabled = planner.preserve_finished_windows(planner.windows(groups, entries), existing, {'r': recorded})
    rebuilt_off = planner.build('synthetic', disabled[-1], {'r': recorded}, existing[disabled[-1]['existing_id']])
    assert rebuilt_off['home_hidden_reason'] == 'below_word_minimum'


def test_late_fragment_does_not_borrow_words_from_a_published_claim():
    initial = recording([segment(0, 480)])
    now = AT + timedelta(minutes=10)
    initial_groups = outline.stretches([initial], now)
    (initial_window,) = planner.windows(initial_groups, [[entry(1)]], cohesion=True)
    prior = planner.build('synthetic', initial_window, {'r': initial})
    raw = {
        **initial,
        'transcript_segments': [*initial['transcript_segments'], segment(2, 37)],
        'claims': [{'conversation_id': prior['id'], **claim} for claim in prior['_v3_claims']['r']],
    }
    groups = outline.stretches([raw], now)
    planned = planner.windows(groups, [[entry(1), entry(2)]], cohesion=True)
    windows = planner.preserve_finished_windows(planned, {prior['id']: prior}, {'r': raw})
    kept, late = windows
    assert kept['existing_id'] == prior['id']
    row = planner.build('synthetic', late, {'r': raw})
    assert row['home_hidden_reason'] == 'below_word_minimum'
    assert row['_v3_claims']['r'] == [{'start': AT + timedelta(seconds=2), 'end': AT + timedelta(seconds=3)}]


def test_late_topic_past_media_does_not_borrow_from_published_topic():
    initial = recording([segment(0, 480)])
    now = AT + timedelta(minutes=10)
    (planned_prior,) = planner.windows(outline.stretches([initial], now), [[entry(1)]], cohesion=True)
    prior = planner.build('synthetic', planned_prior, {'r': initial})
    raw = {
        **initial,
        'transcript_segments': [*initial['transcript_segments'], segment(2, 10), segment(4, 37)],
        'claims': [{'conversation_id': prior['id'], **claim} for claim in prior['_v3_claims']['r']],
    }
    planned = planner.windows(
        outline.stretches([raw], now),
        [[entry(1), {**entry(2), 'kind': 'media'}, entry(3)]],
        cohesion=True,
    )
    kept, media, late = planner.preserve_finished_windows(planned, {prior['id']: prior}, {'r': raw})
    assert kept['existing_id'] == prior['id']
    assert planner.build('synthetic', media, {'r': raw})['home_hidden_reason'] == 'media'
    assert planner.build('synthetic', late, {'r': raw})['home_hidden_reason'] == 'below_word_minimum'


def test_cap_rebases_sections_for_a_topic_spanning_the_boundary(monkeypatch):
    monkeypatch.setattr(planner, 'CAP', timedelta(seconds=9))
    raw = recording([segment(i, 200) for i in (0, 4, 8, 12)])
    topic = {
        **entry(1),
        'sections': [{'first_line': i, 'title': f'Section {i}'} for i in (2, 3, 4)],
    }
    left, right = planner.windows(outline.stretches([raw], AT + timedelta(minutes=10)), [[topic]], cohesion=True)
    # The cap cut follows the longest prefix that ends within the cap, not the sections (#25829).
    assert [line['segment']['id'] for line in left['lines']] == ['0', '4', '8']
    assert [line['segment']['id'] for line in right['lines']] == ['12']
    assert [section['first_line'] for section in left['sections']] == [2, 3]
    assert [section['first_line'] for section in right['sections']] == [1]


def test_resume_merges_within_the_cap_partition_and_keeps_sections(monkeypatch):
    monkeypatch.setattr(planner, 'CAP', timedelta(seconds=10))
    raw = recording([segment(i, 320) for i in (0, 8, 9, 18)])
    topics = [entry(1), entry(2), {**entry(3), 'resumes_previous': True}, {**entry(4), 'resumes_previous': True}]
    windows = planner.windows(outline.stretches([raw], AT + timedelta(minutes=10)), [topics], cohesion=True)
    # Topic 3 resumes Topic 2 inside the first cap partition; Topic 4 cannot resume across the cut.
    assert [[line['segment']['id'] for line in w['lines']] for w in windows] == [['0'], ['8', '9'], ['18']]
    assert windows[1]['sections'] == [{'first_line': 3, 'title': 'Topic 3'}]
