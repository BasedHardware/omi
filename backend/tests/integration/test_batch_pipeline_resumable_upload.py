"""Real GCS SDK protocol against an in-process synthetic transport, no network."""

import json
from urllib.parse import parse_qs, urlsplit

from google.auth.credentials import AnonymousCredentials
from google.cloud import storage
import pytest
from requests import Response

from utils.batch_pipeline import artifacts
from utils.batch_pipeline.contracts import Priority, WorkItem


@pytest.mark.integration
def test_hour_staging_retries_same_registered_resumable_session(monkeypatch):
    registered = []
    requests = []
    committed = 0
    failed = False
    session_url = 'https://synthetic.invalid/upload/session-only'
    total_bytes = 3600 * 16000 * 2 + 44 + len(artifacts.MAGIC) + 28

    class Transport:
        is_mtls = False

        def request(self, method, url, data=None, headers=None, timeout=None, **kwargs):
            nonlocal committed, failed
            requests.append((method, url, len(data), timeout))
            response = Response()
            response.headers['content-type'] = 'application/json'
            response._content = b'{}'
            if method == 'POST':
                assert parse_qs(urlsplit(url).query)['uploadType'] == ['resumable']
                assert parse_qs(urlsplit(url).query)['ifGenerationMatch'] == ['0']
                assert json.loads(data)['name'] == registered[0].split('/', 3)[3]
                response.status_code = 200
                response.headers['location'] = session_url
            else:
                assert method == 'PUT' and url == session_url
                assert len(data) <= artifacts.UPLOAD_CHUNK_BYTES
                if not failed:
                    failed = True
                    response.status_code = 503
                    return response
                committed += len(data)
                if committed == total_bytes:
                    response.status_code = 200
                    response._content = b'{"generation":"123"}'
                else:
                    assert committed < total_bytes
                    response.status_code = 308
                    response.headers['range'] = f'bytes=0-{committed - 1}'
            return response

    monkeypatch.setattr(artifacts, 'UPLOAD_RETRY', artifacts.UPLOAD_RETRY.with_delay(initial=0.001, maximum=0.001))
    client = storage.Client(project='demo-synthetic', credentials=AnonymousCredentials(), _http=Transport())
    context = artifacts.ProtectionContext('enhanced', 0)
    store = artifacts.ArtifactStore(
        client,
        bucket='synthetic-batch-bucket',
        namespace='batch_pipeline_test_resumable',
        authorize=lambda _: context,
        key_for_owner=lambda _: b'a' * 32,
        register_artifact=lambda item, uri, kind, ctx: registered.append(uri),
    )
    item = WorkItem('synthetic-hour', 'synthetic-owner', 100, 'pending', 3600, Priority.FRESH, privacy_generation=0)
    uri = store.stage_audio(item, b'R' * (3600 * 16000 * 2 + 44))
    assert uri == registered[0] + '#123' and len(registered) == 1
    assert committed == total_bytes and failed
    assert sum(method == 'POST' for method, *_ in requests) == 1
    assert sum(method == 'PUT' for method, *_ in requests) > 10
    assert all(timeout == artifacts.UPLOAD_TIMEOUT for *_, timeout in requests)
