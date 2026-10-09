"""Recap provisioning and dashboard contracts; execute embedded policy builders."""

import json
import os
from pathlib import Path
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


def test_recap_dashboard_four_panels_and_no_grid_overlap():
    doc = json.loads((ROOT / 'backend/charts/monitoring/dashboards/general/omi-core-features.json').read_text())
    row = next(p for p in doc['panels'] if p['title'] == 'Daily recaps — delivery job health')
    assert row['collapsed'] is True
    panels = row['panels']
    assert [p['title'] for p in panels] == [
        'Recap recipients by outcome',
        'Cohort completion',
        'Resumed cohort age',
        'Cohort age now',
    ]
    assert panels[-1]['targets'][0]['instant'] is True
    for panel in panels[2:]:
        assert panel['fieldConfig']['defaults']['unit'] == 's'
        assert panel['fieldConfig']['defaults']['thresholds']['steps'][-1] == {'color': 'red', 'value': 7200}
    occupied = set()
    for panel in panels:
        g = panel['gridPos']
        cells = {(x, y) for x in range(g['x'], g['x'] + g['w']) for y in range(g['y'], g['y'] + g['h'])}
        assert not cells & occupied
        assert g['y'] > row['gridPos']['y']
        occupied |= cells


def test_notifications_namespace_in_both_exporter_filters():
    for env in ('dev', 'prod'):
        text = (
            ROOT
            / f'backend/charts/monitoring/prometheus-stackdriver-exporter/{env}_omi_cloud_run_metrics_exporter.yaml'
        ).read_text()
        assert 'resource.labels.cluster="__run__" AND resource.labels.namespace=one_of(' in text
        assert '"notifications-job"' in text
