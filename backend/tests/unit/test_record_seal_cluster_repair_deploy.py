"""Offline rendered chart contracts for independent concurrent repair."""

import json
from pathlib import Path
import re
import subprocess

import yaml
from utils.batch_pipeline.record_seal_reasons import PROOF_REASONS

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
    assert env['RECORD_SEAL_REPAIR_ROW_SECONDS'] == '270'
    assert env['RECORD_SEAL_REPAIR_ENABLED'] == 'true'
    assert env['RECORD_SEAL_OVERLAP_TRIM_ENABLED'] == 'true'
    assert env['RECORD_SEAL_UPLOAD_FAILED_REPAIR_ENABLED'] == 'true'
    assert env['RECORD_SEAL_REPAIR_MODE'] == 'apply'
    assert json.loads(env['RECORD_SEAL_REPAIR_SERVER_FLAGS']) == {}
    assert 'nvidia.com/gpu' not in pod['containers'][0]['resources']['limits']
    assert pod['containers'][0]['securityContext']['readOnlyRootFilesystem']


def test_seal_rules_have_independent_chart_rollback_switches():
    docs = documents(
        '--set', 'recordSealRules.overlapTrimEnabled=false', '--set', 'recordSealRules.uploadFailedRepairEnabled=false'
    )

    def env(name):
        container = docs[('CronJob', name)]['spec']['jobTemplate']['spec']['template']['spec']['containers'][0]
        return {e['name']: e.get('value') for e in container['env']}

    assert env('record-seal-repair')['RECORD_SEAL_OVERLAP_TRIM_ENABLED'] == 'false'
    assert env('record-seal-repair')['RECORD_SEAL_UPLOAD_FAILED_REPAIR_ENABLED'] == 'false'
    assert env('record-seal-sweeper')['RECORD_SEAL_OVERLAP_TRIM_ENABLED'] == 'false'
    assert 'RECORD_SEAL_UPLOAD_FAILED_REPAIR_ENABLED' not in env('record-seal-sweeper')


def test_cpu_admission_switch_is_declared_in_runtime_manifest_and_listen_chart():
    backend = Path(__file__).resolve().parents[2]
    manifest = yaml.load((backend / 'deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    key = 'RECORD_SEAL_OVERLAP_TRIM_ENABLED'
    for stage, config in manifest['environments'].items():
        assert config['gke']['backend-listen']['env'][key]['value'] == 'true'
        assert config['gke']['pusher']['env'][key]['value'] == 'true'
        for service in config['cloud_run']['services'].values():
            assert service['env'][key]['value'] == 'true'
        values = backend / f'charts/backend-listen/{stage}_omi_backend_listen_values.yaml'
        entries = yaml.load(values.read_text(), Loader=yaml.CSafeLoader)['env']
        assert next(e for e in entries if e['name'] == key)['value'] == 'true'
        rendered = subprocess.run(
            [
                'helm',
                'template',
                'sealrules-test',
                str(backend / 'charts/backend-listen'),
                '-f',
                str(values),
                '--set-string',
                'image.tag=synthetic',
                '--set-string',
                f'privateEnv.{key}=false',
            ],
            capture_output=True,
            text=True,
        )
        assert rendered.returncode == 0
        deployment = next(
            d for d in yaml.load_all(rendered.stdout, Loader=yaml.CSafeLoader) if d and d['kind'] == 'Deployment'
        )
        entries = deployment['spec']['template']['spec']['containers'][0]['env']
        assert [e['value'] for e in entries if e['name'] == key] == ['false']
        pusher_values = backend / f'charts/pusher/{stage}_omi_pusher_values.yaml'
        pusher_entries = yaml.load(pusher_values.read_text(), Loader=yaml.CSafeLoader)['env']
        assert next(e for e in pusher_entries if e['name'] == key)['value'] == 'true'


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

    def extract(expression, message):
        assert expression.startswith('REGEXP_EXTRACT(jsonPayload.message, ')
        pattern = json.loads(expression.split(', ', 1)[1][:-1])
        return re.search(pattern, json.dumps(message)).group(1)

    assert list(rows['labelExtractors']) == ['disposition']
    assert extract(rows['labelExtractors']['disposition'], {'disposition': 'privacy_refused'}) == 'privacy_refused'
    assert extract(rows['valueExtractor'], {'count': 1}) == '1'
    assert all('resource.labels.container_name="repair"' in metric['filter'] for metric in metrics)
    assert all('jsonPayload.logger="record-seal-repair"' in metric['filter'] for metric in metrics)
    assert all('jsonPayload.message' in metric['filter'] for metric in metrics)
    assert extract(metrics[1]['valueExtractor'], {'seal_age_seconds': 1801}) == '1801'
    assert extract(metrics[2]['valueExtractor'], {'oldest_unsealed_seconds': 1802}) == '1802'
    proof = next(metric for metric in metrics if metric['name'].endswith('_proof_refused'))
    assert list(proof['labelExtractors']) == ['proof_reason']
    assert 'proof_refused' in proof['filter']
    for reason in PROOF_REASONS:
        assert extract(proof['labelExtractors']['proof_reason'], {'proof_reason': reason}) == reason
    expression = proof['labelExtractors']['proof_reason']
    pattern = json.loads(expression.split(', ', 1)[1][:-1])
    for private in ('A' * 28, 'private@example.invalid', 'users/private/conversations/private', 'other_private'):
        assert re.search(pattern, json.dumps({'proof_reason': private})) is None

    from utils.batch_pipeline.record_seal_reasons import TAIL_GAP_BUCKETS

    gap = next(metric for metric in metrics if metric['name'].endswith('_tail_gap'))
    assert list(gap['labelExtractors']) == ['tail_gap_bucket']
    assert 'proof_refused' in gap['filter'] and 'tail_lagging' in gap['filter']
    assert extract(gap['valueExtractor'], {'count': 1}) == '1'
    for bucket in TAIL_GAP_BUCKETS:
        assert extract(gap['labelExtractors']['tail_gap_bucket'], {'tail_gap_bucket': bucket}) == bucket
    pattern = json.loads(gap['labelExtractors']['tail_gap_bucket'].split(', ', 1)[1][:-1])
    for private in ('A' * 28, 'private@example.invalid', 'users/private/conversations/private', 'under_1s_private'):
        assert re.search(pattern, json.dumps({'tail_gap_bucket': private})) is None
