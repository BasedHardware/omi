"""Offline Helm contract: no deployment, dedicated pool and scoped queue age."""

from pathlib import Path
import json
import os
import shutil
import subprocess

import pytest
import yaml

CHART = Path(__file__).resolve().parents[2] / 'charts' / 'batch-pipeline-worker'


def render(*arguments, namespace='synthetic'):
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('Helm unavailable; render check runs on the packaging host')
    # Production sweeps require their real namespace even in offline templates.
    if namespace == 'synthetic' and any('prod_omi_' in arg for arg in arguments):
        namespace = 'prod-omi-backend'
    return subprocess.run(
        [helm, 'template', 'synthetic-worker', str(CHART), '--namespace', namespace, *arguments],
        capture_output=True,
        text=True,
    )


def enabled_arguments():
    return [
        '--set',
        'enabled=true',
        '--set',
        'image.repository=synthetic/worker',
        '--set',
        'image.digest=sha256:' + 'a' * 64,
        '--set',
        'serviceAccountName=synthetic-worker',
        '--set',
        'gcpServiceAccount=synthetic-worker@example.invalid',
        '--set',
        'nodeSelector.env=dev',
        '--set',
        'stage=dev',
        '--set',
        'namespace=batch_pipeline_dev',
        '--set',
        'bucket=synthetic-batch',
        '--set',
        'secretName=synthetic-secret',
        '--set',
        'dataPlaneProject=demo-synthetic',
    ]


@pytest.mark.parametrize('percent,cap', [(0, 200), (10, 17)])
def test_shadow_settings_render_for_the_leads_activation(percent, cap):
    result = render(
        *enabled_arguments(),
        '--set',
        f'worker.shadowPercent={percent}',
        '--set',
        f'worker.shadowPaidRecoveryPerHour={cap}',
    )
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc.get('kind') == 'Deployment')
    env = {
        entry['name']: entry.get('value') for entry in deployment['spec']['template']['spec']['containers'][0]['env']
    }
    assert env['BATCH_PIPELINE_SHADOW_PERCENT'] == str(percent)
    assert env['BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR'] == str(cap)


def test_default_chart_has_no_resources_or_admission():
    values = yaml.safe_load((CHART / 'values.yaml').read_text())
    assert values['enabled'] is False and values['autoscaling']['minReplicas'] == 1
    assert values['autoscaling']['enabled'] is False
    assert values['podMonitoring']['enabled'] is True
    assert values['worker']['batchSize'] == 8
    assert values['worker']['shardSpreadEnabled'] is True
    assert values['worker']['workerSilenceDispositionEnabled'] is False
    assert values['worker']['workerValidationDispositionEnabled'] is True
    assert values['worker']['diarizeSpeechOnlyEnabled'] is True
    assert 'shortSpeechSingleEnabled' not in values['worker']
    assert values['resources']['requests']['memory'] == '12Gi'
    assert values['resources']['limits']['memory'] == '14Gi'
    result = render()
    assert result.returncode == 0 and list(yaml.safe_load_all(result.stdout)) == []


def test_enabled_chart_pins_gpu_pool_image_and_age_autoscaling():
    result = render(*enabled_arguments(), '--set', 'autoscaling.enabled=true')
    assert result.returncode == 0, result.stderr
    manifests = {doc['kind']: doc for doc in yaml.safe_load_all(result.stdout) if doc}
    pod = manifests['Deployment']['spec']['template']['spec']
    assert pod['nodeSelector'] == {
        'cloud.google.com/gke-nodepool': 'batch-pipeline-pool',
        'service': 'batch-pipeline',
        'env': 'dev',
    }
    assert manifests['Deployment']['spec']['replicas'] == 1
    assert {(item['key'], item['operator'], item['value'], item['effect']) for item in pod['tolerations']} == {
        ('omi.ai/batch-pipeline', 'Equal', 'true', 'NoSchedule'),
        ('nvidia.com/gpu', 'Equal', 'present', 'NoSchedule'),
    }
    assert manifests['ServiceAccount']['metadata']['annotations'] == {
        'iam.gke.io/gcp-service-account': 'synthetic-worker@example.invalid'
    }
    container = pod['containers'][0]
    assert '@sha256:' in container['image']
    assert container['resources']['limits']['nvidia.com/gpu'] == '1'
    env = {v['name']: v.get('value') for v in container['env']}
    soniox = next(v for v in container['env'] if v['name'] == 'SONIOX_API_KEY')
    assert soniox['valueFrom']['secretKeyRef'] == {
        'name': 'synthetic-secret',
        'key': 'SONIOX_API_KEY',
        'optional': True,
    }
    assert env['BATCH_PIPELINE_MODEL_BATCH_SIZE'] == '8'
    assert env['BATCH_PIPELINE_WORKER_IO_CONCURRENCY'] == '5'
    assert env['BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED'] == 'false'
    assert env['BATCH_PIPELINE_FLIGHT_BATCH_SECONDS'] == '1800'
    assert env['BATCH_PIPELINE_ENABLED'] == 'false' and env['BATCH_PIPELINE_PERCENT'] == '0'
    assert env['BATCH_PIPELINE_POOL_KIND'] == 'dedicated_batch'
    assert env['BATCH_PIPELINE_SHARED_LIVE_ENABLED'] == 'false'
    assert env['BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED'] == 'true'
    assert env['BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED'] == 'true'
    assert 'BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED' not in env
    hpa = manifests['HorizontalPodAutoscaler']['spec']
    assert hpa['minReplicas'] == 1 and hpa['behavior']['scaleDown']['stabilizationWindowSeconds'] == 1800
    assert hpa['behavior']['scaleDown']['policies'] == [{'type': 'Pods', 'value': 1, 'periodSeconds': 600}]
    assert len(hpa['metrics']) == 2
    ready, chain = hpa['metrics']
    assert ready['external']['metric']['name'] == 'omi_batch_pipeline_admissible_ready_units'
    assert ready['external']['metric']['selector']['matchLabels'] == {
        'worker_release': 'synthetic-worker',
        'namespace': 'synthetic',
    }
    assert ready['external']['target'] == {'type': 'AverageValue', 'averageValue': '41'}
    assert chain['external']['metric']['name'] == 'omi_batch_pipeline_gpu_chain_busy_seconds'
    assert chain['external']['metric']['selector']['matchLabels'] == {'namespace': 'synthetic'}
    assert chain['external']['target'] == {'type': 'AverageValue', 'averageValue': '0.56'}


def test_enabled_chart_refuses_unpinned_image_and_unsampled_scale_to_zero():
    assert render('--set', 'enabled=true').returncode != 0
    result = render(*enabled_arguments(), '--set', 'autoscaling.enabled=true', '--set', 'autoscaling.minReplicas=0')
    assert result.returncode != 0 and 'independent sampler' in result.stderr


def test_enabled_release_scrapes_but_waits_for_live_series_before_autoscaling():
    result = render(*enabled_arguments())
    assert result.returncode == 0, result.stderr
    manifests = {doc['kind']: doc for doc in yaml.safe_load_all(result.stdout) if doc}
    assert 'HorizontalPodAutoscaler' not in manifests
    assert manifests['Deployment']['spec']['replicas'] == 1
    monitor = manifests['PodMonitoring']['spec']
    assert monitor['selector']['matchLabels']['app.kubernetes.io/instance'] == 'synthetic-worker'
    assert monitor['endpoints'] == [{'port': 'http', 'path': '/metrics', 'interval': '15s'}]
    env = {v['name']: v for v in manifests['Deployment']['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_PIPELINE_WORKER_RELEASE']['value'] == 'synthetic-worker'
    assert env['POD_NAMESPACE']['valueFrom']['fieldRef']['fieldPath'] == 'metadata.namespace'
    assert render(*enabled_arguments(), '--set', 'replicaCount=0').returncode != 0


def test_worker_metrics_are_scraped_into_the_hpa_prometheus():
    """The adapter reads the in-cluster Prometheus, not GMP; without this job
    the omi_batch_pipeline_* external rules match zero series and the worker
    HPA cannot scale (#23891). Mirrors the diarizer-batch-metrics contract."""
    monitoring = CHART.parents[0] / 'monitoring'
    values = yaml.safe_load((monitoring / 'kube-prometheus-stack/prod_omi_monitoring_values.yaml').read_text())
    scrape = next(
        s
        for s in values['prometheus']['prometheusSpec']['additionalScrapeConfigs']
        if s['job_name'] == 'batch-pipeline-worker-metrics'
    )
    keeps = {r['source_labels'][0]: r['regex'] for r in scrape['relabel_configs'] if r.get('action') == 'keep'}
    assert keeps == {
        '__meta_kubernetes_pod_label_app_kubernetes_io_name': 'batch-pipeline-worker',
        '__meta_kubernetes_pod_container_port_name': 'http',
        '__meta_kubernetes_pod_phase': 'Running',
    }
    # The adapter joins freshness on (namespace, worker_release, pod): relabels
    # must preserve namespace+pod, never touch priority/worker_release.
    labels = {r['target_label']: r['source_labels'] for r in scrape['relabel_configs'] if 'target_label' in r}
    assert labels == {
        'namespace': ['__meta_kubernetes_namespace'],
        'pod': ['__meta_kubernetes_pod_name'],
        'service_name': ['__meta_kubernetes_pod_label_service_name'],
    }
    assert 'metric_relabel_configs' not in scrape
    # Freshness cutoff is 60s; 15s keeps two samples in window and matches the
    # chart's GMP PodMonitoring cadence.
    assert scrape['scrape_interval'] == '15s'
    assert scrape['kubernetes_sd_configs'][0]['namespaces']['names'] == ['prod-omi-backend']
    inventory = yaml.safe_load((monitoring / 'expected-targets.prod.yaml').read_text())['scrape_jobs']
    entry = next(job for job in inventory if job['name'] == 'batch-pipeline-worker-metrics')
    assert entry['mechanism'] == 'additionalScrapeConfigs'
    assert entry['namespace'] == 'prod-omi-backend'
    assert entry['auth'] is None and entry['coverage_status'] == 'enforced'
    assert entry['coverage_alert'] == 'omi-scrape-batch-pipeline-worker-metrics'
    assert entry['coverage_modes'] == ['down', 'empty']


@pytest.mark.parametrize(
    'environment,stage,namespace,project,bucket,gsa,secret',
    [
        (
            'dev',
            'dev',
            'batch_pipeline_dev',
            'based-hardware',
            'based-hardware-dev-batch-pipeline-staging',
            'batch-pipeline-worker@based-hardware-dev.iam.gserviceaccount.com',
            'dev-omi-backend-secrets',
        ),
        (
            'prod',
            'prod',
            'batch_pipeline_prod',
            'based-hardware',
            'based-hardware-batch-pipeline-staging',
            'batch-pipeline-worker@based-hardware.iam.gserviceaccount.com',
            'prod-omi-backend-secrets',
        ),
    ],
)
def test_environment_values_render_worker_identity_and_gpu_pool(
    environment, stage, namespace, project, bucket, gsa, secret
):
    values = CHART / f'{environment}_omi_batch-pipeline-worker_values.yaml'
    result = render('-f', str(values), '--set-string', 'image.digest=sha256:' + 'b' * 64)
    assert result.returncode == 0, result.stderr
    manifests = {doc['kind']: doc for doc in yaml.safe_load_all(result.stdout) if doc}
    account = manifests['ServiceAccount']['metadata']
    assert account['name'] == 'batch-pipeline-worker'
    assert account['annotations']['iam.gke.io/gcp-service-account'] == gsa

    deployments = [doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment']
    deployment = next(doc for doc in deployments if doc['metadata']['name'] == 'synthetic-worker')
    assert deployment['spec']['progressDeadlineSeconds'] == 2400
    pod = deployment['spec']['template']['spec']
    if environment == 'prod':
        # Borrowing stays off in prod so Parakeet's freed L4s go back to GCE; the
        # T4 sibling ships at zero replicas next to the CPU record-seal worker.
        assert sorted(d['metadata']['name'] for d in deployments) == [
            'record-seal-worker',
            'synthetic-worker',
            'synthetic-worker-t4',
        ]
        assert deployment['spec']['replicas'] == 4  # Preserve the approved live floor for HPA.
        hpa = next(
            doc['spec']
            for doc in yaml.safe_load_all(result.stdout)
            if doc and doc['kind'] == 'HorizontalPodAutoscaler' and doc['metadata']['name'] == 'synthetic-worker'
        )
        assert hpa['minReplicas'] == 4 and hpa['maxReplicas'] == 8
        assert 'omi.ai/required-companion-deployment' not in deployment['metadata'].get('annotations', {})
    else:
        assert len(deployments) == 1 and deployment['spec']['replicas'] == 1
    assert pod['serviceAccountName'] == 'batch-pipeline-worker'
    assert pod['terminationGracePeriodSeconds'] == 1500 and 'priorityClassName' not in pod
    expected_selector = {'service': 'batch-pipeline', 'env': stage}
    if environment in ('dev', 'prod'):  # prod pins OD-first (f05065); dev keeps its pool pin
        expected_selector['cloud.google.com/gke-nodepool'] = 'batch-pipeline-pool'
    assert pod['nodeSelector'] == expected_selector
    assert {(item['key'], item['operator'], item['value'], item['effect']) for item in pod['tolerations']} == {
        ('omi.ai/batch-pipeline', 'Equal', 'true', 'NoSchedule'),
        ('nvidia.com/gpu', 'Equal', 'present', 'NoSchedule'),
    }
    container = pod['containers'][0]
    project_env = {item['name']: item for item in container['env']}
    lever_manifest = json.loads((CHART.parents[1] / 'deploy/firestore_read_levers_manifest.json').read_text())
    integration_levers = lever_manifest['surfaces']['runtime/prod/cloud_run/services/backend-integration']['explicit']
    for candidate in deployments:
        for worker in candidate['spec']['template']['spec']['containers']:
            if worker['name'] != 'worker':
                continue
            worker_env = {item['name']: item.get('value') for item in worker['env']}
            # SCA-1993/SCA-2024: default-off backoff must stay absent from every worker sibling.
            assert 'BATCH_PROJECTION_FINISH_BACKOFF_ENABLED' not in worker_env
            assert 'BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED' not in worker_env
            if environment == 'prod':
                assert worker_env['BATCH_HELD_POLL_SKIP_ENABLED'] == 'true'
                assert json.loads(worker_env['FIRESTORE_READ_LEVERS']) == dict(
                    integration_levers, usage_month_cache=0, usage_month_total=0
                )
            else:
                assert 'BATCH_HELD_POLL_SKIP_ENABLED' not in worker_env
                assert worker_env['FIRESTORE_READ_LEVERS'] == '{}'
    assert project_env['OMI_FIRESTORE_DATA_PLANE_PROJECT']['value'] == project
    assert project_env['OMI_ENV_STAGE']['value'] == stage
    assert project_env['BATCH_PIPELINE_NAMESPACE']['value'] == namespace
    assert project_env['BUCKET_BATCH_PIPELINE']['value'] == bucket
    defaults = yaml.safe_load((CHART / 'values.yaml').read_text())
    environment_values = yaml.safe_load(values.read_text())
    head_priority_enabled = environment_values.get('worker', {}).get(
        'headPriorityEnabled', defaults['worker']['headPriorityEnabled']
    )
    assert project_env['BATCH_PIPELINE_HEAD_PRIORITY_ENABLED']['value'] == str(head_priority_enabled).lower()
    batch_size = environment_values.get('worker', {}).get('batchSize', defaults['worker']['batchSize'])
    assert batch_size == 8
    assert project_env['BATCH_PIPELINE_MODEL_BATCH_SIZE']['value'] == str(batch_size)
    processes = environment_values.get('worker', {}).get('processes', defaults['worker']['processes'])
    assert project_env['BATCH_PIPELINE_WORKER_PROCESSES']['value'] == str(processes)
    # Two processes double the one-process host sizing, inside g2-standard-8.
    sized = ('12Gi', '14Gi', '4') if processes == 1 else ('24Gi', '26Gi', '6')
    assert (
        container['resources']['requests']['memory'],
        container['resources']['limits']['memory'],
        container['resources']['requests']['cpu'],
    ) == sized
    assert container['resources']['limits']['cpu'] == '8'
    assert container['resources']['requests']['nvidia.com/gpu'] == '1'
    assert container['resources']['limits']['nvidia.com/gpu'] == '1'
    for name in ('ENCRYPTION_SECRET', 'HUGGINGFACE_TOKEN'):
        assert project_env[name]['valueFrom']['secretKeyRef']['name'] == secret
    project_id = 'based-hardware-dev' if environment == 'dev' else 'based-hardware'
    assert container['image'] == f"gcr.io/{project_id}/batch-pipeline-worker@sha256:{'b' * 64}"
    assert ('HorizontalPodAutoscaler' in manifests) == (environment == 'prod')


def test_balanced_pools_have_distinct_ownership_and_shared_fresh_queue_scope():
    result = render(
        *enabled_arguments(),
        '--set',
        'autoscaling.enabled=true,autoscaling.balancedPools.enabled=true,autoscaling.minReplicas=2,autoscaling.maxReplicas=24,worker.stageProfilingEnabled=true',
    )
    assert result.returncode == 0, result.stderr
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    deployments = {d['metadata']['name']: d for d in docs if d['kind'] == 'Deployment'}
    hpas = {d['metadata']['name']: d for d in docs if d['kind'] == 'HorizontalPodAutoscaler'}
    monitors = {d['metadata']['name']: d for d in docs if d['kind'] == 'PodMonitoring'}
    assert deployments.keys() == hpas.keys() == monitors.keys() == {'synthetic-worker', 'synthetic-worker-spot'}
    for name, pool in [
        ('synthetic-worker', 'batch-pipeline-pool'),
        ('synthetic-worker-spot', 'batch-pipeline-pool-spot'),
    ]:
        d, h, monitor = deployments[name], hpas[name]['spec'], monitors[name]['spec']
        pod = d['spec']['template']
        assert d['spec']['selector']['matchLabels'] == monitor['selector']['matchLabels']
        assert pod['metadata']['labels'] == {
            **d['spec']['selector']['matchLabels'],
            'service_name': 'batch-pipeline-worker',
        }
        assert pod['metadata']['labels']['app.kubernetes.io/instance'] == name
        assert pod['spec']['nodeSelector']['cloud.google.com/gke-nodepool'] == pool
        assert 'topologySpreadConstraints' not in pod['spec']
        assert d['spec']['strategy']['type'] == 'Recreate'
        assert pod['spec']['terminationGracePeriodSeconds'] == 1500
        env = {v['name']: v.get('value') for v in pod['spec']['containers'][0]['env']}
        assert env['BATCH_PIPELINE_WORKER_RELEASE'] == 'synthetic-worker'
        assert env['BATCH_PIPELINE_STAGE_PROFILING_ENABLED'] == 'true'
        assert env['BATCH_PIPELINE_PERCENT'] == '0'
        assert h['scaleTargetRef']['name'] == name
        assert h['minReplicas'] == 1 and h['maxReplicas'] == 12
        assert h['behavior']['scaleDown']['stabilizationWindowSeconds'] == 1800
        assert len(h['metrics']) == 2
        ready, chain = h['metrics']
        ready_labels = ready['external']['metric']['selector']['matchLabels']
        assert ready_labels == {'worker_release': 'synthetic-worker', 'namespace': 'synthetic'}
        assert ready['external']['metric']['name'] == 'omi_batch_pipeline_admissible_ready_units'
        chain_labels = chain['external']['metric']['selector']['matchLabels']
        # Stage timers export only the stage label, so the chain metric scopes
        # by namespace alone; requiring worker_release would match zero series.
        assert chain_labels == {'namespace': 'synthetic'}
        assert chain['external']['metric']['name'] == 'omi_batch_pipeline_gpu_chain_busy_seconds'
        # Both pool deployments export the same worker_release and one
        # namespace's chain metric covers the whole fleet, so both targets
        # double: each pool HPA buys half of either demand instead of buying
        # it twice.
        assert ready['external']['target'] == {'type': 'AverageValue', 'averageValue': '82'}
        assert chain['external']['target'] == {'type': 'AverageValue', 'averageValue': '1.12'}
    assert (
        deployments['synthetic-worker']['metadata']['annotations']['omi.ai/required-companion-deployment']
        == 'synthetic-worker-spot'
    )


@pytest.mark.parametrize(
    'setting',
    [
        'autoscaling.enabled=false',
        'autoscaling.minReplicas=1',
        'autoscaling.minReplicas=3',
        'autoscaling.maxReplicas=23',
        'autoscaling.maxReplicas=0',
        'autoscaling.balancedPools.spotNodePool=batch-pipeline-pool',
        'autoscaling.targetQueuedUnitsPerWorker=0',
        'autoscaling.targetChainBusyPerWorker=0',
        'autoscaling.targetChainBusyPerWorker=1.5',
    ],
)
def test_balanced_pools_refuse_unsafe_or_ambiguous_budgets(setting):
    result = render(
        *enabled_arguments(),
        '--set',
        'autoscaling.enabled=true,autoscaling.balancedPools.enabled=true',
        '--set',
        setting,
    )
    assert result.returncode != 0


@pytest.mark.parametrize('min_replicas', [3, 4])
def test_production_values_refuse_balanced_pools_even_with_replica_override(min_replicas):
    # Lead f05065 (10-28): production only uses one OD-pinned HPA. The explicit
    # production guard must also reject an even min override that would split
    # the OD floor below three when Spot is unavailable.
    result = render(
        '-f',
        str(CHART / 'prod_omi_batch-pipeline-worker_values.yaml'),
        '--set-string',
        'image.digest=sha256:' + 'b' * 64,
        '--set',
        f'autoscaling.enabled=true,autoscaling.balancedPools.enabled=true,autoscaling.minReplicas={min_replicas}',
    )
    assert result.returncode != 0
    assert 'production requires a single OD-pinned HPA' in result.stderr


def test_production_release_namespace_refuses_balanced_pools_with_dev_values():
    # The deploy workflow installs production releases into prod-omi-backend;
    # changing both chart values to dev must not bypass the release namespace guard.
    result = render(
        *enabled_arguments(),
        '--set',
        'autoscaling.enabled=true,autoscaling.balancedPools.enabled=true,autoscaling.minReplicas=4',
        namespace='prod-omi-backend',
    )
    assert result.returncode != 0
    assert 'production requires a single OD-pinned HPA' in result.stderr


def render_prod(*extra):
    return render(
        '-f',
        str(CHART / 'prod_omi_batch-pipeline-worker_values.yaml'),
        '--set-string',
        'image.digest=sha256:' + 'b' * 64,
        '--set',
        'borrowedNodePools.enabled=true',
        *extra,
    )


def by_name(docs, kind):
    return {d['metadata']['name']: d for d in docs if d['kind'] == kind}


def test_production_cutover_preserves_live_single_od_hpa_min4_max8():
    # The approved live shape (2026-11-06, David D4 / bc18db): one HPA pinned
    # to the on-demand pool, GPU floor 4 to ceiling 8; no -spot deployment.
    # The floor is config: replicaCount and minReplicas move together.
    # The stockout borrower (below) is extra and never part of this floor.
    values = yaml.safe_load((CHART / 'prod_omi_batch-pipeline-worker_values.yaml').read_text())
    assert values['replicaCount'] == values['autoscaling']['minReplicas'] == 4
    result = render_prod()
    assert result.returncode == 0, result.stderr
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    hpas = by_name(docs, 'HorizontalPodAutoscaler')
    assert hpas['synthetic-worker']['spec']['minReplicas'] == 4
    assert hpas['synthetic-worker']['spec']['maxReplicas'] == 8
    assert not [name for name in hpas if name.endswith('-spot')]
    pod = by_name(docs, 'Deployment')['synthetic-worker']['spec']['template']['spec']
    assert pod['nodeSelector']['cloud.google.com/gke-nodepool'] == 'batch-pipeline-pool'
    assert pod['terminationGracePeriodSeconds'] == 1500
    assert 'affinity' not in pod and 'priorityClassName' not in pod
    # The T4 stockout fallback ships at zero replicas with no HPA.
    assert by_name(docs, 'Deployment')['synthetic-worker-t4']['spec']['replicas'] == 0
    assert 'synthetic-worker-t4' not in hpas
    # Prod L4 workers run two pump processes; the T4 sibling stays at one.
    for name, processes in (('synthetic-worker', '2'), ('synthetic-worker-t4', '1')):
        container = by_name(docs, 'Deployment')[name]['spec']['template']['spec']['containers'][0]
        env = {v['name']: v.get('value') for v in container['env']}
        assert env['BATCH_PIPELINE_WORKER_PROCESSES'] == processes
        # Three pump lanes per process on L4; the slower T4 sibling keeps two.
        assert env['BATCH_PIPELINE_WORKER_PIPELINE_DEPTH'] == ('3' if processes == '2' else '2')


PROD_BORROWED = ['parakeet-pool', 'parakeet-pool-b', 'parakeet-pool-v2']


def test_prod_borrower_runs_only_on_parakeet_nodes_and_yields_fast():
    # L4 stockout (l4capacity 2026-11-01): nodes Parakeet frees go to borrower
    # workers instead of back to GCE. Parakeet (no class, priority 0) preempts a
    # borrower, which must release the GPU in minutes, not the OD 1500s drain.
    result = render_prod()
    assert result.returncode == 0, result.stderr
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    [priority_class] = [d for d in docs if d['kind'] == 'PriorityClass']
    assert -10 <= priority_class['value'] < 0  # Below default pods; not autoscaler-expendable.
    assert priority_class['preemptionPolicy'] == 'Never' and priority_class['globalDefault'] is False

    borrow = by_name(docs, 'Deployment')['synthetic-worker-borrow']
    pod = borrow['spec']['template']['spec']
    assert borrow['spec']['strategy']['type'] == 'Recreate' and borrow['spec']['replicas'] == 1
    assert pod['priorityClassName'] == priority_class['metadata']['name'] == 'synthetic-worker-borrower'
    assert pod['terminationGracePeriodSeconds'] == 120
    [term] = pod['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms']
    assert term['matchExpressions'] == [
        {'key': 'cloud.google.com/gke-nodepool', 'operator': 'In', 'values': PROD_BORROWED}
    ]
    assert pod['nodeSelector'] == {'env': 'prod'}
    # Parakeet nodes carry only the nvidia.com/gpu taint, which the worker already tolerates.
    assert ('nvidia.com/gpu', 'present') in {(t['key'], t['value']) for t in pod['tolerations']}
    env = {v['name']: v.get('value') for v in pod['containers'][0]['env']}
    assert env['BATCH_PIPELINE_WORKER_RELEASE'] == 'synthetic-worker'  # Same queue metric scope as OD.

    hpa = by_name(docs, 'HorizontalPodAutoscaler')['synthetic-worker-borrow']['spec']
    od_hpa = by_name(docs, 'HorizontalPodAutoscaler')['synthetic-worker']['spec']
    assert (hpa['minReplicas'], hpa['maxReplicas']) == (1, 3)
    assert hpa['metrics'] == od_hpa['metrics']
    assert 'synthetic-worker-borrow' in by_name(docs, 'PodMonitoring')
    # Parakeet itself never gets a class, so it keeps priority 0 over borrowers.
    parakeet = yaml.safe_load((CHART.parent / 'parakeet' / 'prod_omi_parakeet_values.yaml').read_text())
    assert not parakeet.get('priorityClassName')


def test_borrowing_off_renders_exactly_the_od_worker():
    on = [doc for doc in yaml.safe_load_all(render_prod().stdout) if doc]
    result = render_prod('--set', 'borrowedNodePools.enabled=false')
    assert result.returncode == 0, result.stderr
    off = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    assert not [d for d in off if d['kind'] == 'PriorityClass']
    assert set(by_name(off, 'Deployment')) == {'synthetic-worker', 'synthetic-worker-t4', 'record-seal-worker'}
    assert set(by_name(off, 'HorizontalPodAutoscaler')) == {'synthetic-worker', 'record-seal-worker'}
    assert by_name(off, 'Deployment')['synthetic-worker'] == by_name(on, 'Deployment')['synthetic-worker']


@pytest.mark.parametrize(
    'overrides,message',
    [
        (['borrowedNodePools.pools={batch-pipeline-pool-spot}'], 'other on-demand pools'),
        (['borrowedNodePools.pools={batch-pipeline-pool}'], 'other on-demand pools'),
        (['borrowedNodePools.pools=null'], 'non-empty pools list'),
        (['autoscaling.enabled=false'], 'needs autoscaling'),
        (['borrowedNodePools.terminationGracePeriodSeconds=1500'], 'must be in [1, 300]'),
        (['borrowedNodePools.maxReplicas=0'], 'maxReplicas must be >= 1'),
        (['borrowedNodePools.priority=0'], 'must be in [-10, 0)'),
        (['borrowedNodePools.priority=-11'], 'must be in [-10, 0)'),
    ],
)
def test_borrowing_rejects_unsafe_shapes(overrides, message):
    arguments = []
    for override in overrides:
        arguments += ['--set', override]
    result = render_prod(*arguments)
    assert result.returncode != 0 and message in result.stderr


@pytest.mark.parametrize('service,timeout', [('batch-pipeline-worker', '2400s'), ('diarizer', '600s')])
@pytest.mark.parametrize('rollout_exit', [0, 1])
def test_rollout_wait_covers_worker_startup_and_still_fails_on_timeout(tmp_path, service, timeout, rollout_exit):
    workflow = yaml.safe_load((CHART.parents[2] / '.github/workflows/gcp_diarizer.yml').read_text())
    step = next(step for step in workflow['jobs']['deploy']['steps'] if step.get('name') == 'Verify rollout')
    receipt = tmp_path / 'kubectl-arguments'
    kubectl = tmp_path / 'kubectl'
    kubectl.write_text('#!/bin/sh\n[ "$3" = get ] && exit 0\nprintf "%s\\n" "$@" > "$RECEIPT"\nexit "$ROLLOUT_EXIT"\n')
    kubectl.chmod(0o755)
    reporter = tmp_path / 'python3'
    reporter.write_text('#!/bin/sh\nexit 0\n')
    reporter.chmod(0o755)
    result = subprocess.run(
        ['bash', '-e', '-c', step['run']],
        env={
            **os.environ,
            'PATH': f'{tmp_path}:{os.environ["PATH"]}',
            'SERVICE': service,
            'DEPLOY_NAMESPACE': 'synthetic',
            'DEPLOY_ENV': 'dev',
            'TARGET_RELEASE': f'synthetic-{service}',
            'RECEIPT': str(receipt),
            'ROLLOUT_EXIT': str(rollout_exit),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == rollout_exit, result.stderr
    assert receipt.read_text().splitlines() == [
        '-n',
        'synthetic',
        'rollout',
        'status',
        f'deploy/synthetic-{service}',
        f'--timeout={timeout}',
    ]


@pytest.mark.parametrize('deployed_digest,expected_exit', [('a' * 64, 0), ('f' * 64, 1)])
def test_rollout_verify_requires_the_built_digest(tmp_path, deployed_digest, expected_exit):
    workflow = yaml.safe_load((CHART.parents[2] / '.github/workflows/gcp_diarizer.yml').read_text())
    deploy = workflow['jobs']['deploy']
    step = next(step for step in deploy['steps'] if step.get('name') == 'Verify rollout')
    # 2026-10-20: the job ran 47 min with no verdict; every layer must now be bounded.
    assert deploy['timeout-minutes'] >= step['timeout-minutes'] > 2400 / 60
    kubectl = tmp_path / 'kubectl'
    kubectl.write_text(
        '#!/bin/sh\ncase "$3" in rollout) exit 0;; get) printf "gcr.io/p/w@sha256:%s" "$DEPLOYED";; esac\n'
    )
    kubectl.chmod(0o755)
    reporter = tmp_path / 'python3'
    reporter.write_text('#!/bin/sh\nexit 0\n')
    reporter.chmod(0o755)
    result = subprocess.run(
        ['bash', '-e', '-c', step['run']],
        env={
            **os.environ,
            'PATH': f'{tmp_path}:{os.environ["PATH"]}',
            'SERVICE': 'batch-pipeline-worker',
            'DEPLOY_NAMESPACE': 'synthetic',
            'DEPLOY_ENV': 'dev',
            'TARGET_RELEASE': 'synthetic-batch-pipeline-worker',
            'EXPECTED_DIGEST': 'sha256:' + 'a' * 64,
            'DEPLOYED': deployed_digest,
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected_exit, result.stdout + result.stderr


def test_production_worker_refuses_missing_or_mismatched_policy_binding():
    values = CHART / 'prod_omi_batch-pipeline-worker_values.yaml'
    args = ['-f', str(values), '--set-string', 'image.digest=sha256:' + 'c' * 64]
    for override in ['worker.apiUrl=', 'worker.apiUrl=http://insecure.invalid', 'worker.audience=wrong']:
        result = render(*args, '--set-string', override)
        assert result.returncode != 0 and 'matching OIDC audience' in result.stderr


def test_production_worker_policy_binding_matches_accepted_identity():
    values = CHART / 'prod_omi_batch-pipeline-worker_values.yaml'
    config = yaml.safe_load(values.read_text())
    assert config['image']['digest'] == ''  # Workflow supplies the built prod digest.
    result = render('-f', str(values), '--set-string', 'image.digest=sha256:' + 'c' * 64)
    assert result.returncode == 0, result.stderr
    # The OD worker: the stockout borrower is a second `-borrow` Deployment/HPA
    # and the T4 fallback a zero-replica `-t4` Deployment.
    docs = {
        doc['kind']: doc
        for doc in yaml.safe_load_all(result.stdout)
        if doc
        and not doc['metadata']['name'].endswith(('-borrow', '-t4'))
        and doc['metadata']['name'] != 'record-seal-worker'
    }
    env = {e['name']: e.get('value') for e in docs['Deployment']['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_PIPELINE_WORKER_ENABLED'] == 'true'
    assert env['BATCH_PIPELINE_ENABLED'] == 'false'
    assert env['BATCH_PIPELINE_API_URL'] == config['worker']['apiUrl'] == config['worker']['audience']
    assert env['BATCH_PIPELINE_WORKER_AUDIENCE'] == config['worker']['audience']
    assert docs['Deployment']['spec']['replicas'] == 4  # Keep the HPA floor through Helm upgrades.
    hpa = docs['HorizontalPodAutoscaler']['spec']
    assert hpa['minReplicas'] == 4 and hpa['maxReplicas'] == 8


@pytest.mark.parametrize('enabled', [False, True])
def test_empty_asr_disposition_is_explicitly_dark_and_operator_enabled(enabled):
    result = render(*enabled_arguments(), '--set', f'worker.emptyAsrDispositionEnabled={str(enabled).lower()}')
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    env = {row['name']: row.get('value') for row in deployment['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED'] == str(enabled).lower()


@pytest.mark.parametrize('enabled', [False, True])
def test_worker_silence_disposition_flag_renders_explicitly(enabled):
    result = render(*enabled_arguments(), '--set', f'worker.workerSilenceDispositionEnabled={str(enabled).lower()}')
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    env = {v['name']: v.get('value') for v in deployment['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED'] == str(enabled).lower()


def test_worker_validation_disposition_kill_switch_renders_false():
    result = render(*enabled_arguments(), '--set', 'worker.workerValidationDispositionEnabled=false')
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    env = {v['name']: v.get('value') for v in deployment['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED'] == 'false'


@pytest.mark.parametrize(
    'arguments,expected', [((), 'true'), (('--set', 'worker.sharedEmbeddingTrunkEnabled=false'), 'false')]
)
def test_shared_embedding_trunk_ships_on_with_helm_kill_switch(arguments, expected):
    result = render(*enabled_arguments(), *arguments)
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    env = {v['name']: v.get('value') for v in deployment['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_PIPELINE_SHARED_EMBEDDING_TRUNK_ENABLED'] == expected


@pytest.mark.parametrize(
    'value,env_name',
    [
        ('vadSegmentationReuseEnabled', 'BATCH_PIPELINE_VAD_SEGMENTATION_REUSE_ENABLED'),
        ('prepareFlightEnabled', 'BATCH_PIPELINE_PREPARE_FLIGHT_ENABLED'),
        ('asrCudaGraphsEnabled', 'BATCH_PIPELINE_ASR_CUDA_GRAPHS_ENABLED'),
    ],
)
@pytest.mark.parametrize('kill', [False, True])
def test_gpu_efficiency_levers_ship_on_with_helm_kill_switches(value, env_name, kill):
    arguments = ('--set', f'worker.{value}=false') if kill else ()
    result = render(*enabled_arguments(), *arguments)
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    env = {v['name']: v.get('value') for v in deployment['spec']['template']['spec']['containers'][0]['env']}
    assert env[env_name] == ('false' if kill else 'true')


@pytest.mark.parametrize('arguments,expected', [((), 'true'), (('--set', 'worker.shardSpreadEnabled=false'), 'false')])
def test_shard_spread_ships_on_with_helm_kill_switch(arguments, expected):
    result = render(*enabled_arguments(), *arguments)
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    env = {v['name']: v.get('value') for v in deployment['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_SHARD_SPREAD_ENABLED'] == expected


@pytest.mark.parametrize(
    'arguments,expected', [((), 'true'), (('--set', 'worker.pullMultiLeaseEnabled=false'), 'false')]
)
def test_pull_multi_lease_ships_on_with_helm_kill_switch(arguments, expected):
    result = render(*enabled_arguments(), *arguments)
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    env = {v['name']: v.get('value') for v in deployment['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_PULL_MULTI_LEASE_ENABLED'] == expected


@pytest.mark.parametrize(
    'arguments,expected', [((), 'true'), (('--set', 'worker.pullBusyBorrowEnabled=false'), 'false')]
)
def test_pull_busy_borrow_ships_on_with_helm_kill_switch(arguments, expected):
    result = render(*enabled_arguments(), *arguments)
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    env = {v['name']: v.get('value') for v in deployment['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_PULL_BUSY_BORROW_ENABLED'] == expected


@pytest.mark.parametrize('arguments,expected', [((), '2'), (('--set', 'worker.pipelineDepth=1'), '1')])
def test_worker_pipeline_depth_ships_on_with_serial_kill_switch(arguments, expected):
    result = render(*enabled_arguments(), *arguments)
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    env = {v['name']: v.get('value') for v in deployment['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_PIPELINE_WORKER_PIPELINE_DEPTH'] == expected


@pytest.mark.parametrize(
    'arguments,expected,memory',
    [((), '1', ('12Gi', '14Gi')), (('--set', 'worker.processes=2'), '2', ('24Gi', '26Gi'))],
)
def test_worker_processes_default_one_and_two_size_the_pod(arguments, expected, memory):
    result = render(*enabled_arguments(), *arguments)
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    container = deployment['spec']['template']['spec']['containers'][0]
    env = {v['name']: v.get('value') for v in container['env']}
    assert env['BATCH_PIPELINE_WORKER_PROCESSES'] == expected
    assert (container['resources']['requests']['memory'], container['resources']['limits']['memory']) == memory
    assert container['resources']['limits']['nvidia.com/gpu'] == '1'  # Processes share one GPU.
    assert container['ports'] == [{'name': 'http', 'containerPort': 8080}]  # Children stay on loopback.


@pytest.mark.parametrize('count,message', [(0, 'must be in'), (4, 'must be in'), (3, 'processResources.3')])
def test_worker_processes_refuse_unsized_counts(count, message):
    result = render(*enabled_arguments(), '--set', f'worker.processes={count}')
    assert result.returncode != 0 and message in result.stderr


def test_gpu_skip_switches_render_overrides():
    result = render(
        *enabled_arguments(),
        '--set',
        'worker.diarizeSpeechOnlyEnabled=false',
        '--set',
        'worker.shortSpeechSingleEnabled=true',
    )
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    env = {v['name']: v.get('value') for v in deployment['spec']['template']['spec']['containers'][0]['env']}
    assert env['BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED'] == 'false'
    assert 'BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED' not in env


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_worker_dispatch_rollout_defaults_are_dark_and_live_only(environment):
    values = CHART / f'{environment}_omi_batch-pipeline-worker_values.yaml'
    result = render('-f', str(values), '--set-string', 'image.digest=sha256:' + 'd' * 64)
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    env = {row['name']: row.get('value') for row in deployment['spec']['template']['spec']['containers'][0]['env']}
    assert env['STT_CAP_DISPATCH_ENFORCEMENT'] == 'false'
    assert 'LADDER_V1_BUDGET_ENFORCEMENT_ENABLED' not in env
    assert env['STT_CAP_DISPATCH_COHORT'] == ''
    assert env['STT_CAP_DISPATCH_LANES'] == 'live'


def test_worker_dispatch_scope_can_be_bound_without_changing_other_admission():
    result = render(
        *enabled_arguments(),
        '--set',
        'worker.capDispatchEnforcement=true',
        '--set-string',
        'worker.capDispatchCohort=uid:synthetic',
        '--set-string',
        'worker.capDispatchLanes=batch',
        '--set',
        'worker.ladderBudgetEnforcement=true',
    )
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    env = {row['name']: row.get('value') for row in deployment['spec']['template']['spec']['containers'][0]['env']}
    assert env['STT_CAP_DISPATCH_ENFORCEMENT'] == 'true'
    assert 'LADDER_V1_BUDGET_ENFORCEMENT_ENABLED' not in env
    assert env['STT_CAP_DISPATCH_COHORT'] == 'uid:synthetic'
    assert env['STT_CAP_DISPATCH_LANES'] == 'batch'
    assert env['BATCH_PIPELINE_ENABLED'] == 'false'


def test_t4_fallback_is_a_zero_replica_t4_sibling_without_hpa():
    result = render(
        *enabled_arguments(),
        '--set',
        'autoscaling.enabled=true,autoscaling.minReplicas=4,autoscaling.maxReplicas=16,t4Fallback.enabled=true',
    )
    assert result.returncode == 0, result.stderr
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    deployments = {d['metadata']['name']: d for d in docs if d['kind'] == 'Deployment'}
    hpas = {d['metadata']['name'] for d in docs if d['kind'] == 'HorizontalPodAutoscaler'}
    monitors = {d['metadata']['name'] for d in docs if d['kind'] == 'PodMonitoring'}
    assert set(deployments) == monitors == {'synthetic-worker', 'synthetic-worker-t4'}
    assert hpas == {'synthetic-worker'}
    primary, t4 = deployments['synthetic-worker'], deployments['synthetic-worker-t4']
    assert t4['spec']['replicas'] == 0
    pod = t4['spec']['template']
    assert pod['metadata']['labels']['app.kubernetes.io/instance'] == 'synthetic-worker-t4'
    assert pod['metadata']['labels'] == {
        **t4['spec']['selector']['matchLabels'],
        'service_name': 'batch-pipeline-worker',
    }
    assert pod['spec']['nodeSelector'] == {
        **primary['spec']['template']['spec']['nodeSelector'],
        'cloud.google.com/gke-nodepool': 'batch-pipeline-t4-pool',
    }
    assert pod['spec']['tolerations'] == primary['spec']['template']['spec']['tolerations']
    assert pod['spec']['containers'][0]['image'] == primary['spec']['template']['spec']['containers'][0]['image']
    assert t4['spec']['strategy']['type'] == 'Recreate'


@pytest.mark.parametrize(
    't4_setting,t4_expected,t4_memory', [((), '1', '14Gi'), (('--set', 't4Fallback.processes=2'), '2', '26Gi')]
)
def test_t4_fallback_keeps_its_own_process_count(t4_setting, t4_expected, t4_memory):
    # Two model chains are qualified on a 24 GB L4, not a 16 GB T4: the
    # sibling takes t4Fallback.processes, never worker.processes.
    result = render(*enabled_arguments(), '--set', 'worker.processes=2,t4Fallback.enabled=true', *t4_setting)
    assert result.returncode == 0, result.stderr
    deployments = by_name([doc for doc in yaml.safe_load_all(result.stdout) if doc], 'Deployment')

    def shape(name):
        container = deployments[name]['spec']['template']['spec']['containers'][0]
        env = {v['name']: v.get('value') for v in container['env']}
        return env['BATCH_PIPELINE_WORKER_PROCESSES'], container['resources']['limits']['memory']

    assert shape('synthetic-worker') == ('2', '26Gi')
    assert shape('synthetic-worker-t4') == (t4_expected, t4_memory)


def test_t4_fallback_refuses_an_out_of_range_process_count():
    result = render(*enabled_arguments(), '--set', 't4Fallback.enabled=true,t4Fallback.processes=0')
    assert result.returncode != 0 and 'must be in' in result.stderr


@pytest.mark.parametrize('setting', ['t4Fallback.nodePool=batch-pipeline-pool', 't4Fallback.replicas=-1'])
def test_t4_fallback_refuses_the_primary_pool_or_negative_replicas(setting):
    result = render(*enabled_arguments(), '--set', 't4Fallback.enabled=true', '--set', setting)
    assert result.returncode != 0


@pytest.mark.parametrize('pool,accepted', [('primary-od', False), ('primary-spot', False), ('fallback-t4', True)])
def test_t4_fallback_is_distinct_from_every_resolved_balanced_pool(pool, accepted):
    result = render(
        *enabled_arguments(),
        '--set',
        'autoscaling.enabled=true,autoscaling.balancedPools.enabled=true,'
        'autoscaling.minReplicas=4,autoscaling.maxReplicas=16,'
        'autoscaling.balancedPools.onDemandNodePool=primary-od,'
        'autoscaling.balancedPools.spotNodePool=primary-spot,'
        f't4Fallback.enabled=true,t4Fallback.nodePool={pool}',
    )
    if accepted:
        assert result.returncode == 0, result.stderr
        docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
        pod = by_name(docs, 'Deployment')['synthetic-worker-t4']['spec']['template']['spec']
        assert pod['nodeSelector']['cloud.google.com/gke-nodepool'] == pool
    else:
        assert result.returncode != 0
        assert 'must differ from all primary pools' in result.stderr


def test_t4_fallback_is_off_outside_production_values():
    result = render(*enabled_arguments())
    assert result.returncode == 0, result.stderr
    names = [d['metadata']['name'] for d in yaml.safe_load_all(result.stdout) if d and d['kind'] == 'Deployment']
    assert names == ['synthetic-worker']


def test_t4_kill_switch_removes_only_the_sibling():
    on = [doc for doc in yaml.safe_load_all(render_prod().stdout) if doc]
    result = render_prod('--set', 't4Fallback.enabled=false')
    assert result.returncode == 0, result.stderr
    off = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    for kind in ('Deployment', 'PodMonitoring'):
        assert 'synthetic-worker-t4' not in by_name(off, kind)
        assert by_name(off, kind) == {
            name: doc for name, doc in by_name(on, kind).items() if name != 'synthetic-worker-t4'
        }
    assert by_name(on, 'HorizontalPodAutoscaler') == by_name(off, 'HorizontalPodAutoscaler')


@pytest.mark.parametrize(
    'fallback_replicas,expected', [('', []), ('0', []), ('2', ['synthetic-batch-pipeline-worker-t4'])]
)
@pytest.mark.parametrize('failure', ['', 'lookup', 'rollout', 'digest', 'budget'])
def test_rollout_verify_waits_for_a_serving_t4_fallback(tmp_path, fallback_replicas, expected, failure):
    workflow = yaml.safe_load((CHART.parents[2] / '.github/workflows/gcp_diarizer.yml').read_text())
    step = next(step for step in workflow['jobs']['deploy']['steps'] if step.get('name') == 'Verify rollout')
    log = tmp_path / 'rollouts'
    reported = tmp_path / 'reported'
    kubectl = tmp_path / 'kubectl'
    kubectl.write_text(
        '#!/bin/sh\n'
        'case "$3 $4" in\n'
        '  "rollout status") echo "${5#deploy/}" >> "$LOG";\n'
        '    case "$5" in *-t4) [ "$FAILURE" = rollout ] && exit 1;; esac;;\n'
        '  get*) case "$*" in\n'
        '    *spec.replicas*) [ "$FAILURE" = lookup ] && exit 1; printf "%s" "$FALLBACK";;\n'
        '    *-t4*) [ "$FAILURE" = digest ] && printf "wrong-image" || printf "img@sha256:%s" "$DIGEST";;\n'
        '    *) printf "img@sha256:%s" "$DIGEST";; esac;;\n'
        'esac\n'
        'exit 0\n'
    )
    kubectl.chmod(0o755)
    (tmp_path / 'python3').write_text('#!/bin/sh\ntouch "$REPORTED"\n')
    (tmp_path / 'python3').chmod(0o755)
    script = step['run']
    if failure == 'budget':
        # Exercise the deadline without waiting for a real 40-minute rollout.
        script = script.replace('rollout_deadline=$((SECONDS + ${rollout_timeout%s}))', 'rollout_deadline=$SECONDS')
    result = subprocess.run(
        ['bash', '-e', '-c', script],
        env={
            **os.environ,
            'PATH': f'{tmp_path}:{os.environ["PATH"]}',
            'SERVICE': 'batch-pipeline-worker',
            'DEPLOY_NAMESPACE': 'synthetic',
            'DEPLOY_ENV': 'dev',
            'TARGET_RELEASE': 'synthetic-batch-pipeline-worker',
            'EXPECTED_DIGEST': 'sha256:' + 'a' * 64,
            'DIGEST': 'a' * 64,
            'FALLBACK': fallback_replicas,
            'LOG': str(log),
            'FAILURE': failure,
            'REPORTED': str(reported),
        },
        capture_output=True,
        text=True,
    )
    should_fail = failure == 'lookup' or (fallback_replicas == '2' and bool(failure))
    assert result.returncode == int(should_fail), result.stdout + result.stderr
    assert reported.exists() != should_fail
    if failure == 'lookup' or (fallback_replicas == '2' and failure == 'budget'):
        expected = []
    assert log.read_text().splitlines() == ['synthetic-batch-pipeline-worker', *expected]


@pytest.mark.parametrize('rollback', [False, True])
def test_control_loop_defaults_and_value_only_rollback_render(tmp_path, rollback):
    # JSON is a string: Helm cannot deep-merge the enabled key into an empty map.
    overrides = tmp_path / 'rollback.yaml'
    overrides.write_text(
        "worker:\n  controlCandidateFanout: 64\n  admissionParallelCalls: false\n  idlePollMaxSeconds: 2\n  firestoreReadLevers: '{}'\n"
    )
    arguments = ['-f', str(overrides)] if rollback else []
    result = render(*enabled_arguments(), *arguments)
    assert result.returncode == 0, result.stderr
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc.get('kind') == 'Deployment')
    env = {
        entry['name']: entry.get('value') for entry in deployment['spec']['template']['spec']['containers'][0]['env']
    }
    expected = ('64', 'false', '2', '{}') if rollback else ('16', 'true', '10', '{}')
    assert (
        tuple(
            env[key]
            for key in (
                'BATCH_CONTROL_CANDIDATE_FANOUT',
                'BATCH_ADMISSION_PARALLEL_CALLS',
                'BATCH_PIPELINE_IDLE_POLL_MAX_SECONDS',
                'FIRESTORE_READ_LEVERS',
            )
        )
        == expected
    )


@pytest.mark.parametrize('enabled', ['true', 'false'])
def test_held_dead_letter_kill_switch_renders_literal_worker_setting(enabled):
    result = render(*enabled_arguments(), '--set', f'worker.heldDeadLetterEnabled={enabled}')
    assert result.returncode == 0, result.stderr
    deployments = [v for v in yaml.safe_load_all(result.stdout) if v and v.get('kind') == 'Deployment']
    assert deployments
    for deployment in deployments:
        env = deployment['spec']['template']['spec']['containers'][0]['env']
        assert next(v['value'] for v in env if v['name'] == 'BATCH_HELD_DEAD_LETTER_ENABLED') == enabled


@pytest.mark.parametrize('environment', ['default', 'dev'])
def test_worker_default_inheritance_is_reviewed_and_unresolved(environment):
    manifest = json.loads((CHART.parents[1] / 'deploy/firestore_read_levers_manifest.json').read_text())
    surface = manifest['surfaces'][f'chart/{environment}/batch-pipeline-worker']
    assert surface['explicit'] == {}
    assert surface['inheritance']['reason'] == 'intentionally inherits code defaults'
    assert surface['inheritance']['status'] == 'UNRESOLVED'
    assert surface['effective']['batch_timeliness_leader'] == 100


def test_prod_worker_levers_match_backend_integration():
    manifest = json.loads((CHART.parents[1] / 'deploy/firestore_read_levers_manifest.json').read_text())
    worker = manifest['surfaces']['chart/prod/batch-pipeline-worker']
    integration = manifest['surfaces']['runtime/prod/cloud_run/services/backend-integration']
    assert worker['explicit'] == dict(integration['explicit'], usage_month_cache=0, usage_month_total=0)
    assert worker['effective'] == dict(integration['effective'], usage_month_cache=0, usage_month_total=0)
    assert worker['explicit']['bpp_decision_cache'] == 100
    assert 'inheritance' not in worker
