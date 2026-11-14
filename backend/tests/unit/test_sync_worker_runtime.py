"""Idle worker imports, authenticated pulls and bounded chart contracts."""

import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock

import httpx
import pytest
import yaml

from utils.sync import worker_client, worker_runtime

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    'base,audience',
    [
        ('https://synthetic.run.app/path', 'https://synthetic.run.app/path'),
        ('https://api.omi.me', 'https://api.omi.me'),
        ('http://synthetic.run.app', 'http://synthetic.run.app'),
        ('https://synthetic.run.app', 'https://different.run.app'),
        ('https://synthetic.run.app?rig=dev', 'https://synthetic.run.app?rig=dev'),
    ],
)
def test_worker_refuses_nonservice_or_mismatched_endpoint(monkeypatch, base, audience):
    monkeypatch.setenv('SYNC_BACKFILL_WORKER_API_URL', base)
    monkeypatch.setenv('SYNC_BACKFILL_WORKER_AUDIENCE', audience)
    with pytest.raises(ValueError):
        worker_client.worker_endpoint()


async def test_idle_tick_authenticates_and_does_no_pipeline_work(monkeypatch):
    calls = []

    def handle(request):
        calls.append(request)
        assert request.headers['authorization'] == 'Bearer synthetic-token'
        assert json.loads(request.content) == {'stage': 'prod'}
        return httpx.Response(200, json={'lease': None})

    monkeypatch.setattr(worker_client, 'identity_token', lambda _: 'synthetic-token')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        runtime = worker_runtime.Runtime(worker_client.WorkerClient(http, 'https://synthetic.run.app', 'audience'))
        await runtime.tick()
        assert runtime.connected
    assert len(calls) == 1
    assert calls[0].url.path == '/v2/sync-jobs/claim'
    assert 'main' not in sys.modules
    assert 'app_roles' not in sys.modules
    assert 'utils.batch_pipeline.serving' not in sys.modules
    assert 'utils.sync.pipeline' not in sys.modules


async def test_runtime_passes_claim_to_supervisor():
    class Client:
        def __init__(self):
            self.operations = []

        async def call(self, operation, body=None):
            self.operations.append(operation)
            return {'lease': {'payload': {'uid': 'synthetic', 'job_id': 'job', 'sequencer_epoch': 1}, 'token': 't'}}

    client = Client()
    runtime = worker_runtime.Runtime(client)
    runtime.execute = AsyncMock()
    await runtime.tick()
    assert client.operations == ['claim']
    runtime.execute.assert_awaited_once()


async def test_stop_interrupts_idle_wait():
    class Client:
        async def call(self, *args):
            runtime.stop.set()
            return {'lease': None}

    runtime = worker_runtime.Runtime(Client())
    await runtime.run()
    assert runtime.stop.is_set()


async def test_empty_claims_back_off_and_work_resets_poll_interval():
    client = AsyncMock()
    client.call.return_value = {'lease': None}
    runtime = worker_runtime.Runtime(client)
    runtime.execute = AsyncMock()
    for _ in range(8):
        await runtime.tick()
    assert runtime.poll_seconds == 60
    client.call.return_value = {'lease': {'payload': {}}}
    await runtime.tick()
    assert runtime.poll_seconds == worker_runtime.POLL_SECONDS


def render(*extra):
    result = subprocess.run(
        [
            'helm',
            'template',
            'sync-backfill-worker',
            str(ROOT / 'backend/charts/sync-backfill-worker'),
            '--set',
            'image.repository=synthetic/worker',
            '--set',
            'image.digest=sha256:' + 'a' * 64,
            '--set',
            'runtimeSecret=synthetic-runtime',
            '--set',
            'serviceAccount.gcpEmail=worker@synthetic.invalid',
            '--set',
            'worker.apiUrl=https://synthetic.run.app',
            '--set',
            'worker.audience=https://synthetic.run.app',
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result


def test_chart_pins_identity_resources_and_dedicated_entrypoint():
    result = render()
    assert result.returncode == 0, result.stderr
    docs = {doc['kind']: doc for doc in yaml.safe_load_all(result.stdout) if doc}
    deployment = docs['Deployment']['spec']
    pod = deployment['template']['spec']
    container = pod['containers'][0]
    assert deployment['strategy'] == {'type': 'Recreate'}
    assert deployment['replicas'] == 1
    assert pod['terminationGracePeriodSeconds'] == 1500
    assert pod['nodeSelector']['cloud.google.com/gke-nodepool'] == 'sync-backfill-pool'
    assert container['command'] == ['python', '-m', 'utils.sync.worker_runtime']
    assert container['image'].endswith('@sha256:' + 'a' * 64)
    assert container['envFrom'] == [{'secretRef': {'name': 'synthetic-runtime'}}]
    assert next(e for e in container['env'] if e['name'] == 'BATCH_FINAL_PASS_ENABLED') == {
        'name': 'BATCH_FINAL_PASS_ENABLED',
        'valueFrom': {'configMapKeyRef': {'name': 'prod-omi-backend-config', 'key': 'BATCH_FINAL_PASS_ENABLED'}},
    }
    assert set(docs) == {'ServiceAccount', 'Deployment', 'PodMonitoring'}
    monitoring = docs['PodMonitoring']['spec']
    assert monitoring['selector']['matchLabels'] == deployment['selector']['matchLabels']
    assert deployment['template']['metadata']['labels'] == {
        **monitoring['selector']['matchLabels'],
        'service_name': 'sync-backfill-worker',
    }
    assert monitoring['targetLabels']['fromPod'] == [{'from': 'service_name', 'to': 'service_name'}]
    assert monitoring['endpoints'] == [{'port': 'http', 'path': '/metrics', 'interval': '15s'}]
    desired = yaml.safe_load((ROOT / 'backend/deploy/sync-backfill-worker.yaml').read_text())
    assert desired['admissionPercent'] == 0
    assert desired['nodePool']['config']['spot'] is False
    assert desired['nodePool']['config']['preemptible'] is False
    assert desired['nodePool']['autoscaling']['totalMaxNodeCount'] == 2


@pytest.mark.parametrize(
    'extra',
    [
        ['--set', 'image.digest=latest'],
        ['--set', 'replicaCount=3'],
        ['--set', 'worker.audience=https://different.run.app'],
    ],
)
def test_chart_refuses_unqualified_pilot(extra):
    assert render(*extra).returncode != 0
