"""Offline source/threshold/pending/recovery contracts for alert-only drain guards."""

import importlib.util
import json
from pathlib import Path
import re

import pytest

BACKEND = Path(__file__).resolve().parents[2]
MONITORING = BACKEND / 'charts/monitoring'
spec = importlib.util.spec_from_file_location('pipeline_alert_backtest', BACKEND / 'scripts/alert_backtest.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
RULES = {r['uid']: r for r in json.loads((MONITORING / 'alerts/pipeline-drain.json').read_text())}


def test_sources_match_inventory_and_are_routed_resolving_warnings():
    inventory = json.loads((MONITORING / 'metric-inventory.prod.json').read_text())
    combined = {r['uid']: r for r in json.loads((MONITORING / 'alert-rules.json').read_text())}
    gate = json.loads((MONITORING / 'live-alert-gate.json').read_text())['uids']
    reference = json.loads((MONITORING / 'alerts/batch-timeliness.json').read_text())[0]
    for uid, rule in RULES.items():
        assert combined[uid] == rule
        assert not b.lint_rule(rule, inventory)
        assert rule['labels']['severity'] == 'warning'
        assert rule['notification_settings']['receiver'] == reference['notification_settings']['receiver']
        assert rule['notification_settings']['group_wait'] == '5m'
        assert rule['notification_settings']['group_interval'] == '1h'
        assert rule['notification_settings']['repeat_interval'] == '24h'
        assert rule['keep_firing_for'] == '0s'
        assert rule['missingSeriesEvalsToResolve'] == 2
        assert rule['noDataState'] == 'OK'
        assert not rule['isPaused']
        assert uid not in gate
        assert (BACKEND.parent / rule['annotations']['runbook']).is_file()
        assert rule['annotations']['verification']
        assert rule['annotations']['review_by'] == '2026-11-07'
        for q in rule['data']:
            if q['datasourceUid'] == 'gmp-cloud-run':
                assert 'offset 10m' in q['model']['expr']


@pytest.mark.parametrize(
    'uid,frames,expected',
    [
        ('omi-pipeline-upload-503-storm', {'A': 100}, 0),
        ('omi-pipeline-upload-503-storm', {'A': 101}, 1),
        ('omi-pipeline-firestore-contention', {'A': 20}, 0),
        ('omi-pipeline-firestore-contention', {'A': 21}, 1),
        ('omi-pipeline-projection-drain-stall', {'A': 0.5, 'B': 10, 'C': 1}, 0),
        ('omi-pipeline-projection-drain-stall', {'A': 0.51, 'B': 20, 'C': 1}, 1),
        ('omi-pipeline-projection-drain-stall', {'A': 0, 'B': 9.9, 'C': 1}, 1),
        ('omi-pipeline-projection-drain-stall', {'A': 0, 'B': 0, 'C': 1}, 1),
        ('omi-pipeline-projection-drain-stall', {'A': 1, 'B': 0, 'C': 0}, 0),
        ('omi-pipeline-held-row-age', {'A': 21600}, 0),
        ('omi-pipeline-held-row-age', {'A': 21601}, 1),
        ('omi-pipeline-held-row-age', {'A': 200000}, 1),
    ],
)
def test_strict_thresholds_and_drain_or_requires_pending_debt(uid, frames, expected):
    assert b.evaluate(RULES[uid], {ref: {(): [v]} for ref, v in frames.items()}) == {(): expected}


@pytest.mark.parametrize('uid', RULES)
def test_pending_period_and_auto_resolution(uid):
    rule = RULES[uid]
    pending = 900 if 'drain-stall' in uid else 600
    assert b.seconds(rule['for']) == pending
    brief = [(t, {(): float(t < pending)}) for t in range(0, pending + 121, 60)]
    assert b.episodes(rule, brief, 0, pending + 120, 60)['episodes'] == 0
    sustained = [(t, {(): float(t <= pending)}) for t in range(0, pending + 121, 60)]
    result = b.episodes(rule, sustained, 0, pending + 120, 60)
    assert result['episodes'] == 1
    assert result['total_duration_seconds'] == 60
    missing = {q['refId']: {} for q in rule['data'] if q['datasourceUid'] != '__expr__'}
    assert b.evaluate(rule, missing) == {}


def test_held_legs_are_independent_and_use_fresh_uncapped_source():
    rule = RULES['omi-pipeline-held-row-age']
    expr = rule['data'][0]['model']['expr']
    assert 'omi_batch_held_oldest_age_seconds' in expr
    assert 'record_pending_new_oldest' not in expr
    assert 'and ignoring(leg) (time() - omi_batch_timeliness_observed_at_seconds < 900)' in expr
    values = {
        (("leg", 'quarantine_held'),): [300000],
        (("leg", 'assignment_held'),): [60],
        (("leg", 'record_pending'),): [90000],
    }
    assert b.evaluate(rule, {'A': values}) == {label: float(v[0] > 21600) for label, v in values.items()}


def test_drain_uses_sum_for_rows_and_count_for_weighted_turn_share():
    rule = RULES['omi-pipeline-projection-drain-stall']
    nodes = {q['refId']: q['model'] for q in rule['data']}
    assert 'owner_drain_claim_busy' in nodes['A']['expr']
    assert 'owner_drain_advanced_count' in nodes['A']['expr']
    assert 'owner_drain_advanced_sum' in nodes['B']['expr']
    assert 'rate(' in nodes['A']['expr'] and '[5m]' in nodes['B']['expr']
    assert 'or vector(0)' in nodes['B']['expr']
    assert 'timeliness_observed_at_seconds < 900' in nodes['C']['expr']
    assert rule['data'][0]['datasourceUid'] == 'gmp-cloud-run'
    assert rule['data'][2]['datasourceUid'] == 'prometheus'


def test_log_metric_source_scopes_and_real_turn_extraction():
    metrics = {m['name']: m for m in json.loads((MONITORING / 'batch-projection/log-metrics.json').read_text())}
    inventory = json.loads((MONITORING / 'metric-inventory.prod.json').read_text())
    declared = inventory['datasource_metrics']['gmp-cloud-run']['declared_metrics']
    expected = {
        'logging_googleapis_com:user_' + m['name'] + suffix
        for m in metrics.values()
        for suffix in (['_sum', '_count'] if m['metricDescriptor']['valueType'] == 'DISTRIBUTION' else [''])
    }
    assert set(declared) == expected
    upload = metrics['omi_pipeline_upload_admission_503']['filter']
    for token in (
        'resource.type="cloud_run_revision"',
        'resource.labels.project_id="based-hardware"',
        'resource.labels.service_name="backend-sync"',
        'httpRequest.status=503',
        'httpRequest.responseSize=266',
        'httpRequest.requestMethod="POST"',
        'run.googleapis.com%2Frequests',
    ):
        assert token in upload
    route = re.search(r'httpRequest.requestUrl=~"([^"]+)"', upload).group(1)
    for path in ('/v2/sync-local-files', '/v2/sync-local-files/', '/v2/sync-local-files?device=x'):
        assert re.search(route, 'https://example.test' + path)
    for path in ('/v2/sync-local-files/job', '/v1/sync-local-files', '/v2/sync-local-files-other'):
        assert not re.search(route, 'https://example.test' + path)
    assert (
        'jsonPayload.message:"FirestoreContentionExhausted"'
        in metrics['omi_pipeline_firestore_contention_exhausted']['filter']
    )
    for metric in metrics.values():
        assert metric['metricDescriptor']['metricKind'] == 'DELTA'
        assert not metric.get('labelExtractors')
        if metric['name'] != 'omi_pipeline_upload_admission_503':
            for service in ('backend-sync', 'backend-sync-backfill', 'backend-integration'):
                assert '"' + service + '"' in metric['filter']
    advanced = metrics['omi_pipeline_owner_drain_advanced']
    assert advanced['metricDescriptor']['valueType'] == 'DISTRIBUTION'
    pattern = re.search(r'REGEXP_EXTRACT\(textPayload, "(.*)"\)', advanced['valueExtractor']).group(1)
    for rows in (0, 1, 128, 10000):
        line = f'event=batch_projection action=owner_drain outcome=turn steps=2 advanced={rows} more=false stop=claim_busy elapsed_ms=1'
        assert int(re.search(pattern, line).group(1)) == rows
    assert 'outcome=turn ' in advanced['filter']
    assert 'stop=claim_busy([[:space:]]|$)' in metrics['omi_pipeline_owner_drain_claim_busy']['filter']
