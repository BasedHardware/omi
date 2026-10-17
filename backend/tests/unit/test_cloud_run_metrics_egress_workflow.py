"""Static ownership contract for the Cloud Run metrics Helm releases.

The egress values are inert until a credentialed workflow installs both the
Cloud Monitoring exporter and the Prometheus scrape configuration.
"""

from pathlib import Path
import json
import os
import subprocess

import pytest

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / '.github/workflows/gcp_cloud_run_metrics_egress.yml'
EXPORTER_VALUES = ROOT / 'backend/charts/monitoring/prometheus-stackdriver-exporter'
STACK_VALUES = ROOT / 'backend/charts/monitoring/kube-prometheus-stack'


def _workflow() -> dict:
    loaded = yaml.load(WORKFLOW.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    assert isinstance(loaded, dict)
    return loaded


def _run_scripts(workflow: dict) -> str:
    steps = workflow['jobs']['deploy']['steps']
    return '\n'.join(str(step.get('run', '')) for step in steps)


def test_workflow_owns_dev_auto_deploy_and_manual_production() -> None:
    workflow = _workflow()
    triggers = workflow['on']

    assert triggers['push']['branches'] == ['main']
    assert set(triggers['push']['paths']) == {
        'backend/charts/monitoring/prometheus-stackdriver-exporter/*_omi_cloud_run_metrics_exporter.yaml',
        'backend/charts/monitoring/kube-prometheus-stack/*_omi_monitoring_values.yaml',
        'backend/charts/monitoring/alerts/live-stt.json',
        'backend/charts/monitoring/alerts/resilience.json',
        'backend/charts/monitoring/live-alert-gate.json',
        'backend/charts/monitoring/gmp/frontend-values.prod.yaml',
        '.github/workflows/gcp_cloud_run_metrics_egress.yml',
    }
    environment = triggers['workflow_dispatch']['inputs']['environment']
    assert environment['options'] == ['development', 'prod']
    assert workflow['concurrency'] == {
        'group': "deploy-cloud-run-metrics-egress-${{ github.event.inputs.environment || 'development' }}",
        'cancel-in-progress': 'false',
    }
    assert workflow['jobs']['deploy']['steps'][0]['with']['ref'] == '${{ github.sha }}'
    assert workflow['jobs']['deploy']['if'] == "github.ref == 'refs/heads/main'"
    assert workflow['jobs']['deploy']['environment'] == (
        "${{ github.event.inputs.environment == 'prod' && 'prod' || 'development' }}"
    )


def test_workflow_installs_both_pinned_releases_with_retention_safe_prod_rollback() -> None:
    scripts = _run_scripts(_workflow())

    assert 'stack_release=dev-kube-prometheus-stack' in scripts
    assert 'stack_release=prod-omi-kube-prometheus-stack' in scripts
    assert 'EXPORTER_RELEASE=${ENV_SLUG}-omi-cloud-run-metrics-exporter' in scripts
    assert 'SYNC_EXPORTER_RELEASE=${ENV_SLUG}-omi-cloud-run-sync-metrics-exporter' in scripts
    assert scripts.count('helm upgrade --install') == 3
    assert scripts.count('--atomic') == 3
    assert scripts.count('prometheus-stackdriver-exporter \\\n  --version 4.8.3') == 4
    assert 'kube-prometheus-stack \\\n  --version 75.15.1' in scripts
    assert 'for release in "$EXPORTER_RELEASE" "$SYNC_EXPORTER_RELEASE"; do' in scripts
    assert 'kubectl rollout status "deployment/$release"' in scripts


def test_sync_exporter_installs_before_the_main_exporter_drops_sync_namespaces() -> None:
    steps = _workflow()['jobs']['deploy']['steps']
    names = [step.get('name') for step in steps]
    assert (
        names.index('Deploy isolated Cloud Run sync metrics exporter')
        < names.index('Deploy isolated Cloud Run metrics exporter')
        < names.index('Deploy Prometheus scrape configuration')
    )


STATS_PROXY_FLAG = '--set-string "grafana.podAnnotations.omi-stats-proxy-sha256=$STATS_PROXY_SHA256"'


def test_stack_upgrade_keeps_the_parent_applied_stats_proxy_annotation() -> None:
    """The values file does not carry Grafana's omi-stats-proxy-sha256 annotation.

    The parent applies the grafana-stats-proxy ConfigMap and sets the annotation by
    hand. A stack upgrade without it drops the annotation, which changes the pod
    template and restarts Grafana on every run of this workflow.
    """
    steps = _workflow()['jobs']['deploy']['steps']
    by_name = {step.get('name'): step for step in steps}
    resolve = by_name['Resolve environment-specific release contract']['run']
    assert (
        'stats_proxy_sha256="$(sha256sum backend/charts/monitoring/grafana/stats_proxy.py | cut -d\' \' -f1)"'
        in resolve
    )
    assert 'echo "STATS_PROXY_SHA256=$stats_proxy_sha256"' in resolve
    # Hashed only for prod: dev Grafana has no stats proxy to roll.
    prod_branch = resolve[resolve.index('prod)') : resolve.index(';;', resolve.index('prod)'))]
    assert 'sha256sum' in prod_branch
    dev_branch = resolve[resolve.index('dev)') : resolve.index(';;', resolve.index('dev)'))]
    assert 'sha256sum' not in dev_branch

    for name in ('Render Cloud Run metrics egress releases', 'Deploy Prometheus scrape configuration'):
        run = by_name[name]['run']
        stack_command = run[run.index('"$STACK_RELEASE" prometheus-community/kube-prometheus-stack') :]
        assert STATS_PROXY_FLAG in run, name
        assert '"${stack_flags[@]}"' in stack_command, name
    # The ConfigMap stays parent-applied; this workflow never writes it.
    workflow_text = WORKFLOW.read_text(encoding='utf-8').lower()
    assert 'kubectl apply' not in workflow_text
    assert 'create configmap' not in workflow_text


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_production_overlay_and_rollback_flags_reach_helm_only_in_prod(tmp_path, environment):
    steps = _workflow()['jobs']['deploy']['steps']
    script = next(step['run'] for step in steps if step['name'] == 'Deploy Prometheus scrape configuration')
    helm = tmp_path / 'helm'
    helm.write_text(
        '#!/usr/bin/env python3\nimport json,os,sys\nopen(os.environ["RECORDED_ARGS"],"w").write(json.dumps(sys.argv[1:]))\n'
    )
    helm.chmod(0o755)
    recorded = tmp_path / 'args.json'
    env = {
        **os.environ,
        'PATH': str(tmp_path) + os.pathsep + os.environ['PATH'],
        'MONITORING_NAMESPACE': f'{environment}-omi-monitoring',
        'STACK_RELEASE': f'{environment}-stack',
        'STACK_VALUES': 'base-values.yaml',
        # Defined for both environments like the resolve step, and non-empty so
        # local bash 3.2 does not treat the empty stack_flags array as unbound.
        'STATS_PROXY_SHA256': '0' * 64,
        'RECORDED_ARGS': str(recorded),
    }
    subprocess.run(['bash', '-c', script], env=env, check=True, capture_output=True, text=True)
    arguments = json.loads(recorded.read_text())
    assert ('--atomic' in arguments) is (environment == 'dev')
    assert '--skip-crds' in arguments
    assert ('backend/charts/monitoring/gmp/frontend-values.prod.yaml' in arguments) is (environment == 'prod')


def test_grafana_writers_share_environment_lock_and_prod_checks_query_path():
    workflow = _workflow()
    provision = workflow['jobs']['provision-live-alerts']
    assert provision['concurrency'] == {
        'group': "grafana-alert-provisioning-${{ github.event.inputs.environment == 'prod' && 'prod' || 'dev' }}",
        'cancel-in-progress': 'false',
    }
    step = next(
        step for step in workflow['jobs']['deploy']['steps'] if step['name'] == 'Verify production GMP query path'
    )
    assert step['if'] == "github.event.inputs.environment == 'prod'"
    assert 'provision_monitoring_alerts.py --probe-datasources' in step['run']
    assert '--context gke_based-hardware_us-central1_prod-omi-gke' in step['run']
    assert step['env']['MONITOR_GRAFANA_TOKEN'] == '${{ secrets.MONITOR_GRAFANA_TOKEN }}'
    dashboard = yaml.load(
        (ROOT / '.github/workflows/grafana_dashboard_provisioning.yml').read_text(), Loader=yaml.BaseLoader
    )
    writer = dashboard['jobs']['provision']
    assert writer['concurrency'] == {
        'group': 'grafana-alert-provisioning-${{ matrix.environment }}',
        'cancel-in-progress': 'false',
    }
    assert writer['environment'] == "${{ matrix.environment == 'prod' && 'prod' || 'development' }}"
    assert writer['strategy']['matrix']['environment'] == ["${{ github.event.inputs.environment || 'dev' }}"]
    alert_step = next(
        s for s in writer['steps'] if s.get('name') == 'Apply production alert definitions and check drift'
    )
    assert alert_step['if'] == "matrix.environment == 'prod'"
    assert '--backup-file' in alert_step['run']


def test_workflow_provisions_live_stt_alerts_independently_of_helm() -> None:
    workflow = _workflow()
    jobs = workflow['jobs']
    deploy = jobs['deploy']
    provision = jobs['provision-live-alerts']
    provision_steps = provision['steps']
    deploy_names = {step['name'] for step in deploy['steps']}
    assert 'Import allowlisted live-STT Grafana alerts' not in deploy_names
    assert 'Verify imported live-STT Grafana alert coverage' not in deploy_names

    assert provision['if'] == "github.ref == 'refs/heads/main'"
    assert provision['environment'] == deploy['environment']
    assert provision['permissions'] == {'contents': 'read'}
    assert 'needs' not in provision
    assert provision_steps[0]['uses'] == 'actions/checkout@v7'
    assert provision_steps[0]['with']['ref'] == '${{ github.sha }}'
    assert not any(
        'google-github-actions/auth@' in step.get('uses', '')
        or 'google-github-actions/get-gke-credentials@' in step.get('uses', '')
        for step in provision_steps
    )

    steps = provision_steps
    names = [step['name'] for step in steps]
    imported = names.index('Import allowlisted live-STT Grafana alerts')
    verified = names.index('Verify imported live-STT Grafana alert coverage')
    assert imported < verified
    import_run = steps[imported]['run']
    verify_run = steps[verified]['run']
    assert '--mode import' in import_run
    assert '--mode fleet' in verify_run
    assert '--alert-set live-stt' in verify_run
    assert '--fail-on gated' in verify_run
    for run in (import_run, verify_run):
        assert 'MONITOR_GRAFANA_TOKEN' in run
        assert 'token_file' in run
        assert '--token-file "$token_file"' in run
        assert 'umask 077' in run
        assert 'trap cleanup EXIT' in run
        assert (
            steps[imported if run == import_run else verified]['env']['MONITOR_GRAFANA_TOKEN']
            == '${{ secrets.MONITOR_GRAFANA_TOKEN }}'
        )
        assert 'python3 backend/scripts/verify_pusher_live_alert_route.py' in run
    push_paths = set(workflow['on']['push']['paths'])
    assert 'backend/charts/monitoring/alerts/live-stt.json' in push_paths
    assert 'backend/charts/monitoring/alerts/resilience.json' in push_paths
    assert 'backend/charts/monitoring/live-alert-gate.json' in push_paths


def test_workflow_values_exist_for_every_environment() -> None:
    for environment in ('dev', 'prod'):
        assert (EXPORTER_VALUES / f'{environment}_omi_cloud_run_metrics_exporter.yaml').is_file()
        assert (EXPORTER_VALUES / f'{environment}_sync_omi_cloud_run_metrics_exporter.yaml').is_file()
        assert (STACK_VALUES / f'{environment}_omi_monitoring_values.yaml').is_file()


def test_deadman_is_prod_only_and_cannot_block_the_helm_rollout() -> None:
    steps = _workflow()['jobs']['deploy']['steps']
    names = [step['name'] for step in steps]
    validate = steps[names.index('Validate prod dead-man notification channels')]
    ensure = steps[names.index('Ensure external prod Grafana dead-man')]
    for step in (validate, ensure):
        assert step['if'] == "github.event.inputs.environment == 'prod'"
        assert step['env']['ALERT_CHANNELS'] == '${{ vars.MONITORING_DEADMAN_NOTIFICATION_CHANNELS }}'
    assert 'exit 1' in validate['run']
    assert 'must be created' in validate['run']
    assert names.index(validate['name']) < names.index('Google Auth (prod WIF)')
    assert names.index('Google Auth (prod WIF)') < names.index(ensure['name'])
    # A Monitoring IAM gap must not block the Grafana/Prometheus rollout (2026-10-13 prod run 38344425582).
    assert names.index('Deploy Prometheus scrape configuration') < names.index(ensure['name'])
    assert names.index('Verify deployed egress resources') < names.index(ensure['name'])
    assert '--notification-channels="$ALERT_CHANNELS"' in ensure['run']
    assert 'SYNC_BACKFILL_ALERT_NOTIFICATION_CHANNELS' not in WORKFLOW.read_text()


def test_production_verifies_operator_created_replicas_before_egress_success() -> None:
    steps = _workflow()['jobs']['deploy']['steps']
    names = [step.get('name') for step in steps]
    name = 'Verify operator-created production Prometheus replicas'
    assert (
        names.index('Deploy Prometheus scrape configuration')
        < names.index(name)
        < names.index('Verify deployed egress resources')
    )
    step = steps[names.index(name)]
    assert step['if'] == "github.event.inputs.environment == 'prod'"
    script = step['run']
    assert script.index("wait --for=jsonpath='{.spec.replicas}'=2") < script.index('rollout status')
    assert 'gke_based-hardware_us-central1_prod-omi-gke' in script
    assert 'verify_prometheus_replica_readiness.py' in script
    assert all(flag in script for flag in ['--statefulset-json', '--pods-json', '--pvcs-json'])
