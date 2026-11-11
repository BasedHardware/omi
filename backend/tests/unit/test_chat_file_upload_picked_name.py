"""POST /v1|/v2/files saves the name the user picked, not the uuid temp name (#15179).

The routes stream each upload through a uuid-named temp file
(``/tmp/<uuid32>_photo.png``) for path-traversal safety, and
``openai.files.create`` echoes the multipart filename it was given back as
``response.filename``. Sending it the bare temp handle made the provider record
— and therefore ``FileChat.name`` and the persisted doc — carry
``ef0c40fc..._photo.png`` instead of ``photo.png``.

The provider double answers with exactly what it was given, like production: a
bare file handle is answered with its basename (the uuid temp name), a
``(filename, fileobj)`` tuple with the tuple's name. If the upload path
regresses to sending the bare temp handle, these tests go red with the uuid
name stored.
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


def _provider_double(file_id):
    """Provider double: answers with the multipart filename it was given.

    Production ``openai.files.create`` echoes the filename back as
    ``response.filename``. The SDK's ``(filename, fileobj)`` tuple form carries
    the picked name; a bare handle carries the route's temp file, whose basename
    is ``<uuid32>_<picked name>`` — the defect's upstream source.
    """
    seen: dict[str, str] = {}

    def _create(*, file, purpose):
        if isinstance(file, tuple):
            seen['name'] = file[0]
        else:
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
    _create, seen = _provider_double('file-1')
    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=_create))

    response = client.post(route, files={'files': (filename, payload, mime)})

    assert response.status_code == 200
    # The provider record itself carries the picked name, not the uuid temp basename.
    assert seen['name'] == filename
    # So do the client answer and the persisted doc.
    assert response.json()[0]['name'] == filename
    assert response.json()[0]['openai_file_id'] == 'file-1'
    saved_files = module.chat_db.add_multi_files.call_args[0][1]
    assert [f['name'] for f in saved_files] == [filename]


def test_upload_without_picked_name_falls_back_to_provider_name(chat_client, monkeypatch, tmp_path):
    """Direct callers with no picked name keep the provider's filename.

    This is also the double's sabotage guard: the bare handle is answered with
    the uuid temp basename, exactly what the unfixed route stored.
    """
    chat_file = sys.modules['utils.other.chat_file']
    _create, seen = _provider_double('file-2')
    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=_create))
    doc = tmp_path / 'ef0c40fc9b98_photo.txt'
    doc.write_text('note')

    result = chat_file.FileChatTool.upload(doc)

    assert seen['name'] == 'ef0c40fc9b98_photo.txt'
    assert result['file_name'] == 'ef0c40fc9b98_photo.txt'


def test_upload_strips_directory_from_picked_name(chat_client, monkeypatch, tmp_path):
    """The picked name is user input; only its basename may reach the provider."""
    chat_file = sys.modules['utils.other.chat_file']
    _create, seen = _provider_double('file-3')
    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=_create))
    doc = tmp_path / 'ef0c40fc9b98_photo.txt'
    doc.write_text('note')

    result = chat_file.FileChatTool.upload(doc, file_name='../../photo.txt')

    assert seen['name'] == 'photo.txt'
    assert result['file_name'] == 'photo.txt'
