"""Critical failure conditions must reach the existing import and paging path."""

import importlib.util
import json
import logging
from pathlib import Path
import runpy

import pytest

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
        ('omi-finalization-dead-letter-stock', 49812, 38288),
        ('omi-stt-vendor-benched-page', 25, 100),
        ('omi-stt-vendor-credit-page', 1, 0),
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
        return evaluate(alarm, {'A': {(): [age]}, 'B': {(): [sample_age]}})[()]

    assert hit(7201, 30) == 1
    assert hit(7200, 30) == 0
    assert hit(7201, 900) == 0


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
