"""POST /v1|/v2/files must upload an image's thumbnail and clean it up.

Since uploads moved to the system temp dir, the thumbnail is written next to the temp file there,
but the routes handed storage only the bare thumbnail name and storage read `./{name}` from the
working directory. The upload failed (logged and swallowed), every image was saved with an empty
thumbnail, the file in the temp dir was never removed, and /v1/files 500'd on its unconditional
unlink of the relative path.
"""

import io
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from tests.unit import _chat_router_test_harness as harness
from tests.unit.test_chat_file_upload_unsupported import _make_chat_client
from utils.other import storage as storage_mod


@pytest.fixture
def chat_client():
    client, module, saved = _make_chat_client()
    try:
        yield client, module
    finally:
        harness.cleanup(saved)


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(buffer, format='PNG')
    return buffer.getvalue()


@pytest.mark.parametrize('route', ['/v2/files', '/v1/files'])
def test_image_upload_stores_the_thumbnail_and_removes_the_temp_copy(chat_client, route, monkeypatch):
    client, module = chat_client
    chat_file = sys.modules['utils.other.chat_file']
    monkeypatch.setattr(
        chat_file.openai,
        'files',
        SimpleNamespace(create=lambda *, file, purpose: SimpleNamespace(id='file-img', filename=Path(file.name).name)),
    )
    uploaded = []

    def _upload(file_paths, uid):
        uploaded.extend(file_paths)
        return {
            Path(path).name: f'https://storage.test/{uid}/{Path(path).name}'
            for path in file_paths
            if Path(path).exists()
        }

    monkeypatch.setattr(module.storage, 'upload_multi_chat_files', _upload, raising=False)

    response = client.post(route, files={'files': ('photo.png', _png(), 'image/png')})

    assert response.status_code == 200
    assert response.json()[0]['thumbnail'].startswith('https://storage.test/')
    assert len(uploaded) == 1
    assert not Path(uploaded[0]).exists()


def test_chat_files_are_uploaded_from_the_given_path(monkeypatch, tmp_path):
    thumbnail = tmp_path / 'abc_photo_thumbnail.png'
    thumbnail.write_bytes(b'png')
    bucket = MagicMock()
    monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: MagicMock(bucket=lambda _name: bucket))
    monkeypatch.setattr(storage_mod, 'owner_storage_write_gate', lambda *_args, **_kwargs: nullcontext())

    urls = storage_mod.upload_multi_chat_files([str(thumbnail)], 'user-1')

    bucket.blob.assert_called_once_with('user-1/abc_photo_thumbnail.png')
    bucket.blob.return_value.upload_from_filename.assert_called_once_with(str(thumbnail))
    assert list(urls) == ['abc_photo_thumbnail.png']
