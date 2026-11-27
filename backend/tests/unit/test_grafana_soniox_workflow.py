"""Keep the existing Grafana workflow's Soniox route scoped and reversible."""

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[3] / '.github/workflows/grafana_dashboard_provisioning.yml'


def load_workflow():
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def step_by_name(steps, name):
    return next(step for step in steps if step.get('name') == name)


def test_soniox_scope_is_prod_gated_and_skips_every_dashboard_write():
    workflow = load_workflow()
    inputs = workflow['on']['workflow_dispatch']['inputs']
    job = workflow['jobs']['provision']
    steps = job['steps']

    assert inputs['alert_scope']['options'] == ['all', 'soniox-alert']
    assert inputs['alert_scope']['default'] == 'all'
    assert inputs['alert_operation']['options'] == ['apply', 'restore']
    assert job['environment'] == "${{ matrix.environment == 'prod' && 'prod' || 'development' }}"
    assert job['concurrency']['group'] == 'grafana-alert-provisioning-${{ matrix.environment }}'

    assert step_by_name(steps, 'Provision dashboards')['if'] == "inputs.alert_scope != 'soniox-alert'"
    assert step_by_name(steps, 'Provision private Business board (prod only)')['if'] == (
        "matrix.environment == 'prod' && inputs.alert_scope != 'soniox-alert'"
    )

    full_apply = step_by_name(steps, 'Apply production alert definitions and check drift')
    soniox_apply = step_by_name(steps, 'Apply only the Soniox daily-hours alert')
    assert "inputs.alert_scope != 'soniox-alert'" in full_apply['if']
    assert "inputs.alert_scope == 'soniox-alert'" in soniox_apply['if']
    assert "inputs.alert_operation == 'apply'" in soniox_apply['if']
    assert '--soniox-alert-only' in soniox_apply['run']
    assert 'provision_grafana_dashboards.py' not in str(soniox_apply)
    # Merging only this workflow/helper change must not trigger dashboard applies.
    push_paths = workflow['on']['push']['paths']
    assert '.github/workflows/grafana_dashboard_provisioning.yml' not in push_paths
    assert 'backend/scripts/provision_monitoring_alerts.py' not in push_paths


def test_soniox_restore_uses_the_source_bound_apply_artifact():
    workflow = load_workflow()
    steps = workflow['jobs']['provision']['steps']
    download = step_by_name(steps, 'Download the selected Soniox apply snapshot')
    restore = step_by_name(steps, 'Restore or remove only the Soniox daily-hours alert')
    preserve = step_by_name(steps, 'Preserve pre-apply Soniox alert state for rollback')

    assert download['with']['run-id'] == '${{ inputs.source_run_id }}'
    assert download['with']['name'] == 'grafana-soniox-alert-backup-${{ inputs.source_run_id }}'
    assert download['with']['github-token'] == '${{ secrets.GITHUB_TOKEN }}'
    assert restore['if'] == download['if']
    assert 'restore_soniox_alert.py' in restore['run']
    assert '--expected-source-sha "$SOURCE_SHA"' in restore['run']
    assert '--expected-source-run-id "$SOURCE_RUN_ID"' in restore['run']
    assert '--confirm-soniox-alert-restore' in restore['run']
    assert preserve['with']['name'] == 'grafana-soniox-alert-backup-${{ github.run_id }}'
    assert preserve['with']['if-no-files-found'] == 'error'


def test_soniox_scope_requires_prod_main_and_valid_restore_coordinates():
    workflow = load_workflow()
    validate = step_by_name(workflow['jobs']['validate']['steps'], 'Validate alert scope and operation')

    assert 'refs/heads/main' in validate['run']
    assert '"$ENVIRONMENT" == prod' in validate['run']
    assert 'SOURCE_RUN_ID' in validate['run']
    assert 'SOURCE_SHA' in validate['run']
    assert 'soniox-alert-only --lint' in validate['run']
