"""POST /v1|/v2/files saves the name the user picked, not the uuid temp name (#15179).

The routes stream each upload through a uuid-named temp file
(``/tmp/<uuid32>_photo.png``) for path-traversal safety, and the provider echoes
that temp name back as ``response.filename``. Storing it verbatim made the chat
UI show ``ef0c40fc...47d_photo.png`` instead of ``photo.png``.

The provider double below reproduces production faithfully: it answers with the
basename of the file handle it was given, exactly like ``openai.files.create``
does for a temp file. The route must still answer — and persist — the picked
name.
"""

import base64
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.unit import _chat_router_test_harness as harness
from tests.unit._chat_router_test_harness import BACKEND_DIR

PDF_BYTES = b'%PDF-1.1\n%%EOF\n'
# 1x1 PNG: real decodable image bytes so the thumbnail path runs like production.
PNG_BYTES = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
)


def _make_chat_client():
    saved = {k: v for k, v in sys.modules.items()}

    harness.install_package('models', BACKEND_DIR / 'models')
    harness.install_package('database', BACKEND_DIR / 'database')
    harness.install_package('utils', BACKEND_DIR / 'utils')
    harness.install_package('utils.other', BACKEND_DIR / 'utils' / 'other')
    harness.install_package('utils.sync', BACKEND_DIR / 'utils' / 'sync')
    harness.install_package('utils.stt', BACKEND_DIR / 'utils' / 'stt')
    harness.install_package('utils.llm', BACKEND_DIR / 'utils' / 'llm')
    harness.install_package('utils.retrieval', BACKEND_DIR / 'utils' / 'retrieval')

    harness.wire_common_stubs(harness.install_module)
    harness.install_module('models.app')

    # wire_common_stubs replaces chat_file with a MagicMock; this suite needs the real module,
    # because the picked-name fix lives in FileChatTool.upload.
    harness.load_real_module('utils.other.chat_file', BACKEND_DIR / 'utils' / 'other' / 'chat_file.py')

    chat_utils = harness.install_module('utils.chat', ModuleType('utils.chat'))
    for name in (
        'acquire_chat_session',
        'emit_stream_error_fallback',
        'initial_message_util',
        'process_voice_message_segment_stream',
        'resolve_voice_message_language',
        'transcribe_voice_message_segment',
        'transcribe_pcm_bytes',
    ):
        setattr(chat_utils, name, MagicMock())

    graph = harness.install_module('utils.retrieval.graph', ModuleType('utils.retrieval.graph'))
    graph.execute_chat_stream = MagicMock()
    graph.execute_graph = MagicMock()
    graph.execute_persona_chat_stream = MagicMock()

    sys.modules.pop('routers.chat', None)
    module = harness.load_real_module('routers.chat', BACKEND_DIR / 'routers' / 'chat.py')

    # The image path uploads generated thumbnails; the harness storage stub has no
    # upload_multi_chat_files until the suite adds one.
    module.storage.upload_multi_chat_files = MagicMock(return_value={})

    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app), module, saved


@pytest.fixture
def chat_client():
    client, module, saved = _make_chat_client()
    try:
        yield client, module
    finally:
        harness.cleanup(saved)


def _provider_echoing_temp_name(file_id):
    """Provider double: returns the basename of the handle it was given.

    Production ``openai.files.create`` receives the temp file opened from the
    route, so ``response.filename`` is ``<uuid32>_<picked name>`` — the defect's
    upstream source.
    """
    seen: dict[str, str] = {}

    def _create(*, file, purpose):
        seen['name'] = Path(file.name).name
        return SimpleNamespace(id=file_id, filename=seen['name'])

    return _create, seen


@pytest.mark.parametrize(
    'filename,mime,payload',
    [
        ('photo.png', 'image/png', PNG_BYTES),
        ('brief.pdf', 'application/pdf', PDF_BYTES),
    ],
)
@pytest.mark.parametrize('route', ['/v2/files', '/v1/files'])
def test_upload_answers_and_saves_the_picked_name(chat_client, monkeypatch, route, filename, mime, payload):
    client, module = chat_client
    chat_file = sys.modules['utils.other.chat_file']
    _create, seen = _provider_echoing_temp_name('file-1')
    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=_create))

    response = client.post(route, files={'files': (filename, payload, mime)})

    assert response.status_code == 200
    # Reproduction guard: the provider really answered with the uuid temp name.
    assert seen['name'] != filename
    assert seen['name'].endswith(f'_{filename}')
    # The client answer and the persisted doc keep the picked name instead.
    assert response.json()[0]['name'] == filename
    assert response.json()[0]['openai_file_id'] == 'file-1'
    saved_files = module.chat_db.add_multi_files.call_args[0][1]
    assert [f['name'] for f in saved_files] == [filename]


def test_upload_without_picked_name_falls_back_to_provider_name(chat_client, monkeypatch, tmp_path):
    """Direct callers with no picked name keep the provider's filename."""
    chat_file = sys.modules['utils.other.chat_file']
    _create, _seen = _provider_echoing_temp_name('file-2')
    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=_create))
    doc = tmp_path / 'ef0c40fc9b98_photo.txt'
    doc.write_text('note')

    result = chat_file.FileChatTool.upload(doc)

    assert result['file_name'] == 'ef0c40fc9b98_photo.txt'


def test_upload_strips_directory_from_picked_name(chat_client, monkeypatch, tmp_path):
    """The picked name is user input; only its basename may be stored."""
    chat_file = sys.modules['utils.other.chat_file']
    _create, _seen = _provider_echoing_temp_name('file-3')
    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=_create))
    doc = tmp_path / 'ef0c40fc9b98_photo.txt'
    doc.write_text('note')

    result = chat_file.FileChatTool.upload(doc, file_name='../../photo.txt')

    assert result['file_name'] == 'photo.txt'
