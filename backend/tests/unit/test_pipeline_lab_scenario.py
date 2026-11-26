"""Pipeline-lab scenarios: the file format, the event plan, checks and outcomes (pure, no stack)."""

import copy
import json
from datetime import timedelta

import pytest

from testing.pipeline_lab import cli
from testing.pipeline_lab.scenario import stack
from testing.pipeline_lab.scenario.checks import OUTCOMES, conversation_row, evaluate, outcome
from testing.pipeline_lab.scenario.spec import (
    FILL_WORDS,
    ScenarioError,
    admission_offset,
    fill_lines,
    load_scenario,
    parse_scenario,
    plan_events,
)

COMMITTED = sorted(stack.SCENARIO_DIR.glob('*.json'))

BASE = {
    'name': 'tiny',
    'origins': [{'id': 'O'}],
    'recordings': [
        {
            'id': 'A',
            'origin': 'O',
            'session': 'S1',
            'audio': [0, 20],
            'sealed_at': 30,
            'transcript_at': 90,
            'speech': [{'fill': [0, 20], 'every': 4, 'words': 5}],
        },
        {
            'id': 'B',
            'origin': 'O',
            'session': 'S2',
            'audio': [40, 60],
            'speech': [{'at': 41, 'end': 44, 'text': 'Synthetic words here.', 'is_user': False}],
        },
    ],
    'gaps': [{'origin': 'O', 'between': ['A', 'B']}],
    'sync': [
        {'id': 'F', 'origin': 'O', 'audio': [1, 2], 'arrives_at': 50, 'speech': [{'at': 1, 'end': 2, 'text': 'Hi.'}]}
    ],
    'finish': {'at': 55, 'provisional_latency': 10},
    'expect': [
        {'at': 70, 'conversation_of': '@finish', 'visible': True},
        {'conversation_of': '@finish', 'recordings': ['A', 'B', 'F']},
        {'no_hidden_with': 'A'},
    ],
}


def scenario(**changes):
    raw = copy.deepcopy(BASE)
    raw.update(changes)
    return parse_scenario(raw)


# ---- committed scenarios ---------------------------------------------------------------------------


def test_committed_scenarios_are_valid_and_named_after_their_file():
    assert {p.stem for p in COMMITTED} >= {'finish_after_reconnect_late_transcript', 'finish_single_recording_fast'}
    for path in COMMITTED:
        parsed = load_scenario(path)
        assert parsed.name == path.stem
        assert plan_events(parsed)


def test_incident_scenarios_are_plain_passes_since_the_finish_fix():
    # #26304 (SCA-4385) landed; a known-bug block left behind would turn a regression into exit 0.
    for path in COMMITTED:
        assert load_scenario(path).expected_failure is None, path.name


def test_incident_scenario_keeps_the_sca_4385_shape():
    parsed = load_scenario(stack.SCENARIO_DIR / 'finish_after_reconnect_late_transcript.json')
    a, b, f = (parsed.recording(x) for x in 'ABF')
    assert (a.audio, a.sealed_at, a.transcript_at) == ((0, 64), 109, 184)
    assert b.audio == (129, 154) and a.session != b.session and a.origin == b.origin == f.origin
    assert (f.lane, f.audio, f.arrives_at) == ('sync', (1.5, 2.7), 162)
    assert parsed.finish.at == 152 and parsed.finish_target().label == 'B'
    assert admission_offset(parsed, b) == 169  # the provisional transcript lands at +169 s
    assert parsed.gaps[0]['seconds'] == 65
    finish_row = {'conversation_of': '@finish', 'recordings': ['A', 'B', 'F'], 'visible': True, 'manual_end': True}
    assert finish_row in [c.raw for c in parsed.checks]


@pytest.mark.parametrize(
    'name, members',
    [('finish_after_reconnect_late_transcript', ['A', 'B', 'F']), ('finish_after_long_reconnect_gap', ['A', 'B'])],
)
def test_reconnect_checks_hold_for_one_finish_conversation(name, members):
    # Review of #26303: a visible non-manual conversation with every recording plus a visible manual one
    # holding only the Finish recording must not pass as "the Finish conversation holds them all".
    parsed = load_scenario(stack.SCENARIO_DIR / f'{name}.json')
    split = [conv('whole', members), conv('only_b', ['B'], manual_end=True)]
    assert not all(evaluate(c, split, 'B').ok for c in parsed.checks)
    merged = [conv('whole', members, manual_end=True)]
    assert all(evaluate(c, merged, 'B').ok for c in parsed.checks)


def test_long_gap_scenario_is_longer_than_the_silence_gap_and_reconnects_one_capture():
    parsed = load_scenario(stack.SCENARIO_DIR / 'finish_after_long_reconnect_gap.json')
    a, b = (parsed.recording(x) for x in 'AB')
    assert parsed.gaps[0]['seconds'] == 360 > 300  # the ordinary v3 silence gap
    assert a.origin == b.origin and a.session != b.session
    assert a.sealed_at < parsed.finish.at < admission_offset(parsed, b) < a.transcript_at


def test_batch_rows_name_their_capture_origin_and_session():
    from testing.pipeline_lab.scenario.ops import ScenarioOps

    parsed = load_scenario(stack.SCENARIO_DIR / 'finish_after_reconnect_late_transcript.json')
    ops = ScenarioOps.__new__(ScenarioOps)
    ops.scenario = parsed
    a, b = (ops._row(parsed.recording(x), created=0, status='completed') for x in 'AB')
    assert a['external_data']['recording_origin_id'] == b['external_data']['recording_origin_id']
    assert a['external_data']['recording_session_id'] != b['external_data']['recording_session_id']
    assert a['client_device_id'] == b['client_device_id']


def test_scenario_text_is_synthetic_placeholder_text():
    for path in COMMITTED:
        for rec in load_scenario(path).recordings:
            for line in rec.lines:
                words = [w.strip('.').lower() for w in line.text.split()]
                assert set(words) <= set(FILL_WORDS), (path.name, line.text)


# ---- parsing ---------------------------------------------------------------------------------------


def test_fill_lines_alternate_speakers_and_stay_inside_the_span():
    lines = fill_lines((0, 10), every=4, words=3, speakers=['SPEAKER_00', 'SPEAKER_01'], seed=0)
    assert [(l.start, l.end, l.speaker, l.is_user) for l in lines] == [
        (0, 3.5, 'SPEAKER_00', True),
        (4, 7.5, 'SPEAKER_01', False),
        (8, 10, 'SPEAKER_00', True),
    ]
    assert all(len(l.text.split()) == 3 for l in lines)


@pytest.mark.parametrize(
    'mutate, message',
    [
        (lambda r: r.update(name='Bad Name'), 'name'),
        (lambda r: r.update(t0='2026-03-14T09:00:00'), 'timezone'),
        (lambda r: r.update(origins=[]), 'origins'),
        (lambda r: r['recordings'][0].update(origin='X'), 'origin'),
        (lambda r: r['recordings'][0].update(audio=[5, 5]), 'start must be before end'),
        (lambda r: r['recordings'][0].update(sealed_at=10), 'sealed_at is before the audio ends'),
        (lambda r: r['recordings'][0].update(transcript_at=25), 'before the capture is sealed'),
        (lambda r: r['recordings'][1].update(speech=[{'at': 10, 'end': 12, 'text': 'x'}]), 'outside the audio'),
        (lambda r: r['recordings'][1].update(id='A'), 'unique'),
        (lambda r: r['recordings'][1].update(id='a'), 'ignoring case'),  # both would write scn-a
        (lambda r: r['sync'][0].update(id='b'), 'ignoring case'),
        (lambda r: r['origins'].append({'id': 'o'}), 'ignoring case'),
        (lambda r: r['recordings'][1].update(session='S1'), 'new recording session'),
        (lambda r: r['recordings'][0].update(bogus=1), 'unknown keys'),
        (lambda r: r['sync'][0].update(arrives_at=1.5), 'arrives after'),
        (lambda r: r['finish'].update(provisional_latency=1), 'before the capture is sealed'),
        (lambda r: r['expect'].append({'conversation_of': 'Z', 'visible': True}), 'unknown recording'),
        (lambda r: r['expect'].append({'conversation_of': 'A'}), 'at least one'),
        (lambda r: r['expect'].append({'no_hidden_with': 'A', 'visible': True}), 'no other fields'),
        (lambda r: r['expect'].append({'conversation_of': 'A', 'recordings': ['Q']}), 'declared recording'),
        (lambda r: r.update(expected_failure={'strict': True}), 'expected_failure'),
        (lambda r: r.update(expected_failure={'reason': 'SCA-1: known'}), 'expected_failure.checks'),
        (lambda r: r.update(expected_failure={'reason': 'SCA-1', 'checks': ['nope']}), 'unknown check label'),
        (lambda r: r['expect'][1].update(label='Bad Label'), 'label'),
        (lambda r: [c.update(label='same') for c in r['expect'][:2]], 'check labels must be unique'),
        (
            lambda r: [c.update(label=f'c{i}') for i, c in enumerate(r['expect'])]
            and r.update(expected_failure={'reason': 'SCA-1', 'checks': ['c0', 'c1', 'c2']}),
            'at least one check that must pass',
        ),
        (
            lambda r: r['recordings'].append(
                {'id': 'C', 'origin': 'O', 'session': 'S3', 'audio': [40, 58], 'speech': [{'fill': [40, 58]}]}
            ),
            'ambiguous',
        ),
        (lambda r: r.update(env={'X': 1}), 'env'),
    ],
)
def test_malformed_scenarios_are_refused(mutate, message):
    raw = copy.deepcopy(BASE)
    mutate(raw)
    with pytest.raises(ScenarioError, match=message):
        parse_scenario(raw)


def test_finish_alias_needs_a_finish():
    raw = copy.deepcopy(BASE)
    raw.pop('finish')
    with pytest.raises(ScenarioError, match='@finish needs a finish'):
        parse_scenario(raw)


# ---- plan ------------------------------------------------------------------------------------------


def test_sync_arrival_at_zero_is_kept_not_replaced_by_the_audio_end():
    sync = [
        {'id': 'F', 'origin': 'O', 'audio': [-5, -1], 'arrives_at': 0, 'speech': [{'at': -5, 'end': -1, 'text': 'Hi.'}]}
    ]
    parsed = scenario(sync=sync)
    arrivals = [parsed.offset(e.instant) for e in plan_events(parsed) if e.kind == 'sync' and e.ref == 'F']
    assert arrivals == [0]  # was -1: a falsy 0 fell back to the audio end


def test_plan_orders_events_and_places_the_provisional_transcript_after_the_tap():
    parsed = scenario()
    plan = [(parsed.offset(e.instant), e.kind, e.ref) for e in plan_events(parsed)]
    assert plan == [
        (0, 'capture_start', 'A'),
        (30, 'seal', 'A'),
        (35, 'admission', 'A'),  # seal + admission_lag
        (40, 'capture_start', 'B'),
        (50, 'sync', 'F'),
        (55, 'finish', 'finish'),
        (60, 'seal', 'B'),
        (65, 'admission', 'B'),  # finish + provisional latency
        (70, 'checkpoint', 'expect[0]'),
        (90, 'transcript', 'A'),
    ]
    event = plan_events(parsed)[0]
    # what V3Driver reads from an arrival
    assert (event.recording_id, event.instant_source, event.instant) == ('A', 'capture_start', parsed.t0)


def test_finish_target_is_the_capture_still_open_until_its_seal():
    # Review of #26303: audio [0, 40], seal at 50, a tap at 42 still finds the row in_progress (only the
    # seal completes it), so the fast-finish transcript lands at 42 + 30, not at seal + lag.
    raw = {
        'name': 'late_tap',
        'origins': [{'id': 'O'}],
        'recordings': [{'id': 'B', 'origin': 'O', 'audio': [0, 40], 'sealed_at': 50, 'speech': [{'fill': [0, 40]}]}],
        'finish': {'at': 42, 'provisional_latency': 30},
    }
    parsed = parse_scenario(raw)
    assert parsed.finish_target().label == 'B'
    assert admission_offset(parsed, parsed.recording('B')) == 72
    raw['finish'] = {'at': 50.5, 'provisional_latency': 30}  # after the seal: nothing is capturing
    parsed = parse_scenario(raw)
    assert parsed.finish_target() is None
    assert admission_offset(parsed, parsed.recording('B')) == 55


def test_finish_target_is_the_newest_open_capture():
    # get_in_progress_conversation orders by created_at descending: A is open until its seal at 45, B from 40.
    raw = copy.deepcopy(BASE)
    raw['recordings'][0]['sealed_at'] = 45
    raw['recordings'][0]['transcript_at'] = 90
    parsed = parse_scenario({**raw, 'finish': {'at': 42, 'provisional_latency': 20}})
    assert [r.label for r in parsed.open_at(42)] == ['A', 'B']
    assert parsed.finish_target().label == 'B'


def test_ties_run_finish_before_seal_and_without_fast_finish_admission_follows_the_seal():
    parsed = scenario(finish={'at': 60, 'fast_finish': False})
    assert parsed.finish_target().label == 'B'  # the tap ties B's seal and runs first: B is still capturing
    parsed = scenario(finish={'at': 60.5, 'fast_finish': False})
    assert parsed.finish_target() is None
    parsed = scenario(finish={'at': 59.5, 'fast_finish': False})
    kinds = [(parsed.offset(e.instant), e.kind) for e in plan_events(parsed) if e.ref in ('B', 'finish')]
    assert kinds == [(40, 'capture_start'), (59.5, 'finish'), (60, 'seal'), (65, 'admission')]
    same = scenario(finish={'at': 40, 'provisional_latency': 20})
    order = [e.kind for e in plan_events(same) if same.offset(e.instant) == 40]
    assert order == ['capture_start', 'finish']
    assert same.t0 + timedelta(seconds=60) == next(
        e.instant for e in plan_events(same) if e.kind == 'admission' and e.ref == 'B'
    )


# ---- checks ----------------------------------------------------------------------------------------


def conv(handle, recordings, *, visible=True, reason=None, manual_end=False, words=10, deleted=False):
    return {
        'handle': handle,
        'recordings': recordings,
        'words': words,
        'visible': visible,
        'hidden_reason': reason,
        'manual_end': manual_end,
        'kind': 'conversation',
        'status': 'completed',
        'deleted': deleted,
    }


def test_checks_read_the_incident_result_as_failures_and_the_fixed_result_as_passes():
    parsed = scenario()
    exact, hidden = parsed.checks[1], parsed.checks[2]
    incident = [conv('c1', ['F', 'B'], manual_end=True), conv('c2', ['A'], visible=False, reason='below_word_minimum')]
    results = [evaluate(exact, incident, 'B'), evaluate(hidden, incident, 'B')]
    assert [r.ok for r in results] == [False, False]
    assert "recordings=['F', 'B']" in results[0].detail and 'below_word_minimum' in results[1].detail
    fixed = [conv('c1', ['A', 'B', 'F'], manual_end=True), conv('old', ['A'], visible=False, deleted=True)]
    assert evaluate(exact, fixed, 'B').ok and evaluate(hidden, fixed, 'B').ok


def test_conversation_checks_name_missing_targets():
    parsed = scenario()
    assert not evaluate(parsed.checks[0], [], 'B').ok
    assert evaluate(parsed.checks[0], [], None).detail == 'the Finish cut no recording'
    assert evaluate(parsed.checks[0], [conv('c', ['B'])], 'B').ok


def labelled(**changes):
    raw = copy.deepcopy(BASE)
    raw['expect'] = [
        {'label': 'finish_visible', 'conversation_of': '@finish', 'visible': True, 'manual_end': True},
        {'label': 'merged', 'conversation_of': '@finish', 'recordings': ['A', 'B', 'F']},
    ]
    raw.update(changes)
    return parse_scenario(raw)


def results_for(parsed, snapshot, finish_label='B'):
    return [evaluate(check, snapshot, finish_label) for check in parsed.checks]


def test_outcomes_and_exit_codes():
    known = {'reason': 'SCA-1: known', 'checks': ['merged']}
    plain, xfail, loose = (
        labelled(),
        labelled(expected_failure=known),
        labelled(expected_failure={**known, 'strict': False}),
    )
    good = results_for(plain, [conv('c', ['A', 'B', 'F'], manual_end=True)])
    incident = results_for(plain, [conv('c', ['F', 'B'], manual_end=True), conv('d', ['A'], visible=False)])
    assert [r.ok for r in incident] == [True, False]
    assert [outcome(plain, good), outcome(plain, incident), outcome(xfail, incident), outcome(xfail, good)] == [
        'passed',
        'failed',
        'xfail',
        'xpass',
    ]
    assert outcome(loose, good) == 'passed' and outcome(plain, good, error='boom') == 'error'
    assert [OUTCOMES[o] for o in ('passed', 'xfail', 'failed', 'xpass', 'error')] == [0, 0, 1, 1, 2]


def test_expected_failure_does_not_excuse_checks_it_does_not_name():
    # Review of #26303: an empty run with no Finish target failed every check and still read as XFAIL.
    xfail = labelled(expected_failure={'reason': 'SCA-1: known', 'checks': ['merged']})
    assert outcome(xfail, results_for(xfail, [], None)) == 'failed'
    assert outcome(xfail, results_for(xfail, [], 'B')) == 'failed'
    not_manual = results_for(xfail, [conv('c', ['F', 'B'])])  # the Finish conversation lost its manual end
    assert [r.ok for r in not_manual] == [False, False] and outcome(xfail, not_manual) == 'failed'
    assert outcome(xfail, results_for(xfail, [], 'B'), error='boom') == 'error'


def test_conversation_row_keeps_safe_fields_only():
    row = {
        'id': 'v3-conversation-id-long',
        'v3_recording_ids': ['scn-a', 'scn-b', 'other'],
        'home_hidden': True,
        'home_hidden_reason': 'below_word_minimum',
        'status': 'completed',
        'structured': {'title': 'private title'},
        'transcript_segments': [{'text': 'private words'}],
    }
    label = {'scn-a': 'A', 'scn-b': 'B'}.get
    summary = conversation_row(row, lambda rid: label(rid) or '?' + rid[:8], 4)
    assert summary['recordings'] == ['A', 'B', '?other'] and summary['handle'] == 'v3-conve'
    assert summary['visible'] is False and summary['hidden_reason'] == 'below_word_minimum'
    assert 'private' not in json.dumps(summary)


# ---- command line ----------------------------------------------------------------------------------


def test_cli_scenario_check_prints_the_plan_without_a_stack(capsys):
    assert cli.main(['scenario', 'check', 'finish_single_recording_fast']) == 0
    out = capsys.readouterr().out
    assert 'finish_single_recording_fast: valid' in out and 'admission     B' in out
    assert cli.main(['--json', 'scenario', 'check', str(COMMITTED[0])]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])[0]['plan']


def test_cli_scenario_refuses_unknown_files_and_output_inside_git(capsys, tmp_path):
    assert cli.main(['scenario', 'check', 'no_such_scenario']) == 2
    assert 'no such file' in capsys.readouterr().err
    inside = stack.BACKEND / 'testing' / 'pipeline_lab' / 'scenario' / 'out'
    assert cli.main(['scenario', 'run', 'finish_single_recording_fast', '--keep', str(inside)]) == 2
    assert 'outside every git worktree' in capsys.readouterr().err
    assert not inside.exists()


def test_report_formats_timeline_tables_and_checks():
    result = {
        'scenario': 'tiny',
        'outcome': 'xfail',
        'seconds': 12.3,
        'expected_failure': {'reason': 'SCA-4385: known'},
        'timeline': [
            {'t': 0.0, 'kind': 'capture_start', 'ref': 'A', 'outcome': 'recording', 'session': 'S1'},
            {'t': 70.0, 'kind': 'task', 'ref': 'reconcile', 'outcome': 'error', 'error': 'X', 'where': ['f.py:1 g']},
        ],
        'checkpoints': {'0': {'t': 70, 'conversations': [conv('c1', ['B'], manual_end=True)]}},
        'conversations': [conv('c1', ['F', 'B']), conv('c2', ['A'], visible=False, reason='below_word_minimum')],
        'recordings': [{'label': 'A', 'lane': 'batch', 'words': 5, 'claims': 1}],
        'finish_target': 'B',
        'checks': [
            {'check': 'conversation of @finish: visible=true', 'ok': False, 'detail': 'no conversation holds B'}
        ],
    }
    text = stack.format_report(result)
    assert '== tiny: XFAIL' in text and 'expected failure: SCA-4385' in text
    assert 'capture_start A' in text and 'session=S1' in text and "X at ['f.py:1 g']" in text
    assert 'conversations at +70s:' in text and 'below_word_minimum' in text and 'F+B' in text
    assert 'FAIL  conversation of @finish' in text
