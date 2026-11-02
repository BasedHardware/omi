"""Datasource outages have dedicated pages without changing business no-data policy."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MONITORING = ROOT / 'backend/charts/monitoring'
spec = importlib.util.spec_from_file_location('health_backtest', ROOT / 'backend/scripts/alert_backtest.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def test_canaries_execute_active_numeric_datasources_and_route_to_telegram():
    canaries = json.loads((MONITORING / 'alerts/datasource-health.json').read_text())
    assert {r['data'][0]['datasourceUid'] for r in canaries} == {'prometheus', 'beuxmaq8oxhq8e', 'gmp-cloud-run'}
    for rule in canaries:
        assert rule['noDataState'] == rule['execErrState'] == 'Alerting'
        assert rule['for'] == '2m' and not rule['isPaused']
        assert rule['labels']['impact'] == 'infrastructure'
        assert rule['notification_settings']['receiver'] == 'Omi - Services Alerting (Telegram)'
        assert rule['notification_settings']['group_by'] == ['alertname']
        # Healthy samples, including zero instances, resolve; no samples page after pending.
        healthy = 0 if rule['data'][0]['datasourceUid'] == 'beuxmaq8oxhq8e' else 1
        assert b.evaluate(rule, {'A': {(): [healthy]}}) == {(): 0}
        assert b.episodes(rule, [(t, {}) for t in range(0, 240, 60)], 0, 180, 60)['episodes'] == 1
    by_source = {rule['data'][0]['datasourceUid']: rule for rule in canaries}
    prometheus, cloud = by_source['prometheus'], by_source['beuxmaq8oxhq8e']
    assert 'cluster="__run__"' in by_source['gmp-cloud-run']['data'][0]['model']['expr']
    assert prometheus['data'][0]['model']['expr'] == 'max(up)'
    query = cloud['data'][0]['model']
    assert query['queryType'] == 'timeSeriesList'
    assert query['timeSeriesList']['projectName'] == 'based-hardware'
    assert query['timeSeriesList']['filters'] == [
        'metric.type',
        '=',
        'run.googleapis.com/container/instance_count',
        'AND',
        'resource.type',
        '=',
        'cloud_run_revision',
        'AND',
        'resource.label.service_name',
        '=',
        'backend',
    ]
    assert query['timeSeriesList']['crossSeriesReducer'] == 'REDUCE_SUM'
    assert query['timeSeriesList']['groupBys'] == []
    assert cloud['data'][0]['relativeTimeRange'] == {'from': 600, 'to': 0}


def test_business_error_policy_preserves_firing_state_and_admission_debt():
    rules = b.rules()
    inventory = json.loads(b.INVENTORY.read_text())
    for uid, rule in rules.items():
        if rule.get('isPaused') or uid.startswith('omi-datasource-'):
            continue
        if uid == 'omi-cr-start-fail':
            # Existing unsupported Logging-plugin rule is migrated separately.
            assert rule['execErrState'] == 'OK'
        elif uid in inventory['legacy_debt']:
            assert b.fingerprint(rule) == inventory['legacy_debt'][uid]['sha256']
        else:
            assert rule['execErrState'] == 'KeepLast', uid
    assert not b.lint(rules, inventory)['failures']
    assert all(rules[uid]['isPaused'] for uid in inventory['admission_holds'])


def test_deadman_shorter_window_keeps_external_channels_and_resource_identity():
    config = json.loads((ROOT / 'backend/deploy/monitoring/grafana-deadman.json').read_text())
    policy = config['alertPolicy']
    # ensure_grafana_deadman selects existing resources by stable displayName.
    assert policy['displayName'] == 'Prod Grafana dead-man: health failing for 5 minutes'
    assert policy['conditions'][0]['conditionThreshold']['duration'] == '120s'
    assert policy['notificationChannels'] == []  # approved channels supplied by existing workflow
    assert config['uptimeCheck']['period'] == '60s'
    assert set(config['uptimeCheck']['selectedRegions']) == {'USA', 'EUROPE', 'ASIA_PACIFIC'}
