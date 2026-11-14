"""Repo-enforceable production telemetry contract (#9587).

Encodes expected scrape targets, routing labels, and coverage-alert linkage
without requiring live Grafana credentials. Complements #9138 exclusions;
does not duplicate managed-GKE control-plane disables (#11093).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
import subprocess
from typing import Any

import pytest

import yaml

from scripts.alert_backtest import metric_names, prometheus
from tests.unit.test_record_seal_cluster_repair_deploy import documents as repair_documents

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
CLOUD_RUN_SYNC_EXPORTER = (
    MONITORING / 'prometheus-stackdriver-exporter' / 'prod_sync_omi_cloud_run_metrics_exporter.yaml'
)
CLOUD_RUN_SYNC_EXPORTER_DEV = (
    MONITORING / 'prometheus-stackdriver-exporter' / 'dev_sync_omi_cloud_run_metrics_exporter.yaml'
)


def _cpu_millicores(value: object) -> float:
    text = str(value)
    return float(text[:-1]) if text.endswith('m') else float(text) * 1000


@pytest.mark.parametrize('env', ['dev', 'prod'])
def test_every_record_token_alert_metric_survives_its_producer_scrape_filters(env):
    rules = json.loads((MONITORING / 'alerts/record-token-lease.json').read_text())
    queried = set().union(
        *(metric_names(node['model']['expr']) for rule in rules for node in rule['data'] if prometheus(node))
    )
    producers = {
        'omi_record_token_late_append_total': {'sync', 'pusher'},
        'omi_record_token_lease_expired_sealed_total': {'repair'},
        'omi_record_seal_oldest_age_seconds': {'repair'},
    }
    assert queried == set(producers), 'new alert metrics require their actual producer ingestion path'

    def passes(name, relabels):
        labels = {'__name__': name}
        for rule in relabels:
            value = ';'.join(labels.get(key, '') for key in rule['sourceLabels'])
            matched = re.fullmatch(rule['regex'], value)
            if rule['action'] == 'keep' and not matched or rule['action'] == 'drop' and matched:
                return False
        return True

    sync = yaml.safe_load((REPO / 'backend/deploy/cloud_run_gmp_sync.yaml').read_text())
    sync_relabels = sync['spec']['endpoints'][0]['metricRelabeling']
    shared = yaml.safe_load((REPO / 'backend/deploy/cloud_run_gmp_sidecar.yaml').read_text())
    shared_relabels = shared['spec']['endpoints'][0]['metricRelabeling']
    # Keep the entire requested lease family, including histogram samples.
    for metric in (
        'omi_record_token_late_append_total',
        'omi_record_token_lease_renewals_total',
        'omi_record_token_lease_signal_gap_seconds_bucket',
        'omi_record_token_lease_signal_gap_seconds_sum',
        'omi_record_token_lease_signal_gap_seconds_count',
        'omi_record_token_lease_active',
        'omi_record_token_lease_expired_would_total',
        'omi_record_token_lease_expired_sealed_total',
    ):
        assert passes(metric, sync_relabels), metric
    pusher = REPO / 'backend/charts/pusher'
    result = subprocess.run(
        [
            'helm',
            'template',
            'prod-omi-pusher',
            str(pusher),
            '-n',
            'prod-omi-backend',
            '-f',
            str(pusher / 'prod_omi_pusher_values.yaml'),
            '--set-string',
            'image.digest=sha256:' + 'a' * 64,
            '--set',
            'image.pullPolicy=IfNotPresent',
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    pusher_monitors = [doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'PodMonitoring']
    assert len(pusher_monitors) == 1
    repair = repair_documents()['PodMonitoring', 'record-seal-repair']
    paths = {
        'sync': sync_relabels,
        'pusher': pusher_monitors[0]['spec']['endpoints'][0].get('metricRelabeling', []),
        'repair': repair['spec']['endpoints'][0].get('metricRelabeling', []),
    }
    for metric in queried:
        for producer in producers[metric]:
            assert passes(metric, paths[producer]), (producer, metric)
        if 'sync' in producers[metric]:
            assert passes(metric, shared_relabels)
            for profile in ('', 'sync_'):
                path = (
                    MONITORING / f'prometheus-stackdriver-exporter/{env}_{profile}omi_cloud_run_metrics_exporter.yaml'
                )
                prefixes = yaml.safe_load(path.read_text())['stackdriver']['metrics']['prefixes']
                assert f'prometheus.googleapis.com/{metric}/' in prefixes, (path.name, metric)


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


def test_lifecycle_alerts_share_existing_egress_trigger_and_gate_import():
    workflow = (REPO / '.github/workflows/gcp_cloud_run_metrics_egress.yml').read_text()
    assert "'backend/charts/monitoring/alerts/resilience.json'" in workflow
    assert "'backend/charts/monitoring/live-alert-gate.json'" in workflow
    rules = json.loads((MONITORING / 'alerts/resilience.json').read_text())
    lifecycle = {rule['uid']: rule for rule in rules if rule['annotations'].get('evidence_date') == '2026-11-04'}
    assert len(lifecycle) == 19
    gate = set(json.loads((MONITORING / 'live-alert-gate.json').read_text())['uids'])
    assert set(lifecycle) <= gate
    importer = (REPO / 'backend/scripts/verify_pusher_live_alert_route.py').read_text()
    assert 'for uid in load_gated_uids(committed)' in importer
    for uid, rule in lifecycle.items():
        assert rule['labels']['alert_identity'] == uid
        assert rule['notification_settings']['receiver'] == 'Omi - Services Alerting (Telegram)'


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
    'resource.labels.namespace=one_of("backend","desktop-backend","notifications-job")'
)

# The sync services run the full backend codebase, so every omi_* family arrives
# once per instance of each. Importing all of it took a collection from ~52k to
# ~187k series and OOMKilled the exporter at 2Gi (2026-10-16). A dedicated release
# imports only consumed families from these namespaces; the main release excludes
# them. One release cannot do both: the exporter ANDs every filter whose prefix
# matches, and Cloud Monitoring rejects OR across resource.labels with HTTP 400.
SYNC_NAMESPACES = ('backend-sync', 'backend-sync-backfill', 'backend-integration')
# The main release imports only families an in-cluster consumer can read from
# job=cloud-run-application-metrics: a query with an explicit job match, a job
# regex that includes it, or no job selector at all. The blanket omi_ prefix
# imported 188 families / ~54k live series on 2026-10-21, 156 of them read by
# nothing in-cluster, re-created once per Cloud Run instance replacement
# (~380k of the 2.27M-series Prometheus head). A trailing slash pins exactly
# one family. Extend this list only together with the consumer that reads the
# family from the backend/desktop-backend/notifications-job namespaces, and
# mirror the change into both <env>_omi_cloud_run_metrics_exporter.yaml files.
CLOUD_RUN_EXPORTER_PREFIXES = [
    'prometheus.googleapis.com/omi_finalization_pair_',
    'prometheus.googleapis.com/omi_enrichment_summary_repair_',
    'prometheus.googleapis.com/omi_batch_record_pending_',
    'prometheus.googleapis.com/omi_batch_held_expired_total/',
    'prometheus.googleapis.com/omi_batch_held_expired_units/',
    'prometheus.googleapis.com/omi_batch_held_expired_observed_at_seconds/',
    'prometheus.googleapis.com/omi_batch_record_dead_letter_total/',
    'prometheus.googleapis.com/omi_batch_record_dead_letter_units/',
    'prometheus.googleapis.com/omi_batch_record_dead_letter_observed_at_seconds/',
    'prometheus.googleapis.com/omi_backlog_state_transitions_total/',
    'prometheus.googleapis.com/omi_capture_retry_cap_total/',
    'prometheus.googleapis.com/omi_record_seal_nojob_',
    'prometheus.googleapis.com/omi_record_token_lease_',
    'prometheus.googleapis.com/omi_record_token_late_append_total/',
    'prometheus.googleapis.com/omi_enrichment_obligation_',
    'prometheus.googleapis.com/omi_finalization_byok_',
    'prometheus.googleapis.com/omi_capture_finalization_failures_total/',
    'prometheus.googleapis.com/omi_capture_finalization_reconciliations_total/',
    'prometheus.googleapis.com/omi_chat_search_tool_outcomes_total/',
    'prometheus.googleapis.com/omi_client_app_startup_duration_seconds/',
    'prometheus.googleapis.com/omi_client_events_total/',
    'prometheus.googleapis.com/omi_client_journey_accepted_total/',
    'prometheus.googleapis.com/omi_client_journey_duration_seconds/',
    'prometheus.googleapis.com/omi_client_journey_issues_total/',
    'prometheus.googleapis.com/omi_client_journey_terminal_total/',
    'prometheus.googleapis.com/omi_client_telemetry_rejected_total/',
    'prometheus.googleapis.com/omi_conversation_duration_seconds/',
    'prometheus.googleapis.com/omi_conversation_summary_vector_upserts_total/',
    'prometheus.googleapis.com/omi_daily_summary_resumed_cohort_age_seconds/',
    'prometheus.googleapis.com/omi_fallback_total/',
    'prometheus.googleapis.com/omi_firestore_documents_per_operation/',
    'prometheus.googleapis.com/omi_firestore_read_operations_total/',
    'prometheus.googleapis.com/omi_home_rows_user_day_count_total/',
    'prometheus.googleapis.com/omi_home_rows_user_day_sum_total/',
    'prometheus.googleapis.com/omi_journey_accepted_total/',
    'prometheus.googleapis.com/omi_journey_failure_reason_total/',
    'prometheus.googleapis.com/omi_journey_latency_seconds/',
    'prometheus.googleapis.com/omi_journey_terminal_total/',
    'prometheus.googleapis.com/omi_listen_audio_decode_failures_total/',
    'prometheus.googleapis.com/omi_listen_demand_failure_detail_total/',
    'prometheus.googleapis.com/omi_live_session_transcript_outcome_total/',
    'prometheus.googleapis.com/omi_owner_recognition_conversations_total/',
    'prometheus.googleapis.com/omi_product_event_total/',
    'prometheus.googleapis.com/omi_queue_oldest_ready_age_seconds/',
    'prometheus.googleapis.com/omi_queue_oldest_ready_sample_unknown/',
    'prometheus.googleapis.com/omi_stt_chain_exhausted_total/',
    'prometheus.googleapis.com/omi_stt_provider_circuit_open/',
    'prometheus.googleapis.com/omi_stt_provider_connect_total/',
    'prometheus.googleapis.com/omi_stt_provider_retired/',
    'prometheus.googleapis.com/omi_stt_stream_close_total/',
    'prometheus.googleapis.com/omi_subscription_events_total/',
    'prometheus.googleapis.com/omi_translation_cache_ops_total/',
    'prometheus.googleapis.com/omi_translation_chars_total/',
    'prometheus.googleapis.com/omi_translation_errors_total/',
    'prometheus.googleapis.com/omi_translation_latency_seconds/',
    'prometheus.googleapis.com/omi_translation_requests_total/',
    'prometheus.googleapis.com/omi_translation_skip_total/',
    'prometheus.googleapis.com/omi_vertex_managed_25_attempts_total/',
    'prometheus.googleapis.com/omi_vertex_managed_25_on_demand_responses_total/',
    'prometheus.googleapis.com/omi_vertex_non_dream_flash_after_cutover_attempts_total/',
]
CLOUD_RUN_SYNC_EXPORTER_FILTER = (
    'prometheus.googleapis.com/omi_:resource.labels.cluster="__run__" AND '
    'resource.labels.namespace=one_of("backend-sync","backend-sync-backfill","backend-integration")'
)
# omi_sync_ is pinned to its consumed families: omi_sync_phase_* (no in-cluster
# consumer, read from GMP by the rightsizing runbook) alone re-created ~13k live
# series per backend-sync instance generation through this release.
CLOUD_RUN_SYNC_EXPORTER_PREFIXES = [
    'prometheus.googleapis.com/omi_batch_timeliness_',
    'prometheus.googleapis.com/omi_batch_allowance_held_units/',
    'prometheus.googleapis.com/omi_batch_held_oldest_age_seconds/',
    'prometheus.googleapis.com/omi_batch_projection_drain_oldest_age_seconds/',
    'prometheus.googleapis.com/omi_batch_staged_input_clock_invalid_total/',
    'prometheus.googleapis.com/omi_finalization_pair_',
    'prometheus.googleapis.com/omi_enrichment_summary_repair_',
    'prometheus.googleapis.com/omi_batch_record_pending_',
    'prometheus.googleapis.com/omi_batch_held_expired_total/',
    'prometheus.googleapis.com/omi_batch_held_expired_units/',
    'prometheus.googleapis.com/omi_batch_held_expired_observed_at_seconds/',
    'prometheus.googleapis.com/omi_batch_record_dead_letter_total/',
    'prometheus.googleapis.com/omi_batch_record_dead_letter_units/',
    'prometheus.googleapis.com/omi_batch_record_dead_letter_observed_at_seconds/',
    'prometheus.googleapis.com/omi_conversation_finalization_dead_letter_total/',
    'prometheus.googleapis.com/omi_backlog_state_transitions_total/',
    'prometheus.googleapis.com/omi_capture_retry_cap_total/',
    'prometheus.googleapis.com/omi_record_seal_nojob_',
    'prometheus.googleapis.com/omi_record_token_lease_',
    'prometheus.googleapis.com/omi_record_token_late_append_total/',
    'prometheus.googleapis.com/omi_enrichment_obligation_',
    'prometheus.googleapis.com/omi_finalization_byok_',
    'prometheus.googleapis.com/omi_sync_dispatch_attempts_total/',
    'prometheus.googleapis.com/omi_sync_upload_total/',
    'prometheus.googleapis.com/omi_sync_transcription_job_total/',
    'prometheus.googleapis.com/omi_sync_intake',
    'prometheus.googleapis.com/omi_journey_',
    'prometheus.googleapis.com/omi_client_journey_',
    'prometheus.googleapis.com/omi_owner_recognition_conversations_total/',
    'prometheus.googleapis.com/omi_conversation_duration_seconds/',
    'prometheus.googleapis.com/omi_conversation_relevance_decision_total/',
    'prometheus.googleapis.com/omi_conversation_summary_vector_upserts_total/',
    'prometheus.googleapis.com/omi_firestore_documents_per_operation/',
    'prometheus.googleapis.com/omi_capture_finalization_',
    'prometheus.googleapis.com/omi_held_content_',
    'prometheus.googleapis.com/omi_stt_cap_recovery_reconciliation_total/',
    'prometheus.googleapis.com/omi_queue_oldest_ready_',
]


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
    assert metrics['prefixes'] == CLOUD_RUN_EXPORTER_PREFIXES
    # stackdriver_exporter silently drops a prefix that starts with another listed one.
    for prefix in metrics['prefixes']:
        assert not any(other != prefix and prefix.startswith(other) for other in metrics['prefixes'])
    # The custom-metric omi_sync_phase_ import left with its filter: nothing in-cluster reads it.
    assert not any(prefix.startswith('custom.googleapis.com/') for prefix in metrics['prefixes'])
    assert metrics['interval'] == '10m'
    assert metrics['offset'] == '1m'
    assert metrics['filters'] == [CLOUD_RUN_EXPORTER_FILTER]
    assert values['serviceAccount'] == {
        'create': False,
        'name': service_account,
    }
    for namespace in SYNC_NAMESPACES:
        assert f'"{namespace}"' not in metrics['filters'][0], f'{path.name}: {namespace} belongs to the sync release'


@pytest.mark.parametrize(
    ('path', 'env', 'project_id'),
    (
        (CLOUD_RUN_SYNC_EXPORTER, 'prod', 'based-hardware'),
        (CLOUD_RUN_SYNC_EXPORTER_DEV, 'dev', 'based-hardware-dev'),
    ),
    ids=('prod', 'dev'),
)
def test_cloud_run_sync_metrics_exporter_imports_only_consumed_families(path, env, project_id):
    values = yaml.safe_load(path.read_text(encoding='utf-8'))
    metrics = values['stackdriver']['metrics']
    assert values['fullnameOverride'] == f'{env}-omi-cloud-run-sync-metrics-exporter'
    assert values['stackdriver']['projectIds'] == [project_id]
    assert metrics['prefixes'] == CLOUD_RUN_SYNC_EXPORTER_PREFIXES
    # stackdriver_exporter silently drops a prefix that starts with another listed one.
    for prefix in metrics['prefixes']:
        assert not any(other != prefix and prefix.startswith(other) for other in metrics['prefixes'])
    assert metrics['filters'] == [CLOUD_RUN_SYNC_EXPORTER_FILTER]
    assert metrics['interval'] == '10m'
    assert metrics['offset'] == '1m'
    assert values['serviceAccount'] == {'create': False, 'name': f'{env}-omi-prometheus-stackdriver-exporter'}


@pytest.mark.parametrize('env', ('prod', 'dev'))
def test_cloud_run_application_job_scrapes_both_exporter_releases(env):
    text = (MONITORING / 'kube-prometheus-stack' / f'{env}_omi_monitoring_values.yaml').read_text(encoding='utf-8')
    job = text[text.index('- job_name: cloud-run-application-metrics') :]
    match = re.search(r'regex: "([^"]+)"', job)
    assert match
    pattern = re.compile(match.group(1))
    for release in (f'{env}-omi-cloud-run-metrics-exporter', f'{env}-omi-cloud-run-sync-metrics-exporter'):
        assert pattern.fullmatch(release), release
    # The 1-second LB/Firestore exporter job must not pick either release up.
    assert not re.fullmatch('(.*)-prometheus-stackdriver-exporter', f'{env}-omi-cloud-run-sync-metrics-exporter')


@pytest.mark.parametrize(
    'path',
    (CLOUD_RUN_EXPORTER, CLOUD_RUN_EXPORTER_DEV, CLOUD_RUN_SYNC_EXPORTER, CLOUD_RUN_SYNC_EXPORTER_DEV),
    ids=('prod', 'dev', 'sync-prod', 'sync-dev'),
)
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


@pytest.mark.parametrize(
    'path',
    (CLOUD_RUN_EXPORTER, CLOUD_RUN_EXPORTER_DEV, CLOUD_RUN_SYNC_EXPORTER, CLOUD_RUN_SYNC_EXPORTER_DEV),
    ids=('prod', 'dev', 'sync-prod', 'sync-dev'),
)
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


REVIEWED_EXEMPTIONS = frozenset()  # Today: every job is enforced.
# The literal prefix plus inventory name is 41 characters; Grafana allows 40.
COVERAGE_UID_OVERRIDES = {'prometheus-stackdriver-metrics': 'omi-scrape-stackdriver-metrics'}


def test_every_scrape_job_is_enforced_by_a_named_coverage_rule():
    inventory = _load_inventory()
    rules = {rule['uid']: rule for rule in _alert_rules()}
    for job in inventory['scrape_jobs']:
        name = job['name']
        if job.get('coverage_status') == 'exempt':
            assert name in REVIEWED_EXEMPTIONS, f"{name}: exemption not reviewed"
            assert job.get('coverage_exemption_reason'), name
            assert job.get('coverage_alert') is None, name
            continue
        assert job.get('coverage_status') == 'enforced', (
            f"{name}: coverage_status must be 'enforced' or 'exempt' with a reason "
            "(the old silent 'declared' status is gone; KSM 2026-11-05)"
        )
        uid = job['coverage_alert']
        assert uid == COVERAGE_UID_OVERRIDES.get(name, f'omi-scrape-{name}'), name
        rule = rules.get(uid)
        assert rule, f"{name}: coverage rule {uid} missing from alert-rules.json"
        expr = rule['data'][0]['model']['expr'] if rule.get('data') else ''
        assert expr, f"{uid} has no data[].model.expr"
        # Check the actual query matcher, not a job name in unrelated metadata.
        matcher = job.get('job_matcher') or f'job="{name}"'
        assert f'up{{{matcher}}}' in expr, f"{name}: {uid} expr lacks matcher {matcher!r}"
        modes = job.get('coverage_modes') or ['down', 'absent', 'empty']
        if 'empty' in modes:
            assert f'scrape_samples_scraped{{{matcher}}}' in expr, name
        if 'absent' in modes:
            assert 'absent(' in expr and rule['noDataState'] == 'Alerting', name
        else:
            assert 'absent(' not in expr, f"{name}: absence is legitimate"
            assert rule['noDataState'] == 'OK', f"{name}: presence-gated rule must treat NoData as OK"
        if 'empty' in modes:
            # `or` is a set union, not boolean OR: healthy up=1 yields an
            # unlabeled zero that would mask an empty-scrape one on the right.
            down = f'(min(up{{{matcher}}}) < bool 1)'
            samples = f'scrape_samples_scraped{{{matcher}}}'
            if 'absent' in modes:
                expected_expr = (
                    f'max(absent(up{{{matcher}}}) or {down}) + '
                    f'((min(min_over_time({samples}[15m])) or vector(0)) < bool 1)'
                )
            else:
                expected_expr = f'{down} + (min(min_over_time({samples}[15m])) < bool 1)'
            assert expr == expected_expr, f"{name}: down must not mask empty scrapes"
        if 'empty' not in modes:
            extra = job.get('empty_scrape_alert')
            assert extra, f"{name}: empty mode must be owned by a named rule"
            owner_rule = rules[extra]
            owner_expr = owner_rule['data'][0]['model']['expr']
            # The named owner is the only empty-mode guard, so pin it exactly; it is gated on the
            # target being up so down/absence stays with this job's own rule (no double firing).
            assert owner_expr == (
                f'(min(min_over_time(scrape_samples_scraped{{{matcher}}}[15m])) < bool 1) '
                f'and on() (max(max_over_time(up{{{matcher}}}[15m])) == 1)'
            ), f"{name}: empty-scrape owner {extra} must alert on empty scrapes while up"
            assert owner_rule['for'] == '30m' and owner_rule['noDataState'] == 'OK', extra
            assert owner_rule['labels']['alert_identity'] == extra, extra
        assert rule['for'] == '30m' and rule['labels']['tier'] == 'agent', uid
        assert rule['labels']['alert_identity'] == uid, uid


def test_no_job_is_declared_without_coverage_any_more():
    inventory = _load_inventory()
    for job in inventory['scrape_jobs']:
        assert (
            job.get('coverage_status') != 'declared'
        ), f"{job['name']}: 'declared' was eliminated 2026-11; enforce or exempt-with-reason"


def test_alert_rules_use_declared_receiver_and_instatus_components():
    inventory = _load_inventory()
    routing = inventory['routing']
    allowed = set(routing['allowed_instatus_components'])
    default_receiver = routing['default_receiver']
    label_key = routing['instatus_label']

    for rule in _alert_rules():
        receiver = (rule.get('notification_settings') or {}).get('receiver')
        assert receiver == default_receiver, f"{rule.get('uid')}: unexpected receiver {receiver!r}"
        labels = rule.get('labels') or {}
        component = labels.get(label_key)
        canary_sources = {
            'omi-datasource-prometheus': 'prometheus',
            'omi-datasource-cloud-monitoring': 'beuxmaq8oxhq8e',
            'omi-datasource-gmp': 'gmp-cloud-run',
        }
        if rule.get('uid') in canary_sources:
            # A datasource outage is monitoring infrastructure, not evidence of
            # an Omi product outage. These explicit canaries reach Telegram
            # via the root receiver and must not update a product Instatus page.
            source = canary_sources[rule['uid']]
            assert labels['impact'] == 'infrastructure'
            assert labels['component'] == 'monitoring'
            assert labels['datasource_uid'] == source
            assert rule['data'][0]['datasourceUid'] == source
            assert component is None
        elif labels.get('component') == 'mobile-capture':
            # Device signals come from PostHog fleet telemetry, not a product
            # service; they never drive a public Instatus component.
            assert component is None
        else:
            assert component in allowed, f"{rule.get('uid')}: unexpected {label_key}={component!r}"


def test_every_alert_rule_declares_tier_owner_and_audience():
    # Only tier=page reaches the human Telegram channel. Agent-tier rules keep
    # evaluating (agents read them from the Alertmanager API) but are muted by
    # the always-on time interval, so a missing label is a page-noise bug.
    routing = _load_inventory()['routing']
    silent = routing['agent_tier_mute_timing']
    for rule in _alert_rules():
        uid = rule.get('uid')
        labels = rule.get('labels') or {}
        settings = rule.get('notification_settings') or {}
        assert labels.get('owner'), f"{uid}: missing owner label"
        assert labels.get('tier') in {'page', 'agent'}, f"{uid}: tier must be page or agent"
        if labels['tier'] == 'page':
            assert labels.get('audience') == 'human', uid
            assert silent not in (settings.get('mute_time_intervals') or []), f"{uid}: page rule is muted"
        else:
            assert labels.get('audience') == 'agent', uid
            assert silent in (settings.get('mute_time_intervals') or []), f"{uid}: agent rule would page Telegram"


def test_scrape_health_no_data_semantics_match_inventory():
    inventory = _load_inventory()
    expected = inventory['no_data_semantics']['scrape_health']
    rules = {rule['uid']: rule for rule in _alert_rules()}
    assert rules['omi-journey-scrape-missing']['noDataState'] == expected
    for job in inventory['scrape_jobs']:
        if job.get('coverage_status') == 'exempt':
            continue
        modes = job.get('coverage_modes') or ['down', 'absent', 'empty']
        key = 'scrape_health' if 'absent' in modes else 'scrape_health_presence_gated'
        assert rules[job['coverage_alert']]['noDataState'] == inventory['no_data_semantics'][key], job['name']


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


CLOUD_MONITORING_CUSTOM_REWRITE = "stackdriver_generic_task_custom_googleapis_com_(omi_.+)"


@pytest.mark.parametrize("env", ["dev", "prod"])
def test_custom_metric_api_aggregates_are_renamed_back_too(env):
    """backend-sync writes omi_sync_phase_* through the custom-metric API, which the
    exporter names stackdriver_generic_task_custom_googleapis_com_<name>. Leaving them
    mangled keeps omi-cloud-run-metric-names-unnormalized pending at critical."""
    import re

    job = _cloud_run_scrape_job(env)
    rewrites = [rule for rule in job.get("metric_relabel_configs", []) if rule.get("target_label") == "__name__"]
    custom = [rule for rule in rewrites if rule["regex"] == CLOUD_MONITORING_CUSTOM_REWRITE]
    assert len(custom) == 1, env
    assert custom[0]["source_labels"] == ["__name__"] and custom[0]["replacement"] == "${1}", env
    mangled = "stackdriver_generic_task_custom_googleapis_com_omi_sync_phase_duration_seconds_bucket"
    match = re.fullmatch(CLOUD_MONITORING_CUSTOM_REWRITE, mangled)
    assert match and match.group(1) == "omi_sync_phase_duration_seconds_bucket"
    # The unnormalized alert counts stackdriver_.*_omi_.* names; nothing inventoried may still carry one.
    inventory = json.loads(
        (Path(__file__).resolve().parents[3] / "backend/charts/monitoring/metric-inventory.prod.json").read_text()
    )
    assert not [m for m in inventory["metrics"] if re.fullmatch(r"stackdriver_.*_omi_.*", m)]


@pytest.mark.parametrize(
    'path', [CLOUD_RUN_EXPORTER, CLOUD_RUN_EXPORTER_DEV, CLOUD_RUN_SYNC_EXPORTER, CLOUD_RUN_SYNC_EXPORTER_DEV]
)
def test_held_dead_letter_producer_families_reach_the_volume_alert_through_each_cloud_run_bridge(path):
    from prometheus_client import CollectorRegistry
    from utils.batch_pipeline.metrics import QueueMetrics

    registry = CollectorRegistry()
    producer = QueueMetrics(registry)
    producer.held_expired.inc()
    producer.held_expired_stock.set(101)
    producer.held_expired_observed_at.set(1000)
    families = {
        'omi_batch_held_expired_total',
        'omi_batch_held_expired_units',
        'omi_batch_held_expired_observed_at_seconds',
    }
    emitted = {sample.name for metric in registry.collect() for sample in metric.samples}
    assert families <= emitted
    imported = set(yaml.safe_load(path.read_text())['stackdriver']['metrics']['prefixes'])
    assert {f'prometheus.googleapis.com/{name}/' for name in families} <= imported
    rule = next(r for r in json.loads(ALERT_RULES.read_text()) if r['uid'] == 'omi-batch-held-expired-volume')
    queries = ' '.join(node['model'].get('expr', '') for node in rule['data'])
    assert all(name in queries for name in families)


@pytest.mark.parametrize(
    'path', [CLOUD_RUN_EXPORTER, CLOUD_RUN_EXPORTER_DEV, CLOUD_RUN_SYNC_EXPORTER, CLOUD_RUN_SYNC_EXPORTER_DEV]
)
@pytest.mark.parametrize('profile', ['cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'])
def test_record_dead_letter_alert_metrics_survive_each_ingestion_allowlist(path, profile):
    from prometheus_client import CollectorRegistry
    from scripts.alert_backtest import metric_names, prometheus
    from utils.batch_pipeline.metrics import QueueMetrics

    rule = next(r for r in json.loads(ALERT_RULES.read_text()) if r['uid'] == 'omi-batch-record-dead-letter-volume')
    queried = set().union(*(metric_names(node['model']['expr']) for node in rule['data'] if prometheus(node)))
    assert queried == {
        'omi_batch_record_dead_letter_total',
        'omi_batch_record_dead_letter_units',
        'omi_batch_record_dead_letter_observed_at_seconds',
    }
    registry = CollectorRegistry()
    producer = QueueMetrics(registry)
    producer.record_dead_letter.inc()
    producer.record_dead_letter_stock.set(101)
    producer.record_dead_letter_observed_at.set(1000)
    emitted = {sample.name for metric in registry.collect() for sample in metric.samples}
    assert queried <= emitted
    inventory = json.loads((MONITORING / 'metric-inventory.prod.json').read_text())
    assert queried <= set(inventory['declared_metrics'])
    imported = set(yaml.safe_load(path.read_text())['stackdriver']['metrics']['prefixes'])
    assert {f'prometheus.googleapis.com/{name}/' for name in queried} <= imported
    relabels = yaml.safe_load((REPO / 'backend/deploy' / profile).read_text())['spec']['endpoints'][0][
        'metricRelabeling'
    ]
    for name in queried:
        labels = {'__name__': name}
        for relabel in relabels:
            value = ';'.join(labels.get(key, '') for key in relabel['sourceLabels'])
            matched = re.fullmatch(relabel['regex'], value)
            if relabel['action'] == 'keep':
                assert matched, (profile, name)
            elif relabel['action'] == 'drop':
                assert not matched, (profile, name)


BACKLOG_ALERTS = MONITORING / 'alerts' / 'backlog-state-machine.json'


def _imported(family, prefixes):
    for prefix in prefixes:
        name = prefix.removeprefix('prometheus.googleapis.com/')
        if name.endswith('/') and family == name[:-1]:
            return True
        if not name.endswith('/') and family.startswith(name):
            return True
    return False


@pytest.mark.parametrize('env', ['prod', 'dev'])
def test_backlog_alert_metric_families_are_imported_by_the_cloud_run_exporters(env):
    """Alert-to-importer wiring: a family no exporter imports reads as vector(0), so its alert never fires.

    Batch transitions are emitted by backend (serving maintenance, intake polls,
    operator routes) and sync caps by the sync sequencer, so every family the
    backlog alerts query must reach in-cluster Prometheus through both releases.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location('alert_backtest', MONITORING.parents[1] / 'scripts/alert_backtest.py')
    backtest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backtest)
    exporters = {
        'prod': (CLOUD_RUN_EXPORTER, CLOUD_RUN_SYNC_EXPORTER),
        'dev': (CLOUD_RUN_EXPORTER_DEV, CLOUD_RUN_SYNC_EXPORTER_DEV),
    }[env]
    rules = json.loads(BACKLOG_ALERTS.read_text(encoding='utf-8'))
    families = set()
    for alert in rules:
        for node in alert['data']:
            expr = node.get('model', {}).get('expr')
            if expr:
                families |= set(backtest.metric_names(expr))
    assert families >= {'omi_backlog_state_transitions_total', 'omi_capture_retry_cap_total'}
    for path in exporters:
        prefixes = yaml.safe_load(path.read_text(encoding='utf-8'))['stackdriver']['metrics']['prefixes']
        missing = sorted(family for family in families if not _imported(family, prefixes))
        assert not missing, f'{path.name} does not import {missing}'

    # Check the producer-side GMP filters too: importing a family downstream
    # cannot recover samples discarded by the source scrape allowlist.
    for profile in ('cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'):
        relabels = yaml.safe_load((REPO / 'backend/deploy' / profile).read_text())['spec']['endpoints'][0][
            'metricRelabeling'
        ]
        for family in families:
            labels = {'__name__': family}
            for relabel in relabels:
                value = ';'.join(labels.get(key, '') for key in relabel['sourceLabels'])
                matched = re.fullmatch(relabel['regex'], value)
                if relabel['action'] == 'keep':
                    assert matched, (profile, family)
                elif relabel['action'] == 'drop':
                    assert not matched, (profile, family)
