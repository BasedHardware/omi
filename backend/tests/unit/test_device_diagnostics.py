import base64
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import device_diagnostics as route
from utils.other import device_diagnostics_storage


def _client(uid=None):
    app = FastAPI()
    app.include_router(route.router)
    if uid is not None:
        app.dependency_overrides[route.upload_uid] = lambda: uid
    return TestClient(app)


def _payload(size=0):
    body = {'schema_version': 2, 'padding': 'x' * size}
    return {'bundle_base64': base64.b64encode(json.dumps(body).encode()).decode()}


def test_upload_requires_auth():
    response = _client().post('/v1/mobile/device-diagnostics', json=_payload())
    assert response.status_code in {401, 403}


def test_upload_size_and_schema(monkeypatch):
    monkeypatch.setattr(route.device_diagnostics_storage, 'save_bundle', lambda uid, body: 'ABCDEF123456')
    client = _client('test-user')
    assert client.post('/v1/mobile/device-diagnostics', json=_payload()).json() == {'ticket': 'ABCDEF123456'}
    assert client.post('/v1/mobile/device-diagnostics', json=_payload(4 * 1024 * 1024)).status_code == 413
    assert client.post('/v1/mobile/device-diagnostics', json={'bundle_base64': '%%%'}).status_code == 400
    old = base64.b64encode(b'{"schema_version":1}').decode()
    assert client.post('/v1/mobile/device-diagnostics', json={'bundle_base64': old}).status_code == 400


def test_admin_read_requires_key(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'private-key')
    monkeypatch.setattr(route.device_diagnostics_storage, 'read_bundle', lambda ticket: {'schema_version': 2})
    client = _client()
    path = '/v1/admin/device-diagnostics/ABCDEF123456'
    assert client.get(path).status_code in {401, 403, 422}
    assert client.get(path, headers={'X-Admin-Key': 'wrong'}).status_code == 403
    assert client.get(path, headers={'X-Admin-Key': 'private-key'}).json() == {'bundle': {'schema_version': 2}}
    assert client.get('/v1/admin/device-diagnostics/invalid', headers={'X-Admin-Key': 'private-key'}).status_code == 404


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

    class Client:
        def bucket(self, name):
            assert name == device_diagnostics_storage.storage.private_cloud_sync_bucket
            return Bucket()

    monkeypatch.setattr(device_diagnostics_storage.storage, '_get_storage_client', lambda: Client())
    monkeypatch.setattr(device_diagnostics_storage.secrets, 'token_hex', lambda n: 'abcdef123456')
    ticket = device_diagnostics_storage.save_bundle('owner', b'{"schema_version":2}')
    assert ticket == 'ABCDEF123456'
    assert 'diagnostics/owner/ABCDEF123456.json' in objects
    assert device_diagnostics_storage.read_bundle(ticket) == {'schema_version': 2}
    assert device_diagnostics_storage.read_bundle('FFFFFFFFFFFF') is None
