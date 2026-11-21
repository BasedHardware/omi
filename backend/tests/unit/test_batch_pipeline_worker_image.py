"""Synthetic projected credentials and API responses for the image-only rollout."""

import base64
import json
from unittest.mock import MagicMock

import pytest

from diarizer import worker_image
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import Scheduler

REPOSITORY = 'registry.example/batch'
OLD, NEW = ('sha256:' + digit * 64 for digit in 'ab')


def own_pod(name, digest):
    image = REPOSITORY + '@' + digest
    return {
        'metadata': {'name': name, 'namespace': 'synthetic', 'uid': name + '-uid'},
        'spec': {'containers': [{'name': 'worker', 'image': image}]},
        'status': {
            'containerStatuses': [
                {'name': 'other', 'imageID': REPOSITORY + '@' + NEW},
                {'name': 'worker', 'state': {'running': {'startedAt': '2026-11-20T00:00:00Z'}}, 'imageID': image},
            ]
        },
    }


def pod_api(monkeypatch, tmp_path, pod, *, status=200):
    meta = pod['metadata']
    claims = {'kubernetes.io': {'namespace': meta['namespace'], 'pod': {'name': meta['name'], 'uid': meta['uid']}}}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
    token = 'fixture.' + payload + '.fixture'
    (tmp_path / 'token').write_text(token)
    monkeypatch.setattr(worker_image, 'SERVICE_ACCOUNT', tmp_path)
    monkeypatch.setattr(worker_image.ssl, 'create_default_context', MagicMock())
    connection = MagicMock()
    monkeypatch.setattr(worker_image, 'HTTPSConnection', lambda *args, **kwargs: connection)
    response = connection.getresponse.return_value.__enter__.return_value
    response.status = status
    response.read.return_value = json.dumps({'items': [pod]}).encode()
    return connection, token


def test_mixed_pods_commit_their_own_digest_and_preserve_first_publication(monkeypatch, tmp_path):
    store = MemoryStore()
    queue, merge = Scheduler(store), OrderedMerge(store)
    workers = []
    for name, digest, io in [('old', OLD, 1), ('new', NEW, 2), ('unverified', None, 1)]:
        pod = own_pod(name, digest or OLD)
        api, token = pod_api(monkeypatch, tmp_path, pod, status=200 if digest else 403)
        worker, *_ = setup_worker(io_concurrency=io)
        worker.worker_image_digest = worker_image.producing_image_digest()
        api.request.assert_called_once_with(
            'GET',
            f'/api/v1/namespaces/synthetic/pods?fieldSelector=metadata.name%3D{name}&limit=1',
            headers={'Authorization': 'Bearer ' + token},
        )
        workers.append((worker, name, digest))

    for worker, name, digest in workers:
        work = item(name)
        queue.enqueue(work, 0)
        lease = queue.pull(1)[0]
        (result,) = worker.process_batch([lease.item])
        assert queue.complete(result, lease.token, 2)
        assert merge.commit_next(work.owner_id, 3)
        replay = WorkResult(result.segment_id, result.result_uri, result.outcome)
        assert queue.complete(replay, lease.token, 4)
        conflicting = WorkResult(
            result.segment_id, result.result_uri, result.outcome, worker_image_digest=NEW if digest == OLD else OLD
        )
        assert queue.complete(conflicting, lease.token, 5) == (digest is None)
        committed = merge.committed_result(name)['result']
        if digest:
            assert committed['worker_image_digest'] == digest
        else:
            assert committed == replay.to_dict()


@pytest.mark.parametrize(
    'fault', ['tag', 'different-id', 'wrong-uid', 'other-container', 'waiting', 'missing-token', 'malformed-token']
)
def test_unverified_identity_is_unknown(monkeypatch, tmp_path, fault):
    pod = own_pod('producer', OLD)
    api, _ = pod_api(monkeypatch, tmp_path, pod)
    status = pod['status']['containerStatuses'][1]
    if fault == 'tag':
        pod['spec']['containers'][0]['image'] = REPOSITORY + ':latest'
    elif fault == 'different-id':
        status['imageID'] = REPOSITORY + '@' + NEW
    elif fault == 'wrong-uid':
        pod['metadata']['uid'] = 'replacement-uid'
    elif fault == 'other-container':
        status['name'] = 'sidecar'
    elif fault == 'waiting':
        status['state'] = {'waiting': {}}
    elif fault == 'missing-token':
        (tmp_path / 'token').unlink()
    else:
        (tmp_path / 'token').write_text('invalid')
    api.getresponse.return_value.__enter__.return_value.read.return_value = json.dumps({'items': [pod]}).encode()
    assert worker_image.producing_image_digest() is None
