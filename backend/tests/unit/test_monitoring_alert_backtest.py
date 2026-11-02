"""Synthetic Grafana chain/state tests and the offline admission contract."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/alert_backtest.py'
spec = importlib.util.spec_from_file_location('alert_backtest', SCRIPT)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def rule(kind='threshold', duration='2m', state='OK'):
    return {
        'uid': 'fixture',
        'for': duration,
        'noDataState': state,
        'condition': 'C',
        'data': [
            {'refId': 'A', 'datasourceUid': 'prometheus', 'model': {'expr': 'fixture_total', 'instant': True}},
            {
                'refId': 'B',
                'datasourceUid': '__expr__',
                'model': {'type': 'reduce', 'expression': 'A', 'reducer': 'max'},
            },
            {
                'refId': 'C',
                'datasourceUid': '__expr__',
                'model': {
                    'type': kind,
                    'expression': 'B',
                    'conditions': [{'evaluator': {'type': 'gt', 'params': [5]}}],
                },
            },
        ],
    }


def test_reduce_is_over_time_per_series_and_threshold_is_strict():
    result = b.evaluate(rule(), {'A': {(('pod', 'a'),): [1, 7, 2], (('pod', 'b'),): [5]}})
    assert result == {(('pod', 'a'),): 1, (('pod', 'b'),): 0}


def test_pending_does_not_cross_labels_or_false_samples():
    samples = [(t, {(('pod', str(t // 120)),): 1}) for t in range(0, 600, 60)]
    assert b.episodes(rule(), samples, 0, 540, 60)['episodes'] == 0
    samples = [(t, {(): float(t in (0, 60, 120, 180, 300))}) for t in range(0, 420, 60)]
    result = b.episodes(rule(), samples, 0, 360, 60)
    assert result['episodes'] == 1
    assert result['total_duration_seconds'] == 120
    assert result['longest_seconds'] == 120


@pytest.mark.parametrize('state,count', [('OK', 0), ('NoData', 0), ('Alerting', 1)])
def test_no_data_policy(state, count):
    result = b.episodes(rule(state=state), [(t, {}) for t in range(0, 300, 60)], 0, 240, 60)
    assert result['episodes'] == count
    assert result['unknown_ticks'] == (5 if state == 'NoData' else 0)


def test_keep_last_does_not_invent_a_resolved_transition():
    result = b.episodes(rule(duration='0s', state='KeepLast'), [(0, {(): 1}), (60, {}), (120, {(): 0})], 0, 120, 60)
    assert result['total_duration_seconds'] == 120
    assert result['unknown_ticks'] == 1


def test_math_joins_by_labels_and_scalar_broadcasts():
    inputs = {'A': {(('pod', 'a'),): [7], (('pod', 'b'),): [2]}, 'B': {(('pod', 'a'),): [1]}, 'D': {(): [5]}}
    assert b.joined_math('$A > $D && $B == 1', inputs) == {(('pod', 'a'),): [1]}
    assert b.joined_math('$A / $D', inputs)[(('pod', 'b'),)] == [0.4]
    with pytest.raises(b.Unsupported):
        b.math_expression('__import__("os")', {})
    with pytest.raises(b.Unsupported):
        b.joined_math('$A + $B', {'A': {(): [1], (('pod', 'a'),): [2]}, 'B': {(): [2]}})


def test_classic_reduces_and_combines_conditions():
    r = rule()
    r['data'][2]['model'] = {
        'type': 'classic_conditions',
        'conditions': [
            {
                'query': {'params': ['A']},
                'reducer': {'type': 'mean'},
                'evaluator': {'type': 'gt', 'params': [3]},
                'operator': {'type': 'and'},
            },
            {
                'query': {'params': ['B']},
                'reducer': {'type': 'last'},
                'evaluator': {'type': 'lt', 'params': [10]},
                'operator': {'type': 'and'},
            },
        ],
    }
    assert b.evaluate(r, {'A': {(): [2, 6]}}) == {(): 1}


def test_nonfinite_reduction_modes_and_ranges():
    assert b.reduce_values([1, float('nan'), 3], 'mean', {'mode': 'dropNN'}) == 2
    assert b.reduce_values([1, float('nan')], 'sum', {'mode': 'replaceNN', 'replaceWithValue': 2}) == 3
    assert b.threshold(5, {'type': 'within_range', 'params': [2, 8]}) == 1
    assert b.threshold(8, {'type': 'outside_range', 'params': [2, 8]}) == 1


def test_flap_counts_short_instance_episodes():
    result = b.episodes(rule(duration='0s'), [(t, {(): float(t % 120 == 0)}) for t in range(0, 1200, 60)], 0, 1140, 60)
    assert result['episodes'] == 10 and result['flap']


def test_metric_inventory_extraction_includes_bare_metrics():
    assert b.metric_names('sum(rate(foo_total{reason="secret"}[5m])) / clamp_min(bar, 1) or vector(0)') == {
        'foo_total',
        'bar',
    }
    assert b.metric_names('max by (pod) (up) unless on (pod) baz offset 1h') == {'up', 'baz'}


def test_lint_blocks_new_dead_metric_and_edited_legacy_debt():
    r = rule()
    inventory = {'metrics': []}
    assert b.lint({'fixture': r}, inventory)['failures']
    inventory['legacy_debt'] = {'fixture': {'sha256': b.fingerprint(r), 'errors': b.lint_rule(r, inventory)}}
    assert not b.lint({'fixture': r}, inventory)['failures']
    r['for'] = '3m'
    assert b.lint({'fixture': r}, inventory)['failures']


def test_declared_metrics_allow_source_backed_rules_without_claiming_observation():
    r = rule()
    inventory = {'metrics': [], 'declared_metrics': ['fixture_total']}

    assert not b.lint({'fixture': r}, inventory)['failures']
    assert inventory['metrics'] == []


def test_committed_offline_admission_gate():
    assert not b.lint(b.rules(), json.loads(b.INVENTORY.read_text()))['failures']


def test_replay_range_frames_honor_offsets_and_resolution():
    r = rule(duration='0s')
    r['data'][0]['model'].update(instant=False, intervalMs=30000, maxDataPoints=100)
    r['data'][0]['relativeTimeRange'] = {'from': 120, 'to': 30}
    calls = []

    class Client:
        def get(self, endpoint, **params):
            calls.append((endpoint, params))
            if endpoint == 'query':
                return {'result': [{'value': [0, '1']}]}
            return {'result': [{'metric': {'pod': 'a'}, 'values': [[params['start'], '7'], [params['end'], '1']]}]}

    result = b.replay(r, Client(), 300, 600, 300)
    assert result['episodes'] == 1
    queries = [params for endpoint, params in calls if endpoint == 'query_range']
    assert queries == [
        dict(query='fixture_total', start=180, end=270, step=30),
        dict(query='fixture_total', start=480, end=570, step=30),
    ]


def test_lint_rejects_cycles_noisy_no_pending_and_bad_boolean_units():
    r = rule(duration='0s')
    r['data'][0]['model']['expr'] = 'rate(fixture_total[5m])'
    assert 'no pending duration on noisy rate/ratio/average' in b.lint_rule(r, {'metrics': ['fixture_total']})
    r['data'][1]['model'] = {'type': 'math', 'expression': '$A > 0'}
    assert 'boolean threshold outside [0,1]' in b.lint_rule(r, {'metrics': ['fixture_total']})
    r['data'][1]['model']['expression'] = '$C > 0'
    assert any('cyclic' in error for error in b.lint_rule(r, {'metrics': ['fixture_total']}))


def test_retired_proactive_rule_is_absent_from_both_exports():
    assert 'omi-chat-first-proactive-stalled' not in b.rules()
    combined = json.loads((b.MONITORING / 'alert-rules.json').read_text())
    assert all(r['uid'] != 'omi-chat-first-proactive-stalled' for r in combined)


def test_admission_hold_cannot_be_unpaused_by_a_quiet_lint():
    r = rule()
    inventory = {'metrics': ['fixture_total'], 'admission_holds': {'fixture': 'incident triage required'}}
    assert b.lint({'fixture': r}, inventory)['failures']
    r['isPaused'] = True
    assert not b.lint({'fixture': r}, inventory)['failures']


def test_daily_chunks_preserve_grid_and_series_identity(monkeypatch):
    client = b.Prometheus(url='http://unused.invalid')
    calls = []

    def get(endpoint, **params):
        calls.append(params)
        return {
            'result': [
                {
                    'metric': {'pod': 'a'},
                    'values': [[t, '1'] for t in range(params['start'], params['end'] + 1, params['step'])],
                }
            ]
        }

    monkeypatch.setattr(client, 'get', get)
    series = client.range('fixture_total', 0, 86400, 300)
    assert [t for t, _ in series[0]['values']] == list(range(0, 86401, 300))
    assert [(c['start'], c['end']) for c in calls] == [(0, 86100), (86400, 86400)]


def test_debt_fingerprint_ignores_routing_and_annotations():
    rule = next(iter(b.rules().values()))
    rerouted = json.loads(json.dumps(rule))
    rerouted['notification_settings'] = {'receiver': 'x', 'repeat_interval': '24h'}
    rerouted['annotations'] = {**rerouted.get('annotations', {}), '__dashboardUid__': 'other'}
    rerouted['labels'] = {**rerouted.get('labels', {}), 'severity': 'warning'}
    assert b.fingerprint(rerouted) == b.fingerprint(rule)
    retuned = json.loads(json.dumps(rule))
    retuned['for'] = '99m'
    assert b.fingerprint(retuned) != b.fingerprint(rule)
