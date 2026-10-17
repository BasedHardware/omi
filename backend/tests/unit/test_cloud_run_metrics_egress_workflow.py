"""Static ownership contract for the Cloud Run metrics Helm releases.

The egress values are inert until a credentialed workflow installs both the
Cloud Monitoring exporter and the Prometheus scrape configuration.
"""

from pathlib import Path

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


def test_workflow_installs_both_pinned_releases_atomically() -> None:
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
