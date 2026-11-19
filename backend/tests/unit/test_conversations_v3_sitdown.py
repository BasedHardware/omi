"""Sit-down cutting (CONVERSATIONS_V3_SITDOWN): 15-minute stretches, gap markers, joined talk."""

from datetime import datetime, timedelta, timezone

from config.conversations_v3 import sitdown_enabled, sitdown_silence_seconds
from utils.conversations.v3 import outline, planner

AT = datetime(2026, 11, 18, tzinfo=timezone.utc)


def segment(start, words, **fields):
    return {'id': str(start), 'start': start, 'end': start + 1, 'text': 'speech ' * words, **fields}


def recording(segments, **fields):
    return {'id': 'r', 'started_at': AT, 'transcript_segments': segments, **fields}


def entry(number, kind='conversation'):
    return {'first_line': number, 'title': f'Topic {number}', 'line': '', 'kind': kind, 'people': []}


def test_switch_is_on_by_default_and_off_is_the_kill_switch(monkeypatch):
    monkeypatch.delenv('CONVERSATIONS_V3_SITDOWN', raising=False)
    assert sitdown_enabled()
    for disabled in ('off', 'false', '0', 'no', ' OFF '):
        monkeypatch.setenv('CONVERSATIONS_V3_SITDOWN', disabled)
        assert not sitdown_enabled()


def test_a_ten_minute_pause_stays_in_one_sitdown_stretch_but_splits_at_five_minutes():
    raw = recording([segment(0, 50), segment(10 * 60, 50), segment(30 * 60, 50)])
    now = AT + timedelta(hours=1)
    assert [len(g['lines']) for g in outline.stretches([raw], now)] == [1, 1, 1]
    sitdown = outline.stretches([raw], now, silence=outline.SITDOWN_SILENCE)
    assert [len(g['lines']) for g in sitdown] == [2, 1]
    assert all(g['silence'] == outline.SITDOWN_SILENCE for g in sitdown)


def test_a_sitdown_stretch_finishes_only_after_its_own_silence():
    raw = recording([segment(0, 50)])
    ten_minutes_later = AT + timedelta(minutes=10)
    assert outline.stretches([raw], ten_minutes_later)[0]['finished']
    assert not outline.stretches([raw], ten_minutes_later, silence=outline.SITDOWN_SILENCE)[0]['finished']
    assert outline.stretches([raw], AT + timedelta(minutes=16), silence=outline.SITDOWN_SILENCE)[0]['finished']


def test_sitdown_messages_mark_pauses_and_replace_the_five_minute_rule():
    raw = recording([segment(0, 3), segment(4 * 60, 3), segment(4 * 60 + 30, 3)])
    group = outline.stretches([raw], AT + timedelta(hours=1), silence=outline.SITDOWN_SILENCE)[0]
    system, human = outline.messages(group, timezone.utc, cohesion=True, sitdown=True)
    assert outline.FIVE_MINUTE_RULE not in system[1] and outline.SITDOWN_RULE in system[1]
    body = human[1].splitlines()
    assert '---- 4 min without speech ----' in body
    assert [line[:4] for line in body if line.startswith('[L')] == ['[L1 ', '[L2 ', '[L3 ']  # numbering unchanged
    plain_system, plain_human = outline.messages(group, timezone.utc, cohesion=True)
    assert outline.FIVE_MINUTE_RULE in plain_system[1] and 'without speech' not in plain_human[1]


def test_neighbouring_conversation_cards_of_a_stretch_join_and_media_stays_apart():
    # Every topic is over the Home word minimum, so the short-topic fold alone would keep them apart.
    raw = recording([segment(i * 2, words) for i, words in enumerate([400, 400, 40, 400, 100, 400])])
    groups = outline.stretches([raw], AT + timedelta(hours=1), silence=outline.SITDOWN_SILENCE)
    entries = [
        [
            entry(1),
            entry(2),
            entry(3, 'voice_work'),  # short dictation between two conversation cards joins
            entry(4),
            entry(5, 'media'),
            entry(6),
        ]
    ]
    joined = planner.windows(groups, entries, cohesion=True, sitdown=True)
    assert [(w['kind'], len(w['lines'])) for w in joined] == [('conversation', 4), ('media', 1), ('conversation', 1)]
    assert [s['title'] for s in joined[0]['sections']][:2] == ['Topic 2', 'Topic 3']
    apart = planner.windows(groups, entries, cohesion=True)
    assert len(apart) > len(joined)


def test_long_dictation_between_conversations_keeps_its_own_card():
    raw = recording([segment(i * 2, words) for i, words in enumerate([400, 400, 400])])
    groups = outline.stretches([raw], AT + timedelta(hours=1), silence=outline.SITDOWN_SILENCE)
    joined = planner.windows(groups, [[entry(1), entry(2, 'voice_work'), entry(3)]], cohesion=True, sitdown=True)
    assert [w['kind'] for w in joined] == ['conversation', 'voice_work', 'conversation']


def test_manual_end_stretches_keep_their_existing_single_card():
    raw = recording([segment(0, 200), segment(2, 200)], v3_manual_end=True, finished_at=AT + timedelta(seconds=3))
    groups = outline.stretches([raw], AT + timedelta(hours=1), silence=outline.SITDOWN_SILENCE)
    joined = planner.windows(groups, [[entry(1), entry(2, 'media')]], cohesion=True, sitdown=True)
    assert len(joined) == 1


def test_sitdown_silence_is_bounded_and_defaults_to_fifteen_minutes(monkeypatch):
    monkeypatch.delenv('CONVERSATIONS_V3_SITDOWN_SILENCE_SECONDS', raising=False)
    assert sitdown_silence_seconds() == 900 == outline.SITDOWN_SILENCE.total_seconds()
    for raw, expected in (('300', 300), ('1800', 1800), ('120', 900), ('7200', 900), ('soon', 900)):
        monkeypatch.setenv('CONVERSATIONS_V3_SITDOWN_SILENCE_SECONDS', raw)
        assert sitdown_silence_seconds() == expected


def test_a_joined_sitdown_card_meets_the_home_minimum_on_its_own_words():
    # One 400-word sit-down and, after media, a 40-word aside: the stretch total would pass both.
    raw = recording([segment(0, 400), segment(2, 30), segment(4, 40)])
    groups = outline.stretches([raw], AT + timedelta(hours=1), silence=outline.SITDOWN_SILENCE)
    entries = [[entry(1), entry(2, 'media'), entry(3)]]
    joined = planner.windows(groups, entries, cohesion=True, sitdown=True)
    assert [(w['kind'], w['_stretch_words']) for w in joined] == [
        ('conversation', 400),
        ('media', 30),
        ('conversation', 40),
    ]
    stretch_level = planner.windows(groups, entries, cohesion=True)
    assert {w['_stretch_words'] for w in stretch_level} == {470}
