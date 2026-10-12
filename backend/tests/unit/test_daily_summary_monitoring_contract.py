"""Recap provisioning and dashboard contracts; execute embedded policy builders."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_recap_alerts_are_idempotent_and_have_correct_conditions(tmp_path):
    workflow = yaml.load((ROOT / '.github/workflows/gcp_notifications_job.yml').read_text(), Loader=yaml.BaseLoader)
    steps = workflow['jobs']['deploy']['steps']
    for metric, kind, duration in (
        ('daily_summary_cohort_incomplete', 'conditionThreshold', '10800s'),
        ('daily_summary_job_heartbeat_missing', 'conditionAbsent', '3600s'),
    ):
        step = next(step for step in steps if step['name'] == 'Provision ' + metric)
        assert step['if'] == "github.event.inputs.environment == 'prod'"
        script = step['run']
        assert 'test -n "$ALERT_CHANNELS"' in script
        for operation in ('describe', 'update', 'create'):
            assert 'gcloud logging metrics ' + operation in script
        for operation in ('list', 'create', 'update', 'describe'):
            assert 'gcloud monitoring policies ' + operation in script
        assert script.count('--policy-from-file="$policy_file"') == 2
        assert 'backend/docs/runbooks/daily-summary-cutover.md' in script
        assert '071ff86cdc' in script
        builder = script.split("<<'PY_POLICY'\n", 1)[1].split('\nPY_POLICY', 1)[0]
        target = tmp_path / (metric + '.json')
        for policy in ('', 'projects/test/alertPolicies/123'):
            env = dict(
                os.environ,
                RECAP_METRIC=metric,
                RECAP_DISPLAY_NAME=metric,
                RECAP_DOCUMENTATION='runbook',
                RECAP_POLICY=policy,
                ALERT_CHANNELS='channel1,channel2',
            )
            subprocess.run([sys.executable, '-', str(target)], input=builder, text=True, env=env, check=True)
            body = json.loads(target.read_text())
            assert body.get('name', '') == policy
            assert body['notificationChannels'] == ['channel1', 'channel2']
            condition = body['conditions'][0][kind]
            assert condition['duration'] == duration
            assert condition['aggregations'][0]['alignmentPeriod'] == '900s'
            if kind == 'conditionThreshold':
                assert condition['thresholdValue'] == 0
                assert condition['aggregations'][0]['perSeriesAligner'] == 'ALIGN_RATE'
                assert '"complete=False"' in script


DASHBOARD = ROOT / 'backend/charts/monitoring/dashboards/general/omi-core-features.json'
CLOUD_MONITORING = {'type': 'stackdriver', 'uid': 'beuxmaq8oxhq8e'}
RECAP_LOG_METRICS = ('daily_summary_recap_generated', 'daily_summary_user_failed')


def _promql_name(metric):
    return 'logging_googleapis_com:user_' + metric


def _provisioned_log_metrics():
    workflow = yaml.load((ROOT / '.github/workflows/gcp_notifications_job.yml').read_text(), Loader=yaml.BaseLoader)
    names = set()
    for step in workflow['jobs']['deploy']['steps']:
        names |= set(re.findall(r"^metric='([a-z_]+)'$", step.get('run', ''), flags=re.M))
        if step['name'] == 'Provision daily recap outcome log metrics':
            assert step['if'] == "github.event.inputs.environment == 'prod'"
            assert 'for metric in ' + ' '.join(RECAP_LOG_METRICS) + '; do' in step['run']
            names |= set(RECAP_LOG_METRICS)
    return names


def _cloud_monitoring_exprs(panel_or_rule_nodes):
    return [node['promQLQuery']['expr'] for node in panel_or_rule_nodes if node.get('queryType') == 'promQL']


def _referenced_log_metrics(expr):
    return set(re.findall(r'logging_googleapis_com:user_([a-z_]+)', expr))


def test_recap_log_metrics_extract_bounded_labels(tmp_path):
    workflow = yaml.load((ROOT / '.github/workflows/gcp_notifications_job.yml').read_text(), Loader=yaml.BaseLoader)
    step = next(
        s for s in workflow['jobs']['deploy']['steps'] if s['name'] == 'Provision daily recap outcome log metrics'
    )
    script = step['run']
    for operation in ('describe', 'update', 'create'):
        assert 'gcloud logging metrics ' + operation in script
    assert script.count('--config-from-file="$config"') == 2
    builder = script.split("<<'PY_LOG_METRICS'\n", 1)[1].split('\nPY_LOG_METRICS', 1)[0]
    subprocess.run([sys.executable, '-', str(tmp_path)], input=builder, text=True, check=True)
    bodies = {path.stem: json.loads(path.read_text()) for path in tmp_path.glob('*.json')}
    assert set(bodies) == set(RECAP_LOG_METRICS)
    for name, body in bodies.items():
        assert body['name'] == name
        assert body['filter'].startswith('resource.type="cloud_run_job" resource.labels.job_name="notifications-job" ')
        assert body['metricDescriptor']['metricKind'] == 'DELTA'
        labels = {label['key'] for label in body['metricDescriptor']['labels']}
        assert labels == set(body['labelExtractors'])
        # uid is never a label: Cloud Logging metric cardinality, and recipients are not dimensions.
        assert not any('uid' in extractor for extractor in body['labelExtractors'].values())
    assert set(bodies['daily_summary_user_failed']['labelExtractors']) == {'reason', 'error_type'}


def test_feature_health_row_carries_the_daily_recap_outcome():
    doc = json.loads(DASHBOARD.read_text())
    top = doc['panels']
    feature_row = top.index(next(p for p in top if p['title'] == 'Feature health — did the user get an outcome?'))
    next_row = next(i for i, p in enumerate(top) if i > feature_row and p['type'] == 'row')
    stats = top[feature_row + 1 : next_row]
    recap = [p for p in stats if p['title'].startswith(('Daily recap', 'Recap'))]
    assert [p['title'] for p in recap] == [
        'Daily recap generation (3h)',
        'Daily recaps generated (24h)',
        'Recap generation failures (3h)',
        'Recap job passes (1h, expect 4)',
    ]
    success = recap[0]
    assert success['fieldConfig']['defaults']['unit'] == 'percent'
    assert success['fieldConfig']['defaults']['thresholds']['steps'][1] == {'color': 'orange', 'value': 90}
    assert success['fieldConfig']['defaults']['noValue'] == 'no recaps due'
    assert recap[1]['fieldConfig']['defaults']['thresholds']['steps'] == [
        {'color': 'red', 'value': None},
        {'color': 'green', 'value': 1},
    ]
    provisioned = _provisioned_log_metrics()
    for panel in recap:
        assert panel['datasource'] == CLOUD_MONITORING, 'recap stats must not read the scrape path'
        (expr,) = _cloud_monitoring_exprs(panel['targets'])
        referenced = _referenced_log_metrics(expr)
        assert referenced and referenced <= provisioned, (panel['title'], referenced - provisioned)
    assert 'DailySummaryDeliveryError' in _cloud_monitoring_exprs(success['targets'])[0]
    occupied = set()
    for panel in stats:
        g = panel['gridPos']
        cells = {(x, y) for x in range(g['x'], g['x'] + g['w']) for y in range(g['y'], g['y'] + g['h'])}
        assert not cells & occupied, panel['title']
        assert g['y'] + g['h'] <= top[next_row]['gridPos']['y'], panel['title']
        occupied |= cells


def test_recap_dashboard_row_and_no_grid_overlap():
    doc = json.loads(DASHBOARD.read_text())
    row = next(p for p in doc['panels'] if p['title'] == 'Daily recaps — generation and delivery job health')
    assert row['collapsed'] is True
    panels = row['panels']
    assert [p['title'] for p in panels] == [
        'Recap outcomes per 15 minutes',
        'Cohort passes: all vs incomplete',
        'Resumed cohort age',
        'Cohort age now',
    ]
    provisioned = _provisioned_log_metrics()
    for panel in panels[:2]:
        assert panel['datasource'] == CLOUD_MONITORING
        for expr in _cloud_monitoring_exprs(panel['targets']):
            assert _referenced_log_metrics(expr) <= provisioned
    assert panels[0]['fieldConfig']['defaults']['custom']['stacking']['mode'] == 'none'
    assert panels[-1]['targets'][0]['instant'] is True
    assert 'max' not in panels[-1]['fieldConfig']['defaults'], 'cohort age must not inherit a percent clamp'
    for panel in panels[2:]:
        assert 'roles/monitoring.metricWriter' in panel['description']
        assert panel['fieldConfig']['defaults']['unit'] == 's'
        assert panel['fieldConfig']['defaults']['thresholds']['steps'][-1] == {'color': 'red', 'value': 7200}
    occupied = set()
    for panel in panels:
        g = panel['gridPos']
        cells = {(x, y) for x in range(g['x'], g['x'] + g['w']) for y in range(g['y'], g['y'] + g['h'])}
        assert not cells & occupied
        assert g['y'] > row['gridPos']['y']
        occupied |= cells


def test_recap_alert_reads_provisioned_log_metrics_and_gates_on_volume():
    """Failure-Class: FC-alert-never-provably-fired -- every series the rule reads is provisioned."""
    provisioned = _provisioned_log_metrics()
    for export in ('alerts/daily-recap.json', 'alert-rules.json'):
        rules = json.loads((ROOT / 'backend/charts/monitoring' / export).read_text())
        rule = next(r for r in rules if r['uid'] == 'omi-daily-recap-generation-failing')
        assert rule['labels']['alert_identity'] == rule['uid']
        assert rule['notification_settings']['receiver'] == 'Omi - Services Alerting (Telegram)'
        assert rule['noDataState'] == 'OK'
        assert rule['for'] == '15m'
        models = [node['model'] for node in rule['data']]
        exprs = _cloud_monitoring_exprs(models)
        assert len(exprs) == 4
        for node in rule['data']:
            if node['model'].get('queryType') == 'promQL':
                assert node['datasourceUid'] == CLOUD_MONITORING['uid']
        for expr in exprs:
            assert _referenced_log_metrics(expr) <= provisioned
            # An absent generated series during a total outage must read 0, not No Data.
            assert expr.endswith(' or vector(0)')
        assert sum('DailySummaryDeliveryError' in expr for expr in exprs) == 2
        assert ['[1h]' in e for e in exprs] == [True, True, False, False]
        maths = [m['expression'] for m in models if m.get('type') == 'math']
        assert maths == ['($E >= 10 && $F / ($E + $F) < 0.5) || ($G >= 20 && $H == 0)']
        assert rule['annotations']['__dashboardUid__'] == 'omi-core-features'
        assert rule['annotations']['__panelId__'] == '73'


def test_notifications_namespace_in_both_exporter_filters():
    for env in ('dev', 'prod'):
        text = (
            ROOT
            / f'backend/charts/monitoring/prometheus-stackdriver-exporter/{env}_omi_cloud_run_metrics_exporter.yaml'
        ).read_text()
        assert 'resource.labels.cluster="__run__" AND resource.labels.namespace=one_of(' in text
        assert '"notifications-job"' in text
