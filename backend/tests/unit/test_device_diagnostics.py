from __future__ import annotations

import base64
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.device_diagnostics import (
    MAX_BUNDLE_BYTES,
    MAX_ENCODED_BYTES,
    MAX_REQUEST_BYTES,
    DiagnosticsUpload,
    router,
    upload_uid,
)
from utils.other import device_diagnostics_storage

TEST_UID = 'test-user-123'
TEST_ADMIN_KEY = 'test-secret-admin-key'


def _make_app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def client():
    app = _make_app()
    app.dependency_overrides[upload_uid] = lambda: TEST_UID
    return TestClient(app)


# ---------------------------------------------------------------------------
# Router: upload_device_diagnostics
# ---------------------------------------------------------------------------


def test_upload_diagnostics_success(client, monkeypatch):
    monkeypatch.setattr(device_diagnostics_storage, 'save_bundle', lambda uid, body: '0123456789AB')

    valid_payload = {'schema_version': 2, 'data': 'sample_diagnostics'}
    encoded = base64.b64encode(json.dumps(valid_payload).encode()).decode()

    response = client.post('/v1/mobile/device-diagnostics', json={'bundle_base64': encoded})
    assert response.status_code == 201
    assert response.json() == {'ticket': '0123456789AB'}


def test_upload_diagnostics_rejects_oversized_encoded(client):
    oversized = 'A' * (MAX_ENCODED_BYTES + 1)
    response = client.post('/v1/mobile/device-diagnostics', json={'bundle_base64': oversized})
    assert response.status_code == 413
    assert 'too large' in response.json()['detail']


def test_upload_diagnostics_rejects_oversized_decoded(client):
    large_body = b'x' * (MAX_BUNDLE_BYTES + 1)
    encoded = base64.b64encode(large_body).decode()
    response = client.post('/v1/mobile/device-diagnostics', json={'bundle_base64': encoded})
    assert response.status_code == 413
    assert 'too large' in response.json()['detail']


def test_upload_rejects_oversized_stream_before_json_validation(client):
    response = client.post(
        '/v1/mobile/device-diagnostics',
        content=b' ' * (MAX_REQUEST_BYTES + 1),
        headers={'Content-Type': 'application/json'},
    )
    assert response.status_code == 413


def test_upload_diagnostics_invalid_base64(client):
    response = client.post('/v1/mobile/device-diagnostics', json={'bundle_base64': '!!!not_base64!!!'})
    assert response.status_code == 400
    assert 'Invalid base64' in response.json()['detail']


def test_upload_diagnostics_invalid_json(client):
    encoded = base64.b64encode(b'this is not json').decode()
    response = client.post('/v1/mobile/device-diagnostics', json={'bundle_base64': encoded})
    assert response.status_code == 400
    assert 'must be JSON' in response.json()['detail']


def test_upload_diagnostics_unsupported_schema_version(client):
    payload = {'schema_version': 1, 'data': 'old'}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    response = client.post('/v1/mobile/device-diagnostics', json={'bundle_base64': encoded})
    assert response.status_code == 400
    assert 'Unsupported diagnostics schema' in response.json()['detail']


def test_upload_diagnostics_non_dict_json(client):
    payload = [1, 2, 3]
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    response = client.post('/v1/mobile/device-diagnostics', json={'bundle_base64': encoded})
    assert response.status_code == 400
    assert 'Unsupported diagnostics schema' in response.json()['detail']


def test_upload_diagnostics_empty_uid():
    app = _make_app()
    app.dependency_overrides[upload_uid] = lambda: '   '
    cli = TestClient(app)

    payload = {'schema_version': 2}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    response = cli.post('/v1/mobile/device-diagnostics', json={'bundle_base64': encoded})
    assert response.status_code == 401
    assert 'Authentication required' in response.json()['detail']


def test_upload_diagnostics_storage_value_error(client, monkeypatch):
    def _mock_save(uid, body):
        raise ValueError('Invalid or empty uid')

    monkeypatch.setattr(device_diagnostics_storage, 'save_bundle', _mock_save)

    payload = {'schema_version': 2}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    response = client.post('/v1/mobile/device-diagnostics', json={'bundle_base64': encoded})
    assert response.status_code == 400
    assert 'Invalid or empty uid' in response.json()['detail']


def test_upload_diagnostics_storage_unexpected_error(client, monkeypatch):
    def _mock_save(uid, body):
        raise RuntimeError('GCS connection reset')

    monkeypatch.setattr(device_diagnostics_storage, 'save_bundle', _mock_save)

    payload = {'schema_version': 2}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    response = client.post('/v1/mobile/device-diagnostics', json={'bundle_base64': encoded})
    assert response.status_code == 500
    assert 'Failed to save diagnostics bundle' in response.json()['detail']


# ---------------------------------------------------------------------------
# Router: read_device_diagnostics
# ---------------------------------------------------------------------------


def test_read_diagnostics_invalid_ticket_format(client, monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', TEST_ADMIN_KEY)
    response = client.get('/v1/admin/device-diagnostics/short', headers={'X-Admin-Key': TEST_ADMIN_KEY})
    assert response.status_code == 404
    assert 'Ticket not found' in response.json()['detail']


def test_read_diagnostics_missing_admin_key(client, monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', TEST_ADMIN_KEY)
    response = client.get('/v1/admin/device-diagnostics/0123456789AB')
    assert response.status_code == 422  # Missing required header


def test_read_diagnostics_invalid_admin_key(client, monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', TEST_ADMIN_KEY)
    response = client.get('/v1/admin/device-diagnostics/0123456789AB', headers={'X-Admin-Key': 'wrong-key'})
    assert response.status_code == 403
    assert 'Invalid admin key' in response.json()['detail']


def test_read_diagnostics_ticket_not_found(client, monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', TEST_ADMIN_KEY)
    monkeypatch.setattr(device_diagnostics_storage, 'read_bundle', lambda ticket: None)

    response = client.get('/v1/admin/device-diagnostics/0123456789AB', headers={'X-Admin-Key': TEST_ADMIN_KEY})
    assert response.status_code == 404
    assert 'Ticket not found' in response.json()['detail']


def test_read_diagnostics_success(client, monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', TEST_ADMIN_KEY)
    sample_bundle = {'schema_version': 2, 'battery': 98, 'logs': ['ble connected']}
    monkeypatch.setattr(device_diagnostics_storage, 'read_bundle', lambda ticket: sample_bundle)

    response = client.get(
        '/v1/admin/device-diagnostics/0123456789AB',
        headers={'X-Admin-Key': TEST_ADMIN_KEY, 'X-Admin-User': 'admin_alice'},
    )
    assert response.status_code == 200
    assert response.json() == {'bundle': sample_bundle}


def test_read_diagnostics_storage_error(client, monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', TEST_ADMIN_KEY)

    def _mock_read(ticket):
        raise RuntimeError('Storage timeout')

    monkeypatch.setattr(device_diagnostics_storage, 'read_bundle', _mock_read)

    response = client.get('/v1/admin/device-diagnostics/0123456789AB', headers={'X-Admin-Key': TEST_ADMIN_KEY})
    assert response.status_code == 500
    assert 'Failed to retrieve diagnostics bundle' in response.json()['detail']


# ---------------------------------------------------------------------------
# Storage: save_bundle & read_bundle resilience
# ---------------------------------------------------------------------------


def test_storage_save_bundle_invalid_uid():
    with pytest.raises(ValueError, match='Invalid or empty uid'):
        device_diagnostics_storage.save_bundle('', b'{}')

    with pytest.raises(ValueError, match='Invalid or empty uid'):
        device_diagnostics_storage.save_bundle('../evil', b'{}')

    with pytest.raises(ValueError, match='Invalid or empty uid'):
        device_diagnostics_storage.save_bundle('user/subpath', b'{}')


def test_storage_save_bundle_invalid_bundle_type():
    with pytest.raises(TypeError, match='bundle must be bytes'):
        device_diagnostics_storage.save_bundle('valid-uid', 'not-bytes')


def test_storage_save_bundle_success(monkeypatch):
    uploaded = {}

    class MockBlob:
        def __init__(self, path):
            self.path = path

        def upload_from_string(self, data, content_type=None):
            uploaded[self.path] = data

    class MockBucket:
        def blob(self, path):
            return MockBlob(path)

    class MockContext:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr('utils.other.storage.get_private_cloud_sync_bucket', lambda: MockBucket())
    monkeypatch.setattr('utils.other.storage.owner_storage_write_gate', lambda uid, bucket: MockContext())

    ticket = device_diagnostics_storage.save_bundle('user-100', b'{"schema_version": 2}')
    assert len(ticket) == 12
    assert f'diagnostics/user-100/{ticket}.json' in uploaded
    assert f'diagnostics/tickets/{ticket}.json' in uploaded


def test_storage_read_bundle_handles_corrupt_lookup_json(monkeypatch):
    class MockBlob:
        def exists(self):
            return True

        def download_as_bytes(self):
            return b'not valid json{{{'

    class MockBucket:
        def blob(self, path):
            return MockBlob()

    monkeypatch.setattr('utils.other.storage.get_private_cloud_sync_bucket', lambda: MockBucket())
    result = device_diagnostics_storage.read_bundle('0123456789AB')
    assert result is None


def test_storage_read_bundle_handles_malformed_reference_schema(monkeypatch):
    class MockBlob:
        def exists(self):
            return True

        def download_as_bytes(self):
            return json.dumps({'invalid_key': 123}).encode()

    class MockBucket:
        def blob(self, path):
            return MockBlob()

    monkeypatch.setattr('utils.other.storage.get_private_cloud_sync_bucket', lambda: MockBucket())
    result = device_diagnostics_storage.read_bundle('0123456789AB')
    assert result is None


def test_storage_read_bundle_path_mismatch(monkeypatch):
    class MockBlob:
        def exists(self):
            return True

        def download_as_bytes(self):
            return json.dumps({'uid': 'user-1', 'path': 'diagnostics/user-2/wrong.json'}).encode()

    class MockBucket:
        def blob(self, path):
            return MockBlob()

    monkeypatch.setattr('utils.other.storage.get_private_cloud_sync_bucket', lambda: MockBucket())
    result = device_diagnostics_storage.read_bundle('0123456789AB')
    assert result is None


def test_storage_read_bundle_corrupt_payload(monkeypatch):
    class MockBlob:
        def __init__(self, path):
            self.path = path

        def exists(self):
            return True

        def download_as_bytes(self):
            if 'tickets' in self.path:
                return json.dumps({'uid': 'user-1', 'path': 'diagnostics/user-1/0123456789AB.json'}).encode()
            return b'invalid bundle bytes{{'

    class MockBucket:
        def blob(self, path):
            return MockBlob(path)

    monkeypatch.setattr('utils.other.storage.get_private_cloud_sync_bucket', lambda: MockBucket())
    result = device_diagnostics_storage.read_bundle('0123456789AB')
    assert result is None


def test_storage_read_bundle_success(monkeypatch):
    payload_data = {'schema_version': 2, 'hw_rev': 'v3'}

    class MockBlob:
        def __init__(self, path):
            self.path = path

        def exists(self):
            return True

        def download_as_bytes(self):
            if 'tickets' in self.path:
                return json.dumps({'uid': 'user-1', 'path': 'diagnostics/user-1/0123456789AB.json'}).encode()
            return json.dumps(payload_data).encode()

    class MockBucket:
        def blob(self, path):
            return MockBlob(path)

    monkeypatch.setattr('utils.other.storage.get_private_cloud_sync_bucket', lambda: MockBucket())
    result = device_diagnostics_storage.read_bundle('0123456789AB')
    assert result == payload_data


def test_storage_read_bundle_propagates_storage_error(monkeypatch):
    class BrokenBlob:
        def exists(self):
            raise RuntimeError('GCS transport outage')

    class BrokenBucket:
        def blob(self, path):
            return BrokenBlob()

    monkeypatch.setattr('utils.other.storage.get_private_cloud_sync_bucket', lambda: BrokenBucket())
    with pytest.raises(RuntimeError, match='GCS transport outage'):
        device_diagnostics_storage.read_bundle('0123456789AB')


def test_private_storage_round_trip_and_owner_path(monkeypatch):
    objects = {}

    class Blob:
        def __init__(self, name):
            self.name = name

        def upload_from_string(self, data, content_type=None):
            objects[self.name] = data.encode() if isinstance(data, str) else data

        def exists(self):
            return self.name in objects

        def download_as_bytes(self):
            return objects[self.name]

    class Bucket:
        def blob(self, name):
            return Blob(name)

    class MockContext:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    mock_bucket = Bucket()
    monkeypatch.setattr('utils.other.storage.get_private_cloud_sync_bucket', lambda: mock_bucket)
    monkeypatch.setattr('utils.other.storage.owner_storage_write_gate', lambda uid, bucket: MockContext())
    monkeypatch.setattr(device_diagnostics_storage.secrets, 'token_hex', lambda n: 'abcdef123456')

    ticket = device_diagnostics_storage.save_bundle('owner', b'{"schema_version": 2}')
    assert ticket == 'ABCDEF123456'
    assert 'diagnostics/owner/ABCDEF123456.json' in objects
    assert 'diagnostics/tickets/ABCDEF123456.json' in objects
    assert device_diagnostics_storage.read_bundle(ticket) == {'schema_version': 2}
    assert device_diagnostics_storage.read_bundle('FFFFFFFFFFFF') is None
