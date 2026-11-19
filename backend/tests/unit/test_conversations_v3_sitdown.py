"""Sit-down cutting: a silence gap over five minutes (CONVERSATIONS_V3_SILENCE_GAP_SECONDS) marks pauses
for the outline and joins one sit-down's talk into one card."""

from datetime import datetime, timedelta, timezone

from utils.conversations.v3 import outline, planner

AT = datetime(2026, 11, 18, tzinfo=timezone.utc)
GAP = timedelta(seconds=900)


def segment(start, words, **fields):
    return {'id': str(start), 'start': start, 'end': start + 1, 'text': 'speech ' * words, **fields}


def recording(segments, rid='r', **fields):
    return {'id': rid, 'started_at': AT, 'transcript_segments': segments, **fields}


def entry(number, kind='conversation'):
    return {'first_line': number, 'title': f'Topic {number}', 'line': '', 'kind': kind, 'people': []}


def test_only_a_gap_over_five_minutes_cuts_at_sitdowns():
    assert not outline.sitdown(outline.SILENCE)
    assert not outline.sitdown(timedelta(seconds=240))
    assert outline.sitdown(timedelta(seconds=301)) and outline.sitdown(GAP)


def test_the_hard_boundary_sentence_is_in_the_prompt_to_replace():
    assert outline.HARD_BOUNDARY_RULE in outline.SYSTEM_PROMPT


def test_sitdown_messages_mark_pauses_and_replace_the_hard_boundary_rule():
    raw = recording([segment(0, 3), segment(4 * 60, 3), segment(4 * 60 + 30, 3)])
    group = outline.stretches([raw], AT + timedelta(hours=1), silence_gap=GAP, lock_delay=GAP)[0]
    system, human = outline.messages(group, timezone.utc, cohesion=True, silence_gap=GAP)
    assert 'recorded silence is a hard boundary' not in system[1] and outline.SITDOWN_RULE in system[1]
    assert '{silence_boundary}' not in system[1]
    body = human[1].splitlines()
    assert '---- 4 min without speech ----' in body
    assert [line[:4] for line in body if line.startswith('[L')] == ['[L1 ', '[L2 ', '[L3 ']  # numbering unchanged
    plain_system, plain_human = outline.messages(group, timezone.utc, cohesion=True)
    assert 'Five minutes of recorded silence is a hard boundary' in plain_system[1]
    assert 'without speech' not in plain_human[1]


def test_neighbouring_conversation_cards_of_a_stretch_join_and_media_stays_apart():
    # Every topic is over the Home word minimum, so the short-topic fold alone would keep them apart.
    raw = recording([segment(i * 2, words) for i, words in enumerate([400, 400, 40, 400, 100, 400])])
    groups = outline.stretches([raw], AT + timedelta(hours=1), silence_gap=GAP, lock_delay=GAP)
    entries = [[entry(1), entry(2), entry(3, 'voice_work'), entry(4), entry(5, 'media'), entry(6)]]
    joined = planner.windows(groups, entries, cohesion=True, silence_gap=GAP)
    assert [(w['kind'], len(w['lines'])) for w in joined] == [('conversation', 4), ('media', 1), ('conversation', 1)]
    assert [s['title'] for s in joined[0]['sections']][:2] == ['Topic 2', 'Topic 3']
    apart = planner.windows(groups, entries, cohesion=True)
    assert len(apart) > len(joined)


def test_long_dictation_between_conversations_keeps_its_own_card():
    raw = recording([segment(i * 2, 400) for i in range(3)])
    groups = outline.stretches([raw], AT + timedelta(hours=1), silence_gap=GAP, lock_delay=GAP)
    joined = planner.windows(groups, [[entry(1), entry(2, 'voice_work'), entry(3)]], cohesion=True, silence_gap=GAP)
    assert [w['kind'] for w in joined] == ['conversation', 'voice_work', 'conversation']


def test_manual_end_stretches_keep_their_existing_single_card():
    raw = recording([segment(0, 200), segment(2, 200)], v3_manual_end=True, finished_at=AT + timedelta(seconds=3))
    groups = outline.stretches([raw], AT + timedelta(hours=1), silence_gap=GAP, lock_delay=GAP)
    joined = planner.windows(groups, [[entry(1), entry(2, 'media')]], cohesion=True, silence_gap=GAP)
    assert len(joined) == 1


def test_a_joined_sitdown_card_meets_the_home_minimum_on_its_own_words():
    # One 400-word sit-down and, after media, a 40-word aside: the stretch total would pass both.
    raw = recording([segment(0, 400), segment(2, 30), segment(4, 40)])
    groups = outline.stretches([raw], AT + timedelta(hours=1), silence_gap=GAP, lock_delay=GAP)
    entries = [[entry(1), entry(2, 'media'), entry(3)]]
    joined = planner.windows(groups, entries, cohesion=True, silence_gap=GAP)
    assert [(w['kind'], w['_stretch_words']) for w in joined] == [
        ('conversation', 400),
        ('media', 30),
        ('conversation', 40),
    ]
    stretch_level = planner.windows(groups, entries, cohesion=True)
    assert {w['_stretch_words'] for w in stretch_level} == {470}


def test_joining_never_holds_an_earlier_stretch_open():
    # Two sit-downs 20 minutes apart; the second is still going. Only the last window may be open (#25800).
    first = recording([segment(0, 400), segment(60, 400)], rid='a')
    second = recording([segment(30 * 60, 400), segment(31 * 60, 400)], rid='b')
    now = AT + timedelta(minutes=33)
    groups = outline.stretches([first, second], now, silence_gap=GAP, lock_delay=timedelta(seconds=3600))
    assert [g['finished'] for g in groups] == [True, False]
    entries = [[entry(1), entry(2)], [entry(1), entry(2)]]
    planned = planner.windows(groups, entries, cohesion=True, silence_gap=GAP, defer_topic_lock=True)
    assert len(planned) == 2  # each sit-down joined into one card
    windows = planner.preserve_finished_windows(planned, {}, {'a': first, 'b': second}, protect_provisional=True)
    assert [w['finished'] for w in windows] == [True, False]
