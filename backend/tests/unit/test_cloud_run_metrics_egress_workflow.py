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


def test_workflow_values_exist_for_every_environment() -> None:
    for environment in ('dev', 'prod'):
        assert (EXPORTER_VALUES / f'{environment}_omi_cloud_run_metrics_exporter.yaml').is_file()
        assert (STACK_VALUES / f'{environment}_omi_monitoring_values.yaml').is_file()
