"""Repo-enforceable production telemetry contract (#9587).

Encodes expected scrape targets, routing labels, and coverage-alert linkage
without requiring live Grafana credentials. Complements #9138 exclusions;
does not duplicate managed-GKE control-plane disables (#11093).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
MONITORING = REPO / 'backend/charts/monitoring'
INVENTORY_PATH = MONITORING / 'expected-targets.prod.yaml'
PROD_VALUES = MONITORING / 'kube-prometheus-stack' / 'prod_omi_monitoring_values.yaml'
ALERT_RULES = MONITORING / 'alert-rules.json'
PARAKEET_SERVICEMONITOR = REPO / 'backend/charts/parakeet' / 'templates' / 'servicemonitor.yaml'
STACKDRIVER_EXPORTER = MONITORING / 'prometheus-stackdriver-exporter' / 'prod_omi_stackdriver_exporter.yaml'


def _load_inventory() -> dict[str, Any]:
    loaded = yaml.safe_load(INVENTORY_PATH.read_text(encoding='utf-8'))
    assert isinstance(loaded, dict)
    return loaded


def _load_prod_values() -> dict[str, Any]:
    loaded = yaml.safe_load(PROD_VALUES.read_text(encoding='utf-8'))
    assert isinstance(loaded, dict)
    return loaded


def _additional_scrape_job_names(values: dict[str, Any]) -> set[str]:
    scrape_configs = values['prometheus']['prometheusSpec']['additionalScrapeConfigs']
    return {entry['job_name'] for entry in scrape_configs}


def _scrape_jobs_by_name(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scrape_configs = values['prometheus']['prometheusSpec']['additionalScrapeConfigs']
    return {entry['job_name']: entry for entry in scrape_configs}


def _alert_rules() -> list[dict[str, Any]]:
    loaded = json.loads(ALERT_RULES.read_text(encoding='utf-8'))
    assert isinstance(loaded, list)
    return loaded


def test_inventory_file_exists_and_versioned():
    inventory = _load_inventory()
    assert inventory['version'] == 1
    assert inventory['environment'] == 'prod'
    assert inventory['scrape_jobs'], 'inventory must declare at least one scrape job'


def test_additional_scrape_jobs_exist_in_prod_values():
    inventory = _load_inventory()
    values = _load_prod_values()
    configured = _additional_scrape_job_names(values)

    declared = {job['name'] for job in inventory['scrape_jobs'] if job['mechanism'] == 'additionalScrapeConfigs'}
    for name in declared:
        assert name in configured, f"inventory job {name!r} missing from prod additionalScrapeConfigs"

    # Reverse direction: a job added straight to prod values without a matching
    # inventory entry is undeclared monitoring drift and must fail fast, not
    # silently scrape in production with nothing tracking it (cubic review on #9587).
    for name in configured:
        assert name in declared, f"prod additionalScrapeConfigs job {name!r} is not declared in the inventory"


def test_token_scraped_jobs_use_metrics_scrape_token():
    inventory = _load_inventory()
    jobs = _scrape_jobs_by_name(_load_prod_values())

    for job in inventory['scrape_jobs']:
        if job.get('auth') != 'metrics-scrape-token':
            continue
        configured = jobs[job['name']]
        auth = configured.get('authorization') or {}
        credentials = str(auth.get('credentials_file', ''))
        assert (
            'metrics-scrape-token' in credentials
        ), f"{job['name']} must scrape with metrics-scrape-token bearer credentials"


def test_kube_state_metrics_enabled_in_prod():
    inventory = _load_inventory()
    assert any(job['name'] == 'kube-state-metrics' for job in inventory['scrape_jobs'])
    values = _load_prod_values()
    assert values['kube-state-metrics']['enabled'] is True


def test_parakeet_servicemonitor_template_exists():
    inventory = _load_inventory()
    assert any(job['name'] == 'parakeet' and job['mechanism'] == 'serviceMonitor' for job in inventory['scrape_jobs'])
    text = PARAKEET_SERVICEMONITOR.read_text(encoding='utf-8')
    assert 'kind: ServiceMonitor' in text
    assert 'path: /metrics' in text


def test_stackdriver_exporter_values_present():
    assert STACKDRIVER_EXPORTER.is_file()
    inventory = _load_inventory()
    assert any(job['name'] == 'prometheus-stackdriver-metrics' for job in inventory['scrape_jobs'])


def test_enforced_coverage_alert_includes_declared_jobs():
    inventory = _load_inventory()
    rules = _alert_rules()
    scrape_rule = next(rule for rule in rules if rule['uid'] == 'omi-journey-scrape-missing')
    # Grafana alert expressions live in data[].model.expr. Require it directly —
    # a JSON-dump-the-whole-rule fallback would let the job name match an
    # unrelated field (uid, title, a label) and pass even when the actual
    # alerting expression is wrong or missing (cubic review on #9587).
    expr = scrape_rule['data'][0]['model']['expr'] if scrape_rule.get('data') else ''
    assert expr, f"omi-journey-scrape-missing has no data[].model.expr to enforce coverage against: {scrape_rule!r}"

    for job in inventory['scrape_jobs']:
        if job.get('coverage_status') != 'enforced':
            continue
        assert job.get('coverage_alert') == 'omi-journey-scrape-missing'
        assert job['name'] in expr, f"enforced job {job['name']!r} must appear in omi-journey-scrape-missing expr"


def test_declared_gaps_are_explicit_not_silently_enforced():
    inventory = _load_inventory()
    for job in inventory['scrape_jobs']:
        if job.get('coverage_status') == 'declared':
            assert (
                job.get('coverage_alert') is None
            ), f"{job['name']} is declared-only; do not claim a coverage_alert until one exists"


def test_alert_rules_use_declared_receiver_and_instatus_components():
    inventory = _load_inventory()
    routing = inventory['routing']
    allowed = set(routing['allowed_instatus_components'])
    default_receiver = routing['default_receiver']
    label_key = routing['instatus_label']

    for rule in _alert_rules():
        receiver = (rule.get('notification_settings') or {}).get('receiver')
        assert receiver == default_receiver, f"{rule.get('uid')}: unexpected receiver {receiver!r}"
        component = (rule.get('labels') or {}).get(label_key)
        assert component in allowed, f"{rule.get('uid')}: unexpected {label_key}={component!r}"


def test_scrape_health_no_data_semantics_match_inventory():
    inventory = _load_inventory()
    expected = inventory['no_data_semantics']['scrape_health']
    scrape_rule = next(rule for rule in _alert_rules() if rule['uid'] == 'omi-journey-scrape-missing')
    assert scrape_rule['noDataState'] == expected


def test_managed_gke_exclusions_are_documented():
    inventory = _load_inventory()
    exclusions = set(inventory['managed_gke_exclusions'])
    assert exclusions == {'kubeProxy', 'kubeScheduler', 'kubeControllerManager'}
