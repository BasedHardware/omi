"""Offline chart and nested-log alert contracts; no cluster/cloud access."""

import json
from pathlib import Path
import re
import subprocess

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[2]
CHART = BACKEND / 'charts/batch-pipeline-worker'
DEPLOY = BACKEND / 'deploy/record-seal-sweeper'


def render(*args, namespace='prod-omi-backend'):
    result = subprocess.run(
        [
            'helm',
            'template',
            'prod-omi-batch-pipeline-worker',
            str(CHART),
            '-n',
            namespace,
            '-f',
            str(CHART / 'prod_omi_batch-pipeline-worker_values.yaml'),
            '--set-string',
            'image.digest=sha256:' + 'a' * 64,
            *args,
        ],
        capture_output=True,
        text=True,
    )
    return result


def test_ship_on_cpu_cron_reuses_worker_identity_and_image():
    result = render()
    assert result.returncode == 0, result.stderr
    docs = list(filter(None, yaml.safe_load_all(result.stdout)))
    cron = next(doc for doc in docs if doc['kind'] == 'CronJob' and doc['metadata']['name'] == 'record-seal-sweeper')
    assert cron['metadata']['name'] == 'record-seal-sweeper'
    spec = cron['spec']
    assert spec['schedule'] == '*/5 * * * *' and spec['concurrencyPolicy'] == 'Forbid'
    job = spec['jobTemplate']['spec']
    assert job['activeDeadlineSeconds'] == 240 and job['backoffLimit'] == 0
    pod = job['template']['spec']
    worker = next(doc for doc in docs if doc['kind'] == 'Deployment')['spec']['template']['spec']
    assert pod['serviceAccountName'] == worker['serviceAccountName'] == 'batch-pipeline-worker'
    assert pod['containers'][0]['image'] == worker['containers'][0]['image']
    assert pod['containers'][0]['command'] == ['python', 'scripts/record_seal_sweep.py']
    assert pod['restartPolicy'] == 'Never' and pod['automountServiceAccountToken'] is True
    assert 'tolerations' not in pod and 'nodeSelector' not in pod
    assert 'nvidia.com/gpu' not in json.dumps(pod['containers'][0]['resources'])
    assert pod['securityContext']['runAsNonRoot']
    assert pod['containers'][0]['securityContext']['readOnlyRootFilesystem']
    env = {e['name']: e.get('value') for e in pod['containers'][0]['env']}
    assert env['RECORD_SEAL_SWEEPER_MODE'] == 'apply'
    assert env['RECORD_SEAL_SWEEPER_ENABLED'] == 'true'
    assert env['OMI_FIRESTORE_DATA_PLANE_PROJECT'] == 'based-hardware'
    assert env['BATCH_PIPELINE_ENABLED'] == env['BATCH_PIPELINE_WORKER_ENABLED'] == 'false'
    role = next(doc for doc in docs if doc['kind'] == 'Role')
    assert role['rules'] == [{'apiGroups': [''], 'resources': ['pods'], 'verbs': ['list']}]
    binding = next(doc for doc in docs if doc['kind'] == 'RoleBinding')
    assert binding['subjects'] == [
        {'kind': 'ServiceAccount', 'name': 'batch-pipeline-worker', 'namespace': 'prod-omi-backend'}
    ]
    assert len([doc for doc in docs if doc['kind'] == 'ServiceAccount']) == 1
    assert not any(doc['kind'] in {'ClusterRole', 'ClusterRoleBinding'} for doc in docs)


def test_chart_kill_switch_removes_job_and_rbac_and_plan_mode_is_explicit():
    result = render('--set', 'recordSealSweeper.enabled=false,recordSealRepair.enabled=false')
    assert result.returncode == 0
    assert not any(
        doc and doc['kind'] in {'CronJob', 'Role', 'RoleBinding'} for doc in yaml.safe_load_all(result.stdout)
    )
    result = render('--set', 'recordSealSweeper.mode=plan,recordSealSweeper.runtimeEnabled=false')
    assert result.returncode == 0
    cron = next(
        doc
        for doc in yaml.safe_load_all(result.stdout)
        if doc and doc['kind'] == 'CronJob' and doc['metadata']['name'] == 'record-seal-sweeper'
    )
    env = {
        e['name']: e.get('value')
        for e in cron['spec']['jobTemplate']['spec']['template']['spec']['containers'][0]['env']
    }
    assert env['RECORD_SEAL_SWEEPER_MODE'] == 'plan' and env['RECORD_SEAL_SWEEPER_ENABLED'] == 'false'


def test_chart_refuses_wrong_namespace_and_mode():
    assert render(namespace='dev-omi-backend').returncode != 0
    assert render('--set', 'recordSealSweeper.mode=other').returncode != 0
    for stage in ('dev', 'staging'):
        assert (
            yaml.safe_load((CHART / f'{stage}_omi_batch-pipeline-worker_values.yaml').read_text())['recordSealSweeper'][
                'enabled'
            ]
            is False
        )


def _matches(filter_text, message):
    # Decode the Cloud Logging string-literal layer, then evaluate message
    # predicates against an actual inner omi_logging message string.
    terms = re.findall(r'jsonPayload\.message(:|=~)("(?:\\.|[^"\\])*")', filter_text)
    assert terms
    return all(
        (json.loads(literal) in message) if op == ':' else bool(re.search(json.loads(literal), message))
        for op, literal in terms
    )


def test_alert_filters_parse_inner_message_and_never_extract_identifiers():
    metrics = json.loads((DEPLOY / 'log-metrics.json').read_text())
    for metric in metrics:
        assert 'labelExtractors' not in metric
        assert 'jsonPayload.message' in metric['filter']
        assert 'jsonPayload.event' not in metric['filter']
        message = json.dumps(
            {
                'event': 'record_seal_sweep',
                'outcome': 'ok',
                'backlog': 2,
                'oldest_unsealed_seconds': 14401,
                'oldest_unsealed_over_four_hours': True,
            },
            sort_keys=True,
        )
        assert _matches(metric['filter'], message)
        assert not _matches(metric['filter'], json.dumps({'event': 'other', 'outcome': 'ok'}))
        if 'valueExtractor' in metric:
            expression = metric['valueExtractor']
            regex = json.loads(expression[expression.index(',') + 1 : -1].strip())
            assert int(re.search(regex, message).group(1)) in {2, 14401}
    nonempty = next(m for m in metrics if m['name'].endswith('nonempty_runs'))
    assert not _matches(nonempty['filter'], json.dumps({'event': 'record_seal_sweep', 'outcome': 'ok', 'backlog': 0}))
    old = next(m for m in metrics if m['name'].endswith('old_runs'))
    assert not _matches(
        old['filter'],
        json.dumps({'event': 'record_seal_sweep', 'outcome': 'ok', 'oldest_unsealed_over_four_hours': False}),
    )
    policies = json.loads((DEPLOY / 'alert-policies.json').read_text())
    conditions = policies[0]['conditions']
    backlog = conditions[0]['conditionThreshold']
    assert backlog['duration'] == '7200s' and backlog['thresholdValue'] == 0.999
    assert backlog['denominatorFilter'].endswith('omi_record_seal_runs"')
    assert backlog['evaluationMissingData'] == 'EVALUATION_MISSING_DATA_INACTIVE'
    assert backlog['aggregations'] == backlog['denominatorAggregations']
    assert conditions[1]['conditionThreshold']['thresholdValue'] == 0
    assert conditions[2]['conditionAbsent']['duration'] == '1800s'
    bare = policies[1]['conditions'][0]['conditionMatchedLog']['filter']
    for count in (1, 10, 128):
        assert _matches(bare, json.dumps({'event': 'record_seal_sweep', 'bare_token_skips': count}))
    assert not _matches(bare, json.dumps({'event': 'record_seal_sweep', 'bare_token_skips': 0}))
