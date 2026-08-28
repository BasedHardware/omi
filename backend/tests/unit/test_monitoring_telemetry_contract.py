"""Repo-enforceable production telemetry contract (#9587).

Encodes expected scrape targets, routing labels, and coverage-alert linkage
without requiring live Grafana credentials. Complements #9138 exclusions;
does not duplicate managed-GKE control-plane disables (#11093).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

import yaml

REPO = Path(__file__).resolve().parents[3]
MONITORING = REPO / 'backend/charts/monitoring'
INVENTORY_PATH = MONITORING / 'expected-targets.prod.yaml'
PROD_VALUES = MONITORING / 'kube-prometheus-stack' / 'prod_omi_monitoring_values.yaml'
ALERT_RULES = MONITORING / 'alert-rules.json'
PARAKEET_SERVICEMONITOR = REPO / 'backend/charts/parakeet' / 'templates' / 'servicemonitor.yaml'
STACKDRIVER_EXPORTER = MONITORING / 'prometheus-stackdriver-exporter' / 'prod_omi_stackdriver_exporter.yaml'
STACKDRIVER_EXPORTER_DEV = MONITORING / 'prometheus-stackdriver-exporter' / 'dev_omi_stackdriver_exporter.yaml'
CLOUD_RUN_EXPORTER = MONITORING / 'prometheus-stackdriver-exporter' / 'prod_omi_cloud_run_metrics_exporter.yaml'
CLOUD_RUN_EXPORTER_DEV = MONITORING / 'prometheus-stackdriver-exporter' / 'dev_omi_cloud_run_metrics_exporter.yaml'


def _cpu_millicores(value: object) -> float:
    text = str(value)
    return float(text[:-1]) if text.endswith('m') else float(text) * 1000


def _memory_mebibytes(value: object) -> float:
    text = str(value)
    for suffix, factor in (('Gi', 1024), ('Mi', 1), ('G', 953.7), ('M', 0.9537)):
        if text.endswith(suffix):
            return float(text[: -len(suffix)]) * factor
    return float(text) / (1024 * 1024)


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


@pytest.mark.parametrize(
    'path',
    (STACKDRIVER_EXPORTER, STACKDRIVER_EXPORTER_DEV),
    ids=('prod', 'dev'),
)
def test_stackdriver_exporter_ingests_firestore_read_count(path):
    """A Firestore cost runaway is invisible unless this prefix is scraped.

    document/read_count was absent from every Prometheus metric name during the
    2026-08-23 cost incident, so nothing could alert on it. Both environments
    are asserted: the dev values file is what the automatic post-merge rollout
    installs, so leaving it unpinned lets dev drift away from the contract prod
    is held to (same rationale as the Cloud Run exporter parametrization above).
    """
    values = yaml.safe_load(path.read_text(encoding='utf-8'))
    prefixes = values['stackdriver']['metrics']['prefixes']

    assert (
        'firestore.googleapis.com/document/read_count' in prefixes
    ), f'{path.name}: missing the firestore.googleapis.com/document/read_count prefix'
    # The existing loadbalancing prefixes must survive the edit untouched.
    assert 'loadbalancing.googleapis.com/https/backend_request_count' in prefixes
    assert 'loadbalancing.googleapis.com/https/internal/backend_latencies' in prefixes


# Cloud Monitoring rejects a filter that mixes AND with OR across resource.labels
# restrictions ("AND and OR cannot be mixed for 'resource.labels' restrictions",
# HTTP 400). The exporter answers that rejection per descriptor, so the pod stays
# Available and `up` stays 1 while every import fails and Grafana shows an empty
# panel that reads as no traffic. Use one_of() and pin the exact string.
CLOUD_RUN_EXPORTER_FILTER = (
    'prometheus.googleapis.com/omi_:resource.labels.cluster="__run__" AND '
    'resource.labels.namespace=one_of("backend","desktop-backend")'
)


@pytest.mark.parametrize(
    ('path', 'project_id', 'service_account'),
    (
        (CLOUD_RUN_EXPORTER, 'based-hardware', 'prod-omi-prometheus-stackdriver-exporter'),
        (CLOUD_RUN_EXPORTER_DEV, 'based-hardware-dev', 'dev-omi-prometheus-stackdriver-exporter'),
    ),
    ids=('prod', 'dev'),
)
def test_cloud_run_metrics_exporter_is_scoped_and_rate_limited(path, project_id, service_account):
    # Both environments are asserted: the dev values file is what the automatic
    # post-merge rollout installs, so leaving it unpinned lets dev drift away
    # from the contract prod is held to.
    values = yaml.safe_load(path.read_text(encoding='utf-8'))
    metrics = values['stackdriver']['metrics']
    assert values['stackdriver']['projectIds'] == [project_id]
    assert metrics['prefixes'] == ['prometheus.googleapis.com/omi_']
    assert metrics['interval'] == '2m'
    assert metrics['offset'] == '1m'
    assert metrics['filters'] == [CLOUD_RUN_EXPORTER_FILTER]
    assert values['serviceAccount'] == {
        'create': False,
        'name': service_account,
    }


@pytest.mark.parametrize('path', (CLOUD_RUN_EXPORTER, CLOUD_RUN_EXPORTER_DEV), ids=('prod', 'dev'))
def test_cloud_run_metrics_exporter_can_outlast_its_own_scrape(path):
    """The exporter collects from Cloud Monitoring inline, so it must be sized for it.

    A prod scrape is ~28MB / ~52k series and takes 6-10s. Under a 200m CPU ceiling
    and a 10s probe timeout the process was killed mid-collection 120 times, held
    up=0, and recorded scrape_samples_scraped=0 -- while reporting a Deployment
    that had simply never had anything to collect. Floors, not exact values, so
    capacity can be raised without editing this test.
    """
    values = yaml.safe_load(path.read_text(encoding='utf-8'))

    limits = values['resources']['limits']
    assert (
        _cpu_millicores(limits['cpu']) >= 1000
    ), f'{path.name}: measured steady state is ~238m and a scrape needs ~1 core'
    assert _memory_mebibytes(limits['memory']) >= 1024, f'{path.name}: measured steady state is ~331Mi'

    # The chart hardcodes both probes and reads no probe values, so a probe block
    # here would render nothing while looking like configuration. Reject it, and
    # keep capacity as the lever that actually decides whether a probe survives.
    for probe in ('livenessProbe', 'readinessProbe'):
        assert probe not in values, (
            f'{path.name}: prometheus-stackdriver-exporter templates {probe} with a fixed 10s timeout and '
            f'exposes no values key for it; this block would be inert'
        )


@pytest.mark.parametrize('path', (CLOUD_RUN_EXPORTER, CLOUD_RUN_EXPORTER_DEV), ids=('prod', 'dev'))
def test_cloud_run_metrics_exporter_filter_has_no_mixed_and_or(path):
    # A narrow static tripwire for the one shape that took the bridge down, not a
    # grammar check: it does not parse the filter language and does not call Cloud
    # Monitoring, so a malformed filter can still pass. Its only job is to make a
    # reintroduced resource.labels disjunction fail with the reason attached
    # instead of as a bare equality mismatch above. Acceptance is only ever proved
    # against the live API, post-deploy, by stackdriver_monitoring_last_scrape_error.
    values = yaml.safe_load(path.read_text(encoding='utf-8'))
    for entry in values['stackdriver']['metrics']['filters']:
        _, _, expression = entry.partition(':')
        restrictions = re.findall(r'resource\.labels\.[A-Za-z0-9_]+', expression)
        mixes_and_or = ' AND ' in expression and ' OR ' in expression
        assert not (len(restrictions) > 1 and mixes_and_or), (
            f'{path.name}: Cloud Monitoring rejects AND/OR mixed across resource.labels '
            f'restrictions with HTTP 400; express the disjunction as one_of(...): {expression}'
        )


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


CLOUD_RUN_SCRAPE_JOB = "cloud-run-application-metrics"
CLOUD_RUN_NAME_REWRITE = (
    "stackdriver_prometheus_target_prometheus_googleapis_com_"
    "(omi_.+?)_(counter|gauge|histogram|summary|untyped|unknown)(_bucket|_sum|_count)?"
)


def _cloud_run_scrape_job(env: str) -> dict:
    import yaml

    values = yaml.safe_load(
        (
            Path(__file__).resolve().parents[3]
            / f"backend/charts/monitoring/kube-prometheus-stack/{env}_omi_monitoring_values.yaml"
        ).read_text(encoding="utf-8")
    )
    configs = values["prometheus"]["prometheusSpec"]["additionalScrapeConfigs"]
    return next(job for job in configs if job["job_name"] == CLOUD_RUN_SCRAPE_JOB)


@pytest.mark.parametrize("env", ["dev", "prod"])
def test_cloud_run_metrics_are_renamed_back_to_their_plain_prometheus_names(env):
    """Ingested-but-unmatched is the same outage as never-ingested.

    The Stackdriver exporter renames every imported series to
    stackdriver_<resource>_<metric type>_<value type>. Without this rewrite,
    omi_journey_accepted_total arrives from Cloud Run as
    stackdriver_prometheus_target_prometheus_googleapis_com_omi_journey_accepted_total_counter
    and every existing alert, recording rule, and dashboard keeps matching
    nothing while the metrics are demonstrably flowing.
    """
    job = _cloud_run_scrape_job(env)
    rewrites = [rule for rule in job.get("metric_relabel_configs", []) if rule.get("target_label") == "__name__"]

    assert rewrites, f"{env}: cloud-run scrape job does not rename anything"
    rewrite = rewrites[0]
    assert rewrite["regex"] == CLOUD_RUN_NAME_REWRITE, env
    assert rewrite["source_labels"] == ["__name__"], env
    assert rewrite["replacement"] == "${1}${3}", env


@pytest.mark.parametrize(
    "mangled,plain",
    [
        (
            "stackdriver_prometheus_target_prometheus_googleapis_com_omi_journey_accepted_total_counter",
            "omi_journey_accepted_total",
        ),
        (
            "stackdriver_prometheus_target_prometheus_googleapis_com_omi_client_journey_duration_seconds_histogram_bucket",
            "omi_client_journey_duration_seconds_bucket",
        ),
        (
            "stackdriver_prometheus_target_prometheus_googleapis_com_omi_client_journey_duration_seconds_histogram_sum",
            "omi_client_journey_duration_seconds_sum",
        ),
        # A metric whose own name contains a value-type word must not be
        # truncated at the first match.
        (
            "stackdriver_prometheus_target_prometheus_googleapis_com_omi_counter_edge_total_counter",
            "omi_counter_edge_total",
        ),
    ],
)
def test_the_rewrite_regex_recovers_the_original_metric_name(mangled, plain):
    match = re.fullmatch(CLOUD_RUN_NAME_REWRITE, mangled)

    assert match is not None, mangled
    assert match.group(1) + (match.group(3) or "") == plain


@pytest.mark.parametrize(
    "untouched",
    [
        "up",
        "llm_gateway_requests_total",
        "stackdriver_https_lb_rule_loadbalancing_googleapis_com_https_request_count_delta",
    ],
)
def test_the_rewrite_regex_leaves_every_other_series_alone(untouched):
    assert re.fullmatch(CLOUD_RUN_NAME_REWRITE, untouched) is None
