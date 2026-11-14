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
    # Prod runs repair at 16 workers: 48 saturated per-row I/O (2026-11-05, #24729 rolled back).
    assert env['RECORD_SEAL_REPAIR_WORKERS'] == '16'
    assert env['RECORD_SEAL_REPAIR_ROW_SECONDS'] == '270'
    assert env['RECORD_SEAL_REPAIR_ENABLED'] == 'true'
    assert env['RECORD_SEAL_REPAIR_JOBS'] == 'on'
    assert env['RECORD_SEAL_OVERLAP_TRIM_ENABLED'] == 'true'
    assert env['RECORD_SEAL_UPLOAD_FAILED_REPAIR_ENABLED'] == 'true'
    assert env['RECORD_SEAL_REPAIR_MODE'] == 'apply'
    flags = json.loads(env['RECORD_SEAL_REPAIR_SERVER_FLAGS'])
    assert flags == {
        'K_SERVICE': 'backend',
        'BATCH_PIPELINE_ENABLED': 'true',
        'BATCH_PIPELINE_LIVE_ADMISSION_ENABLED': 'false',
        'BATCH_PIPELINE_PERCENT': '100',
        'BATCH_LIVE_STT_RETIRE_PERCENT': '0',
        'TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE': 'true',
        'TRANSCRIPTION_FINAL_PASS_DIARIZER': 'pyannote_shadow',
        'TRANSCRIPTION_FINAL_PASS_PERCENT': '5',
    }
    # UID allowlists hold real account ids and the repo is public: they never live in git.
    assert not any('ALLOWLIST' in key for key in flags)
    assert 'nvidia.com/gpu' not in pod['containers'][0]['resources']['limits']
    assert pod['containers'][0]['securityContext']['readOnlyRootFilesystem']


def test_repair_pod_runs_on_batch_pipeline_pool_with_four_requested_cores():
    pod = documents()[('CronJob', 'record-seal-repair')]['spec']['jobTemplate']['spec']['template']['spec']
    terms = pod['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms']
    assert terms == [
        {
            'matchExpressions': [
                {
                    'key': 'cloud.google.com/gke-nodepool',
                    'operator': 'In',
                    'values': ['batch-pipeline-pool'],
                }
            ]
        }
    ]
    # The pool is tainted; without these the pod never schedules there.
    assert {(t['key'], t['value'], t['effect']) for t in pod['tolerations']} == {
        ('omi.ai/batch-pipeline', 'true', 'NoSchedule'),
        ('nvidia.com/gpu', 'present', 'NoSchedule'),
    }
    resources = pod['containers'][0]['resources']
    # Reserve the full CPU limit. Memory still differs, so pod QoS is Burstable.
    assert resources['requests']['cpu'] == '4'
    assert resources['limits']['cpu'] == '4'
    assert 'nvidia.com/gpu' not in resources['limits']


def test_repair_placement_rolls_back_to_the_old_exclusion_from_values_only():
    pod = documents('--set', 'recordSealRepair.nodePool=', '--set-json', 'recordSealRepair.tolerations=[]')[
        ('CronJob', 'record-seal-repair')
    ]['spec']['jobTemplate']['spec']['template']['spec']
    terms = pod['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms']
    assert terms == [
        {
            'matchExpressions': [
                {'key': 'cloud.google.com/gke-accelerator', 'operator': 'DoesNotExist'},
                {
                    'key': 'cloud.google.com/gke-nodepool',
                    'operator': 'NotIn',
                    'values': ['batch-pipeline-pool', 'batch-pipeline-pool-spot', 'parakeet-pool'],
                },
            ]
        }
    ]
    assert 'tolerations' not in pod


def test_repair_row_process_may_read_precompiled_bytecode():
    pod = documents()[('CronJob', 'record-seal-repair')]['spec']['jobTemplate']['spec']['template']['spec']
    env = {e['name']: e.get('value') for e in pod['containers'][0]['env']}
    # The image precompiles .pyc at build; the row must be allowed to use it.
    assert 'PYTHONDONTWRITEBYTECODE' not in env


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
    docs = documents(
        '--set', 'recordSealSweeper.enabled=false,recordSealRepair.enabled=false,recordSealWorker.enabled=false'
    )
    assert not any(kind in {'CronJob', 'Role', 'RoleBinding'} for kind, _ in docs)


def test_invalid_config_and_nonprod_refuse():
    assert render('--set', 'recordSealRepair.workers=65').returncode != 0
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
    assert 'jsonPayload.message:"\\\"seal_age_seconds\\\""' in metrics[1]['filter']
    assert extract(metrics[2]['valueExtractor'], {'oldest_unsealed_seconds': 1802}) == '1802'
    invalid = next(metric for metric in metrics if metric['name'].endswith('_invalid_clock_rows'))
    assert invalid['filter'] == metrics[2]['filter']
    assert invalid['metricDescriptor'] == {'metricKind': 'DELTA', 'valueType': 'INT64', 'unit': '1'}
    assert extract(invalid['valueExtractor'], {'invalid_clock_rows': 2}) == '2'

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


def test_jobs_discovery_rollback_reaches_only_repair_cron():
    before = documents()
    after = documents('--set-string', 'recordSealRepair.jobsDiscovery=off')
    assert before.keys() == after.keys()
    assert [key for key in before if before[key] != after[key]] == [('CronJob', 'record-seal-repair')]
    container = after[('CronJob', 'record-seal-repair')]['spec']['jobTemplate']['spec']['template']['spec'][
        'containers'
    ][0]
    env = {entry['name']: entry.get('value') for entry in container['env']}
    assert env['RECORD_SEAL_REPAIR_JOBS'] == 'off'


def test_projection_debt_kill_switch_reaches_cron_without_disabling_seal_repair():
    for setting in ('true', 'false'):
        docs = documents('--set', f'recordSealRepair.projectionDebtDurableEnabled={setting}')
        pod = docs[('CronJob', 'record-seal-repair')]['spec']['jobTemplate']['spec']['template']['spec']
        env = {e['name']: e.get('value') for e in pod['containers'][0]['env']}
        assert env['PUSHER_PROJECTION_DEBT_DURABLE_ENABLED'] == setting
        assert env['RECORD_SEAL_REPAIR_ENABLED'] == 'true'


def test_pusher_flag_can_arrive_unshadowed_from_existing_runtime_configmap():
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            'helm',
            'template',
            'projection-debt-test',
            str(backend / 'charts/pusher'),
            '-f',
            str(backend / 'charts/pusher/prod_omi_pusher_values.yaml'),
            '--set-string',
            'image.tag=synthetic',
            '--set-string',
            'image.digest=',
            '--set-string',
            'runtimeConfigMapName=projection-debt-test-config',
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    container = deployment['spec']['template']['spec']['containers'][0]
    assert {'configMapRef': {'name': 'projection-debt-test-config'}} in container['envFrom']
    assert not any(item['name'] == 'PUSHER_PROJECTION_DEBT_DURABLE_ENABLED' for item in container.get('env', []))


def test_worker_deploy_gates_selected_source_before_build_or_helm():
    workflow = yaml.safe_load((Path(__file__).resolve().parents[3] / '.github/workflows/gcp_diarizer.yml').read_text())
    steps = workflow['jobs']['deploy']['steps']
    gate_index, gate = next(
        (i, step) for i, step in enumerate(steps) if step.get('name') == 'Verify serving Firestore indexes'
    )
    assert 'if' not in gate
    assert gate['uses'] == './.github/firestore-workflow/.github/actions/firestore-readiness'
    assert not gate.get('continue-on-error', False)
    assert gate['with']['source_sha'] == '${{ steps.vars.outputs.source_sha }}'
    assert gate['with']['project_id'] == '${{ vars.RUNTIME_GCP_PROJECT_ID }}'
    # The optional worker helper has its own checkout; the Firestore gate owns
    # this path, not whichever step happens to be immediately before the gate.
    control_checkouts = [
        (i, step)
        for i, step in enumerate(steps)
        if step.get('uses', '').startswith('actions/checkout@')
        and step.get('with', {}).get('path') == '.github/firestore-workflow'
    ]
    assert len(control_checkouts) == 1
    controls_index, controls = control_checkouts[0]
    assert controls_index < gate_index
    assert 'if' not in controls
    assert controls['with']['ref'] == '${{ github.workflow_sha }}'
    assert controls['with']['path'] == '.github/firestore-workflow'
    source = next(step for step in steps if step.get('id') == 'vars')
    assert 'source_sha=$(git rev-parse HEAD)' in source['run']
    mutations = [
        i
        for i, step in enumerate(steps)
        if step.get('name') in {'Build and Push Docker image', 'Verify promoted worker digest'}
        or 'upgrade --install' in step.get('run', '')
        or 'worker_image_only.py deploy' in step.get('run', '')
    ]
    assert len(mutations) == 4 and all(i > gate_index for i in mutations)
