"""Critical failure conditions must reach the existing import and paging path."""

import importlib.util
import json
import logging
import os
from pathlib import Path
import runpy
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
MON = ROOT / 'backend/charts/monitoring'
RULES = {r['uid']: r for r in json.loads((MON / 'alerts/critical-failures.json').read_text())}
BATCH = {r['uid']: r for r in json.loads((MON / 'alerts/batch-timeliness.json').read_text())}
BACKTEST = runpy.run_path(str(ROOT / 'backend/scripts/alert_backtest.py'))


def test_all_critical_rules_are_imported_gated_and_deliver_to_humans():
    verifier = runpy.run_path(str(ROOT / 'backend/scripts/verify_pusher_live_alert_route.py'))
    imported = verifier['load_live_stt_import_rules']()
    gated = set(verifier['load_gated_uids'](verifier['load_all_committed_rules']()))
    workflow = (ROOT / '.github/workflows/gcp_cloud_run_metrics_egress.yml').read_text()
    assert "'backend/charts/monitoring/live-alert-gate.json'" in workflow
    assert '--mode import' in workflow and '--alert-set live-stt' in workflow and '--fail-on gated' in workflow
    for uid, rule in (RULES | {'omi-batch-unit-unpublished-2h': BATCH['omi-batch-unit-unpublished-2h']}).items():
        assert uid in gated and imported[uid] == rule
        assert rule['labels']['tier'] == 'page' and rule['labels']['audience'] == 'human'
        assert not rule['notification_settings'].get('mute_time_intervals')
        assert rule['notification_settings']['receiver'] == verifier['TELEGRAM_RECEIVER']
        assert (ROOT / rule['annotations']['runbook']).is_file()


@pytest.mark.parametrize(
    'uid,bad,good',
    [
        ('omi-batch-held-backlog-growing', 1, 0),
        ('omi-enrichment-queue-depth-page', 21563, 5261),
        ('omi-stt-vendor-benched-page', 25, 100),
        ('omi-modulate-credit-page', 1, 0),
        ('omi-incluster-guard-unsafe-page', 1, 0),
    ],
)
def test_real_grafana_nodes_page_on_incident_and_resolve_on_control(uid, bad, good):
    rule = RULES[uid]
    evaluate, episodes = BACKTEST['evaluate'], BACKTEST['episodes']
    pending = int(BACKTEST['seconds'](rule['for']))

    # Run the real reduce/threshold graph through a full pending window. The
    # exact PromQL is separately replayed on retained aggregate query results.
    def frame(value):
        return evaluate(rule, {'A': {(): [float(value)]}})

    result = episodes(rule, [(t, frame(bad)) for t in range(0, pending + 61, 60)], 0, pending + 60, 60)
    assert result['episodes'] == 1
    result = episodes(rule, [(t, frame(good)) for t in range(0, pending + 61, 60)], 0, pending + 60, 60)
    assert result['episodes'] == 0


def test_batch_alarm_requires_freshness_and_keeps_the_two_hour_contract():
    alarm = BATCH['omi-batch-unit-unpublished-2h']
    evaluate = BACKTEST['evaluate']

    def hit(age, sample_age):
        # The merged rule also pages on the all-epoch compute commitment (C/F
        # disjunct, owned by the backtest matrix); hold it quiet here so these
        # assertions keep testing the new-cohort delivery legs.
        return evaluate(alarm, {'A': {(): [age]}, 'B': {(): [sample_age]}, 'C': {(): [0]}, 'F': {(): [0]}})[()]

    assert hit(7201, 30) == 1
    assert hit(7200, 30) == 0
    assert hit(7201, 900) == 0


def test_held_backlog_growth_or_saturation_contract_and_mirrors():
    rule = RULES['omi-batch-held-backlog-growing']
    stock = 'max(omi_batch_timeliness_backlog_units{leg="assignment_held"})'
    assert rule['data'][0]['model']['expr'] == (
        f'((({stock} > 1000) and on() (delta(({stock})[1h:5m]) > 50)) '
        f'or ({stock} >= 10000) or on() vector(0)) '
        '* on() ((time() - max(omi_batch_timeliness_observed_at_seconds)) < bool 900)'
    )
    assert rule['for'] == '15m'
    assert rule['data'][2]['model']['conditions'][0]['evaluator'] == {'params': [0.5], 'type': 'gt'}
    combined = {r['uid']: r for r in json.loads((MON / 'alert-rules.json').read_text())}
    assert combined[rule['uid']] == rule
    inventory = json.loads((MON / 'gmp-query-migration-inventory.json').read_text())
    # The migration inventory must describe the same executable query.
    entry = next(row for row in inventory['consumers'] if row['owner_uid'] == rule['uid'])
    assert entry['expression'] == rule['data'][0]['model']['expr']
    assert entry['owner_title'] == rule['title']


def test_held_backlog_saturation_promql_and_pending_window(tmp_path):
    executable = os.environ.get('PROMTOOL_BIN') or shutil.which('promtool')
    if not executable:
        pytest.skip('set PROMTOOL_BIN to run the offline Prometheus semantic regression')
    rule = RULES['omi-batch-held-backlog-growing']
    expr = rule['data'][0]['model']['expr']
    threshold = rule['data'][2]['model']['conditions'][0]['evaluator']['params'][0]
    alert = {'alert': 'HeldBacklog', 'expr': f'({expr}) > {threshold}', 'for': rule['for']}
    (tmp_path / 'rules.yaml').write_text(yaml.safe_dump({'groups': [{'name': 'held', 'rules': [alert]}]}))

    def case(name, stock, expected, *, observed='0+60x90', when='90m', firing=False):
        series = [
            {'series': 'omi_batch_timeliness_backlog_units{leg="assignment_held"}', 'values': stock},
            {'series': 'omi_batch_timeliness_observed_at_seconds', 'values': observed},
        ]
        return {
            'name': name,
            'interval': '1m',
            'input_series': series,
            'promql_expr_test': [
                {'expr': expr, 'eval_time': when, 'exp_samples': [{'labels': '{}', 'value': expected}]}
            ],
            'alert_rule_test': [
                {
                    'eval_time': when,
                    'alertname': 'HeldBacklog',
                    'exp_alerts': [{'exp_labels': {}, 'exp_annotations': {}}] if firing else [],
                }
            ],
        }

    tests = [
        case('flat capped stock still pages after 1h delta reaches zero', '10000x90', 10000, firing=True),
        case('saturation needs no growth history', '_ _ 10000x88', 10000, when='2m'),
        case('saturation respects pending duration', '10000x90', 10000, when='14m'),
        case('saturation fires after pending duration', '10000x90', 10000, when='15m', firing=True),
        case('below cap flat stock is quiet', '9999x90', 0),
        case('small growing stock stays quiet', '0+1x90', 0),
        case('below cap growing stock still pages', '2000+2x90', 2180, firing=True),
        case('lever zero exact stock above cap pages', '10123x90', 10123, firing=True),
        case('saturated but stale sample is quiet', '10000x90', 0, observed='0x90'),
        case('freshness boundary excludes saturation', '10000x90', 0, observed='0+60x75 4500x14'),
        case('draining below cap resolves without requiring measured growth', '10000x70 9999x19', 0),
    ]
    (tmp_path / 'test.yaml').write_text(
        yaml.safe_dump({'rule_files': ['rules.yaml'], 'evaluation_interval': '1m', 'tests': tests})
    )
    result = subprocess.run(
        [executable, 'test', 'rules', 'test.yaml'], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    'event,verdict',
    [('batch_safety', 'TRIP'), ('parakeet_guard', 'BLIND'), ('batch_rollback', 'TRIP'), ('guard_error', None)],
)
def test_guard_logs_signal_unsafe_verdicts_and_suppress_dry_runs(event, verdict, caplog, monkeypatch):
    script = ROOT / 'backend/charts/incluster-guards/files/guard.py'
    spec = importlib.util.spec_from_file_location('critical_guard_signal', script)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    monkeypatch.delenv('DRY_RUN', raising=False)
    caplog.set_level(logging.INFO, logger='incluster-guards')
    # The isolated process entrypoint configures logging when loaded; attach
    # this test's capture handler after that configuration, without changing
    # production logging or depending on root-handler propagation.
    monkeypatch.setattr(logging.getLogger('incluster-guards'), 'handlers', [caplog.handler])
    guard.log(event, verdict=verdict)
    assert json.loads(caplog.records[-1].message)['page_signal'] is True
    guard.log(event, verdict=verdict, dry_run=True)
    assert json.loads(caplog.records[-1].message)['page_signal'] is False
    monkeypatch.setenv('DRY_RUN', 'true')
    guard.log(event, verdict=verdict)
    assert json.loads(caplog.records[-1].message)['page_signal'] is False


def test_guard_log_metric_is_bounded_to_production_and_the_emitted_signal():
    metric = json.loads((MON / 'guard-unsafe.log-metric.json').read_text())
    assert metric['metricDescriptor']['metricKind'] == 'DELTA'
    assert metric['metricDescriptor']['valueType'] == 'INT64'
    assert metric['name'] == 'omi_incluster_guard_unsafe'
    assert 'prod-omi-backend' in metric['filter']
    assert 'page_signal' in metric['filter']
    assert not metric.get('labelExtractors')  # No unbounded log labels.
