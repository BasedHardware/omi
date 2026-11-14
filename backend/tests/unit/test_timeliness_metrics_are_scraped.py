"""Every eligible timeliness leader must export its result through both filters."""

import ast
import json
import os
import io
import subprocess
import sys
import tokenize
from pathlib import Path
import re

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[2]


def timeliness_metric_names(source=None):
    # Read the whole registration section, including names outside timeliness_*.
    # Avoid importing the producer's database dependencies or executing any scans.
    if source is None:
        source = (BACKEND / 'utils/batch_pipeline/metrics.py').read_text()
    markers = [
        token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT and '2-hour timeliness alarm' in token.string
    ]
    assert len(markers) == 1, 'QueueMetrics timeliness section marker missing or ambiguous'
    tree = ast.parse(source)
    queue = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'QueueMetrics')
    init = next(node for node in queue.body if isinstance(node, ast.FunctionDef) and node.name == '__init__')
    ended = False
    names = []
    for node in init.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Attribute):
            continue
        attribute = node.targets[0].attr
        if node.lineno <= markers[0]:
            continue
        if attribute == '_timeliness_due':
            ended = True
            break
        if isinstance(node.value, ast.Call):
            name = ast.literal_eval(node.value.args[0])
            assert isinstance(name, str) and name.startswith('omi_')
            names.append(name)
    assert ended and names, 'QueueMetrics timeliness registration section not found'
    return names


def test_new_family_before_first_existing_registration_is_discovered():
    source = (BACKEND / 'utils/batch_pipeline/metrics.py').read_text()
    addition = "        self.future_sampler = Gauge('omi_batch_future_sampler_units', 'future', registry=registry)\n"
    modified = source.replace('        self.timeliness_age = ', addition + '        self.timeliness_age = ', 1)
    assert 'omi_batch_future_sampler_units' in timeliness_metric_names(modified)


@pytest.mark.parametrize('stage', ['dev', 'prod'])
def test_timeliness_families_survive_cloud_run_and_prometheus_bridge(stage):
    config = yaml.safe_load((BACKEND / 'deploy/cloud_run_gmp_sync.yaml').read_text())
    rules = config['spec']['endpoints'][0]['metricRelabeling']
    keep = next(rule for rule in rules if rule['action'] == 'keep')
    assert keep['sourceLabels'] == ['__name__']
    bridge = yaml.safe_load(
        (
            BACKEND
            / f'charts/monitoring/prometheus-stackdriver-exporter/{stage}_sync_omi_cloud_run_metrics_exporter.yaml'
        ).read_text()
    )['stackdriver']['metrics']
    assert '"backend-integration"' in ' '.join(bridge['filters'])
    for name in timeliness_metric_names():
        assert re.fullmatch(keep['regex'], name), f'Cloud Run drops {name}'
        # Check subsequent drop rules too: both sources use the same closed labels.
        labels = {'__name__': name}
        for rule in rules:
            if rule['action'] == 'drop':
                value = ';'.join(labels.get(label, '') for label in rule['sourceLabels'])
                assert not re.fullmatch(rule['regex'], value), f'Cloud Run drops {name}'
        assert any(
            f'prometheus.googleapis.com/{name}/'.startswith(prefix) for prefix in bridge['prefixes']
        ), f'Prometheus bridge drops {name}'


OBSERVED = 'max_over_time(omi_batch_timeliness_observed_at_seconds[20m])'
NEWEST = f'({OBSERVED} == scalar(max({OBSERVED})))'
FRESH_NEWEST = f'({NEWEST} and (time() - {OBSERVED} < 1200))'


def consuming_expressions():
    names = timeliness_metric_names()
    monitoring = BACKEND / 'charts/monitoring'
    # Scan all split/combined alerts and recording-rule YAML, including new files.
    paths = [*sorted((monitoring / 'alerts').glob('*.json')), monitoring / 'alert-rules.json']
    paths += sorted(monitoring.rglob('*.yaml'))
    for path in paths:
        if path.suffix == '.json':
            rules = json.loads(path.read_text())
            entries = [
                (rule['uid'], query['refId'], query['model'].get('expr', ''))
                for rule in rules
                for query in rule['data']
            ]
        else:
            # Monitoring values may contain Helm strings; only load recording rules.
            if 'record:' not in path.read_text():
                continue
            data = yaml.safe_load(path.read_text())
            entries = [
                (rule.get('record', rule.get('alert')), '', rule['expr'])
                for group in data.get('spec', data).get('groups', [])
                for rule in group['rules']
            ]
        for uid, ref, expression in entries:
            used = [name for name in names if re.search(rf'\b{re.escape(name)}\b', expression)]
            if used:
                yield path, uid, ref, expression, used


def assert_newest_source_join(expression, names, context):
    assert NEWEST in expression, context
    for name in names:
        for selector in re.findall(rf'{name}(?:\{{[^}}]*\}})?', expression):
            assert not re.search(r'\b(namespace|job|cluster)\s*[!=~]', selector), context
        if name == 'omi_batch_timeliness_observed_at_seconds':
            continue
        # Every value occurrence must join before aggregation. Ignoring only
        # leg preserves all labels identifying its OWN observation source.
        occurrences = list(re.finditer(rf'\b{name}(?:\{{[^}}]*\}})?', expression))
        joined = re.findall(
            rf'\b{name}(?:\{{[^}}]*\}})?(?: >= 0\))? and ignoring\(leg\) {re.escape(FRESH_NEWEST)}',
            expression,
        )
        assert len(joined) == len(occurrences), context


def test_every_timeliness_consumer_joins_its_own_newest_source():
    # Always runs in CI: this structural guard has no promtool dependency.
    expressions = list(consuming_expressions())
    assert expressions
    for path, uid, ref, expression, names in expressions:
        assert_newest_source_join(expression, names, f'{path.name}:{uid}:{ref}')


def corrupted_consuming_expressions():
    cases = []
    for path, uid, ref, expression, names in consuming_expressions():
        context = f'{path.stem}:{uid}:{ref}'
        cases.append(
            pytest.param(
                expression.replace(NEWEST, f'({OBSERVED} >= 0)', 1),
                names,
                id=f'{context}:missing-newest-selector',
            )
        )
        values = [name for name in names if name != 'omi_batch_timeliness_observed_at_seconds']
        if values:
            cases.append(
                pytest.param(
                    expression.replace('and ignoring(leg)', 'and ignoring(leg, namespace)', 1),
                    names,
                    id=f'{context}:wrong-source-identity',
                )
            )
            cases.append(
                pytest.param(
                    expression + f' or {values[0]}',
                    names,
                    id=f'{context}:unpaired-value',
                )
            )
    return cases


@pytest.mark.parametrize('expression,names', corrupted_consuming_expressions())
def test_ci_join_guard_rejects_broken_pairing_in_every_consumer(expression, names):
    # Mutation coverage proves the CI-only structural guard checks each value's
    # identity join and newest-source selector, including repeated backlog terms.
    with pytest.raises(AssertionError):
        assert_newest_source_join(expression, names, 'mutated consumer')


@pytest.mark.parametrize('uid', ['omi-batch-unit-unpublished-2h', 'omi-batch-timeliness-sample-stale'])
def test_freshness_annotations_match_executable_conditions(uid):
    monitoring = BACKEND / 'charts/monitoring'
    split = {rule['uid']: rule for rule in json.loads((monitoring / 'alerts/batch-timeliness.json').read_text())}
    combined = {rule['uid']: rule for rule in json.loads((monitoring / 'alert-rules.json').read_text())}
    rule = split[uid]
    condition = next(query['model']['expression'] for query in rule['data'] if query['refId'] == 'D')
    assert '1200' in condition
    assert rule['annotations']['threshold'] == f"{condition} for {rule['for']}"
    assert combined[uid] == rule


@pytest.mark.parametrize(
    'source',
    [
        'backend/utils/batch_pipeline/metrics.py',
        'backend/database/batch_pipeline_store.py',
        'backend/deploy/cloud_run_gmp_sync.yaml',
        'backend/charts/monitoring/prometheus-stackdriver-exporter/prod_sync_omi_cloud_run_metrics_exporter.yaml',
        'backend/charts/monitoring/alerts/pipeline-drain.json',
        'backend/charts/monitoring/core-features/recording-rules.yaml',
    ],
)
def test_regression_surfaces_select_this_guard(tmp_path, source):
    changed = tmp_path / 'changed.txt'
    changed.write_text(source + '\n')
    result = subprocess.run(
        [sys.executable, str(BACKEND / 'scripts/select_backend_unit_tests.py'), '--changed-files', str(changed)],
        cwd=BACKEND,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert 'tests/unit/test_timeliness_metrics_are_scraped.py' in result.stdout.splitlines()
    if source == 'backend/deploy/cloud_run_gmp_sync.yaml':
        # This unmapped deploy path retains its existing full-suite fallback.
        assert 'tests/unit/test_attach_cloud_run_gmp_sidecar.py' in result.stdout.splitlines()
    if source.startswith('backend/utils/batch_pipeline/'):
        assert 'tests/unit/test_lifecycle_invariants.py' in result.stdout.splitlines()


def test_prometheus_replayed_handoffs_and_sustained_leadership(tmp_path):
    executable = os.environ.get('PROMTOOL_BIN')
    if not executable:
        pytest.skip('Local promtool check; CI does not run it. Set PROMTOOL_BIN to run Prometheus semantics locally.')
    monitoring = BACKEND / 'charts/monitoring'
    rules = {
        rule['uid']: rule for path in (monitoring / 'alerts').glob('*.json') for rule in json.loads(path.read_text())
    }
    # Exercise every consuming split expression, including all three occurrences
    # of the backlog stock inside its growth/saturation branches.
    expressions = {
        (uid, ref): expression
        for path, uid, ref, expression, _ in consuming_expressions()
        if path.parent.name == 'alerts'
    }
    stale_uid = 'omi-batch-timeliness-sample-stale'
    stale_expr = expressions[stale_uid, 'A']
    stale_rule = rules[stale_uid]
    assert any(q['model'].get('expression') == '$A >= 1200' for q in stale_rule['data'])
    (tmp_path / 'rules.yaml').write_text(
        yaml.safe_dump(
            {
                'groups': [
                    {
                        'name': 'timeliness',
                        'rules': [
                            {
                                'alert': 'SamplerStale',
                                'expr': f'({stale_expr}) >= 1200',
                                'for': stale_rule['for'],
                            }
                        ],
                    }
                ]
            }
        )
    )

    def series(name, values, source, leg=None):
        labels = {
            'job': 'cloud-run-application-metrics' if source == 'run' else 'worker',
            'namespace': 'backend-integration' if source == 'run' else 'prod-omi-backend',
            'instance': source,
            'exported_instance': f'{source}-process',
            'cluster': source,
        }
        if leg is not None:
            labels['leg'] = leg
        selector = ','.join(f'{k}={json.dumps(v)}' for k, v in sorted(labels.items()))
        return {'series': f'{name}{{{selector}}}', 'values': values}

    tests = []
    for old, new in [('run', 'gke'), ('gke', 'run')]:
        inputs = []
        for source, outdated in [(old, True), (new, False)]:
            observations = (
                '0x30' if outdated else '_ ' + ' '.join(str(max(60, minute // 10 * 600)) for minute in range(1, 31))
            )
            inputs.append(series('omi_batch_timeliness_observed_at_seconds', observations, source))
            for metric, leg, breach in [
                ('omi_batch_timeliness_new_oldest_age_seconds', 'quarantined', 9000),
                ('omi_batch_timeliness_scan_truncated', 'uncommitted', 1),
                ('omi_batch_timeliness_backlog_units', 'assignment_held', 10000),
                ('omi_batch_held_oldest_age_seconds', 'quarantine_held', 90000),
                ('omi_batch_held_oldest_age_seconds', 'staged_input', 900000),
                ('omi_batch_projection_drain_oldest_age_seconds', None, 90000),
            ]:
                inputs.append(series(metric, f'{breach}x30' if outdated else '_ 0x29', source, leg))
        checks = []
        for (uid, ref), expression in expressions.items():
            for minute in (1, 5, 10, 15, 19):
                value = (
                    max(0, minute * 60 - max(60, minute // 10 * 600))
                    if (uid == stale_uid or (uid == 'omi-batch-unit-unpublished-2h' and ref == 'B'))
                    else 0
                )
                labels = '{leg="quarantine_held"}' if uid == 'omi-pipeline-held-row-age' else '{}'
                checks.append(
                    {'expr': expression, 'eval_time': f'{minute}m', 'exp_samples': [{'labels': labels, 'value': value}]}
                )
        tests.append(
            {
                'name': f'{old} replay cannot outlive healthy {new} handoff',
                'interval': '1m',
                'input_series': inputs,
                'promql_expr_test': checks,
            }
        )

    for source, lag_minutes in [('gke', 0), ('run', 3)]:
        # Sparse points model preserved timestamps/instant-lookback gaps as well
        # as the bridge's usual repeated points. No fresh-scrape timestamp can
        # replace the numeric observed_at value. Ten-minute sampling + 3m lag
        # must stay quiet throughout an hour; stopping samples must still page.
        observed = [
            (
                str((minute - lag_minutes) * 60)
                if minute >= lag_minutes and (minute - lag_minutes) % 10 == 0 and minute <= 63
                else '_'
            )
            for minute in range(91)
        ]
        checks = []
        for minute in range(max(3, lag_minutes), 64):
            observed_at = (minute - lag_minutes) // 10 * 600
            checks.append(
                {
                    'expr': stale_expr,
                    'eval_time': f'{minute}m',
                    'exp_samples': [{'labels': '{}', 'value': minute * 60 - observed_at}],
                }
            )
        tests.append(
            {
                'name': f'sustained {source} leader then stopped sampler',
                'interval': '1m',
                'input_series': [series('omi_batch_timeliness_observed_at_seconds', ' '.join(observed), source)],
                'promql_expr_test': checks,
                'alert_rule_test': [
                    {
                        'eval_time': f'{minute}m',
                        'alertname': 'SamplerStale',
                        'exp_alerts': [{'exp_labels': {}, 'exp_annotations': {}}] if minute == 86 else [],
                    }
                    for minute in (5, 15, 30, 60, 63, 86)
                ],
            }
        )
    (tmp_path / 'test.yaml').write_text(
        yaml.safe_dump(
            {
                'rule_files': ['rules.yaml'],
                'evaluation_interval': '1m',
                'tests': tests,
            }
        )
    )
    result = subprocess.run(
        [executable, 'test', 'rules', 'test.yaml'], cwd=tmp_path, capture_output=True, text=True, timeout=45
    )
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.rstrip())
