"""POST /v1|/v2/files keeps the name the user picked, not the backend temp name.

The routes write uploads to ``/tmp/<uuid>_<name>`` and FileChatTool.upload sent that
path to the provider, so ``response.filename`` — and therefore FileChat.name and the
saved record — came back as ``<uuid>_photo.png`` instead of ``photo.png``.
"""

import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from tests.unit import _chat_router_test_harness as harness
from tests.unit.test_chat_file_upload_unsupported import _make_chat_client


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


def _provider_filename(file) -> str:
    # The SDK sends either a bare file object (temp name wins) or a
    # (filename, fileobj) tuple (picked name wins); the API echoes it back.
    if isinstance(file, tuple):
        return file[0]
    return Path(file.name).name


@pytest.mark.parametrize('route', ['/v2/files', '/v1/files'])
def test_uploaded_chat_file_keeps_picked_name(chat_client, route, monkeypatch):
    client, module = chat_client
    chat_file = sys.modules['utils.other.chat_file']
    sent: dict[str, object] = {}

    def _create(*, file, purpose):
        sent['filename'] = _provider_filename(file)
        return SimpleNamespace(id='file-img', filename=sent['filename'])

    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=_create))
    monkeypatch.setattr(
        module.storage,
        'upload_multi_chat_files',
        lambda file_paths, uid: {path: f'https://storage.test/{uid}/{Path(path).name}' for path in file_paths},
        raising=False,
    )

    response = client.post(route, files={'files': ('photo.png', _png(), 'image/png')})

    assert response.status_code == 200
    assert sent['filename'] == 'photo.png'
    assert response.json()[0]['name'] == 'photo.png'


def test_upload_sends_picked_name_to_provider(chat_client, tmp_path, monkeypatch):
    """FileChatTool.upload is the shared path: file_name overrides the temp basename."""
    _client, _module = chat_client  # fixture loads the real utils.other.chat_file under stubs
    chat_file = sys.modules['utils.other.chat_file']
    sent: dict[str, object] = {}

    def _create(*, file, purpose):
        sent['filename'] = _provider_filename(file)
        return SimpleNamespace(id='file-1', filename=sent['filename'])

    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=_create))

    temp_path = tmp_path / 'ef0c40fc9b98_photo.png'
    temp_path.write_bytes(_png())

    result = chat_file.FileChatTool.upload(temp_path, file_name='photo.png')

    assert sent['filename'] == 'photo.png'
    assert result['file_name'] == 'photo.png'
