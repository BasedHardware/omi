"""Keep the Soniox production route scoped and reversible."""

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[3] / '.github/workflows/grafana_soniox_alert.yml'


def test_soniox_workflow_writes_only_one_rule_under_prod_gate():
    workflow = yaml.load(WORKFLOW.resolve().read_text(), Loader=yaml.BaseLoader)
    job = workflow['jobs']['provision-soniox-alert']
    steps = job['steps']
    apply = next(step for step in steps if step.get('name') == 'Apply only the Soniox daily-hours alert')
    restore = next(step for step in steps if step.get('name') == 'Restore or remove only the Soniox daily-hours alert')

    assert job['environment'] == 'prod'
    assert job['concurrency'] == {
        'group': 'grafana-alert-provisioning-prod',
        'cancel-in-progress': 'false',
    }
    assert '--soniox-alert-only' in apply['run']
    assert 'provision_grafana_dashboards.py' not in apply['run']
    assert 'restore_soniox_alert.py' in restore['run']
    assert '--confirm-soniox-alert-restore' in restore['run']
    assert 'provision_grafana_dashboards.py' not in str(job)


def test_restore_download_is_bound_to_the_named_apply_run():
    workflow = yaml.load(WORKFLOW.resolve().read_text(), Loader=yaml.BaseLoader)
    steps = workflow['jobs']['provision-soniox-alert']['steps']
    download = next(step for step in steps if step.get('name') == 'Download the selected apply snapshot')

    assert download['with']['run-id'] == '${{ inputs.source_run_id }}'
    assert download['with']['name'] == 'grafana-soniox-alert-backup-${{ inputs.source_run_id }}'
    assert download['with']['github-token'] == '${{ secrets.GITHUB_TOKEN }}'
