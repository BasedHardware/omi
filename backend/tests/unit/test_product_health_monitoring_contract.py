"""Static safety contract for the real-traffic product-health monitoring artifacts."""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MONITORING = REPO / 'backend/charts/monitoring'
METRIC = 'omi_product_journey_terminal_total'
DASHBOARD = MONITORING / 'dashboards/omi-services/product-health-real-traffic.json'
ALERTS = MONITORING / 'alerts/product-health.json'


def _rules(path: Path) -> dict[str, dict]:
    return {rule['uid']: rule for rule in json.loads(path.read_text(encoding='utf-8'))}


def _promql(rule: dict) -> str:
    return rule['data'][0]['model']['expr']


def test_dashboard_declares_real_traffic_only_scope_and_self_baseline():
    dashboard = json.loads(DASHBOARD.read_text(encoding='utf-8'))
    assert dashboard['uid'] == 'omi-product-health-real-traffic'

    text_panels = [panel['options']['content'] for panel in dashboard['panels'] if panel['type'] == 'text']
    assert any('No synthetic canaries' in content for content in text_panels)
    assert any('same environment' in content for content in text_panels)
    assert any('Cloud Run scrape gap' in content for content in text_panels)

    expressions = [
        target.get('expr', '')
        for panel in dashboard['panels']
        for target in panel.get('targets', [])
        if isinstance(target, dict)
    ]
    assert any(METRIC in expression for expression in expressions)
    assert all('environment=' not in expression and 'env=' not in expression for expression in expressions)


def test_alerts_are_traffic_gated_and_compare_only_to_their_own_baseline():
    combined = _rules(MONITORING / 'alert-rules.json')
    split = _rules(ALERTS)
    required = {'product_health_capture_finalization_outage', 'product_health_pusher_regression'}

    assert required <= combined.keys()
    assert required <= split.keys()
    for uid in required:
        assert combined[uid]['noDataState'] == split[uid]['noDataState'] == 'OK'
        assert combined[uid]['for'] == split[uid]['for'] == '15m'
        expression = _promql(combined[uid])
        assert METRIC in expression
        assert 'increase(omi_product_journey_accepted_total' in expression
        assert 'offset 24h' in expression
        assert 'environment=' not in expression and 'env=' not in expression
        assert combined[uid]['labels']['severity'] == 'critical'


def test_dev_and_prod_scrape_the_same_real_traffic_targets():
    for environment in ('dev', 'prod'):
        values = (MONITORING / 'kube-prometheus-stack' / f'{environment}_omi_monitoring_values.yaml').read_text(
            encoding='utf-8'
        )
        assert 'job_name: backend-listen-metrics' in values
        assert 'job_name: pusher-metrics' in values
        assert 'scrape_interval: 15s' in values
