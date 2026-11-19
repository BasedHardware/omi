"""Pipeline-lab ideals: packet lines, the ideal validator and structure scoring (synthetic data only)."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from testing.pipeline_lab.ideal.packet import build_lines, render_transcript
from testing.pipeline_lab.ideal.schema import expand, validate
from testing.pipeline_lab.ideal.score import conversations_partition, ideal_partition, score

T0 = datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc)
TZ = ZoneInfo('Asia/Ho_Chi_Minh')


def seg(text, start, end, **extra):
    return {'text': text, 'start': start, 'end': end, **extra}


def recording(rid, start, segments, **extra):
    row = {
        'id': rid,
        'started_at': start.isoformat(),
        'finished_at': (start + timedelta(minutes=5)).isoformat(),
        'status': 'completed',
        'transcript_segments': segments,
    }
    row.update(extra)
    return row


@pytest.fixture
def day():
    rows = [
        recording(
            'rec-a',
            T0,
            [
                seg('we should order the seeds today', 0, 3, is_user=True),
                seg('yes the tomato ones', 4, 6, speaker='BATCH_UNASSIGNED_abc_1'),
                seg('and the water timer', 7, 9, speaker='SPEAKER_3'),
            ],
        ),
        # overlapping capture of the same speech, then its own line
        recording(
            'rec-b',
            T0 + timedelta(seconds=4),
            [seg('yes the tomato ones', 0.5, 2, speaker='SPEAKER_1'), seg('see you at noon', 60, 62)],
        ),
        recording('rec-c', T0 + timedelta(minutes=30), [seg('the festival starts friday', 0, 3, person_id='p1')]),
        recording('rec-gone', T0 + timedelta(minutes=40), [seg('gone', 0, 1)], deleted=True),
    ]
    return build_lines(rows, tz=TZ, people={'p1': 'Huong'})


def test_lines_are_numbered_in_time_order_with_clean_speakers_and_duplicates(day):
    lines, recs = day
    assert [r['recording_id'] for r in recs] == ['rec-a', 'rec-b', 'rec-c']  # deleted rows left out
    assert [line['line'] for line in lines] == ['L0001', 'L0002', 'L0003', 'L0004', 'L0005', 'L0006']
    speakers = [(line['recording'], line['speaker']) for line in lines]
    assert speakers[0] == ('r001', 'ME')
    assert ('r001', 'S?') in speakers and ('r001', 'S1') in speakers and ('r003', 'Huong') in speakers
    dup = next(line for line in lines if line['recording'] == 'r002' and line['text'] == 'yes the tomato ones')
    assert dup['dup_of'] == 'L0002'
    assert lines[0]['local'] == '16:00:00'
    text = render_transcript(lines)
    assert '(duplicate of L0002)' in text and 'min without speech' in text and '[r003 starts]' in text


def ideal_for(lines, groups, home=(True,)):
    cards = []
    for i, ids in enumerate(groups):
        on = home[i] if i < len(home) else False
        cards.append(
            {
                'id': f'c{i + 1}',
                'lines': ids,
                'kind': 'conversation',
                'home': on,
                'hidden_reason': None if on else 'too_short',
                'title': f'Card {i + 1}',
                'people': [],
                'key_points': ['a point'] if on else [],
                'tasks': [],
                'confidence': 'high',
                'why': 'test',
            }
        )
    return {'day': '2026-03-14', 'author': 'test', 'spec_version': 1, 'cards': cards}


def test_expand_ranges_and_reject_bad_refs():
    assert expand('L0003-L0005') == ['L0003', 'L0004', 'L0005']
    assert expand('L0007') == ['L0007']
    with pytest.raises(ValueError):
        expand('L0005-L0003')
    with pytest.raises(ValueError):
        expand('line 4')


def test_validator_accepts_a_full_partition_and_names_each_problem(day):
    lines, _ = day
    good = ideal_for(lines, [['L0001-L0002', 'L0004', 'L0005'], ['L0006']], home=(True, False))
    assert validate(good, lines) == []
    bad = ideal_for(lines, [['L0001-L0003'], ['L0005', 'L0009']], home=(True, True))
    bad['cards'][1]['key_points'] = []
    errors = validate(bad, lines)
    assert any('duplicate of L0002' in e for e in errors)  # L0003 is the overlapping copy
    assert any('unknown line L0009' in e for e in errors)
    assert any('1-6 key_points' in e for e in errors)
    assert any('in no card' in e and 'L0004' in e for e in errors)


def test_score_counts_splits_merges_and_home_against_the_ideal(day):
    lines, _ = day
    ideal = ideal_partition(ideal_for(lines, [['L0001-L0002', 'L0004', 'L0005'], ['L0006']], home=(True, True)))
    # candidate splits card 1 after L0002 and merges card 2 into the second piece, which is hidden
    other = ideal_partition(ideal_for(lines, [['L0001-L0002'], ['L0004', 'L0005', 'L0006']], home=(True, False)))
    result = score(ideal, other, lines)
    assert result['split'] == 1 and result['merge'] == 1
    # card 1 is half on Home in one piece: recalled, not whole; card 2 is hidden in the merged piece
    assert result['home']['ideal'] == 2 and result['home']['recall'] == 0.5 and result['home']['whole'] == 0.0
    assert result['home']['misses'] == ['Card 2'] and result['home']['precision'] == 1.0
    same = score(ideal, ideal, lines)
    assert same['split'] == same['merge'] == 0 and same['boundary']['f1'] == 1.0 and same['home']['whole'] == 1.0


def test_conversations_map_to_lines_by_text_and_time(day):
    lines, _ = day
    conversations = [
        {
            'id': 'v3-1',
            'started_at': T0.isoformat(),
            'segments': [
                seg('we should order the seeds today', 0, 3),
                seg('yes the tomato ones', 4.5, 6),  # the duplicate capture: counts for L0002
                seg('and the water timer', 7, 9),
            ],
            'v3': {'home_hidden': False, 'visible': True},
            'structured': {'title': 'Seeds'},
        },
        {
            'id': 'v3-2',
            'started_at': (T0 + timedelta(minutes=30)).isoformat(),
            'segments': [seg('the festival starts friday', 0, 3)],
            'v3': {'home_hidden': True, 'visible': False},
            'structured': {'title': 'Festival'},
        },
    ]
    part = conversations_partition(conversations, lines)
    assert part.card_of == {'L0001': 'v3-1', 'L0002': 'v3-1', 'L0004': 'v3-1', 'L0006': 'v3-2'}
    ideal = ideal_partition(ideal_for(lines, [['L0001-L0002', 'L0004', 'L0005'], ['L0006']], home=(True, True)))
    result = score(ideal, conversations_partition(conversations, lines), lines)
    assert result['unassigned_lines'] == 1  # "see you at noon" is in no conversation
    assert result['home']['misses'] == ['Card 2']


def test_review_agrees_on_matching_cards_and_disputes_a_split_or_home_flip(day):
    from testing.pipeline_lab.ideal.review import spans

    lines, _ = day
    a = ideal_for(lines, [['L0001-L0002', 'L0004', 'L0005'], ['L0006']], home=(True, True))
    same = ideal_for(lines, [['L0001-L0002', 'L0004', 'L0005'], ['L0006']], home=(True, True))
    assert [s['agreed'] for s in spans(a, same)] == [True, True]
    flipped = ideal_for(lines, [['L0001-L0002', 'L0004', 'L0005'], ['L0006']], home=(True, False))
    assert [s['agreed'] for s in spans(a, flipped)] == [True, False]
    split = ideal_for(lines, [['L0001-L0002'], ['L0004', 'L0005'], ['L0006']], home=(True, True, True))
    result = spans(a, split)
    assert [s['agreed'] for s in result] == [False, True]
    assert result[0]['lines'] == ['L0001', 'L0002', 'L0004', 'L0005'] and len(result[0]['b']) == 2
