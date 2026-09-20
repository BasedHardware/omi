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


@pytest.mark.parametrize('route', ['/v2/files', '/v1/files'])
def test_uploaded_chat_file_keeps_the_name_the_user_picked(chat_client, route, monkeypatch):
    client, module = chat_client
    chat_file = sys.modules['utils.other.chat_file']
    monkeypatch.setattr(
        chat_file.openai,
        'files',
        SimpleNamespace(create=lambda *, file, purpose: SimpleNamespace(id='file-img', filename=Path(file.name).name)),
    )
    monkeypatch.setattr(
        module.storage,
        'upload_multi_chat_files',
        lambda file_paths, uid: {
            Path(path).name: f'https://storage.test/{uid}/{Path(path).name}' for path in file_paths
        },
        raising=False,
    )

    response = client.post(route, files={'files': ('photo.png', _png(), 'image/png')})

    assert response.status_code == 200
    assert response.json()[0]['name'] == 'photo.png'
