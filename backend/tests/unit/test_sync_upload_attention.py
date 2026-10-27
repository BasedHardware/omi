"""Real HTTP multipart admission and the no-audio boundary, without cloud IO."""

from io import BytesIO

import pytest
from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient

from utils.multipart import MultipartMaxPartSizeRoute, max_part_size
from utils.sync.empty_upload import empty_framed_clip


@pytest.mark.parametrize(
    'body,empty',
    [(b'', True), (b'\x01', True), (b'\x01\0\0\0', True), (b'\x01\0\0\0\x42', False), (b'\0' * 25000, False)],
)
def test_no_complete_frame_boundary_keeps_tiny_audio(body, empty):
    stream = BytesIO(body)
    stream.seek(min(1, len(body)))
    position = stream.tell()
    assert empty_framed_clip(stream) is empty
    assert stream.tell() == position


@pytest.fixture
def client():
    app = FastAPI()
    app.router.route_class = MultipartMaxPartSizeRoute

    @app.post('/v2/sync-local-files')
    @max_part_size(32)
    async def upload(files: list[UploadFile] = File(...)):
        return {'files': len(files)}

    return TestClient(app)


def test_small_valid_multipart_is_not_refused(client):
    assert client.post('/v2/sync-local-files', files=[('files', ('audio.bin', b'12345'))]).status_code == 200


def test_missing_boundary_has_closed_reason_even_for_small_body(client):
    result = client.post('/v2/sync-local-files', content=b'123', headers={'Content-Type': 'multipart/form-data'})
    assert result.status_code == 400
    assert result.json()['code'] == 'malformed_multipart'


def test_part_limit_remains_bounded_and_reports_reason(client):
    result = client.post('/v2/sync-local-files', files=[('files', ('audio.bin', b'x' * 33))])
    assert result.status_code == 400
    assert result.json()['code'] == 'too_large'


def test_invalid_small_boundary_body_is_typed_400(client):
    result = client.post(
        '/v2/sync-local-files',
        content=b'not-a-boundary',
        headers={'Content-Type': 'multipart/form-data; boundary=expected'},
    )
    assert result.status_code == 400
    assert result.json()['code'] == 'malformed_multipart'
