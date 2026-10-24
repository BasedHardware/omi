"""Batch capacity cannot share live GPUs; HPA and imports use real delivery paths."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from scripts import runtime_image_contracts as images

ROOT = Path(__file__).resolve().parents[3]
CHART = ROOT / 'backend/charts/diarizer'


def rendered(batch):
    command = [
        'helm',
        'template',
        'prod-omi-diarizer-batch' if batch else 'prod-omi-diarizer',
        str(CHART),
        '-f',
        str(CHART / 'prod_omi_diarizer_values.yaml'),
        '--set-string',
        'image.tag=contract-test',
    ]
    if batch:
        command += ['-f', str(CHART / 'prod_omi_diarizer_batch_values.yaml')]
    return {o['kind']: o for o in yaml.safe_load_all(subprocess.check_output(command, text=True)) if o}


def test_batch_scheduling_and_resources_are_disjoint_from_embedding():
    batch, live = rendered(True), rendered(False)
    pod = batch['Deployment']['spec']['template']['spec']
    # No gke-nodepool pin: the on-demand pool and its Spot sibling share the
    # service/env labels and omi.ai taints; the autoscaler prefers Spot first.
    assert 'cloud.google.com/gke-nodepool' not in pod['nodeSelector']
    assert pod['nodeSelector'] == {'service': 'diarizer-batch', 'env': 'prod'}
    assert 'affinity' not in pod
    assert {t['key']: t['value'] for t in pod['tolerations']}['omi.ai/diarizer-batch'] == 'true'
    assert live['Deployment']['spec']['template']['spec']['affinity']['nodeAffinity']
    assert all(batch[k]['metadata']['name'] != live[k]['metadata']['name'] for k in batch if k in live)
    assert batch['HorizontalPodAutoscaler']['spec']['minReplicas'] == 1
    assert batch['HorizontalPodAutoscaler']['spec']['maxReplicas'] == 18
    assert live['BackendConfig']['spec']['timeoutSec'] == 30
    assert batch['BackendConfig']['spec']['timeoutSec'] == 900
    assert 'Ingress' not in batch
    route = batch['HTTPRoute']
    assert route['spec']['rules'][0]['matches'][0]['path']['value'] == '/diarizer-batch'
    assert route['spec']['rules'][0]['backendRefs'][0]['name'] == 'prod-omi-diarizer-batch-gw'
    assert batch['GCPBackendPolicy']['spec']['default']['timeoutSec'] == 900


def test_hpa_metric_has_scrape_resource_labels_and_per_pod_adapter_mapping():
    monitoring = ROOT / 'backend/charts/monitoring'
    values = yaml.safe_load((monitoring / 'kube-prometheus-stack/prod_omi_monitoring_values.yaml').read_text())
    scrape = next(
        s
        for s in values['prometheus']['prometheusSpec']['additionalScrapeConfigs']
        if s['job_name'] == 'diarizer-batch-metrics'
    )
    labels = {r['target_label']: r['source_labels'] for r in scrape['relabel_configs'] if 'target_label' in r}
    assert labels == {'namespace': ['__meta_kubernetes_namespace'], 'pod': ['__meta_kubernetes_pod_name']}
    assert any(r.get('regex') == 'prod-omi-diarizer-batch' and r['action'] == 'keep' for r in scrape['relabel_configs'])
    hpa_metric = rendered(True)['HorizontalPodAutoscaler']['spec']['metrics'][0]
    assert hpa_metric['type'] == 'Pods'
    rules = yaml.safe_load((monitoring / 'prometheus-adapter/prod_omi_prometheus_adapter.yaml').read_text())['rules'][
        'custom'
    ]
    rule = next(r for r in rules if r['name']['as'] == hpa_metric['pods']['metric']['name'])
    assert rule['resources']['overrides'] == {'namespace': {'resource': 'namespace'}, 'pod': {'resource': 'pod'}}
    assert 'job="diarizer-batch-metrics"' in rule['seriesQuery'] and 'pod!=""' in rule['seriesQuery']
    assert '<<.LabelMatchers>>' in rule['metricsQuery'] and 'by (<<.GroupBy>>)' in rule['metricsQuery']
    assert 'vector(0)' not in rule['metricsQuery']


@pytest.mark.parametrize('omit_turns', [False, True])
def test_registry_import_probe_uses_copied_sources_and_rejects_missing_turn_module(tmp_path, omit_turns):
    contract = images.contract_for_name(images.load_contracts(), 'diarizer')
    assert contract.image_import_smoke and 'batch_main' in contract.smoke_entrypoints
    images.stage_runtime_sources(contract, tmp_path)
    app = tmp_path  # Canonical staging maps WORKDIR to this root.
    if omit_turns:
        (app / 'utils/stt/diarization_turns.py').unlink()
    # Isolated child: stub native/model deps, never any first-party source. It
    # runs the same registry prelude and entrypoint import as the built image.
    native_stubs = '''
import sys, importlib, types, numpy as np
class Tensor:
    def __init__(self, value): self.value = value
    def unsqueeze(self, dim): return Tensor(np.expand_dims(self.value, dim))
    @property
    def shape(self): return self.value.shape
    def tolist(self): return self.value.tolist()
torch = types.ModuleType('torch')
torch.from_numpy = Tensor
torch.equal = lambda a, b: np.array_equal(a.value, b.value)
audio = types.ModuleType('torchaudio')
audio.load = lambda *a, **k: (_ for _ in ()).throw(AssertionError('file codec invoked'))
pyannote = types.ModuleType('pyannote.audio')
pyannote.Model = type('Model', (), {})
pyannote.Pipeline = type('Pipeline', (), {})
pyannote.Inference = type('Inference', (), {})
sys.modules.update({'torch': torch, 'torchaudio': audio, 'pyannote.audio': pyannote})
'''
    code = native_stubs + f'\nsys.path.insert(0, {str(app)!r})\n' + contract.smoke_prelude + '\n'
    code += '\n'.join(f'importlib.import_module({entry!r})' for entry in contract.smoke_entrypoints)
    result = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, text=True, cwd=tmp_path)
    if omit_turns:
        assert result.returncode != 0
        assert 'utils' in result.stderr and 'ModuleNotFoundError' in result.stderr
    else:
        assert result.returncode == 0, result.stderr


def test_batch_can_pin_a_published_digest_and_rejects_malformed_digest():
    command = [
        'helm',
        'template',
        'prod-omi-diarizer-batch',
        str(CHART),
        '-f',
        str(CHART / 'prod_omi_diarizer_values.yaml'),
        '-f',
        str(CHART / 'prod_omi_diarizer_batch_values.yaml'),
        '--set-string',
        'image.tag=',
        '--set-string',
        'image.digest=sha256:' + 'a' * 64,
    ]
    objects = list(yaml.safe_load_all(subprocess.check_output(command, text=True)))
    deployment = next(o for o in objects if o['kind'] == 'Deployment')
    image = deployment['spec']['template']['spec']['containers'][0]['image']
    assert image == 'gcr.io/based-hardware/diarizer@sha256:' + 'a' * 64
    command[-1] = 'image.digest=latest'
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0 and 'image.digest must be sha256' in result.stderr
