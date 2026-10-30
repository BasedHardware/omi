"""Offline rendered chart contracts for independent concurrent repair."""

import json

import yaml

from tests.unit.test_record_seal_sweeper_deploy import render, CHART


def documents(*args):
    result = render(*args)
    assert result.returncode == 0, result.stderr
    return {(doc['kind'], doc['metadata']['name']): doc for doc in yaml.safe_load_all(result.stdout) if doc}


def test_independent_job_uses_worker_identity_and_has_separate_deadline():
    docs = documents()
    repair = docs[('CronJob', 'record-seal-repair')]['spec']
    sweep = docs[('CronJob', 'record-seal-sweeper')]['spec']
    assert repair['concurrencyPolicy'] == 'Forbid'
    assert sweep['jobTemplate']['spec']['activeDeadlineSeconds'] == 240
    assert repair['jobTemplate']['spec']['activeDeadlineSeconds'] == 1680
    assert repair['jobTemplate']['spec']['backoffLimit'] == 0
    pod = repair['jobTemplate']['spec']['template']['spec']
    worker = next(doc for (kind, _), doc in docs.items() if kind == 'Deployment')['spec']['template']['spec']
    assert pod['serviceAccountName'] == worker['serviceAccountName']
    assert pod['containers'][0]['image'] == worker['containers'][0]['image']
    assert pod['containers'][0]['command'] == ['python', 'scripts/record_seal_repair_job.py']
    env = {e['name']: e.get('value') for e in pod['containers'][0]['env']}
    assert env['RECORD_SEAL_REPAIR_WORKERS'] == '8'
    assert env['RECORD_SEAL_REPAIR_ROW_SECONDS'] == '240'
    assert env['RECORD_SEAL_REPAIR_ENABLED'] == 'true'
    assert env['RECORD_SEAL_REPAIR_MODE'] == 'apply'
    assert json.loads(env['RECORD_SEAL_REPAIR_SERVER_FLAGS']) == {}
    assert 'nvidia.com/gpu' not in pod['containers'][0]['resources']['limits']
    assert pod['containers'][0]['securityContext']['readOnlyRootFilesystem']


def test_repair_only_ramp_refresh_changes_no_other_resource():
    before = documents(
        '--set-json',
        'recordSealRepair.serverFlags={"K_SERVICE":"test-role","BATCH_PIPELINE_PERCENT":"0","BATCH_LIVE_STT_RETIRE_PERCENT":"0"}',
    )
    after = documents(
        '--set-json',
        'recordSealRepair.serverFlags={"K_SERVICE":"test-role","BATCH_PIPELINE_PERCENT":"100","BATCH_LIVE_STT_RETIRE_PERCENT":"100"}',
    )
    assert before.keys() == after.keys()
    assert [key for key in before if before[key] != after[key]] == [('CronJob', 'record-seal-repair')]


def test_either_job_keeps_shared_narrow_pod_list_role():
    docs = documents('--set', 'recordSealSweeper.enabled=false')
    assert ('CronJob', 'record-seal-repair') in docs and ('CronJob', 'record-seal-sweeper') not in docs
    assert docs[('Role', 'record-seal-sweeper')]['rules'] == [
        {'apiGroups': [''], 'resources': ['pods'], 'verbs': ['list']}
    ]
    docs = documents('--set', 'recordSealRepair.enabled=false')
    assert ('CronJob', 'record-seal-repair') not in docs and ('Role', 'record-seal-sweeper') in docs
    docs = documents('--set', 'recordSealSweeper.enabled=false,recordSealRepair.enabled=false')
    assert not any(kind in {'CronJob', 'Role', 'RoleBinding'} for kind, _ in docs)


def test_invalid_config_and_nonprod_refuse():
    assert render('--set', 'recordSealRepair.workers=17').returncode != 0
    assert render('--set', 'recordSealRepair.mode=unknown').returncode != 0
    assert render(namespace='dev-omi-backend').returncode != 0
    for stage in ('dev', 'staging'):
        assert (
            yaml.safe_load((CHART / f'{stage}_omi_batch-pipeline-worker_values.yaml').read_text())['recordSealRepair'][
                'enabled'
            ]
            is False
        )


def test_log_metrics_use_only_allowlisted_row_counts_and_numeric_age():
    metrics = json.loads((CHART.parents[1] / 'deploy/record-seal-repair/log-metrics.json').read_text())
    rows = next(metric for metric in metrics if metric['name'].endswith('_rows'))
    assert rows['labelExtractors'] == {'disposition': 'EXTRACT(jsonPayload.disposition)'}
    assert rows['valueExtractor'] == 'EXTRACT(jsonPayload.count)'
    assert all('resource.labels.container_name="repair"' in metric['filter'] for metric in metrics)
    assert all('jsonPayload.event=' in metric['filter'] for metric in metrics)
    assert [metric['valueExtractor'] for metric in metrics[1:]] == [
        'EXTRACT(jsonPayload.seal_age_seconds)',
        'EXTRACT(jsonPayload.oldest_unsealed_seconds)',
    ]
