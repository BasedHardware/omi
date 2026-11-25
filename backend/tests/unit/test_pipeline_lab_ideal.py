"""Pipeline-lab ideals: packet lines, the ideal validator and structure scoring (synthetic data only)."""

import json
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


def test_hourpass_walks_windows_carries_the_open_card_and_merges_continuations():
    from testing.pipeline_lab.ideal.hourpass import run_day

    t = T0
    rows = []
    # 0-50 min: talk A; 55-70 min: talk B (crosses the 60 min window edge); 80 min: talk C
    for i, minute in enumerate([0, 20, 50, 55, 58, 62, 70, 80]):
        rows.append(seg(f'line {i}', minute * 60, minute * 60 + 5))
    lines, _ = build_lines([recording('rec', t, rows)], tz=TZ)
    asked = []

    def ask(messages, tag):
        prompt = messages[-1]['content'] if len(messages) == 2 else messages[1]['content']
        ids = [ln.split()[0] for ln in prompt.split('THIS STRETCH')[1].splitlines()[1:] if ln.startswith('L')]
        asked.append(ids)
        if len(asked) == 1:  # first window: A = first three lines, B = the rest (still open)
            return {
                'cards': [
                    {
                        'lines': [f'{ids[0]}-{ids[2]}'],
                        'kind': 'conversation',
                        'home': True,
                        'title': 'A',
                        'key_points': ['a'],
                    },
                    {
                        'lines': [f'{ids[3]}-{ids[-1]}'],
                        'kind': 'conversation',
                        'home': False,
                        'hidden_reason': 'too_short',
                        'title': 'B',
                    },
                ]
            }
        # second window: B again (whole), C says it continues A
        return {
            'cards': [
                {
                    'lines': [ids[0] + '-' + ids[-2]],
                    'kind': 'conversation',
                    'home': True,
                    'title': 'B',
                    'key_points': ['b'],
                },
                {
                    'lines': [ids[-1]],
                    'kind': 'conversation',
                    'home': False,
                    'hidden_reason': 'too_short',
                    'title': 'C',
                    'continues': 'c001',
                },
            ]
        }

    cards, logs = run_day(lines, spec='rules', context={'day': 'd'}, ask=ask)
    assert asked[0] == ['L0001', 'L0002', 'L0003', 'L0004', 'L0005']  # lines before minute 60
    assert asked[1][0] == 'L0004'  # the open card B is carried, not decided
    assert logs[0].carried == 'B' and logs[1].continued == ['c001']
    assert [(c.title, c.home) for c in cards] == [('A', True), ('B', True)]
    assert cards[0].lines == ['L0001', 'L0002', 'L0003', 'L0008']  # C merged into A, A never split


def _timed_lines(spec):
    """spec: (minute, recording, text) -> packet lines in one day."""
    rows = {}
    for minute, rid, text in spec:
        rows.setdefault(rid, []).append((minute, text))
    recs = []
    for rid, items in rows.items():
        first = min(m for m, _ in items)
        segs = [seg(text, (m - first) * 60, (m - first) * 60 + 5) for m, text in items]
        recs.append(recording(rid, T0 + timedelta(minutes=first), segs))
    lines, _ = build_lines(recs, tz=TZ)
    return lines


def test_repair_gives_each_line_one_owner_and_fills_gaps_from_the_line_before():
    from testing.pipeline_lab.ideal.hourpass import repair

    lines = _timed_lines([(m, 'r', f'word {m}') for m in range(6)])
    answer = [{'lines': ['L0002-L0003'], 'kind': 'conversation'}, {'lines': ['L0003-L0004', 'L0009']}]
    cards, moved = repair(answer, lines)
    assert [c['lines'] for c in cards] == [['L0001', 'L0002', 'L0003'], ['L0004', 'L0005', 'L0006']]
    assert moved == 3  # L0001 joins the line after it; L0005 and L0006 the line before
    assert repair([{'lines': ['bad']}], lines) == ([], 0)


def test_render_markers_and_second_capture_tags():
    from testing.pipeline_lab.ideal.hourpass import render

    lines = _timed_lines([(0, 'a', 'hello there'), (10, 'a', 'back again')])
    text = render(lines, markers=True, second={'L0002'})
    assert '---- 10 min without speech ----' in text and text.startswith('[r001 starts]')
    assert text.endswith('back again (second capture)')
    assert render(lines) == '\n'.join(text.splitlines()[i] for i in (1, 3)).replace(' (second capture)', '')


def test_second_capture_lines_collapse_and_reattach_to_the_nearest_card():
    from testing.pipeline_lab.ideal.hourpass import Card, attach_dropped, collapse_plan, secondary_lines

    lines = _timed_lines(
        [(0, 'main', 'a long sentence with many words in it'), (1, 'main', 'another long sentence here too')]
        + [(1, 'echo', 'garbled')]
    )
    second = secondary_lines(lines)
    echo = next(x['line'] for x in lines if x['text'] == 'garbled')
    assert second == {echo: 'r001'}
    assert collapse_plan(lines) == {echo}
    kept = [x['line'] for x in lines if x['line'] != echo]
    card = Card('c001', kept, 'conversation', True, None, 't', [], [], [], 'high', '')
    assert attach_dropped([card], lines, {echo}) == 1 and echo in card.lines


def test_silence_windows_end_at_a_long_silence_after_the_minimum():
    from testing.pipeline_lab.ideal.hourpass import Variant, run_day

    # talk at 0-40 min, a 25 min silence ending after minute 45, more at 65 and 70 min
    lines = _timed_lines([(m, 'r', f'line {m}') for m in (0, 20, 40, 65, 70)])
    asked = []

    def ask(messages, tag):
        ids = [
            ln.split()[0]
            for ln in messages[1]['content'].split('THIS STRETCH')[1].splitlines()[1:]
            if ln.startswith('L')
        ]
        asked.append(ids)
        return {'cards': [{'lines': [f'{ids[0]}-{ids[-1]}'], 'kind': 'conversation', 'title': 'x'}]}

    cards, logs = run_day(
        lines, spec='rules', context={}, ask=ask, variant=Variant(boundaries_only=True, silence_windows=True)
    )
    assert [len(ids) for ids in asked] == [3, 2]
    assert [c.home for c in cards] == [False, False]  # boundaries-only leaves Home to a later pass


def test_refine_absorbs_background_inside_a_conversation_and_merges_by_threshold():
    from testing.pipeline_lab.ideal.refine import absorb, build, group_key, pairs

    lines = _timed_lines([(m, 'r', f'w{m} ' * 60) for m in (0, 1, 2, 3, 10, 40)])
    ids = [x['line'] for x in lines]
    cards = [
        {'id': 'c1', 'lines': ids[0:2], 'kind': 'conversation', 'title': 'A'},
        {'id': 'c2', 'lines': ids[2:3], 'kind': 'background', 'title': 'bg'},
        {'id': 'c3', 'lines': ids[3:4], 'kind': 'conversation', 'title': 'A again'},
        {'id': 'c4', 'lines': ids[4:5], 'kind': 'conversation', 'title': 'B'},
        {'id': 'c5', 'lines': ids[5:6], 'kind': 'conversation', 'title': 'C, much later'},
    ]
    owner = absorb(cards, lines)
    assert owner[ids[2]] == 'c1'
    found = {(a, b) for a, b, _ in pairs(cards, owner, lines)}
    assert found == {('c1', 'c3'), ('c3', 'c4')}  # c5 is 30 min after c4
    refined = {
        'owner': owner,
        'pairs': [{'a': 'c1', 'b': 'c3', 'p': 0.9}, {'a': 'c3', 'b': 'c4', 'p': 0.4}],
        'groups': {
            group_key(['c1', 'c3']): {'words': 240, 'p_keep': 0.6, 'p_wearer': 0.9},
            group_key(['c4']): {'words': 60, 'p_keep': 0.35, 'p_wearer': None},
            group_key(['c5']): {'words': 60, 'p_keep': 0.7, 'p_wearer': None},
        },
    }
    out = build({'cards': cards}, refined, merge=0.5)
    assert [(c['id'], c['home']) for c in out['cards']] == [('c1', True), ('c4', False), ('c5', True)]
    assert out['cards'][0]['lines'] == [f'{ids[0]}-{ids[3]}']


def test_run_diff_reports_boundaries_and_home_flips_without_text(tmp_path, capsys):
    from testing.pipeline_lab.ideal import runs

    def conv(cid, start_min, end_min, words, visible):
        return {
            'id': cid,
            'started_at': (T0 + timedelta(minutes=start_min)).isoformat(),
            'finished_at': (T0 + timedelta(minutes=end_min)).isoformat(),
            'transcript_segments': [seg('secret ' * words, 0, 1)],
            'v3': {'visible': visible, **({} if visible else {'home_hidden_reason': 'below_word_minimum'})},
        }

    for run_id, rows in {
        'run-a': [conv('a1', 0, 10, 5, True), conv('a2', 10, 20, 3, True)],
        'run-b': [conv('b1', 0, 10, 5, False), conv('b2', 10, 30, 4, True)],
    }.items():
        folder = tmp_path / 'runs' / run_id / 'conversations'
        folder.mkdir(parents=True)
        for row in rows:
            (folder / f"{row['id']}.json").write_text(json.dumps(row), encoding='utf-8')

    d = runs.card_diff(
        [runs.card(c) for c in runs.load_run(tmp_path, 'run-a')],
        [runs.card(c) for c in runs.load_run(tmp_path, 'run-b')],
    )
    assert d['identical'] == 1 and len(d['only_a']) == 1 and len(d['only_b']) == 1
    assert [(x[3], y[3], y[4]) for x, y in d['home_flips']] == [(True, False, 'below_word_minimum')]

    assert runs.main(['--root', str(tmp_path), 'diff', 'a=run-a', 'b=run-b']) == 0
    out = capsys.readouterr().out
    assert 'identical boundaries 1' in out and 'Home flips on identical cards 1' in out
    assert '09:10:00-09:20:00   10m      3w HOME' in out
    assert 'secret' not in out


def test_a_shared_line_goes_to_the_earlier_conversation_whatever_the_input_order(day):
    lines, _ = day
    first = {'id': 'z-early', 'started_at': T0.isoformat(), 'transcript_segments': [seg('yes the tomato ones', 4, 6)]}
    late = {
        'id': 'a-late',
        'started_at': (T0 + timedelta(seconds=4)).isoformat(),
        'transcript_segments': [seg('yes the tomato ones', 0, 2)],
    }
    owners = [conversations_partition(order, lines).card_of for order in ([first, late], [late, first])]
    assert owners[0] == owners[1]
    assert set(owners[0].values()) == {'z-early'}


def test_run_card_for_an_open_conversation_ends_at_its_last_segment():
    from testing.pipeline_lab.ideal import runs

    start, end, words, home, reason = runs.card(
        {'started_at': T0.isoformat(), 'finished_at': None, 'transcript_segments': [seg('a b', 0, 4), seg('c', 5, 9)]}
    )
    assert (end - start).total_seconds() == 9 and words == 3 and reason.endswith('+open')
