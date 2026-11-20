"""Pod-bound image proof and the worker -> lease completion -> ordered result path."""

import base64
from dataclasses import replace
import json
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from diarizer import worker_image
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler

A, B = ('sha256:' + digit * 64 for digit in 'ab')


def pod(digest):
    image = 'example.invalid/gpu@' + digest
    return {
        'metadata': {'namespace': 'batch', 'name': 'producer', 'uid': 'this-pod'},
        'spec': {'containers': [{'name': 'worker', 'image': image}]},
        'status': {
            'containerStatuses': [
                {'name': 'sidecar', 'imageID': B},
                {
                    'name': 'worker',
                    'state': {'running': {'startedAt': '2026-01-01T00:00:00Z'}},
                    'image': image,
                    'imageID': 'docker-pullable://' + image,
                },
            ]
        },
    }


@pytest.fixture
def api(tmp_path, monkeypatch):
    identity = {'kubernetes.io': {'namespace': 'batch', 'pod': {'name': 'producer', 'uid': 'this-pod'}}}
    payload = base64.urlsafe_b64encode(json.dumps(identity).encode()).decode().rstrip('=')
    (tmp_path / 'token').write_text(f'header.{payload}.signature')
    (tmp_path / 'namespace').write_text('batch')
    monkeypatch.setattr(worker_image, '_SERVICE_ACCOUNT', tmp_path)
    monkeypatch.setattr(worker_image.ssl, 'create_default_context', Mock())
    connection = Mock()
    monkeypatch.setattr(worker_image, 'HTTPSConnection', Mock(return_value=connection))
    response = connection.getresponse.return_value
    response.status = 200
    response.read.return_value = json.dumps({'items': [pod(A)]}).encode()
    return connection


@pytest.mark.parametrize('io_concurrency,digest', [(1, A), (3, B)])
def test_image_only_change_follows_completing_worker_through_ordered_commit(api, io_concurrency, digest):
    api.getresponse.return_value.read.return_value = json.dumps({'items': [pod(digest)]}).encode()
    worker, *_ = setup_worker(io_concurrency=io_concurrency)
    worker.worker_image_digest = worker_image.running_worker_digest()
    method, target = api.request.call_args.args
    assert method == 'GET'
    assert urlsplit(target).path == '/api/v1/namespaces/batch/pods'
    assert parse_qs(urlsplit(target).query) == {'fieldSelector': ['metadata.name=producer'], 'limit': ['1']}
    api.close.assert_called_once()
    store = MemoryStore()
    scheduler, merge = Scheduler(store), OrderedMerge(store)
    work = item('unit', duration=4)
    scheduler.enqueue(work, 0)
    (lease,) = scheduler.pull(0, 1)
    (result,) = worker.process_batch([lease.item])
    assert result.worker_image_digest == digest
    assert not scheduler.complete(result, 'stale-token', 1)
    assert scheduler.complete(result, lease.token, 1)
    # Lost completion acknowledgement, retried without optional telemetry.
    assert scheduler.complete(replace(result, worker_image_digest=None), lease.token, 1)
    assert merge.commit_next(work.owner_id, 2)['result']['worker_image_digest'] == digest
    # A replay cannot replace the committed producer.
    assert scheduler.complete(replace(result, worker_image_digest=B if digest == A else A), lease.token, 3)
    assert merge.committed_result(work.segment_id)['result']['worker_image_digest'] == digest


@pytest.mark.parametrize(
    'failure',
    [
        'wrong_uid',
        'wrong_namespace',
        'wrong_name',
        'other_image',
        'tag',
        'waiting',
        'absent',
        'denied',
        'timeout',
        'oversize',
        'bad_token',
    ],
)
def test_missing_or_unverified_provenance_stays_absent(api, failure):
    row = pod(A)
    status = row['status']['containerStatuses'][1]
    response = api.getresponse.return_value
    if failure.startswith('wrong_'):
        row['metadata'][failure.removeprefix('wrong_')] = 'other'
    elif failure == 'other_image':
        status['imageID'] = 'example.invalid/gpu@' + B
    elif failure == 'tag':
        row['spec']['containers'][0]['image'] = 'example.invalid/gpu:latest'
    elif failure == 'waiting':
        status['state'] = {'waiting': {}}
    elif failure == 'denied':
        response.status = 403
    elif failure == 'timeout':
        api.getresponse.side_effect = TimeoutError()
    elif failure == 'bad_token':
        (worker_image._SERVICE_ACCOUNT / 'token').write_text('unbound')
    response.read.return_value = json.dumps({'items': [] if failure == 'absent' else [row]}).encode()
    if failure == 'oversize':
        response.read.return_value = b' ' * (worker_image._MAX_RESPONSE + 1)
    assert worker_image.running_worker_digest() is None


def test_runtime_config_id_requires_the_running_image_pin(api):
    row = pod(A)
    status = row['status']['containerStatuses'][1]
    status['imageID'] = 'containerd://' + B
    api.getresponse.return_value.read.return_value = json.dumps({'items': [row]}).encode()
    assert worker_image.running_worker_digest() == A
    status['image'] = 'example.invalid/gpu:latest'
    api.getresponse.return_value.read.return_value = json.dumps({'items': [row]}).encode()
    assert worker_image.running_worker_digest() is None


def test_later_proof_never_backfills_legacy_completion():
    store = MemoryStore()
    scheduler = Scheduler(store)
    work = item('legacy')
    scheduler.enqueue(work, 0)
    (lease,) = scheduler.pull(0, 1)
    result = WorkResult(work.segment_id, 'encrypted://result', worker_image_digest='invalid')
    assert 'worker_image_digest' not in result.to_dict()
    assert scheduler.complete(result, lease.token, 1)
    assert scheduler.complete(replace(result, worker_image_digest=B), lease.token, 1)
    assert 'worker_image_digest' not in OrderedMerge(store).commit_next(work.owner_id, 2)['result']
