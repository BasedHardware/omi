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
    assert scripts.count('helm upgrade --install') == 2
    assert scripts.count('--atomic') == 2
    assert 'prometheus-stackdriver-exporter \\\n  --version 4.8.3' in scripts
    assert 'kube-prometheus-stack \\\n  --version 75.15.1' in scripts
    assert 'kubectl rollout status "deployment/$EXPORTER_RELEASE"' in scripts


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
    assert 'backend/charts/monitoring/live-alert-gate.json' in push_paths


def test_workflow_values_exist_for_every_environment() -> None:
    for environment in ('dev', 'prod'):
        assert (EXPORTER_VALUES / f'{environment}_omi_cloud_run_metrics_exporter.yaml').is_file()
        assert (STACK_VALUES / f'{environment}_omi_monitoring_values.yaml').is_file()
