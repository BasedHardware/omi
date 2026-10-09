"""Synthetic-only keep-rescue contract and offline benchmark acceptance."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[3]


def harness():
    spec = importlib.util.spec_from_file_location('pilot_harness', ROOT / 'benchmarks/jev-vs-rules/harness.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    'score,rescued',
    [
        (0.79, True),
        (0.80, False),
        (0.81, False),
        (None, True),
        (float('nan'), True),
        (-1, True),
        (2, True),
        (True, True),
    ],
)
def test_policy_boundaries(score, rescued):
    from utils.conversations.relevance_rescue import rescue_decision

    assert rescue_decision(lambda: score).rescued is rescued


def test_error_is_conservative():
    from utils.conversations.relevance_rescue import rescue_decision

    result = rescue_decision(Mock(side_effect=TimeoutError))
    assert (result.rescued, result.outcome, result.score) == (True, 'error_keep', None)


@pytest.mark.parametrize(
    'reason,eligible',
    [
        ('filler_only', True),
        ('no_content_words', True),
        ('calendar_overlap', False),
        ('mic_check', False),
        ('empty_transcript', False),
    ],
)
def test_admission(reason, eligible):
    from utils.conversations.relevance_rescue import should_rescue

    assert should_rescue(['um'], reason) is eligible
    assert not should_rescue([], reason)


def test_off_and_shadow_identity_and_calendar(monkeypatch):
    from utils.conversations import relevance_rescue as rescue
    from utils.conversations.relevance import decide_relevance
    from utils.conversations.processing_trigger import ProcessingTrigger

    calls = Mock(return_value=rescue.rescue_decision(lambda: 0.79))
    metrics = Mock()
    monkeypatch.setattr(rescue, 'score_segments', calls)
    monkeypatch.setattr(rescue, 'record_rescue', metrics)
    kwargs = dict(
        trigger=ProcessingTrigger.CAPTURE_END,
        texts=['um'],
        speech_seconds=1,
        has_photos=False,
        user_kept=False,
        exempt=False,
        trusted_wake_word=False,
        model_discards=None,
        calendar_retains=lambda: False,
    )
    monkeypatch.delenv(rescue.FLAG, raising=False)
    baseline = decide_relevance(**kwargs)
    assert baseline.as_record() == dict(
        verdict='discard', decided_by='rule', reason='filler_only', trigger='capture_end', rules_version=1
    )
    calls.assert_not_called()
    metrics.assert_not_called()
    monkeypatch.setenv(rescue.FLAG, 'off')
    assert decide_relevance(**kwargs).as_record() == baseline.as_record()
    monkeypatch.setenv(rescue.FLAG, 'invalid')
    assert decide_relevance(**kwargs).as_record() == baseline.as_record()
    calls.assert_not_called()
    monkeypatch.setenv(rescue.FLAG, 'shadow')
    assert decide_relevance(**kwargs).as_record() == baseline.as_record()
    metrics.assert_called_once_with(mode='shadow', rule='filler_only', outcome='rescue')
    monkeypatch.setenv(rescue.FLAG, 'on')
    decision = decide_relevance(**kwargs)
    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'jev', 'rescue_filler_only')
    assert decision.jev_p_discard == 0.79
    calls.reset_mock()
    kwargs['calendar_retains'] = lambda: True
    assert decide_relevance(**kwargs).reason == 'calendar_overlap'
    calls.assert_not_called()


def test_fixtures_and_generator():
    h = harness()
    rows = h.load_fixtures()
    assert len(rows) >= 90
    assert len({row['family_id'] for row in rows}) == len(rows)
    for rule in ('R03', 'R08', 'R16'):
        assert sum(rule in row['rule_ids'] for row in rows) >= 30
    for row in rows:
        assert row['provenance'] == 'synthetic'
        assert row['expected_baseline'] == h.baseline(row)
        if 'R16' in row['rule_ids']:
            assert row['expected_without_calendar'] == h.baseline(row, without_calendar=True)
    spec = importlib.util.spec_from_file_location(
        'fixture_generator', ROOT / 'benchmarks/jev-vs-rules/generate_fixtures.py'
    )
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    assert generator.generate() == rows


@pytest.mark.parametrize('status', [None, '', 'reviewed', 'ground_truth', 'agent_proposed_unreviewed '])
def test_fixture_labels_must_be_provisional(tmp_path, monkeypatch, status):
    h = harness()
    row = json.loads(h.FIXTURES.read_text().splitlines()[0])
    if status is None:
        row.pop('label_status')
    else:
        row['label_status'] = status
    path = tmp_path / 'fixtures.jsonl'
    path.write_text(json.dumps(row) + '\n')
    baseline = Mock()
    monkeypatch.setattr(h, 'baseline', baseline)
    with pytest.raises(ValueError, match='label_status must be agent_proposed_unreviewed'):
        h.load_fixtures(path)
    baseline.assert_not_called()


def test_matrix_and_calendar_counterfactual():
    h = harness()
    rows = h.load_fixtures()
    keep = next(r for r in rows if r['keep_label'] == 'keep' and r['expected_baseline']['verdict'] == 'discard')
    noise = next(r for r in rows if r['keep_label'] == 'discard' and r['expected_baseline']['verdict'] == 'discard')
    calendar = next(r for r in rows if 'R16' in r['rule_ids'] and r['calendar'] and r['keep_label'] == 'discard')
    client = h.MockJevClient({r['family_id']: 0.79 for r in (keep, noise, calendar)})
    results = h.evaluate([keep, noise, calendar], client)
    assert results[2]['baseline']['reason'] == 'calendar_overlap'
    assert results[2]['final'] == results[2]['baseline']
    assert results[2]['without_calendar']['rescued']
    summary = h.summarize(results)
    assert summary['label_status'] == 'agent_proposed_unreviewed'
    assert all(result['label_status'] == summary['label_status'] for result in results)
    assert summary['totals']['false_discard_delta'] == -1
    assert summary['totals']['false_keep_delta'] == 1
    assert sum(cell['families'] for cell in summary['matrix']) == 3
    assert results[0]['agreement'] is True
    assert 'calendar' not in client.calls[0]['state'].lower()


def test_prompt_matches_shipped_shape():
    h = harness()
    relevance_jev = h.runtime()['utils.conversations.relevance_jev']

    state, questions = h.prompt(['stop', "don't go"])
    assert state == relevance_jev.relevance_state("Speaker 0: stop\n\nSpeaker 0: don't go")
    assert state == "Transcript:\n```\nSpeaker 0: stop\n\nSpeaker 0: don't go\n```\nWord count: 7 words."
    assert questions == relevance_jev.QUESTIONS
    assert 'Losing a real memory' in questions['worth_keeping']['instructions']


def test_live_guard_precedes_client_import(monkeypatch):
    spec = importlib.util.spec_from_file_location('score_real', ROOT / 'benchmarks/jev-vs-rules/score_real.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv('JEV_PILOT_LIVE', raising=False)
    with pytest.raises(SystemExit, match='JEV_PILOT_LIVE=1'):
        module.main([])


@pytest.mark.parametrize(
    'score,verdict,outcome',
    [(0.79, 'keep', 'rescue'), (0.80, 'discard', 'discard_stands'), (None, 'keep', 'error_keep')],
)
@pytest.mark.parametrize('mode', ['on', 'shadow'])
def test_wired_policy(mode, score, verdict, outcome, monkeypatch):
    from utils.conversations import relevance_rescue as rescue
    from utils.conversations.relevance import decide_relevance
    from utils.conversations.processing_trigger import ProcessingTrigger

    monkeypatch.setenv(rescue.FLAG, mode)
    monkeypatch.setattr(rescue, 'score_segments', lambda segments: rescue.rescue_decision(lambda: score))
    record = Mock()
    monkeypatch.setattr(rescue, 'record_rescue', record)
    decision = decide_relevance(
        trigger=ProcessingTrigger.CAPTURE_END,
        texts=['stop'],
        speech_seconds=None,
        has_photos=False,
        user_kept=False,
        exempt=False,
        trusted_wake_word=False,
        model_discards=None,
        calendar_retains=lambda: False,
    )
    assert decision.verdict == ('discard' if mode == 'shadow' else verdict)
    record.assert_called_once_with(mode=mode, rule='no_content_words', outcome=outcome)


def test_score_segments_uses_real_client_seam(monkeypatch):
    from utils.conversations import relevance_rescue as rescue

    h = harness()
    # Run the real relevance_jev module with its offline transport seam scoped to this call.
    jev = h.runtime()['utils.conversations.relevance_jev']
    asked = Mock(return_value=type('Answers', (), {'noul': lambda self, name: 0.21})())
    monkeypatch.setitem(jev.jev_discard_probability.__globals__, 'ask_jev', asked)
    from unittest.mock import patch
    import sys

    with patch.dict(sys.modules, {'utils.conversations.relevance_jev': jev}):
        result = rescue.score_segments(['stop'])
    assert result.rescued
    asked.assert_called_once_with(
        'Transcript:\n```\nSpeaker 0: stop\n```\nWord count: 3 words.', jev.QUESTIONS, lane=jev.LANE
    )


def test_all_fixture_records_are_identical_off_and_shadow(monkeypatch):
    from utils.conversations import relevance_rescue as rescue
    from utils.conversations.relevance import decide_relevance
    from utils.conversations.processing_trigger import ProcessingTrigger
    import json

    h = harness()
    calls = Mock(return_value=rescue.rescue_decision(lambda: 0.79))
    monkeypatch.setattr(rescue, 'score_segments', calls)
    monkeypatch.setattr(rescue, 'record_rescue', Mock())
    for row in h.load_fixtures():
        kwargs = dict(
            trigger=ProcessingTrigger.CAPTURE_END,
            texts=row['segments'],
            speech_seconds=None,
            has_photos=False,
            user_kept=False,
            exempt=False,
            trusted_wake_word=False,
            model_discards=lambda error, neighbor: False,
            calendar_retains=lambda: h.calendar_retains(row),
        )
        monkeypatch.setenv(rescue.FLAG, 'off')
        before = decide_relevance(**kwargs)
        expected = dict(row['expected_baseline'], trigger='capture_end', rules_version=1)
        assert json.dumps(before.as_record(), sort_keys=True) == json.dumps(expected, sort_keys=True)
        monkeypatch.setenv(rescue.FLAG, 'shadow')
        assert json.dumps(decide_relevance(**kwargs).as_record(), sort_keys=True) == json.dumps(
            before.as_record(), sort_keys=True
        )


def test_uncertain_excluded_from_errors_and_call_reuse():
    h = harness()
    row = next(
        r
        for r in h.load_fixtures()
        if r['keep_label'] == 'uncertain' and r['expected_baseline']['verdict'] == 'discard'
    )
    client = h.MockJevClient({row['family_id']: None})
    results = h.evaluate([row], client)
    assert results[0]['agreement'] is None
    assert h.summarize(results)['totals']['false_keep_delta'] == 0
    row = next(r for r in h.load_fixtures() if 'R16' in r['rule_ids'] and r['calendar'] is None)
    client = h.MockJevClient()
    h.evaluate([row], client)
    assert len(client.calls) == 1


def test_metrics_are_bounded(monkeypatch):
    from utils import metrics

    counter = Mock()
    monkeypatch.setattr(metrics, 'CONVERSATION_RELEVANCE_RESCUE_TOTAL', counter)
    metrics.record_conversation_relevance_rescue(mode='shadow', rule='filler_only', outcome='rescue')
    counter.labels.assert_called_with(mode='shadow', rule='filler_only', outcome='rescue')
    metrics.record_conversation_relevance_rescue(mode='secret', rule='private text', outcome='private text')
    counter.labels.assert_called_with(mode='other', rule='other', outcome='other')


def test_missing_score_fallback_telemetry(monkeypatch):
    from utils.conversations import relevance_rescue as rescue
    from utils.observability import fallback
    from utils import metrics

    monkeypatch.setattr(metrics, 'record_conversation_relevance_rescue', Mock())
    record = Mock()
    monkeypatch.setattr(fallback, 'record_fallback', record)
    rescue.record_rescue(mode='shadow', rule='filler_only', outcome='error_keep')
    record.assert_called_once_with(
        component='conversation_relevance', from_mode='jev', to_mode='keep', reason='model_error', outcome='recovered'
    )


def test_real_runner_accounting_with_fake_client(capsys):
    spec = importlib.util.spec_from_file_location('score_real', ROOT / 'benchmarks/jev-vs-rules/score_real.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    answer = type('Answers', (), {'usage': {}, 'noul': lambda self, name: 0.21})()
    ask = Mock(return_value=answer)
    client = module.RealJevClient(ask)
    assert client.score('synthetic', 'synthetic transcript', {}) == pytest.approx(0.79)
    assert client.accounting[0]['cost_usd'] is None
    assert client.accounting[0]['cost_status'] == 'COULD NOT DETERMINE'
    assert client.accounting[0]['latency_seconds'] >= 0
    assert 'synthetic transcript' not in capsys.readouterr().out
    answer.usage = {'cost': 0.001}
    client.score('synthetic', 'synthetic transcript', {})
    assert client.accounting[-1]['cost_usd'] == 0.001


def test_noneligible_paths_never_score(monkeypatch):
    from utils.conversations import relevance_rescue as rescue
    from utils.conversations.relevance import decide_relevance
    from utils.conversations.processing_trigger import ProcessingTrigger

    monkeypatch.setenv(rescue.FLAG, 'on')
    score = Mock(side_effect=AssertionError('noneligible must never score'))
    monkeypatch.setattr(rescue, 'score_segments', score)
    kwargs = dict(
        trigger=ProcessingTrigger.CAPTURE_END,
        texts=['testing one two three'],
        speech_seconds=None,
        has_photos=False,
        user_kept=False,
        exempt=False,
        trusted_wake_word=False,
        model_discards=lambda error, neighbor: False,
        calendar_retains=lambda: False,
    )
    assert decide_relevance(**kwargs).reason == 'mic_check'
    kwargs['texts'] = ['']
    assert decide_relevance(**kwargs).reason == 'empty_transcript'
    kwargs['texts'] = ['um']
    for key in ('has_photos', 'user_kept', 'exempt', 'trusted_wake_word'):
        assert decide_relevance(**dict(kwargs, **{key: True})).verdict == 'keep'
    score.assert_not_called()
